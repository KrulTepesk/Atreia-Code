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
        self._bg = QColor(12, 11, 9)        # céu do Abismo
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
        pen = QColor(self._accent) if self._accent.alpha() else (QColor(168, 116, 42, 55) if self._locked else QColor(224, 176, 79, 110))
        p.setPen(pen)
        from PySide6.QtCore import QRectF
        from theme import chamfer_path
        path = chamfer_path(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12)
        p.drawPath(path)
        # traço de éter no canto de cima (mesma assinatura dos cartões do painel)
        if not self._accent.alpha():
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPen
            p.setPen(QPen(QColor(224, 176, 79, 200), 1.4))
            p.drawLine(QPointF(1, 13), QPointF(13, 1))
