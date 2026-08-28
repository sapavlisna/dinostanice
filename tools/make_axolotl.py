"""Postavi plavajiciho axolotla z modelu, ktery prisel bez kostry.

Stejny pripad jako ptakojester (viz tools/make_pteranodon.py a CREDITS.md):
rigovany axolotl pod otevrenou licenci neexistuje, staticky ano. Prace je ale
kratsi — zdroj je jediny mesh, uz soumerny podle osy x a narovnany do os
(x sirka, y vyska, z delka, hlava na +z), takze narovnavani ani zrcadleni
poloviny netreba. Zbyva rozdelit tvora na casti, odvodit z nich kostru a
dopsat plavani.

    python tools/make_axolotl.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dinostanice.glbexport import write_skinned
from dinostanice.gltf import Model

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/models_src/axolotl_static.glb"
DST = ROOT / "data/models_src/axolotl.glb"

# Kloub kostry na kazdy uzel retezu, v podilu delky tela od hlavy k ocasu.
# Axolotl plave ocasem, trup drzi skoro rovny, takze vazna cast vlneni pripada
# na posledni dva clanky.
SPINE = {"Head": 0.30, "Body": 0.00, "Tail1": -0.25, "Tail2": -0.55, "Tail3": -0.80}
CHAIN = ["Head", "Body", "Tail1", "Tail2", "Tail3"]

YAW_DEG = {"Head": 3.5, "Tail1": 7.0, "Tail2": 13.0, "Tail3": 21.0}
LAG = {"Head": 0.0, "Tail1": 0.14, "Tail2": 0.27, "Tail3": 0.40}
GILL_DEG = 7.0           # rozkmit vejire zaber
GILL_BEATS = 2.5         # kolikrat se zabry zachveji za jeden kmit ocasu
# Zabry se jen chveji, natrvalo se nikam nepreklapeji. Zkouseno bylo oboji:
# zamest stonky dopredu podel hlavy pridalo na predloze 15,6 -> 17,4 %
# obrysovych pixelu zaber, ale z boku pak trci proti smeru plavani, a zamest
# je dozadu je zase v pohledu shora nazene na predni nohy (13,4 %). Vlastni
# poloha z modelu vyhrava na oboji.
PERIOD = 2.4             # axolotl se sune line, ne jako ryba
FRAMES = 30

PARTS = ("head", "trunk", "leg", "gill")
# Material na cast tela: predloha z hranic materialu bere vnitrni linky, takze
# dite dostane obtazene nohy a zabry misto jedine velke plochy (zdroj ma
# material jediny). Hlava a trup jdou do jednoho: jejich skorapky se u sije
# prostupuji, takze nejblizsi plocha se tam strida a hranice by vysla
# roztrepana jako pila.
GROUP = {"head": 0, "trunk": 0, "leg": 1, "gill": 2}
GROUP_COLOURS = [[0.76, 0.55, 0.58], [0.70, 0.50, 0.53], [0.86, 0.46, 0.52]]


def shells(tris: np.ndarray, count: int) -> list[np.ndarray]:
    """Rozdeli mesh na kusy spojene hranou.

    Zdroj neni svareny: kazda anatomicka cast (hlava, trup, noha, zaberni
    stonek) je vlastni skorapka a osa soumernosti mesh navic puli, takze kazda
    cast vyjde dvakrat — presne to, co je pro kostru potreba.
    """
    parent = list(range(count))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in tris:
        for x, y in ((a, b), (b, c)):
            ra, rb = find(x), find(y)
            if ra != rb:
                parent[rb] = ra

    groups: dict[int, list[int]] = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    return [np.array(v, np.int64) for v in groups.values()]


def classify(verts: np.ndarray, parts: list[np.ndarray]) -> np.ndarray:
    """Kazdemu kusu priradi cast tela: hlava, trup, noha, zabry.

    Rozhoduje geometrie, ne velikost: nohy visi pod bricho, zaberni stonky
    trci do stran za hlavou a drobne kusy (ocni bulvy na cenichu) nedelaji ani
    jedno, takze padnou k hlave.
    """
    z = verts[:, 2]
    tail_end, snout = z.min(), z.max()
    label = np.full(len(parts), "head", "<U5")

    trunk = [i for i, p in enumerate(parts) if verts[p, 2].min() < tail_end + 1e-6]
    for i in trunk:
        label[i] = "trunk"
    head = [i for i, p in enumerate(parts) if verts[p, 2].max() > snout - 1e-6]

    belly = min(verts[parts[i], 1].min() for i in trunk)
    flank = max(np.abs(verts[parts[i], 0]).max() for i in trunk)
    for i, p in enumerate(parts):
        if i in trunk or i in head:
            continue
        if verts[p, 1].min() < belly:
            label[i] = "leg"
        elif np.abs(verts[p, 0]).max() > flank:
            label[i] = "gill"
    return label


def build_rig(verts: np.ndarray, part: np.ndarray, gill_side: np.ndarray):
    """Kostra ze segmentace: retez podel osy tela a dva vejire zaber.

    Nohy vlastni kloub nemaji zamerne — axolotl je pri plavani nese s telem,
    visi pod nim a nekopou. Kazdy vrchol proto bere vahu z retezu podle sve
    pozice na ose (`_chain_weights`), takze noha jde s tim clankem trupu, ke
    kteremu patri, a nic se nemusi rozpoznavat navic.
    """
    length = float(np.ptp(verts[:, 2]))
    knots = np.array([SPINE[n] for n in CHAIN]) * length
    head_y = float(verts[part == "head", 1].mean())

    skeleton = [("Body", -1, (0.0, 0.0, 0.0))]
    index = {"Body": 0}
    for name in ("Head", "Tail1", "Tail2", "Tail3"):
        parent = {"Head": "Body", "Tail1": "Body", "Tail2": "Tail1", "Tail3": "Tail2"}[name]
        dz = SPINE[name] * length - SPINE[parent] * length
        dy = head_y if name == "Head" else 0.0
        index[name] = len(skeleton)
        skeleton.append((name, index[parent], (0.0, dy, dz)))

    gill = part == "gill"
    for side, sign in (("L", 1.0), ("R", -1.0)):
        sel = gill & (gill_side == sign)
        base = verts[sel].mean(0) if sel.any() else verts.mean(0)
        # kloub lezi u koreni stonku, ne v jeho tezisti: vejir se ma sklapet
        # od hlavy, ne rotovat kolem sveho stredu
        base = np.array([sign * 0.25 * abs(base[0]), base[1], base[2]])
        head_origin = np.array([0.0, head_y, SPINE["Head"] * length])
        index[f"Gill{side}"] = len(skeleton)
        skeleton.append((f"Gill{side}", index["Head"], tuple(base - head_origin)))

    joints = np.zeros((len(verts), 4), np.uint8)
    weights = np.zeros((len(verts), 4), np.float32)
    lo, hi, blend = _chain_weights(verts[:, 2], knots)
    joints[:, 0] = [index[CHAIN[i]] for i in lo]
    joints[:, 1] = [index[CHAIN[i]] for i in hi]
    weights[:, 0] = 1.0 - blend
    weights[:, 1] = blend

    # zabry visi cele na svem kloubu, jen u koreni se preleji do hlavy, aby
    # vejir pri sklapeni neodjel od lebky
    for side, sign in (("L", 1.0), ("R", -1.0)):
        sel = gill & (gill_side == sign)
        if not sel.any():
            continue
        reach = np.abs(verts[sel, 0]).max()
        out = np.clip(np.abs(verts[sel, 0]) / max(reach, 1e-9), 0, 1)
        joints[sel, 2] = index[f"Gill{side}"]
        weights[sel, 2] = out
        weights[sel, 0] *= 1.0 - out
        weights[sel, 1] *= 1.0 - out
    return skeleton, joints, weights, index


def _chain_weights(z: np.ndarray, knots: np.ndarray):
    """Pro kazdy vrchol dva sousedni clanky retezu a jejich pomer.

    Knots jdou od hlavy k ocasu (klesajici z); za krajnimi uzly se vaha
    zaklapne na jedinou, takze cenich a spicka ocasu jdou cele s nimi.
    """
    lo = np.zeros(len(z), np.int64)
    blend = np.zeros(len(z))
    for i in range(len(knots) - 1):
        a, b = knots[i], knots[i + 1]
        sel = (z <= a) & (z > b) if i else (z > b)
        lo[sel] = i
        blend[sel] = np.clip((a - z[sel]) / (a - b), 0, 1)
    tail = z <= knots[-1]
    lo[tail] = len(knots) - 2
    blend[tail] = 1.0
    return lo, lo + 1, blend


def _axis_quat(angle: np.ndarray, axis: int) -> np.ndarray:
    q = np.zeros((len(angle), 4), np.float32)
    q[:, axis] = np.sin(angle / 2)
    q[:, 3] = np.cos(angle / 2)
    return q


def swim(index: dict) -> dict:
    """Klip plavani: vlna probehne podel osy tela, zabry se chveji rychleji."""
    times = np.linspace(0.0, PERIOD, FRAMES + 1)
    channels = {}

    for name, deg in YAW_DEG.items():
        phase = 2 * np.pi * (times / PERIOD - LAG[name])
        sign = -1.0 if name == "Head" else 1.0    # hlava jde proti vlne
        channels[index[name]] = (times, _axis_quat(sign * np.radians(deg) * np.sin(phase), 1))

    for side, sign in (("L", 1.0), ("R", -1.0)):
        phase = 2 * np.pi * GILL_BEATS * times / PERIOD
        channels[index[f"Gill{side}"]] = (
            times, _axis_quat(sign * np.radians(GILL_DEG) * np.sin(phase), 2))
    return {"Swim": channels}


def main() -> None:
    model = Model(SRC)
    verts, normals = model.posed(None, 0.0)
    verts = verts - np.array([0.0, verts[:, 1].mean(), verts[:, 2].mean()])

    pieces = shells(model.indices, len(verts))
    label = classify(verts, pieces)
    part = np.empty(len(verts), "<U5")
    side = np.zeros(len(verts))
    for i, p in enumerate(pieces):
        part[p] = label[i]
        side[p] = 1.0 if verts[p, 0].mean() >= 0 else -1.0

    skeleton, joints, weights, index = build_rig(verts, part, side)

    group = np.array([GROUP[part[t[0]]] for t in model.indices], np.int32)
    write_skinned(DST, verts=verts, normals=normals, tris=model.indices,
                  tri_group=group, colours=GROUP_COLOURS, joints=joints,
                  weights=weights, skeleton=skeleton, clips=swim(index))

    counts = {name: int((part == name).sum()) for name in PARTS}
    print(f"{DST} ({DST.stat().st_size // 1024} kB)")
    print(f"{len(verts)} vrcholu, {len(model.indices)} trojuhelniku, "
          f"delka {np.ptp(verts[:, 2]):.2f}, sirka {np.ptp(verts[:, 0]):.2f}")
    print(f"casti: {counts}, kloubu {len(skeleton)}")


if __name__ == "__main__":
    main()
