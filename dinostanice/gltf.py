"""Minimalni GLB loader se skinningem.

Nacte binarni glTF 2.0, slozi vrcholy vsech primitiv do jednoho pole a umi
vyhodnotit skeletalni animaci v libovolnem case (linear blend skinning).
Zamerne bez externich zavislosti — glTF je jednoduchy format a numpy tu uz je.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_COMPONENT = {
    5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
    5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4),
}
_NUM = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


@dataclass
class Primitive:
    material: str
    first_vertex: int
    vertex_count: int
    first_index: int
    index_count: int


@dataclass
class Animation:
    name: str
    duration: float
    channels: dict = field(default_factory=dict)


class Model:
    """Mesh + kostra + animace, vsechno uz v numpy."""

    def __init__(self, path: str | Path):
        data = Path(path).read_bytes()
        magic = data[:4]
        if magic != b"glTF":
            raise ValueError(f"{path} neni binarni glTF")
        chunks, off = {}, 12
        while off < len(data):
            clen, ctype = struct.unpack("<I4s", data[off:off + 8])
            chunks[ctype.rstrip(b"\x00")] = data[off + 8: off + 8 + clen]
            off += 8 + clen + (-clen % 4)
        self.g = json.loads(chunks[b"JSON"])
        self.bin = chunks.get(b"BIN", b"")
        self._read_mesh()
        self._read_nodes()
        self._read_skin()
        self._read_animations()

    # --- pristup k datum ---------------------------------------------------

    def accessor(self, idx: int) -> np.ndarray:
        acc = self.g["accessors"][idx]
        n = _NUM[acc["type"]]
        fmt, size = _COMPONENT[acc["componentType"]]
        count = acc["count"]
        bv = self.g["bufferViews"][acc["bufferView"]]
        base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride") or n * size
        need = stride * (count - 1) + n * size
        raw = np.frombuffer(self.bin, dtype=np.uint8, count=need, offset=base)
        view = np.lib.stride_tricks.as_strided(raw, shape=(count, n * size), strides=(stride, 1))
        return np.ascontiguousarray(view.copy().view(np.dtype(fmt)).reshape(count, n))

    # --- mesh --------------------------------------------------------------

    def _read_mesh(self) -> None:
        pos, nrm, joints, weights, idx = [], [], [], [], []
        self.primitives: list[Primitive] = []
        base_v = base_i = 0
        shared: dict[int, tuple[int, int]] = {}   # accessor -> (base_v, pocet)
        for mesh in self.g["meshes"]:
            for prim in mesh["primitives"]:
                a = prim["attributes"]
                if a["POSITION"] in shared:
                    # vic primitiv nad jednim vrcholovym bufferem (jen jine
                    # materialy); nacitat ho znovu by vrcholy zdvojilo
                    start, count = shared[a["POSITION"]]
                    tri = self.accessor(prim["indices"]).reshape(-1).astype(np.int64) + start
                    mat = (self.g["materials"][prim["material"]]["name"]
                           if "material" in prim else "default")
                    self.primitives.append(Primitive(mat, start, count, base_i, len(tri)))
                    idx.append(tri)
                    base_i += len(tri)
                    continue
                p = self.accessor(a["POSITION"]).astype(np.float64)
                n = (self.accessor(a["NORMAL"]).astype(np.float64) if "NORMAL" in a
                     else np.zeros_like(p))
                j = (self.accessor(a["JOINTS_0"]).astype(np.int32) if "JOINTS_0" in a
                     else np.zeros((len(p), 4), np.int32))
                w = (self.accessor(a["WEIGHTS_0"]).astype(np.float64) if "WEIGHTS_0" in a
                     else np.tile([1.0, 0, 0, 0], (len(p), 1)))
                tri = self.accessor(prim["indices"]).reshape(-1).astype(np.int64) + base_v
                mat = self.g["materials"][prim["material"]]["name"] if "material" in prim else "default"
                self.primitives.append(Primitive(mat, base_v, len(p), base_i, len(tri)))
                shared[a["POSITION"]] = (base_v, len(p))
                pos.append(p)
                nrm.append(n)
                joints.append(j)
                weights.append(w)
                idx.append(tri)
                base_v += len(p)
                base_i += len(tri)
        self.positions = np.concatenate(pos)
        self.normals = np.concatenate(nrm)
        self.joints = np.concatenate(joints)
        self.weights = np.concatenate(weights)
        self.indices = np.concatenate(idx).reshape(-1, 3)
        self.tri_material = np.concatenate([
            np.full(p.index_count // 3, i, np.int32) for i, p in enumerate(self.primitives)
        ])
        self.materials = [p.material for p in self.primitives]

    # --- hierarchie --------------------------------------------------------

    def _read_nodes(self) -> None:
        nodes = self.g["nodes"]
        self.node_names = [n.get("name", f"node{i}") for i, n in enumerate(nodes)]
        self.parent = np.full(len(nodes), -1, np.int32)
        for i, n in enumerate(nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.local_rest = np.stack([_node_matrix(n) for n in nodes])
        self.trs_rest = [(
            np.array(n.get("translation", [0, 0, 0]), float),
            np.array(n.get("rotation", [0, 0, 0, 1]), float),
            np.array(n.get("scale", [1, 1, 1]), float),
        ) for n in nodes]
        order, seen = [], set()

        def visit(i: int) -> None:
            if i in seen:
                return
            seen.add(i)
            order.append(i)
            for c in nodes[i].get("children", []):
                visit(c)

        for root in self.g["scenes"][self.g.get("scene", 0)]["nodes"]:
            visit(root)
        for i in range(len(nodes)):
            visit(i)
        self.order = order

    def _read_skin(self) -> None:
        if not self.g.get("skins"):
            self.skin_joints, self.inverse_bind = None, None
            return
        skin = self.g["skins"][0]
        self.skin_joints = np.array(skin["joints"], np.int32)
        ibm = self.accessor(skin["inverseBindMatrices"]).astype(np.float64)
        self.inverse_bind = ibm.reshape(-1, 4, 4).transpose(0, 2, 1)

    def _read_animations(self) -> None:
        self.animations: dict[str, Animation] = {}
        for i, anim in enumerate(self.g.get("animations", [])):
            name = anim.get("name", f"anim{i}")
            a = Animation(name=name, duration=0.0)
            for ch in anim["channels"]:
                s = anim["samplers"][ch["sampler"]]
                times = self.accessor(s["input"]).reshape(-1).astype(np.float64)
                values = self.accessor(s["output"]).astype(np.float64)
                node = ch["target"]["node"]
                a.channels.setdefault(node, {})[ch["target"]["path"]] = (
                    times, values, s.get("interpolation", "LINEAR")
                )
                a.duration = max(a.duration, float(times[-1]))
            self.animations[name] = a

    def clip(self, name: str) -> str | None:
        """Jmeno animace podle holeho nazvu.

        Klipy z FBX nesou jmeno armatury ("Armature|TRex_Walk",
        "CharacterArmature|Fast_Flying"), ktere se model od modelu lisi, takze
        se hleda podle konce, ne podle prefixu.
        """
        for full in self.animations:
            tail = full.split("|")[-1]
            if tail == name or tail.endswith("_" + name):
                return full
        return None

    # --- pozovani ----------------------------------------------------------

    def global_matrices(self, anim: str | None = None, t: float = 0.0) -> np.ndarray:
        local = self.local_rest.copy()
        if anim is not None:
            for node, paths in self.animations[anim].channels.items():
                tr, rot, sc = self.trs_rest[node]
                if "translation" in paths:
                    tr = _sample(*paths["translation"], t)
                if "rotation" in paths:
                    rot = _normalize(_sample_quat(*paths["rotation"], t))
                if "scale" in paths:
                    sc = _sample(*paths["scale"], t)
                local[node] = _compose(tr, rot, sc)
        world = np.zeros_like(local)
        for i in self.order:
            p = self.parent[i]
            world[i] = local[i] if p < 0 else world[p] @ local[i]
        return world

    def posed(self, anim: str | None = None, t: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Vrcholy a normaly v pozici dane animace (None = bind pose)."""
        world = self.global_matrices(anim, t)
        if self.skin_joints is None:
            return self.positions.copy(), self.normals.copy()
        skin = world[self.skin_joints] @ self.inverse_bind
        w = self.weights / np.maximum(self.weights.sum(1, keepdims=True), 1e-12)
        m = np.einsum("vk,vkij->vij", w, skin[self.joints])
        pos = np.einsum("vij,vj->vi", m[:, :3, :3], self.positions) + m[:, :3, 3]
        nrm = np.einsum("vij,vj->vi", m[:, :3, :3], self.normals)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        return pos, nrm


# --- pomocne -----------------------------------------------------------------

def _node_matrix(n: dict) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"], float).reshape(4, 4).T
    return _compose(
        np.array(n.get("translation", [0, 0, 0]), float),
        np.array(n.get("rotation", [0, 0, 0, 1]), float),
        np.array(n.get("scale", [1, 1, 1]), float),
    )


def _compose(tr: np.ndarray, q: np.ndarray, sc: np.ndarray) -> np.ndarray:
    x, y, z, w = q
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = r * sc
    m[:3, 3] = tr
    return m


def _normalize(q: np.ndarray) -> np.ndarray:
    return q / max(float(np.linalg.norm(q)), 1e-12)


def _span(times: np.ndarray, t: float) -> tuple[int, int, float]:
    if len(times) == 1:
        return 0, 0, 0.0
    t = float(np.clip(t, times[0], times[-1]))
    i = int(np.searchsorted(times, t, "right") - 1)
    i = min(max(i, 0), len(times) - 2)
    dt = times[i + 1] - times[i]
    return i, i + 1, 0.0 if dt <= 0 else (t - times[i]) / dt


def _sample(times: np.ndarray, values: np.ndarray, interp: str, t: float) -> np.ndarray:
    if interp == "CUBICSPLINE":
        values = values.reshape(len(times), 3, -1)[:, 1]
    i, k, u = _span(times, t)
    if interp == "STEP":
        return values[i]
    return values[i] * (1 - u) + values[k] * u


def _sample_quat(times: np.ndarray, values: np.ndarray, interp: str, t: float) -> np.ndarray:
    if interp == "CUBICSPLINE":
        values = values.reshape(len(times), 3, -1)[:, 1]
    i, k, u = _span(times, t)
    if interp == "STEP" or i == k:
        return values[i]
    a, b = values[i], values[k]
    if float(a @ b) < 0:
        b = -b
    dot = float(np.clip(a @ b, -1.0, 1.0))
    if dot > 0.9995:
        return a * (1 - u) + b * u
    th = float(np.arccos(dot))
    s = np.sin(th)
    return a * (np.sin((1 - u) * th) / s) + b * (np.sin(u * th) / s)
