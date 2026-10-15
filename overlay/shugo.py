"""Aviso do Festival Shugo (toda hora cheia, horário do servidor).

Não fica nada fixo na tela: um aviso aparece X minutos antes (padrão 5 e 1),
toca o som e some sozinho depois de alguns segundos.
"""
import math
import os
import shutil
from datetime import datetime, timedelta

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap

import alert_style
import sounds_player
from base_window import OverlayWindow
from i18n import T
from config import APP_DIR, cfg, resolve, save

DEFAULT_ICON = "shugo_icon.png"
SHOW_SECONDS = 10


class ShugoWidget(OverlayWindow):
    W = 360

    def __init__(self):
        super().__init__("shugo", QPoint(40, 120))
        c = cfg["shugo"]
        c.setdefault("alerts", [5, 1])
        c.setdefault("icon", DEFAULT_ICON)
        self._fired = set()
        self._hide_at = None
        self._shown_at = None
        self.title = T("Festival Shugo")
        self.msg = ""
        self.sub = ""
        self.target = None          # hora do festival (contagem ao vivo)
        self.urgent = False
        self.pix = None
        self.setFixedSize(self.W, 84)
        self.load_icon()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)

    # ------------------------------------------------------------------ ícone
    def load_icon(self):
        pm = QPixmap(resolve(cfg["shugo"].get("icon") or DEFAULT_ICON))
        if pm.isNull():
            pm = QPixmap(resolve(DEFAULT_ICON))
        self.pix = pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.update()

    def set_icon_file(self, path):
        os.makedirs(APP_DIR, exist_ok=True)
        dest = os.path.join(APP_DIR, "shugo_icone" + os.path.splitext(path)[1].lower())
        if QPixmap(path).isNull():
            return False                       # não é imagem: não copia nem troca o ícone
        if os.path.abspath(path) != os.path.abspath(dest):   # escolher o próprio ícone salvo dava erro
            try:
                shutil.copyfile(path, dest)
            except OSError:
                return False
        cfg["shugo"]["icon"] = dest
        save()
        self.load_icon()
        return True

    def reset_icon(self):
        cfg["shugo"]["icon"] = DEFAULT_ICON
        save()
        self.load_icon()

    # ------------------------------------------------------------------ relógio
    def server_now(self):
        return datetime.now() + timedelta(minutes=cfg["shugo"].get("offset_minutes", 0))

    def tick(self):
        if not cfg["shugo"].get("enabled", True):     # aviso desligado na aba Shugo
            if self.isVisible() and self._hide_at is not None and datetime.now() >= self._hide_at:
                self._hide_at = None
                self.hide()
            return
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
            self.timer.setInterval(500)
        if self.isVisible():
            self.update()

    def alert(self, minutes=5, nxt=None, play_sound=True):
        nxt = nxt or (self.server_now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        self.target = nxt
        self.urgent = minutes <= 1
        if minutes <= 1:
            self.msg = T("Começa em 1 minuto!")
            self.sub = T("Lobby aberto — entre agora")
        else:
            self.msg = T("Começa em {n} minutos").format(n=minutes)
            self.sub = T("Lobby abre 3 min antes") if minutes > 3 else T("Lobby aberto — entre agora")
        if play_sound:
            c = cfg["shugo"]
            sounds_player.play(c.get("sound"), c.get("volume", 80))
        self.show_for(cfg["shugo"].get("show_seconds", 6))

    def show_for(self, seconds):
        self._shown_at = datetime.now()
        self._hide_at = self._shown_at + timedelta(seconds=seconds)
        self.setFixedHeight(alert_style.alert_height(self.W, self.sub))
        was = self.isVisible()
        self.show()
        self.raise_()
        if not was:
            alert_style.fade_in(self, cfg["shugo"].get("opacity", 0.85))
        self.timer.setInterval(100)            # contagem e o halo andando lisos enquanto aparece
        self.update()

    def preview_position(self):
        """Mostra o aviso por 15 s para arrastar até o lugar desejado (com os overlays destravados)."""
        self.target = None
        self.urgent = False
        self.msg = T("Arraste para posicionar")
        self.sub = T("Some sozinho em 15 s")
        self.show_for(15)

    def mouseDoubleClickEvent(self, e):
        self._hide_at = None
        self.hide()
        self.timer.setInterval(500)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        now = datetime.now()
        life = None
        if self._hide_at and self._shown_at:
            total = (self._hide_at - self._shown_at).total_seconds() or 1
            life = (self._hide_at - now).total_seconds() / total
        left = (self.target - self.server_now()).total_seconds() if self.target else None
        pulse = (0.5 + 0.5 * math.sin(now.timestamp() * 5)) if self.urgent else 0.0
        alert_style.draw_alert(p, self.width(), self.height(), "shugo", self.title, self.msg, self.sub,
                               left=left, life=life, locked=self._locked, pixmap=self.pix, pulse=pulse)
        p.end()
