"""Teclas de atalho configuráveis (aba Geral).

Cada ação tem um botão: clique, aperte a combinação e pronto. Ela funciona com o jogo em foco (atalho global
do Windows). Esc cancela; Backspace/Delete apaga o atalho daquela ação.
Letra/número sozinho não vale (atrapalharia digitar no chat do jogo): precisa de Ctrl, Alt ou Shift.
F1–F12 e afins podem ser sozinhos.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from config import cfg, save
from i18n import T

# ação -> (texto, atalho padrão (mods, vk, texto) ou None)
ACTIONS = [
    ("dps_reset", "Zerar o DPS Meter", (["ctrl", "alt"], 0x52, "Ctrl+Alt+R")),
    ("dps_toggle", "Mostrar / esconder o DPS Meter", (["ctrl", "alt"], 0x44, "Ctrl+Alt+D")),
    ("dps_view", "Alternar Luta / Sessão no DPS Meter", None),
    ("lock", "Travar / destravar os overlays", (["ctrl", "alt"], 0x4C, "Ctrl+Alt+L")),
    ("minimap", "Ligar / desligar os ícones no minimapa", None),
    ("map", "Abrir / fechar o mapa", None),
    ("panel", "Abrir o painel do Meta Overlay", None),
]
IDS = {name: 10 + i for i, (name, _t, _d) in enumerate(ACTIONS)}
NAMES = {v: k for k, v in IDS.items()}

# teclas que o Qt dá sem o código do Windows (fora do Windows / em testes): Qt.Key -> VK
_QT2VK = {Qt.Key_Home: 0x24, Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
          Qt.Key_Insert: 0x2D, Qt.Key_Delete: 0x2E, Qt.Key_Left: 0x25, Qt.Key_Up: 0x26,
          Qt.Key_Right: 0x27, Qt.Key_Down: 0x28, Qt.Key_Pause: 0x13, Qt.Key_ScrollLock: 0x91,
          Qt.Key_Space: 0x20}
_MODKEYS = {Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr}


def hk_cfg():
    c = cfg.setdefault("hotkeys", {})
    for name, _t, default in ACTIONS:
        if name not in c:
            c[name] = ({"mods": list(default[0]), "vk": default[1], "text": default[2]} if default else None)
    return c


def vk_from_event(e):
    """Código de tecla do Windows (VK) do evento, ou None se a tecla não serve para atalho."""
    k = e.key()
    if k in _MODKEYS or k == Qt.Key_unknown:
        return None
    vk = e.nativeVirtualKey() if hasattr(e, "nativeVirtualKey") else 0
    if vk and vk not in (0x10, 0x11, 0x12, 0x5B, 0x5C):    # Shift/Ctrl/Alt/Win sozinhos não
        return vk
    if Qt.Key_A <= k <= Qt.Key_Z or Qt.Key_0 <= k <= Qt.Key_9:
        return k                                           # mesmos códigos do VK para A-Z e 0-9
    if Qt.Key_F1 <= k <= Qt.Key_F24:
        return 0x70 + (k - Qt.Key_F1)
    return _QT2VK.get(k)


def mods_from_event(e):
    m = e.modifiers()
    out = []
    if m & Qt.ControlModifier:
        out.append("ctrl")
    if m & Qt.AltModifier:
        out.append("alt")
    if m & Qt.ShiftModifier:
        out.append("shift")
    return out


def needs_modifier(vk):
    """Letras, números, espaço e afins sozinhos atrapalham digitar no jogo."""
    return not (0x70 <= vk <= 0x87 or vk in (0x13, 0x91, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22))


def combo_text(e, mods):
    seq = QKeySequence(e.keyCombination()).toString(QKeySequence.NativeText) if hasattr(e, "keyCombination") else ""
    if seq:
        return seq
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}
    return "+".join([names[m] for m in mods] + [QKeySequence(e.key()).toString()])


class HotkeyButton(QPushButton):
    """Mostra o atalho; clicou, fica esperando a combinação."""
    chosen = Signal(object)          # {"mods", "vk", "text"} ou None (apagou)
    capturing = Signal(bool)

    def __init__(self, value):
        super().__init__()
        self.value = value
        self.listening = False
        self.setMinimumWidth(130)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self.start)
        self.refresh()

    def refresh(self):
        if self.listening:
            self.setText(T("Aperte as teclas…"))
        else:
            self.setText(self.value["text"] if self.value else T("(nenhum)"))

    def start(self):
        self.listening = True
        self.capturing.emit(True)
        self.refresh()
        self.setFocus()
        self.grabKeyboard()

    def stop(self):
        if self.listening:
            self.listening = False
            self.releaseKeyboard()
            self.capturing.emit(False)
            self.refresh()

    def focusOutEvent(self, e):
        self.stop()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self.listening:
            return super().keyPressEvent(e)
        k = e.key()
        if k == Qt.Key_Escape:
            self.stop()
            return
        if k in (Qt.Key_Backspace,) or (k == Qt.Key_Delete and not e.modifiers()):
            self.stop()
            self.chosen.emit(None)
            return
        if k in _MODKEYS:
            return                                    # espera a tecla de verdade
        vk = vk_from_event(e)
        mods = mods_from_event(e)
        if vk is None:
            self.setText(T("Tecla não aceita — tente outra"))
            return
        if not mods and needs_modifier(vk):
            self.setText(T("Use com Ctrl, Alt ou Shift"))
            return
        value = {"mods": mods, "vk": int(vk), "text": combo_text(e, mods)}
        self.stop()
        self.chosen.emit(value)


class HotkeysBox(QGroupBox):
    """Lista de ações com o botão de atalho de cada uma."""

    def __init__(self, on_changed, on_capturing):
        super().__init__("Teclas de atalho (funcionam dentro do jogo)")
        self.on_changed = on_changed
        lay = QVBoxLayout(self)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.buttons = {}
        self.status = {}
        c = hk_cfg()
        for i, (name, text, _d) in enumerate(ACTIONS):
            row = i * 2
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setObjectName("hkAction")         # texto normal (não o cinza das dicas)
            g.addWidget(lbl, row, 0)
            b = HotkeyButton(c.get(name))
            b.chosen.connect(lambda v, n=name: self.set_key(n, v))
            b.capturing.connect(on_capturing)
            g.addWidget(b, row, 1)
            clr = QPushButton("Limpar")
            clr.clicked.connect(lambda _=False, n=name: self.set_key(n, None))
            g.addWidget(clr, row, 2)
            st = QLabel("")                       # aviso numa linha só dele (não alarga a página)
            st.setStyleSheet("color:#f0883e;")
            st.setWordWrap(True)
            st.hide()
            g.addWidget(st, row + 1, 0, 1, 3)
            self.buttons[name] = b
            self.status[name] = st
        g.setColumnStretch(0, 1)
        lay.addLayout(g)
        hint = QLabel("Clique no atalho e aperte a combinação. Esc cancela, Backspace apaga. "
                      "Letra ou número precisa de Ctrl, Alt ou Shift; F1–F12 podem ser sozinhos.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch()
        rst = QPushButton("Restaurar padrões")
        rst.clicked.connect(self.reset_defaults)
        row.addWidget(rst)
        lay.addLayout(row)

    def _status(self, name, text):
        st = self.status[name]
        st.setText(text)
        st.setVisible(bool(text))

    def set_key(self, name, value):
        c = hk_cfg()
        if value:
            for other, v in c.items():
                if other != name and v and v["vk"] == value["vk"] and sorted(v["mods"]) == sorted(value["mods"]):
                    label = next(t for n, t, _d in ACTIONS if n == other)
                    self._status(name, T("Já usado em: {a}").format(a=T(label)))
                    self.buttons[name].refresh()
                    return
        c[name] = value
        save()
        self.buttons[name].value = value
        self.buttons[name].refresh()
        self._status(name, "")
        self.on_changed()

    def reset_defaults(self):
        c = hk_cfg()
        for name, _t, default in ACTIONS:
            c[name] = {"mods": list(default[0]), "vk": default[1], "text": default[2]} if default else None
            self.buttons[name].value = c[name]
            self.buttons[name].refresh()
            self._status(name, "")
        save()
        self.on_changed()

    def show_failed(self, failed):
        """Ações cujo atalho o Windows recusou (outro programa já usa)."""
        for name, st in self.status.items():
            if name in failed:
                self._status(name, T("Em uso por outro programa"))
            elif st.text() == T("Em uso por outro programa"):
                self._status(name, "")
