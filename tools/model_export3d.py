"""Pripravi modely pro prohlizec: GLB s UV a ukazkovou texturu.

    python tools/model_export3d.py            # cely katalog
    python tools/model_export3d.py trex3d

GLB si nese kostru i vsechny animace od autora modelu, navic dostane UV
odpovidajici pozici na listu. Prohlizec uz jen nahodi vybarvenou fotku.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_paint_demo as demo
from dinostanice import modelsheet as ms
from dinostanice.creatures3d import BY_KEY, CATALOGUE, resolve_roles
from dinostanice.glbexport import write_with_uv
from dinostanice.gltf import Model
from dinostanice.paint import paint_relief
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/models3d"


def export(spec, index_only=False) -> dict:
    shape = ms.load(ROOT / f"data/shapes3d/{spec.key}.json")
    model = Model(ROOT / "data/models_src" / spec.glb)

    verts, _ = model.posed(shape.anim or None, shape.time)
    if not index_only:
        mm = shape.placement.to_mm(verts)
        uv = np.stack([mm[:, 0] / SHEET_W_MM, mm[:, 1] / SHEET_H_MM], axis=1)
        write_with_uv(model, uv, OUT / f"{spec.key}.glb")

        sheet = demo.paint_sheet(shape, spec.paint, spec.key,
                                 side_view=tuple(spec.axes) == (2, 1, 0), lines=not spec.paint)
        cv2.imwrite(str(OUT / f"{spec.key}_texture.png"),
                    ms.to_texture(sheet, shape, demo.PPM, remove_ink=not spec.paint))
        if spec.paint.get("relief"):
            relief = paint_relief(shape, spec.paint, demo.PPM, sheet.shape[:2], spec.key)
            cv2.imwrite(str(OUT / f"{spec.key}_bump.png"),
                        ms.to_texture(relief, shape, demo.PPM, remove_ink=False))

    clips = {name.split("|")[-1].split("_")[-1]: name
             for name in sorted(model.animations)}
    roles, missing = resolve_roles(spec.clip_roles(), clips)
    if missing:
        print(f"  {spec.key}: bez klipu pro role {', '.join(missing)} — scena je nenabidne")
    entry = {
        "key": spec.key,
        "label": spec.label,
        "motion": spec.motion,
        "scene": spec.scene,
        "glb": f"/models3d/{spec.key}.glb",
        "texture": f"/models3d/{spec.key}_texture.png",
        # Kratke jmeno klipu: nejdriv pryc prefix armatury, pak jeji jmeno
        # z FBX exportu. Rybi klipy nesou prefix s podtrzitkem
        # ("Fish_Armature|Attack"), takze bez oriznuti po "|" by z Attacku
        # zbylo "Armature|Attack" a scena by roli nenasla.
        "clips": clips,
        "clipFor": roles,
        "pose": shape.anim,
        "size": round(float(np.ptp(verts[:, 2])), 2),
    }
    if spec.paint.get("relief"):
        entry["bump"] = f"/models3d/{spec.key}_bump.png"
    if spec.material:
        entry["material"] = spec.material
    if spec.activities:
        entry["activities"] = spec.activities
    if spec.extra:
        entry["extra"] = True
    if spec.stride_rate:
        entry["strideRate"] = list(spec.stride_rate)
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--index-only", action="store_true",
                    help="prepsat jen catalogue3d.json, GLB a textur se nedotykat")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    specs = [BY_KEY[k] for k in args.keys] if args.keys else CATALOGUE
    entries = [export(s, index_only=args.index_only) for s in specs]

    index = OUT / "catalogue3d.json"
    if args.keys and index.exists():
        old = {e["key"]: e for e in json.loads(index.read_text(encoding="utf-8"))}
        old.update({e["key"]: e for e in entries})
        entries = [old[s.key] for s in CATALOGUE if s.key in old]
    index.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")

    for e in entries:
        print(f"{e['key']:20} {len(e['clips'])} animaci  delka {e['size']}")
    print(index)


if __name__ == "__main__":
    main()
