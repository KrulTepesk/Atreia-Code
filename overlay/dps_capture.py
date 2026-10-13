"""DPS: medidor ao vivo + gravador de captura (diagnóstico).

Usa o driver Npcap (via scapy) para ler SÓ o tráfego que o servidor do jogo manda. Captura passiva:
não injeta nada, não lê memória e não mexe nos arquivos do jogo. Nada é enviado
para a internet; o arquivo fica só no seu PC.

Desligado por padrão. O uso é por sua conta e risco (regras do jogo).
"""
import ctypes
import datetime
import os
import sys
import time

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from i18n import T
from config import APP_DIR, cfg, save
from dps_live import GAME_PORT
from dps_meter import CLASSES, COLUMNS, LOOK_DEFAULTS, DpsMeter, SkillPanel, look

CAPTURE_DIR = os.path.join(APP_DIR, "capturas")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True  # fora do Windows não se aplica


def npcap_installed():
    if os.name != "nt":
        return True
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.exists(os.path.join(sysroot, "System32", "Npcap")) or \
        os.path.exists(os.path.join(sysroot, "System32", "wpcap.dll"))


def restart_as_admin():
    """Abre de novo o programa pedindo permissão de administrador e fecha este."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, "--replace"
    else:
        exe, params = sys.executable, f'"{os.path.abspath(sys.argv[0])}" --replace'
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return r > 32


NPCAP_URL = "https://npcap.com/dist/npcap-1.89.exe"
# SHA-256 do npcap-1.89.exe oficial (conferido no build do GitHub: assinatura válida da Nmap Software LLC)
NPCAP_SHA256 = "8aed85e900d783d1308506e919587d3e540451947af8a82f2d04f819e44305cc"
NPCAP_SIGNER = "O=Nmap Software LLC"
NPCAP_HOWTO = ("Vai abrir o instalador oficial do Npcap.\n\nDeixe marcada a opção \"Install Npcap in WinPcap "
               "API-compatible Mode\" e clique em I Agree / Install.\nO Windows vai pedir permissão de "
               "administrador: clique em Sim.\n\nDepois, clique em \"Reabrir como administrador\".")


def npcap_source():
    """(url, sha256) — o build grava data/npcap.json com o SHA-256 do instalador conferido no GitHub."""
    import json
    try:
        from config import BASE_DIR
        with open(os.path.join(BASE_DIR, "data", "npcap.json"), encoding="utf-8") as f:
            d = json.load(f)
        url, sha = d.get("url") or NPCAP_URL, (d.get("sha256") or "").lower()
        if url.startswith("https://npcap.com/") and len(sha) == 64:
            return url, sha
    except Exception:
        pass
    return NPCAP_URL, NPCAP_SHA256


def _authenticode_ok(path):
    """Assinatura digital válida e do autor do Npcap (pelo PowerShell do próprio Windows)."""
    import subprocess
    try:
        env = dict(os.environ, METAOVERLAY_FILE=path)
        cmd = ("$s = Get-AuthenticodeSignature -LiteralPath $env:METAOVERLAY_FILE; "
               "Write-Output ($s.Status.ToString() + '|' + $s.SignerCertificate.Subject)")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], env=env,
                           capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        status, _, subject = r.stdout.strip().partition("|")
        return status == "Valid" and NPCAP_SIGNER in subject
    except Exception:
        return False


def verify_npcap(path, sha=""):
    """Só abre o instalador se for o arquivo esperado: SHA-256 fixado (quando o build gravou) e assinatura."""
    import hashlib
    if sha:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha:
            return False
    return _authenticode_ok(path) or bool(sha)


def deps_ok():
    try:
        import psutil  # noqa: F401
        import netlib
        netlib.load()
        return True, ""
    except Exception as e:
        return False, str(e)


def _external(ip):
    """Ignora conexões locais (127.x, ::1, rede interna 0.0.0.0) — o jogo fala com servidores de fora."""
    import ipaddress
    try:
        a = ipaddress.ip_address(ip)
        return not (a.is_loopback or a.is_unspecified or a.is_link_local)
    except ValueError:
        return False


def list_game_processes():
    """Processos com conexões externas; os que parecem ser o Aion vêm primeiro (e os com mais conexões)."""
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            conns = [c for c in p.net_connections(kind="inet")
                     if c.raddr and _external(c.raddr.ip) and
                     (c.status == psutil.CONN_ESTABLISHED or c.type == 2)]
        except Exception:
            continue
        if conns:
            out.append((p.info["name"] or "?", p.info["pid"], len(conns)))
    out.sort(key=lambda t: (0 if "aion" in t[0].lower() else 1, -t[2], t[0].lower()))
    return out


def remote_endpoints(pid):
    """(ip, porta, protocolo) de fora com que o processo está conversando."""
    import psutil
    eps = set()
    for c in psutil.Process(pid).net_connections(kind="inet"):
        if c.raddr and _external(c.raddr.ip) and (c.status == psutil.CONN_ESTABLISHED or c.type == 2):
            eps.add((c.raddr.ip, c.raddr.port, "udp" if c.type == 2 else "tcp"))
    return sorted(eps)


def game_server_hosts(port=GAME_PORT):
    """IPs dos servidores do jogo (conexões TCP abertas na porta do jogo)."""
    import psutil
    try:
        return sorted({c.raddr.ip for c in psutil.net_connections(kind="tcp")
                       if c.raddr and c.raddr.port == port and c.status == psutil.CONN_ESTABLISHED})
    except Exception:
        return []


class CaptureThread(QThread):
    stats = Signal(int, int)        # pacotes, bytes
    error = Signal(str)
    endpoints = Signal(str)

    def __init__(self, pid, path):
        super().__init__()
        self.pid, self.path = pid, path
        self._run = True

    def stop(self):
        self._run = False
        self.wait(4000)

    def run(self):
        try:
            import netlib
            _n = netlib.load()
            AsyncSniffer, PcapWriter, conf = _n.AsyncSniffer, _n.PcapWriter, _n.conf
            eps = remote_endpoints(self.pid)
            if not eps:
                self.error.emit("O processo não tem conexões com servidores de fora")
                return
            self.endpoints.emit(", ".join(f"{ip}:{port}/{pr}" for ip, port, pr in eps))
            hosts = sorted({ip for ip, _p, _pr in eps})
            bpf = "(tcp or udp) and (" + " or ".join(f"host {h}" for h in hosts) + ")"
            iface = conf.route.route(hosts[0])[0]
            writer = PcapWriter(self.path, append=False, sync=True)
            count = [0, 0]

            def on_pkt(pkt):
                writer.write(pkt)
                count[0] += 1
                count[1] += len(pkt)

            sniffer = AsyncSniffer(iface=iface, filter=bpf, prn=on_pkt, store=False)
            sniffer.start()
            while self._run:
                time.sleep(0.5)
                self.stats.emit(count[0], count[1])
            sniffer.stop()
            writer.close()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class DpsTab(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.quit_app = None             # o painel liga aqui o "fechar de vez" (usado ao reabrir como admin)
        d = cfg.setdefault("dps", {})
        d.setdefault("enabled", False)
        d.setdefault("char_name", "")
        d.setdefault("show_meter", True)
        d.setdefault("autostart", False)
        d.setdefault("mode", "party")
        d.setdefault("show_skills", True)
        d.setdefault("view", "fight")
        self.thread = None
        self.current = None
        self.marks_file = None
        self.t0 = None
        self.meter = DpsMeter()
        self.skills = SkillPanel()
        self.meter.docked = self.skills
        self.sel_id = None            # jogador mostrado no detalhe (None = você)
        self._last = None
        self.meter.row_clicked.connect(self.select_row)
        self.meter.reset_requested.connect(self.reset_fight)
        self.meter.view_requested.connect(self.set_view)
        self._hide_overlays()
        hub.updated.connect(lambda snap: self.on_live(snap) if self.reader else None)
        hub.status.connect(self.on_live_status)
        hub.running_changed.connect(self._hub_running)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = QVBoxLayout(inner)

        warn = QLabel(
            "<b>Desligado por padrão.</b> Lê só o tráfego de rede do jogo pelo Npcap "
            "(sem ler memória, sem mexer em arquivos, sem enviar nada para a internet). "
            "Mesmo assim, programas externos vão contra as regras do jogo: use por sua conta e risco.")
        warn.setWordWrap(True)
        lay.addWidget(warn)

        self.enable = QCheckBox("Ligar módulo DPS")
        self.enable.setChecked(d["enabled"])
        self.enable.toggled.connect(self.set_enabled)
        lay.addWidget(self.enable)

        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)

        # ---- requisitos
        g_req = QGroupBox("Requisitos")
        b = QVBoxLayout(g_req)
        req = QHBoxLayout()
        self.req_label = QLabel()
        self.btn_npcap = QPushButton("Instalar Npcap")
        self.btn_npcap.clicked.connect(self.install_npcap)
        self.btn_admin = QPushButton("Reabrir como administrador")
        self.btn_admin.clicked.connect(self.reopen_admin)
        req.addWidget(self.req_label, 1)
        req.addWidget(self.btn_npcap)
        req.addWidget(self.btn_admin)
        b.addLayout(req)
        about = QLabel(
            "<b>Por que precisa do Npcap?</b> O medidor de DPS calcula o dano lendo o tráfego de rede do jogo. "
            "O Npcap é um driver de rede para Windows que deixa um programa ler "
            "uma <i>cópia</i> dos dados que passam pela sua internet. O overlay usa isso para ler só o tráfego do "
            "Aion 2: não altera, não bloqueia e não envia nada, e não mexe nos arquivos do jogo. "
            "Sem o Npcap só o DPS deixa de funcionar; o resto do overlay continua normal.")
        about.setWordWrap(True)
        about.setStyleSheet("color:#d4ccbb; padding:4px 0 8px 0;")
        b.addWidget(about)
        bl.addWidget(g_req)

        # ---- medidor ao vivo
        g_live = QGroupBox("Medidor de dano ao vivo")
        f = QFormLayout(g_live)
        self.char_name = QLineEdit(d["char_name"])
        self.char_name.setPlaceholderText("ex.: Krul")
        self.char_name.editingFinished.connect(self.save_char_name)
        f.addRow("Seu personagem:", self.char_name)
        hint = QLabel("Opcional. O medidor normalmente descobre sozinho qual linha é a sua (fica com contorno branco); "
                      "o nome só ajuda se isso falhar.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9b9282;")
        f.addRow(hint)
        row = QHBoxLayout()
        self.btn_live = QPushButton("▶ Iniciar medidor")
        import theme as _theme
        _theme.primary(self.btn_live)
        self.btn_live.clicked.connect(self.toggle_live)
        btn_reset = QPushButton("Zerar luta")
        btn_reset.clicked.connect(self.reset_fight)
        row.addWidget(self.btn_live)
        row.addWidget(btn_reset)
        row.addStretch()
        f.addRow(row)
        self.mode = QComboBox()
        self.mode.addItem(T("Só eu e meu grupo"), "party")
        self.mode.addItem(T("Todos os jogadores por perto"), "all")
        self.mode.setCurrentIndex(max(0, self.mode.findData(d["mode"])))
        self.mode.currentIndexChanged.connect(self.set_mode)
        f.addRow("Mostrar:", self.mode)
        group_hint = QLabel("O grupo é reconhecido por quem troca buffs e curas com você durante o jogo. "
                            "Zerar: botão ↺ no próprio medidor ou Ctrl+Alt+R.")
        group_hint.setWordWrap(True)
        group_hint.setStyleSheet("color:#9b9282;")
        f.addRow(group_hint)
        self.chk_show = QCheckBox("Mostrar o medidor na tela")
        self.chk_show.setChecked(d["show_meter"])
        self.chk_show.toggled.connect(self.set_show)
        f.addRow(self.chk_show)
        self.chk_skills = QCheckBox("Mostrar as habilidades abaixo do medidor (clique num jogador para ver as dele)")
        self.chk_skills.setChecked(d["show_skills"])
        self.chk_skills.toggled.connect(self.set_show_skills)
        f.addRow(self.chk_skills)
        self.chk_auto = QCheckBox("Iniciar o medidor junto com o programa")
        self.chk_auto.setChecked(d["autostart"])
        self.chk_auto.toggled.connect(lambda on: (cfg["dps"].__setitem__("autostart", on), save()))
        f.addRow(self.chk_auto)
        self.live_status = QLabel("")
        self.live_status.setWordWrap(True)
        self.live_status.setStyleSheet("color:#9b9282;")
        f.addRow(self.live_status)
        note_live = QLabel("Conta o dano que o servidor informa para você e para quem está por perto. "
                           "Uma luta termina depois de 8 s sem golpes; a próxima começa do zero. "
                           "Se o jogo receber atualização e o medidor parar de contar, grave uma captura abaixo.")
        note_live.setWordWrap(True)
        note_live.setStyleSheet("color:#9b9282;")
        f.addRow(note_live)
        bl.addWidget(g_live)
        bl.addWidget(self._look_box())

        # ---- gravação (diagnóstico)
        g_rec = QGroupBox("Gravar captura (diagnóstico, para corrigir o medidor depois de atualizações)")
        b = QVBoxLayout(g_rec)
        steps = QLabel(
            "1. Entre no jogo, vá até um boneco de treino e escolha o processo do jogo abaixo.\n"
            "2. Clique em Gravar. Bata uns 20–30 s, usando 2 ou 3 habilidades diferentes.\n"
            "   Aperte \"Marcar\" no instante de um golpe e escreva o dano que apareceu.\n"
            "3. Pare a gravação e envie o arquivo .pcap + o _marcas.txt ao desenvolvedor.")
        steps.setWordWrap(True)
        b.addWidget(steps)

        row = QHBoxLayout()
        self.proc = QComboBox()
        self.proc.setMinimumWidth(300)
        refresh = QPushButton("Atualizar lista")
        refresh.clicked.connect(self.refresh_procs)
        row.addWidget(QLabel("Processo:"))
        row.addWidget(self.proc, 1)
        row.addWidget(refresh)
        b.addLayout(row)

        row2 = QHBoxLayout()
        self.rec = QPushButton("● Gravar")
        self.rec.clicked.connect(self.toggle_record)
        self.mark_text = QLineEdit()
        self.mark_text.setPlaceholderText("anotação (ex.: golpe 1 = 12.345 de dano)")
        mark = QPushButton("Marcar")
        mark.clicked.connect(self.mark)
        opendir = QPushButton("Abrir pasta das capturas")
        opendir.clicked.connect(lambda: (os.makedirs(CAPTURE_DIR, exist_ok=True), os.startfile(CAPTURE_DIR))
                                if hasattr(os, "startfile") else None)
        row2.addWidget(self.rec)
        row2.addWidget(self.mark_text, 1)
        row2.addWidget(mark)
        row2.addWidget(opendir)
        b.addLayout(row2)

        self.status = QLabel("")
        b.addWidget(self.status)
        self.ep_label = QLabel("")
        self.ep_label.setWordWrap(True)
        self.ep_label.setStyleSheet("color:#9b9282;")
        b.addWidget(self.ep_label)
        note = QLabel("O arquivo contém o tráfego da sua sessão de jogo: mande só para quem você confia "
                      "e não publique. Grave já logado e dentro do jogo, não na tela de login.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9b9282;")
        b.addWidget(note)
        bl.addWidget(g_rec)

        lay.addWidget(self.body)
        lay.addStretch()
        self.set_enabled(self.enable.isChecked(), init=True)
        if self.enable.isChecked() and d["autostart"] and npcap_installed() and is_admin():
            QTimer.singleShot(1500, self.toggle_live)

    # ------------------------------------------------------------------ aparência
    def _look_box(self):
        L = look()
        g = QGroupBox("Aparência do medidor")
        f = QFormLayout(g)
        self.look_w = {}

        def slider(key, lo, hi, suffix, getter, setter):
            row = QHBoxLayout()
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(getter())
            val = QLabel(f"{getter()}{suffix}")
            val.setMinimumWidth(42)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            def changed(v):
                val.setText(f"{v}{suffix}")
                setter(v)
            sl.valueChanged.connect(changed)
            row.addWidget(sl, 1)
            row.addWidget(val)
            self.look_w[key] = sl
            return row

        f.addRow("Tamanho:", slider("scale", 70, 160, "%", lambda: look()["scale"],
                                    lambda v: self.set_look("scale", v)))
        f.addRow("Fundo:", slider("bg", 0, 100, "%", lambda: look()["bg"], lambda v: self.set_look("bg", v)))
        f.addRow("Transparência geral:", slider("opacity", 30, 100, "%",
                                                lambda: int(round(cfg["dps"].get("opacity", 0.9) * 100)),
                                                self.set_opacity))
        rows = QComboBox()
        rows.addItem(T("Todos"), 0)
        for n in (3, 4, 5, 6, 8, 10):
            rows.addItem(T("Até {n}").format(n=n), n)
        rows.setCurrentIndex(max(0, rows.findData(L["rows"])))
        rows.currentIndexChanged.connect(lambda _i: self.set_look("rows", rows.currentData()))
        self.look_w["rows"] = rows
        f.addRow("Jogadores na lista:", rows)
        bars = QComboBox()
        bars.addItem(T("Cor da classe"), "class")
        bars.addItem(T("Uma cor só (dourado)"), "gold")
        bars.setCurrentIndex(max(0, bars.findData(L["bars"])))
        bars.currentIndexChanged.connect(lambda _i: self.set_look("bars", bars.currentData()))
        self.look_w["bars"] = bars
        f.addRow("Cor das barras:", bars)

        cols = QHBoxLayout()
        names = {"crit": "Crítico", "multi": "Duplo", "dps": "DPS", "total": "Total", "pct": "%"}
        for key, _t, _w in reversed(COLUMNS):                 # na ordem em que aparecem (esquerda → direita)
            cb = QCheckBox(T(names[key]))
            cb.setChecked(L["cols"].get(key, True))
            cb.toggled.connect(lambda on, k=key: self.set_look_col(k, on))
            self.look_w["col_" + key] = cb
            cols.addWidget(cb)
        cols.addStretch()
        f.addRow("Colunas:", cols)
        compact = QCheckBox("Linhas compactas")
        compact.setChecked(L["compact"])
        compact.toggled.connect(lambda on: self.set_look("compact", on))
        self.look_w["compact"] = compact
        f.addRow(compact)
        hide = QCheckBox("Esconder o nome dos outros jogadores (mostra só a classe — bom para gravar ou fazer live)")
        hide.setChecked(L["hide_names"])
        hide.toggled.connect(lambda on: self.set_look("hide_names", on))
        self.look_w["hide_names"] = hide
        f.addRow(hide)

        row = QHBoxLayout()
        prev = QPushButton("Ver prévia na tela")
        prev.clicked.connect(self.preview_look)
        rst = QPushButton("Restaurar padrão")
        rst.clicked.connect(self.reset_look)
        row.addWidget(prev)
        row.addStretch()
        row.addWidget(rst)
        f.addRow(row)
        hint = QLabel("As mudanças aparecem na hora. A prévia mostra o medidor com dados de exemplo por 10 s "
                      "(destrave os overlays para arrastá-lo).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9b9282;")
        f.addRow(hint)
        return g

    def _apply_look(self):
        save()
        self.meter.apply_look()
        self.skills.apply_look()
        if self._last and (self.reader or self._previewing):
            self.on_live(self._last)

    def set_look(self, key, value):
        look()[key] = value
        self._apply_look()

    def set_look_col(self, key, on):
        look()["cols"][key] = on
        self._apply_look()

    def reset_look(self):
        import copy
        cfg["dps"]["look"] = copy.deepcopy(LOOK_DEFAULTS)
        cfg["dps"]["opacity"] = 0.9
        L = look()
        w = self.look_w
        for key in ("scale", "bg"):
            w[key].setValue(L[key])
        w["opacity"].setValue(90)
        w["rows"].setCurrentIndex(max(0, w["rows"].findData(L["rows"])))
        w["bars"].setCurrentIndex(max(0, w["bars"].findData(L["bars"])))
        for key, _t, _w in COLUMNS:
            w["col_" + key].setChecked(True)
        w["compact"].setChecked(L["compact"])
        w["hide_names"].setChecked(L["hide_names"])
        self._apply_look()

    _previewing = False

    def preview_look(self):
        """Mostra o medidor com dados de exemplo por 10 s (só quando ele não está lendo o jogo)."""
        if self.reader:
            self._show_overlays()
            return
        demo = [(1, "Krul", "gl", 1_284_500, True, 0.34, 0.21), (2, "Aeris", "so", 1_102_300, False, 0.29, 0.12),
                (3, "Lunna", "ra", 865_900, False, 0.41, 0.09), (4, "Thoran", "te", 512_400, False, 0.18, 0.15),
                (5, "Mirae", "cl", 143_700, False, 0.12, 0.04), (6, "Kael", "as", 98_200, False, 0.37, 0.25)]
        snap = {"rows": [{"id": i, "name": n, "cls": c, "dmg": d, "me": me, "crit": cr, "multi": mu,
                          "dps": d / 75} for i, n, c, d, me, cr, mu in demo],
                "found_me": True, "active": True, "elapsed": 75, "my_heal": 0,
                "skills": {1: [{"skill": 1, "name": T("Golpe de exemplo"), "dmg": 642_000, "heal": 0, "hits": 31,
                                "crit": 11, "cls": "gl"},
                               {"skill": 2, "name": T("Outro golpe"), "dmg": 401_500, "heal": 0, "hits": 18,
                                "crit": 6, "cls": "gl"}]}}
        self._previewing = True
        self.sel_id = None
        self.on_live(snap)
        self.meter.restore_position()
        self._show_overlays()
        self.meter.set_locked(cfg.get("locked", False))
        QTimer.singleShot(10000, self._end_preview)

    def _end_preview(self):
        if not self._previewing:
            return
        self._previewing = False
        if not self.reader:
            self._hide_overlays()
            self._last = None
            self.meter.set_data(T("Bata em algo para começar"), 0, [])
            self.skills.set_data("", None, [])

    def display_name(self, r):
        cname = T(CLASSES[r["cls"]][0]) if r.get("cls") in CLASSES else ""
        if not r["me"] and look()["hide_names"]:
            return cname or T("Jogador")
        return r["name"] or (T("Você") if r["me"] else (cname or f"#{r['id']}"))

    # ------------------------------------------------------------------ medidor ao vivo
    def save_char_name(self):
        cfg["dps"]["char_name"] = self.char_name.text().strip()
        save()
        if self.hub.reader:
            self.hub.reader.self_name = cfg["dps"]["char_name"]
            self.hub.reader.self_id = None

    def _show_overlays(self):
        self.meter.show()
        self.meter._dock()
        if cfg["dps"].get("show_skills", True):
            self.skills.show()
        else:
            self.skills.hide()

    def _hide_overlays(self):
        self.meter.hide()
        self.skills.hide()

    def set_show_skills(self, on):
        cfg["dps"]["show_skills"] = on
        save()
        if self.meter.isVisible() and on:
            self.skills.show()
            self.meter._dock()
        else:
            self.skills.hide()

    def select_row(self, pid):
        snap = self._last
        if not snap or pid is None:
            return
        if any(r["id"] == pid for r in snap["rows"]):
            self.sel_id = pid
            self.on_live(snap)

    def set_mode(self, _i):
        cfg["dps"]["mode"] = self.mode.currentData()
        save()
        if self.reader:
            self.reader.mode = cfg["dps"]["mode"]

    def set_view(self, v):
        cfg["dps"]["view"] = v
        save()
        if self.hub.reader:
            self.hub.reader.view = v
            self.on_live(self.hub.reader.snapshot())

    def reset_fight(self):
        self.sel_id = None
        if self.reader:
            self.reader.reset()
            self.on_live(self.reader.snapshot())

    def set_show(self, on):
        cfg["dps"]["show_meter"] = on
        save()
        if self.reader and on:
            self._show_overlays()
            self.meter.set_locked(cfg.get("locked", False))
        else:
            self._hide_overlays()

    def set_opacity(self, v):
        cfg["dps"]["opacity"] = v / 100
        save()
        self.skills.setWindowOpacity(v / 100)
        self.meter.setWindowOpacity(v / 100)

    @property
    def reader(self):
        """A leitura do jogo, se o medidor estiver ligado (ela é dividida com o farm e os chefes de campo)."""
        return self.hub.reader if "dps" in self.hub.users else None

    def _hub_running(self, on):
        if not on and hasattr(self, "btn_live"):
            self.btn_live.setText(T("▶ Iniciar medidor"))
            self._hide_overlays()

    def toggle_live(self):
        if self.reader:
            self.hub.release("dps")
            self._hide_overlays()
            self.btn_live.setText(T("▶ Iniciar medidor"))
            self.live_status.setText(T("Medidor parado."))
            return
        if self.hub.acquire("dps"):
            self.live_status.setText(T("Precisa do Npcap e de abrir o overlay como administrador (veja acima)."))
            return
        self.hub.reader.mode = cfg["dps"].get("mode", "party")
        self.hub.reader.view = cfg["dps"].get("view", "fight")
        self.live_status.setText(T("Lendo o tráfego do jogo... bata em algo para começar."))
        self.btn_live.setText(T("■ Parar medidor"))
        if cfg["dps"].get("show_meter", True):
            self.meter.restore_position()
            self._show_overlays()
            self.meter.set_locked(cfg.get("locked", False))

    def on_live_status(self, msg):
        if msg.startswith("Lendo"):
            self.live_status.setText(T("Lendo o tráfego do jogo... bata em algo para começar."))
        elif msg.startswith("aviso:"):
            self.live_status.setText(msg[6:].strip())          # erro passageiro: o medidor continua
        else:
            self.live_status.setText(f"{T('Erro:')} {msg}")
            self.btn_live.setText(T("▶ Iniciar medidor"))      # o NetHub já parou a captura
            self._hide_overlays()

    def on_live(self, snap):
        rows = []
        for r in snap["rows"]:
            rows.append((self.display_name(r), r.get("cls"), r["dmg"], r["me"], r["crit"], r["multi"], r.get("dps"),
                         r["id"]))
        if cfg["dps"].get("mode") == "party" and not snap.get("found_me"):
            state = T("Procurando o seu personagem...")
        else:
            state = T("Em luta") if snap["active"] else (T("Última luta") if rows else "—")
            if cfg["dps"].get("view") == "session":
                state = T("Desde o zerar") if rows else "—"
        foot = f"{T('Sua cura')}: {snap['my_heal']:,}".replace(",", ".") if snap.get("my_heal") else ""
        self.meter.set_data(state, snap["elapsed"], rows, foot)
        # detalhe de habilidades: o jogador clicado; senão você; senão quem mais bateu
        self._last = snap
        ids = [r["id"] for r in snap["rows"]]
        who = self.sel_id if self.sel_id in ids else None
        if who is None:
            me = [r["id"] for r in snap["rows"] if r["me"]]
            who = me[0] if me else (max(snap["rows"], key=lambda r: r["dmg"])["id"] if snap["rows"] else None)
        r = next((x for x in snap["rows"] if x["id"] == who), None)
        if r:
            self.skills.set_data(self.display_name(r), r.get("cls"), snap.get("skills", {}).get(who, []))
        else:
            self.skills.set_data("", None, [])

    def shutdown(self):
        if self.reader:
            self.hub.release("dps")
            self._hide_overlays()
            if hasattr(self, "btn_live"):
                self.btn_live.setText(T("▶ Iniciar medidor"))
        if self.thread:
            self.toggle_record()

    # ------------------------------------------------------------------
    def set_enabled(self, on, init=False):
        cfg.setdefault("dps", {})["enabled"] = on
        save()
        self.body.setEnabled(on)
        if not on:
            self.shutdown()
        if on:
            ok, err = deps_ok()
            if not ok:
                self.status.setText(f"Falta instalar componentes: {err}. Rode o INICIAR.bat de novo.")
                self.body.setEnabled(False)
                return
            self.refresh_requirements()
            if not init:
                self.refresh_procs()

    def refresh_requirements(self):
        npcap, admin = npcap_installed(), is_admin()
        self.btn_npcap.setVisible(not npcap)
        self.btn_admin.setVisible(not admin)
        if npcap and admin:
            self.req_label.setText("<span style='color:#3fb950'>✓ " + T("Npcap instalado") + " · ✓ " +
                                   T("administrador") + "</span>")
        else:
            falta = [T(t) for t, ok in (("instalar o Npcap", npcap), ("abrir como administrador", admin)) if not ok]
            self.req_label.setText("<span style='color:#f0883e'>" + T("Falta:") + " " +
                                   (" " + T("e") + " ").join(falta) + "</span>")

    def install_npcap(self):
        """Baixa o instalador oficial, confere que é ele mesmo (SHA-256 fixado no build + assinatura digital
        da Nmap Software LLC) e só então abre (o Windows pede permissão de administrador)."""
        import tempfile
        import threading
        import urllib.request
        url, sha = npcap_source()
        dest = os.path.join(tempfile.mkdtemp(prefix="metaoverlay-npcap-"), "npcap-setup.exe")
        self.btn_npcap.setEnabled(False)
        self.req_label.setText(T("Baixando o Npcap..."))

        def work():
            try:
                if not url.startswith("https://npcap.com/"):
                    raise ValueError("endereço inesperado")
                with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
                    if not r.geturl().startswith("https://"):
                        raise ValueError("redirecionado para fora do https")
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        if f.tell() > 50_000_000:
                            raise ValueError("arquivo grande demais")
                ok = os.path.getsize(dest) > 1_000_000 and verify_npcap(dest, sha)
            except Exception:
                ok = False
            if not ok:
                try:
                    os.remove(dest)
                except OSError:
                    pass
            QTimer.singleShot(0, lambda: self._npcap_downloaded(ok, dest))

        threading.Thread(target=work, daemon=True).start()

    def _npcap_downloaded(self, ok, dest):
        self.btn_npcap.setEnabled(True)
        if ok and hasattr(os, "startfile"):
            QMessageBox.information(self, "Npcap", T(NPCAP_HOWTO))
            os.startfile(dest)
            self.req_label.setText(T("Instalador do Npcap aberto. Termine a instalação e reabra como administrador."))
        else:
            self.req_label.setText(T("Não deu para baixar ou conferir o instalador agora; abrindo a página oficial."))
            QDesktopServices.openUrl(QUrl("https://npcap.com/#download"))

    def reopen_admin(self):
        import instance
        instance.release()
        if restart_as_admin():
            # A cópia nova (administrador) já está abrindo: esta fecha de vez. Antes era só um
            # QApplication.quit(), que o Qt 6 cancela quando a janela do painel recusa fechar (ela vai
            # para a bandeja) — o programa antigo ficava rodando escondido.
            if self.quit_app:
                self.quit_app()
            else:
                from PySide6.QtWidgets import QApplication
                QApplication.instance().exit(0)
        else:
            instance.acquire()           # recusou o pedido do Windows: continua aberto e volta a marcar que está

    def refresh_procs(self):
        self.proc.clear()
        try:
            for name, pid, n in list_game_processes():
                self.proc.addItem(f"{name}  (PID {pid}, {n} {T('conexões')})", pid)
        except Exception as e:
            self.status.setText(f"Erro ao listar processos: {e}")

    def toggle_record(self):
        if self.thread:
            self.thread.stop()
            self.thread = None
            if self.marks_file:
                self.marks_file.close()
                self.marks_file = None
            self.rec.setText(T("● Gravar"))
            self.status.setText(f"{T('Captura salva:')} {self.current}")
            return
        if self.proc.count() == 0:
            self.refresh_procs()
        pid = self.proc.currentData()
        if pid is None:
            QMessageBox.information(self, "DPS", T("Escolha o processo do jogo."))
            return
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current = os.path.join(CAPTURE_DIR, f"aion2_{stamp}.pcap")
        self.marks_file = open(self.current.replace(".pcap", "_marcas.txt"), "w", encoding="utf-8")
        self.t0 = time.time()
        self.thread = CaptureThread(pid, self.current)
        self.thread.stats.connect(lambda n, by: self.status.setText(
            f"Gravando… {n} pacotes, {by / 1024:.0f} KB, {time.time() - self.t0:.0f} s"))
        self.thread.error.connect(self.on_error)
        self.thread.endpoints.connect(lambda e: self.ep_label.setText(f"{T('Servidores do jogo:')} {e}"))
        self.thread.start()
        self.rec.setText(T("■ Parar"))

    def on_error(self, msg):
        hint = ""
        if "Permission" in msg or "admin" in msg.lower() or "Npcap" in msg or "winpcap" in msg.lower():
            hint = " — confira se o Npcap está instalado e se o overlay foi aberto como Administrador."
        self.status.setText(f"Erro: {msg}{hint}")
        if self.thread:
            self.thread = None
            self.rec.setText("● Gravar")

    def mark(self):
        if not self.marks_file:
            return
        t = time.time()
        line = f"{datetime.datetime.fromtimestamp(t):%H:%M:%S.%f}\t+{t - self.t0:.3f}s\t{self.mark_text.text()}\n"
        self.marks_file.write(line)
        self.marks_file.flush()
        self.mark_text.clear()
        self.status.setText(self.status.text() + "  ✓ marcado")
