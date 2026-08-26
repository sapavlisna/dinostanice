"""Doplni do GLB souradnice textury.

Model z internetu zadne UV nema — barvy nese v materialech. Predloha ale vznika
projekci modelu na list, takze UV kazdeho vrcholu uz zname: je to jeho pozice
na papire. Zapisou se do kopie GLB, aby si prohlizec nacetl hotovy soubor
i s kostrou a animacemi a jen na nej hodil vybarvenou fotku.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .gltf import Model


def _pad(data: bytearray, align: int = 4, fill: int = 0) -> None:
    while len(data) % align:
        data.append(fill)


def write_with_uv(model: Model, uv: np.ndarray, dst: str | Path) -> Path:
    """Zapise kopii modelu, ve ktere ma kazda primitiva TEXCOORD_0."""
    g = json.loads(json.dumps(model.g))
    blob = bytearray(model.bin)
    _pad(blob)

    prim_specs = [p for mesh in g["meshes"] for p in mesh["primitives"]]
    if len(prim_specs) != len(model.primitives):
        raise ValueError("pocet primitiv nesedi na nactenou geometrii")

    for spec, prim in zip(prim_specs, model.primitives):
        chunk = np.ascontiguousarray(
            uv[prim.first_vertex: prim.first_vertex + prim.vertex_count], dtype=np.float32
        )
        offset = len(blob)
        blob.extend(chunk.tobytes())
        _pad(blob)
        g["bufferViews"].append({
            "buffer": 0, "byteOffset": offset, "byteLength": int(chunk.nbytes), "target": 34962,
        })
        g["accessors"].append({
            "bufferView": len(g["bufferViews"]) - 1, "componentType": 5126,
            "count": int(len(chunk)), "type": "VEC2",
            "min": [float(chunk[:, 0].min()), float(chunk[:, 1].min())],
            "max": [float(chunk[:, 0].max()), float(chunk[:, 1].max())],
        })
        spec["attributes"]["TEXCOORD_0"] = len(g["accessors"]) - 1

    g["buffers"][0] = {"byteLength": len(blob)}
    g["asset"] = dict(g.get("asset", {}), generator="DinoStanice")

    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js = js + b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<I4s", len(js), b"JSON") + js
    out += struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob)

    dst = Path(dst)
    dst.write_bytes(out)
    return dst


def _accessor(g: dict, blob: bytearray, data: np.ndarray, comp: int, kind: str,
              target: int | None = None, minmax: bool = False) -> int:
    """Zapise pole do bufferu a vrati index accessoru."""
    _pad(blob)
    offset = len(blob)
    blob.extend(np.ascontiguousarray(data).tobytes())
    _pad(blob)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": int(data.nbytes)}
    if target is not None:
        view["target"] = target
    g["bufferViews"].append(view)
    acc = {"bufferView": len(g["bufferViews"]) - 1, "componentType": comp,
           "count": int(len(data)), "type": kind}
    if minmax:
        flat = data.reshape(len(data), -1).astype(float)
        acc["min"] = flat.min(0).tolist()
        acc["max"] = flat.max(0).tolist()
    g["accessors"].append(acc)
    return len(g["accessors"]) - 1


def write_skinned(dst: str | Path, *, verts: np.ndarray, normals: np.ndarray,
                  tris: np.ndarray, tri_group: np.ndarray, colours: list,
                  joints: np.ndarray, weights: np.ndarray,
                  skeleton: list, clips: dict) -> Path:
    """Zapise GLB s vlastni kostrou a animacemi.

    `skeleton` je [(jmeno, index_rodice, translace), ...] v poradi, ve kterem na
    ne odkazuji `joints`. `clips` je {jmeno: {index_jointu: (casy, kvaterniony)}}.
    Slouzi k tomu, aby sel rozhybat model, ktery prisel bez kostry.
    """
    g = {
        "asset": {"version": "2.0", "generator": "DinoStanice"},
        "scenes": [{"nodes": [0]}], "scene": 0, "nodes": [], "meshes": [],
        "materials": [], "accessors": [], "bufferViews": [], "buffers": [],
        "skins": [], "animations": [],
    }
    blob = bytearray()

    pos = _accessor(g, blob, verts.astype(np.float32), 5126, "VEC3", 34962, minmax=True)
    nrm = _accessor(g, blob, normals.astype(np.float32), 5126, "VEC3", 34962)
    jnt = _accessor(g, blob, joints.astype(np.uint8), 5121, "VEC4", 34962)
    wgt = _accessor(g, blob, weights.astype(np.float32), 5126, "VEC4", 34962)

    primitives = []
    for gi, colour in enumerate(colours):
        sel = tris[tri_group == gi]
        if not len(sel):
            continue
        idx = _accessor(g, blob, sel.reshape(-1).astype(np.uint32), 5125, "SCALAR", 34963)
        g["materials"].append({
            "name": f"mat{gi}",
            "pbrMetallicRoughness": {"baseColorFactor": [*colour, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.9},
        })
        primitives.append({
            "attributes": {"POSITION": pos, "NORMAL": nrm, "JOINTS_0": jnt, "WEIGHTS_0": wgt},
            "indices": idx, "material": len(g["materials"]) - 1,
        })
    g["meshes"].append({"name": "body", "primitives": primitives})

    # node 0 je scenovy koren s meshem, jointy zacinaji na 1
    g["nodes"].append({"name": "Root", "mesh": 0, "skin": 0,
                       "children": [i + 1 for i, s in enumerate(skeleton) if s[1] < 0]})
    world = []
    for i, (name, parent, translation) in enumerate(skeleton):
        node = {"name": name, "translation": [float(x) for x in translation]}
        kids = [k + 1 for k, s in enumerate(skeleton) if s[1] == i]
        if kids:
            node["children"] = kids
        g["nodes"].append(node)
        origin = np.asarray(translation, float)
        if parent >= 0:
            origin = origin + world[parent]
        world.append(origin)

    ibm = np.zeros((len(skeleton), 16), np.float32)
    for i, origin in enumerate(world):
        m = np.eye(4)
        m[:3, 3] = -origin
        ibm[i] = m.T.reshape(-1)          # glTF cte matice po sloupcich
    g["skins"].append({"joints": [i + 1 for i in range(len(skeleton))],
                       "inverseBindMatrices": _accessor(g, blob, ibm, 5126, "MAT4")})

    for name, channels in clips.items():
        samplers, chans = [], []
        for joint, (times, quats) in channels.items():
            t_acc = _accessor(g, blob, np.asarray(times, np.float32), 5126, "SCALAR", minmax=True)
            q_acc = _accessor(g, blob, np.asarray(quats, np.float32), 5126, "VEC4")
            samplers.append({"input": t_acc, "output": q_acc, "interpolation": "LINEAR"})
            chans.append({"sampler": len(samplers) - 1,
                          "target": {"node": joint + 1, "path": "rotation"}})
        g["animations"].append({"name": name, "samplers": samplers, "channels": chans})

    g["buffers"].append({"byteLength": len(blob)})
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<I4s", len(js), b"JSON") + js
    out += struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob)
    dst = Path(dst)
    dst.write_bytes(out)
    return dst
