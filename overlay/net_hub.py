"""Uma única leitura do tráfego do jogo, dividida entre quem precisa dela.

O medidor de DPS, o farm de pet (abates automáticos) e os chefes de campo (mortes automáticas) usam o
mesmo DpsReader. Cada um "pede" a leitura (acquire) e "devolve" (release); ela só para quando ninguém
mais precisa.
"""
from PySide6.QtCore import QObject, Signal

from config import cfg, save


class NetHub(QObject):
    updated = Signal(object)          # estado da luta (medidor de DPS)
    status = Signal(str)              # texto de estado / erro
    kill = Signal(object)             # dict do world_live (um monstro morreu)
    soul = Signal(object)             # {"pet": id, "n": quantidade}: você ganhou alma de pet
    world = Signal(object)            # id do mapa atual (str) quando muda
    running_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.reader = None
        self.users = set()
        self.last_status = ""

    # ------------------------------------------------------------ requisitos
    @staticmethod
    def requirements():
        """(ok, falta) — o mesmo que o medidor de DPS precisa."""
        from dps_capture import is_admin, npcap_installed
        npcap, admin = npcap_installed(), is_admin()
        falta = [t for t, ok in (("Npcap", npcap), ("administrador", admin)) if not ok]
        return not falta, falta

    @property
    def running(self):
        return self.reader is not None

    def acquire(self, who):
        """Liga a leitura (se ainda não estiver). Devolve None ou o motivo de não ter ligado."""
        ok, falta = self.requirements()
        if not ok:
            return falta
        self.users.add(who)
        if self.reader is None:
            from dps_capture import game_server_hosts
            from dps_live import DpsReader
            r = DpsReader(game_server_hosts())
            r.self_name = cfg.get("dps", {}).get("char_name", "")
            r.mode = cfg.get("dps", {}).get("mode", "party")
            r.view = cfg.get("dps", {}).get("view", "fight")
            r.enable_world()
            r.updated.connect(self._on_updated)
            r.status.connect(self._on_status)
            r.world_events.connect(self._on_world)
            self.reader = r
            r.start()
            self.running_changed.emit(True)
        return None

    def release(self, who):
        self.users.discard(who)
        if not self.users and self.reader is not None:
            self.stop()

    def stop(self):
        r, self.reader = self.reader, None
        self.users.clear()
        if r is not None:
            r.stop()
            self.running_changed.emit(False)

    # ------------------------------------------------------------ repasse
    def _on_updated(self, snap):
        # aprende o nome do seu personagem sozinho (ajuda a reconhecer os seus abates nas próximas vezes)
        d = cfg.setdefault("dps", {})
        if not d.get("char_name"):
            for row in snap.get("rows", []):
                if row.get("me") and row.get("name"):
                    d["char_name"] = row["name"]
                    save()
                    if self.reader:
                        self.reader.self_name = row["name"]
                    break
        self.updated.emit(snap)

    def _on_status(self, msg):
        self.last_status = msg
        self.status.emit(msg)
        if not (msg.startswith("Lendo") or msg.startswith("aviso:")):
            self.stop()                       # erro de verdade: a captura parou

    def _on_world(self, events):
        for kind, ev in events:
            if kind == "kill":
                d = cfg.setdefault("dps", {})
                if (not d.get("char_name") and ev.get("killer") and self.reader
                        and ev.get("killer_id") == self.reader.find_self()):
                    d["char_name"] = ev["killer"]          # o servidor disse o nome de quem matou: é você
                    self.reader.self_name = ev["killer"]
                    save()
                self.kill.emit(ev)
            elif kind == "soul":
                self.soul.emit(ev)
            elif kind == "world":
                self.world.emit(ev["world"])

    def world_state(self):
        if self.reader is None:
            return None, None
        return self.reader.world_state()
