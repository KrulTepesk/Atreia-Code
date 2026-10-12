"""Meta Overlay — painel de controle, ícone na bandeja e janelas de overlay."""
import os
import sys

# Coordenadas em pixels reais (necessário para a captura de tela do PvP bater com a posição na tela)
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QSystemTrayIcon, QTabWidget,
                               QVBoxLayout, QWidget)

import config
import i18n
import minimap
from i18n import T
import theme
import sounds_player
from config import cfg, save
from dps_capture import DpsTab
from events import EventScheduler, EventsTab
from farm import FarmTab
from field_bosses import FieldBossManager, FieldBossTab
from net_hub import NetHub
from hotkeys import Hotkeys
from map_window import MapWindow
from pvp import PvpWidget, ReferenceDialog, RegionSelector
from shugo import ShugoWidget


def make_icon():
    path = os.path.join(config.BASE_DIR, "icon.png")
    if os.path.exists(path):
        return QIcon(path)
    return QIcon(theme.app_icon_pixmap(64))


def screen_names():
    out = []
    for i, s in enumerate(QGuiApplication.screens(), 1):
        g = s.geometry()
        prim = T(" (principal)") if s == QGuiApplication.primaryScreen() else ""
        out.append((f"Monitor {i}{prim} — {g.width()}x{g.height()}", s))
    return out


class SoundRow(QWidget):
    """Escolher arquivo de som + volume + testar."""

    def __init__(self, section):
        super().__init__()
        self.section = section
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setMinimumWidth(160)
        pick = QPushButton("Escolher som...")
        pick.clicked.connect(self.pick)
        default = QPushButton("Padrão")
        default.clicked.connect(self.reset)
        test = QPushButton("▶ Testar")
        test.clicked.connect(lambda: sounds_player.play(cfg[section]["sound"], cfg[section]["volume"]))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(cfg[section].get("volume", 80))
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(self.set_vol)
        for w in (self.label, pick, default, test, QLabel("Volume"), self.vol):
            lay.addWidget(w)
        self.refresh()

    def refresh(self):
        self.label.setText(os.path.basename(cfg[self.section].get("sound") or "(nenhum)"))

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher som", "", "Áudio (*.wav *.mp3 *.ogg)")
        if path:
            cfg[self.section]["sound"] = path
            save()
            self.refresh()

    def reset(self):
        cfg[self.section]["sound"] = config.DEFAULTS[self.section]["sound"]
        save()
        self.refresh()

    def set_vol(self, v):
        cfg[self.section]["volume"] = v
        save()


class ControlPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Meta Overlay")
        self.setWindowIcon(make_icon())
        self.resize(960, 680)

        self.shugo = ShugoWidget()
        self.pvp = PvpWidget()
        self.map = None
        self.selector = None

        self.minimap = minimap.MinimapController()
        self.hub = NetHub()                 # leitura do jogo dividida entre DPS, farm e chefes de campo
        self._lock_icons = {False: theme.glyph_icon("unlock"), True: theme.glyph_icon("lock")}
        tabs = self.tabs = theme.NavTabs("Meta Overlay", "Ferramentas para Aion 2")
        tabs.addTab(self.tab_general(), "Geral", "general", "Idioma, monitores e trava dos overlays.")
        tabs.addTab(self.tab_shugo(), "Shugo", "shugo", "Aviso antes do Festival do Shugo começar.")
        tabs.addTab(self.tab_pvp(), "PvP", "pvp", "Toca um som quando você derrota alguém.")
        tabs.addTab(self.tab_map(), "Mapa", "map", "Coletáveis, mobs e o minimapa do Alt+M com os recursos por cima.")
        self.dps_tab = DpsTab(self.hub)
        self.farm_tab = FarmTab(self)
        tabs.addTab(self.farm_tab, "Farm de pet", "farm", "Conta sozinho os seus abates e mostra os mobs de pet onde você está.")
        self.events = EventScheduler()
        tabs.insertTab(2, EventsTab(self.events, SoundRow), "Rifts e chefes", "rifts",
                       "Avisos 5 minutos antes e na hora das fendas e dos chefes do mundo.")
        self.field_bosses = FieldBossManager(self.events, self.hub)
        tabs.insertTab(3, FieldBossTab(self.field_bosses), "Chefes de campo", "crown",
                       "Quando cada field boss renasce, com aviso e mapa do local.")
        tabs.addTab(self.dps_tab, "DPS (experimental)", "dps", "Medidor de dano seu e do seu grupo, lido do tráfego do jogo.")
        # trava dos overlays sempre à mão, no rodapé do menu
        self.lock_pill = QPushButton()
        self.lock_pill.setObjectName("LockPill")
        self.lock_pill.setCheckable(True)
        self.lock_pill.setCursor(Qt.PointingHandCursor)
        self.lock_pill.setIconSize(QSize(18, 18))
        self.lock_pill.clicked.connect(lambda on: self.lock.setChecked(on))
        tabs.add_footer(self.lock_pill)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(tabs)

        i18n.translate_tree(self)
        theme.polish(self)
        self.refresh_lock_pill()
        self.minimap.on_status = self.mm_status.setText
        if minimap.mm_cfg()["enabled"]:
            self.set_minimap(True)

        # o PvP não tem painel na tela: só toca o som (o detector roda escondido)
        # o Shugo não fica na tela: o aviso aparece sozinho 5 e 1 minuto antes
        self.shugo.restore_position()
        self.shugo.set_locked(cfg.get("locked", False))
        self.events.set_locked(cfg.get("locked", False))
        if cfg["pvp"].get("enabled"):
            self.set_pvp(True)

        self.tray = QSystemTrayIcon(make_icon(), self)
        menu = QMenu()
        for text, fn in (("Painel", self.show_panel), ("Mapa de coletáveis", self.open_map),
                         ("Travar / destravar overlays", self.toggle_lock), ("Sair", self.quit)):
            a = QAction(T(text), menu)
            a.triggered.connect(fn)
            menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_panel() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.setToolTip("Meta Overlay")
        self.tray.show()

        # atalho global: zerar DPS (Ctrl+Alt+R)
        self.hotkeys = Hotkeys(app)
        self._hk_wanted = {10: ("ctrl+alt", "R")}
        self._hk_tries = 0
        self._hk_base = self.hk_label.text()
        self.register_hotkeys()
        self.hotkeys.pressed.connect(lambda hid: self.dps_tab.reset_fight() if hid == 10 else None)

    def register_hotkeys(self):
        """Registra os atalhos que faltam. Se outro programa (ou a cópia anterior do próprio app que ainda está
        fechando, ex.: depois de "Reiniciar") estiver usando, tenta de novo a cada 2 s por até 30 s."""
        if not self.hotkeys.ok:
            return
        failed = []
        for hid, (mods, k) in self._hk_wanted.items():
            if hid in self.hotkeys.ids:
                continue
            if not self.hotkeys.add(hid, mods, k):
                failed.append(f"Ctrl+Alt+{k}")
        lbl = self.hk_label
        if failed:
            self._hk_tries += 1
            msg = T("Em uso por outro programa: {k}").format(k=", ".join(failed))
            if self._hk_tries < 15:
                msg += " " + T("(tentando de novo...)")
                QTimer.singleShot(2000, self.register_hotkeys)
            lbl.setText(self._hk_base + f"<br><span style='color:#f0883e'>{msg}</span>")
        else:
            lbl.setText(self._hk_base)

    # ------------------------------------------------------------------ abas
    def tab_general(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lock = QCheckBox("Travar overlays (o clique passa direto para o jogo)")
        self.lock.setChecked(cfg.get("locked", False))
        self.lock.toggled.connect(self.set_lock)
        lay.addWidget(self.lock)
        lay.addWidget(QLabel("Destravado: arraste os painéis com o mouse para qualquer lugar, inclusive outro monitor."))

        box_l = QGroupBox("Idioma")
        fl = QFormLayout(box_l)
        self.lang = QComboBox()
        for code, name in i18n.LANGS:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(i18n.lang())))
        self.lang.currentIndexChanged.connect(self.lang_changed)
        fl.addRow("Idioma:", self.lang)
        rowl = QHBoxLayout()
        self.lang_note = QLabel("O idioma muda depois de reiniciar o programa.")
        self.lang_note.setStyleSheet("color:#9b9282;")
        self.btn_restart = QPushButton("Reiniciar agora")
        self.btn_restart.clicked.connect(self.restart)
        self.btn_restart.hide()
        rowl.addWidget(self.lang_note)
        rowl.addStretch()
        rowl.addWidget(self.btn_restart)
        fl.addRow(rowl)
        lay.addWidget(box_l)

        box = QGroupBox("Mandar para outro monitor")
        f = QFormLayout(box)
        self.screens = QComboBox()
        for name, s in screen_names():
            self.screens.addItem(name, s)
        f.addRow("Monitor:", self.screens)
        row = QHBoxLayout()
        for text, target in (("Aviso do Shugo", lambda: self.shugo), ("Avisos de rifts/chefes", lambda: self.events.toast),
                             ("Mini-mapa dos chefes", lambda: self.events.popup), ("Card do farm", lambda: self.farm_tab.card),
                             ("Medidor de DPS", lambda: self.dps_tab.meter),
                             ("Mapa", self.get_map),
                             ("Todos", None)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, t=target: self.send_to_screen(t))
            row.addWidget(b)
        f.addRow("Mover:", row)
        lay.addWidget(box)

        self.hk_label = QLabel("Atalho (funciona dentro do jogo): Ctrl+Alt+R = zerar o medidor de DPS")
        self.hk_label.setWordWrap(True)
        self.hk_label.setStyleSheet("color:#9b9282;")
        lay.addWidget(self.hk_label)
        lay.addStretch()
        lay.addWidget(QLabel("Fechar esta janela não fecha o overlay — ele fica no ícone da bandeja."))
        return w

    def tab_shugo(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("O Festival Shugo começa toda hora cheia (horário do servidor). Nada fica fixo na tela: "
                       "um aviso aparece com som nos minutos escolhidos e some sozinho (duplo clique fecha antes).")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        box = QGroupBox("Quando avisar")
        f = QFormLayout(box)
        alerts = cfg["shugo"].setdefault("alerts", [5, 1])
        for i, label in enumerate(("Primeiro aviso:", "Segundo aviso:")):
            sp = QSpinBox()
            sp.setRange(0, 30)
            sp.setSuffix(" min antes")
            sp.setSpecialValueText("desligado")
            sp.setValue(alerts[i] if i < len(alerts) else 0)
            sp.valueChanged.connect(lambda v, i=i: self.set_alert(i, v))
            f.addRow(label, sp)
        off = QSpinBox()
        off.setRange(-59, 59)
        off.setSuffix(" min")
        off.setValue(cfg["shugo"].get("offset_minutes", 0))
        off.valueChanged.connect(lambda v: (cfg["shugo"].__setitem__("offset_minutes", v), save()))
        f.addRow("Ajuste de relógio:", off)
        f.addRow(QLabel("Deixe 0, a não ser que o festival comece fora do minuto :00 no seu relógio."))
        lay.addWidget(box)

        box2 = QGroupBox("Como o aviso aparece")
        f2 = QFormLayout(box2)
        f2.addRow("Som:", SoundRow("shugo"))
        secs = QSpinBox()
        secs.setRange(2, 60)
        secs.setSuffix(" s")
        secs.setValue(cfg["shugo"].get("show_seconds", 6))
        secs.valueChanged.connect(lambda v: (cfg["shugo"].__setitem__("show_seconds", v), save()))
        f2.addRow("Aviso fica na tela:", secs)
        icon_row = QHBoxLayout()
        bicon = QPushButton("Escolher ícone...")
        bicon.clicked.connect(self.pick_shugo_icon)
        bdef = QPushButton("Ícone padrão")
        bdef.clicked.connect(self.shugo.reset_icon)
        icon_row.addWidget(bicon)
        icon_row.addWidget(bdef)
        icon_row.addStretch()
        f2.addRow("Ícone do aviso:", icon_row)
        lay.addWidget(box2)

        row = QHBoxLayout()
        t5 = theme.primary(QPushButton("Testar aviso de 5 min"))
        t5.clicked.connect(lambda: self.shugo.alert(5))
        t1 = QPushButton("Testar aviso de 1 min")
        t1.clicked.connect(lambda: self.shugo.alert(1))
        pos = QPushButton("Posicionar aviso")
        pos.clicked.connect(self.position_shugo)
        for b in (t5, t1, pos):
            row.addWidget(b)
        row.addStretch()
        lay.addSpacing(6)
        lay.addLayout(row)
        lay.addStretch()
        return w

    def tab_pvp(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel("Toca um som quando você mata alguém. Não aparece nada na tela, é só o som. "
                      "Funciona reconhecendo a mensagem de abate do jogo: só olha a tela (como o OBS), "
                      "não lê memória, pacotes nem arquivos do jogo.")
        info.setWordWrap(True)
        lay.addWidget(info)

        box = QGroupBox("1. Imagem de referência da mensagem de abate")
        v = QVBoxLayout(box)
        self.ref_label = QLabel()
        v.addWidget(self.ref_label)
        b = QPushButton("Definir referência a partir de um print...")
        b.clicked.connect(self.define_reference)
        v.addWidget(b)
        lay.addWidget(box)

        box2 = QGroupBox("2. Onde procurar")
        f = QFormLayout(box2)
        self.region_label = QLabel()
        row = QHBoxLayout()
        bsel = QPushButton("Marcar área na tela...")
        bsel.clicked.connect(self.select_region)
        bclr = QPushButton("Usar monitor inteiro")
        bclr.clicked.connect(self.clear_region)
        row.addWidget(bsel)
        row.addWidget(bclr)
        f.addRow("Área:", self.region_label)
        f.addRow("", row)
        self.game_monitor = QComboBox()
        for i, (name, _s) in enumerate(screen_names(), 1):
            self.game_monitor.addItem(name, i)
        self.game_monitor.setCurrentIndex(max(0, cfg["pvp"].get("monitor", 1) - 1))
        self.game_monitor.currentIndexChanged.connect(
            lambda i: (cfg["pvp"].__setitem__("monitor", i + 1), save(), self.restart_pvp()))
        f.addRow("Monitor do jogo:", self.game_monitor)
        f.addRow(QLabel("Marcar uma área pequena deixa a detecção mais leve e mais precisa."))
        lay.addWidget(box2)

        box3 = QGroupBox("3. Ajustes")
        f3 = QFormLayout(box3)
        thr = QDoubleSpinBox()
        thr.setRange(0.5, 0.99)
        thr.setSingleStep(0.01)
        thr.setValue(cfg["pvp"].get("threshold", 0.8))
        thr.valueChanged.connect(lambda v: (cfg["pvp"].__setitem__("threshold", v), save()))
        f3.addRow("Precisão (0.80 padrão):", thr)
        self.score_label = QLabel("—")
        f3.addRow("Semelhança agora:", self.score_label)
        f3.addRow("Som:", SoundRow("pvp"))
        lay.addWidget(box3)

        row = QHBoxLayout()
        self.pvp_on = QCheckBox("Ativar detecção de abates")
        self.pvp_on.setChecked(cfg["pvp"].get("enabled", False))
        self.pvp_on.toggled.connect(self.set_pvp)
        row.addWidget(self.pvp_on)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.refresh_pvp_labels()
        return w

    def tab_map(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Mapa completo")
        v = QVBoxLayout(box)
        v.addWidget(QLabel("Pontos de coleta e spawns de monstros de Verteron, Eltnen, Altgard, Morheim e Reshanta."))
        b = theme.primary(QPushButton("Abrir mapa"))
        b.clicked.connect(self.open_map)
        v.addWidget(b)
        lay.addWidget(box)

        box2 = QGroupBox("Recursos no minimapa do jogo (Alt+M)")
        f = QFormLayout(box2)
        info = QLabel("O programa reconhece qual parte do mapa aparece no minimapa do Alt+M e desenha os "
                      "recursos por cima dele, seguindo quando você anda ou dá zoom. Usa os mesmos filtros do "
                      "mapa completo (tipos, material, esconder coletados) e mostra também os spawns do farm "
                      "de pet. Só olha a tela, igual ao som de abate.")
        info.setWordWrap(True)
        f.addRow(info)
        row = QHBoxLayout()
        bsel = QPushButton("Marcar área do minimapa...")
        bsel.clicked.connect(self.select_minimap)
        self.mm_on = QCheckBox("Ativar")
        self.mm_on.setChecked(minimap.mm_cfg()["enabled"])
        self.mm_on.toggled.connect(self.set_minimap)
        row.addWidget(bsel)
        row.addStretch()
        row.addWidget(self.mm_on)
        f.addRow(row)
        self.mm_status = QLabel("")
        self.mm_status.setWordWrap(True)
        f.addRow("Status:", self.mm_status)
        show_f = QCheckBox("Mostrar spawns do farm de pet")
        show_f.setChecked(minimap.mm_cfg()["show_farm"])
        show_f.toggled.connect(lambda on: (minimap.mm_cfg().__setitem__("show_farm", on), save()))
        f.addRow(show_f)
        size = QSpinBox()
        size.setRange(10, 40)
        size.setSuffix(" px")
        size.setValue(minimap.mm_cfg()["icon_size"])
        size.valueChanged.connect(lambda v: (minimap.mm_cfg().__setitem__("icon_size", v), save()))
        f.addRow("Tamanho dos ícones:", size)
        click = QCheckBox("Clicar nos ícones marca a coleta e começa o timer")
        click.setChecked(minimap.mm_cfg()["clickable"])
        click.toggled.connect(lambda on: (minimap.mm_cfg().__setitem__("clickable", on), save(),
                                          self.minimap.overlay.set_clickable(on)))
        f.addRow(click)
        resp = QSpinBox()
        resp.setRange(1, 60)
        resp.setSuffix(" min")
        resp.setValue(cfg["map"].get("respawn_minutes", 5))
        resp.valueChanged.connect(lambda v: (cfg["map"].__setitem__("respawn_minutes", v), save()))
        f.addRow("Tempo para renascer:", resp)
        how = QLabel("Clique esquerdo no ícone: coletei, começa a contagem (o ícone fica apagado com o tempo "
                     "embaixo e volta sozinho). Clique direito: cancela. O resto do minimapa continua "
                     "recebendo os cliques normalmente.")
        how.setWordWrap(True)
        f.addRow(how)
        note = QLabel("Marque só o quadro do mapa (sem as barras de opacidade e os botões, se der). Hoje o "
                      "reconhecimento funciona em Verteron e Altgard, que são os mapas com imagem de fundo; os outros "
                      "passam a funcionar quando ganharem imagem de fundo.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9b9282;")
        f.addRow(note)
        lay.addWidget(box2)
        lay.addStretch()
        return w

    def select_minimap(self):
        screens = QGuiApplication.screens()
        idx = self.game_monitor.currentIndex() if hasattr(self, "game_monitor") else 0
        screen = screens[idx] if idx < len(screens) else QGuiApplication.primaryScreen()
        self.mm_selector = RegionSelector(screen)
        self.mm_selector.hint_text = "Arraste em volta da área onde fica o minimapa  (Esc cancela)"
        self.mm_selector.chosen.connect(self.minimap_chosen)
        self.mm_selector.show()
        self.mm_selector.activateWindow()

    def minimap_chosen(self, r):
        minimap.mm_cfg()["region"] = r
        save()
        self.mm_status.setText(T("Área marcada: {w}x{h}").format(w=r[2], h=r[3]))
        if self.mm_on.isChecked():
            self.set_minimap(True)

    def set_minimap(self, on):
        minimap.mm_cfg()["enabled"] = on
        save()
        if on:
            if not self.minimap.start():
                self.mm_on.blockSignals(True)
                self.mm_on.setChecked(False)
                self.mm_on.blockSignals(False)
                minimap.mm_cfg()["enabled"] = False
                save()
        else:
            self.minimap.stop()
            self.mm_status.setText(T("Desligado"))

    # ------------------------------------------------------------------ ações
    def get_map(self):
        if self.map is None:
            self.map = MapWindow()
            self.map.on_farm = self.farm_tab.start_farm
        return self.map

    def open_map(self):
        m = self.get_map()
        m.show()
        theme.dark_titlebar(m)
        m.raise_()
        m.activateWindow()

    def send_to_screen(self, target):
        screen = self.screens.currentData()
        targets = [target()] if target else [self.shugo, self.farm_tab.card, self.events.toast,
                                             self.events.popup, self.dps_tab.meter] + ([self.map] if self.map else [])
        for i, t in enumerate(targets):
            t.move_to_screen(screen)
            if t is self.map:
                t.show()

    def set_alert(self, i, v):
        a = cfg["shugo"].setdefault("alerts", [5, 1])
        while len(a) <= i:
            a.append(0)
        a[i] = v
        save()

    def pick_shugo_icon(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ícone do aviso", "", "Imagens (*.png *.jpg *.jpeg *.webp *.ico)")
        if path:
            self.shugo.set_icon_file(path)

    def position_shugo(self):
        if self.lock.isChecked():
            self.lock.setChecked(False)
        self.shugo.preview_position()

    def lang_changed(self, _i):
        cfg["lang"] = self.lang.currentData()
        save()
        self.btn_restart.show()

    def restart(self):
        from PySide6.QtCore import QProcess
        args = [] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])]
        release_instance()
        QProcess.startDetached(sys.executable, args)
        self.quit()

    def refresh_lock_pill(self):
        on = cfg.get("locked", False)
        self.lock_pill.setChecked(on)
        self.lock_pill.setText("  " + (T("Overlays travados") if on else T("Overlays destravados")))
        self.lock_pill.setIcon(self._lock_icons[on])
        self.lock_pill.setToolTip(T("Travados: o clique passa direto para o jogo. Destravados: dá para arrastar."))

    def set_lock(self, on):
        cfg["locked"] = on
        save()
        if hasattr(self, "lock_pill"):
            self.refresh_lock_pill()
        self.shugo.set_locked(on)
        self.farm_tab.card.set_locked(on)
        self.events.set_locked(on)
        self.dps_tab.meter.set_locked(on)

    def toggle_lock(self):
        self.lock.setChecked(not self.lock.isChecked())

    def set_visible(self, key, widget, on):
        cfg[key]["visible"] = on
        save()
        widget.setVisible(on)
        if on:
            widget.set_locked(cfg.get("locked", False))

    def set_opacity(self, key, widget, val):
        cfg[key]["opacity"] = val / 100
        save()
        widget.setWindowOpacity(val / 100)

    def define_reference(self):
        if ReferenceDialog(self).exec():
            self.refresh_pvp_labels()
            self.restart_pvp()

    def select_region(self):
        idx = self.game_monitor.currentIndex()
        screens = QGuiApplication.screens()
        screen = screens[idx] if idx < len(screens) else QGuiApplication.primaryScreen()
        self.selector = RegionSelector(screen)
        self.selector.chosen.connect(self.region_chosen)
        self.selector.show()
        self.selector.activateWindow()

    def region_chosen(self, r):
        cfg["pvp"]["region"] = r
        save()
        self.refresh_pvp_labels()
        self.restart_pvp()

    def clear_region(self):
        cfg["pvp"]["region"] = None
        save()
        self.refresh_pvp_labels()
        self.restart_pvp()

    def refresh_pvp_labels(self):
        ref = cfg["pvp"].get("reference")
        self.ref_label.setText(T("Referência salva: {f}").format(f=os.path.basename(ref)) if ref and os.path.exists(ref)
                               else T("Nenhuma referência definida ainda."))
        r = cfg["pvp"].get("region")
        self.region_label.setText(f"{r[2]}x{r[3]} ({r[0]}, {r[1]})" if r else T("Monitor inteiro"))

    def set_pvp(self, on):
        cfg["pvp"]["enabled"] = on
        save()
        if on:
            if not self.pvp.start():
                QMessageBox.information(self, "PvP", "Defina primeiro a imagem de referência da mensagem de abate.")
                self.pvp_on.setChecked(False)
                return
            self.pvp.watcher.score.connect(lambda s: self.score_label.setText(f"{s:.2f}"))
        else:
            self.pvp.stop()
            self.score_label.setText("—")

    def restart_pvp(self):
        if cfg["pvp"].get("enabled"):
            self.set_pvp(True)

    def show_panel(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.tray.showMessage("Meta Overlay", T("Continua rodando na bandeja."), QSystemTrayIcon.Information, 2000)

    def quit(self):
        self.dps_tab.shutdown()
        self.hub.stop()
        self.pvp.stop()
        self.minimap.stop()
        self.farm_tab.shutdown()
        self.hotkeys.clear()
        if self.map:
            self.map.closeEvent(None)
        save()
        self.app.quit()


def single_instance():
    """Marca que o programa está aberto (o instalador usa isso) e evita abrir duas vezes."""
    if os.name != "nt":
        return True
    import ctypes
    k = ctypes.windll.kernel32
    main._mutex = k.CreateMutexW(None, False, "Aion2OverlayMutex")
    return k.GetLastError() != 183      # ERROR_ALREADY_EXISTS


def release_instance():
    """Solta a marca de 'aberto' antes de reabrir o programa (reiniciar / abrir como administrador)."""
    h = getattr(main, "_mutex", None)
    if h and os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.CloseHandle(h)
        main._mutex = None


def main():
    config.load()
    if not single_instance():
        from PySide6.QtWidgets import QMessageBox
        _app = QApplication(sys.argv)
        QMessageBox.information(None, "Meta Overlay",
                                T("O Meta Overlay já está aberto. Procure o ícone dele perto do relógio."))
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Meta Overlay")
    app.setWindowIcon(make_icon())
    theme.apply(app)
    panel = ControlPanel(app)
    panel.show()
    theme.dark_titlebar(panel)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
