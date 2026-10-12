"""Ícones do jogo (recortados da imagem enviada pelo usuário) para recursos e chefes.

icons/mat_<n>.png  -> material n da lista "names" de data/resources.json
icons/cat_<cat>.png -> ícone que representa a categoria
icons/world_boss.png
"""
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from config import BASE_DIR

FOLDER = os.path.join(BASE_DIR, "icons")
_names = None
_cache = {}


def _material_index(name):
    global _names
    if _names is None:
        try:
            with open(os.path.join(BASE_DIR, "data", "resources.json"), encoding="utf-8") as f:
                _names = json.load(f)["names"]
        except Exception:
            _names = []
    try:
        return _names.index(name)
    except ValueError:
        return None


def _pix(file, size):
    key = (file, size)
    if key not in _cache:
        path = os.path.join(FOLDER, file)
        pm = QPixmap(path) if os.path.exists(path) else QPixmap()
        if not pm.isNull():
            pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _cache[key] = pm
    return _cache[key]


def material(name, size=20):
    i = _material_index(name)
    return _pix(f"mat_{i}.png", size) if i is not None else QPixmap()


def category(cat, size=20):
    return _pix(f"cat_{cat}.png", size)


def world_boss(size=40):
    return _pix("world_boss.png", size)


def draw_resource(p, center, pix, size, left=None, total=300, collected=False, fallback=None):
    """Desenha o ícone do recurso. Com timer: ícone apagado + anel de contagem + tempo embaixo."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QFont, QPen
    from respawn import fmt
    r = size / 2
    p.save()
    # sombra redonda para destacar o ícone em qualquer fundo
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(8, 7, 6, 150))
    p.drawEllipse(center, r * 0.95, r * 0.95)
    p.setOpacity(0.28 if collected else (0.42 if left else 1.0))
    if pix is not None and not pix.isNull():
        p.drawPixmap(QRectF(center.x() - r, center.y() - r, size, size), pix, QRectF(pix.rect()))
    else:
        p.setBrush(QColor(fallback or "#e0b04f"))
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.2))
        p.drawEllipse(center, r * 0.45, r * 0.45)
    p.setOpacity(1.0)
    if left:
        ring = QRectF(center.x() - r - 2, center.y() - r - 2, size + 4, size + 4)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        p.drawEllipse(ring)
        p.setPen(QPen(QColor("#e0b04f"), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(ring, 90 * 16, int(-360 * 16 * left / total))
        txt = fmt(left)
        f = QFont("Segoe UI", max(7, int(size / 2.6)), QFont.Bold)
        p.setFont(f)
        tr = QRectF(center.x() - 26, center.y() + r + 2, 52, f.pointSize() + 8)
        p.setPen(QColor(0, 0, 0, 200))
        p.drawText(tr.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, txt)
        p.setPen(QColor("#fff6e2"))
        p.drawText(tr, Qt.AlignHCenter | Qt.AlignTop, txt)
    p.restore()
