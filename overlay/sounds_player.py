"""Toca .wav / .mp3 / .ogg sem travar a interface."""
import os

from config import resolve

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:  # instalação sem o módulo de multimídia: usa o winsound (só .wav)
    QMediaPlayer = None

_active = []


def play(path, volume=80):
    path = resolve(path)
    if not path or not os.path.exists(path):
        return False
    if QMediaPlayer is None:
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        except Exception:
            return False
    player = QMediaPlayer()
    out = QAudioOutput()
    out.setVolume(max(0.0, min(1.0, volume / 100)))
    player.setAudioOutput(out)
    player.setSource(QUrl.fromLocalFile(path))
    pair = (player, out)
    _active.append(pair)

    def done(status):
        if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.InvalidMedia) and pair in _active:
            _active.remove(pair)
            player.deleteLater()

    player.mediaStatusChanged.connect(done)
    player.play()
    return True
