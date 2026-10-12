"""Painel do medidor de DPS na tela (os dados vêm do dps_live).

Cada linha: ícone + cor da classe, nome, crítico %, dupla chance %, DPS, total e %.
Botão de zerar no próprio painel (funciona mesmo com os overlays travados).
Ícones: desenhos próprios; para usar outros, ponha PNGs em %APPDATA%/Aion2Overlay/classes/
com os nomes gl.png, te.png, as.png, ra.png, so.png, el.png, cl.png, ch.png.
"""
import math
import os

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from base_window import OverlayWindow
from config import APP_DIR, BASE_DIR, cfg
from i18n import T

CLASSES = {
    # código: (nome, cor)
    "gl": ("Gladiador", "#e0583c"),
    "te": ("Templário", "#d9a441"),
    "as": ("Assassino", "#a35ddb"),
    "ra": ("Ranger", "#5dbb4f"),
    "so": ("Feiticeiro", "#4a86e8"),
    "el": ("Elementalista", "#2ec4c4"),
    "cl": ("Clérigo", "#efe0a0"),
    "ch": ("Chanter", "#e07bb0"),
}
NO_CLASS = "#9b9282"


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


_custom = {}


def custom_icon(code):
    if code not in _custom:
        _custom[code] = None
        for folder in (os.path.join(APP_DIR, "classes"), os.path.join(BASE_DIR, "classes")):
            path = os.path.join(folder, f"{code}.png")
            if os.path.exists(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    _custom[code] = pm
                    break
    return _custom[code]


def draw_class_icon(p, code, r):
    """Círculo na cor da classe com um símbolo simples desenhado."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor(CLASSES.get(code, ("", NO_CLASS))[1])
    pm = custom_icon(code) if code else None
    if pm:
        p.drawPixmap(r.toRect(), pm)
        p.restore()
        return
    p.setPen(QPen(color.lighter(130), 1.2))
    p.setBrush(color.darker(260))
    p.drawEllipse(r)
    c = r.center()
    s = r.width() / 2 * 0.62          # raio útil do desenho
    ink = QColor(color.lighter(115))
    pen = QPen(ink, max(1.4, r.width() / 12), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    P = lambda dx, dy: QPointF(c.x() + dx * s, c.y() + dy * s)
    if code == "gl":            # espada grande (lâmina larga + guarda + cabo)
        p.setBrush(ink)
        p.drawPolygon(QPolygonF([P(0, -1.0), P(0.2, -0.75), P(0.2, 0.3), P(-0.2, 0.3), P(-0.2, -0.75)]))
        p.setBrush(Qt.NoBrush)
        p.drawLine(P(-0.55, 0.38), P(0.55, 0.38))
        p.drawLine(P(0, 0.4), P(0, 0.85))
        p.drawEllipse(P(0, 0.95), s * 0.08, s * 0.08)
    elif code == "te":          # escudo
        path = QPainterPath(P(-0.7, -0.8))
        path.lineTo(P(0.7, -0.8))
        path.lineTo(P(0.7, 0.05))
        path.quadTo(P(0.6, 0.7), P(0, 1))
        path.quadTo(P(-0.6, 0.7), P(-0.7, 0.05))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(0, -0.45), P(0, 0.55))
    elif code == "as":          # duas adagas cruzadas
        p.drawLine(P(-0.8, 0.8), P(0.6, -0.6))
        p.drawLine(P(0.8, 0.8), P(-0.6, -0.6))
        p.drawLine(P(-0.75, 0.35), P(-0.35, 0.75))
        p.drawLine(P(0.75, 0.35), P(0.35, 0.75))
    elif code == "ra":          # arco e flecha
        path = QPainterPath(P(-0.2, -0.95))
        path.quadTo(P(0.9, 0), P(-0.2, 0.95))
        p.drawPath(path)
        p.drawLine(P(-0.2, -0.95), P(-0.2, 0.95))
        p.drawLine(P(-0.85, 0), P(0.75, 0))
        p.drawLine(P(0.75, 0), P(0.5, -0.22))
        p.drawLine(P(0.75, 0), P(0.5, 0.22))
    elif code == "so":          # chama
        path = QPainterPath(P(0, -1))
        path.cubicTo(P(0.9, -0.1), P(0.75, 0.95), P(0, 0.95))
        path.cubicTo(P(-0.75, 0.95), P(-0.8, 0.1), P(-0.25, -0.35))
        path.cubicTo(P(-0.2, 0.05), P(0.1, -0.2), P(0, -1))
        p.setBrush(ink)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif code == "el":          # estrela de 4 pontas (espírito)
        pts = []
        for k in range(8):
            ang = -math.pi / 2 + k * math.pi / 4
            rad = 1.0 if k % 2 == 0 else 0.32
            pts.append(P(math.cos(ang) * rad, math.sin(ang) * rad))
        p.setBrush(ink)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF(pts))
    elif code == "cl":          # sol com raios (luz / cura)
        p.drawEllipse(P(0, 0), s * 0.38, s * 0.38)
        for k in range(8):
            ang = k * math.pi / 4
            p.drawLine(P(math.cos(ang) * 0.62, math.sin(ang) * 0.62), P(math.cos(ang) * 0.98, math.sin(ang) * 0.98))
    elif code == "ch":          # cajado com anel
        p.drawLine(P(-0.55, 0.95), P(0.25, -0.25))
        p.drawEllipse(P(0.45, -0.5), s * 0.38, s * 0.38)
    else:                       # sem classe ainda
        p.setFont(QFont("Segoe UI", max(6, int(r.width() / 2.4)), QFont.Bold))
        p.drawText(r, Qt.AlignCenter, "?")
    p.restore()


class DpsMeter(OverlayWindow):
    W = 420
    ROW = 26
    reset_requested = Signal()
    row_clicked = Signal(int)      # índice da linha clicada (para o detalhe de habilidades)

    def __init__(self):
        cfg.setdefault("dps", {}).setdefault("opacity", 0.9)
        cfg["dps"].setdefault("pos", None)
        super().__init__("dps", QPoint(40, 340))
        # não rouba o foco do jogo ao clicar no botão de zerar
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setMouseTracking(True)
        self.target = T("Bata em algo para começar")
        self.elapsed = 0
        self.rows = []          # [(nome, classe, dano_total, é_você, crítico%, múltiplo%)]
        self.footer = ""
        self._hover_reset = False
        self.setFixedWidth(self.W)
        self._resize()

    # o painel continua clicável mesmo travado (só para o botão); travado = não arrasta
    def set_locked(self, locked):
        self._locked = locked
        self.update()

    def reset_rect(self):
        return QRectF(self.W - 70, 9, 22, 18)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.reset_rect().contains(e.position()):
            self.reset_requested.emit()
            return
        self._press_pos = e.position()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        start = getattr(self, "_press_pos", None)
        self._press_pos = None
        if start is None or e.button() != Qt.LeftButton:
            return
        if (e.position() - start).manhattanLength() < 5:        # clique (não arraste) numa linha
            y = e.position().y()
            i = int((y - 56) // self.ROW)
            if y >= 56 and 0 <= i < len(self.rows):
                self.row_clicked.emit(i)

    # o detalhe de habilidades fica sempre colado embaixo
    docked = None

    def _dock(self):
        if self.docked is not None:
            self.docked.move(self.x(), self.y() + self.height() + 6)

    def moveEvent(self, e):
        super().moveEvent(e)
        self._dock()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._dock()

    def mouseMoveEvent(self, e):
        h = self.reset_rect().contains(e.position())
        if h != self._hover_reset:
            self._hover_reset = h
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()
        super().mouseMoveEvent(e)

    def set_data(self, target, elapsed, rows, footer=""):
        self.target, self.elapsed, self.footer = target, elapsed, footer
        self.rows = sorted(rows, key=lambda r: -r[2])
        self._resize()
        self.update()

    def _resize(self):
        self.setFixedHeight(64 + max(1, len(self.rows)) * self.ROW + 30)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pad = 12
        # cabeçalho
        from theme import display_font, draw_diamond
        draw_diamond(p, QPointF(pad + 4, 17), 3.5, "#e0b04f")
        p.setPen(QColor("#f2ede3"))
        p.setFont(display_font(11))
        p.drawText(pad + 14, 22, T("Medidor de dano"))
        m, s = divmod(int(self.elapsed), 60)
        p.setPen(QColor("#c7bda8"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(0, 8, self.W - pad, 18), Qt.AlignRight, f"{m:02d}:{s:02d}")
        # botão zerar
        rr = self.reset_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 60 if self._hover_reset else 28))
        p.drawRect(rr)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI Symbol", 9, QFont.Bold))
        p.drawText(rr, Qt.AlignCenter, "↺")
        p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        p.drawText(pad, 44, self.target)
        p.setPen(QColor("#9b9282"))
        p.setFont(QFont("Segoe UI", 8))
        x = self.W - pad - 8
        for txt, w in (("%", 44), (T("Total"), 58), ("DPS", 52), (T("Duplo"), 40), (T("Crít."), 40)):
            p.drawText(QRectF(x - w, 30, w, 18), Qt.AlignRight | Qt.AlignVCenter, txt)
            x -= w

        total = sum(r[2] for r in self.rows) or 1
        top = self.rows[0][2] if self.rows else 1
        dur = max(1, self.elapsed)
        y = 56
        f_name = QFont("Segoe UI", 9, QFont.DemiBold)
        f_num = QFont("Segoe UI", 9)
        for i, row in enumerate(self.rows):
            name, cls, dmg, me = row[:4]
            crit, multi = (row[4], row[5]) if len(row) > 5 else (None, None)
            r = QRectF(pad, y, self.W - 2 * pad, self.ROW - 4)
            path = QPainterPath()
            path.addRect(r)
            p.fillPath(path, QColor(255, 255, 255, 18))
            bar = QRectF(r.x(), r.y(), r.width() * dmg / top, r.height())
            bp = QPainterPath()
            bp.addRect(bar)
            c = QColor(CLASSES.get(cls, ("", NO_CLASS))[1])
            c.setAlpha(120 if not me else 185)
            p.fillPath(bp, c)
            if me:
                p.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
            ic = QRectF(r.x() + 3, r.y() + 1, r.height() - 2, r.height() - 2)
            draw_class_icon(p, cls, ic)
            p.setPen(QColor("white"))
            p.setFont(f_name)
            p.drawText(r.adjusted(ic.width() + 9, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setFont(f_num)
            cols = [(f"{dmg / total * 100:.1f}%", 44), (fmt(dmg), 58), (fmt(dmg / dur), 52)]
            if crit is not None:
                cols += [(f"{multi * 100:.0f}%", 40), (f"{crit * 100:.0f}%", 40)]
            x = r.right() - 8
            for k, (txt, w) in enumerate(cols):
                p.setPen(QColor("white") if k < 3 else QColor(255, 255, 255, 190))
                p.drawText(QRectF(x - w, r.y(), w, r.height()), Qt.AlignVCenter | Qt.AlignRight, txt)
                x -= w
            y += self.ROW
        p.setPen(QColor("#9b9282"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(pad, y + 2, self.W - 2 * pad, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{T('Total')}: {fmt(total)}  ·  {fmt(total / dur)}/s" + (f"   ·   {self.footer}" if self.footer else ""))
        p.end()


class SkillPanel(OverlayWindow):
    """Detalhe por habilidade, preso logo abaixo do medidor: ícone, nome, golpes, crítico, dano/cura e %."""
    W = 420
    ROW = 24
    MAX = 12

    def __init__(self):
        cfg.setdefault("dps_skills", {}).setdefault("opacity", 0.9)
        cfg["dps_skills"].setdefault("pos", None)
        super().__init__("dps_skills", QPoint(40, 600))
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setWindowFlag(Qt.WindowTransparentForInput, True)   # não tem botão: o clique vai para o jogo
        self.who = ""
        self.cls = None
        self.rows = []
        self.setFixedWidth(self.W)
        self._resize()

    def set_locked(self, locked):          # vai junto com o medidor; não se arrasta sozinho
        self._locked = locked
        self.update()

    def mousePressEvent(self, e):
        pass

    def set_data(self, who, cls, rows):
        self.who, self.cls, self.rows = who, cls, rows[:self.MAX]
        self._resize()
        self.update()

    def _resize(self):
        self.setFixedHeight(48 + max(1, len(self.rows)) * self.ROW + 30)

    def paintEvent(self, e):
        super().paintEvent(e)
        from theme import display_font, draw_diamond
        import skills_db
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        pad = 12
        draw_diamond(p, QPointF(pad + 4, 17), 3.5, CLASSES.get(self.cls, ("", "#e0b04f"))[1])
        p.setPen(QColor("#f2ede3"))
        p.setFont(display_font(11))
        p.drawText(pad + 14, 22, T("Habilidades") + (f" · {self.who}" if self.who else ""))
        p.setPen(QColor("#9b9282"))
        p.setFont(QFont("Segoe UI", 8))
        x = self.W - pad - 8
        for txt, w in (("%", 44), (T("Valor"), 64), (T("Crít."), 40), (T("Golpes"), 46)):
            p.drawText(QRectF(x - w, 26, w, 16), Qt.AlignRight | Qt.AlignVCenter, txt)
            x -= w
        if not self.rows:
            p.setPen(QColor("#9b9282"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(pad, 46, self.W - 2 * pad, self.ROW), Qt.AlignVCenter | Qt.AlignLeft,
                       T("Nenhuma habilidade ainda."))
            p.end()
            return
        tot_d = sum(r["dmg"] for r in self.rows) or 1
        tot_h = sum(r["heal"] for r in self.rows) or 1
        tot_s = sum(r.get("shield", 0) for r in self.rows) or 1
        top = max(max(r["dmg"], r["heal"], r.get("shield", 0)) for r in self.rows) or 1
        ccol = QColor(CLASSES.get(self.cls, ("", NO_CLASS))[1])
        y = 46
        f_name = QFont("Segoe UI", 9, QFont.DemiBold)
        f_num = QFont("Segoe UI", 9)
        for r in self.rows:
            if r["dmg"]:
                val, tot, col, kind = r["dmg"], tot_d, QColor(ccol), "dmg"
            elif r["heal"]:
                val, tot, col, kind = r["heal"], tot_h, QColor("#5ee39a"), "heal"
            else:
                val, tot, col, kind = r.get("shield", 0), tot_s, QColor("#e0b04f"), "shield"
            rr = QRectF(pad, y, self.W - 2 * pad, self.ROW - 3)
            p.fillRect(rr, QColor(255, 255, 255, 14))
            col.setAlpha(90)
            p.fillRect(QRectF(rr.x(), rr.y(), rr.width() * val / top, rr.height()), col)
            ic = QRectF(rr.x() + 2, rr.y() + 1, rr.height() - 2, rr.height() - 2)
            pm = skills_db.icon(r.get("icon"), int(ic.width()))
            if pm:
                p.drawPixmap(ic.toRect(), pm)
            else:   # sem ícone baixado: quadradinho na cor da classe com as iniciais
                p.fillRect(ic, QColor(CLASSES.get(r.get("cls"), ("", NO_CLASS))[1]).darker(220))
                p.setPen(QColor("white"))
                p.setFont(QFont("Segoe UI", 7, QFont.Bold))
                ini = "".join(w[0] for w in (r.get("name") or "?").split()[:2]).upper()
                p.drawText(ic, Qt.AlignCenter, ini)
            p.setPen(QColor("white"))
            p.setFont(f_name)
            name = r.get("name") or f"#{r['skill']}"
            p.drawText(rr.adjusted(ic.width() + 8, 0, -200, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(name, Qt.ElideRight, int(rr.width() - ic.width() - 208)))
            p.setFont(f_num)
            hits = r["hits"] if kind == "dmg" else r.get("heals", 0)
            crit = f"{r['crit'] / r['hits'] * 100:.0f}%" if kind == "dmg" and r["hits"] else "—"
            sign = "+" if kind == "heal" else ""
            cols = [(f"{val / tot * 100:.1f}%", 44), (sign + fmt(val), 64), (crit, 40), (str(hits), 46)]
            x = rr.right() - 8
            for k, (txt, w) in enumerate(cols):
                if k == 1 and kind == "heal":
                    p.setPen(QColor("#8ff0b8"))
                elif k == 1 and kind == "shield":
                    p.setPen(QColor("#f4d58c"))
                else:
                    p.setPen(QColor("white") if k < 2 else QColor(255, 255, 255, 190))
                p.drawText(QRectF(x - w, rr.y(), w, rr.height()), Qt.AlignVCenter | Qt.AlignRight, txt)
                x -= w
            y += self.ROW
        dmg = sum(r["dmg"] for r in self.rows)
        heal = sum(r["heal"] for r in self.rows)
        shield = sum(r.get("shield", 0) for r in self.rows)
        p.setPen(QColor("#9b9282"))
        p.setFont(QFont("Segoe UI", 8))
        txt = f"{T('Dano')}: {fmt(dmg)}   ·   {T('Cura')}: {fmt(heal)}   ·   {T('Escudo')}: {fmt(shield) if shield else '—'}"
        p.drawText(QRectF(pad, y + 2, self.W - 2 * pad, 18), Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.end()
