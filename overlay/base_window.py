"""Janela de overlay: sem borda, transparente, sempre por cima, arrastável e com posição salva."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from config import cfg, save


class OverlayWindow(QWidget):
    def __init__(self, key, default_offset=QPoint(40, 40)):
        super().__init__(None)
        self.key = key
        self._drag = None
        self._locked = False
        self._bg = QColor(8, 8, 9)        # céu do Abismo
        self._accent = QColor(0, 0, 0, 0)
        self.default_offset = default_offset
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(cfg[key].get("opacity", 0.85))

    # ---------- posição / monitores ----------
    def restore_position(self):
        pos = cfg[self.key].get("pos")
        if pos:
            p = QPoint(*pos)
            if any(s.geometry().contains(p) for s in QGuiApplication.screens()):
                self.move(p)
                return
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.topLeft() + self.default_offset)

    def move_to_screen(self, screen):
        geo = screen.availableGeometry()
        self.move(geo.topLeft() + self.default_offset)
        self._save_pos()
        if hasattr(self, "preview_position"):
            self.preview_position()

    def _save_pos(self):
        cfg[self.key]["pos"] = [self.x(), self.y()]
        save()

    # ---------- travar (clique atravessa a janela) ----------
    def set_locked(self, locked):
        self._locked = locked
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, locked)
        if visible:
            self.show()
        self.update()

    # ---------- arrastar ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._locked:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self._save_pos()

    # ---------- fundo arredondado ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(self._bg)
        bg.setAlpha(215)
        p.setBrush(bg)
        pen = QColor(self._accent) if self._accent.alpha() else (QColor(255, 255, 255, 18) if self._locked else QColor(217, 164, 65, 120))
        p.setPen(pen)
        from PySide6.QtCore import QRectF
        from theme import draw_bevel, panel_path
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.drawPath(panel_path(r, 10))
        if not self._accent.alpha():
            draw_bevel(p, r, 10, 26)
