"""Configuração persistente do overlay (salva em %APPDATA%/Aion2Overlay/config.json)."""
import copy
import json
import os
import sys

# Pasta dos arquivos do programa (funciona também empacotado com PyInstaller)
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Aion2Overlay")
CFG_PATH = os.path.join(APP_DIR, "config.json")
os.makedirs(APP_DIR, exist_ok=True)

CATEGORIES = [
    # chave interna, nome exibido, cor
    ("berry", "Berries (Frutas)", "#e0475b"),
    ("jewelry", "Gems (Gemas)", "#c86bf0"),
    ("herb", "Herbs (Ervas)", "#58c46c"),
    ("metal", "Metal Ore (Minério)", "#c0c7d1"),
    ("od", "Od (Odyle)", "#3fd0e0"),
    ("shellfish", "Shellfish (Mariscos)", "#f2a65a"),
    ("tree", "Trees (Árvores)", "#9a6b3f"),
    ("vegetable", "Vegetables (Vegetais)", "#b5d94a"),
    # locais onde o cubo PODE nascer — não é garantido
    ("cube", "Hidden Cube (possível)", "#e0583c"),
]

DEFAULTS = {
    "locked": False,
    "ui_scale": 1.0,
    "app": {
        "close_action": "tray",  # X da janela: "tray" = continua na bandeja, "quit" = fecha o programa
    },
    "dps": {"enabled": False},
    "events": {"sound": "sounds/shugo.wav", "volume": 80},
    "farm": {"sound": "sounds/shugo.wav", "volume": 80},
    "shugo": {
        "enabled": True,         # aviso do Festival Shugo ligado
        "visible": True,
        "warn_minutes": 3,
        "offset_minutes": 0,
        "sound": "sounds/shugo.wav",
        "volume": 80,
        "opacity": 0.85,
        "pos": None,
    },
    "pvp": {
        "auto": True,            # liga sozinho ao abrir (se tiver Npcap e administrador)
        "sound": "sounds/kill.wav",
        "volume": 80,
    },
    "pvp_assist": {"sound": "sounds/assist.wav", "volume": 70},
    "map": {
        "world": "1010",
        "filters": {c[0]: True for c in CATEGORIES},
        "material": "",
        "collected": [],
        "hide_collected": False,
        "show_regions": True,
        "show_labels": True,
        "on_top": True,
        "opacity": 1.0,
        "geometry": None,
        "dot_size": 8,
    },
}


def _same_kind(default, value):
    """O valor salvo tem o mesmo tipo do padrão? (um config.json editado à mão ou estragado não pode
    derrubar o programa toda vez que ele abre)"""
    if default is None or value is None:
        return True
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, (list, tuple)):
        return isinstance(value, (list, tuple))
    if isinstance(default, dict):
        return isinstance(value, dict)
    return True


def _merge(base, extra):
    if not isinstance(extra, dict):
        return base
    for k, v in extra.items():
        if isinstance(base.get(k), dict):
            if isinstance(v, dict):
                _merge(base[k], v)
        elif k not in base or _same_kind(base[k], v):
            base[k] = v
    return base


cfg = copy.deepcopy(DEFAULTS)


def load():
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                _merge(cfg, json.load(f))
        except Exception as e:  # config corrompida: guarda uma cópia e começa do padrão
            print("Erro lendo config:", e)
            try:
                import shutil
                shutil.copy2(CFG_PATH, CFG_PATH.replace(".json", ".corrompido.json"))
            except OSError:
                pass
    return cfg


def save():
    """Grava de forma segura (arquivo temporário + troca). Se o Windows/antivírus estiver segurando o
    arquivo, tenta de novo algumas vezes; nunca derruba a ação que pediu para salvar."""
    import time
    tmp = CFG_PATH + ".tmp"
    for attempt in range(5):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
            os.replace(tmp, CFG_PATH)
            return True
        except (OSError, TypeError, ValueError) as e:
            last = e
            time.sleep(0.05 * (attempt + 1))
    print("Não deu para salvar a config:", last)
    return False


def resolve(path):
    """Caminhos relativos apontam para a pasta do programa."""
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
