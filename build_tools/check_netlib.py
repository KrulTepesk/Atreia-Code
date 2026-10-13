"""CI (Windows): o carregamento enxuto do scapy (overlay/netlib.py) tem que dar o mesmo resultado do
scapy.all nas partes que o leitor usa: sockets de captura do Npcap e tipos de enlace."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = r'''
import json, sys
sys.path.insert(0, %r)
if sys.argv[1] == "full":
    import scapy.all
    from scapy.config import conf
else:
    import netlib
    conf = netlib.load().conf
n = lambda x: getattr(x, "__name__", str(type(x).__name__))
print(json.dumps({"L2listen": n(conf.L2listen), "L2socket": n(conf.L2socket), "L3socket": n(conf.L3socket),
                  "use_pcap": bool(getattr(conf, "use_pcap", False)),
                  "l2types": sorted(int(k) for k in conf.l2types.num2layer)}))
''' % os.path.join(ROOT, "overlay")


def probe(kind):
    out = subprocess.run([sys.executable, "-c", PROBE, kind], capture_output=True, text=True, timeout=120)
    if out.returncode:
        print(out.stderr)
        raise SystemExit(f"falhou ao carregar ({kind})")
    return json.loads(out.stdout.strip().splitlines()[-1])


full, slim = probe("full"), probe("slim")
print("full:", {k: v for k, v in full.items() if k != "l2types"})
print("slim:", {k: v for k, v in slim.items() if k != "l2types"})
problems = [k for k in ("L2listen", "L2socket", "L3socket", "use_pcap") if full[k] != slim[k]]
# Ethernet, NULL/loopback, IP puro (VPN), Linux cooked, PPP/PPPoE
needed = {1, 0, 12, 14, 101, 108, 113, 9, 51, 204}
missing = sorted((needed & set(full["l2types"])) - set(slim["l2types"]))
if problems or missing:
    raise SystemExit(f"netlib diferente do scapy.all: {problems} tipos de enlace faltando: {missing}")
print("::notice title=Teste::netlib igual ao scapy.all (sockets de captura e tipos de enlace)")
