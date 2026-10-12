"""Farm de pet automático.

Lê o mesmo tráfego do medidor de DPS (net_hub): quando você mata um monstro que dá alma de pet, o farm
começa sozinho com aquele monstro e cada abate seu é contado. Também mostra quais monstros de pet existem
na região onde você está e onde nascem (mini-mapa na tela).
"""
import json
import math
import os
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from base_window import OverlayWindow
from i18n import N, PET, T
from config import BASE_DIR, cfg, resolve, save

DEFAULTS = {
    "active": False, "world": "", "mob": "", "coords": [], "pet": "", "kills": 0, "visible": True,
    "auto": True,                # liga a leitura do jogo sozinho ao abrir o programa
    "tally": {},                 # mob -> {"kills": n, "first": t, "last": t}  (sessão atual)
    "soul_tally": {},            # pet -> almas ganhas nesta sessão (lidas do jogo, 0x900d)
    "soul_total": {},            # pet -> almas contadas pelo programa desde sempre
    "opacity": 0.92, "pos": None,
}
OLD_KEYS = ("souls", "goal", "start_souls", "stage", "detect", "reference", "region", "monitor", "threshold",
            "cooldown", "interval_ms", "sound", "volume")

_cache = {"res": None, "bg": {}, "regions": {}}


def farm_cfg():
    c = cfg.setdefault("farm", {})
    for k in OLD_KEYS:              # contagem manual / detecção por tela antigas: não existem mais
        c.pop(k, None)
    for k, v in DEFAULTS.items():
        c.setdefault(k, v)
    return c


def _resources():
    if _cache["res"] is None:
        with open(os.path.join(BASE_DIR, "data", "resources.json"), encoding="utf-8") as f:
            _cache["res"] = json.load(f)
    return _cache["res"]


def _background(wid):
    """(pixmap, x, y, scale) do fundo do mapa, se houver."""
    bgc = cfg.get("map", {}).get("backgrounds", {}).get(wid)
    if not bgc:
        try:
            with open(os.path.join(BASE_DIR, "fundos", "presets.json"), encoding="utf-8") as f:
                bgc = json.load(f).get(wid)
        except OSError:
            bgc = None
    if not bgc or not bgc.get("path") or not os.path.exists(resolve(bgc["path"])):
        return None
    path = resolve(bgc["path"])
    if path not in _cache["bg"]:
        _cache["bg"][path] = QPixmap(path)
    return _cache["bg"][path], bgc["x"], bgc["y"], bgc["scale"]


def region_of(wid, coords):
    """Região (nível 1) onde está a maioria dos spawns."""
    world = _resources()["worlds"].get(wid)
    if not world or not coords:
        return ""
    paths = []
    for r in world["regions"]:
        if r["r"] != 1:
            continue
        p = QPainterPath()
        for poly in r["p"]:
            p.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
        paths.append((r["n"], p))
    votes = {}
    for i in range(0, len(coords), 2):
        pt = QPointF(coords[i], coords[i + 1])
        for name, p in paths:
            if p.contains(pt):
                votes[name] = votes.get(name, 0) + 1
                break
    return max(votes, key=votes.get) if votes else world["name"]


def render_minimap(wid, coords, w, h, marker=None, min_span=30000):
    pm = QPixmap(w, h)
    pm.fill(QColor("#171511"))
    if not coords:
        return pm
    xs = coords[0::2]
    ys = [-y for y in coords[1::2]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * w / h, min_span) * 1.35
    sw, sh = span, span * h / w
    view = QRectF(cx - sw / 2, cy - sh / 2, sw, sh)
    k = w / sw

    def to_px(x, y):
        return QPointF((x - view.left()) * k, (y - view.top()) * k)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = _background(wid)
    if bg:
        img, bx, by, bs = bg
        src = QRectF((view.left() - bx) / bs, (view.top() - by) / bs, sw / bs, sh / bs)
        p.drawPixmap(QRectF(0, 0, w, h), img, src)
    world = _resources()["worlds"].get(wid)
    if world:
        for r in world["regions"]:
            if r["r"] != 1:
                continue
            for poly in r["p"]:
                path = QPainterPath()
                path.addPolygon(QPolygonF([to_px(x, -y) for x, y in poly]))
                path.closeSubpath()
                if not bg:
                    p.fillPath(path, QColor(36, 32, 26))
                p.setPen(QPen(QColor(240, 232, 215, 110), 1))
                p.drawPath(path)
    if world:  # nomes das regiões para se localizar
        f = QFont("Segoe UI", 7, QFont.Bold)
        p.setFont(f)
        labels = []
        for r in world["regions"]:
            if r["r"] != 1:
                continue
            lp = to_px(r["l"][0], -r["l"][1])
            if 0 <= lp.x() <= w and 0 <= lp.y() <= h:
                labels.append((lp, r["n"]))
        for lp, name in (labels if len(labels) <= 10 else []):  # muitos nomes = poluído demais
            if True:
                r = {"n": name}
                rect = QRectF(lp.x() - 70, lp.y() - 8, 140, 16)
                p.setPen(QColor(0, 0, 0, 200))
                p.drawText(rect.translated(1, 1), Qt.AlignCenter, r["n"])
                p.setPen(QColor(242, 236, 224, 220))
                p.drawText(rect, Qt.AlignCenter, r["n"])
    for x, y in zip(xs, ys):
        c = to_px(x, y)
        if marker is not None and not marker.isNull():
            mw, mh = marker.width(), marker.height()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(8, 7, 6, 170))
            p.drawEllipse(c, mw * 0.55, mh * 0.55)
            p.drawPixmap(int(c.x() - mw / 2), int(c.y() - mh / 2), marker)
        else:
            p.setPen(QPen(QColor(20, 10, 10, 200), 1.2))
            p.setBrush(QColor("#ff6b5e"))
            p.drawEllipse(c, 4, 4)
    p.end()
    return pm


# ====================================================================== card na tela


def _region_paths(wid):
    if wid not in _cache["regions"]:
        world = _resources()["worlds"].get(wid)
        paths = []
        for r in (world or {}).get("regions", []):
            if r["r"] != 1:
                continue
            p = QPainterPath()
            for poly in r["p"]:
                p.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
            paths.append((r["n"], p))
        _cache["regions"][wid] = paths
    return _cache["regions"][wid]


def region_at(wid, x, y):
    pt = QPointF(x, y)
    for name, p in _region_paths(wid):
        if p.contains(pt):
            return name
    return ""


def world_name(wid):
    return T(_resources()["worlds"].get(wid, {}).get("name", "")) if wid else ""


def rate_text(t):
    """abates por hora de uma linha do tally."""
    if not t or t.get("kills", 0) < 2:
        return ""
    mins = max(1.0, (t["last"] - t["first"]) / 60)
    return T("{n}/h").format(n=int(round(t["kills"] * 60 / mins)))


# ====================================================================== card na tela
class FarmWidget(OverlayWindow):
    W, MAP_H = 290, 150

    def __init__(self):
        farm_cfg()
        super().__init__("farm", QPoint(40, 200))
        self.setFixedSize(self.W, self.MAP_H + 90)
        self.souls = ""
        self.minimap = None
        self.region = ""
        self.pet_name = ""

    def refresh(self, rebuild_map=False, pet_name=None):
        c = farm_cfg()
        if pet_name is not None:
            self.pet_name = pet_name
        if rebuild_map or self.minimap is None:
            self.minimap = render_minimap(c["world"], c["coords"], self.W - 4, self.MAP_H - 2)
            self.region = N(region_of(c["world"], c["coords"]))
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        c = farm_cfg()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(2, 2, self.W - 4, self.MAP_H), 9, 9)
        p.save()
        p.setClipPath(clip)
        if self.minimap:
            p.drawPixmap(2, 2, self.minimap)
        p.fillRect(QRectF(2, 2, self.W - 4, 26), QColor(0, 0, 0, 130))
        p.restore()
        f_reg = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(f_reg)
        p.setPen(QColor("white"))
        p.drawText(QRectF(12, 4, self.W - 24, 22), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(f_reg).elidedText(self.region or "—", Qt.ElideRight, self.W - 24))

        y0 = self.MAP_H + 6
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.setPen(QColor("#f4d58c"))
        f = QFont("Segoe UI", 11, QFont.Bold)
        p.drawText(QRectF(14, y0, self.W - 28, 22), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(f).elidedText(self.pet_name or N(c["mob"]), Qt.ElideRight, self.W - 28))
        f2 = QFont("Segoe UI", 8)
        p.setFont(f2)
        p.setPen(QColor("#c7bda8"))
        p.drawText(QRectF(14, y0 + 20, self.W - 28, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(f2).elidedText(N(c["mob"]), Qt.ElideRight, self.W - 28))
        t = c["tally"].get(c["mob"], {})
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 13, QFont.Bold))
        p.drawText(QRectF(14, y0 + 38, self.W - 28, 26), Qt.AlignVCenter | Qt.AlignLeft,
                   T("{n} abates").format(n=t.get("kills", 0)))
        p.setPen(QColor("#5ee39a"))
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRectF(14, y0 + 38, self.W - 28, 26), Qt.AlignVCenter | Qt.AlignRight, rate_text(t))
        p.setPen(QColor("#f4d58c"))
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRectF(14, y0 + 62, self.W - 28, 18), Qt.AlignVCenter | Qt.AlignLeft, self.souls)
        p.end()


# ====================================================================== aba do painel
class FarmTab(QWidget):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.hub = panel.hub
        self.card = FarmWidget()
        with open(os.path.join(BASE_DIR, "data", "mobs.json"), encoding="utf-8") as f:
            self.mobdata = json.load(f)
        self.pets = self.mobdata["pets"]
        self.pet_names = {pid: PET(pid, name) for pid, name, _ in self.pets}
        self.suggest = self.mobdata["suggest"]
        c = farm_cfg()
        c["tally"] = {}                     # cada vez que o programa abre é uma sessão nova
        c["soul_tally"] = {}
        lay = QVBoxLayout(self)

        # ---- leitura do jogo
        box0 = QGroupBox("Contagem automática")
        v0 = QVBoxLayout(box0)
        self.net_label = QLabel("")
        self.net_label.setWordWrap(True)
        self.net_label.setTextFormat(Qt.RichText)
        v0.addWidget(self.net_label)
        row = QHBoxLayout()
        self.btn_net = __import__("theme").primary(QPushButton("Ligar"))
        self.btn_net.clicked.connect(self.toggle_net)
        self.btn_npcap = QPushButton("Instalar Npcap")
        self.btn_npcap.clicked.connect(lambda: panel.dps_tab.install_npcap())
        self.btn_admin = QPushButton("Abrir como administrador")
        self.btn_admin.clicked.connect(lambda: panel.dps_tab.reopen_admin())
        self.chk_auto = QCheckBox("Ligar sozinho ao abrir o programa")
        self.chk_auto.setChecked(c["auto"])
        self.chk_auto.toggled.connect(lambda on: self.set("auto", on))
        for w in (self.btn_net, self.btn_npcap, self.btn_admin):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.chk_auto)
        v0.addLayout(row)
        hint = QLabel("Mate um monstro que dá alma de pet e o farm começa sozinho com ele; cada abate seu e cada alma "
                      "que você ganha são contados. Usa o mesmo leitor do medidor de DPS (só lê o tráfego do jogo).")
        hint.setWordWrap(True)
        hint.setProperty("hint", True)
        v0.addWidget(hint)
        lay.addWidget(box0)

        # ---- farm atual
        box1 = QGroupBox("Farm atual")
        v1 = QVBoxLayout(box1)
        self.now_label = QLabel("")
        self.now_label.setWordWrap(True)
        self.now_label.setTextFormat(Qt.RichText)
        v1.addWidget(self.now_label)
        row = QHBoxLayout()
        bsee = QPushButton("Ver no mapa")
        bsee.clicked.connect(self.see_current)
        breset = QPushButton("Zerar contagem")
        breset.clicked.connect(self.reset_session)
        bstop = QPushButton("Parar farm")
        bstop.clicked.connect(self.stop_farm)
        self.show_card = QCheckBox("Mostrar o card do farm na tela")
        self.show_card.setChecked(c["visible"])
        self.show_card.toggled.connect(self.set_visible)
        for w in (bsee, breset, bstop):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.show_card)
        v1.addLayout(row)
        lay.addWidget(box1)

        # ---- mobs de pet onde você está
        box2 = QGroupBox("Mobs de pet na sua região")
        v2 = QVBoxLayout(box2)
        self.here_label = QLabel("")
        self.here_label.setWordWrap(True)
        v2.addWidget(self.here_label)
        self.here = QTreeWidget()
        self.here.setRootIsDecorated(False)
        self.here.setUniformRowHeights(True)
        self.here.setHeaderLabels([T("Monstro"), T("Alma de"), T("Distância"), T("Seus abates"), T("Almas")])
        hh = self.here.header()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (2, 3, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.here.setMinimumHeight(150)
        self.here.itemDoubleClicked.connect(self.pick_here)
        v2.addWidget(self.here)
        tip = QLabel("Duplo clique: farmar esse monstro e ver onde ele nasce.")
        tip.setProperty("hint", True)
        v2.addWidget(tip)
        lay.addWidget(box2, 1)

        # ---- procurar um pet específico
        box3 = QGroupBox("Procurar um pet")
        f = QFormLayout(box3)
        self.pet = QComboBox()
        self.pet.setEditable(True)
        self.pet.setInsertPolicy(QComboBox.NoInsert)
        self.pet.addItem("", "")
        for pid, name, _ in self.pets:
            self.pet.addItem(self.pet_names[pid], pid)
        self.pet.completer().setFilterMode(Qt.MatchContains)
        self.pet.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.pet.currentIndexChanged.connect(self.fill_where)
        f.addRow("Pet:", self.pet)
        wrow = QHBoxLayout()
        self.where = QComboBox()
        self.where.setMinimumWidth(260)
        self.btn_go = QPushButton("Farmar este mob")
        self.btn_go.clicked.connect(self.farm_where)
        bsee2 = QPushButton("Ver no mapa")
        bsee2.clicked.connect(self.see_where)
        wrow.addWidget(self.where, 1)
        wrow.addWidget(self.btn_go)
        wrow.addWidget(bsee2)
        f.addRow("Onde:", wrow)
        self.where_hint = QLabel("")
        self.where_hint.setWordWrap(True)
        self.where_hint.setProperty("hint", True)
        f.addRow(self.where_hint)
        lay.addWidget(box3)

        hub = self.hub
        hub.kill.connect(self.on_kill)
        hub.soul.connect(self.on_soul)
        hub.running_changed.connect(lambda _on: self.refresh_net())
        hub.status.connect(lambda _m: self.refresh_net())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_here)
        self.timer.start(3000)

        self.fill_where()
        self.refresh_all(rebuild=True)
        self.card.restore_position()
        self.card.set_locked(cfg.get("locked", False))
        if c["active"] and c["visible"]:
            self.card.show()
        self.refresh_net()
        if c["auto"] and hub.requirements()[0]:
            QTimer.singleShot(2000, lambda: (hub.acquire("farm"), self.refresh_net()))

    # ------------------------------------------------------------------ estado
    def set(self, key, value):
        farm_cfg()[key] = value
        save()

    def pet_of(self, mob):
        pid = self.suggest.get(mob, "")
        return pid, self.pet_names.get(pid, "")

    def pet_kills(self, pid):
        """Seus abates nesta sessão de todos os mobs que dão a alma desse pet."""
        return sum(t["kills"] for m, t in farm_cfg()["tally"].items() if self.suggest.get(m) == pid)

    def soul_line(self, pid):
        c = farm_cfg()
        n = c["soul_tally"].get(pid, 0)
        k = self.pet_kills(pid)
        txt = T("{n} alma(s)").format(n=n)
        if n and k:
            txt += " · " + T("1 a cada {r} abates").format(r=f"{k / n:.1f}".rstrip("0").rstrip("."))
        return txt

    def refresh_all(self, rebuild=False):
        c = farm_cfg()
        if c["active"]:
            _pid, pname = self.pet_of(c["mob"])
            t = c["tally"].get(c["mob"], {})
            region = N(region_of(c["world"], c["coords"]))
            rate = rate_text(t)
            self.now_label.setText(
                f"<span style='font-size:13pt; font-weight:600'>{N(c['mob'])}</span>"
                + (f"&nbsp;&nbsp;<span style='color:#e0b04f'>{T('alma de')} {pname}</span>" if pname else "")
                + f"<br><span style='color:#9b9282'>{world_name(c['world'])} · {region}</span>"
                + f"<br><span style='font-size:15pt; font-weight:600'>{t.get('kills', 0)}</span> "
                + T("abates nesta sessão") + (f" &nbsp;·&nbsp; <span style='color:#5ee39a'>{rate}</span>" if rate else "")
                + (f"<br><span style='font-size:13pt; font-weight:600; color:#f4d58c'>{self.soul_line(_pid)}</span>"
                   if _pid else ""))
            self.card.souls = self.soul_line(_pid) if _pid else ""
            self.card.refresh(rebuild_map=rebuild, pet_name=pname)
        else:
            self.now_label.setText(T("Nenhum farm ainda. Mate um monstro de pet (veja a lista abaixo) "
                                     "e o farm começa sozinho."))

    def refresh_net(self):
        ok, falta = self.hub.requirements()
        self.btn_npcap.setVisible("Npcap" in falta)
        self.btn_admin.setVisible("administrador" in falta)
        if self.hub.running and "farm" in self.hub.users:
            self.btn_net.setText(T("Desligar"))
            wid, _pos = self.hub.world_state()
            who = cfg.get("dps", {}).get("char_name") or T("procurando o seu personagem (costuma aparecer quando você toma dano)…")
            where = world_name(wid) if wid else T("procurando onde você está…")
            self.net_label.setText(f"<span style='color:#5ee39a'>●</span> <b>{T('Lendo o jogo')}</b> — "
                                   f"{where} · {T('personagem')}: {who}")
        else:
            self.btn_net.setText(T("Ligar"))
            if ok:
                self.net_label.setText(f"<span style='color:#9b9282'>○</span> {T('Desligado.')}")
            else:
                faltam = (" " + T("e") + " ").join(T(x) for x in falta)
                self.net_label.setText("<span style='color:#f0883e'>○</span> " +
                                       T("Para contar sozinho falta: {f}.").format(f=faltam))
        self.btn_net.setEnabled(ok)

    def toggle_net(self):
        if self.hub.running and "farm" in self.hub.users:
            self.hub.release("farm")
        else:
            self.hub.acquire("farm")
        self.refresh_net()

    # ------------------------------------------------------------------ abates
    def on_kill(self, ev):
        if not ev.get("mine") or not ev.get("mob"):
            return
        c = farm_cfg()
        mob, wid = ev["mob"], ev.get("world") or c["world"]
        now = time.time()
        t = c["tally"].setdefault(mob, {"kills": 0, "first": now, "last": now})
        t["kills"] += 1
        t["last"] = now
        pid, _pname = self.pet_of(mob)
        if pid and (not c["active"] or c["mob"] != mob):
            data = self.panel.hub.reader.world.sp.by_name.get((wid, mob)) if self.hub.reader and self.hub.reader.world else None
            coords = data[1] if data else []
            self.start_farm(wid, mob, coords, pid)
            return
        if c["active"] and c["mob"] == mob:
            c["kills"] = t["kills"]
        save()
        self.refresh_all()
        self.refresh_here()

    def on_soul(self, ev):
        c = farm_cfg()
        pid, n = ev["pet"], ev["n"]
        c["soul_tally"][pid] = c["soul_tally"].get(pid, 0) + n
        c["soul_total"][pid] = c["soul_total"].get(pid, 0) + n
        save()
        self.refresh_all()
        self._here_key = None
        self.refresh_here()

    def start_farm(self, wid, mob, coords, pet_id=""):
        c = farm_cfg()
        if not coords:
            for name, _cat, co in self.mobdata["worlds"].get(wid, []):
                if name == mob:
                    coords = co
                    break
        c.update(active=True, world=wid, mob=mob, coords=coords, pet=pet_id or self.suggest.get(mob, ""),
                 kills=c["tally"].get(mob, {}).get("kills", 0))
        save()
        if c["visible"]:
            self.card.show()
            self.card.set_locked(cfg.get("locked", False))
        self.refresh_all(rebuild=True)
        self.refresh_here()

    def stop_farm(self):
        farm_cfg()["active"] = False
        save()
        self.card.hide()
        self.refresh_all()

    def reset_session(self):
        c = farm_cfg()
        c["tally"] = {}
        c["soul_tally"] = {}
        c["kills"] = 0
        save()
        self.refresh_all()
        self.refresh_here()

    def set_visible(self, on):
        farm_cfg()["visible"] = on
        save()
        if on and farm_cfg()["active"]:
            self.card.refresh(rebuild_map=True)
            self.card.show()
            self.card.set_locked(cfg.get("locked", False))
        else:
            self.card.hide()

    # ------------------------------------------------------------------ onde você está
    def refresh_here(self):
        if self.hub.running:
            self.refresh_net()
        wid, pos = self.hub.world_state()
        c = farm_cfg()
        if not wid:
            wid, pos = (c["world"], None) if c["active"] else (None, None)
        if not wid:
            self.here_label.setText(T("Ligue a contagem automática e ande um pouco pelo mapa: a lista mostra os "
                                      "monstros de pet da região onde você estiver."))
            self.here.clear()
            return
        region = region_at(wid, *pos) if pos else ""
        key = (wid, region, int(pos[0] // 2000) if pos else 0, int(pos[1] // 2000) if pos else 0,
               tuple(sorted((m, t["kills"]) for m, t in c["tally"].items())), c["mob"],
               tuple(sorted(c["soul_tally"].items())))
        if key == getattr(self, "_here_key", None):
            return
        self._here_key = key
        rows = []
        for name, _cat, co in self.mobdata["worlds"].get(wid, []):
            pid = self.suggest.get(name)
            if not pid:
                continue
            pts = [(co[i], co[i + 1]) for i in range(0, len(co) - 1, 2)]
            if region:
                inside = [pt for pt in pts if region_at(wid, *pt) == region]
                if not inside:
                    continue
                pts = inside
            dist = min(math.hypot(x - pos[0], y - pos[1]) for x, y in pts) if pos else None
            if not region and dist is not None and dist > 25000:
                continue
            rows.append((dist if dist is not None else 0, name, pid, len(pts), co))
        rows.sort(key=lambda r: r[0])
        self.here.clear()
        for dist, name, pid, n, co in rows[:40]:
            kills = c["tally"].get(name, {}).get("kills", 0)
            d = (f"{dist / 100:.0f} m" if dist < 100000 else f"{dist / 100000:.1f} km") if pos else f"{n} spawns"
            souls = c["soul_tally"].get(pid, 0)
            it = QTreeWidgetItem([N(name), self.pet_names.get(pid, ""), d, str(kills) if kills else "",
                                  str(souls) if souls else ""])
            it.setData(0, Qt.UserRole, (wid, name))
            if c["active"] and c["mob"] == name:
                for col in range(5):
                    it.setForeground(col, QColor("#f4d58c"))
            self.here.addTopLevelItem(it)
        where = world_name(wid) + (f" · {N(region)}" if region else "")
        self.here_label.setText(T("Você está em {w}: {n} monstro(s) que dão alma de pet.").format(w=where, n=len(rows))
                                if pos else T("{w}: {n} monstro(s) que dão alma de pet.").format(w=where, n=len(rows)))

    def pick_here(self, it, _col=0):
        wid, name = it.data(0, Qt.UserRole)
        self.start_farm(wid, name, None)
        self.show_on_map(wid, name)

    # ------------------------------------------------------------------ procurar pet
    def fill_where(self, *_):
        pid = self.pet.currentData() or ""
        res = _resources()["worlds"]
        self.where.clear()
        for wid, mob, n in self.mobdata.get("sources", {}).get(pid, []):
            self.where.addItem(f"{N(mob)} — {T(res.get(wid, {}).get('name', wid))} ({n} spawns)", (wid, mob))
        has = self.where.count() > 0
        self.where.setEnabled(has)
        self.btn_go.setEnabled(has)
        if not pid:
            self.where_hint.setText(T("Escolha o pet para ver quais mobs dão a alma dele."))
        elif not has:
            self.where_hint.setText(T("Esse pet não vem de mobs dos mapas abertos (é de masmorra, evento ou "
                                      "outra forma)."))
        else:
            self.where_hint.setText(T("{n} mob(s) dão essa alma.").format(n=self.where.count()))

    def farm_where(self):
        data = self.where.currentData()
        if data:
            self.start_farm(data[0], data[1], None, self.pet.currentData() or "")

    def see_where(self):
        data = self.where.currentData()
        if data:
            self.show_on_map(*data)
        else:
            self.open_map()

    def see_current(self):
        c = farm_cfg()
        if c["active"]:
            self.show_on_map(c["world"], c["mob"])
        else:
            self.open_map()

    def show_on_map(self, wid, mob):
        self.open_map()
        m = self.panel.get_map()
        if hasattr(m, "focus_mob"):
            m.focus_mob(wid, mob)

    def open_map(self):
        m = self.panel.get_map()
        m.set_mode("mobs")
        self.panel.open_map()

    def shutdown(self):
        self.timer.stop()
