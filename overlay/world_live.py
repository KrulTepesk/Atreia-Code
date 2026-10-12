"""O que acontece em volta, lido do mesmo tráfego do medidor de DPS.

- Posição dos monstros perto de você (0x371a/0x371b/0x371c) e a sua (quando você usa uma habilidade, 0x3802).
- Morte de monstro: o HP chega a 0 (0x8d00) e, logo depois, 0x8d04 diz quem ficou com o abate
  (id + nome do personagem; tudo zero quando ninguém do seu lado).
- Qual monstro morreu: o servidor não manda o "tipo" do monstro, mas manda a posição. Como temos todos os
  pontos de nascimento de cada monstro (data/mobs.json), o ponto mais perto diz quem era. Os mesmos pontos
  dizem em qual mapa você está.

- PvP: quando um jogador morre (HP 0 / 0x8d04), quem levou o abate vem na 0x8d04. Se foi você,
  é abate; se você bateu nele nos últimos segundos e outro levou, é assistência. Sem crédito no pacote, vale
  o último golpe.

Coordenadas: no tráfego o eixo Y é invertido em relação ao mobs.json → guardamos sempre (x, -y).
"""
import json
import math
import os
import struct
import time

from config import BASE_DIR

CELL = 4000.0            # grade para achar o ponto de nascimento mais perto rápido
MATCH = 2500.0           # monstro andando: aceita até essa distância do ponto de nascimento
BOSS_MATCH = 5000.0      # chefes andam mais (e têm 1 ponto só)
CREDIT_WAIT = 3.0
PVP_WAIT = 1.0           # jogador morto: espera o crédito do abate (chega junto, mas dá uma folga)
ASSIST_WINDOW = 15.0     # bateu no jogador até 15 s antes da morte e outro levou o abate = assistência
LAST_HIT_WINDOW = 3.0    # sem crédito no pacote: o último golpe (até 3 s antes) decide
BOSS_HP = 3_000_000      # acima disso é chefe (monstros comuns ficam bem abaixo)        # espera o "quem levou o abate" até 3 s depois do HP zerar


def varint(b, i):
    v = s = 0
    while True:
        c = b[i]
        v |= (c & 0x7F) << s
        i += 1
        s += 7
        if c < 0x80:
            return v, i



def parse_credit(b):
    """0x8d04 -> (morto, template, id do matador, nome do matador) ou None.

    morto | template u32 (0 = jogador/invocação) | matador | servidor u16 | tam | nome | tam | legião | ...
    Tudo zero depois do morto = ninguém levou o abate.
    """
    try:
        eid, i = varint(b, 0)
        tpl = struct.unpack_from("<I", b, i)[0]
        killer, j = varint(b, i + 4)
        if not killer:
            return eid, tpl, None, ""
        j += 2                                  # servidor (u16: 7e 05, 66 09...)
        n = b[j]
        if n == 0 or n > 40 or j + 1 + n > len(b):
            return eid, tpl, None, ""
        return eid, tpl, killer, b[j + 1:j + 1 + n].decode("utf-8", "replace")
    except (IndexError, struct.error):
        return None

def _xyz(b, i):
    if i + 12 > len(b):
        return None
    x, y, z = struct.unpack_from("<3f", b, i)
    if not all(math.isfinite(v) for v in (x, y, z)):
        return None
    if abs(x) > 600000 or abs(y) > 600000 or abs(z) > 200000 or (abs(x) < 1 and abs(y) < 1):
        return None
    return x, -y              # → sistema do mobs.json


class Spawns:
    """Pontos de nascimento de todos os monstros, por mapa."""

    def __init__(self, path=None):
        with open(path or os.path.join(BASE_DIR, "data", "mobs.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.suggest = d.get("suggest", {})
        self.grid = {}            # mundo -> {(cx, cy): [(x, y, nome, categoria)]}
        self.by_name = {}         # (mundo, nome) -> coords
        for wid, mobs in d["worlds"].items():
            g = self.grid.setdefault(wid, {})
            for name, cat, co in mobs:
                self.by_name[(wid, name)] = (cat, co)
                for k in range(0, len(co) - 1, 2):
                    x, y = co[k], co[k + 1]
                    g.setdefault((int(x // CELL), int(y // CELL)), []).append((x, y, name, cat))

    def nearest(self, wid, x, y, maxd=MATCH, cat=None):
        g = self.grid.get(wid)
        if not g:
            return None
        best, bd = None, maxd
        r = int(maxd // CELL) + 1
        cx, cy = int(x // CELL), int(y // CELL)
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                for sx, sy, name, c in g.get((i, j), ()):
                    if cat and c != cat:
                        continue
                    dd = math.hypot(sx - x, sy - y)
                    if dd < bd:
                        best, bd = (name, c, dd), dd
        return best

    def guess_world(self, points):
        """Mapa cujos pontos de nascimento mais combinam com as posições vistas (mediana da distância)."""
        points = [(x, y) for x, y in points if abs(x) > 1000 or abs(y) > 1000]    # (0,0) = lixo
        if len(points) < 6:
            return None, None
        res = []
        for wid in self.grid:
            ds = []
            for x, y in points:
                n = self.nearest(wid, x, y, maxd=3000)
                ds.append(n[2] if n else 3000)
            ds.sort()
            res.append((ds[len(ds) // 2], wid))
        res.sort()
        med, wid = res[0]
        # nada combina bem, ou dois mapas combinam quase igual (as coordenadas do Abismo cruzam com as
        # dos outros mapas): melhor não chutar
        if med > 900 or (len(res) > 1 and res[1][0] - med < max(200, med * 0.6)):
            return None, None
        return wid, med


class WorldTracker:
    """Alimentado pelo DpsReader (mesma thread/lock). Gera eventos de abate em self.events."""

    def __init__(self, reader, spawns=None):
        self.r = reader
        self.sp = spawns or Spawns()
        self.pos = {}            # entidade -> (x, y, t)
        self.dead = {}           # entidade -> hora em que o HP zerou (aguardando quem levou o abate)
        self.credit = {}         # entidade -> (id do matador, nome)
        self.maxhp = {}          # entidade -> maior HP visto (chefes têm muito mais vida)
        self.done = set()
        self.me = None           # (x, y, t)
        self.world = None
        self.world_t = 0
        self.events = []         # [(tipo, dict)]
        self._last_guess = 0
        # PvP
        self.hits = {}           # alvo -> {atacante: hora do último golpe com dano}
        self.last_hit = {}       # alvo -> (atacante, hora)
        self.pdead = {}          # jogador -> hora da morte (aguardando crédito)
        self.pcredit = {}        # jogador -> (id do matador, nome)
        self.pdone = {}          # jogador -> hora em que a morte já foi tratada (evita repetir)
        self._last_prune = 0

    # ------------------------------------------------------------ mensagens
    def handle(self, op, b, now=None):
        now = now or time.time()
        try:
            if op in (0x371A, 0x371B, 0x371C):
                eid, i = varint(b, 0)
                if op == 0x371A:
                    p = _xyz(b, i + 2)
                else:
                    p = _xyz(b, i + 1) if b[i] == 4 else _xyz(b, i + 2)
                if p and not self._is_player(eid):
                    self.pos[eid] = (p[0], p[1], now)
            elif op == 0x3802:
                # quem usou | 00 | habilidade (4) | seq (1) | flags (1) | alvo | f32 | [x y z do alvo se flags&2]
                caster, i = varint(b, 0)
                j = i + 6
                flags = b[j]
                tgt, k = varint(b, j + 1)
                if flags & 2:
                    p = _xyz(b, k + 4)
                    if p:
                        me = self.r.find_self()
                        if tgt == me:
                            self.me = (p[0], p[1], now)
                        elif not self._is_player(tgt):
                            self.pos[tgt] = (p[0], p[1], now)
                            if caster == me:
                                self.me = (p[0], p[1], now)      # você está perto do que acertou
            elif op == 0x8D00:
                eid, i = varint(b, 0)
                if b[i:i + 3] == b"\x02\x01\x00" and len(b) >= i + 7:
                    hp = struct.unpack_from("<I", b, i + 3)[0]
                    if hp > self.maxhp.get(eid, 0):
                        self.maxhp[eid] = hp
                    if hp == 0:
                        if self._is_player(eid):
                            self._player_died(eid, now)
                        elif eid not in self.done:
                            self.dead.setdefault(eid, now)
            elif op == 0x8D04:
                c = parse_credit(b)
                if c:
                    eid, tpl, killer, name = c
                    if self._is_player(eid) or eid in self.pdead:
                        self._player_died(eid, now)
                        if killer:
                            self.pcredit[eid] = (killer, name)
                    elif killer:
                        if eid in self.dead or eid in self.pos or eid in self.maxhp:
                            self.credit[eid] = (killer, name)
                            self.dead.setdefault(eid, now)
                    elif eid in self.dead:
                        self.credit.setdefault(eid, (None, ""))
            elif op == 0x900D:
                # alma de pet obtida: n | n × (id do pet u32, quantidade u32)   (ex.: 01 2a040000 01000000)
                n = b[0]
                if 0 < n <= 10 and len(b) >= 1 + 8 * n:
                    for k in range(n):
                        pid, qty = struct.unpack_from("<II", b, 1 + 8 * k)
                        if 1000 <= pid < 100000 and 0 < qty < 100:
                            self.events.append(("soul", {"pet": str(pid), "n": qty, "t": now}))
            elif op == 0x3642:
                eid, _ = varint(b, 0)
                self.pos.pop(eid, None)
        except (IndexError, struct.error):
            pass
        self.poll(now)

    def _is_player(self, eid):
        return eid in self.r.cls or eid in self.r.names or eid == self.r.find_self()

    # ------------------------------------------------------------ PvP
    def on_damage(self, atk, tgt, now=None):
        """Chamado pelo leitor a cada golpe com dano (não cura)."""
        now = now or time.time()
        self.hits.setdefault(tgt, {})[atk] = now
        self.last_hit[tgt] = (atk, now)

    def _player_died(self, eid, now):
        if now - self.pdone.get(eid, -99) < 10:
            return
        self.pdead.setdefault(eid, now)

    def _finish_pvp(self, eid, now):
        t = self.pdead.pop(eid)
        killer, kname = self.pcredit.pop(eid, (None, ""))
        self.pdone[eid] = t
        me = self.r.find_self()
        sname = (self.r.self_name or "").lower()
        if eid == me or (me is None and sname and self.r.names.get(eid, "").lower() == sname):
            return                                   # foi você que morreu
        if me is not None and eid in self.r.group(me):
            return                                   # alguém do seu grupo
        mine = killer is not None and (killer == me or (sname and kname.lower() == sname))
        kind = None
        if mine:
            kind = "kill"
        elif killer is None:
            last = self.last_hit.get(eid)
            if last and me is not None and last[0] == me and t - last[1] <= LAST_HIT_WINDOW:
                kind = "kill"
        if kind is None and me is not None:
            hit = self.hits.get(eid, {}).get(me)
            if hit is not None and t - hit <= ASSIST_WINDOW:
                kind = "assist"
        self.hits.pop(eid, None)
        self.last_hit.pop(eid, None)
        if kind:
            self.events.append(("pvp", {"kind": kind, "t": t, "victim_id": eid,
                                        "victim": self.r.names.get(eid, ""), "killer": kname}))

    def _prune(self, now):
        for tgt in list(self.hits):
            d = self.hits[tgt]
            for a in [a for a, t in d.items() if now - t > ASSIST_WINDOW * 2]:
                del d[a]
            if not d:
                del self.hits[tgt]
                self.last_hit.pop(tgt, None)
        for eid in [e for e, t in self.pdone.items() if now - t > 60]:
            del self.pdone[eid]

    # ------------------------------------------------------------ periodicamente
    def poll(self, now=None):
        now = now or time.time()
        for eid, t in list(self.dead.items()):
            if eid in self.credit or now - t >= CREDIT_WAIT:
                self._finish(eid, now)
        for eid, t in list(self.pdead.items()):
            if eid in self.pcredit or now - t >= PVP_WAIT:
                self._finish_pvp(eid, now)
        if now - self._last_prune > 5:
            self._last_prune = now
            self._prune(now)
        if now - self._last_guess > 4:
            self._last_guess = now
            self._guess_world(now)
            # esquece monstros que sumiram faz tempo
            for eid, (_x, _y, t) in list(self.pos.items()):
                if now - t > 180:
                    self.pos.pop(eid, None)

    def _guess_world(self, now):
        pts = [(x, y) for x, y, t in self.pos.values() if now - t < 120][-60:]
        wid, _med = self.sp.guess_world(pts)
        if wid and wid != self.world:
            self.world = wid
            self.events.append(("world", {"world": wid}))
        if wid:
            self.world_t = now

    def _finish(self, eid, now):
        t = self.dead.pop(eid)
        killer, kname = self.credit.pop(eid, (None, ""))
        self.done.add(eid)
        if len(self.done) > 5000:
            self.done.clear()
        p = self.pos.get(eid)
        sname = (self.r.self_name or "").lower()
        if not p and killer and (killer == self.r.find_self() or (sname and kname.lower() == sname)):
            p = self.my_position(now)          # sem posição do monstro: ele morreu perto de você
        ev = {"eid": eid, "t": t, "killer": kname, "killer_id": killer, "mine": False, "mob": None, "cat": None,
              "world": self.world, "x": None, "y": None}
        me = self.r.find_self()
        if killer is not None and killer != 0:
            group = self.r.group(me) if me is not None else set()
            sname = (self.r.self_name or "").lower()
            ev["mine"] = killer == me or killer in group or (sname and kname.lower() == sname)
        if p:
            ev["x"], ev["y"] = p[0], p[1]
            worlds = [self.world] if self.world else list(self.sp.grid)
            best = None
            for wid in worlds:
                n = self.sp.nearest(wid, p[0], p[1])
                boss = self.sp.nearest(wid, p[0], p[1], maxd=BOSS_MATCH, cat="named")
                if boss and (not n or n[1] != "named"):
                    # chefe: o ponto dele é o mais perto, ou o monstro tinha vida de chefe (eles andam bastante
                    # durante a luta e podem morrer longe do ponto de nascimento)
                    if not n or boss[2] <= n[2] or self.maxhp.get(eid, 0) >= BOSS_HP:
                        n = boss
                if n and (best is None or n[2] < best[0][2]):
                    best = (n, wid)
            if best:
                (name, cat, _d), wid = best
                ev.update(mob=name, cat=cat, world=wid)
        self.pos.pop(eid, None)
        self.maxhp.pop(eid, None)
        self.events.append(("kill", ev))

    def my_position(self, now=None):
        """Sua posição: a da última habilidade usada ou, sem isso, o meio dos monstros em volta."""
        now = now or time.time()
        if self.me and now - self.me[2] < 90:
            return self.me[0], self.me[1]
        pts = [(x, y) for x, y, t in self.pos.values() if now - t < 30]
        if len(pts) >= 2:
            xs = sorted(p[0] for p in pts)
            ys = sorted(p[1] for p in pts)
            return xs[len(xs) // 2], ys[len(ys) // 2]
        return None

    def take_events(self):
        ev, self.events = self.events, []
        return ev
