"""Visual do app: preto em camadas + o ouro metálico do símbolo do Meta Overlay.

Tokens de cor, folha de estilo (QSS), ícones desenhados, menu lateral (NavTabs) e polish()
que deixa os textos de ajuda num tom mais suave.
"""
import ctypes
import math
import os

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QStyleFactory,
                               QVBoxLayout, QWidget)

from config import BASE_DIR

# ---------------------------------------------------------------- cores
# Preto de verdade + o ouro metálico do símbolo. O ouro aparece em poucos lugares (botão principal,
# aba aberta, marca); o resto é preto em camadas com um chanfro de luz em cima, como peça de metal.
INK = "#050505"        # fundo das páginas
SKY = "#000000"        # menu lateral
CARD = "#0f0f10"       # painéis
FIELD = "#17171a"      # campos / botões
FIELD_HI = "#202024"   # hover
LINE = "#26262a"       # bordas
TEXT = "#eeece7"
MUTED = "#8e8b84"
FAINT = "#55534e"
GOLD_HI = "#f5d27a"    # luz do metal
AETHER = "#d9a441"     # ouro (meio do metal)
AETHER2 = "#8a5a1c"    # sombra do metal
GOLD = "#f2c14e"       # alertas (Shugo, eventos)
METAL = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f3d07a, stop:0.48 #d8a443, stop:0.52 #c7922f, stop:1 #93631f)"
METAL_HI = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbe0a0, stop:0.48 #e6b456, stop:0.52 #d6a03b, stop:1 #a57126)"

# nomes antigos (outros módulos ainda importam)
BG, PANEL, PANEL2, BORDER, ACCENT, ACCENT_DARK = INK, CARD, FIELD, LINE, AETHER, AETHER2

UI = os.path.join(BASE_DIR, "ui").replace("\\", "/")
FONT = "'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif"
FONT_DISPLAY = "Barlow Semi Condensed"     # fonte livre (OFL), vem junto em fonts/

QSS = f"""
* {{ font-family: {FONT}; font-size: 9pt; color: {TEXT}; }}
QWidget#Page, QStackedWidget, QScrollArea > QWidget > QWidget {{ background: {INK}; }}
QToolTip {{ background: {FIELD}; color: {TEXT}; border: 1px solid {LINE}; border-radius: 4px; padding: 5px 8px; }}

/* painéis: pintados pelo CardFrame (fundo, borda e o chanfro de luz em cima) */
QGroupBox {{
    background: transparent; border: none;
    margin-top: 2px; padding: 34px 14px 12px 14px;
}}
QGroupBox::title {{ color: transparent; subcontrol-origin: padding; left: 0; top: 0; }}
QLabel {{ background: transparent; }}
QLabel[hint="true"] {{ color: {MUTED}; }}
QLabel:disabled {{ color: {FAINT}; }}

QPushButton {{
    background: {FIELD}; border: 1px solid #2c2c31; border-top-color: #38383e; border-radius: 5px;
    padding: 4px 12px; color: {TEXT}; min-height: 16px;
}}
QPushButton:hover {{ background: {FIELD_HI}; border-color: #46464d; }}
QPushButton:pressed {{ background: #0c0c0d; border-top-color: #1c1c1f; }}
QPushButton:focus {{ border-color: #6b5320; }}
/* ação principal: o metal dourado do símbolo */
QPushButton:checked, QPushButton[primary="true"] {{
    background: {METAL}; border: 1px solid #5c3f12; border-top-color: #f8dc93;
    color: #1b1204; font-weight: 600;
}}
QPushButton[primary="true"]:hover, QPushButton:checked:hover {{ background: {METAL_HI}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: #1c1c1f; background: #0c0c0d; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #0b0b0c; border: 1px solid #2a2a2e; border-bottom-color: #34343a; border-radius: 5px;
    padding: 3px 8px; min-height: 16px;
    selection-background-color: {AETHER}; selection-color: #1b1204;
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #45454c; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {AETHER}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; border-color: #1c1c1f; }}
QSpinBox, QDoubleSpinBox {{ max-width: 170px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({UI}/down.svg); width: 10px; height: 6px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({UI}/up.svg); width: 9px; height: 5px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({UI}/down.svg); width: 9px; height: 5px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent;
}}
QComboBox QAbstractItemView {{
    background: #0f0f10; border: 1px solid {LINE}; border-radius: 5px;
    selection-background-color: #1f1a10; selection-color: {GOLD_HI}; outline: none; padding: 4px;
}}

QCheckBox {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{ width: 32px; height: 18px; border: none; image: url({UI}/switch_off.svg); }}
QCheckBox::indicator:checked {{ image: url({UI}/switch_on.svg); }}
QCheckBox::indicator:disabled {{ image: url({UI}/switch_off_dis.svg); }}
QCheckBox::indicator:checked:disabled {{ image: url({UI}/switch_on_dis.svg); }}
QCheckBox:disabled {{ color: {FAINT}; }}
QRadioButton {{ spacing: 9px; background: transparent; padding: 3px 0; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid {LINE}; background: {FIELD}; }}
QRadioButton::indicator:hover {{ border-color: {MUTED}; }}
QRadioButton::indicator:checked {{ border-color: {AETHER};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {GOLD_HI}, stop:0.42 {AETHER}, stop:0.5 {FIELD}, stop:1 {FIELD}); }}

QSlider::groove:horizontal {{ height: 4px; background: #222226; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {AETHER}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {GOLD_HI}; border: 3px solid #050505; width: 10px; height: 10px; margin: -6px 0; border-radius: 8px;
}}

QListWidget, QTreeWidget, QTableWidget {{
    background: #0b0b0c; border: 1px solid #222226; border-radius: 6px; padding: 2px; outline: none;
    alternate-background-color: #0f0f11;
}}
QListWidget::item, QTreeWidget::item {{ padding: 3px 6px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: #151517; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{ background: #1f1a10; color: {GOLD_HI}; }}
QHeaderView::section {{
    background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid #26262a;
    padding: 4px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a2a2f; min-height: 30px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4a52; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QMenu {{ background: #0f0f10; border: 1px solid {LINE}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: #1f1a10; color: {GOLD_HI}; }}
QMessageBox, QDialog {{ background: {INK}; }}

/* menu lateral: preto puro; a aba aberta ganha uma barra de ouro (pintada no NavButton) */
#NavBar QPushButton {{
    text-align: left; padding: 7px 10px 7px 14px; border: none; border-radius: 6px;
    background: transparent; color: {MUTED}; font-size: 9.5pt;
}}
#NavBar QPushButton[tagged="true"] {{ padding-top: 2px; padding-bottom: 15px; }}
#NavBar QPushButton:hover {{ color: {TEXT}; background: #0e0e10; }}
#NavBar QPushButton:checked {{ color: {TEXT}; background: #141416; border: none; font-weight: 600; }}
#NavBar QPushButton#LockPill {{
    border: 1px solid {LINE}; background: #0b0b0c; padding: 6px 10px; font-size: 8.5pt; border-radius: 6px;
    color: {MUTED};
}}
#NavBar QPushButton#LockPill:checked {{ border-color: #5c3f12; color: {GOLD_HI}; background: #17120a; }}
#Brand {{ color: {TEXT}; font-family: '{FONT_DISPLAY}'; font-size: 13.5pt; font-weight: 600; }}
#BrandSub {{ color: {MUTED}; font-size: 7.5pt; }}
#PageTitle {{ font-family: '{FONT_DISPLAY}'; font-size: 19pt; font-weight: 600; color: {TEXT}; }}
#PageSub {{ color: {MUTED}; font-size: 8.5pt; padding-bottom: 6px; }}
"""


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    folder = os.path.join(BASE_DIR, "fonts")
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(folder, f))


def display_font(pt, weight=QFont.DemiBold):
    f = QFont(FONT_DISPLAY)
    f.setPointSizeF(pt)
    f.setWeight(weight)
    return f


def panel_path(r, radius=8):
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    return path


def draw_bevel(p, r, radius=8, alpha=18):
    """Chanfro de luz na borda de cima (o painel parece uma peça de metal escuro)."""
    p.save()
    p.setClipRect(QRectF(r.left(), r.top(), r.width(), radius + 1))
    c = QColor(255, 255, 255, alpha)
    p.setPen(QPen(c, 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.restore()


def draw_mark(p, center, color, h=12):
    """Marquinha vertical (no lugar do losango antigo) para títulos de overlays."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(center.x() - 1.5, center.y() - h / 2, 3, h), 1.5, 1.5)
    p.restore()


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
    """Pinta os painéis (QGroupBox): preto em camada, borda fina, chanfro de luz e o título na fonte condensada."""

    def eventFilter(self, w, e):
        if e.type() == QEvent.Paint and isinstance(w, QGroupBox):
            p = QPainter(w)
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(w.rect()).adjusted(0.5, 2.5, -0.5, -0.5)
            path = panel_path(r, 8)
            p.fillPath(path, QColor(CARD) if w.isEnabled() else QColor("#0a0a0b"))
            p.setPen(QPen(QColor(LINE), 1))
            p.drawPath(path)
            draw_bevel(p, r, 8, 22 if w.isEnabled() else 8)
            title = w.title()
            if title:
                f = display_font(11.5)
                p.setFont(f)
                p.setPen(QColor(TEXT if w.isEnabled() else FAINT))
                fm = p.fontMetrics()
                p.drawText(QPointF(r.left() + 14, r.top() + 10 + fm.ascent()), title)
            p.end()
        return False


_card_frame = None


def apply(app):
    global _card_frame
    load_fonts()
    _card_frame = CardFrame(app)             # instalado só nos cartões (QGroupBox), em polish()
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
    # antes o pintor dos cartões ficava no app inteiro: todo evento de toda janela (inclusive os overlays
    # redesenhando) passava pelo Python. Agora só os cartões passam por ele.
    if _card_frame is not None:
        for gb in ([root] if isinstance(root, _G) else []) + root.findChildren(_G):
            if not gb.property("_card"):
                gb.setProperty("_card", True)
                gb.installEventFilter(_card_frame)
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
    elif name == "settings":        # engrenagem
        c = P(0.5, 0.5)
        for k in range(8):
            ang = k * math.pi / 4
            p.drawLine(QPointF(c.x() + math.cos(ang) * w * 0.27, c.y() + math.sin(ang) * h * 0.27),
                       QPointF(c.x() + math.cos(ang) * w * 0.4, c.y() + math.sin(ang) * h * 0.4))
        p.drawEllipse(c, w * 0.27, h * 0.27)
        p.drawEllipse(c, w * 0.1, h * 0.1)
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
        self.setFixedSize(38, 38)

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
    """Menu lateral: preto puro com uma linha fina separando das páginas."""

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(SKY))
        p.setPen(QColor("#1b1b1e"))
        p.drawLine(r.topRight(), r.bottomRight())
        p.end()


class NavButton(QPushButton):
    """Item do menu: ícone + texto; o aberto ganha uma barra de ouro metálico na esquerda."""

    tag = ""          # texto pequeno embaixo do nome (ex.: "experimental")

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.tag:
            p = QPainter(self)
            f = QFont(self.font())
            f.setPointSizeF(7.0)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(QColor(AETHER) if self.isChecked() else QColor(AETHER2).lighter(130))
            x = 14 + (self.iconSize().width() + QFontMetrics(self.font()).horizontalAdvance("  ") + 4
                      if not self.icon().isNull() else 0)
            p.drawText(QRectF(x, self.height() - 17, self.width() - x - 6, 12), Qt.AlignLeft | Qt.AlignVCenter,
                       self.tag)
            p.end()
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            g = QLinearGradient(0, 6, 0, self.height() - 6)
            g.setColorAt(0, QColor(GOLD_HI))
            g.setColorAt(1, QColor(AETHER2))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 7, 3, self.height() - 14), 1.5, 1.5)
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
        self.bar.setFixedWidth(194)
        self.bl = QVBoxLayout(self.bar)
        self.bl.setContentsMargins(8, 12, 8, 10)
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
        head.setContentsMargins(2, 0, 0, 10)
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
        wl.setContentsMargins(18, 12, 18, 10)
        wl.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        wl.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setObjectName("PageSub")
            s.setWordWrap(True)
            wl.addWidget(s)
        wl.addSpacing(4)
        # cada página rola sozinha: a janela pode ficar pequena sem esmagar nada
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(widget)
        wl.addWidget(sc, 1)
        return wrap

    def insertTab(self, index, widget, title, icon=None, sub=None):
        index = min(index, len(self.pages))
        key = self._split(title)
        tag = key.endswith(" (experimental)")
        title = self.T(key)
        wrap = self._wrap(widget, title, self.T(sub) if sub else None)
        # "(experimental)" não cabe ao lado do nome no menu: vira uma linha pequena embaixo
        btn = NavButton(("  " if icon else "") + (self.T(key[:-15]) if tag else title))
        if tag:
            btn.tag = self.T("experimental")
            btn.setProperty("tagged", True)
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
