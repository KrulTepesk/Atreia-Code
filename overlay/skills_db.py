"""Banco de habilidades (todas as classes, ativas + estigmas + passivas): id -> classe, nome, ícone.

O id que vem do jogo tem nível/variação nos últimos dígitos (ex.: 18330000 = Marchutan's Wrath,
17350450 = Condemnation nível 45...). Procura o id exato, depois sem os 2 e sem os 4 últimos dígitos.
Os ícones ficam em skill_icons/<ICONE>.png (baixados ao gerar o instalador).
"""
import json
import os

from config import BASE_DIR

_db = None
ICON_DIR = os.path.join(BASE_DIR, "skill_icons")


def _load():
    global _db
    if _db is None:
        try:
            with open(os.path.join(BASE_DIR, "data", "skills.json"), encoding="utf-8") as f:
                _db = json.load(f)
        except Exception:
            _db = {}
    return _db


def lookup(skill):
    """-> (chave, classe, nome, ícone|None)"""
    db = _load()
    for k in (skill, skill // 100 * 100, skill // 10000 * 10000):
        v = db.get(str(k))
        if v:
            return str(k), v[0], v[1], v[2]
    return str(skill), None, None, None


_pix = {}


def icon(icon_name, size):
    """QPixmap do ícone (ou None se ainda não foi baixado)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    if not icon_name:
        return None
    key = (icon_name, size)
    if key not in _pix:
        path = os.path.join(ICON_DIR, icon_name + ".png")
        pm = QPixmap(path) if os.path.exists(path) else QPixmap()
        _pix[key] = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull() else None
    return _pix[key]
