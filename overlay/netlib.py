"""Carrega só a parte do scapy que o leitor do jogo usa.

Antes era `from scapy.all import ...`, que carrega uns 200 protocolos (Wi-Fi, Bluetooth, USB...):
+72 MB de memória e ~0,6 s para ligar. Com só Ethernet/IP/TCP (+ PPP/PPPoE e loopback, para quem usa
VPN ou discagem) fica em ~43 MB e ~0,2 s. Se algo faltar, cai no scapy.all como antes.
"""
from types import SimpleNamespace

_lib = None


def load():
    global _lib
    if _lib is not None:
        return _lib
    try:
        import scapy.arch  # noqa: F401  (Npcap no Windows: interfaces, rotas e sockets de captura)
        import scapy.layers.l2  # noqa: F401  (Ethernet, loopback)
        import scapy.layers.ppp  # noqa: F401  (PPP / PPPoE)
        from scapy.config import conf
        from scapy.layers.inet import IP, TCP
        from scapy.sendrecv import AsyncSniffer
        from scapy.utils import PcapWriter
    except Exception:
        from scapy.all import IP, TCP, AsyncSniffer, PcapWriter, conf
    _lib = SimpleNamespace(IP=IP, TCP=TCP, AsyncSniffer=AsyncSniffer, PcapWriter=PcapWriter, conf=conf)
    return _lib
