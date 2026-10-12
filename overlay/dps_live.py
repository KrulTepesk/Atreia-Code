"""Medidor de DPS ao vivo.

Lê (só lê) o tráfego TCP que o servidor do jogo manda para o PC, via Npcap/scapy:
- monta o fluxo do servidor na ordem certa;
- separa as mensagens (tamanho em varint; corpo = tamanho - 4);
- abre os blocos comprimidos (ff ff + tamanho + LZ4);
- mensagem 0x3804 = golpe (alvo, atacante, habilidade, dano);
- 0x3645 = jogador que apareceu por perto (id + nome); 0x8d04 = abate (inclui o nome de quem matou).
Nada é enviado nem alterado. O formato pode mudar com patches do jogo.
"""
import struct
import threading
import time

from PySide6.QtCore import QThread, Signal

GAME_PORT = 13328
FIGHT_TIMEOUT = 8.0          # segundos sem golpes = fim da luta


def varint(b, i):
    v = s = 0
    while True:
        c = b[i]
        v |= (c & 0x7F) << s
        i += 1
        s += 7
        if c < 0x80:
            return v, i


# ---------------------------------------------------------------- decodificação
def decode_hit(b):
    """Corpo da 0x3804 -> dict(alvo, atacante, habilidade, valor|None, crítico, múltiplo).

    O valor já é o total do golpe (com crítico e golpes extras). Conferido contra o HP do alvo.
    flags 0x20 = golpe múltiplo / dupla chance: no fim vem a lista dos golpes extras (só o detalhe).
    """
    i = 0
    tgt, i = varint(b, i)
    flags = b[i] | (b[i + 1] << 8)
    i += 2
    atk, i = varint(b, i)
    skill = int.from_bytes(b[i:i + 4], "little")
    i += 4
    kind = b[i + 1]                  # 2 = normal, 3 = crítico
    i += 2
    if flags & 0x02:
        i += 3
    i += 4 + 4 + 2                   # marca, nº do golpe, tipo
    dmg = None
    if flags & 0x04:
        dmg, i = varint(b, i)
    extra = 0
    if flags & 0x20:
        try:
            j = i + (1 if (flags & 0x10) and not (flags & 0x02) else 0)
            extra = b[j]
        except IndexError:
            extra = 1
    return {"tgt": tgt, "atk": atk, "skill": skill, "dmg": dmg,
            "crit": kind == 3, "multi": extra > 0}


# classe pelo começo do id da habilidade (8 dígitos): 11 Gladiador ... 18 Chanter. Monstros usam outros ids.
CLASS_BY_PREFIX = {11: "gl", 12: "te", 13: "as", 14: "ra", 15: "so", 16: "el", 17: "cl", 18: "ch"}


def skill_class(skill):
    if 10_000_000 <= skill < 20_000_000:
        return CLASS_BY_PREFIX.get(skill // 1_000_000)
    return None


# curas conhecidas pelo banco de habilidades (id base = sem os 4 últimos dígitos)
HEAL_BASES = {
    17090000, 17100000, 17120000, 17270000, 17320000, 17800000,   # Clérigo: regeneração, Healing Light...
    18120000, 18170000, 18710000,                                  # Chanter: Recuperation, Healing Touch...
    15760000, 16750000, 13790000, 14790000, 15790000, 16790000,   # passivas que recuperam vida
}
# ids exatos já vistos como cura (inclui a regeneração dos bonecos de treino)
HEAL_SKILLS = {1010000, 17800001, 15760007, 18720001}


def is_known_heal(skill):
    return skill in HEAL_SKILLS or skill // 10000 * 10000 in HEAL_BASES


def decode_names(op, b):
    """Retorna (id, nome) se a mensagem traz o nome de um jogador."""
    try:
        if op == 0x3645:
            pid, i = varint(b, 0)
            k = b.find(b"\x07", i, i + 12)
            if k < 0:
                return None
            n = b[k + 1]
            s = b[k + 2:k + 2 + n]
        elif op == 0x8D04:
            _tg, i = varint(b, 0)
            i += 4
            pid, i = varint(b, i)
            i += 2
            n = b[i]
            s = b[i + 1:i + 1 + n]
        else:
            return None
        if 2 <= len(s) <= 16 and s.isascii() and s.isalnum():
            return pid, s.decode()
    except Exception:
        pass
    return None


class MessageParser:
    """Recebe bytes do fluxo do servidor (em ordem) e devolve mensagens (opcode, corpo)."""

    def __init__(self):
        self.buf = bytearray()

    def resync(self):
        self.buf.clear()

    MAX_MSG = 16384

    def _chain(self, b):
        """Percorre mensagens em b; retorna (lista de (ini, fim) dos corpos, bytes consumidos, ok)."""
        k, spans = 0, []
        while k < len(b):
            try:
                L, j = varint(b, k)
            except IndexError:
                return spans, k, True           # varint incompleto: espera mais dados
            n = L - 4
            if n < 0 or n > self.MAX_MSG:
                return spans, k, False          # fora do alinhamento
            if j + n > len(b):
                return spans, k, True           # mensagem incompleta: espera mais dados
            spans.append((j, j + n))
            k = j + n
        return spans, k, True

    def feed(self, data):
        out = []
        joined = bytes(self.buf) + data
        spans, used, ok = self._chain(joined)
        if self.buf and (not ok or used != len(joined)):
            # o resto anterior pode estar desalinhado: se o pacote novo fecha certinho sozinho, usa ele
            s2, u2, ok2 = self._chain(data)
            if ok2 and u2 == len(data) and s2:
                joined, spans, used, ok = data, s2, u2, True
        if not ok:
            for a, b in spans:
                self._emit(joined[a:b], out)
            self.buf = bytearray()              # descarta o lixo; realinha no próximo pacote
            return out
        for a, b in spans:
            self._emit(joined[a:b], out)
        self.buf = bytearray(joined[used:])
        return out

    def _emit(self, body, out, depth=0):
        if body[:2] == b"\xff\xff" and depth < 3:
            try:
                import lz4.block
                size = struct.unpack("<I", body[2:6])[0]
                inner = lz4.block.decompress(body[6:], uncompressed_size=size)
            except Exception:
                return
            k = 0
            while k < len(inner):
                try:
                    L, j = varint(inner, k)
                except IndexError:
                    return
                n = L - 4
                if n < 0 or j + n > len(inner):
                    return
                self._emit(inner[j:j + n], out, depth + 1)
                k = j + n
        elif len(body) >= 2:
            out.append((body[0] | (body[1] << 8), body[2:]))


class TcpStream:
    """Junta os segmentos TCP de um sentido na ordem certa."""

    def __init__(self, parser):
        self.parser = parser
        self.next_seq = None
        self.pending = {}
        self.gap_since = None

    def add(self, seq, data):
        out = []
        if self.next_seq is None:
            self.next_seq = seq
        if seq < self.next_seq:                      # retransmissão
            over = self.next_seq - seq
            if over >= len(data):
                return out
            seq, data = self.next_seq, data[over:]
        self.pending[seq] = data
        while self.next_seq in self.pending:
            d = self.pending.pop(self.next_seq)
            out += self.parser.feed(d)
            self.next_seq += len(d)
            self.gap_since = None
        if self.pending:
            if self.gap_since is None:
                self.gap_since = time.time()
            elif time.time() - self.gap_since > 1.0:  # pacote perdido: recomeça no próximo
                s = min(self.pending)
                self.parser.resync()
                self.next_seq = s
                self.gap_since = None
                return out + self.add(s, self.pending.pop(s))
        return out


# ---------------------------------------------------------------- luta / estatísticas
class Fight:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start = None
        self.last = None
        self.pair = {}        # (atacante, alvo) -> [dano, golpes, críticos, múltiplos]
        self.heal = {}        # quem curou -> total
        self.skills = {}      # (jogador, habilidade) -> [dano, golpes, críticos, cura, curas]

    def _touch(self, t):
        if self.last is not None and t - self.last > FIGHT_TIMEOUT:
            self.reset()
        if self.start is None:
            self.start = t
        self.last = t

    def add(self, t, atk, tgt, dmg, crit=False, multi=False, skill=None):
        self._touch(t)
        v = self.pair.setdefault((atk, tgt), [0, 0, 0, 0])
        v[0] += dmg
        v[1] += 1
        v[2] += crit
        v[3] += multi
        if skill is not None:
            s = self.skills.setdefault((atk, skill), [0, 0, 0, 0, 0])
            s[0] += dmg
            s[1] += 1
            s[2] += crit

    def add_heal(self, t, atk, tgt, val, skill=None):
        if self.start is None:
            return                      # cura fora de luta não abre luta
        self.heal[atk] = self.heal.get(atk, 0) + val
        if skill is not None:
            s = self.skills.setdefault((atk, skill), [0, 0, 0, 0, 0])
            s[3] += val
            s[4] += 1

    def elapsed(self):
        if self.start is None:
            return 0
        return max(1.0, self.last - self.start)

    def players(self, known, mine=frozenset()):
        """Separa os dois lados (quem bate em quem). Seu lado = o seu e de quem você/seus aliados curam;
        sem pista, os nomes conhecidos ou o lado com mais dano causado. Serve para PvE e PvP."""
        adj, dealt = {}, {}
        for (a, t), v in self.pair.items():
            adj.setdefault(a, set()).add(t)
            adj.setdefault(t, set()).add(a)
            dealt[a] = dealt.get(a, 0) + v[0]
        side, comps = {}, []
        for start in adj:
            if start in side:
                continue
            side[start] = 0
            comp, stack = [start], [start]
            while stack:
                x = stack.pop()
                for y in adj[x]:
                    if y not in side:
                        side[y] = 1 - side[x]
                        comp.append(y)
                        stack.append(y)
            comps.append(comp)
        out = set()
        for comp in comps:
            score = [0, 0]
            for x in comp:
                if x in mine:
                    score[side[x]] += 10 ** 15
                elif x in known:
                    score[side[x]] += 10 ** 9
                score[side[x]] += dealt.get(x, 0)
            good = 0 if score[0] >= score[1] else 1
            out |= {x for x in comp if side[x] == good and x in dealt}
        return out


class DpsReader(QThread):
    """Escuta o servidor do jogo e emite o estado da luta a cada ~0,5 s."""
    updated = Signal(object)       # dict com a luta atual
    status = Signal(str)

    def __init__(self, server_hosts=None):
        super().__init__()
        self.hosts = server_hosts or []
        self._run = True
        self.names = {}
        self.fight = Fight()
        self.self_id = None
        self.self_name = ""
        self.auto_self = None
        self.heal_skills = set(HEAL_SKILLS)
        self.lock = threading.RLock()   # o sniffer escreve numa thread e o painel lê em outra
        self.cls = {}             # entidade -> código da classe
        self.links = {}           # buffs/curas entre jogadores (grupo)
        self.harmed = set()       # (atacante, alvo) que já tiveram dano: nunca são grupo
        self.enemies = set()      # quem já levou dano de habilidade de jogador
        self.mode = "party"       # "party" = você + grupo; "all" = todos os jogadores por perto

    def stop(self):
        self._run = False
        self.wait(3000)

    def run(self):
        try:
            from scapy.all import IP, TCP, AsyncSniffer, conf
        except Exception as e:
            self.status.emit(f"scapy: {e}")
            return
        streams = {}
        parser_for = {}

        def on_pkt(p):
            if IP not in p or TCP not in p:
                return
            tcp = p[TCP]
            if tcp.sport != GAME_PORT and not (self.hosts and p[IP].src in self.hosts):
                return
            data = bytes(tcp.payload)
            if not data:
                return
            key = (p[IP].src, tcp.sport, p[IP].dst, tcp.dport)
            if key not in streams:
                parser_for[key] = MessageParser()
                streams[key] = TcpStream(parser_for[key])
            for op, body in streams[key].add(tcp.seq, data):
                self.handle(op, body)

        flt = f"tcp and src port {GAME_PORT}"
        if self.hosts:
            flt = "tcp and (" + " or ".join(f"src host {h}" for h in self.hosts) + f" or src port {GAME_PORT})"
        try:
            iface = conf.route.route(self.hosts[0])[0] if self.hosts else None
            sniffer = AsyncSniffer(iface=iface, filter=flt, prn=on_pkt, store=False)
            sniffer.start()
        except Exception as e:
            self.status.emit(str(e))
            return
        self.status.emit("Lendo o tráfego do jogo...")
        while self._run:
            time.sleep(0.5)
            try:
                self.updated.emit(self.snapshot())
            except Exception as e:          # nunca deixa o medidor congelar por um erro de leitura
                self.status.emit(f"aviso: {e}")
        try:
            sniffer.stop()
        except Exception:
            pass

    # ------------------------------------------------------------ eventos
    def handle(self, op, body):
        with self.lock:
            self._handle(op, body)

    def _handle(self, op, body):
        try:
            if op == 0x3804:
                h = decode_hit(body)
                tgt, atk, skill, dmg = h["tgt"], h["atk"], h["skill"], h["dmg"]
                c = skill_class(skill)
                if c:
                    self.cls[atk] = c
                now = time.time()
                if tgt == atk:
                    if dmg and dmg > 0:
                        # efeito em si mesmo com valor = cura (ex.: roubo de vida). A habilidade é anotada,
                        # mas só vale como cura em alvos que não são inimigos (senão o dano dela sumiria)
                        self.heal_skills.add(skill)
                        self.fight.add_heal(now, atk, tgt, dmg, skill)
                    return
                if not dmg or dmg <= 0:
                    if c and (atk, tgt) not in self.harmed:   # buff/aura de jogador em outro = mesmo grupo
                        self._link(atk, tgt)
                    return
                if is_known_heal(skill) or (skill in self.heal_skills and tgt not in self.enemies):
                    self._link(atk, tgt)
                    self.fight.add_heal(now, atk, tgt, dmg, skill)
                    return
                self.harmed.add((atk, tgt))
                if c:
                    self.enemies.add(tgt)                  # quem leva dano de jogador é inimigo/monstro
                self._unlink(atk, tgt)
                self.fight.add(now, atk, tgt, dmg, h["crit"], h["multi"], skill)
            elif op == 0x364A:
                # mensagem que o servidor só manda sobre o seu próprio personagem
                self.auto_self, _ = varint(body, 0)
            elif op in (0x3645, 0x8D04):
                r = decode_names(op, body)
                if r:
                    pid, name = r
                    if op == 0x8D04 and self.self_name and name.lower() == self.self_name.lower():
                        self.self_id = pid
                    if op == 0x3645 or pid not in self.names:
                        self.names[pid] = name
        except Exception:
            pass

    def _link(self, a, b):
        self.links.setdefault(a, set()).add(b)
        self.links.setdefault(b, set()).add(a)

    def _unlink(self, a, b):
        self.links.get(a, set()).discard(b)
        self.links.get(b, set()).discard(a)

    def group(self, me):
        """Você + quem troca buff/cura com você (e com eles), ao longo da sessão."""
        if me is None:
            return set()
        seen, stack = {me}, [me]
        while stack:
            for y in self.links.get(stack.pop(), ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return seen

    def find_self(self):
        if self.self_id is None and self.self_name:
            for pid, n in self.names.items():
                if n.lower() == self.self_name.lower():
                    self.self_id = pid
        return self.self_id if self.self_id is not None else self.auto_self

    def snapshot(self):
        with self.lock:
            return self._snapshot()

    def _snapshot(self):
        f = self.fight
        me = self.find_self()
        mine = self.group(me)
        if self.mode == "party" and me is not None:
            players = mine
        else:
            players = f.players(self.names, mine) & set(self.cls)   # só quem usa habilidade de classe
        st = {}
        for (a, _t), v in f.pair.items():
            if a in players:
                s_ = st.setdefault(a, [0, 0, 0, 0])
                for k in range(4):
                    s_[k] += v[k]
        order = sorted(st.items(), key=lambda kv: -kv[1][0])
        top = order[:8]
        if me in st and all(a != me for a, _ in top):
            top = order[:7] + [(me, st[me])]       # você sempre aparece
        rows = []
        for a, (d, h, c, mu) in top:
            rows.append({"id": a, "name": self.names.get(a, ""), "cls": self.cls.get(a), "dmg": d, "hits": h,
                         "crit": c / h if h else 0, "multi": mu / h if h else 0,
                         "heal": f.heal.get(a, 0), "me": a == me})
        return {"elapsed": f.elapsed(), "rows": rows, "skills": self.skill_rows([r["id"] for r in rows]),
                "found_me": me is not None, "my_heal": f.heal.get(me, 0) if me is not None else 0,
                "active": f.last is not None and time.time() - f.last < FIGHT_TIMEOUT}

    def skill_rows(self, ids):
        """Por jogador: habilidades que deram dano ou curaram, já com nome/ícone, juntando os níveis."""
        import skills_db
        out = {}
        for (a, sk), v in self.fight.skills.items():
            if a not in ids:
                continue
            key, cls, name, icon = skills_db.lookup(sk)
            row = out.setdefault(a, {}).setdefault(key, {"skill": key, "cls": cls, "name": name, "icon": icon,
                                                         "dmg": 0, "hits": 0, "crit": 0, "heal": 0,
                                                         "heals": 0, "shield": 0})
            row["dmg"] += v[0]
            row["hits"] += v[1]
            row["crit"] += v[2]
            row["heal"] += v[3]
            row["heals"] += v[4]
        return {a: sorted(d.values(), key=lambda r: -(r["dmg"] + r["heal"])) for a, d in out.items()}

    def reset(self):
        with self.lock:
            self.fight.reset()
