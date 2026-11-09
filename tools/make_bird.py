"""Postaví ptáčka: nízkopolygonový zpěvný pták s kostrou a dvěma klipy.

Žádný volný ptačí model nemá kostru ani let, a pták má do scény přiletět,
usednout a zase odletět, takže si ho tahle skripta staví sama:

    python tools/make_bird.py

Model stojí na zemi (y = 0) a kouká k +Z jako ostatní. V klidové póze má
křídla složená na bocích — v ní se z něj dělá předloha k vybarvení (bokorys)
i póza „Perch“. Klip `Fly` křídla rozevře a mává jimi; protože je složená
póza jen jiná váha téhož klipu, přistávání a vzlet se dají prolínat a křídla
se samy skládají a rozkládají.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dinostanice.glbexport import write_skinned  # noqa: E402

DST = ROOT / "data/models_src/bird.glb"

FLY_PERIOD = 0.5
PERCH_PERIOD = 6.0
FRAMES = 20


def _orient(verts, normals, tris):
    """Sjednotí vinutí tak, aby plochy koukaly ven (po normálách)."""
    a, b, c = (verts[tris[:, i]] for i in range(3))
    face = np.cross(b - a, c - a)
    outward = (normals[tris].mean(axis=1) * face).sum(axis=1)
    flip = outward < 0
    tris = tris.copy()
    tris[flip] = tris[flip][:, ::-1]
    return tris


def ellipsoid(centre, radii, rot=None, nu=14, nv=9):
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0, np.pi, nv)
    unit = np.array([[np.sin(vv) * np.cos(uu), np.cos(vv), np.sin(vv) * np.sin(uu)]
                     for vv in v for uu in u])
    radii = np.asarray(radii, float)
    verts = unit * radii
    normals = unit / radii
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    if rot is not None:
        verts, normals = verts @ rot.T, normals @ rot.T
    verts = verts + np.asarray(centre, float)
    tris = []
    for j in range(nv - 1):
        for i in range(nu):
            a, b = j * nu + i, j * nu + (i + 1) % nu
            c, d = (j + 1) * nu + i, (j + 1) * nu + (i + 1) % nu
            tris += [[a, c, b], [b, c, d]]
    tris = _orient(verts, normals, np.array(tris))
    return verts, normals, tris


def cone(base, apex, radius, n=8):
    base, apex = np.asarray(base, float), np.asarray(apex, float)
    axis = apex - base
    axis /= np.linalg.norm(axis)
    side = np.cross(axis, [0, 1, 0])
    side /= np.linalg.norm(side)
    up = np.cross(side, axis)
    ring = [base + radius * (np.cos(t) * side + np.sin(t) * up)
            for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    verts = np.array(ring + [apex, base])
    normals = np.array([(r - base) / np.linalg.norm(r - base) for r in ring]
                       + [axis, -axis])
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris += [[i, n, j], [i, j, n + 1]]
    tris = _orient(verts, normals, np.array(tris))
    return verts, normals, tris


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def quat(m):
    """Kvaternion (x, y, z, w) z rotační matice."""
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
                         (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k]) * 2
    q = np.zeros(4)
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return q


def qmul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                     w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])


def axis_quat(axis, angle):
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    return np.append(axis * np.sin(angle / 2), np.cos(angle / 2))


# rozevřené křídlo: délka z -Z na +X, tětiva z Y na Z (levé křídlo, +X)
SPREAD_L = np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
SPREAD_R = np.diag([-1.0, 1.0, 1.0]) @ SPREAD_L @ np.diag([-1.0, 1.0, 1.0])

BODY_Y = 0.30
SHOULDER = np.array([0.19, 0.38, 0.16])      # světové souřadnice, levé křídlo
WING_LEN = 0.50
TIP_AT = 0.26                                # kde se křídlo láme (od ramene dozadu)


def build():
    parts = []     # (verts, normals, tris, group)

    def add(shape, group, label):
        parts.append((*shape, group, label))

    add(ellipsoid((0, BODY_Y, 0), (0.22, 0.21, 0.36)), 0, 'body')                       # trup
    add(ellipsoid((0, BODY_Y + 0.19, 0.31), (0.15, 0.15, 0.16)), 1, 'head')             # hlava
    add(cone((0, BODY_Y + 0.17, 0.45), (0, BODY_Y + 0.15, 0.61), 0.045), 2, 'head')     # zobák
    add(ellipsoid((0, BODY_Y - 0.02, -0.52), (0.10, 0.045, 0.24),
                  rot=rot_x(np.radians(-8))), 4, 'tail')                                # ocas
    for sx in (1, -1):
        add(ellipsoid((sx * 0.235, BODY_Y + 0.03, -0.08), (0.03, 0.15, 0.30)), 3, 'wingL' if sx > 0 else 'wingR')   # křídlo
        add(ellipsoid((sx * 0.07, 0.10, 0.03), (0.016, 0.10, 0.016)), 5, 'body')            # noha
        add(ellipsoid((sx * 0.07, 0.012, 0.06), (0.03, 0.012, 0.055)), 5, 'body')           # chodidlo

    offset, V, N, T, G, L = 0, [], [], [], [], []
    for v, n, t, g, label in parts:
        L.extend([label] * len(v))
        V.append(v)
        N.append(n)
        T.append(t + offset)
        G.append(np.full(len(t), g, np.int32))
        offset += len(v)
    return np.vstack(V), np.vstack(N), np.vstack(T), np.concatenate(G), np.array(L)


def rig(verts, label):
    """Kostra a váhy. Index kloubu: 0 Body, 1 Head, 2 Tail, 3/4 WingL/Tip, 5/6 WingR/Tip."""
    n = len(verts)
    joints = np.zeros((n, 4), np.uint8)
    weights = np.zeros((n, 4), np.float32)
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]

    head, tail = label == 'head', label == 'tail'
    wing_l, wing_r = label == 'wingL', label == 'wingR'

    joints[:, 0] = 0
    weights[:, 0] = 1.0
    joints[head, 0], weights[head, 0] = 1, 1.0
    joints[tail, 0], weights[tail, 0] = 2, 1.0
    for mask, (jw, jt) in ((wing_l, (3, 4)), (wing_r, (5, 6))):
        s = np.clip((SHOULDER[2] - z[mask]) / TIP_AT, 0, 1)
        w_tip = np.clip((s - 0.55) / 0.45, 0, 1)
        joints[mask, 0], weights[mask, 0] = jw, 1.0 - w_tip
        joints[mask, 1], weights[mask, 1] = jt, w_tip
    skeleton = [
        ("Body", -1, (0.0, BODY_Y, 0.0)),
        ("Head", 0, (0.0, 0.19, 0.30)),
        ("Tail", 0, (0.0, -0.03, -0.30)),
        ("WingL", 0, (SHOULDER[0], SHOULDER[1] - BODY_Y, SHOULDER[2])),
        ("WingTipL", 3, (0.0, 0.0, -TIP_AT)),
        ("WingR", 0, (-SHOULDER[0], SHOULDER[1] - BODY_Y, SHOULDER[2])),
        ("WingTipR", 5, (0.0, 0.0, -TIP_AT)),
    ]
    return skeleton, joints, weights


def clips():
    q_id = np.array([0.0, 0.0, 0.0, 1.0])
    fly_t = np.linspace(0.0, FLY_PERIOD, FRAMES + 1)
    per_t = np.linspace(0.0, PERCH_PERIOD, FRAMES + 1)

    def track(times, fn):
        return times, np.array([fn(t) for t in times])

    fly, perch = {}, {}
    for joint, name, sign, spread in ((3, "WingL", 1.0, SPREAD_L), (5, "WingR", -1.0, SPREAD_R)):
        q_spread = quat(spread)

        def wing(t, sign=sign, q_spread=q_spread):
            ph = 2 * np.pi * t / FLY_PERIOD
            ang = np.radians(10 + 42 * np.sin(ph))
            return qmul(axis_quat([0, 0, 1], sign * ang), q_spread)

        def tip(t, sign=sign):
            ph = 2 * np.pi * (t / FLY_PERIOD - 0.16)
            return axis_quat([0, 1, 0], sign * np.radians(26 * np.sin(ph)))

        fly[joint] = track(fly_t, wing)
        fly[joint + 1] = track(fly_t, tip)
        perch[joint] = (per_t, np.tile(q_id, (len(per_t), 1)))

    fly[0] = track(fly_t, lambda t: axis_quat([1, 0, 0],
                                              np.radians(3 * np.sin(2 * np.pi * t / FLY_PERIOD + 1.2))))
    fly[2] = track(fly_t, lambda t: axis_quat([1, 0, 0],
                                              np.radians(-6 + 5 * np.sin(2 * np.pi * t / FLY_PERIOD + 0.5))))
    fly[1] = (fly_t, np.tile(q_id, (len(fly_t), 1)))

    def head(t):
        ph = 2 * np.pi * t / PERCH_PERIOD
        yaw = np.radians(24 * np.sin(ph) * (0.4 + 0.6 * np.sin(ph * 0.5) ** 2))
        pitch = np.radians(6 * np.sin(ph * 2 + 1))
        return qmul(axis_quat([0, 1, 0], yaw), axis_quat([1, 0, 0], pitch))

    perch[1] = track(per_t, head)
    perch[2] = track(per_t, lambda t: axis_quat(
        [1, 0, 0], np.radians(4 * np.sin(4 * np.pi * t / PERCH_PERIOD) ** 4)))
    perch[0] = track(per_t, lambda t: axis_quat(
        [1, 0, 0], np.radians(1.5 * np.sin(12 * np.pi * t / PERCH_PERIOD))))
    return {"Fly": fly, "Perch": perch}


def main():
    verts, normals, tris, group, label = build()
    skeleton, joints, weights = rig(verts, label)
    # barvy skupin: trup, hlava, zobák, křídla, ocas, nohy (jen záloha, scéna kreslí texturu)
    colours = [[0.62, 0.45, 0.30], [0.55, 0.40, 0.28], [0.95, 0.70, 0.20],
               [0.45, 0.33, 0.24], [0.40, 0.30, 0.22], [0.85, 0.65, 0.45]]
    write_skinned(DST, verts=verts, normals=normals, tris=tris, tri_group=group,
                  colours=colours, joints=joints, weights=weights, skeleton=skeleton,
                  clips=clips())
    print(f"{DST} ({DST.stat().st_size // 1024} kB), {len(verts)} vrcholů, "
          f"{len(tris)} trojúhelníků")


if __name__ == "__main__":
    main()
