"""Mapa próprio dos coletáveis (Berries, Gems, Herbs, Metal Ore, Od, Shellfish, Trees, Vegetables).

Dados em data/resources.json: contornos das regiões e posição de cada ponto de coleta.
Clique num ponto = marcar/desmarcar como coletado. Roda = zoom. Arrastar = mover.
"""
import json
import os
import shutil

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGraphicsEllipseItem,
                               QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSlider, QVBoxLayout, QWidget)

from i18n import N, PET, T, translate_tree
from config import APP_DIR, BASE_DIR, CATEGORIES, cfg, resolve, save

MOB_COLOR = QColor("#ff4d5e")


def load_mobs():
    with open(os.path.join(BASE_DIR, "data", "mobs.json"), encoding="utf-8") as f:
        return json.load(f)

try:
    with open(os.path.join(BASE_DIR, "fundos", "presets.json"), encoding="utf-8") as _f:
        PRESETS = json.load(_f)
except OSError:
    PRESETS = {}

CAT_COLOR = {k: QColor(c) for k, _, c in CATEGORIES}
CAT_LABEL = {k: n for k, n, _ in CATEGORIES}


def load_data():
    with open(os.path.join(BASE_DIR, "data", "resources.json"), encoding="utf-8") as f:
        return json.load(f)


class Dot(QGraphicsItem):
    """Recurso no mapa: o ícone do material (tamanho fixo na tela). Coletado = apagado;
    com timer de renascimento = apagado + anel de contagem + tempo."""

    def __init__(self, key, cat, name, region, x, y, size):
        super().__init__()
        import icons
        self.key, self.cat, self.mat = key, cat, name
        self.size = size
        self.collected = False
        self.pix = icons.material(name, size)
        self.setPos(x, -y)  # y do jogo cresce para o norte; na tela cresce para baixo
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        tip = f"{N(name)}\n{N(region)}" if region else N(name)
        if cat == "cube":
            tip += "\n" + T("Local onde o cubo pode nascer — não aparece sempre.")
        self.setToolTip(tip)
        self.setZValue(10)

    def boundingRect(self):
        s = self.size
        return QRectF(-s / 2 - 4, -s / 2 - 4, s + 8, s + 22)

    def shape(self):
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.size / 2 + 2, self.size / 2 + 2)
        return path

    def paint_state(self, collected):
        self.collected = collected
        self.update()

    def update(self, *a):
        import respawn
        self.setZValue(12 if respawn.remaining(self.key) else 10)   # com timer fica por cima
        super().update(*a)

    def paint(self, p, _opt, _w=None):
        import icons
        import respawn
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        icons.draw_resource(p, QPointF(0, 0), self.pix, self.size, respawn.remaining(self.key),
                            respawn.total(), self.collected, CAT_COLOR[self.cat])


class MapView(QGraphicsView):
    def __init__(self, on_click):
        super().__init__()
        self.on_click = on_click
        self.setRenderHints(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor("#080807"))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._press = None
        self.bg = None            # QGraphicsPixmapItem do fundo
        self.adjusting = False    # modo de encaixar o fundo
        self.on_bg_changed = None
        self._bg_drag = None

    def set_adjusting(self, on):
        self.adjusting = on
        self.setDragMode(QGraphicsView.NoDrag if on else QGraphicsView.ScrollHandDrag)
        self.viewport().setCursor(Qt.SizeAllCursor if on else Qt.OpenHandCursor)

    def wheelEvent(self, e):
        up = e.angleDelta().y() > 0
        if self.adjusting and self.bg and e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            # Ctrl = escala rápida, Shift = escala fina, mantendo o ponto sob o mouse
            step = 1.05 if e.modifiers() & Qt.ControlModifier else 1.005
            f = step if up else 1 / step
            anchor = self.mapToScene(e.position().toPoint())
            local = self.bg.mapFromScene(anchor)
            self.bg.setScale(self.bg.scale() * f)
            self.bg.setPos(self.bg.pos() + anchor - self.bg.mapToScene(local))
            if self.on_bg_changed:
                self.on_bg_changed()
            return
        f = 1.25 if up else 1 / 1.25
        self.scale(f, f)

    def mousePressEvent(self, e):
        self._press = e.position().toPoint()
        if self.adjusting and self.bg and e.button() == Qt.LeftButton:
            self._bg_drag = (self.mapToScene(self._press), self.bg.pos())
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._bg_drag:
            start, pos0 = self._bg_drag
            self.bg.setPos(pos0 + self.mapToScene(e.position().toPoint()) - start)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._bg_drag:
            self._bg_drag = None
            self._press = None
            if self.on_bg_changed:
                self.on_bg_changed()
            return
        super().mouseReleaseEvent(e)
        if self._press is not None and (e.position().toPoint() - self._press).manhattanLength() < 5:
            for it in self.items(e.position().toPoint()):
                if isinstance(it, Dot):
                    if e.button() == Qt.RightButton and getattr(self, "on_right", None):
                        self.on_right(it)        # clique direito: timer de renascimento
                    else:
                        self.on_click(it)
                    break
        self._press = None


class MapWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("Aion 2 — Mapa")
        self.on_farm = None          # chamado quando o usuário escolhe um mob para farmar
        self.mob_items = []
        self.mobs = load_mobs()
        self.data = load_data()
        self.dots = []
        self.labels = []
        self.region_items = []
        self.collected = set(cfg["map"].get("collected", []))
        # redesenha a contagem dos timers de renascimento uma vez por segundo
        from PySide6.QtCore import QTimer
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_timers)
        self._tick.start(1000)
        self._timer_keys = set()
        self.resize(1100, 760)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QFrame()
        side.setStyleSheet("""
            QFrame{background:#100f0d;} QLabel{color:#e3ddd0;} QCheckBox{color:#e3ddd0; spacing:6px;}
            QComboBox,QPushButton{background:#1d1a16; color:#eee8dc; border:1px solid #3a3429;
                border-radius:5px; padding:4px 8px;}
            QPushButton:hover{background:#2c271f;}
            QPushButton:checked{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #e0b04f,stop:1 #a8742a); color:#0a0908; border:none;}
            QLineEdit,QListWidget{background:#0e0d0b; color:#eee8dc; border:1px solid #3a3429; border-radius:5px;}
            QListWidget::item{padding:3px;} QListWidget::item:selected{background:#2c271f;}""")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 12, 12)
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(272)
        side.setMaximumWidth(256)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none; background:#100f0d; border-right:1px solid #2a261f;}")

        self.world = QComboBox()
        for wid, w in self.data["worlds"].items():
            self.world.addItem(f"{T(w['name'])} — {T(w['faction'])}", wid)
        sl.addWidget(QLabel("<b>Mapa</b>"))
        sl.addWidget(self.world)

        mode = QHBoxLayout()
        self.mode_collect = QPushButton("Coletáveis")
        self.mode_mobs = QPushButton("Farm de pet")
        for b in (self.mode_collect, self.mode_mobs):
            b.setCheckable(True)
            mode.addWidget(b)
        self.mode_collect.clicked.connect(lambda: self.set_mode("collect"))
        self.mode_mobs.clicked.connect(lambda: self.set_mode("mobs"))
        sl.addLayout(mode)

        self.counter = QLabel()
        self.counter.setStyleSheet("color:#e0b04f; font-size:14px; font-weight:600; padding:6px 0;")
        self.counter.setWordWrap(True)
        sl.addWidget(self.counter)

        # ----- painel: farm de pet (monstros)
        self.mob_panel = QWidget()
        ml = QVBoxLayout(self.mob_panel)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("<b>Procurar monstro</b>"))
        self.mob_search = QLineEdit()
        self.mob_search.setPlaceholderText("nome do mob ou do pet (ex.: Abelha Mutante)")
        self.mob_search.textChanged.connect(self.fill_mob_list)
        ml.addWidget(self.mob_search)
        self.only_tame = QCheckBox("Só mobs que dão alma de pet")
        self.only_tame.setChecked(cfg["map"].get("only_tame", True))
        self.only_tame.toggled.connect(lambda on: (cfg["map"].__setitem__("only_tame", on), save(),
                                                   self.fill_mob_list()))
        ml.addWidget(self.only_tame)
        self.mob_list = QListWidget()
        self.mob_list.setMinimumHeight(260)
        self.mob_list.currentItemChanged.connect(self.show_mob)
        ml.addWidget(self.mob_list)
        self.mob_info = QLabel("")
        self.mob_info.setWordWrap(True)
        ml.addWidget(self.mob_info)
        self.btn_farm = QPushButton("Farmar este mob")
        self.btn_farm.clicked.connect(self.farm_selected)
        ml.addWidget(self.btn_farm)
        sl.addWidget(self.mob_panel)

        # ----- painel: coletáveis
        self.collect_panel = QWidget()
        cl = QVBoxLayout(self.collect_panel)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("<b>Coletáveis</b>"))
        self.cat_checks = {}
        for k, name, color in CATEGORIES:
            cb = QCheckBox()
            cb.setChecked(cfg["map"]["filters"].get(k, True))
            import icons
            from PySide6.QtGui import QIcon
            cb.setIcon(QIcon(icons.category(k, 40)))
            from PySide6.QtCore import QSize
            cb.setIconSize(QSize(22, 22))
            cb.toggled.connect(self.apply_filters)
            if k == "cube":
                cb.setToolTip(T("Locais onde o Hidden Cube PODE nascer. Não é garantido: o cubo aparece só em "
                                "alguns deles."))
            self.cat_checks[k] = cb
            cl.addWidget(cb)
        cube_note = QLabel("Hidden Cube: são locais onde ele pode nascer, não aparece em todos.")
        cube_note.setWordWrap(True)
        cube_note.setStyleSheet("color:#9b9282; font-size:8pt;")
        cl.addWidget(cube_note)
        row = QHBoxLayout()
        ball = QPushButton("Todos")
        ball.clicked.connect(lambda: self.set_all(True))
        bnone = QPushButton("Nenhum")
        bnone.clicked.connect(lambda: self.set_all(False))
        row.addWidget(ball)
        row.addWidget(bnone)
        cl.addLayout(row)

        cl.addWidget(QLabel("<b>Material específico</b>"))
        self.material = QComboBox()
        self.material.currentIndexChanged.connect(self.apply_filters)
        cl.addWidget(self.material)
        self.hide_col = QCheckBox("Esconder coletados")
        cl.addWidget(self.hide_col)
        breset = QPushButton("Limpar coletados deste mapa")
        breset.clicked.connect(self.clear_collected)
        cl.addWidget(breset)
        sl.addWidget(self.collect_panel)

        sl.addSpacing(6)
        self.hide_col.setChecked(cfg["map"].get("hide_collected", False))
        self.show_reg = QCheckBox("Mostrar regiões")
        self.show_reg.setChecked(cfg["map"].get("show_regions", True))
        self.show_lab = QCheckBox("Mostrar nomes")
        self.show_lab.setChecked(cfg["map"].get("show_labels", True))
        self.on_top = QCheckBox("Sempre por cima do jogo")
        self.on_top.setChecked(cfg["map"].get("on_top", True))
        self.hide_col.toggled.connect(self.apply_filters)
        for cb in (self.show_reg, self.show_lab):
            cb.toggled.connect(self.apply_filters)
            sl.addWidget(cb)
        self.on_top.toggled.connect(self.set_on_top)
        sl.addWidget(self.on_top)

        sl.addWidget(QLabel("Transparência"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(int(cfg["map"].get("opacity", 1.0) * 100))
        self.opacity.valueChanged.connect(self.set_opacity)
        sl.addWidget(self.opacity)

        sl.addSpacing(6)
        sl.addWidget(QLabel("<b>Imagem de fundo</b>"))
        row = QHBoxLayout()
        bload = QPushButton("Carregar...")
        bload.clicked.connect(self.load_background)
        brem = QPushButton("Remover")
        brem.clicked.connect(self.remove_background)
        row.addWidget(bload)
        row.addWidget(brem)
        sl.addLayout(row)
        self.adjust = QPushButton("Ajustar fundo")
        self.adjust.setCheckable(True)
        self.adjust.toggled.connect(self.toggle_adjust)
        sl.addWidget(self.adjust)
        self.bg_opacity = QSlider(Qt.Horizontal)
        self.bg_opacity.setRange(10, 100)
        self.bg_opacity.valueChanged.connect(self.set_bg_opacity)
        sl.addWidget(self.bg_opacity)
        self.adjust_hint = QLabel("Arraste = mover o fundo\nCtrl+roda = tamanho · Shift+roda = ajuste fino\n"
                                  "Encaixe o desenho nas linhas das regiões.")
        self.adjust_hint.setStyleSheet("color:#f5c542; font-size:11px;")
        self.adjust_hint.setWordWrap(True)
        self.adjust_hint.hide()
        sl.addWidget(self.adjust_hint)

        bfit = QPushButton("Centralizar mapa")
        bfit.clicked.connect(self.fit)
        sl.addWidget(bfit)
        sl.addStretch()
        hint = QLabel("Coletáveis: clique num ponto para marcar como coletado.\nRoda do mouse = zoom · arrastar = mover")
        hint.setStyleSheet("color:#8a8272; font-size:11px;")
        hint.setWordWrap(True)
        sl.addWidget(hint)

        self.scene = QGraphicsScene(self)
        self.view = MapView(self.toggle_collected)
        self.view.on_right = self.toggle_timer
        self.view.setScene(self.scene)
        root.addWidget(scroll)
        root.addWidget(self.view, 1)

        idx = self.world.findData(cfg["map"].get("world", "1010"))
        self.world.setCurrentIndex(max(0, idx))
        self.world.currentIndexChanged.connect(self.build)
        self.set_on_top(self.on_top.isChecked(), first=True)
        self.set_opacity(self.opacity.value())
        geo = cfg["map"].get("geometry")
        if geo:
            self.setGeometry(*geo)
        self.mode = cfg["map"].get("mode", "collect")
        translate_tree(self)
        self.build()
        self.set_mode(self.mode)

    # ---------------------------------------------------------- construção
    def build(self):
        wid = self.world.currentData()
        cfg["map"]["world"] = wid
        w = self.data["worlds"][wid]
        names = self.data["names"]
        self.adjust.setChecked(False)
        self.scene.clear()
        self.dots, self.labels, self.region_items = [], [], []
        self.view.bg = None
        self.view.on_bg_changed = self.save_background

        bgc = cfg["map"].setdefault("backgrounds", {}).get(wid)
        old_preset = bgc and bgc.get("path", "").startswith("fundos/") and \
            wid in PRESETS and bgc["path"] != PRESETS[wid]["path"]
        if (bgc is None or old_preset) and wid in PRESETS:  # fundo que já vem alinhado com o programa
            bgc = dict(PRESETS[wid])
            cfg["map"]["backgrounds"][wid] = bgc
        has_bg = False
        if bgc and os.path.exists(resolve(bgc.get("path", ""))):
            pm = QPixmap(resolve(bgc["path"]))
            if not pm.isNull():
                bg = QGraphicsPixmapItem(pm)
                bg.setTransformationMode(Qt.SmoothTransformation)
                bg.setZValue(0)
                bg.setPos(bgc.get("x", 0), bgc.get("y", 0))
                bg.setScale(bgc.get("scale", 1.0))
                bg.setOpacity(bgc.get("opacity", 1.0))
                self.scene.addItem(bg)
                self.view.bg = bg
                has_bg = True
        self.bg_opacity.blockSignals(True)
        self.bg_opacity.setValue(int((bgc or {}).get("opacity", 1.0) * 100))
        self.bg_opacity.blockSignals(False)

        for r in w["regions"]:
            path = QPainterPath()
            for poly in r["p"]:
                path.addPolygon(QPolygonF([QPointF(x, -y) for x, y in poly]))
                path.closeSubpath()
            it = QGraphicsPathItem(path)
            base = r["r"] == 1
            it.setPen(QPen(QColor(150, 135, 105, 200 if base else 90), 1.6 if base else 0.8))
            it.pen().setCosmetic(True)
            pen = it.pen()
            pen.setCosmetic(True)
            it.setPen(pen)
            it.setBrush(QColor(36, 32, 26, 255) if base and not has_bg else Qt.NoBrush)
            it.setZValue(1 if base else 2)
            self.scene.addItem(it)
            self.region_items.append(it)
            if base or r["k"] == "village":
                t = QGraphicsSimpleTextItem(N(r["n"]).upper() if base else N(r["n"]))
                t.setFont(QFont("Segoe UI", 8 if base else 7, QFont.Bold if base else QFont.Normal))
                t.setBrush(QColor(238, 230, 214, 230) if base else QColor(245, 197, 66, 220))
                t.setPen(QPen(QColor(0, 0, 0, 170), 0.45))  # contorno escuro: legível em fundo claro
                t.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                t.setPos(r["l"][0], -r["l"][1])
                t.setZValue(20)
                self.scene.addItem(t)
                self.labels.append(t)

        size = cfg["map"].get("icon_size", 20)
        mats = set()
        for cat, ni, x, y, region in w["points"]:
            key = f"{wid}:{x}:{y}:{cat}"
            d = Dot(key, cat, names[ni], region, x, y, size)
            d.mat = names[ni]
            mats.add((cat, names[ni]))
            d.paint_state(key in self.collected)
            self.scene.addItem(d)
            self.dots.append(d)

        self.material.blockSignals(True)
        self.material.clear()
        self.material.addItem(T("Todos os materiais"), "")
        for cat, name in sorted(mats, key=lambda m: (CAT_LABEL[m[0]], N(m[1]))):
            self.material.addItem(f"{N(name)}  ({CAT_LABEL[cat].split(' (')[0]})", name)
        i = self.material.findData(cfg["map"].get("material", ""))
        self.material.setCurrentIndex(max(0, i))
        self.material.blockSignals(False)

        counts = {}
        for d in self.dots:
            counts[d.cat] = counts.get(d.cat, 0) + 1
        for k, cb in self.cat_checks.items():
            cb.setText(f"{T(CAT_LABEL[k])}   {counts.get(k, 0)}")
            cb.setEnabled(k in counts)

        rect = self.scene.itemsBoundingRect()
        self.scene.setSceneRect(rect.adjusted(-rect.width() * .3, -rect.height() * .3,
                                              rect.width() * .3, rect.height() * .3))
        self.mob_items = []
        self.apply_filters()
        self.fit()
        if getattr(self, "mode", "collect") == "mobs":
            self.mob_list.setCurrentItem(None)
            self.fill_mob_list()
        save()

    def fit(self):
        if not self.dots:  # mapa sem pontos de coleta (ex.: Reshanta Média): enquadra as regiões
            r = QRectF()
            for it in self.region_items:
                r = r.united(it.sceneBoundingRect())
            if not r.isNull():
                self.view.resetTransform()
                self.view.fitInView(r, Qt.KeepAspectRatio)
                return
        pts = [d.pos() for d in self.dots] or [QPointF(0, 0)]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        r = QRectF(min(xs), min(ys), max(xs) - min(xs) or 1, max(ys) - min(ys) or 1)
        self.view.resetTransform()
        self.view.fitInView(r.adjusted(-r.width() * .05, -r.height() * .05, r.width() * .05, r.height() * .05),
                            Qt.KeepAspectRatio)

    # ---------------------------------------------------------- filtros
    def set_all(self, on):
        for cb in self.cat_checks.values():
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
        self.apply_filters()

    def apply_filters(self):
        m = cfg["map"]
        m["filters"] = {k: cb.isChecked() for k, cb in self.cat_checks.items()}
        m["material"] = self.material.currentData() or ""
        m["hide_collected"] = self.hide_col.isChecked()
        m["show_regions"] = self.show_reg.isChecked()
        m["show_labels"] = self.show_lab.isChecked()
        mat = m["material"]
        shown = total = done = 0
        for d in self.dots:
            ok = m["filters"].get(d.cat, True) and (not mat or d.mat == mat)
            if ok:
                total += 1
                if d.key in self.collected:
                    done += 1
            vis = ok and not (m["hide_collected"] and d.key in self.collected)
            d.setVisible(vis)
            shown += vis
        for it in self.region_items:
            it.setVisible(m["show_regions"] or it.zValue() == 1)
            if it.zValue() == 1:
                it.setPen(QPen(QColor(150, 135, 105, 200 if m["show_regions"] else 0), 1.6))
                pen = it.pen()
                pen.setCosmetic(True)
                it.setPen(pen)
        for t in self.labels:
            t.setVisible(m["show_labels"])
        if getattr(self, "mode", "collect") == "mobs":
            for d in self.dots:
                d.setVisible(False)
        else:
            self.counter.setText(T("Coletados: {a} / {b}").format(a=done, b=total))
        save()

    def _refresh_timers(self):
        import respawn
        keys = respawn.active_keys()
        changed = keys | self._timer_keys
        self._timer_keys = keys
        if changed and self.isVisible():
            for d in self.dots:
                if d.key in changed:
                    d.update()

    def toggle_timer(self, dot):
        import respawn
        if respawn.remaining(dot.key) is None:
            respawn.start(dot.key)
        else:
            respawn.cancel(dot.key)
        dot.update()

    def toggle_collected(self, dot):
        if dot.key in self.collected:
            self.collected.discard(dot.key)
        else:
            self.collected.add(dot.key)
        dot.paint_state(dot.key in self.collected)
        cfg["map"]["collected"] = sorted(self.collected)
        self.apply_filters()

    def clear_collected(self):
        wid = self.world.currentData()
        self.collected = {k for k in self.collected if not k.startswith(wid + ":")}
        for d in self.dots:
            d.paint_state(False)
        cfg["map"]["collected"] = sorted(self.collected)
        self.apply_filters()

    # ---------------------------------------------------------- farm de pet (monstros)
    def set_mode(self, mode):
        self.mode = mode
        cfg["map"]["mode"] = mode
        self.mode_collect.setChecked(mode == "collect")
        self.mode_mobs.setChecked(mode == "mobs")
        self.collect_panel.setVisible(mode == "collect")
        self.mob_panel.setVisible(mode == "mobs")
        if mode == "mobs":
            self.fill_mob_list()
        else:
            self.clear_mob_dots()
        self.apply_filters()

    def world_mobs(self):
        return self.mobs["worlds"].get(self.world.currentData(), [])

    def pet_name(self, pet_id):
        for pid, name, _ in self.mobs["pets"]:
            if pid == pet_id:
                return PET(pid, name)
        return ""

    def fill_mob_list(self):
        import unicodedata
        norm = lambda t: unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        q = norm(self.mob_search.text().strip())
        sel = self.mob_list.currentItem().data(Qt.UserRole) if self.mob_list.currentItem() else None
        self.mob_list.blockSignals(True)
        self.mob_list.clear()
        keep = None
        only = self.only_tame.isChecked()
        for i, (name, cat, coords) in enumerate(self.world_mobs()):
            pet = self.pet_name(self.mobs["suggest"].get(name, ""))
            if only and not pet:
                continue
            if q and q not in norm(name) and q not in norm(pet) and q not in norm(N(name)):
                continue
            it = QListWidgetItem(f"{N(name)}  ({len(coords) // 2})" + ("\n    " + T("alma: {p}").format(p=pet) if pet else ""))
            it.setData(Qt.UserRole, i)
            self.mob_list.addItem(it)
            if i == sel:
                keep = it
        self.mob_list.blockSignals(False)
        if keep:
            self.mob_list.setCurrentItem(keep)
        if self.mode == "mobs":
            n = self.mob_list.count()
            if q:
                self.counter.setText(T("{n} encontrados").format(n=n))
            else:
                self.counter.setText(T("{n} mobs que dão alma neste mapa").format(n=n) if only
                                     else T("{n} monstros neste mapa").format(n=n))

    def focus_mob(self, wid, mob):
        """Abre o mapa certo no modo Farm de pet e seleciona o mob (usado pelo "Ver no mapa" da aba)."""
        i = self.world.findData(wid)
        if i >= 0 and i != self.world.currentIndex():
            self.world.setCurrentIndex(i)
        self.set_mode("mobs")
        self.mode_collect.setChecked(False)
        self.mode_mobs.setChecked(True)
        self.mob_search.setText("")
        for r in range(self.mob_list.count()):
            it = self.mob_list.item(r)
            if self.world_mobs()[it.data(Qt.UserRole)][0] == mob:
                self.mob_list.setCurrentItem(it)
                self.mob_list.scrollToItem(it)
                break

    def clear_mob_dots(self):
        for it in self.mob_items:
            self.scene.removeItem(it)
        self.mob_items = []

    def show_mob(self, item, _prev=None):
        self.clear_mob_dots()
        if item is None:
            return
        name, cat, coords = self.world_mobs()[item.data(Qt.UserRole)]
        pts = [QPointF(coords[i], -coords[i + 1]) for i in range(0, len(coords), 2)]
        for p in pts:
            d = QGraphicsEllipseItem(-5, -5, 10, 10)
            d.setPos(p)
            d.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            d.setBrush(MOB_COLOR)
            d.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
            d.setZValue(15)
            d.setToolTip(N(name))
            self.scene.addItem(d)
            self.mob_items.append(d)
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        r = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        pad = max(r.width(), r.height(), 25000) * 0.6
        self.view.resetTransform()
        self.view.fitInView(r.adjusted(-pad, -pad, pad, pad), Qt.KeepAspectRatio)
        pet = self.pet_name(self.mobs["suggest"].get(name, ""))
        self.mob_info.setText(f"<b>{N(name)}</b><br>{len(pts)} {T('pontos de spawn')}<br>"
                              + (T("Dá a alma de: <b>{p}</b>").format(p=pet) if pet else T("Esse mob não dá alma de pet.")))
        self.counter.setText(T("{n} spawns de {m}").format(n=len(pts), m=N(name)))

    def farm_selected(self):
        item = self.mob_list.currentItem()
        if not item:
            QMessageBox.information(self, "Farm", T("Escolha um monstro na lista."))
            return
        name, cat, coords = self.world_mobs()[item.data(Qt.UserRole)]
        if self.on_farm:
            self.on_farm(self.world.currentData(), name, coords, self.mobs["suggest"].get(name, ""))

    # ---------------------------------------------------------- imagem de fundo
    def load_background(self):
        path, _ = QFileDialog.getOpenFileName(self, "Imagem de fundo do mapa", "",
                                              "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "Mapa", T("Não consegui abrir essa imagem."))
            return
        wid = self.world.currentData()
        os.makedirs(os.path.join(APP_DIR, "fundos"), exist_ok=True)
        dest = os.path.join(APP_DIR, "fundos", f"{wid}{os.path.splitext(path)[1].lower()}")
        if os.path.abspath(path) != os.path.abspath(dest):
            try:
                shutil.copyfile(path, dest)
            except OSError:
                QMessageBox.warning(self, "Mapa", T("Não consegui abrir essa imagem."))
                return
        # posição inicial: imagem esticada sobre a área das regiões, para começar perto do encaixe
        area = QRectF()
        for it in self.region_items:
            if it.zValue() == 1:
                area = area.united(it.sceneBoundingRect())
        if area.isNull():
            area = self.scene.itemsBoundingRect()
        scale = min(area.width() / pm.width(), area.height() / pm.height())
        cfg["map"].setdefault("backgrounds", {})[wid] = {
            "path": dest, "scale": scale, "opacity": 1.0,
            "x": area.center().x() - pm.width() * scale / 2,
            "y": area.center().y() - pm.height() * scale / 2,
        }
        save()
        self.build()
        self.adjust.setChecked(True)

    def remove_background(self):
        cfg["map"].setdefault("backgrounds", {})[self.world.currentData()] = {"path": ""}
        save()
        self.adjust.setChecked(False)
        self.build()

    def toggle_adjust(self, on):
        if on and not self.view.bg:
            self.adjust.setChecked(False)
            return
        self.view.set_adjusting(on)
        self.adjust_hint.setVisible(on)
        self.adjust.setText(T("Concluir ajuste") if on else T("Ajustar fundo"))
        # durante o ajuste os contornos ficam fortes para servir de guia
        for it in self.region_items:
            base = it.zValue() == 1
            if on:
                pen = QPen(QColor(255, 210, 60, 230), 1.6)
            else:
                pen = QPen(QColor(150, 135, 105, 200 if base else 90), 1.6 if base else 0.8)
            pen.setCosmetic(True)
            it.setPen(pen)
        for d in self.dots:
            d.setVisible(False if on else d.isVisible())
        if not on:
            self.apply_filters()

    def set_bg_opacity(self, v):
        if self.view.bg:
            self.view.bg.setOpacity(v / 100)
            self.save_background()

    def save_background(self):
        bg = self.view.bg
        bgc = cfg["map"].get("backgrounds", {}).get(self.world.currentData())
        if bg and bgc:
            bgc.update(x=bg.pos().x(), y=bg.pos().y(), scale=bg.scale(), opacity=bg.opacity())
            save()

    # ---------------------------------------------------------- janela
    def set_on_top(self, on, first=False):
        cfg["map"]["on_top"] = on
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if vis and not first:
            self.show()
        save()

    def set_opacity(self, v):
        cfg["map"]["opacity"] = v / 100
        self.setWindowOpacity(v / 100)

    def move_to_screen(self, screen):
        g = screen.availableGeometry()
        self.move(g.x() + 60, g.y() + 60)
        self.closeEvent(None)

    def closeEvent(self, e):
        g = self.geometry()
        cfg["map"]["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        save()
        if e is not None:
            e.accept()
