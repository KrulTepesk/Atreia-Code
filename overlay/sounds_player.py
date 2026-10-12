"""Toca .wav / .mp3 sem travar a interface, usando o tocador do próprio Windows (MCI / winmm).

Antes usava o QtMultimedia, que sozinho trazia dezenas de MB (FFmpeg) para o instalador só para
tocar um aviso curto. O MCI já vem no Windows, toca wav e mp3 e aceita volume.
"""
import itertools
import os
import threading

from config import resolve

_ids = itertools.count(1)


def _mci(cmd):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    return ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, None), buf.value


def _play_mci(path, volume):
    """Abre, toca e fecha tudo na mesma thread (o MCI prefere assim); se não abrir, cai no winsound."""
    alias = f"a2snd{next(_ids)}"

    def run():
        err, _ = _mci(f'open "{path}" type mpegvideo alias {alias}')
        if err:
            _winsound(path)
            return
        try:
            _mci(f"setaudio {alias} volume to {int(max(0, min(100, volume)) * 10)}")
            _mci(f"play {alias} wait")          # espera aqui; a interface não trava
        finally:
            _mci(f"close {alias}")

    threading.Thread(target=run, daemon=True).start()
    return True


def _winsound(path):
    try:  # reserva: só .wav, sem volume
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def play(path, volume=80):
    path = resolve(path)
    if not path or not os.path.isfile(path):
        return False
    if '"' in path or "\n" in path or "\r" in path:
        return False          # aspas/quebras quebrariam o comando do MCI (e poderiam virar outro comando)
    if os.name != "nt":
        return False
    try:
        return _play_mci(os.path.abspath(path), volume)
    except Exception:
        return _winsound(path)
