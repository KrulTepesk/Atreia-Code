"""Meta Overlay — painel de controle, ícone na bandeja e janelas de overlay."""
import html
import os
import sys
import time

# Coordenadas em pixels reais (necessário para a captura de tela do PvP bater com a posição na tela)
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QRadioButton, QSlider, QSpinBox, QSystemTrayIcon, QTabWidget,
                               QVBoxLayout, QWidget)

import config
import instance
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
import hotkey_ui
from map_window import MapWindow
from region_select import RegionSelector
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
        self.label.setMinimumWidth(90)
        pick = QPushButton("Escolher som...")
        pick.clicked.connect(self.pick)
        default = QPushButton("Padrão")
        default.clicked.connect(self.reset)
        test = QPushButton("▶ Testar")
        test.clicked.connect(lambda: sounds_player.play(cfg[section]["sound"], cfg[section]["volume"]))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(cfg[section].get("volume", 80))
        self.vol.setMinimumWidth(80)
        self.vol.valueChanged.connect(self.set_vol)
        # duas linhas: cabe em janela estreita
        from PySide6.QtWidgets import QGridLayout
        lay.deleteLater()
        g = QGridLayout()
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(4)
        g.addWidget(self.label, 0, 0, 1, 2)
        g.addWidget(pick, 0, 2)
        g.addWidget(default, 0, 3)
        g.addWidget(test, 1, 0)
        g.addWidget(QLabel("Volume"), 1, 1)
        g.addWidget(self.vol, 1, 2, 1, 2)
        QWidget().setLayout(lay)          # tira o layout antigo deste widget
        self.setLayout(g)
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
        self._quitting = False
        self.setWindowTitle("Meta Overlay")
        self.setWindowIcon(make_icon())
        # tamanho compacto; em telas pequenas (ou com zoom do Windows) nunca passa de ~75% da tela
        self.setMinimumSize(560, 380)
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(860, int(avail.width() * 0.75)), min(600, int(avail.height() * 0.75)))

        self.shugo = ShugoWidget()
        self.map = None
        self.selector = None

        self.minimap = minimap.MinimapController()
        self.hub = NetHub()                 # leitura do jogo dividida entre DPS, farm e chefes de campo
        self._lock_icons = {False: theme.glyph_icon("unlock"), True: theme.glyph_icon("lock")}
        tabs = self.tabs = theme.NavTabs("Meta Overlay", "Ferramentas para Aion 2")
        tabs.addTab(self.tab_general(), "Geral", "general", "Idioma, monitores e trava dos overlays.")
        tabs.addTab(self.tab_shugo(), "Shugo", "shugo", "Aviso antes do Festival do Shugo começar.")
        tabs.addTab(self.tab_map(), "Mapa", "map", "Coletáveis, mobs e o minimapa do Alt+M com os recursos por cima.")
        self.dps_tab = DpsTab(self.hub)
        self.farm_tab = FarmTab(self)
        tabs.addTab(self.farm_tab, "Farm de pet (experimental)", "farm", "Conta sozinho os seus abates e mostra os mobs de pet onde você está.")
        self.events = EventScheduler()
        tabs.insertTab(2, EventsTab(self.events, SoundRow), "Rifts e chefes", "rifts",
                       "Avisos 5 minutos antes e na hora das fendas e dos chefes do mundo.")
        self.field_bosses = FieldBossManager(self.events, self.hub)
        tabs.insertTab(3, FieldBossTab(self.field_bosses), "Chefes de campo", "crown",
                       "Quando cada field boss renasce, com aviso e mapa do local.")
        tabs.addTab(self.dps_tab, "DPS Meter", "dps", "Medidor de dano seu e do seu grupo, lido do tráfego do jogo.")
        tabs.addTab(self.tab_pvp(), "PvP (experimental)", "pvp", "Um som quando você mata um jogador e outro quando dá assistência.")
        tabs.addTab(self.tab_settings(), "Configurações", "settings", "Como o Meta Overlay se comporta ao fechar a janela.")
        self.dps_tab.quit_app = self.quit
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

        # o Shugo não fica na tela: o aviso aparece sozinho 5 e 1 minuto antes
        self.shugo.restore_position()
        self.shugo.set_locked(cfg.get("locked", False))
        self.events.set_locked(cfg.get("locked", False))
        # sons de abate/assistência no PvP: lidos do tráfego do jogo, ligam sozinhos
        self.hub.pvp.connect(self.on_pvp)
        self.hub.running_changed.connect(lambda _on: self.refresh_pvp())
        if cfg["pvp"].get("auto", True) and self.hub.requirements()[0]:
            QTimer.singleShot(3000, lambda: (self.hub.acquire("pvp"), self.refresh_pvp()))

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

        # teclas de atalho globais (configuráveis na aba Geral)
        self.hotkeys = Hotkeys(app)
        self._hk_tries = 0
        self.register_hotkeys()
        self.hotkeys.pressed.connect(self.on_hotkey)

    def register_hotkeys(self, retry=True):
        """(Re)registra todos os atalhos configurados. Se outro programa (ou a cópia anterior do próprio app que
        ainda está fechando, ex.: depois de "Reiniciar") estiver usando, tenta de novo a cada 2 s por até 30 s."""
        if not self.hotkeys.ok:
            return
        self.hotkeys.clear()
        failed = []
        for name, v in hotkey_ui.hk_cfg().items():
            if v and name in hotkey_ui.IDS:
                if not self.hotkeys.add(hotkey_ui.IDS[name], v["mods"], v["vk"]):
                    failed.append(name)
        self.hk_box.show_failed(failed)
        if failed and retry:
            self._hk_tries += 1
            if self._hk_tries < 15:
                QTimer.singleShot(2000, self.register_hotkeys)
        elif not failed:
            self._hk_tries = 0

    def hotkeys_capturing(self, on):
        """Enquanto escolhe uma tecla, solta os atalhos (senão o Windows pega a tecla antes do botão)."""
        if on:
            self.hotkeys.clear()
        else:
            self.register_hotkeys(retry=False)

    def on_hotkey(self, hid):
        name = hotkey_ui.NAMES.get(hid)
        if name == "dps_reset":
            self.dps_tab.reset_fight()
        elif name == "dps_toggle":
            self.dps_tab.chk_show.toggle()
        elif name == "dps_view":
            v = "session" if cfg.get("dps", {}).get("view", "fight") == "fight" else "fight"
            self.dps_tab.meter.view = v
            self.dps_tab.set_view(v)
            self.dps_tab.meter.update()
        elif name == "lock":
            self.toggle_lock()
        elif name == "minimap":
            self.mm_on.toggle()
        elif name == "map":
            if self.map is not None and self.map.isVisible():
                self.map.hide()
            else:
                self.open_map()
        elif name == "panel":
            self.show_panel()

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
        from PySide6.QtWidgets import QGridLayout
        row = QGridLayout()
        row.setHorizontalSpacing(6)
        row.setVerticalSpacing(6)
        for i, (text, target) in enumerate((("Aviso do Shugo", lambda: self.shugo),
                                            ("Avisos de rifts/chefes", lambda: self.events.toast),
                                            ("Mini-mapa dos chefes", lambda: self.events.popup),
                                            ("Card do farm", lambda: self.farm_tab.card),
                                            ("Medidor de DPS", lambda: self.dps_tab.meter),
                                            ("Mapa", self.get_map),
                                            ("Todos", None))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, t=target: self.send_to_screen(t))
            row.addWidget(b, i // 3, i % 3)
        f.addRow("Mover:", row)
        lay.addWidget(box)

        self.hk_box = hotkey_ui.HotkeysBox(lambda: self.register_hotkeys(retry=False),
                                           lambda on: self.hotkeys_capturing(on))
        lay.addWidget(self.hk_box)
        lay.addStretch()
        return w

    # ------------------------------------------------------------ Configurações
    def tab_settings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Ao fechar a janela (botão X)")
        v = QVBoxLayout(box)
        self.close_tray = QRadioButton("Deixar rodando em segundo plano (ícone perto do relógio)")
        self.close_quit = QRadioButton("Fechar o Meta Overlay")
        (self.close_quit if close_action() == "quit" else self.close_tray).setChecked(True)
        self.close_tray.toggled.connect(lambda on: on and self.set_close_action("tray"))
        self.close_quit.toggled.connect(lambda on: on and self.set_close_action("quit"))
        v.addWidget(self.close_tray)
        v.addWidget(self.close_quit)
        hint = QLabel("Em segundo plano, os avisos, o DPS Meter e as teclas de atalho continuam funcionando. "
                      "Para fechar de vez, use \"Sair\" no menu do ícone perto do relógio.")
        hint.setWordWrap(True)
        v.addWidget(hint)
        lay.addWidget(box)

        row = QHBoxLayout()
        row.addStretch()
        b = QPushButton("Sair do Meta Overlay agora")
        b.clicked.connect(self.quit)
        row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch()
        return w

    def set_close_action(self, action):
        cfg.setdefault("app", {})["close_action"] = action
        save()

    def tab_shugo(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("O Festival Shugo começa toda hora cheia (horário do servidor). Nada fica fixo na tela: "
                       "um aviso aparece com som nos minutos escolhidos e some sozinho (duplo clique fecha antes).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.shugo_on = QCheckBox("Avisar do Festival Shugo")
        self.shugo_on.setChecked(cfg["shugo"].get("enabled", True))
        lay.addWidget(self.shugo_on)

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
        self._shugo_boxes = [box, box2]
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
        def set_shugo(on):
            cfg["shugo"]["enabled"] = on
            save()
            for b in self._shugo_boxes:
                b.setEnabled(on)
            if not on:
                self.shugo.hide()
        self.shugo_on.toggled.connect(set_shugo)
        for b in self._shugo_boxes:
            b.setEnabled(self.shugo_on.isChecked())
        return w

    def tab_pvp(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel("Tudo automático: usa a mesma leitura do jogo do medidor de DPS. Não precisa marcar nada na tela.")
        info.setWordWrap(True)
        lay.addWidget(info)

        box0 = QGroupBox("Leitura do jogo")
        v0 = QVBoxLayout(box0)
        self.pvp_status = QLabel("")
        self.pvp_status.setWordWrap(True)
        self.pvp_status.setTextFormat(Qt.RichText)
        v0.addWidget(self.pvp_status)
        row = QHBoxLayout()
        self.pvp_btn = theme.primary(QPushButton("Ligar"))
        self.pvp_btn.clicked.connect(self.toggle_pvp)
        self.pvp_npcap = QPushButton("Instalar Npcap")
        self.pvp_npcap.clicked.connect(lambda: self.dps_tab.install_npcap())
        self.pvp_admin = QPushButton("Abrir como administrador")
        self.pvp_admin.clicked.connect(lambda: self.dps_tab.reopen_admin())
        auto = QCheckBox("Ligar sozinho ao abrir o programa")
        auto.setChecked(cfg["pvp"].get("auto", True))
        auto.toggled.connect(lambda on: (cfg["pvp"].__setitem__("auto", on), save()))
        for b in (self.pvp_btn, self.pvp_npcap, self.pvp_admin):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(auto)
        v0.addLayout(row)
        lay.addWidget(box0)

        box = QGroupBox("Abate")
        v = QVBoxLayout(box)
        lk = QLabel("Você levou o abate do jogador.")
        lk.setStyleSheet(f"color:{theme.MUTED}")
        v.addWidget(lk)
        v.addWidget(SoundRow("pvp"))
        lay.addWidget(box)

        box2 = QGroupBox("Assistência")
        v2 = QVBoxLayout(box2)
        la = QLabel("Você bateu no jogador nos últimos 15 segundos e outro levou o abate.")
        la.setWordWrap(True)
        la.setStyleSheet(f"color:{theme.MUTED}")
        v2.addWidget(la)
        v2.addWidget(SoundRow("pvp_assist"))
        lay.addWidget(box2)

        box3 = QGroupBox("Nesta sessão")
        v3 = QVBoxLayout(box3)
        self.pvp_count = QLabel("")
        self.pvp_last = QLabel("")
        self.pvp_last.setTextFormat(Qt.PlainText)          # o nome vem do jogo: nunca vira HTML
        self.pvp_last.setStyleSheet(f"color:{theme.MUTED}")
        v3.addWidget(self.pvp_count)
        v3.addWidget(self.pvp_last)
        lay.addWidget(box3)
        lay.addStretch()
        self.pvp_n = {"kill": 0, "assist": 0}
        self.refresh_pvp()
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
                      "de pet. Só olha a tela.")
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
        self.game_monitor = QComboBox()
        for i, (name, _s) in enumerate(screen_names(), 1):
            self.game_monitor.addItem(name, i)
        mon = minimap.mm_cfg().get("monitor") or cfg.get("pvp", {}).get("monitor", 1)
        self.game_monitor.setCurrentIndex(max(0, min(self.game_monitor.count() - 1, mon - 1)))
        self.game_monitor.currentIndexChanged.connect(
            lambda i: (minimap.mm_cfg().__setitem__("monitor", i + 1), save()))
        f.addRow("Monitor do jogo:", self.game_monitor)
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
        if path and not self.shugo.set_icon_file(path):
            QMessageBox.warning(self, "Shugo", T("Não consegui usar essa imagem."))

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
        args = ([] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])]) + ["--replace"]
        self.hide()
        self.tray.hide()
        save()
        instance.release()
        QProcess.startDetached(sys.executable, args)
        self.quit()                     # main() encerra o processo de vez depois do app.exec()

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

    # ------------------------------------------------------------ PvP
    def refresh_pvp(self):
        ok, falta = self.hub.requirements()
        self.pvp_npcap.setVisible("Npcap" in falta)
        self.pvp_admin.setVisible("administrador" in falta)
        self.pvp_btn.setEnabled(ok)
        if self.hub.running and "pvp" in self.hub.users:
            self.pvp_btn.setText(T("Desligar"))
            who = html.escape(cfg.get("dps", {}).get("char_name") or "") or T("procurando o seu personagem (costuma aparecer quando você toma dano)…")
            self.pvp_status.setText(f"<span style='color:#5ee39a'>●</span> <b>{T('Lendo o jogo')}</b> — "
                                    f"{T('personagem')}: {who}")
        else:
            self.pvp_btn.setText(T("Ligar"))
            if ok:
                self.pvp_status.setText(f"<span style='color:#9b9282'>○</span> {T('Desligado.')}")
            else:
                faltam = (" " + T("e") + " ").join(T(x) for x in falta)
                self.pvp_status.setText("<span style='color:#f0883e'>○</span> " +
                                        T("Para tocar os sons falta: {f}.").format(f=faltam))
        self.pvp_count.setText(T("{k} abates · {a} assistências").format(k=self.pvp_n["kill"], a=self.pvp_n["assist"]))
        if not getattr(self, "_pvp_last_txt", ""):
            self.pvp_last.setText(T("Nenhum ainda."))

    def toggle_pvp(self):
        if self.hub.running and "pvp" in self.hub.users:
            self.hub.release("pvp")
        else:
            self.hub.acquire("pvp")
        self.refresh_pvp()

    def on_pvp(self, ev):
        if "pvp" not in self.hub.users:
            return
        kind = ev.get("kind")
        sec = "pvp" if kind == "kill" else "pvp_assist"
        sounds_player.play(cfg[sec]["sound"], cfg[sec].get("volume", 80))
        self.pvp_n[kind] = self.pvp_n.get(kind, 0) + 1
        who = ev.get("victim") or T("um jogador")
        when = time.strftime("%H:%M:%S", time.localtime(ev.get("t") or time.time()))
        self._pvp_last_txt = (T("Último: abate em {n}") if kind == "kill" else T("Último: assistência em {n}")).format(n=who) + f"  ({when})"
        self.pvp_last.setText(self._pvp_last_txt)
        self.refresh_pvp()

    def show_panel(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if self._quitting:
            e.accept()
            return
        e.ignore()
        if close_action() == "quit":
            self.quit()
            return
        self.hide()
        self.tray.showMessage("Meta Overlay", T("Continua rodando na bandeja."), QSystemTrayIcon.Information, 2000)

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        # cada parte fecha por conta própria: um erro numa delas não pode impedir o programa de sair
        # (senão ele ficava escondido rodando e, ao abrir de novo, eram dois)
        steps = [self.hide, self.tray.hide, self.dps_tab.shutdown, self.hub.stop, self.minimap.stop,
                 self.farm_tab.shutdown, self.hotkeys.clear, lambda: self.map and self.map.closeEvent(None), save]
        for step in steps:
            try:
                step()
            except Exception as e:
                print("ao fechar:", e)
        # exit() e não quit(): no Qt 6 o quit() pede para cada janela fechar e é cancelado se alguma recusa
        # (o painel recusa para ir à bandeja) — era por isso que "reabrir como administrador" deixava a
        # cópia antiga rodando escondida. Se mesmo assim algo travar o laço, o processo sai sozinho.
        QTimer.singleShot(4000, lambda: os._exit(0))
        self.app.exit(0)

    def check_instance(self):
        """Outra cópia pediu: 'show' = abriram de novo pelo atalho; 'quit' = a cópia nova vai assumir."""
        what = instance.poll()
        if what == "show":
            self.show_panel()
        elif what == "quit":
            self.hide()
            self.tray.hide()
            instance.release()
            self.quit()


def close_action():
    a = cfg.get("app", {}).get("close_action", "tray")
    return a if a in ("tray", "quit") else "tray"


def main():
    config.load()
    replace = "--replace" in sys.argv
    if not instance.acquire(replace=replace):
        if not instance.other_was_shown():      # versão antiga aberta (não sabe mostrar o painel sozinha)
            from PySide6.QtWidgets import QMessageBox
            _app = QApplication([a for a in sys.argv if a != "--replace"])  # noqa: F841
            QMessageBox.information(None, "Meta Overlay",
                                    T("O Meta Overlay já está aberto. Procure o ícone dele perto do relógio."))
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Meta Overlay")
    app.setWindowIcon(make_icon())
    theme.apply(app)
    panel = ControlPanel(app)
    inst_timer = QTimer(panel)
    inst_timer.timeout.connect(panel.check_instance)
    inst_timer.start(400)
    panel.show()
    theme.dark_titlebar(panel)
    code = app.exec()
    # Fecha de verdade. Sem isso, alguma leitura em segundo plano (rede, tela) podia segurar o processo
    # escondido depois de "Reiniciar" / trocar o idioma, e ficavam dois programas abertos.
    try:
        panel.tray.hide()
        save()
    except Exception:
        pass
    sys.stdout.flush() if sys.stdout else None
    os._exit(code)


if __name__ == "__main__":
    main()
