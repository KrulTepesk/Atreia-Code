"""Idioma do aplicativo: Português (Brasil), English ou Español.

Os textos do programa são escritos em português; nos outros idiomas, T() troca pelo texto do
dicionário EN / ES. Nomes do jogo (monstros, materiais, regiões, pets) usam data/names_en.json
(em espanhol também, já que os nomes oficiais em espanhol não estão no banco de dados).
A troca de idioma vale depois de reiniciar o programa.
"""
import json
import os

from config import BASE_DIR, cfg

LANGS = [("pt", "Português (Brasil)"), ("en", "English"), ("es", "Español")]
_names = None


def lang():
    return cfg.get("lang", "pt")


def T(text):
    lg = lang()
    if lg == "pt" or not isinstance(text, str):
        return text
    if lg == "es":
        from i18n_es import ES
        return ES.get(text, text)
    from i18n_en import EN
    return EN.get(text, text)


def N(name):
    """Nome do jogo (monstro, material, região) no idioma escolhido."""
    global _names
    if lang() == "pt" or not name:
        return name
    if _names is None:
        try:
            with open(os.path.join(BASE_DIR, "data", "names_en.json"), encoding="utf-8") as f:
                _names = json.load(f)
        except OSError:
            _names = {"names": {}, "regions": {}, "pets": {}}
    return _names["names"].get(name) or _names["regions"].get(name) or name


def PET(pet_id, pt_name):
    if lang() == "pt":
        return pt_name
    N("")  # garante carregado
    global _names
    if _names is None:
        N("x")
    return (_names or {}).get("pets", {}).get(pet_id, pt_name)


def translate_tree(root):
    """Traduz os textos fixos de uma janela já montada (labels, botões, caixas, títulos...)."""
    if lang() == "pt":
        return
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QWidget)
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        if isinstance(w, (QLabel, QAbstractButton)):
            t = w.text()
            nt = T(t)
            if nt != t:
                w.setText(nt)
        if isinstance(w, QGroupBox):
            w.setTitle(T(w.title()))
        if isinstance(w, QLineEdit) and w.placeholderText():
            w.setPlaceholderText(T(w.placeholderText()))
        if isinstance(w, QComboBox) and not w.isEditable():
            for i in range(w.count()):
                w.setItemText(i, T(w.itemText(i)))
        if w.toolTip():
            w.setToolTip(T(w.toolTip()))
        if w.isWindow() and w.windowTitle():
            w.setWindowTitle(T(w.windowTitle()))
