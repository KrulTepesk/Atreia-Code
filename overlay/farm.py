"""Farm de pet: escolhe um mob no mapa, mostra os spawns num mini-mapa e conta as almas
que faltam para o próximo nível de afinidade do pet.

Contagem: teclas de atalho globais (funcionam com o jogo em foco) ou, opcionalmente,
detecção da mensagem de alma na tela (mesmo método do som de abate do PvP).
"""
import json
import os

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import sounds_player
from base_window import OverlayWindow
from i18n import N, PET, T
from config import APP_DIR, BASE_DIR, cfg, resolve, save

STAGES = [("obter", "Obter o pet", 5), ("1", "Afinidade nível 1 → 2", 25), ("2", "Afinidade nível 2 → 3", 75)]
SOUL_REF = os.path.join(APP_DIR, "alma_referencia.png")
HOTKEYS = {1: ("ctrl+alt", "S", "+1 alma"), 2: ("ctrl+alt", "X", "−1 alma"), 3: ("ctrl+alt", "K", "+1 abate")}

DEFAULTS = {
    "active": False, "world": "", "mob": "", "coords": [], "pet": "", "stage": "1",
    "souls": 0, "goal": 25, "start_souls": 0, "kills": 0, "visible": True,
    "sound": "sounds/shugo.wav", "volume": 80, "opacity": 0.92, "pos": None,
    # detecção automática da mensagem de alma (opcional)
    "detect": False, "reference": "", "region": None, "monitor": 1,
    "threshold": 0.8, "cooldown": 1.5, "interval_ms": 250,
}

_cache = {"res": None, "bg": {}}


def farm_cfg():
    c = cfg.setdefault("farm", {})
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


def render_minimap(wid, coords, w, h, marker=None):
    pm = QPixmap(w, h)
    pm.fill(QColor("#1a1631"))
    if not coords:
        return pm
    xs = coords[0::2]
    ys = [-y for y in coords[1::2]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * w / h, 30000) * 1.35
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
                    p.fillPath(path, QColor(38, 46, 61))
                p.setPen(QPen(QColor(230, 235, 245, 110), 1))
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
                p.setPen(QColor(235, 238, 245, 220))
                p.drawText(rect, Qt.AlignCenter, r["n"])
    for x, y in zip(xs, ys):
        c = to_px(x, y)
        if marker is not None and not marker.isNull():
            mw, mh = marker.width(), marker.height()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(8, 6, 18, 170))
            p.drawEllipse(c, mw * 0.55, mh * 0.55)
            p.drawPixmap(int(c.x() - mw / 2), int(c.y() - mh / 2), marker)
        else:
            p.setPen(QPen(QColor(20, 10, 10, 200), 1.2))
            p.setBrush(QColor("#ff6b5e"))
            p.drawEllipse(c, 4, 4)
    p.end()
    return pm


# ====================================================================== card na tela
class FarmWidget(OverlayWindow):
    W, MAP_H = 290, 150

    def __init__(self):
        farm_cfg()
        super().__init__("farm", QPoint(40, 200))
        self.setFixedSize(self.W, self.MAP_H + 92)
        self.minimap = None
        self.region = ""
        self.pet_name = ""
        self.done_flash = False

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
        # mini-mapa com cantos arredondados
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(2, 2, self.W - 4, self.MAP_H), 9, 9)
        p.save()
        p.setClipPath(clip)
        if self.minimap:
            p.drawPixmap(2, 2, self.minimap)
        p.fillRect(QRectF(2, 2, self.W - 4, 26), QColor(0, 0, 0, 120))
        p.restore()
        p.setPen(QColor("white"))
        f_reg = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(f_reg)
        region = QFontMetrics(f_reg).elidedText(self.region or "—", Qt.ElideRight, self.W - 40)
        p.drawText(QRectF(12, 4, self.W - 24, 22), Qt.AlignVCenter | Qt.AlignLeft, region)
        free = self.W - 24 - QFontMetrics(f_reg).horizontalAdvance(region) - 14
        f_mob = QFont("Segoe UI", 8)
        if free > 50:
            p.setPen(QColor("#ffb4ab"))
            p.setFont(f_mob)
            p.drawText(QRectF(12, 4, self.W - 24, 22), Qt.AlignVCenter | Qt.AlignRight,
                       QFontMetrics(f_mob).elidedText(N(c["mob"]), Qt.ElideRight, free))

        y0 = self.MAP_H + 8
        souls, goal = c["souls"], max(1, c["goal"])
        gained = souls - c["start_souls"]
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.drawText(QRectF(14, y0, self.W - 90, 22), Qt.AlignVCenter | Qt.AlignLeft,
                   self.pet_name or T("Escolha o pet"))
        stage = T(next((s[1] for s in STAGES if s[0] == c["stage"]), ""))
        p.setPen(QColor("#b9b3d6"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(self.W - 110, y0, 96, 22), Qt.AlignVCenter | Qt.AlignRight,
                   stage.replace("Afinidade ", "").replace("Affinity ", ""))

        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.setPen(QColor("#5ee39a"))
        p.drawText(QRectF(14, y0 + 22, self.W - 28, 20), Qt.AlignVCenter | Qt.AlignLeft,
                   T("{g} alma(s) · {s}/{t}").format(g=f"{'+' if gained >= 0 else ''}{gained}", s=souls, t=goal))
        left = max(0, goal - souls)
        if souls >= goal:
            right = T("Meta atingida!")
        elif c["kills"] >= 3 and gained > 0:
            right = T("faltam ~{n} abates").format(n=round(left * c['kills'] / gained))
        else:
            right = T("faltam {n} almas").format(n=left)
        p.setPen(QColor("#f5c542") if souls >= goal else QColor("#d7dce5"))
        p.drawText(QRectF(14, y0 + 22, self.W - 28, 20), Qt.AlignVCenter | Qt.AlignRight, right)

        bar = QRectF(14, y0 + 48, self.W - 28, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(bar, 3.5, 3.5)
        p.setBrush(QColor("#5ee39a") if souls < goal else QColor("#f5c542"))
        p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * min(1, souls / goal), bar.height()), 3.5, 3.5)
        p.setPen(QColor("#958fb3"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(14, y0 + 58, self.W - 28, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   T("Abates: {n}").format(n=c['kills']))
        p.end()


# ====================================================================== aba do painel
class FarmTab(QWidget):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.watcher = None
        self.card = FarmWidget()
        with open(os.path.join(BASE_DIR, "data", "mobs.json"), encoding="utf-8") as f:
            self.mobdata = json.load(f)
        self.pets = self.mobdata["pets"]
        c = farm_cfg()
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.target = QLabel()
        self.target.setWordWrap(True)
        bmap = QPushButton("Escolher mob no mapa...")
        bmap.clicked.connect(self.open_map)
        top.addWidget(self.target, 1)
        top.addWidget(bmap)
        lay.addLayout(top)

        box = QGroupBox("Pet e meta")
        f = QFormLayout(box)
        self.pet = QComboBox()
        self.pet.setEditable(True)
        self.pet.setInsertPolicy(QComboBox.NoInsert)
        self.pet.addItem("", "")
        for pid, name, _ in self.pets:
            self.pet.addItem(PET(pid, name), pid)
        self.pet.completer().setFilterMode(Qt.MatchContains)
        self.pet.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.pet.currentIndexChanged.connect(self.pet_changed)
        f.addRow("Pet (alma):", self.pet)
        # onde farmar: todos os mobs que dão a alma do pet escolhido (dados do banco do jogo)
        wrow = QHBoxLayout()
        self.where = QComboBox()
        self.where.setMinimumWidth(260)
        self.btn_go = __import__("theme").primary(QPushButton("Farmar este mob"))
        self.btn_go.clicked.connect(self.farm_where)
        bsee = QPushButton("Ver no mapa")
        bsee.clicked.connect(self.see_where)
        wrow.addWidget(self.where, 1)
        wrow.addWidget(self.btn_go)
        wrow.addWidget(bsee)
        f.addRow("Onde farmar:", wrow)
        self.where_hint = QLabel("")
        self.where_hint.setWordWrap(True)
        f.addRow(self.where_hint)
        self.stage = QComboBox()
        for key, label, n in STAGES:
            self.stage.addItem(T(f"{label} ({n} almas)"), key)
        self.stage.currentIndexChanged.connect(self.stage_changed)
        f.addRow("Etapa:", self.stage)
        row = QHBoxLayout()
        self.souls = QSpinBox()
        self.souls.setRange(0, 999)
        self.souls.valueChanged.connect(self.souls_changed)
        self.goal = QSpinBox()
        self.goal.setRange(1, 999)
        self.goal.valueChanged.connect(lambda v: (self.set("goal", v), self.refresh_progress()))
        row.addWidget(self.souls)
        row.addWidget(QLabel(" de "))
        row.addWidget(self.goal)
        row.addStretch()
        f.addRow("Almas agora:", row)
        f.addRow(QLabel("Coloque o número que aparece no jogo (ex.: 57 de 75)."))
        lay.addWidget(box)

        boxp = QGroupBox("Progresso")
        vp = QVBoxLayout(boxp)
        self.progress = QLabel("")
        self.progress.setTextFormat(Qt.RichText)
        self.progress.setObjectName("FarmProgress")
        vp.addWidget(self.progress)
        lay.addWidget(boxp)

        box2 = QGroupBox("Contar")
        v = QVBoxLayout(box2)
        row = QHBoxLayout()
        for text, fn in (("+1 alma", lambda: self.add_soul(1)), ("−1 alma", lambda: self.add_soul(-1)),
                         ("+1 abate", self.add_kill), ("Zerar abates", self.reset_session)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        keys = "   ·   ".join(f"Ctrl+Alt+{k[1]} = {k[2]}" for k in HOTKEYS.values())
        self.hk_label = QLabel(f"Atalhos (funcionam dentro do jogo): {keys}")
        self.hk_label.setWordWrap(True)
        v.addWidget(self.hk_label)
        lay.addWidget(box2)

        box3 = QGroupBox("Contar almas sozinho (opcional)")
        v3 = QVBoxLayout(box3)
        v3.addWidget(QLabel("Reconhece na tela a mensagem de \"alma obtida\" do jogo, igual ao som de abate do PvP."))
        row = QHBoxLayout()
        bref = QPushButton("Definir referência...")
        bref.clicked.connect(self.define_reference)
        breg = QPushButton("Marcar área na tela...")
        breg.clicked.connect(self.select_region)
        self.detect = QCheckBox("Ativar")
        self.detect.setChecked(c["detect"])
        self.detect.toggled.connect(self.set_detect)
        row.addWidget(bref)
        row.addWidget(breg)
        row.addStretch()
        row.addWidget(self.detect)
        v3.addLayout(row)
        self.detect_status = QLabel("")
        v3.addWidget(self.detect_status)
        lay.addWidget(box3)

        row = QHBoxLayout()
        self.show_card = QCheckBox("Mostrar o card do farm na tela")
        self.show_card.setChecked(c["visible"])
        self.show_card.toggled.connect(self.set_visible)
        bstop = QPushButton("Parar farm")
        bstop.clicked.connect(self.stop_farm)
        row.addWidget(self.show_card)
        row.addStretch()
        row.addWidget(bstop)
        lay.addLayout(row)
        lay.addStretch()

        self.load_from_cfg()
        self.card.restore_position()
        self.card.set_locked(cfg.get("locked", False))
        if c["active"] and c["visible"]:
            self.card.refresh(rebuild_map=True, pet_name=self.pet.currentText())
            self.card.show()
        if c["detect"]:
            self.set_detect(True)

    # ------------------------------------------------------------------ estado
    def set(self, key, value):
        farm_cfg()[key] = value
        save()
        self.card.refresh()

    def load_from_cfg(self):
        c = farm_cfg()
        for w in (self.pet, self.stage, self.souls, self.goal):
            w.blockSignals(True)
        self.pet.setCurrentIndex(max(0, self.pet.findData(c["pet"])))
        self.stage.setCurrentIndex(max(0, self.stage.findData(c["stage"])))
        self.souls.setValue(c["souls"])
        self.goal.setValue(c["goal"])
        for w in (self.pet, self.stage, self.souls, self.goal):
            w.blockSignals(False)
        if c["active"]:
            self.target.setText(f"<b>{T('Farmando:')}</b> {N(c['mob'])}<br><span style='color:#888'>"
                                f"{N(region_of(c['world'], c['coords']))}</span>")
        else:
            self.target.setText(T("Nenhum farm ativo. Escolha o pet abaixo e clique em \"Farmar este mob\"."))
        self.card.pet_name = self.pet.currentText()
        if hasattr(self, "where"):
            self.fill_where()
            self.refresh_progress()

    def start_farm(self, wid, mob, coords, pet_id):
        c = farm_cfg()
        c.update(active=True, world=wid, mob=mob, coords=coords, kills=0)
        if pet_id:
            c["pet"] = pet_id
        c["start_souls"] = c["souls"]
        save()
        self.load_from_cfg()
        c["visible"] = True
        self.show_card.setChecked(True)
        self.card.refresh(rebuild_map=True, pet_name=self.pet.currentText())
        self.card.show()
        self.panel.show_panel()
        self.panel.tabs.setCurrentWidget(self)

    def stop_farm(self):
        farm_cfg()["active"] = False
        save()
        self.card.hide()
        self.load_from_cfg()

    def pet_changed(self, _i):
        self.set("pet", self.pet.currentData() or "")
        self.card.refresh(pet_name=self.pet.currentText())
        self.fill_where()

    # ------------------------------------------------------------------ onde farmar
    def fill_where(self):
        pid = self.pet.currentData() or ""
        res = _resources()["worlds"]
        cur = farm_cfg().get("mob", "")
        self.where.clear()
        for wid, mob, n in self.mobdata.get("sources", {}).get(pid, []):
            wname = T(res.get(wid, {}).get("name", wid))
            self.where.addItem(f"{N(mob)} — {wname} ({n} spawns)", (wid, mob))
            if mob == cur:
                self.where.setCurrentIndex(self.where.count() - 1)
        has = self.where.count() > 0
        self.where.setEnabled(has)
        self.btn_go.setEnabled(has)
        if not pid:
            self.where_hint.setText(T("Escolha o pet para ver quais mobs dão a alma dele."))
        elif not has:
            self.where_hint.setText(T("Esse pet não vem de mobs dos mapas abertos (é de masmorra, evento ou "
                                      "outra forma). Dá para contar as almas mesmo assim."))
        else:
            self.where_hint.setText(T("{n} mob(s) dão essa alma. Escolha um e clique em Farmar.").format(
                n=self.where.count()))

    def _where_coords(self):
        data = self.where.currentData()
        if not data:
            return None
        wid, mob = data
        for name, _cat, coords in self.mobdata["worlds"].get(wid, []):
            if name == mob:
                return wid, mob, coords
        return None

    def farm_where(self):
        found = self._where_coords()
        if found:
            wid, mob, coords = found
            self.start_farm(wid, mob, coords, self.pet.currentData() or "")

    def see_where(self):
        found = self._where_coords()
        if not found:
            self.open_map()
            return
        wid, mob, _coords = found
        self.open_map()
        m = self.panel.get_map()
        if hasattr(m, "focus_mob"):
            m.focus_mob(wid, mob)

    def refresh_progress(self):
        c = farm_cfg()
        souls, goal = c["souls"], max(1, c["goal"])
        left = max(0, goal - souls)
        gained = max(0, souls - c.get("start_souls", souls))
        kills = c.get("kills", 0)
        lines = [f"<span style='font-size:15pt; font-weight:600'>{souls} / {goal}</span>"
                 f"&nbsp;&nbsp;<span style='color:#958fb3'>{T('almas')}</span>"]
        if left == 0:
            lines.append(f"<span style='color:#5ee39a'>{T('Meta alcançada!')}</span>")
        else:
            lines.append(T("Faltam <b>{n}</b> almas.").format(n=left))
        if kills:
            txt = T("Nesta sessão: {k} abates, {g} almas.").format(k=kills, g=gained)
            if gained and left:
                rate = kills / gained
                txt += " " + T("Média de 1 alma a cada {r:.1f} abates → faltam uns <b>{m}</b> abates.").format(
                    r=rate, m=int(round(left * rate)))
            lines.append(txt)
        else:
            lines.append(f"<span style='color:#958fb3'>{T('Use +1 abate (ou Ctrl+Alt+K) a cada mob morto para ver quantos faltam.')}</span>")
        self.progress.setText("<br>".join(lines))

    def stage_changed(self, i):
        key, _, n = STAGES[i]
        farm_cfg()["stage"] = key
        self.goal.setValue(n)
        self.set("goal", n)

    def souls_changed(self, v):
        c = farm_cfg()
        reached_before = c["souls"] >= c["goal"]
        c["souls"] = v
        if c["start_souls"] > v:
            c["start_souls"] = v
        save()
        self.card.refresh()
        self.refresh_progress()
        if v >= c["goal"] and not reached_before:
            sounds_player.play(c["sound"], c["volume"])

    def add_soul(self, n=1):
        self.souls.setValue(max(0, self.souls.value() + n))

    def add_kill(self):
        c = farm_cfg()
        c["kills"] += 1
        save()
        self.card.refresh()
        self.refresh_progress()

    def reset_session(self):
        c = farm_cfg()
        c["kills"] = 0
        c["start_souls"] = c["souls"]
        save()
        self.card.refresh()
        self.refresh_progress()

    def on_hotkey(self, hid):
        if hid == 1:
            self.add_soul(1)
        elif hid == 2:
            self.add_soul(-1)
        elif hid == 3:
            self.add_kill()

    # ------------------------------------------------------------------ janela
    def open_map(self):
        m = self.panel.get_map()
        m.set_mode("mobs")
        self.panel.open_map()

    def set_visible(self, on):
        farm_cfg()["visible"] = on
        save()
        if on and farm_cfg()["active"]:
            self.card.refresh(rebuild_map=True, pet_name=self.pet.currentText())
            self.card.show()
            self.card.set_locked(cfg.get("locked", False))
        else:
            self.card.hide()

    # ------------------------------------------------------------------ detecção automática
    def define_reference(self):
        from pvp import ReferenceDialog
        dlg = ReferenceDialog(self, section="farm", ref_path=SOUL_REF, what="mensagem de alma obtida",
                              hint="sem a quantidade")
        if dlg.exec() and self.detect.isChecked():
            self.set_detect(True)

    def select_region(self):
        from PySide6.QtGui import QGuiApplication
        from pvp import RegionSelector
        screens = QGuiApplication.screens()
        idx = farm_cfg().get("monitor", 1) - 1
        self._sel = RegionSelector(screens[idx] if 0 <= idx < len(screens) else QGuiApplication.primaryScreen())
        self._sel.chosen.connect(self.region_chosen)
        self._sel.show()

    def region_chosen(self, r):
        farm_cfg()["region"] = r
        save()
        if self.detect.isChecked():
            self.set_detect(True)

    def set_detect(self, on):
        from pvp import KillWatcher
        c = farm_cfg()
        c["detect"] = on
        save()
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if not on:
            self.detect_status.setText("")
            return
        if not c["reference"] or not os.path.exists(c["reference"]):
            self.detect_status.setText(T("Defina a referência primeiro."))
            self.detect.setChecked(False)
            return
        self.watcher = KillWatcher("farm")
        self.watcher.kill.connect(lambda _s: self.add_soul(1))
        self.watcher.error.connect(lambda m: self.detect_status.setText(m))
        self.watcher.score.connect(lambda s: self.detect_status.setText(T("Monitorando · semelhança {s}").format(s=f"{s:.2f}")))
        self.watcher.start()

    def shutdown(self):
        if self.watcher:
            self.watcher.stop()
