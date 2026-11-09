"""Postaví hvězdu: plochá pěticípá hvězda s kostrou a klipem `Twinkle`.

    python tools/make_star.py

Hvězda stojí v rovině x–y a kouká k +Z (zepředu je to bokorys předlohy). Každý
cíp je zvlášť materiál, takže z hranic materiálů vzniknou vnitřní linky a dítě
může každý cíp vybarvit jinak. Klip `Twinkle` ji jen houpe a natáčí kolem
svislé osy, scéna k tomu přidá pulzování velikosti.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dinostanice.glbexport import write_skinned  # noqa: E402
from make_bird import axis_quat, qmul  # noqa: E402

DST = ROOT / "data/models_src/star.glb"

OUTER, INNER, HALF_DEPTH = 0.5, 0.21, 0.035
PERIOD = 3.0
FRAMES = 24


def build():
    pts = []
    for i in range(10):
        ang = np.pi / 2 + i * np.pi / 5
        r = OUTER if i % 2 == 0 else INNER
        pts.append((r * np.cos(ang), r * np.sin(ang)))
    verts, normals, tris, group = [], [], [], []

    def add_tri(a, b, c, n, g):
        base = len(verts)
        verts.extend([a, b, c])
        normals.extend([n, n, n])
        tris.append([base, base + 1, base + 2])
        group.append(g)

    for i in range(10):
        p0, p1 = np.array(pts[i]), np.array(pts[(i + 1) % 10])
        g = ((i + 1) // 2) % 5          # cíp: špička a obě sousední hrany
        f0, f1 = [*p0, HALF_DEPTH], [*p1, HALF_DEPTH]
        b0, b1 = [*p0, -HALF_DEPTH], [*p1, -HALF_DEPTH]
        add_tri([0, 0, HALF_DEPTH], f0, f1, [0, 0, 1], g)
        add_tri([0, 0, -HALF_DEPTH], b1, b0, [0, 0, -1], g)
        edge = p1 - p0
        n = np.array([edge[1], -edge[0], 0.0])
        n /= np.linalg.norm(n)
        add_tri(f0, b0, f1, n, g)
        add_tri(f1, b0, b1, n, g)
    return np.array(verts, float), np.array(normals, float), np.array(tris), np.array(group, np.int32)


def clips():
    times = np.linspace(0.0, PERIOD, FRAMES + 1)
    quats = []
    for t in times:
        ph = 2 * np.pi * t / PERIOD
        roll = axis_quat([0, 0, 1], np.radians(7 * np.sin(ph)))
        sway = axis_quat([0, 1, 0], np.radians(14 * np.sin(ph + 1.3)))
        quats.append(qmul(roll, sway))
    return {"Twinkle": {0: (times, np.array(quats))}}


def main():
    verts, normals, tris, group = build()
    n = len(verts)
    joints = np.zeros((n, 4), np.uint8)
    weights = np.zeros((n, 4), np.float32)
    weights[:, 0] = 1.0
    colours = [[1.0, 0.82, 0.25], [1.0, 0.78, 0.2], [1.0, 0.85, 0.3], [0.98, 0.8, 0.22],
               [1.0, 0.84, 0.28]]
    write_skinned(DST, verts=verts, normals=normals, tris=tris, tri_group=group, colours=colours,
                  joints=joints, weights=weights, skeleton=[("Body", -1, (0.0, 0.0, 0.0))],
                  clips=clips())
    print(f"{DST} ({DST.stat().st_size // 1024} kB), {n} vrcholů")


if __name__ == "__main__":
    main()
