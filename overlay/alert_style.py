"""Visual dos avisos na tela (Shugo, fendas, chefes, eventos e o mini-mapa do local).

Mesma linguagem do DPS Meter: painel escuro com dois cantos cortados e uma linha fina no topo, aqui na cor
do tipo de aviso. Contagem regressiva ao vivo, texto que quebra em 2 linhas em vez de cortar, e uma barra
fininha embaixo mostrando quando o aviso some.
"""
import math

from PySide6.QtCore import QPointF, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen

KIND_COLORS = {
    "shugo": "#f2c14e",     # ouro
    "rift": "#a98bff",      # violeta
    "boss": "#ff6170",      # vermelho
    "event": "#5bb8ff",     # azul
}
PANEL_BG = QColor(10, 12, 15, 238)
HAIRLINE = QColor(255, 255, 255, 24)
TEXT = QColor("#f2f4f7")
MUTED = QColor("#9aa1ab")
CUT = 12


def kind_color(kind):
    return QColor(KIND_COLORS.get(kind, KIND_COLORS["shugo"]))


def panel_path(r, cut=CUT):
    """Retângulo com os cantos de cima à esquerda e de baixo à direita cortados."""
    path = QPainterPath()
    path.moveTo(r.left() + cut, r.top())
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom() - cut)
    path.lineTo(r.right() - cut, r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + cut)
    path.closeSubpath()
    return path


def draw_panel(p, rect, color, locked=True, life=None):
    """Fundo do aviso. life = fração do tempo na tela que ainda resta (0..1) ou None."""
    r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    edge = QColor(HAIRLINE)
    if not locked:                                    # destravado: borda dourada = dá para arrastar
        edge = QColor(217, 164, 65, 150)
    p.setPen(QPen(edge, 1))
    p.setBrush(PANEL_BG)
    p.drawPath(panel_path(r))
    # brilho bem leve da cor do aviso vindo da esquerda
    glow = QLinearGradient(r.left(), 0, r.left() + r.width() * 0.55, 0)
    g0 = QColor(color)
    g0.setAlpha(34)
    g1 = QColor(color)
    g1.setAlpha(0)
    glow.setColorAt(0, g0)
    glow.setColorAt(1, g1)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(glow))
    p.drawPath(panel_path(r.adjusted(1, 1, -1, -1), CUT - 1))
    # a linha do topo (como no medidor), na cor do tipo, apagando para a direita + o corte do canto
    line = QLinearGradient(r.left() + CUT, 0, r.left() + r.width() * 0.75, 0)
    c1 = QColor(color)
    c1.setAlpha(0)
    line.setColorAt(0, color)
    line.setColorAt(1, c1)
    p.setPen(QPen(QBrush(line), 1.8))
    p.drawLine(QPointF(r.left() + CUT, r.top() + 0.9), QPointF(r.right() - 1, r.top() + 0.9))
    p.setPen(QPen(color, 1.8))
    p.drawLine(QPointF(r.left() + 0.9, r.top() + CUT), QPointF(r.left() + CUT, r.top() + 0.9))
    if life is not None:                              # quanto falta para o aviso sumir
        life = max(0.0, min(1.0, life))
        track = QRectF(r.left() + 14, r.bottom() - 4, r.width() - 28 - CUT, 2)
        p.fillRect(track, QColor(255, 255, 255, 18))
        bar = QColor(color)
        bar.setAlpha(170)
        p.fillRect(QRectF(track.left(), track.top(), track.width() * life, track.height()), bar)


def draw_emblem(p, center, radius, color, pixmap=None, glyph=None, pulse=0.0):
    """Ícone redondo: anel na cor do aviso; pulse (0..1) acende um halo nos avisos urgentes."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if pulse > 0:
        halo = QColor(color)
        halo.setAlpha(int(70 * pulse))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(center, radius + 5 * pulse + 2, radius + 5 * pulse + 2)
    disc = QColor(color).darker(520)
    disc.setAlpha(235)
    p.setPen(QPen(color, 1.6))
    p.setBrush(disc)
    p.drawEllipse(center, radius, radius)
    if pixmap is not None and not pixmap.isNull():
        inner = radius - 2.5
        clip = QPainterPath()
        clip.addEllipse(center, inner, inner)
        p.setClipPath(clip)
        p.drawPixmap(QRectF(center.x() - inner, center.y() - inner, inner * 2, inner * 2), pixmap,
                     QRectF(pixmap.rect()))
        p.setClipping(False)
    elif glyph:
        import theme
        s = radius * 1.05
        theme.draw_glyph(p, glyph, QRectF(center.x() - s / 2, center.y() - s / 2, s, s), QColor(color).lighter(125))
    p.restore()


def display(pt, weight=QFont.DemiBold):
    import theme
    f = theme.display_font(pt, weight)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def ui(pt, weight=QFont.Normal):
    f = QFont("Segoe UI", 1, weight)
    f.setPointSizeF(pt)
    return f


def countdown_text(seconds):
    seconds = max(0, int(math.ceil(seconds)))
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def wrap_lines(text, font, width, max_lines=2):
    """Quebra em até max_lines linhas; o que não couber termina em '…'."""
    fm = QFontMetrics(font)
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if fm.horizontalAdvance(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fm.elidedText(lines[-1] + " …", Qt.ElideRight, int(width))
    return [fm.elidedText(ln, Qt.ElideRight, int(width)) for ln in lines] or [""]


def wrap_height(text, font, width, max_lines=2):
    return len(wrap_lines(text, font, width, max_lines)) * QFontMetrics(font).lineSpacing()


def draw_wrapped(p, rect, text, font, color, max_lines=2):
    p.setFont(font)
    p.setPen(color)
    fm = QFontMetrics(font)
    y = rect.top()
    for ln in wrap_lines(text, font, rect.width(), max_lines):
        p.drawText(QRectF(rect.left(), y, rect.width(), fm.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, ln)
        y += fm.lineSpacing()


def draw_alert(p, w, h, kind, title, msg, sub, left=None, life=None, locked=True, pixmap=None, glyph=None,
               pulse=0.0):
    """O aviso inteiro (Shugo, fendas, chefes, eventos): emblema, título na cor do tipo, contagem ao vivo,
    mensagem e detalhe."""
    color = kind_color(kind)
    draw_panel(p, QRectF(0, 0, w, h), color, locked, life)
    draw_emblem(p, QPointF(40, min(h / 2, 46)), 25, color, pixmap, glyph, pulse)
    x = 80
    right = w - 16
    if left is not None and left > 0:
        cd = countdown_text(left)
        p.setFont(display(19, QFont.DemiBold))
        p.setPen(TEXT)
        fm = QFontMetrics(p.font())
        cw = fm.horizontalAdvance(cd)
        p.drawText(QRectF(right - cw, 9, cw, 28), Qt.AlignRight | Qt.AlignVCenter, cd)
        right_title = right - cw - 10
    else:
        right_title = right
    tf = display(10.5, QFont.DemiBold)
    p.setFont(tf)
    p.setPen(color)
    p.drawText(QRectF(x, 11, right_title - x, 18), Qt.AlignLeft | Qt.AlignVCenter,
               QFontMetrics(tf).elidedText(title, Qt.ElideRight, int(right_title - x)))
    mf = ui(12.5, QFont.Bold)
    p.setFont(mf)
    p.setPen(TEXT)
    p.drawText(QRectF(x, 30, right_title - x, 24), Qt.AlignLeft | Qt.AlignVCenter,
               QFontMetrics(mf).elidedText(msg, Qt.ElideRight, int(right_title - x)))
    if sub:
        draw_wrapped(p, QRectF(x, 56, w - x - 16, 40), sub, ui(8.5), MUTED)


def alert_height(w, sub):
    """Altura que o aviso precisa (o detalhe pode ocupar 1 ou 2 linhas)."""
    sh = wrap_height(sub, ui(8.5), w - 80 - 16) if sub else 0
    return int(max(84, 56 + sh + 16))


def fade_in(widget, target):
    """Uma entrada curta (180 ms) no lugar do contorno piscando o tempo todo."""
    try:
        anim = QPropertyAnimation(widget, b"windowOpacity", widget)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(target)
        widget._fade = anim
        anim.start()
    except Exception:
        widget.setWindowOpacity(target)
