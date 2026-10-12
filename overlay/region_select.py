"""Seleção de uma área da tela (arrastar com o mouse), usada para marcar onde fica o minimapa."""
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from i18n import T


class RegionSelector(QWidget):
    """Tela escura por cima de um monitor; arraste para marcar uma área (usado para o minimapa)."""
    chosen = Signal(list)

    def __init__(self, screen):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(screen.geometry())
        self._a = self._b = None
        self.hint_text = "Arraste em volta da área onde aparece a mensagem  (Esc cancela)"
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                   T(self.hint_text))
        if self._a and self._b:
            r = QRect(self._a, self._b).normalized()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(r, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor("#ff5a6a"), 2))
            p.drawRect(r)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    def mousePressEvent(self, e):
        self._a = self._b = e.position().toPoint()

    def mouseMoveEvent(self, e):
        self._b = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e):
        if self._a is None:                      # soltou sem ter apertado aqui dentro
            return
        r = QRect(self._a, e.position().toPoint()).normalized()
        self.close()
        if r.width() > 20 and r.height() > 10:
            g = self.geometry()
            self.chosen.emit([g.x() + r.x(), g.y() + r.y(), r.width(), r.height()])
