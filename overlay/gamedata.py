"""Arquivos grandes de data/ carregados uma vez só e divididos entre quem usa (só leitura).

Antes mobs.json (~4,5 MB na memória) e resources.json (~6 MB) eram lidos de novo pelo farm, pelo mapa,
pelos ícones e pelo leitor do jogo: até 3 cópias de cada.
"""
import json
import os
import threading

from config import BASE_DIR

_lock = threading.Lock()
_cache = {}


def load(name):
    with _lock:
        if name not in _cache:
            with open(os.path.join(BASE_DIR, "data", name), encoding="utf-8") as f:
                _cache[name] = json.load(f)
        return _cache[name]


def mobs():
    return load("mobs.json")


def resources():
    return load("resources.json")
