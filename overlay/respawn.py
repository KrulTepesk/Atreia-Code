"""Timers de renascimento dos recursos (padrão 5 min), compartilhados entre o mapa e o minimapa do Alt+M.

Chave do recurso = "mundo:x:y:categoria" (a mesma usada para "coletado"). Guardado no config com o horário
de término, então continua contando mesmo fechando o programa.
"""
import time

from config import cfg, save


def _timers():
    return cfg.setdefault("map", {}).setdefault("timers", {})


def minutes():
    return cfg.setdefault("map", {}).get("respawn_minutes", 5)


def total():
    return max(1, minutes() * 60)


def start(key):
    _timers()[key] = time.time() + total()
    save()


def cancel(key):
    if _timers().pop(key, None) is not None:
        save()


def remaining(key):
    """Segundos que faltam (ou None se não tem timer / já renasceu)."""
    end = _timers().get(key)
    if end is None:
        return None
    left = end - time.time()
    if left <= 0:
        _timers().pop(key, None)
        return None
    return left


def active_keys():
    now = time.time()
    t = _timers()
    for k in [k for k, end in t.items() if end <= now]:
        t.pop(k, None)
    return set(t)


def fmt(left):
    m, s = divmod(int(left + 0.999), 60)
    return f"{m}:{s:02d}"
