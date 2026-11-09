"""Postaví motýlka: plochý nízkopolygonový motýl s kostrou a dvěma klipy.

    python tools/make_butterfly.py

Stejný princip jako `make_bird.py`, jen jinak orientovaný: motýl se kreslí zepředu,
s křídly rozloženými do roviny x–y a tělem podél osy y (hlava nahoře). V klidové
póze jsou křídla rozevřená — v ní se z něj dělá předloha k vybarvení (pohled
shora, obě křídla vidět celá). Klip `Fly` jimi mává (křídla se skládají dozadu
a zase otevírají, zadní pár s drobným zpožděním), `Rest` je pomalé pohupování
napůl složenými křídly pro chvíle, kdy sedí na květu.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dinostanice.glbexport import write_skinned  # noqa: E402
from make_bird import axis_quat, cone, ellipsoid  # noqa: E402

DST = ROOT / "data/models_src/butterfly.glb"

FLY_PERIOD = 0.36
REST_PERIOD = 3.2
FRAMES = 18


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def build():
    parts = []

    def add(shape, group, label):
        parts.append((*shape, group, label))

    add(ellipsoid((0, 0, 0), (0.045, 0.24, 0.045), nu=10, nv=9), 0, "body")             # tělo
    add(ellipsoid((0, 0.29, 0.01), (0.06, 0.06, 0.06), nu=10, nv=7), 1, "head")          # hlava
    for sx in (1, -1):
        add(cone((sx * 0.02, 0.33, 0.01), (sx * 0.13, 0.52, 0.01), 0.008, n=5), 2, "head")  # tykadlo
        add(ellipsoid((sx * 0.30, 0.13, 0.0), (0.30, 0.21, 0.012),
                      rot=rot_z(sx * np.radians(22)), nu=18, nv=9), 3,
            "wingL" if sx > 0 else "wingR")                                              # přední křídlo
        add(ellipsoid((sx * 0.21, -0.15, 0.0), (0.19, 0.17, 0.012),
                      rot=rot_z(sx * np.radians(-24)), nu=16, nv=9), 4,
            "hindL" if sx > 0 else "hindR")                                              # zadní křídlo

    offset, V, N, T, G, L = 0, [], [], [], [], []
    for v, n, t, g, label in parts:
        L.extend([label] * len(v))
        V.append(v)
        N.append(n)
        T.append(t + offset)
        G.append(np.full(len(t), g, np.int32))
        offset += len(v)
    return np.vstack(V), np.vstack(N), np.vstack(T), np.concatenate(G), np.array(L)


def rig(label):
    n = len(label)
    joints = np.zeros((n, 4), np.uint8)
    weights = np.zeros((n, 4), np.float32)
    weights[:, 0] = 1.0
    # 0 Body, 1 WingL, 2 WingR, 3 HindL, 4 HindR, 5 Head
    for name, joint in (("wingL", 1), ("wingR", 2), ("hindL", 3), ("hindR", 4), ("head", 5)):
        m = label == name
        joints[m, 0] = joint
    skeleton = [
        ("Body", -1, (0.0, 0.0, 0.0)),
        ("WingL", 0, (0.04, 0.06, 0.0)),
        ("WingR", 0, (-0.04, 0.06, 0.0)),
        ("HindL", 0, (0.04, -0.04, 0.0)),
        ("HindR", 0, (-0.04, -0.04, 0.0)),
        ("Head", 0, (0.0, 0.29, 0.0)),
    ]
    return skeleton, joints, weights


def clips():
    q_id = np.array([0.0, 0.0, 0.0, 1.0])
    fly_t = np.linspace(0.0, FLY_PERIOD, FRAMES + 1)
    rest_t = np.linspace(0.0, REST_PERIOD, FRAMES + 1)

    def track(times, fn):
        return times, np.array([fn(t) for t in times])

    fly, rest = {}, {}
    for joint, sign, lag, amp in ((1, 1.0, 0.0, 1.0), (2, -1.0, 0.0, 1.0),
                                  (3, 1.0, 0.10, 0.8), (4, -1.0, 0.10, 0.8)):
        def wing(t, sign=sign, lag=lag, amp=amp):
            ph = 2 * np.pi * (t / FLY_PERIOD - lag)
            return axis_quat([0, 1, 0], sign * np.radians(34 + 30 * amp * np.sin(ph)))

        def calm(t, sign=sign, lag=lag):
            ph = 2 * np.pi * (t / REST_PERIOD - lag)
            return axis_quat([0, 1, 0], sign * np.radians(62 + 10 * np.sin(ph)))

        fly[joint] = track(fly_t, wing)
        rest[joint] = track(rest_t, calm)
    fly[0] = track(fly_t, lambda t: axis_quat([1, 0, 0], np.radians(6 * np.sin(2 * np.pi * t / FLY_PERIOD + 1.0))))
    rest[0] = (rest_t, np.tile(q_id, (len(rest_t), 1)))
    fly[5] = (fly_t, np.tile(q_id, (len(fly_t), 1)))
    rest[5] = track(rest_t, lambda t: axis_quat([0, 0, 1], np.radians(8 * np.sin(2 * np.pi * t / REST_PERIOD * 2))))
    return {"Fly": fly, "Rest": rest}


def main():
    verts, normals, tris, group, label = build()
    skeleton, joints, weights = rig(label)
    colours = [[0.25, 0.20, 0.18], [0.30, 0.24, 0.20], [0.25, 0.20, 0.18],
               [0.95, 0.60, 0.15], [0.90, 0.45, 0.15]]
    write_skinned(DST, verts=verts, normals=normals, tris=tris, tri_group=group,
                  colours=colours, joints=joints, weights=weights, skeleton=skeleton,
                  clips=clips())
    print(f"{DST} ({DST.stat().st_size // 1024} kB), {len(verts)} vrcholů, "
          f"{len(tris)} trojúhelníků")


if __name__ == "__main__":
    main()
