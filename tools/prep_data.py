"""Gera overlay/data/resources.json e mobs.json a partir de data/export_pt.json (dados do questlog, em português)."""
import json, os, re, unicodedata
from matplotlib.path import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw = json.load(open(os.path.join(ROOT, 'data', 'export_pt.json'), encoding='utf-8'))
WORLDS = {
    '1010': ('Verteron', 'Elyos'), '1011': ('Eltnen', 'Elyos'),
    '1110': ('Altgard', 'Asmodian'), '1111': ('Morheim', 'Asmodian'),
    '20': ('Reshanta Inferior', 'Abismo'), '21': ('Reshanta Inferior (2)', 'Abismo'),
    '22': ('Reshanta Média', 'Abismo'), '23': ('Reshanta Superior', 'Abismo'),
}
out = {'names': raw['names'], 'worlds': {}}
for wid, (name, fac) in WORLDS.items():
    regs = [r for r in raw['regs'] if r['w'] == wid]
    paths = [(r['r'], r['n'], [Path(p) for p in r['p'] if len(p) > 2]) for r in regs]
    pts = []
    for w, cat, ni, x, y in raw['pts']:
        if w != wid:
            continue
        best = None
        for rank, rn, ps in paths:
            if any(p.contains_point((x, y)) for p in ps) and (best is None or rank > best[0]):
                best = (rank, rn)
        pts.append([cat, ni, x, y, best[1] if best else ''])
    out['worlds'][wid] = {
        'name': name, 'faction': fac,
        'regions': [{'n': r['n'], 'k': r['k'], 'r': r['r'], 'l': r['l'], 'p': r['p']} for r in regs],
        'points': pts,
        'rifts': [[x, y] for w, n, x, y in raw['rifts'] if w == wid],
    }
    print(wid, name, len(pts), 'pontos', len(regs), 'regiões', len(out['worlds'][wid]['rifts']), 'rifts')
json.dump(out, open(os.path.join(ROOT, 'overlay', 'data', 'resources.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))

# ---------------------------------------------------------------- monstros + sugestão de pet
old = json.load(open(os.path.join(ROOT, 'overlay', 'data', 'mobs.json'), encoding='utf-8'))
pets = old['pets']
norm = lambda s: unicodedata.normalize('NFKD', s.lower()).encode('ascii', 'ignore').decode()
worlds, sugg = {}, {}
for w, v in raw['mons'].items():
    lst = []
    for k, coords in v.items():
        name, cat = k.split('\t')
        lst.append([name, cat, coords])
        if name not in sugg:
            hits = [p for p in pets if re.search(r'\b' + re.escape(norm(p[1])) + r'\b', norm(name))]
            if hits:
                sugg[name] = max(hits, key=lambda p: len(p[1]))[0]
    lst.sort(key=lambda m: norm(m[0]))
    worlds[w] = lst
json.dump({'worlds': worlds, 'pets': pets, 'suggest': sugg, 'leveling': old['leveling']},
          open(os.path.join(ROOT, 'overlay', 'data', 'mobs.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print('mobs ok', {w: len(v) for w, v in worlds.items()})
