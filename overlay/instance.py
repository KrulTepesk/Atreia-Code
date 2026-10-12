"""Garante um Meta Overlay só aberto por vez.

- Uma trava do Windows ("mutex") marca que o programa está aberto (o instalador também olha ela).
- Quando ele roda como administrador (por causa do DPS Meter), uma cópia aberta sem administrador
  (atalho, "abrir com o Windows", o instalador depois de atualizar) recebia "acesso negado" ao olhar a
  trava e achava que não tinha nenhum aberto: ficavam 2 overlays. Agora a trava e os sinais são criados
  com uma permissão que qualquer cópia do mesmo usuário consegue ver, e "acesso negado" também conta
  como "já está aberto".
- Dois sinais deixam a cópia nova falar com a que já está aberta:
    * mostrar: abrir de novo pelo atalho só traz o painel da que já estava aberta;
    * fechar: reiniciar / trocar idioma / reabrir como administrador / atualizar (--replace) pede para a
      antiga fechar e espera ela sair antes de continuar.
"""
import os
import sys
import time

MUTEX = "Aion2OverlayMutex"                 # o mesmo nome de sempre (o instalador usa)
EV_QUIT = "Local\\MetaOverlayQuit"
EV_SHOW = "Local\\MetaOverlayShow"
# todos podem usar + rótulo de integridade baixo: uma cópia sem administrador consegue sinalizar a com
SDDL = "D:(A;;GA;;;WD)(A;;GA;;;SY)(A;;GA;;;BA)S:(ML;;NW;;;LW)"

ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000

_state = {"mutex": None, "quit": None, "show": None, "sa": None}


def _k32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.SetEvent.restype = wintypes.BOOL
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return ctypes, k


def _security_attributes():
    """SECURITY_ATTRIBUTES com a permissão do SDDL (ou None se não der: aí usa o padrão do Windows)."""
    if _state["sa"] is not None:
        return _state["sa"]
    try:
        import ctypes
        from ctypes import wintypes

        class SA(ctypes.Structure):
            _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", wintypes.BOOL)]

        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        f = adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
        f.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
        f.restype = wintypes.BOOL
        psd = ctypes.c_void_p()
        if not f(SDDL, 1, ctypes.byref(psd), None):
            return None
        sa = SA(ctypes.sizeof(SA), psd, False)
        _state["sa"] = sa                     # fica guardado: o Windows usa enquanto o programa vive
        return sa
    except Exception:
        return None


def _sa_ptr():
    import ctypes
    sa = _security_attributes()
    return ctypes.byref(sa) if sa is not None else None


def _try_lock():
    """True se esta cópia ficou com a trava; False se outra já tem."""
    ctypes, k = _k32()
    h = k.CreateMutexW(_sa_ptr(), False, MUTEX)
    err = ctypes.get_last_error()
    if h and err != ERROR_ALREADY_EXISTS:
        _state["mutex"] = h
        return True
    if h:
        k.CloseHandle(h)
    # ERROR_ACCESS_DENIED: existe, mas foi criada por uma cópia como administrador -> também está aberto
    return False


def _signal(name):
    """Acende o sinal da cópia que já está aberta. False se ela não tem esse sinal (versão antiga)."""
    try:
        _ctypes, k = _k32()
        h = k.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, name)
        if not h:
            return False
        ok = bool(k.SetEvent(h))
        k.CloseHandle(h)
        return ok
    except Exception:
        return False


def _kill_other_copies():
    """Último recurso (versão antiga, sem o sinal de fechar): encerra outras cópias do programa."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import psutil
        me = os.getpid()
        exe = os.path.basename(sys.executable).lower()
        for p in psutil.process_iter(["pid", "name"]):
            if p.info["pid"] != me and (p.info["name"] or "").lower() in (exe, "metaoverlay.exe",
                                                                         "atreiacode.exe", "aion2overlay.exe"):
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass


def acquire(replace=False, wait=12.0):
    """Chamado ao abrir. True = pode continuar abrindo.

    replace=False: já tem um aberto -> manda ele mostrar o painel e devolve False.
    replace=True: pede para o aberto fechar, espera ele sair e fica com a trava.
    """
    if os.name != "nt":
        return True
    try:
        if _try_lock():
            _make_events()
            return True
        if not replace:
            _state["shown"] = _signal(EV_SHOW)
            return False
        asked = _signal(EV_QUIT)
        end = time.time() + wait
        killed = False
        while time.time() < end:
            time.sleep(0.25)
            if _try_lock():
                _make_events()
                return True
            if not asked and not killed and time.time() > end - wait + 1.5:
                _kill_other_copies()
                killed = True
        return False
    except Exception:
        return True          # se o Windows não deixar nem testar, não impede o programa de abrir


def other_was_shown():
    return bool(_state.get("shown"))


def _make_events():
    _ctypes, k = _k32()
    for key, name in (("quit", EV_QUIT), ("show", EV_SHOW)):
        if not _state[key]:
            _state[key] = k.CreateEventW(_sa_ptr(), False, False, name) or None


def poll():
    """'quit', 'show' ou None (chamado por um QTimer)."""
    if os.name != "nt":
        return None
    try:
        _ctypes, k = _k32()
        for key in ("quit", "show"):
            h = _state[key]
            if h and k.WaitForSingleObject(h, 0) == 0:
                return key
    except Exception:
        pass
    return None


def release():
    """Solta a trava e os sinais (antes de abrir a cópia nova num reinício)."""
    if os.name != "nt":
        return
    try:
        _ctypes, k = _k32()
        for key in ("mutex", "quit", "show"):
            if _state[key]:
                k.CloseHandle(_state[key])
                _state[key] = None
    except Exception:
        pass
