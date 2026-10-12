"""Mapa sobre o minimapa do jogo (Alt+M).

O usuário marca a área da tela onde fica o minimapa. O programa tira prints dessa
área (como o OBS), reconhece qual parte do mapa está aparecendo comparando com a
imagem de fundo do mapa (reconhecimento por pontos característicos, SIFT) e desenha
os recursos por cima, numa janela transparente. O clique atravessa tudo, menos os ícones:
clique esquerdo num ícone = coletei (timer de renascimento de 5 min); clique direito = cancela.
Só funciona nos mapas que têm imagem de fundo.
"""
import os
import time

import cv2
import mss
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from config import CATEGORIES, cfg
from i18n import N, T

FEAT_SCALE = 0.35          # o fundo é reduzido para esse fator antes de extrair os pontos


def mm_cfg():
    c = cfg.setdefault("minimap", {})
    for k, v in {"enabled": False, "region": None, "fps": 4, "dot_size": 7, "icon_size": 18,
                 "show_farm": True, "show_collect": True, "clickable": True}.items():
        c.setdefault(k, v)
    return c


class Matcher:
    """Pontos característicos de cada mapa com fundo; acha onde está um recorte do minimapa."""

    def __init__(self):
        self.maps = {}      # wid -> (kp_xy, descriptors, flann, bg_x, bg_y, bg_scale)
        self.sift = cv2.SIFT_create(nfeatures=30000)

    def build(self, backgrounds):
        """backgrounds: {wid: (path, x, y, scale)}"""
        for wid, (path, bx, by, bs) in backgrounds.items():
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            small = cv2.resize(img, None, fx=FEAT_SCALE, fy=FEAT_SCALE, interpolation=cv2.INTER_AREA)
            kp, des = self.sift.detectAndCompute(small, None)
            if des is None:
                continue
            fl = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=40))
            fl.add([des])
            fl.train()
            xy = np.float32([k.pt for k in kp]) / FEAT_SCALE   # em pixels da imagem de fundo original
            self.maps[wid] = (xy, fl, bx, by, bs)

    def locate(self, gray, prefer=None, mask=None):
        """Retorna (wid, A, inliers): A leva pixel do minimapa -> coordenada de cena (x, -y do mundo).
        mask: áreas com 0 são ignoradas (onde o próprio overlay desenhou ícones)."""
        kp, des = self.sift.detectAndCompute(gray, mask)
        if des is None or len(kp) < 12:
            return None
        order = sorted(self.maps, key=lambda w: w != prefer)
        best = None
        for wid in order:
            xy, fl, bx, by, bs = self.maps[wid]
            ms = fl.knnMatch(des, k=2)
            good = [m[0] for m in ms if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
            if len(good) < 10:
                continue
            p1 = np.float32([kp[m.queryIdx].pt for m in good])
            p2 = xy[[m.trainIdx for m in good]] * bs + np.float32([bx, by])   # -> cena
            A, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=4 * bs)
            if A is None:
                continue
            n = int(inl.sum())
            if n >= 12 and (best is None or n > best[2]):
                best = (wid, A, n)
                if n >= 40:
                    break
        return best


class MinimapWorker(QThread):
    located = Signal(object)        # (wid, A, inliers) ou None
    status = Signal(str)

    marks = []      # [(x, y, raio)] dos ícones desenhados pelo overlay (atualizado a cada desenho)

    def __init__(self, backgrounds, prefer):
        super().__init__()
        self.backgrounds, self.prefer = backgrounds, prefer
        self._run = True

    def stop(self):
        self._run = False
        self.wait(3000)

    def run(self):
        self.status.emit(T("Preparando o reconhecimento do mapa..."))
        m = Matcher()
        m.build(self.backgrounds)
        if not m.maps:
            self.status.emit(T("Nenhum mapa com imagem de fundo para comparar."))
            return
        c = mm_cfg()
        r = c["region"]
        box = {"left": r[0], "top": r[1], "width": r[2], "height": r[3]}
        self.status.emit(T("Procurando..."))
        with mss.mss() as sct:
            fails = 0
            while self._run:
                t0 = time.time()
                try:
                    shot = np.asarray(sct.grab(box))
                    fails = 0
                except Exception:
                    # tela bloqueada, mudança de resolução, monitor desligado...: espera e tenta de novo
                    fails += 1
                    if fails == 3:
                        self.status.emit(T("Não deu para ler a tela agora; tentando de novo..."))
                    self.located.emit(None)
                    time.sleep(1.0)
                    continue
                gray = cv2.cvtColor(shot, cv2.COLOR_BGRA2GRAY)
                # o print inclui os ícones que o overlay desenhou: tapa esses pontos para não confundir
                mask = None
                marks = self.marks
                if marks:
                    mask = np.full(gray.shape, 255, np.uint8)
                    for mx, my, mr in marks:
                        cv2.circle(mask, (int(mx), int(my)), int(mr), 0, -1)
                        cv2.rectangle(mask, (int(mx - 26), int(my + mr - 4)), (int(mx + 26), int(my + mr + 16)), 0, -1)
                try:
                    res = m.locate(gray, self.prefer, mask)
                except Exception as e:
                    self.status.emit(str(e))
                    res = None
                if res:
                    self.prefer = res[0]
                self.located.emit(res)
                wait = 1 / max(1, c.get("fps", 4)) - (time.time() - t0)
                if wait > 0:
                    time.sleep(wait)


def exclude_from_capture(widget):
    """Tira a janela dos prints de tela (Windows 10 2004+). Sem isso, os ícones que o overlay desenha
    entram no print do minimapa e atrapalham o reconhecimento do lugar."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        WDA_EXCLUDEFROMCAPTURE = 0x11
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


class MinimapOverlay(QWidget):
    """Janela transparente exatamente por cima do minimapa; desenha os recursos.

    Só os pixels desenhados (os ícones) recebem clique; o resto da janela é 100% transparente e o
    Windows manda o clique direto para o jogo.
    """

    def __init__(self, get_points):
        super().__init__(None)
        self.get_points = get_points      # fn(wid) -> [(tipo, chave, material, categoria, cor, x, y)]
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        if not mm_cfg().get("clickable", True):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.A = None
        self.wid = None
        self.last_ok = 0
        self.hits = []                    # [(chave, px, py)] dos ícones visíveis, para o clique
        self.capture_safe = True
        self.marks = []
        self.on_marks = None              # avisa o reconhecimento onde estão os ícones desenhados
        self.tick = QTimer(self)          # redesenha a contagem mesmo se o reconhecimento pausar
        self.tick.timeout.connect(self.update)
        self.tick.start(1000)

    def showEvent(self, e):
        super().showEvent(e)
        # não usa SetWindowDisplayAffinity: em alguns PCs ela some com a janela transparente da tela.
        # O reconhecimento ignora os pontos onde o overlay desenhou (máscara no MinimapWorker).

    def set_clickable(self, on):
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, not on)
        if vis:
            self.show()

    def place(self):
        r = mm_cfg()["region"]
        if r:
            self.setGeometry(r[0], r[1], r[2], r[3])

    def update_pose(self, res):
        if res:
            self.wid, A, _n = res
            self.A = cv2.invertAffineTransform(A)      # cena -> pixel do minimapa
            self.last_ok = time.time()
        self.update()

    def paintEvent(self, e):
        self.hits = []
        if self.A is None or time.time() - self.last_ok > 3:
            return
        import icons
        import respawn
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        A = self.A
        w, h = self.width(), self.height()
        c = mm_cfg()
        isize = c.get("icon_size", 18)
        dot = c.get("dot_size", 7) / 2
        total = respawn.total()
        timed = []
        for kind, key, mat, cat, col, x, y in self.get_points(self.wid):
            sx, sy = x, -y
            px = A[0, 0] * sx + A[0, 1] * sy + A[0, 2]
            py = A[1, 0] * sx + A[1, 1] * sy + A[1, 2]
            if not (-isize <= px <= w + isize and -isize <= py <= h + isize):
                continue
            if kind == "farm":
                p.setPen(QPen(QColor(255, 255, 255, 230), 1.3))
                p.setBrush(col)
                p.drawEllipse(QPointF(px, py), dot, dot)
                continue
            left = respawn.remaining(key)
            if left:
                timed.append((px, py, mat, col, left))     # desenhados por último, por cima
            elif not self.capture_safe:
                p.setPen(QPen(QColor(255, 255, 255, 230), 1.3))
                p.setBrush(col)
                p.drawEllipse(QPointF(px, py), dot, dot)
            else:
                icons.draw_resource(p, QPointF(px, py), icons.material(mat, isize), isize, None, total,
                                    fallback=col.name())
            self.hits.append((key, px, py))
        for px, py, mat, col, left in timed:
            icons.draw_resource(p, QPointF(px, py), icons.material(mat, isize), isize, left, total,
                                fallback=col.name())
        p.end()
        r = isize / 2 + 5
        self.marks = [(px, py, r) for _k, px, py in self.hits]
        if self.on_marks:
            self.on_marks(self.marks)

    def _hit(self, pos):
        import respawn
        r = mm_cfg().get("icon_size", 18) / 2 + 3
        # o que está por cima (com timer) ganha o clique
        for key, px, py in self.hits:
            if respawn.remaining(key) and (px - pos.x()) ** 2 + (py - pos.y()) ** 2 <= r * r:
                return key
        best = None
        for key, px, py in self.hits:
            d = (px - pos.x()) ** 2 + (py - pos.y()) ** 2
            if d <= r * r and (best is None or d < best[0]):
                best = (d, key)
        return best[1] if best else None

    def mousePressEvent(self, e):
        import respawn
        key = self._hit(e.position())
        if key is None:
            return
        if e.button() == Qt.LeftButton:
            if respawn.remaining(key) is None:
                respawn.start(key)
        elif e.button() == Qt.RightButton:
            respawn.cancel(key)
        self.update()


# ====================================================================== controle (liga/desliga, dados)
def backgrounds_available():
    """{wid: (caminho, x, y, escala)} de todos os mapas com imagem de fundo."""
    import json as _json
    from config import BASE_DIR, resolve
    out = {}
    try:
        with open(os.path.join(BASE_DIR, "fundos", "presets.json"), encoding="utf-8") as f:
            presets = _json.load(f)
    except OSError:
        presets = {}
    user = cfg.get("map", {}).get("backgrounds", {})
    for wid in set(presets) | set(user):
        b = user.get(wid) or presets.get(wid)
        if b and b.get("path") and os.path.exists(resolve(b["path"])):
            out[wid] = (resolve(b["path"]), b["x"], b["y"], b["scale"])
    return out


class MinimapController:
    def __init__(self):
        from farm import _resources
        self.res = _resources()
        self.colors = {k: QColor(c) for k, _n, c in CATEGORIES}
        self.overlay = MinimapOverlay(self.points)
        self.worker = None
        self.on_status = lambda s: None
        self.last_region = ""

    def points(self, wid):
        w = self.res["worlds"].get(wid)
        if not w:
            return []
        m = cfg.get("map", {})
        c = mm_cfg()
        out = []
        if c.get("show_collect", True):
            filters = m.get("filters", {})
            mat = m.get("material", "")
            hide = m.get("hide_collected", False)
            collected = set(m.get("collected", [])) if hide else set()
            names = self.res["names"]
            for cat, ni, x, y, _reg in w["points"]:
                if not filters.get(cat, True) or (mat and names[ni] != mat):
                    continue
                key = f"{wid}:{x}:{y}:{cat}"
                if hide and key in collected:
                    continue
                out.append(("res", key, names[ni], cat, self.colors[cat], x, y))
        f = cfg.get("farm", {})
        if c.get("show_farm", True) and f.get("active") and f.get("world") == wid:
            red = QColor("#ff4d5e")
            co = f.get("coords", [])
            out += [("farm", None, None, None, red, co[i], co[i + 1]) for i in range(0, len(co), 2)]
        return out

    def start(self):
        self.stop()
        c = mm_cfg()
        if not c.get("region"):
            self.on_status(T("Marque primeiro a área do minimapa."))
            return False
        bgs = backgrounds_available()
        if not bgs:
            self.on_status(T("Nenhum mapa tem imagem de fundo ainda."))
            return False
        self.overlay.place()
        self.overlay.show()
        self.worker = MinimapWorker(bgs, cfg.get("map", {}).get("world"))
        w = self.worker
        self.overlay.on_marks = lambda marks: setattr(w, "marks", marks)
        self.worker.located.connect(self._located)
        self.worker.status.connect(self.on_status)
        self.worker.start()
        return True

    def _located(self, res):
        self.overlay.update_pose(res)
        if res:
            wid, A, n = res
            cx, cy = A @ np.array([self.overlay.width() / 2, self.overlay.height() / 2, 1])
            k = len(self.overlay.hits)
            txt = T("Localizado: {r} ({n} pontos)").format(r=N(self.region_at(wid, cx, -cy)), n=n)
            txt += " · " + (T("{k} recursos desenhados").format(k=k) if k else
                            T("nenhum recurso nesta parte — confira os filtros do mapa"))
            self.on_status(txt)
        elif time.time() - self.overlay.last_ok > 3:
            self.on_status(T("Procurando... (abra o mapa com Alt+M)"))

    def region_at(self, wid, x, y):
        return self._region_name(wid, x, y)

    def _region_name(self, wid, x, y):
        from PySide6.QtGui import QPainterPath, QPolygonF
        w = self.res["worlds"].get(wid, {})
        best = None
        for r in w.get("regions", []):
            for poly in r["p"]:
                path = QPainterPath()
                path.addPolygon(QPolygonF([QPointF(a, b) for a, b in poly]))
                if path.contains(QPointF(x, y)) and (best is None or r["r"] > best[0]):
                    best = (r["r"], r["n"])
        return best[1] if best else w.get("name", "")

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.overlay.hide()
