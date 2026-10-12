"""Avisos de eventos com horário fixo: Fendas (rifts), chefes de Reshanta e outros.

Horários do servidor (fuso do servidor escolhido, padrão América do Sul / São Paulo),
convertidos automaticamente para o relógio do PC. Cada evento pode avisar 5 min antes,
na hora e, opcionalmente, abrir um mini-mapa com o local 5 min antes.
"""
import json
import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from PySide6.QtCore import QPointF, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import sounds_player
from base_window import OverlayWindow
from i18n import T
from config import BASE_DIR, cfg, save

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ICONS = {"rift": "🌀", "boss": "👹", "event": "🛡️"}
COLORS = {"rift": "#a77bff", "boss": "#ff5a6a", "event": "#4fb3ff"}
PRE_MIN = 5


def load_events():
    with open(os.path.join(BASE_DIR, "data", "events.json"), encoding="utf-8") as f:
        return json.load(f)


def ev_cfg():
    c = cfg.setdefault("events", {})
    c.setdefault("region", "global-sa")
    c.setdefault("faction", "1110")      # mapa usado no mapa das fendas
    c.setdefault("sound", "sounds/shugo.wav")
    c.setdefault("volume", 80)
    c.setdefault("items", {})
    c.setdefault("toast_seconds", 6)
    if not c.get("_v2"):              # versão antiga deixava o mini-mapa 60 s na tela
        c["map_seconds"] = 15
        c["_v2"] = True
    c.setdefault("map_seconds", 15)
    return c


def item_cfg(ev):
    items = ev_cfg()["items"]
    it = items.setdefault(ev["id"], dict(ev["default"]))
    for k, v in ev["default"].items():
        it.setdefault(k, v)
    return it


def server_tz(region_id, data):
    name = data["regions"].get(region_id, ["", "America/Sao_Paulo"])[1]
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=-3))  # São Paulo sem horário de verão


def occurrences(ev, region_id, data, start, hours=200):
    """Próximos horários (datetime com fuso) a partir de 'start'."""
    sch = ev["schedule"].get(region_id) or next(iter(ev["schedule"].values()))
    tz = server_tz(region_id, data)
    s = start.astimezone(tz)
    out = []
    if sch["type"] == "hourly":
        t = s.replace(minute=sch["minute"], second=0, microsecond=0)
        if t < s:
            t += timedelta(hours=1)
        for i in range(hours):
            out.append(t + timedelta(hours=i))
        return out
    day0 = s.replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(0, hours // 24 + 8):
        day = day0 + timedelta(days=d)
        if sch["type"] == "weekly" and DAYS[day.weekday()] not in sch["days"]:
            continue
        for hm in sch["times"]:
            h, m = map(int, hm.split(":"))
            # recria com o fuso para respeitar horário de verão do servidor
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if t >= s:
                out.append(t)
    return sorted(out)


# ====================================================================== avisos (fila)
class EventToast(OverlayWindow):
    SHOW_SECONDS = 10

    def __init__(self):
        cfg.setdefault("event_toast", {"pos": None, "opacity": 0.95})
        super().__init__("event_toast", QPoint(40, 300))
        self.setFixedSize(340, 82)
        self.queue = []
        self.cur = None
        self._hide_at = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(400)

    def push(self, kind, title, msg, sub):
        self.queue.append((kind, title, msg, sub))
        if self.cur is None:
            self.next()

    def next(self):
        if not self.queue:
            self.cur = None
            self.hide()
            return
        self.cur = self.queue.pop(0)
        self._hide_at = datetime.now() + timedelta(seconds=ev_cfg().get("toast_seconds", 6))
        self.show()
        self.raise_()
        self.update()

    def tick(self):
        if self.cur and datetime.now() >= self._hide_at:
            self.next()
        elif self.cur:
            on = int(datetime.now().timestamp() * 2) % 2 == 0
            col = QColor(COLORS.get(self.cur[0], "#f5c542"))
            if not on:
                col.setAlpha(90)
            self._accent = col
            self.update()

    def mouseDoubleClickEvent(self, e):
        self.next()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.cur:
            return
        kind, title, msg, sub = self.cur
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(COLORS.get(kind, "#f5c542"))
        import theme
        # losango grande na cor do tipo de evento, com o símbolo desenhado dentro
        ctr = QPointF(42, 41)
        bg = QColor(c)
        bg.setAlpha(45)
        theme.draw_diamond(p, ctr, 27, bg, c)
        if kind == "boss":
            import icons
            pm = icons.world_boss(40)
            if not pm.isNull():
                p.drawPixmap(QRectF(22, 21, 40, 40), pm, QRectF(pm.rect()))
            else:
                theme.draw_glyph(p, "pvp", QRectF(29, 28, 26, 26), c.lighter(130))
        else:
            glyph = {"rift": "rifts", "event": "shield"}.get(kind, "shugo")
            theme.draw_glyph(p, glyph, QRectF(29, 28, 26, 26), c.lighter(130))
        p.setPen(c)
        p.setFont(theme.display_font(10.5))
        p.drawText(QRectF(82, 10, 250, 18), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 14, QFont.Bold))
        p.drawText(QRectF(82, 28, 250, 26), Qt.AlignLeft | Qt.AlignVCenter, msg)
        p.setPen(QColor("#b9b3d6"))
        f = QFont("Segoe UI", 8)
        p.setFont(f)
        p.drawText(QRectF(82, 54, 250, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(sub, Qt.ElideRight, 248))
        p.end()


# ====================================================================== mini-mapa do local
class LocationPopup(OverlayWindow):
    W, H = 380, 300

    def __init__(self):
        cfg.setdefault("event_map", {"pos": None, "opacity": 0.97})
        super().__init__("event_map", QPoint(400, 120))
        self.setFixedSize(self.W, self.H)
        self.pix = None
        self.title = ""
        self.sub = ""
        self.kind = "boss"
        self._hide_at = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)

    def show_location(self, kind, title, sub, world, points, seconds=60):
        from farm import render_minimap
        coords = [v for xy in points for v in xy]
        marker = None
        if kind == "boss":
            import icons
            marker = icons.world_boss(34)
        self.pix = render_minimap(world, coords, self.W - 4, self.H - 66, marker)
        self.kind, self.title, self.sub = kind, title, sub
        self._hide_at = datetime.now() + timedelta(seconds=seconds)
        self.show()
        self.raise_()
        self.update()

    def _tick(self):
        if self._hide_at and datetime.now() >= self._hide_at:
            self._hide_at = None
            self.hide()

    def mouseDoubleClickEvent(self, e):
        self._hide_at = None
        self.hide()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(COLORS.get(self.kind, "#f5c542"))
        p.setPen(c)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(QRectF(14, 8, self.W - 28, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(QColor("#b9b3d6"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(14, 30, self.W - 28, 30), Qt.AlignLeft | Qt.TextWordWrap, self.sub)
        if self.pix:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(2, 64, self.W - 4, self.H - 66), 8, 8)
            p.setClipPath(clip)
            p.drawPixmap(2, 64, self.pix)
        p.end()


# ====================================================================== agendador
class EventScheduler:
    def __init__(self):
        self.data = load_events()
        self.toast = EventToast()
        self.popup = LocationPopup()
        self.fired = set()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def resources(self):
        from farm import _resources
        return _resources()

    def next_time(self, ev):
        now = datetime.now(timezone.utc)
        occ = occurrences(ev, ev_cfg()["region"], self.data, now - timedelta(minutes=1), hours=200)
        return occ[0] if occ else None

    def tick(self):
        now = datetime.now(timezone.utc)
        region = ev_cfg()["region"]
        for ev in self.data["events"]:
            it = item_cfg(ev)
            if not it["enabled"]:
                continue
            for t in occurrences(ev, region, self.data, now - timedelta(seconds=30), hours=3)[:3]:
                left = (t - now).total_seconds()
                if it["pre"] and PRE_MIN * 60 - 20 <= left <= PRE_MIN * 60:
                    self.fire(ev, t, "pre")
                if it["at"] and -20 <= left <= 0:
                    self.fire(ev, t, "at")

    def fire(self, ev, t, phase, test=False):
        key = (ev["id"], t.isoformat(), phase)
        if key in self.fired and not test:
            return
        self.fired.add(key)
        it = item_cfg(ev)
        local = t.astimezone()
        if phase == "pre":
            msg = T("Em {n} minutos" if ev["kind"] != "rift" else "Abre em {n} minutos").format(n=PRE_MIN)
        else:
            msg = T({"rift": "Abriu agora!", "boss": "Nasceu agora!"}.get(ev["kind"], "Começou agora!"))
        sub = T("{t} no seu relógio").format(t=f"{local:%H:%M}") + (f" · {T(ev['note'])}" if ev["note"] else "")
        self.toast.push(ev["kind"], T(ev["name"]), msg, sub)
        c = ev_cfg()
        sounds_player.play(c["sound"], c["volume"])
        if phase == "pre" and it.get("map"):
            self.show_map(ev)

    def show_map(self, ev):
        m = ev.get("map")
        if m == "rifts":
            wid = ev_cfg()["faction"]
            pts = self.resources()["worlds"].get(wid, {}).get("rifts", [])
            world_name = T(self.resources()["worlds"].get(wid, {}).get("name", ""))
            if pts:
                self.popup.show_location(ev["kind"], f"{T(ev['name'])} — {world_name}",
                                         T("Locais possíveis das fendas neste mapa."), wid, pts, ev_cfg()["map_seconds"])
        elif m:
            name = T(self.resources()["worlds"].get(m["world"], {}).get("name", ""))
            self.popup.show_location(ev["kind"], f"{T(ev['name'])} — {name}", T(ev["note"]), m["world"], m["points"],
                                     ev_cfg()["map_seconds"])

    def set_locked(self, on):
        self.toast.set_locked(on)
        self.popup.set_locked(on)


# ====================================================================== aba do painel
class EventsTab(QWidget):
    def __init__(self, scheduler, sound_row_cls):
        super().__init__()
        self.s = scheduler
        c = ev_cfg()
        lay = QVBoxLayout(self)

        top = QGroupBox("Servidor")
        f = QFormLayout(top)
        self.region = QComboBox()
        for rid, (label, tz) in self.s.data["regions"].items():
            self.region.addItem(f"{label}  ({tz})", rid)
        self.region.setCurrentIndex(max(0, self.region.findData(c["region"])))
        self.region.currentIndexChanged.connect(self.region_changed)
        f.addRow("Região:", self.region)
        self.faction = QComboBox()
        for wid in ("1010", "1011", "1110", "1111"):
            w = self.s.resources()["worlds"][wid]
            self.faction.addItem(f"{T(w['name'])} ({T(w['faction'])})", wid)
        self.faction.setCurrentIndex(max(0, self.faction.findData(c["faction"])))
        self.faction.currentIndexChanged.connect(lambda _i: self.set_cfg("faction", self.faction.currentData()))
        f.addRow("Mapa das fendas:", self.faction)
        f.addRow(QLabel("Horários convertidos sozinhos para o relógio do seu PC."))
        lay.addWidget(top)

        box = QGroupBox(f"Eventos — avisos {PRE_MIN} min antes e na hora")
        g = QGridLayout(box)
        for col, h in enumerate(("Evento", "Ativo", f"{PRE_MIN} min antes", "Na hora", f"Mapa {PRE_MIN} min antes",
                                 "Próximo", "")):
            lb = QLabel(f"<b>{h}</b>")
            g.addWidget(lb, 0, col)
        self.next_labels = {}
        for row, ev in enumerate(self.s.data["events"], 1):
            it = item_cfg(ev)
            if ev["kind"] == "boss":
                import icons
                lbl = QLabel()
                lbl.setText(f"<img src='{os.path.join(icons.FOLDER, 'world_boss.png').replace(chr(92), '/')}' "
                            f"width='18' height='18' style='vertical-align:middle'>&nbsp; {T(ev['name'])}")
                g.addWidget(lbl, row, 0)
            else:
                g.addWidget(QLabel(f"<span style='color:{COLORS.get(ev['kind'], '#6fd3ff')}'>◆</span>&nbsp; {T(ev['name'])}"), row, 0)
            for col, key in enumerate(("enabled", "pre", "at", "map"), 1):
                cb = QCheckBox()
                cb.setChecked(it.get(key, False))
                if key == "map" and not ev.get("map"):
                    cb.setEnabled(False)
                    cb.setChecked(False)
                cb.toggled.connect(lambda on, e=ev, k=key: self.set_item(e, k, on))
                g.addWidget(cb, row, col, alignment=Qt.AlignCenter)
            nl = QLabel("")
            self.next_labels[ev["id"]] = nl
            g.addWidget(nl, row, 5)
            bt = QPushButton("Testar")
            bt.clicked.connect(lambda _=False, e=ev: self.test(e))
            g.addWidget(bt, row, 6)
        lay.addWidget(box)

        box2 = QGroupBox("Som e posição")
        f2 = QFormLayout(box2)
        f2.addRow("Som:", sound_row_cls("events"))
        dur = QHBoxLayout()
        for label, key, lo, hi in (("Aviso fica na tela:", "toast_seconds", 2, 60),
                                   ("Mini-mapa fica na tela:", "map_seconds", 3, 300)):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setSuffix(" s")
            sp.setValue(c.get(key, 6))
            sp.valueChanged.connect(lambda v, k=key: self.set_cfg(k, v))
            dur.addWidget(QLabel(label))
            dur.addWidget(sp)
            dur.addSpacing(16)
        dur.addStretch()
        f2.addRow(dur)
        row = QHBoxLayout()
        b1 = QPushButton("Posicionar aviso")
        b1.clicked.connect(lambda: self.s.toast.push("event", T("Posicionar"), T("Arraste para posicionar"), T("Some em 10 s")))
        b2 = QPushButton("Posicionar mini-mapa")
        b2.clicked.connect(lambda: self.s.show_map(self.s.data["events"][1]))
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        f2.addRow("", row)
        f2.addRow(QLabel("Duplo clique fecha o aviso ou o mini-mapa antes do tempo."))
        lay.addWidget(box2)

        note = QLabel("Se algum horário estiver diferente no seu servidor, use o ajuste de relógio na aba Shugo. "
                      "Os chefes de campo comuns não têm horário fixo — renascem um tempo depois de mortos — "
                      "por isso não entram aqui.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a8f99;")
        lay.addWidget(note)
        lay.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_next)
        self.timer.start(15000)
        self.refresh_next()

    def set_cfg(self, k, v):
        ev_cfg()[k] = v
        save()

    def region_changed(self, _i):
        self.set_cfg("region", self.region.currentData())
        self.refresh_next()

    def set_item(self, ev, key, on):
        item_cfg(ev)[key] = on
        save()
        self.refresh_next()

    def refresh_next(self):
        now = datetime.now().astimezone()
        for ev in self.s.data["events"]:
            t = self.s.next_time(ev)
            if not t:
                continue
            lt = t.astimezone()
            day = T("hoje") if lt.date() == now.date() else (T("amanhã") if lt.date() == (now + timedelta(days=1)).date()
                                                             else f"{lt:%d/%m}")
            self.next_labels[ev["id"]].setText(f"{day} {lt:%H:%M}")

    def test(self, ev):
        t = self.s.next_time(ev) or datetime.now(timezone.utc)
        self.s.fire(ev, t, "pre", test=True)
        if not item_cfg(ev).get("map") and ev.get("map"):
            self.s.show_map(ev)
