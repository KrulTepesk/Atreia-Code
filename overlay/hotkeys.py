"""Teclas de atalho globais (funcionam com o jogo em foco). Só no Windows; nos outros sistemas não faz nada."""
import ctypes
import os

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.owner.pressed.emit(int(msg.wParam))
                return True, 0
        return False, 0


class Hotkeys(QObject):
    """hk = Hotkeys(app); hk.add(1, ['ctrl', 'alt'], 0x53); hk.pressed.connect(fn)  (tecla: VK ou letra)"""
    pressed = Signal(int)

    def __init__(self, app):
        super().__init__()
        self.ok = os.name == "nt"
        self.ids = []
        if self.ok:
            self._filter = _Filter(self)
            app.installNativeEventFilter(self._filter)

    def add(self, hid, mods, key):
        if not self.ok:
            return False
        m = MOD_NOREPEAT
        if "ctrl" in mods:
            m |= MOD_CONTROL
        if "alt" in mods:
            m |= MOD_ALT
        if "shift" in mods:
            m |= MOD_SHIFT
        vk = key if isinstance(key, int) else (ord(key.upper()) if len(key) == 1 else key)
        if ctypes.windll.user32.RegisterHotKey(None, hid, m, vk):
            self.ids.append(hid)
            return True
        return False  # outra janela já usa esse atalho

    def clear(self):
        if self.ok:
            for hid in self.ids:
                ctypes.windll.user32.UnregisterHotKey(None, hid)
        self.ids = []
