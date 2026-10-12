"""PvP: toca um som quando a notificação de abate aparece na tela.

Funciona só olhando a tela (igual a um programa de gravação): tira prints de uma
área escolhida e compara com uma imagem de referência da mensagem de abate.
Não lê memória, pacotes nem arquivos do jogo.
"""
import os
import time

import cv2
import mss
import numpy as np
from PySide6.QtCore import QPoint, QRect, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)

import sounds_player
from base_window import OverlayWindow
from i18n import T, translate_tree
from config import APP_DIR, cfg, save

REF_PATH = os.path.join(APP_DIR, "pvp_referencia.png")


# ------------------------------------------------------------------ detector
class KillWatcher(QThread):
    kill = Signal(float)
    score = Signal(float)
    error = Signal(str)

    def __init__(self, section="pvp"):
        super().__init__()
        self.section = section
        self._run = True

    def stop(self):
        self._run = False
        self.wait(2000)

    def run(self):
        c = cfg[self.section]
        # imdecode em vez de imread: o imread do OpenCV não abre caminhos com acento no Windows
        # (ex.: C:\\Users\\João\\...), que é onde a referência fica guardada
        ref = None
        path = c.get("reference") or ""
        if path and os.path.exists(path):
            try:
                ref = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            except Exception:
                ref = None
        if ref is None:
            self.error.emit("Sem imagem de referência")
            return
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                region = c.get("region")
                if region:
                    box = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
                else:
                    idx = c.get("monitor", 1)
                    box = mons[idx] if 0 < idx < len(mons) else mons[1]
                if box["width"] < ref.shape[1] or box["height"] < ref.shape[0]:
                    self.error.emit("Área menor que a referência")
                    return
                # área grande (ex.: monitor inteiro): compara em meia resolução, ~6x menos CPU
                half = box["width"] * box["height"] > 900 * 600 and min(ref.shape) >= 24
                if half:
                    ref = cv2.resize(ref, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                armed = True
                last = 0.0
                while self._run:
                    t0 = time.time()
                    try:
                        shot = np.asarray(sct.grab(box))
                    except Exception:
                        time.sleep(1.0)          # tela bloqueada / resolução mudou: tenta de novo
                        continue
                    gray = cv2.cvtColor(shot, cv2.COLOR_BGRA2GRAY)
                    if half:
                        gray = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                    res = cv2.matchTemplate(gray, ref, cv2.TM_CCOEFF_NORMED)
                    best = float(res.max())
                    self.score.emit(best)
                    thr = float(c.get("threshold", 0.8))
                    if best >= thr:
                        # 'armed' evita contar 2x a mesma mensagem que fica parada na tela
                        if armed and t0 - last >= float(c.get("cooldown", 3.0)):
                            last = t0
                            armed = False
                            self.kill.emit(best)
                    elif best < thr - 0.10:
                        armed = True
                    wait = int(c.get("interval_ms", 250)) / 1000 - (time.time() - t0)
                    if wait > 0:
                        time.sleep(wait)
        except Exception as e:
            self.error.emit(str(e))


# ------------------------------------------------------------------ widget
class PvpWidget(OverlayWindow):
    def __init__(self):
        super().__init__("pvp", QPoint(40, 230))
        self.watcher = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 10)
        lay.setSpacing(0)
        t = QLabel("PVP")
        t.setStyleSheet("color:#ff5a6a; font-weight:700; letter-spacing:1px;")
        t.setFont(QFont("Segoe UI", 9))
        self.count = QLabel("0")
        self.count.setFont(QFont("Segoe UI", 22, QFont.Bold))
        self.count.setStyleSheet("color:white;")
        self.status = QLabel("")
        self.status.setStyleSheet("color:#b3aa98;")
        self.status.setFont(QFont("Segoe UI", 9))
        for w in (t, self.count, self.status):
            w.setAlignment(Qt.AlignCenter)
            lay.addWidget(w)
        self.setFixedSize(190, 92)
        self.refresh()

    def refresh(self):
        self.count.setText(f"{cfg['pvp'].get('kills', 0)} abates")
        if self.watcher and self.watcher.isRunning():
            self.status.setText("Monitorando")
        elif not cfg["pvp"].get("reference"):
            self.status.setText("Configure a referência")
        else:
            self.status.setText("Desligado")

    def start(self):
        self.stop()
        if not cfg["pvp"].get("reference") or not os.path.exists(cfg["pvp"]["reference"]):
            self.refresh()
            return False
        self.watcher = KillWatcher()
        self.watcher.kill.connect(self.on_kill)
        self.watcher.error.connect(self.on_error)
        self.watcher.finished.connect(self.refresh)
        self.watcher.start()
        self.refresh()
        return True

    def stop(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self.refresh()

    def on_kill(self, _score):
        c = cfg["pvp"]
        c["kills"] = c.get("kills", 0) + 1
        save()
        sounds_player.play(c.get("sound"), c.get("volume", 80))
        self._accent = QColor("#ff5a6a")
        self.refresh()
        self.update()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._clear_accent)

    def _clear_accent(self):
        self._accent = QColor(0, 0, 0, 0)
        self.update()

    def on_error(self, msg):
        self.status.setText(msg[:28])

    def reset_kills(self):
        cfg["pvp"]["kills"] = 0
        save()
        self.refresh()


# ------------------------------------------------------------------ recortar referência
class CropView(QGraphicsView):
    def __init__(self, image):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.pix = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.scene().addItem(self.pix)
        self.rect_item = QGraphicsRectItem()
        self.rect_item.setPen(QPen(QColor("#ff5a6a"), 0))
        self.rect_item.setBrush(QColor(255, 90, 106, 50))
        self.scene().addItem(self.rect_item)
        self._start = None
        self.selection = QRect()
        self.setDragMode(QGraphicsView.NoDrag)
        self.setBackgroundBrush(QColor(20, 20, 24))

    def showEvent(self, e):
        self.fitInView(self.pix, Qt.KeepAspectRatio)
        super().showEvent(e)

    def wheelEvent(self, e):
        f = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._start = self.mapToScene(e.position().toPoint())
        elif e.button() == Qt.RightButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._start is not None:
            cur = self.mapToScene(e.position().toPoint())
            r = QRect(self._start.toPoint(), cur.toPoint()).normalized()
            r = r.intersected(self.pix.pixmap().rect())
            self.selection = r
            self.rect_item.setRect(r)
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._start = None
        self.setDragMode(QGraphicsView.NoDrag)
        super().mouseReleaseEvent(e)


class ReferenceDialog(QDialog):
    """Abre um print (arquivo ou área de transferência) e deixa recortar a mensagem de abate."""

    def __init__(self, parent=None, section="pvp", ref_path=REF_PATH, what="mensagem de abate",
                 hint="sem o nome do inimigo"):
        super().__init__(parent)
        self.section, self.ref_path = section, ref_path
        self.setWindowTitle(f"Referência — recorte a {what}")
        self.resize(1100, 700)
        self.image = None
        lay = QVBoxLayout(self)
        tip = QLabel("1) Tire um print do jogo no momento do abate (Win+Shift+S, PrintScreen ou F12 da Steam).  "
                     f"2) Abra o print aqui.  3) Arraste com o botão esquerdo em volta da {what} "
                     f"(só o texto/ícone fixo, {hint}).  Roda do mouse = zoom, botão direito = mover.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        row = QHBoxLayout()
        b1 = QPushButton("Abrir print...")
        b1.clicked.connect(self.open_file)
        b2 = QPushButton("Colar da área de transferência")
        b2.clicked.connect(self.paste)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        lay.addLayout(row)
        self.holder = QVBoxLayout()
        self.placeholder = QLabel("Nenhuma imagem aberta")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.holder.addWidget(self.placeholder, 1)
        lay.addLayout(self.holder, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save_ref)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.view = None
        translate_tree(self)

    def set_image(self, img):
        if img is None or img.isNull():
            QMessageBox.warning(self, "Referência", "Não consegui abrir essa imagem.")
            return
        self.image = img.convertToFormat(QImage.Format_RGB32)
        if self.view:
            self.view.setParent(None)
        self.placeholder.hide()
        self.view = CropView(self.image)
        self.holder.addWidget(self.view, 1)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir print", "", "Imagens (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.set_image(QImage(path))

    def paste(self):
        self.set_image(QGuiApplication.clipboard().image())

    def save_ref(self):
        if not self.view or self.view.selection.width() < 8 or self.view.selection.height() < 8:
            QMessageBox.warning(self, "Referência", "Selecione a mensagem arrastando o mouse.")
            return
        self.image.copy(self.view.selection).save(self.ref_path)
        cfg[self.section]["reference"] = self.ref_path
        save()
        self.accept()


# ------------------------------------------------------------------ escolher área da tela
class RegionSelector(QWidget):
    """Tela escura por cima de um monitor; arraste para marcar onde a mensagem aparece."""
    chosen = Signal(list)

    def __init__(self, screen):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(screen.geometry())
        self._a = self._b = None
        self.hint_text = "Arraste em volta da área onde aparece a mensagem  (Esc cancela)"
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                   T(self.hint_text))
        if self._a and self._b:
            r = QRect(self._a, self._b).normalized()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(r, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor("#ff5a6a"), 2))
            p.drawRect(r)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    def mousePressEvent(self, e):
        self._a = self._b = e.position().toPoint()

    def mouseMoveEvent(self, e):
        self._b = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e):
        r = QRect(self._a, e.position().toPoint()).normalized()
        self.close()
        if r.width() > 20 and r.height() > 10:
            g = self.geometry()
            self.chosen.emit([g.x() + r.x(), g.y() + r.y(), r.width(), r.height()])
