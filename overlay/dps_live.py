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


def tcp_payload(ip, tcp):
    """Só os dados de verdade do segmento. Pacotes pequenos (ACK puro) chegam com o "enchimento" do
    Ethernet (bytes zero até 60 bytes) e o scapy junta esse enchimento ao payload; antes ele entrava no
    fluxo como se fosse dado do jogo, desalinhava as mensagens e ~20% delas se perdiam."""
    raw = bytes(tcp.payload)
    try:
        n = int(ip.len) - int(ip.ihl) * 4 - int(tcp.dataofs) * 4
    except (TypeError, ValueError):
        return raw
    return raw[:max(0, n)] if 0 <= n < len(raw) else raw


class MessageParser:
    """Recebe bytes do fluxo do servidor (em ordem) e devolve mensagens (opcode, corpo)."""

    def __init__(self):
        self.buf = bytearray()

    def resync(self):
        self.buf.clear()

    MAX_MSG = 16384
    MAX_INFLATE = 4 * 1024 * 1024    # LZ4 expande no máximo ~255x: 16 KB comprimidos cabem folgado aqui

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
                if not 0 < size <= self.MAX_INFLATE:
                    return                              # tamanho absurdo: não aloca memória à toa
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
    """Junta os segmentos TCP de um sentido na ordem certa.

    O número de sequência do TCP tem 32 bits e dá a volta depois de 4 GB; as contas são feitas módulo 2^32
    (antes, numa sessão muito longa, tudo depois da volta era tratado como retransmissão e o medidor parava).
    """
    MOD = 1 << 32
    MAX_PENDING = 512            # segmentos fora de ordem guardados no máximo
    JUMP = 1 << 24               # salto maior que isso = conexão nova / fluxo perdido: recomeça daqui

    def __init__(self, parser):
        self.parser = parser
        self.next_seq = None
        self.pending = {}
        self.gap_since = None

    def _diff(self, seq):
        """seq - next_seq com sinal, considerando a volta dos 32 bits."""
        d = (seq - self.next_seq) % self.MOD
        return d - self.MOD if d >= self.MOD // 2 else d

    def _trim(self):
        """Segmentos guardados que começam antes do ponto atual (sobrepostos por uma retransmissão maior):
        corta o pedaço já lido ou descarta. True se algum passou a começar exatamente no ponto atual."""
        hit = False
        for k in list(self.pending):
            d = self._diff(k)
            if d < 0:
                data = self.pending.pop(k)
                if -d < len(data):
                    rest = data[-d:]
                    if len(rest) > len(self.pending.get(self.next_seq, b"")):
                        self.pending[self.next_seq] = rest
                    hit = True
        return hit and self.next_seq in self.pending

    def add(self, seq, data):
        out = []
        if self.next_seq is None:
            self.next_seq = seq
        d = self._diff(seq)
        if abs(d) > self.JUMP:                       # outro fluxo: recomeça sem misturar
            self.parser.resync()
            self.pending.clear()
            self.next_seq, d = seq, 0
        if d < 0:                                    # retransmissão
            if -d >= len(data):
                return out
            seq, data = self.next_seq, data[-d:]
        seq %= self.MOD
        if len(data) > len(self.pending.get(seq, b"")):   # retransmissão maior (juntou segmentos) ganha
            self.pending[seq] = data
        while True:
            dd = self.pending.pop(self.next_seq, None)
            if dd is None:
                if not self._trim():
                    break
                continue
            out += self.parser.feed(dd)
            self.next_seq = (self.next_seq + len(dd)) % self.MOD
            self.gap_since = None
        if self.pending:
            if self.gap_since is None:
                self.gap_since = time.time()
            if time.time() - self.gap_since > 1.0 or len(self.pending) > self.MAX_PENDING:
                # pacote perdido: recomeça no próximo que chegou
                s = min(self.pending, key=self._diff)
                self.parser.resync()
                self.next_seq = s
                self.gap_since = None
                return out + self.add(s, self.pending.pop(s))
        return out


# ---------------------------------------------------------------- luta / estatísticas
class Fight:
    """resets=True: uma luta (zera depois de FIGHT_TIMEOUT sem golpes).
    resets=False: a sessão inteira (soma todas as lutas; o tempo conta só enquanto está lutando)."""

    def __init__(self, resets=True):
        self.resets = resets
        self.reset()

    def reset(self):
        self.start = None
        self.last = None
        self.active = 0.0     # segundos lutando (pausas maiores que FIGHT_TIMEOUT não contam)
        self.pair = {}        # (atacante, alvo) -> [dano, golpes, críticos, múltiplos]
        self.heal = {}        # quem curou -> total
        self.act = {}         # jogador -> [último golpe, segundos lutando] (DPS de cada um pelo próprio tempo)
        self.skills = {}      # (jogador, habilidade) -> [dano, golpes, críticos, cura, curas]

    def _touch(self, t):
        if self.last is not None:
            gap = t - self.last
            if gap > FIGHT_TIMEOUT:
                if self.resets:
                    self.reset()
            elif gap > 0:
                self.active += gap
        if self.start is None:
            self.start = t
        self.last = t

    def add(self, t, atk, tgt, dmg, crit=False, multi=False, skill=None, mine=True):
        if mine or self.start is None:
            self._touch(t)            # só você e o seu grupo mantêm a luta aberta
        a = self.act.setdefault(atk, [t, 0.0])
        gap = t - a[0]
        if 0 < gap <= FIGHT_TIMEOUT:
            a[1] += gap
        a[0] = t
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
        return max(1.0, self.active)

    def player_time(self, a):
        """Tempo que esse jogador passou batendo (para o DPS dele)."""
        v = self.act.get(a)
        return max(1.0, v[1]) if v else max(1.0, self.elapsed())

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
    world_events = Signal(object)  # [(tipo, dict)]: abates, mapa atual (world_live.WorldTracker)

    def __init__(self, server_hosts=None):
        super().__init__()
        self.hosts = server_hosts or []
        self._run = True
        self.names = {}
        self.fight = Fight()
        self.session = Fight(resets=False)
        self.view = "fight"       # "fight" = luta atual; "session" = tudo desde que zerou
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
        self.world = None         # WorldTracker (criado no start, para não pesar quem só usa o DPS)
        # invocações (ventania da Bittercold Wind, espíritos do Elementalista, aura do Clérigo...): o jogo
        # cria uma "criatura" separada (0x3641) que bate com a habilidade do dono. Antes ela virava um
        # jogador a mais, sem nome, no medidor. Agora o dano vai para quem invocou.
        self.spawned = {}         # entidade criada como NPC/invocação -> hora em que apareceu
        self.owner = {}           # invocação -> jogador dono
        self.casts = {}           # família da habilidade (id // 10000) -> [(hora, quem usou)]
        self.pending_summon = {}  # invocação sem dono ainda -> golpes guardados
        self.summons = set()      # ids que se mostraram invocações (a morte delas não é abate de monstro)

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
            data = tcp_payload(p[IP], tcp)
            if not data:
                return
            key = (p[IP].src, tcp.sport, p[IP].dst, tcp.dport)
            if key not in streams:
                parser_for[key] = MessageParser()
                streams[key] = TcpStream(parser_for[key])
            try:
                for op, body in streams[key].add(tcp.seq, data):
                    self.handle(op, body)
            except Exception as e:              # um pacote estranho nunca pode derrubar a leitura
                self._warn(e)

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
                self.flush_world()
            except Exception as e:
                self._warn(e)
            try:
                f = self.current()
                key = (f.start, f.last, len(f.pair), self.find_self(), self.mode, self.view)
                active = f.last is not None and time.time() - f.last < FIGHT_TIMEOUT
                if key != getattr(self, "_last_key", None) or active != getattr(self, "_last_active", None):
                    self._last_key, self._last_active = key, active
                    self.updated.emit(self.snapshot())
            except Exception as e:          # nunca deixa o medidor congelar por um erro de leitura
                self.status.emit(f"aviso: {e}")
        try:
            sniffer.stop()
        except Exception:
            pass

    def enable_world(self):
        if self.world is None:
            from world_live import WorldTracker
            with self.lock:
                self.world = WorldTracker(self)

    def flush_world(self):
        if self.world is None:
            return
        with self.lock:
            self.world.poll()
            ev = self.world.take_events()
        if ev:
            self.world_events.emit(ev)

    def world_state(self):
        """(mapa, posição) atuais, ou (None, None)."""
        if self.world is None:
            return None, None
        with self.lock:
            return self.world.world, self.world.my_position()

    # ------------------------------------------------------------ eventos
    def handle(self, op, body):
        with self.lock:
            self._handle(op, body)

    def _warn(self, e):
        now = time.time()
        if now - getattr(self, "_warn_t", 0) > 30:       # não inunda a interface com o mesmo aviso
            self._warn_t = now
            self.status.emit(f"aviso: {type(e).__name__}: {e}")

    SUMMON_BEFORE = 5.0      # o dono usa a habilidade até ~5 s antes da invocação aparecer
    SUMMON_AFTER = 0.6

    def _owner_of(self, summon, skill):
        """Dono de uma invocação: quem usou uma habilidade da mesma família logo antes dela aparecer."""
        if summon in self.owner:
            return self.owner[summon]
        t_sp = self.spawned.get(summon)
        if t_sp is None or not skill_class(skill):
            return None
        best = None
        for t, who in self.casts.get(skill // 10000, ()):
            if t_sp - self.SUMMON_BEFORE <= t <= t_sp + self.SUMMON_AFTER and who not in self.spawned:
                if best is None or t > best[0]:
                    best = (t, who)
        if best:
            self.owner[summon] = best[1]
            return best[1]
        return None

    def _track_entities(self, op, body, now):
        if op == 0x3641:                                   # NPC / invocação apareceu
            eid, _ = varint(body, 0)
            if len(self.spawned) > 20_000:
                self.spawned = {e: t for e, t in self.spawned.items() if now - t < 600}
                self.owner = {e: o for e, o in self.owner.items() if e in self.spawned}
            self.spawned[eid] = now
            self.owner.pop(eid, None)                      # id reaproveitado: esquece o dono antigo
            self.summons.discard(eid)
            self.pending_summon.pop(eid, None)
            if len(self.pending_summon) > 200:
                self.pending_summon.clear()
        elif op == 0x3642:                                 # sumiu
            eid, _ = varint(body, 0)
            self.spawned.pop(eid, None)
            self.owner.pop(eid, None)
            self.pending_summon.pop(eid, None)
        elif op == 0x3802:                                 # alguém usou uma habilidade
            caster, i = varint(body, 0)
            if caster in self.spawned or len(body) < i + 5:
                return
            skill = int.from_bytes(body[i + 1:i + 5], "little")
            if skill_class(skill):
                lst = self.casts.setdefault(skill // 10000, [])
                lst.append((now, caster))
                if len(lst) > 8:
                    del lst[:-8]

    def _apply_hit(self, h, now):
        tgt, atk, skill, dmg = h["tgt"], h["atk"], h["skill"], h["dmg"]
        c = skill_class(skill)
        if c:
            self.cls[atk] = c
        if tgt == atk:
            if dmg and dmg > 0:
                # efeito em si mesmo com valor = cura (ex.: roubo de vida). A habilidade é anotada,
                # mas só vale como cura em alvos que não são inimigos (senão o dano dela sumiria)
                self.heal_skills.add(skill)
                self.fight.add_heal(now, atk, tgt, dmg, skill)
                self.session.add_heal(now, atk, tgt, dmg, skill)
            return
        if not dmg or dmg <= 0:
            if c and (atk, tgt) not in self.harmed:   # buff/aura de jogador em outro = mesmo grupo
                self._link(atk, tgt)
            return
        if is_known_heal(skill) or (skill in self.heal_skills and tgt not in self.enemies):
            self._link(atk, tgt)
            self.fight.add_heal(now, atk, tgt, dmg, skill)
            self.session.add_heal(now, atk, tgt, dmg, skill)
            return
        if len(self.harmed) > 200_000:            # sessão muito longa: não cresce sem limite
            self.harmed.clear()
        self.harmed.add((atk, tgt))
        if self.world is not None:
            self.world.on_damage(atk, tgt, now)
        if c:
            if len(self.enemies) > 100_000:
                self.enemies.clear()
            self.enemies.add(tgt)                  # quem leva dano de jogador é inimigo/monstro
        self._unlink(atk, tgt)
        mine = bool(c) and self._mine(atk)
        self.fight.add(now, atk, tgt, dmg, h["crit"], h["multi"], skill, mine)
        self.session.add(now, atk, tgt, dmg, h["crit"], h["multi"], skill, mine)

    def _handle(self, op, body):
        if self.world is not None:
            try:
                self.world.handle(op, body)
            except Exception as e:
                self._warn(e)
        try:
            if op in (0x3641, 0x3642, 0x3802):
                self._track_entities(op, body, time.time())
            if op == 0x3804:
                h = decode_hit(body)
                now = time.time()
                summon = h["atk"]
                if summon in self.spawned and skill_class(h["skill"]):
                    if len(self.summons) > 5000:
                        self.summons.clear()
                    self.summons.add(summon)
                    owner = self._owner_of(summon, h["skill"])
                    if owner is None:
                        # ainda não deu para saber de quem é: guarda um pouco e entrega quando descobrir
                        lst = self.pending_summon.setdefault(summon, [])
                        if len(lst) < 60:
                            lst.append((h, now))
                        return
                    for hb, tb in self.pending_summon.pop(summon, ()):
                        hb["atk"] = owner
                        self._apply_hit(hb, tb)
                    h["atk"] = owner
                self._apply_hit(h, now)
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
                # só passa por jogadores: um debuff sem dano num monstro ligava você ao monstro e o monstro
                # a qualquer estranho que batesse nele, e o estranho piscava no medidor até o 1º dano
                if y not in seen and y in self.cls:
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

    def _mine(self, atk):
        """Golpe seu / do seu grupo? (sem saber quem é você, vale qualquer jogador)"""
        me = self.find_self()
        if me is None:
            return True
        if atk == me:
            return True
        now = time.time()
        if now - getattr(self, "_grp_t", 0) > 1.0:
            self._grp, self._grp_t = self.group(me), now
        return atk in self._grp

    def current(self):
        return self.session if self.view == "session" else self.fight

    def _snapshot(self):
        f = self.current()
        me = self.find_self()
        mine = self.group(me)
        if self.mode == "party":
            players = mine      # sem saber quem é você ainda, não mostra ninguém (antes mostrava todos)
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
                         "dps": d / f.player_time(a),
                         "crit": c / h if h else 0, "multi": mu / h if h else 0,
                         "heal": f.heal.get(a, 0), "me": a == me})
        return {"elapsed": f.elapsed(), "rows": rows, "skills": self.skill_rows([r["id"] for r in rows]),
                "found_me": me is not None, "my_heal": f.heal.get(me, 0) if me is not None else 0,
                "active": f.last is not None and time.time() - f.last < FIGHT_TIMEOUT}

    def skill_rows(self, ids):
        """Por jogador: habilidades que deram dano ou curaram, já com nome/ícone, juntando os níveis."""
        import skills_db
        out = {}
        for (a, sk), v in self.current().skills.items():
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
            self.session.reset()
