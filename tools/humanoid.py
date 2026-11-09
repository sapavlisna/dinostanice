"""Stavebnice na procedurální humanoidy: tvary, kostra, váhy, klipy a zápis GLB.

Společný základ pro tools/make_mikulas.py. Hotové rigované lidské modely, které
jdou obarvit z bokorysu, nejsou k dohledání (CC0 humanoidi mají jemné povrchy
a tisíce trojúhelníků a z bokorysu by byla šmouha), takže se postavy staví ze
zaoblených hmot jako tools/make_bird.py.

Souřadnice: Y nahoru, postava kouká k +Z, její levá strana je +X. Vzhled
bokorysu (axes (2,1,0), flip (1,-1,1)) vidí pravou stranu, tedy -X. Klidová póza
má všechny kosti bez natočení; směry kostí vyplývají jen z jejich poloh, takže
předpažená ruka s holí je prostě kostra, která už v klidu míří dopředu. Klipy
natáčejí kosti kolem X (kývání v rovině kroku), Y (otáčení) a Z (rozpažení).
Natočení kolem X o kladný úhel zvedá horní konec kosti k +Z, noha tím jde
dozadu — proto je „vpřed“ vždy záporný úhel.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dinostanice.glbexport import _accessor  # noqa: E402

from make_bird import ellipsoid, qmul, quat  # noqa: E402,F401


# ---------------------------------------------------------------- kvaterniony

def axis_q(axis, angle):
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    return np.append(axis * np.sin(angle / 2), np.cos(angle / 2))


def qx(a):
    return axis_q([1, 0, 0], a)


def qy(a):
    return axis_q([0, 1, 0], a)


def qz(a):
    return axis_q([0, 0, 1], a)


def qmul3(*qs):
    out = qs[0]
    for q in qs[1:]:
        out = qmul(out, q)
    return out


ID = np.array([0.0, 0.0, 0.0, 1.0])
rad = np.radians


def smooth(x, lo, hi):
    t = np.clip((np.asarray(x, float) - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------- tvary

def _finish(v, t):
    """Sjednotí vinutí (uzavřené těleso má kladný objem) a spočítá hladké normály."""
    v = np.asarray(v, float)
    t = np.asarray(t, np.int64)
    vol = np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6
    if vol < 0:
        t = t[:, ::-1]
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return v, n, t


def _rings_to_mesh(rings, closed_ring=False):
    nr, nu = rings.shape[:2]
    t = []
    for i in range(nr - 1):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            c, d = (i + 1) * nu + j, (i + 1) * nu + (j + 1) % nu
            t += [[a, c, b], [b, c, d]]
    if closed_ring:
        for j in range(nu):
            a, b = (nr - 1) * nu + j, (nr - 1) * nu + (j + 1) % nu
            c, d = j, (j + 1) % nu
            t += [[a, c, b], [b, c, d]]
    return rings.reshape(-1, 3), np.array(t)


def lathe(rings, nu=16, caps=True):
    """Těleso z vodorovných elips. rings = [(cx, cy, cz, rx, rz), ...] zdola nahoru.
    Konce se zavřou plochým dnem s ostrou hranou (zdvojený prstenec)."""
    rings = [tuple(r) for r in rings]
    if caps:
        a, b = rings[0], rings[-1]
        rings = [(a[0], a[1], a[2], 0.0, 0.0), a, *rings, b, (b[0], b[1], b[2], 0.0, 0.0)]
    th = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    arr = np.stack([np.stack([cx + rx * c, np.full(nu, cy), cz + rz * s], 1)
                    for cx, cy, cz, rx, rz in rings])
    return _finish(*_rings_to_mesh(arr))


def _frames(path):
    tang = np.gradient(path, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-12)
    n = np.zeros_like(tang)
    ref = np.eye(3)[int(np.argmin(np.abs(tang[0])))]
    n[0] = np.cross(tang[0], ref)
    n[0] /= np.linalg.norm(n[0])
    for i in range(1, len(path)):
        v = n[i - 1] - tang[i] * (n[i - 1] @ tang[i])
        n[i] = v / max(np.linalg.norm(v), 1e-12)
    return tang, n, np.cross(tang, n)


def sweep(path, radii, nu=10, dome=(True, True), steps=3):
    """Trubice po lomené čáře. radii = r nebo (rx, rz) na bod; konce zakulacené
    (dome) nebo plochým dnem. Slouží na končetiny, ocas, hůl, rohy."""
    path = np.asarray(path, float)
    radii = np.asarray(radii, float)
    if radii.ndim == 0:
        radii = np.full(len(path), float(radii))
    if radii.ndim == 1:
        radii = np.stack([radii, radii], 1)
    tang, nrm, bin_ = _frames(path)
    rows = [(path[i], radii[i], nrm[i], bin_[i]) for i in range(len(path))]
    if dome[0]:
        p, r, n, b = rows[0]
        mean = r.mean()
        head = [(p - tang[0] * mean * np.cos(a), r * np.sin(a), n, b)
                for a in (np.pi / 2 * np.arange(steps) / steps)]
        rows = head + rows
    else:
        p, r, n, b = rows[0]
        rows = [(p, r * 0, n, b), (p, r, n, b)] + rows
    if dome[1]:
        p, r, n, b = rows[-1]
        mean = r.mean()
        tail = [(p + tang[-1] * mean * np.cos(np.pi / 2 * k / steps),
                 r * np.sin(np.pi / 2 * k / steps), n, b) for k in range(steps - 1, -1, -1)]
        rows = rows + tail
    else:
        p, r, n, b = rows[-1]
        rows = rows + [(p, r, n, b), (p, r * 0, n, b)]
    th = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    c, s = np.cos(th)[:, None], np.sin(th)[:, None]
    arr = np.stack([p + n * (r[0] * c) + b * (r[1] * s) for p, r, n, b in rows])
    return _finish(*_rings_to_mesh(arr))


def torus(centre, major, minor, axis=(1, 0, 0), nu=10, nv=24):
    """Prstenec (svatozář) kolem osy `axis`."""
    axis = np.asarray(axis, float)
    axis /= np.linalg.norm(axis)
    u = np.cross(axis, [0, 1, 0] if abs(axis[1]) < 0.9 else [0, 0, 1])
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    ph = np.linspace(0, 2 * np.pi, nv, endpoint=False)
    th = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    rows = []
    for p in ph:
        radial = np.cos(p) * u + np.sin(p) * w
        rows.append(np.array([np.asarray(centre) + major * radial
                              + minor * (np.cos(t) * radial + np.sin(t) * axis) for t in th]))
    return _finish(*_rings_to_mesh(np.stack(rows), closed_ring=True))


def blob(centre, radii, rot=None, nu=16, nv=10):
    v, n, t = ellipsoid(centre, radii, rot=rot, nu=nu, nv=nv)
    return _finish(v, t)


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def aligned(a, b):
    """Matice, která osu +Y otočí do směru a→b (pro protažené elipsoidy)."""
    d = np.asarray(b, float) - np.asarray(a, float)
    d /= np.linalg.norm(d)
    ax = np.cross([0, 1, 0], d)
    s = np.linalg.norm(ax)
    c = d[1]
    if s < 1e-9:
        return np.eye(3) if c > 0 else rot_x(np.pi)
    ax /= s
    k = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + s * k + (1 - c) * k @ k


def spindle(a, b, radius, bulge=1.0, nu=12, nv=8):
    """Protažený elipsoid mezi dvěma body (pírko, prst, bota)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = np.linalg.norm(b - a)
    return blob((a + b) / 2, (radius[0], length / 2, radius[1]), rot=aligned(a, b), nu=nu, nv=nv)


# ---------------------------------------------------------------------- kostra

class Skeleton:
    def __init__(self):
        self.items = []     # (jméno, rodič, světová poloha)
        self.index = {}

    def add(self, name, parent, pos):
        self.index[name] = len(self.items)
        self.items.append((name, self.index[parent] if parent else -1, np.asarray(pos, float)))
        return self.index[name]

    def id(self, name):
        return self.index[name]

    def pos(self, name):
        return self.items[self.index[name]][2]

    def parent(self, name):
        p = self.items[self.index[name]][1]
        return self.items[p][0] if p >= 0 else None

    def local(self, name):
        i = self.index[name]
        _, p, pos = self.items[i]
        return pos - (self.items[p][2] if p >= 0 else 0)

    def listing(self, scale=1.0):
        return [(n, p, self.local(n) * scale) for n, p, _ in self.items]


# ---------------------------------------------------------------------- váhy

def _pack(joints, weights):
    """Nejvýš čtyři vlivy na vrchol, normalizované."""
    joints, weights = np.asarray(joints), np.asarray(weights, float)
    order = np.argsort(-weights, axis=1)[:, :4]
    j = np.take_along_axis(joints, order, 1)
    w = np.take_along_axis(weights, order, 1)
    if j.shape[1] < 4:
        pad = 4 - j.shape[1]
        j = np.pad(j, ((0, 0), (0, pad)))
        w = np.pad(w, ((0, 0), (0, pad)))
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    return j.astype(np.uint8), w.astype(np.float32)


def rigid(sk, name):
    j = sk.id(name)

    def fn(v):
        return _pack(np.full((len(v), 1), j), np.ones((len(v), 1)))
    return fn


def chain(sk, names, blend=0.06):
    """Váhy podél lomené čáry kloubů: každý kloub táhne úsek za sebou, přechod
    je plynulý na ±blend kolem lomu."""
    pts = np.array([sk.pos(n) for n in names])
    seg = np.diff(pts, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(ln)])
    ids = [sk.id(n) for n in names]

    def fn(v):
        best = np.full(len(v), np.inf)
        s = np.zeros(len(v))
        for i in range(len(seg)):
            rel = v - pts[i]
            t = np.clip(rel @ seg[i] / ln[i] ** 2, 0, 1)
            d = np.linalg.norm(rel - t[:, None] * seg[i], axis=1)
            take = d < best
            best[take] = d[take]
            s[take] = cum[i] + t[take] * ln[i]
        steps = [np.ones(len(v))] + [smooth(s, cum[k] - blend, cum[k] + blend)
                                     for k in range(1, len(names))] + [np.zeros(len(v))]
        w = np.stack([steps[k] - steps[k + 1] for k in range(len(names))], 1)
        return _pack(np.tile(ids, (len(v), 1)), w)
    return fn


def combine(*parts):
    """Smíchá váhy z víc funkcí: parts = [(fn, podíl nebo funkce vrcholů), ...]."""
    def fn(v):
        js, ws = [], []
        for f, k in parts:
            j, w = f(v)
            kk = k(v) if callable(k) else k
            js.append(j.astype(np.int64))
            ws.append(w * np.asarray(kk, float).reshape(-1, 1) if np.ndim(kk) else w * kk)
        return _pack(np.hstack(js), np.hstack(ws))
    return fn


# ---------------------------------------------------------------------- model

class Builder:
    def __init__(self, sk, materials):
        self.sk = sk
        self.materials = materials      # [(jméno, barva)]
        self.parts = []

    def add(self, shape, material, skin, label=""):
        v, n, t = shape
        j, w = skin(v)
        self.parts.append((v, n, t, self.materials_index(material), j, w, label))

    def materials_index(self, m):
        names = [x[0] for x in self.materials]
        return names.index(m) if isinstance(m, str) else m

    def arrays(self, scale=1.0):
        V, N, T, G, J, W, L = [], [], [], [], [], [], []
        off = 0
        for v, n, t, g, j, w, label in self.parts:
            V.append(v * scale)
            N.append(n)
            T.append(t + off)
            G.append(np.full(len(t), g, np.int32))
            J.append(j)
            W.append(w)
            L += [label] * len(v)
            off += len(v)
        return (np.vstack(V), np.vstack(N), np.vstack(T), np.concatenate(G),
                np.vstack(J), np.vstack(W), np.array(L))


# ---------------------------------------------------------------------- klipy

class Pose:
    """Natočení kostí v jednom okamžiku; co není zadané, je klidová póza."""

    def __init__(self):
        self.rot = {}
        self.move = np.zeros(3)

    def turn(self, joint, q):
        self.rot[joint] = qmul(self.rot[joint], q) if joint in self.rot else q
        return self


def leg_foot_drop(l1, l2, a_thigh, a_knee):
    """O kolik je kotník výš (+) než v klidu při natočení nohy; kladný úhel = dozadu."""
    return (l1 + l2) - (l1 * np.cos(a_thigh) + l2 * np.cos(a_thigh + a_knee))


def make_clip(sk, fn, duration, fps=24, loop=True):
    """Vzorkuje fn(t) -> Pose. Vrací {joint_index: {"rotation": (t, q), "translation": (t, v)}}.
    U smyčky se poslední snímek rovná prvnímu."""
    n = int(round(duration * fps))
    times = np.linspace(0.0, duration, n + 1)
    poses = [fn(t if not (loop and i == n) else 0.0) for i, t in enumerate(times)]
    out = {}
    joints = set()
    for p in poses:
        joints |= set(p.rot)
    for name in sorted(joints, key=sk.id):
        q = np.array([p.rot.get(name, ID) for p in poses])
        # po sobě jdoucí kvaterniony na stejné straně, jinak by prolnutí šlo oklikou
        for i in range(1, len(q)):
            if q[i] @ q[i - 1] < 0:
                q[i] = -q[i]
        if np.abs(q - ID).max() > 1e-6:
            out.setdefault(sk.id(name), {})["rotation"] = (times, q)
    mv = np.array([p.move for p in poses])
    if np.abs(mv).max() > 1e-7:
        rest = sk.pos("Hips")
        out.setdefault(sk.id("Hips"), {})["translation"] = (times, mv + rest)
    return out


# ---------------------------------------------------------------------- zápis

def write_rigged(dst, builder, clips, scale=1.0):
    """GLB s kostrou, klipy (rotace i posun) a materiály po skupinách."""
    sk = builder.sk
    verts, normals, tris, group, joints, weights, _ = builder.arrays(scale)
    skeleton = sk.listing(scale)
    g = {
        "asset": {"version": "2.0", "generator": "DinoStanice"},
        "scenes": [{"nodes": [0]}], "scene": 0, "nodes": [], "meshes": [],
        "materials": [], "accessors": [], "bufferViews": [], "buffers": [],
        "skins": [], "animations": [],
    }
    blob_ = bytearray()
    pos = _accessor(g, blob_, verts.astype(np.float32), 5126, "VEC3", 34962, minmax=True)
    nrm = _accessor(g, blob_, normals.astype(np.float32), 5126, "VEC3", 34962)
    jnt = _accessor(g, blob_, joints.astype(np.uint8), 5121, "VEC4", 34962)
    wgt = _accessor(g, blob_, weights.astype(np.float32), 5126, "VEC4", 34962)

    prims = []
    for gi, (name, colour) in enumerate(builder.materials):
        sel = tris[group == gi]
        if not len(sel):
            continue
        idx = _accessor(g, blob_, sel.reshape(-1).astype(np.uint32), 5125, "SCALAR", 34963)
        g["materials"].append({
            "name": name,
            "pbrMetallicRoughness": {"baseColorFactor": [*colour, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.9},
        })
        prims.append({"attributes": {"POSITION": pos, "NORMAL": nrm, "JOINTS_0": jnt,
                                     "WEIGHTS_0": wgt},
                      "indices": idx, "material": len(g["materials"]) - 1})
    g["meshes"].append({"name": "body", "primitives": prims})

    g["nodes"].append({"name": "Root", "mesh": 0, "skin": 0,
                       "children": [i + 1 for i, s in enumerate(skeleton) if s[1] < 0]})
    world = []
    for i, (name, parent, tr) in enumerate(skeleton):
        node = {"name": name, "translation": [float(x) for x in tr]}
        kids = [k + 1 for k, s in enumerate(skeleton) if s[1] == i]
        if kids:
            node["children"] = kids
        g["nodes"].append(node)
        world.append(np.asarray(tr, float) + (world[parent] if parent >= 0 else 0))
    ibm = np.zeros((len(skeleton), 16), np.float32)
    for i, origin in enumerate(world):
        m = np.eye(4)
        m[:3, 3] = -origin
        ibm[i] = m.T.reshape(-1)
    g["skins"].append({"joints": [i + 1 for i in range(len(skeleton))],
                       "inverseBindMatrices": _accessor(g, blob_, ibm, 5126, "MAT4")})

    for name, channels in clips.items():
        samplers, chans = [], []
        for joint, paths in channels.items():
            for path, (times, vals) in paths.items():
                vals = np.asarray(vals, np.float32)
                if path == "translation":
                    vals = vals * scale
                t_acc = _accessor(g, blob_, np.asarray(times, np.float32), 5126, "SCALAR", minmax=True)
                v_acc = _accessor(g, blob_, vals, 5126, "VEC4" if path == "rotation" else "VEC3")
                samplers.append({"input": t_acc, "output": v_acc, "interpolation": "LINEAR"})
                chans.append({"sampler": len(samplers) - 1,
                              "target": {"node": joint + 1, "path": path}})
        g["animations"].append({"name": name, "samplers": samplers, "channels": chans})

    g["buffers"].append({"byteLength": len(blob_)})
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob_))
    out += struct.pack("<I4s", len(js), b"JSON") + js
    out += struct.pack("<I4s", len(blob_), b"BIN\x00") + bytes(blob_)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    return dst
