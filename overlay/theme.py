"""Visual do app: preto com detalhes em ouro (o "éter" virou dourado, como o símbolo do Meta Overlay).

Tokens de cor, folha de estilo (QSS), ícones desenhados, menu lateral (NavTabs) e polish()
que deixa os textos de ajuda num tom mais suave.
"""
import ctypes
import math
import os

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QStyleFactory,
                               QVBoxLayout, QWidget)

from config import BASE_DIR

# ---------------------------------------------------------------- cores
INK = "#0a0908"        # fundo da janela
SKY = "#0d0c0a"        # menu lateral
CARD = "#131210"       # cartões
FIELD = "#1a1815"      # campos / botões
FIELD_HI = "#23201b"   # hover
LINE = "#2b2720"       # bordas
TEXT = "#f2ede3"
MUTED = "#9b9282"
FAINT = "#5f584c"
AETHER = "#e0b04f"     # ouro (destaque)
AETHER2 = "#a8742a"    # bronze (destaque 2)
GOLD = "#f2c14e"       # alertas (Shugo, eventos)

# nomes antigos (outros módulos ainda importam)
BG, PANEL, PANEL2, BORDER, ACCENT, ACCENT_DARK = INK, CARD, FIELD, LINE, AETHER, "#a87b26"

UI = os.path.join(BASE_DIR, "ui").replace("\\", "/")
FONT = "'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif"
FONT_DISPLAY = "Marcellus"     # fonte livre (OFL), vem junto em fonts/

QSS = f"""
* {{ font-family: {FONT}; font-size: 10pt; color: {TEXT}; }}
QWidget#Page, QStackedWidget, QScrollArea > QWidget > QWidget {{ background: {INK}; }}
QToolTip {{ background: {FIELD}; color: {TEXT}; border: 1px solid {LINE}; padding: 5px 8px; }}

/* cartões: moldura com cantos cortados é pintada pelo CardFrame (QSS não faz chanfro) */
QGroupBox {{
    background: transparent; border: none;
    margin-top: 8px; padding: 46px 20px 16px 20px;
}}
QGroupBox::title {{ color: transparent; subcontrol-origin: padding; left: 0; top: 0; }}
QLabel {{ background: transparent; }}
QLabel[hint="true"] {{ color: {MUTED}; }}
QLabel:disabled {{ color: {FAINT}; }}

/* botões: "encaixes" escuros e retos, como os da interface do jogo */
QPushButton {{
    background: #171512; border: 1px solid #3a3328; border-radius: 2px;
    padding: 7px 16px; color: {TEXT}; min-height: 18px;
}}
QPushButton:hover {{ border-color: #8f7135; background: #1f1c17; }}
QPushButton:pressed {{ background: #0c0b09; }}
QPushButton:focus {{ border-color: {AETHER}; }}
QPushButton:checked, QPushButton[primary="true"] {{
    background: #2a1f0b; border: 1px solid {AETHER}; color: #fff0cc; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: #3a2b10; border-color: #f4d58c; }}
QPushButton:disabled {{ color: {FAINT}; border-color: #1e1b17; background: #0f0e0c; }}

/* campos */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #0f0e0c; border: 1px solid #2e2922; border-radius: 2px;
    padding: 6px 10px; min-height: 18px;
    selection-background-color: {AETHER}; selection-color: {INK};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #5c4b2b; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {AETHER}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; border-color: #1e1b17; }}
QSpinBox, QDoubleSpinBox {{ max-width: 170px; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url({UI}/down.svg); width: 10px; height: 6px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({UI}/up.svg); width: 9px; height: 5px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({UI}/down.svg); width: 9px; height: 5px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent;
}}
QComboBox QAbstractItemView {{
    background: #11100e; border: 1px solid {LINE};
    selection-background-color: #221d14; selection-color: {AETHER}; outline: none; padding: 4px;
}}

/* interruptores: encaixe angular com losango */
QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 38px; height: 20px; border: none; image: url({UI}/switch_off.svg); }}
QCheckBox::indicator:checked {{ image: url({UI}/switch_on.svg); }}
QCheckBox::indicator:disabled {{ image: url({UI}/switch_off_dis.svg); }}
QCheckBox::indicator:checked:disabled {{ image: url({UI}/switch_on_dis.svg); }}
QCheckBox:disabled {{ color: {FAINT}; }}

QSlider::groove:horizontal {{ height: 2px; background: {LINE}; }}
QSlider::sub-page:horizontal {{ background: {AETHER}; }}
QSlider::handle:horizontal {{
    image: url({UI}/diamond.svg); width: 16px; height: 16px; margin: -7px 0; background: transparent; border: none;
}}

QListWidget {{ background: #0f0e0c; border: 1px solid #2e2922; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 6px 8px; }}
QListWidget::item:hover {{ background: #191612; }}
QListWidget::item:selected {{ background: #2a1f0b; color: #fff0cc; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 4px 1px; }}
QScrollBar::handle:vertical {{ background: #3b3428; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {AETHER}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QMenu {{ background: #11100e; border: 1px solid {LINE}; padding: 5px; }}
QMenu::item {{ padding: 7px 20px; }}
QMenu::item:selected {{ background: #221d14; color: {AETHER}; }}
QMessageBox, QDialog {{ background: {INK}; }}

/* menu lateral: sem "pílulas"; o item aberto ganha um losango de éter */
#NavBar QPushButton {{
    text-align: left; padding: 10px 14px 10px 24px; border: none; border-radius: 0;
    background: transparent; color: {MUTED}; font-size: 10.5pt;
}}
#NavBar QPushButton:hover {{ color: {TEXT}; background: transparent; }}
#NavBar QPushButton:checked {{ color: {TEXT}; background: transparent; border: none; font-weight: 600; }}
#NavBar QPushButton#LockPill {{
    border: 1px solid {LINE}; background: rgba(10, 9, 8, 0.7); padding: 9px 12px; font-size: 9.5pt; border-radius: 2px;
}}
#NavBar QPushButton#LockPill:checked {{ border-color: {AETHER}; color: #fff0cc; background: rgba(42, 31, 11, 0.8); }}
#Brand {{ color: {TEXT}; font-family: '{FONT_DISPLAY}'; font-size: 15pt; }}
#BrandSub {{ color: {MUTED}; font-size: 8.5pt; }}
#PageTitle {{ font-family: '{FONT_DISPLAY}'; font-size: 24pt; color: {TEXT}; }}
#PageSub {{ color: {MUTED}; font-size: 10pt; padding-bottom: 8px; }}
"""


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    folder = os.path.join(BASE_DIR, "fonts")
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(folder, f))


def display_font(pt):
    f = QFont(FONT_DISPLAY)
    f.setPointSizeF(pt)
    return f


def chamfer_path(r, cut=10, corners=("tl", "br")):
    """Retângulo com cantos cortados (estilo janela de jogo). r: QRectF."""
    c = {k: (cut if k in corners else 0) for k in ("tl", "tr", "br", "bl")}
    path = QPainterPath(QPointF(r.left() + c["tl"], r.top()))
    path.lineTo(r.right() - c["tr"], r.top())
    path.lineTo(r.right(), r.top() + c["tr"])
    path.lineTo(r.right(), r.bottom() - c["br"])
    path.lineTo(r.right() - c["br"], r.bottom())
    path.lineTo(r.left() + c["bl"], r.bottom())
    path.lineTo(r.left(), r.bottom() - c["bl"])
    path.lineTo(r.left(), r.top() + c["tl"])
    path.closeSubpath()
    return path


def draw_diamond(p, center, size, fill, outline=None):
    pts = [QPointF(center.x(), center.y() - size), QPointF(center.x() + size, center.y()),
           QPointF(center.x(), center.y() + size), QPointF(center.x() - size, center.y())]
    from PySide6.QtGui import QPolygonF
    p.setBrush(QColor(fill) if fill else Qt.NoBrush)
    p.setPen(QPen(QColor(outline), 1.2) if outline else Qt.NoPen)
    p.drawPolygon(QPolygonF(pts))


class CardFrame(QObject):
    """Pinta os cartões (QGroupBox): cantos cortados, losango + título na fonte de destaque e um fio até a borda."""

    def eventFilter(self, w, e):
        if e.type() == QEvent.Paint and isinstance(w, QGroupBox):
            p = QPainter(w)
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(w.rect()).adjusted(0.5, 8.5, -0.5, -0.5)
            path = chamfer_path(r, 12)
            p.fillPath(path, QColor(CARD) if w.isEnabled() else QColor("#0f0e0c"))
            p.setPen(QPen(QColor(LINE), 1))
            p.drawPath(path)
            # canto de cima com um traço de éter (marca do "encaixe")
            p.setPen(QPen(QColor(AETHER if w.isEnabled() else LINE), 1.4))
            p.drawLine(QPointF(r.left(), r.top() + 12), QPointF(r.left() + 12, r.top()))
            title = w.title()
            if title:
                y = r.top() + 22
                draw_diamond(p, QPointF(r.left() + 22, y), 4, AETHER if w.isEnabled() else FAINT)
                f = display_font(13)
                p.setFont(f)
                p.setPen(QColor(TEXT if w.isEnabled() else FAINT))
                fm = p.fontMetrics()
                p.drawText(QPointF(r.left() + 34, y + fm.ascent() / 2 - 2), title)
                x2 = r.left() + 34 + fm.horizontalAdvance(title) + 14
                if x2 < r.right() - 24:
                    p.setPen(QPen(QColor(LINE), 1))
                    p.drawLine(QPointF(x2, y), QPointF(r.right() - 20, y))
            p.end()
        return False


_card_frame = None


def apply(app):
    global _card_frame
    load_fonts()
    _card_frame = CardFrame(app)
    app.installEventFilter(_card_frame)      # todos os cartões do app, inclusive os criados depois
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    for role, col in ((QPalette.Window, INK), (QPalette.Base, FIELD), (QPalette.AlternateBase, CARD),
                      (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.Button, FIELD),
                      (QPalette.ButtonText, TEXT), (QPalette.Highlight, AETHER2),
                      (QPalette.HighlightedText, INK), (QPalette.ToolTipBase, FIELD),
                      (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, FAINT), (QPalette.Link, AETHER)):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


OLD_GREYS = ("#9b9282", "#9b9282", "#8a8272", "#d4ccbb")


def polish(root):
    """Textos de ajuda (rótulos com quebra de linha) ficam no tom suave; cinzas antigos viram o lilás do tema;
    o dourado antigo de destaque vira o ciano do éter."""
    from PySide6.QtWidgets import QGroupBox as _G, QLabel as _L
    for w in [root] + root.findChildren(QWidget):
        ss = w.styleSheet()
        if ss:
            new = ss
            for g in OLD_GREYS:
                new = new.replace(g, MUTED)
            if new != ss:
                w.setStyleSheet(new)
        txt = w.text() if isinstance(w, _L) else ""
        is_help = isinstance(w, _L) and not ss and not w.objectName() and not w.pixmap() and (
            w.wordWrap() or (len(txt) > 38 and not txt.rstrip().endswith(":") and "<b>" not in txt))
        if is_help:
            w.setProperty("hint", True)
            w.style().unpolish(w)
            w.style().polish(w)


def primary(button):
    """Marca um botão como ação principal (gradiente do éter)."""
    button.setProperty("primary", True)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def dark_titlebar(widget):
    """Barra de título escura no Windows 10/11 (e cantos arredondados no 11)."""
    if os.name != "nt":
        return
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (novo / antigo)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
        # cor da barra = céu do Abismo (Windows 11; no 10 é ignorado)
        col = ctypes.c_int(0x000A0C0D)   # COLORREF 0x00BBGGRR de #0d0c0a
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(col), ctypes.sizeof(col))
    except Exception:
        pass


# ---------------------------------------------------------------- ícones desenhados
def _icon_painter(size=40):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def draw_glyph(p, name, r, color):
    """Ícones de linha simples (sem imagens de terceiros)."""
    p.save()
    pen = QPen(QColor(color), max(1.5, r.width() / 13), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    P = lambda fx, fy: QPointF(x + fx * w, y + fy * h)
    if name == "general":           # três controles deslizantes
        for fy, fx in ((0.25, 0.65), (0.5, 0.32), (0.75, 0.58)):
            p.drawLine(P(0.12, fy), P(0.88, fy))
            p.setBrush(QColor(INK))
            p.drawEllipse(P(fx, fy), w * 0.1, w * 0.1)
            p.setBrush(Qt.NoBrush)
    elif name == "shugo":           # sino
        path = QPainterPath(P(0.2, 0.72))
        path.cubicTo(P(0.3, 0.6), P(0.24, 0.2), P(0.5, 0.18))
        path.cubicTo(P(0.76, 0.2), P(0.7, 0.6), P(0.8, 0.72))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(0.5, 0.1), P(0.5, 0.18))
        p.drawArc(QRectF(P(0.4, 0.74), P(0.6, 0.9)), 180 * 16, 180 * 16)
    elif name == "rifts":           # fenda / portal em espiral
        p.drawEllipse(QRectF(P(0.14, 0.14), P(0.86, 0.86)))
        path = QPainterPath(P(0.5, 0.5))
        for k in range(1, 40):
            a = k * 0.32
            rad = 0.012 * k
            path.lineTo(P(0.5 + math.cos(a) * rad, 0.5 + math.sin(a) * rad))
        p.drawPath(path)
    elif name == "pvp":             # espadas cruzadas
        p.drawLine(P(0.18, 0.18), P(0.78, 0.78))
        p.drawLine(P(0.82, 0.18), P(0.22, 0.78))
        p.drawLine(P(0.62, 0.86), P(0.86, 0.62))
        p.drawLine(P(0.38, 0.86), P(0.14, 0.62))
    elif name == "map":             # mapa dobrado
        path = QPainterPath(P(0.12, 0.24))
        for pt in ((0.37, 0.14), (0.63, 0.24), (0.88, 0.14), (0.88, 0.76), (0.63, 0.86), (0.37, 0.76),
                   (0.12, 0.86)):
            path.lineTo(P(*pt))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(0.37, 0.14), P(0.37, 0.76))
        p.drawLine(P(0.63, 0.24), P(0.63, 0.86))
    elif name == "farm":            # pata
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        for fx, fy, rr in ((0.24, 0.42, 0.09), (0.4, 0.24, 0.09), (0.6, 0.24, 0.09), (0.76, 0.42, 0.09)):
            p.drawEllipse(P(fx, fy), w * rr, h * rr * 1.15)
        p.drawEllipse(QRectF(P(0.3, 0.5), P(0.7, 0.84)))
    elif name == "dps":             # barras subindo
        for k, top in enumerate((0.55, 0.36, 0.16)):
            fx = 0.2 + k * 0.25
            p.drawLine(P(fx, 0.84), P(fx, top))
        p.drawLine(P(0.1, 0.9), P(0.9, 0.9))
    elif name == "shield":          # escudo (cercos / invasões)
        path = QPainterPath(P(0.2, 0.18))
        path.lineTo(P(0.8, 0.18))
        path.lineTo(P(0.8, 0.5))
        path.quadTo(P(0.75, 0.78), P(0.5, 0.9))
        path.quadTo(P(0.25, 0.78), P(0.2, 0.5))
        path.closeSubpath()
        p.drawPath(path)
    elif name == "crown":           # coroa (chefes de campo)
        path = QPainterPath(P(0.14, 0.78))
        for fx, fy in ((0.14, 0.3), (0.34, 0.52), (0.5, 0.2), (0.66, 0.52), (0.86, 0.3), (0.86, 0.78)):
            path.lineTo(P(fx, fy))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(0.2, 0.66), P(0.8, 0.66))
    elif name == "lock":            # cadeado
        p.drawRoundedRect(QRectF(P(0.2, 0.45), P(0.8, 0.88)), w * 0.08, w * 0.08)
        p.drawArc(QRectF(P(0.32, 0.14), P(0.68, 0.6)), 0, 180 * 16)
        p.drawLine(P(0.32, 0.37), P(0.32, 0.45))
        p.drawLine(P(0.68, 0.37), P(0.68, 0.45))
    elif name == "unlock":
        p.drawRoundedRect(QRectF(P(0.2, 0.45), P(0.8, 0.88)), w * 0.08, w * 0.08)
        p.drawArc(QRectF(P(0.32, 0.1), P(0.68, 0.56)), 20 * 16, 160 * 16)
        p.drawLine(P(0.32, 0.33), P(0.32, 0.45))
    p.restore()


def glyph_icon(name):
    """QIcon com dois estados: normal (lilás) e selecionado (éter)."""
    icon = QIcon()
    for mode_color, state in ((MUTED, QIcon.Off), (AETHER, QIcon.On)):
        pm, p = _icon_painter(40)
        draw_glyph(p, name, QRectF(6, 6, 28, 28), mode_color)
        p.end()
        icon.addPixmap(pm, QIcon.Normal, state)
        icon.addPixmap(pm, QIcon.Active, state)
    return icon


def draw_wings(p, r):
    """Marca do app: um par de asas estilizado em gradiente do éter (desenho próprio)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(AETHER))
    g.setColorAt(1, QColor(AETHER2))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    cx, cy, w, h = r.center().x(), r.center().y(), r.width(), r.height()
    for side in (-1, 1):
        for k, (reach, drop, thick) in enumerate(((0.48, 0.05, 0.16), (0.40, 0.22, 0.13), (0.30, 0.38, 0.11))):
            path = QPainterPath(QPointF(cx + side * w * 0.05, cy - h * 0.12 + k * h * 0.12))
            tip = QPointF(cx + side * w * reach, cy - h * 0.42 + drop * h)
            path.quadTo(QPointF(cx + side * w * (reach * 0.55), cy - h * 0.45 + k * h * 0.14), tip)
            path.quadTo(QPointF(cx + side * w * (reach * 0.6), cy - h * 0.2 + k * h * 0.16 + thick * h),
                        QPointF(cx + side * w * 0.05, cy - h * 0.12 + k * h * 0.12 + thick * h))
            path.closeSubpath()
            p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy + h * 0.2), w * 0.06, w * 0.06)
    p.restore()


def app_icon_pixmap(size=64):
    pm, p = _icon_painter(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(SKY))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    draw_wings(p, QRectF(size * 0.1, size * 0.18, size * 0.8, size * 0.7))
    p.end()
    return pm


# ---------------------------------------------------------------- menu lateral
class Brand(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(48, 48)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        logo = os.path.join(BASE_DIR, "logo.png")
        pm = QPixmap(logo) if os.path.exists(logo) else QPixmap()
        if not pm.isNull():
            p.drawPixmap(self.rect(), pm.scaled(self.size() * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            draw_wings(p, QRectF(2, 4, 36, 32))
        p.end()


class NavBar(QFrame):
    """Fundo do menu pintado como o céu do Abismo: brilhos suaves de éter e algumas estrelas."""
    # só na parte vazia de baixo do menu (não passam por cima dos textos)
    STARS = [(0.12, 0.52), (0.8, 0.5), (0.45, 0.58), (0.68, 0.64), (0.22, 0.68), (0.88, 0.72), (0.36, 0.76),
             (0.6, 0.8), (0.14, 0.86), (0.78, 0.88), (0.5, 0.9), (0.3, 0.62)]

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor(SKY))
        for cx, cy, rad, col, a in ((0.1, 0.0, 1.1, AETHER2, 34), (1.0, 1.0, 1.0, AETHER, 20)):
            g = QRadialGradient(QPointF(r.width() * cx, r.height() * cy), r.width() * rad)
            c = QColor(col)
            c.setAlpha(a)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(r, g)
        p.setPen(Qt.NoPen)
        for k, (sx, sy) in enumerate(self.STARS):
            c = QColor(TEXT)
            c.setAlpha(60 + (k * 37) % 90)
            p.setBrush(c)
            rad = 0.8 + (k % 3) * 0.35
            p.drawEllipse(QPointF(r.width() * sx, r.height() * sy), rad, rad)
        p.setPen(QColor(LINE))
        p.drawLine(r.topRight(), r.bottomRight())
        p.end()


class NavButton(QPushButton):
    """Item do menu: ícone + texto; o aberto ganha um losango de éter e um fio de luz embaixo."""

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            cy = self.height() / 2
            draw_diamond(p, QPointF(9, cy), 4, AETHER)
            g = QLinearGradient(24, 0, self.width(), 0)
            c = QColor(AETHER)
            c.setAlpha(150)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.setPen(QPen(g, 1))
            p.drawLine(QPointF(24, self.height() - 5), QPointF(self.width() - 10, self.height() - 5))
            p.end()


class NavTabs(QWidget):
    """Menu lateral + páginas (substitui as abas); mesma interface básica do QTabWidget."""
    currentChanged = Signal(int)

    def __init__(self, brand="Meta Overlay", sub="Ferramentas para Aion 2"):
        super().__init__()
        from i18n import T
        self.T = T
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.bar = NavBar()
        self.bar.setObjectName("NavBar")
        self.bar.setFixedWidth(232)
        self.bl = QVBoxLayout(self.bar)
        self.bl.setContentsMargins(12, 18, 12, 14)
        self.bl.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(Brand())
        txt = QVBoxLayout()
        txt.setSpacing(0)
        b = QLabel(brand)
        b.setObjectName("Brand")
        s = QLabel(T(sub))
        s.setObjectName("BrandSub")
        txt.addWidget(b)
        txt.addWidget(s)
        head.addLayout(txt, 1)
        hw = QWidget()
        hw.setLayout(head)
        head.setContentsMargins(4, 0, 0, 18)
        self.bl.addWidget(hw)
        self.bl.addStretch()
        self.footer = QVBoxLayout()
        self.bl.addLayout(self.footer)
        self.stack = QStackedWidget()
        self.pages = []      # (wrapper, widget, button)
        lay.addWidget(self.bar)
        lay.addWidget(self.stack, 1)

    @staticmethod
    def _split(title):
        """Aceita o formato antigo '⚙   Geral' (tira o emoji)."""
        parts = title.split(None, 1)
        if len(parts) == 2 and not parts[0][0].isalnum():
            return parts[1].strip()
        return title

    def _wrap(self, widget, title, sub):
        wrap = QWidget()
        wrap.setObjectName("Page")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(30, 24, 30, 20)
        wl.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        wl.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setObjectName("PageSub")
            s.setWordWrap(True)
            wl.addWidget(s)
        wl.addSpacing(8)
        wl.addWidget(widget, 1)
        return wrap

    def insertTab(self, index, widget, title, icon=None, sub=None):
        index = min(index, len(self.pages))
        title = self.T(self._split(title))
        wrap = self._wrap(widget, title, self.T(sub) if sub else None)
        btn = NavButton(("  " if icon else "") + title)
        if icon:
            btn.setIcon(glyph_icon(icon))
            btn.setIconSize(QSize(20, 20))
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        self.pages.insert(index, (wrap, widget, btn))
        self.stack.insertWidget(index, wrap)
        self.bl.insertWidget(1 + index, btn)
        btn.clicked.connect(lambda: self.setCurrentWidget(widget))
        if len(self.pages) == 1:
            self.setCurrentIndex(0)
        return index

    def addTab(self, widget, title, icon=None, sub=None):
        return self.insertTab(len(self.pages), widget, title, icon, sub)

    def add_footer(self, widget):
        self.footer.addWidget(widget)

    def setCurrentIndex(self, i):
        if not 0 <= i < len(self.pages):
            return
        for j, (wrap, w, btn) in enumerate(self.pages):
            btn.setChecked(j == i)
        self.stack.setCurrentWidget(self.pages[i][0])
        self.currentChanged.emit(i)

    def setCurrentWidget(self, widget):
        for i, (wrap, w, btn) in enumerate(self.pages):
            if w is widget or wrap is widget:
                self.setCurrentIndex(i)
                return

    def currentIndex(self):
        return self.stack.currentIndex()
