"""Aviso do Festival Shugo (toda hora cheia, horário do servidor).

Não fica nada fixo na tela: um aviso aparece X minutos antes (padrão 5 e 1),
toca o som e some sozinho depois de alguns segundos.
"""
import os
import shutil
from datetime import datetime, timedelta

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

import sounds_player
from base_window import OverlayWindow
from i18n import T
from config import APP_DIR, cfg, resolve, save

DEFAULT_ICON = "shugo_icon.png"
SHOW_SECONDS = 10


class ShugoWidget(OverlayWindow):
    def __init__(self):
        super().__init__("shugo", QPoint(40, 120))
        c = cfg["shugo"]
        c.setdefault("alerts", [5, 1])
        c.setdefault("icon", DEFAULT_ICON)
        self._fired = set()
        self._hide_at = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 16, 10)
        lay.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedSize(56, 56)
        lay.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel(T("FESTIVAL SHUGO"))
        self.title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.title.setStyleSheet("color:#f5c542; letter-spacing:1px;")
        self.msg = QLabel("")
        self.msg.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.msg.setStyleSheet("color:white;")
        self.sub = QLabel("")
        self.sub.setFont(QFont("Segoe UI", 9))
        self.sub.setStyleSheet("color:#b3aa98;")
        for w in (self.title, self.msg, self.sub):
            col.addWidget(w)
        lay.addLayout(col)
        self.setFixedSize(330, 82)
        self.load_icon()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)

    # ------------------------------------------------------------------ ícone
    def load_icon(self):
        pm = QPixmap(resolve(cfg["shugo"].get("icon") or DEFAULT_ICON))
        if pm.isNull():
            pm = QPixmap(resolve(DEFAULT_ICON))
        self.icon.setPixmap(pm.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def set_icon_file(self, path):
        os.makedirs(APP_DIR, exist_ok=True)
        dest = os.path.join(APP_DIR, "shugo_icone" + os.path.splitext(path)[1].lower())
        shutil.copyfile(path, dest)
        cfg["shugo"]["icon"] = dest
        save()
        self.load_icon()

    def reset_icon(self):
        cfg["shugo"]["icon"] = DEFAULT_ICON
        save()
        self.load_icon()

    # ------------------------------------------------------------------ relógio
    def server_now(self):
        return datetime.now() + timedelta(minutes=cfg["shugo"].get("offset_minutes", 0))

    def tick(self):
        now = self.server_now()
        nxt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        left = (nxt - now).total_seconds()
        for minutes in cfg["shugo"].get("alerts", [5, 1]):
            if not minutes:
                continue
            key = (nxt.strftime("%Y%m%d%H"), minutes)
            # dispara quando entra na janela do aviso (até 20 s de tolerância, p/ PC que estava suspenso)
            if minutes * 60 - 20 <= left <= minutes * 60 and key not in self._fired:
                self._fired.add(key)
                self.alert(minutes, nxt)
        if self._hide_at and datetime.now() >= self._hide_at:
            self._hide_at = None
            self.hide()
        if self.isVisible():
            on = int(datetime.now().timestamp() * 2) % 2 == 0
            self._accent = QColor("#f5c542") if on else QColor(245, 197, 66, 90)
            self.update()

    def alert(self, minutes=5, nxt=None, play_sound=True):
        nxt = nxt or (self.server_now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        if minutes <= 1:
            self.msg.setText(T("Começa em 1 minuto!"))
            self.sub.setText(T("Lobby aberto — entre agora"))
        else:
            self.msg.setText(T("Começa em {n} minutos").format(n=minutes))
            self.sub.setText(T("Lobby abre 3 min antes") if minutes > 3 else T("Lobby aberto — entre agora"))
        if play_sound:
            c = cfg["shugo"]
            sounds_player.play(c.get("sound"), c.get("volume", 80))
        self.show_for(cfg["shugo"].get("show_seconds", 6))

    def show_for(self, seconds):
        self._hide_at = datetime.now() + timedelta(seconds=seconds)
        self.show()
        self.raise_()

    def preview_position(self):
        """Mostra o aviso por 15 s para arrastar até o lugar desejado (com os overlays destravados)."""
        self.msg.setText(T("Arraste para posicionar"))
        self.sub.setText(T("Some sozinho em 15 s"))
        self.show_for(15)

    def mouseDoubleClickEvent(self, e):
        self._hide_at = None
        self.hide()
