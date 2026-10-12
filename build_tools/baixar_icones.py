"""Baixa os ícones das habilidades (uma vez, ao gerar o instalador) e salva como PNG em overlay/skill_icons.

O programa instalado não acessa a internet para isso: os ícones vão dentro do instalador.
Se algum download falhar, o medidor mostra as iniciais da habilidade no lugar do ícone.
"""
import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "overlay")
OUT = os.path.join(SRC, "skill_icons")
BASE = "https://aion2.app/db-item-icons/"


def _baixar(nome):
    """Tenta .webp, depois .png e .avif. Devolve a imagem (Pillow) ou None."""
    from PIL import Image
    for ext in (".webp", ".png", ".avif"):
        try:
            req = urllib.request.Request(BASE + nome + ext, headers={
                "User-Agent": "Mozilla/5.0", "Accept": "image/webp,image/png,image/*;q=0.8"})
            data = urllib.request.urlopen(req, timeout=20).read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            continue
    return None


def main():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow não instalado; pulando ícones.")
        return 0
    try:
        import pillow_avif  # noqa: F401  (só se existir; ajuda com ícones em AVIF)
    except ImportError:
        pass
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(SRC, "data", "skills.json"), encoding="utf-8") as f:
        names = sorted({v[2] for v in json.load(f).values()})
    ok = skip = 0
    falhas = []
    for i, n in enumerate(names, 1):
        dest = os.path.join(OUT, n + ".png")
        if os.path.exists(dest):
            skip += 1
            continue
        im = _baixar(n)
        if im is None:
            falhas.append(n)
        else:
            im.thumbnail((64, 64))
            im.save(dest)
            ok += 1
        if i % 30 == 0 or i == len(names):
            print(f"  {i}/{len(names)} ícones verificados...")
    print(f"Ícones de habilidade: {ok} baixados, {skip} já existiam, {len(falhas)} indisponíveis.")
    if falhas:
        print("  (sem problema: essas habilidades aparecem com as iniciais no lugar do ícone)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
