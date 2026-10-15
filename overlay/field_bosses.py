"""Chefes de campo (field bosses): renascem um tempo depois de mortos.

- Quando um chefe morre perto de você, a leitura do jogo (net_hub/world_live) percebe sozinha e começa a
  contar o tempo até ele renascer. Também dá para marcar "morreu agora" na aba.
- 5 minutos antes e na hora em que ele renasce: aviso igual ao dos chefes do mundo, com o mini-mapa do local.

Tempos: data/field_bosses.json (servidor coreano; dá para mudar por chefe na aba).
"""
import json
import os
import time

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSpinBox, QTableWidget, QVBoxLayout, QWidget)

import sounds_player
from config import BASE_DIR, cfg, save
from i18n import N, T

PRE_MIN = 5
WORLDS = ("1010", "1110", "1011", "1111", "20")


def fb_cfg():
    c = cfg.setdefault("field_bosses", {})
    for k, v in {"auto": True, "pre": True, "at": True, "map": True, "items": {}, "world": "1110"}.items():
        c.setdefault(k, v)
    return c


def load_bosses():
    with open(os.path.join(BASE_DIR, "data", "field_bosses.json"), encoding="utf-8") as f:
        return json.load(f)


def bkey(b):
    return f"{b['world']}:{b['name']}"


def fmt_left(sec):
    sec = int(max(0, sec))
    h, m = divmod(sec // 60, 60)
    return f"{h}h{m:02d}" if h else f"{m}:{sec % 60:02d}"


class FieldBossManager(QObject):
    def __init__(self, scheduler, hub):
        super().__init__()
        self.s = scheduler                  # usa o mesmo aviso e mini-mapa dos eventos
        self.hub = hub
        self.data = load_bosses()
        self.bosses = {bkey(b): b for b in self.data["bosses"]}
        self.fired = set()
        self.on_change = None
        hub.kill.connect(self.on_kill)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        if fb_cfg()["auto"] and hub.requirements()[0]:
            QTimer.singleShot(2500, lambda: hub.acquire("bosses"))

    # ------------------------------------------------------------ estado de cada chefe
    def item(self, key):
        b = self.bosses[key]
        it = fb_cfg()["items"].setdefault(key, {})
        it.setdefault("alert", True)
        it.setdefault("minutes", b["minutes"])
        it.setdefault("dead_at", None)
        return it

    def respawn_at(self, key):
        it = self.item(key)
        if not it["dead_at"] or not it["minutes"]:
            return None
        return it["dead_at"] + it["minutes"] * 60

    def mark_dead(self, key, t=None):
        self.item(key)["dead_at"] = t or time.time()
        save()
        if self.on_change:
            self.on_change()

    def clear(self, key):
        self.item(key)["dead_at"] = None
        save()
        if self.on_change:
            self.on_change()

    def on_kill(self, ev):
        if ev.get("cat") != "named" or not ev.get("mob"):
            return
        key = f"{ev.get('world')}:{ev['mob']}"
        if key in self.bosses:
            self.mark_dead(key, ev.get("t"))

    # ------------------------------------------------------------ avisos
    def tick(self):
        c = fb_cfg()
        now = time.time()
        for key in self.bosses:
            it = self.item(key)
            t = self.respawn_at(key)
            if not t or not it["alert"]:
                continue
            left = t - now
            if c["pre"] and PRE_MIN * 60 - 20 <= left <= PRE_MIN * 60:
                self.fire(key, t, "pre")
            if c["at"] and -20 <= left <= 0:
                self.fire(key, t, "at")
            if left < -1800:                     # já renasceu faz tempo: some da contagem
                it["dead_at"] = None

    def fire(self, key, t, phase, test=False):
        k = (key, int(t), phase)
        if k in self.fired and not test:
            return
        self.fired.add(k)
        b = self.bosses[key]
        from farm import region_of
        world = T(self.s.resources()["worlds"].get(b["world"], {}).get("name", ""))
        coords = [v for xy in b["points"] for v in xy]
        region = N(region_of(b["world"], coords))
        msg = T("Renasce em {n} minutos").format(n=PRE_MIN) if phase == "pre" else T("Renasceu agora!")
        when = time.strftime("%H:%M", time.localtime(t))
        self.s.toast.push("boss", N(b["name"]), msg, T("{t} no seu relógio").format(t=when) + f" · {world} · {region}",
                          at=t)
        ec = cfg.get("events", {})
        sounds_player.play(ec.get("sound", "sounds/shugo.wav"), ec.get("volume", 80))
        if fb_cfg()["map"] and (phase == "pre" or test):
            self.show_map(key)

    def show_map(self, key):
        b = self.bosses[key]
        world = T(self.s.resources()["worlds"].get(b["world"], {}).get("name", ""))
        self.s.popup.show_location("boss", f"{N(b['name'])} — {world}", T("Chefe de campo: onde ele nasce."),
                                   b["world"], b["points"], cfg.get("events", {}).get("map_seconds", 15))


# ====================================================================== aba
class FieldBossTab(QWidget):
    COLS = ("Chefe", "Renasce a cada", "Situação", "Avisar", "", "")

    def __init__(self, manager):
        super().__init__()
        self.m = manager
        manager.on_change = self.refresh_status
        c = fb_cfg()
        lay = QVBoxLayout(self)

        top = QGroupBox("Como funciona")
        v = QVBoxLayout(top)
        lb = QLabel("Quando um chefe de campo morre perto de você, o tempo até ele renascer começa a contar sozinho "
                    "(leitura do jogo, a mesma do medidor de DPS). Longe dele, use \"Morreu agora\". "
                    f"Aviso {PRE_MIN} minutos antes e na hora, com o mini-mapa do local.")
        lb.setWordWrap(True)
        v.addWidget(lb)
        row = QHBoxLayout()
        self.chk_auto = QCheckBox("Perceber mortes sozinho")
        self.chk_auto.setChecked(c["auto"])
        self.chk_auto.toggled.connect(self.set_auto)
        row.addWidget(self.chk_auto)
        for text, key in ((f"Aviso {PRE_MIN} min antes", "pre"), ("Na hora", "at"), ("Mini-mapa", "map")):
            cb = QCheckBox(text)
            cb.setChecked(c[key])
            cb.toggled.connect(lambda on, k=key: (fb_cfg().__setitem__(k, on), save()))
            row.addWidget(cb)
        row.addStretch()
        v.addLayout(row)
        self.net = QLabel("")
        self.net.setProperty("hint", True)
        v.addWidget(self.net)
        lay.addWidget(top)

        row = QHBoxLayout()
        row.addWidget(QLabel("Mapa:"))
        self.world = QComboBox()
        res = self.m.s.resources()["worlds"]
        for wid in WORLDS:
            n = sum(1 for b in self.m.data["bosses"] if b["world"] == wid)
            if n:
                self.world.addItem(f"{T(res[wid]['name'])} ({n})", wid)
        self.world.setCurrentIndex(max(0, self.world.findData(c["world"])))
        self.world.currentIndexChanged.connect(self.fill)
        row.addWidget(self.world)
        row.addStretch()
        lay.addLayout(row)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([T(x) for x in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 150)
        self.table.setMinimumHeight(260)
        lay.addWidget(self.table, 1)

        note = QLabel(self.m.data.get("source", ""))
        note.setWordWrap(True)
        note.setProperty("hint", True)
        lay.addWidget(note)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)
        self.m.hub.running_changed.connect(lambda _on: self.refresh_net())
        self.fill()
        self.refresh_net()

    def set_auto(self, on):
        fb_cfg()["auto"] = on
        save()
        if on:
            self.m.hub.acquire("bosses")
        else:
            self.m.hub.release("bosses")
        self.refresh_net()

    def refresh_net(self):
        ok, falta = self.m.hub.requirements()
        if "bosses" in self.m.hub.users:
            self.net.setText(T("● Lendo o jogo: mortes perto de você entram sozinhas."))
        elif not ok:
            self.net.setText(T("Para perceber sozinho falta: {f} (veja a aba DPS).").format(
                f=(" " + T("e") + " ").join(T(x) for x in falta)))
        else:
            self.net.setText(T("Desligado: use \"Morreu agora\"."))

    def fill(self, *_):
        from farm import region_of
        wid = self.world.currentData()
        fb_cfg()["world"] = wid
        save()
        rows = [b for b in self.m.data["bosses"] if b["world"] == wid]
        rows.sort(key=lambda b: (b["minutes"] or 99999, N(b["name"])))
        self.keys = [bkey(b) for b in rows]
        self.table.setRowCount(len(rows))
        import icons
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QTableWidgetItem
        ic = QIcon(icons.world_boss(20))
        self.status_items = {}
        for r, b in enumerate(rows):
            key = bkey(b)
            it = self.m.item(key)
            coords = [v for xy in b["points"] for v in xy]
            region = N(region_of(b["world"], coords))
            name = QTableWidgetItem(ic, f"{N(b['name'])}\n{region}")
            name.setToolTip(f"{N(b['name'])} — {region}")
            self.table.setItem(r, 0, name)
            sp = QSpinBox()
            sp.setRange(0, 2880)
            sp.setSingleStep(30)
            sp.setSuffix(" min")
            sp.setSpecialValueText(T("defina"))
            sp.setValue(it["minutes"] or 0)
            sp.setMaximumWidth(96)
            sp.valueChanged.connect(lambda v, k=key: self.set_minutes(k, v))
            self.table.setCellWidget(r, 1, sp)
            st = QTableWidgetItem("")
            self.table.setItem(r, 2, st)
            self.status_items[key] = st
            cb = QCheckBox()
            cb.setChecked(it["alert"])
            cb.toggled.connect(lambda on, k=key: (self.m.item(k).__setitem__("alert", on), save()))
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(cb, alignment=Qt.AlignCenter)
            self.table.setCellWidget(r, 3, w)
            bmap = QPushButton(T("Mapa"))
            bmap.clicked.connect(lambda _=False, k=key: self.m.show_map(k))
            self.table.setCellWidget(r, 4, bmap)
            bdead = QPushButton(T("Morreu agora"))
            bdead.clicked.connect(lambda _=False, k=key: self.toggle_dead(k))
            self.table.setCellWidget(r, 5, bdead)
        self.refresh_status()

    def set_minutes(self, key, v):
        self.m.item(key)["minutes"] = v or None
        save()
        self.refresh_status()

    def toggle_dead(self, key):
        if self.m.respawn_at(key) and self.m.respawn_at(key) > time.time():
            self.m.clear(key)
        else:
            self.m.mark_dead(key)

    def refresh_status(self):
        if not hasattr(self, "keys"):
            return
        now = time.time()
        for r, key in enumerate(self.keys):
            st = self.status_items.get(key)
            if st is None:
                continue
            it = self.m.item(key)
            t = self.m.respawn_at(key)
            btn = self.table.cellWidget(r, 5)
            if it["dead_at"] and not it["minutes"]:
                txt = T("morto às {h} (defina o tempo)").format(h=time.strftime("%H:%M", time.localtime(it["dead_at"])))
            elif t and t > now:
                txt = T("renasce em {t} ({h})").format(t=fmt_left(t - now), h=time.strftime("%H:%M", time.localtime(t)))
            elif t:
                txt = T("vivo (renasceu às {h})").format(h=time.strftime("%H:%M", time.localtime(t)))
            else:
                txt = "—"
            st.setText(txt)
            if btn:
                btn.setText(T("Limpar") if (t and t > now) else T("Morreu agora"))
