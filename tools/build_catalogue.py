"""Precompute creature geometry from the downloaded silhouettes.

Deriving a shape means skeletonising a bitmap, which is far too slow to run on
every import. This bakes the result into data/shapes/<key>.json, which
dinostanice.creatures then just reads.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dinostanice import silhouette
from dinostanice.shapes import split_limb_polygon

SIL_DIR = "data/silhouettes"
OUT_DIR = "data/shapes"
CONTROL_POINTS = 20


def control_points(spine, profile, n=CONTROL_POINTS):
    """Thin the dense derived spine down to control points.

    The rest of the model runs every spine through catmull_rom, so feeding it a
    per-pixel curve would both bloat it and smooth it twice.
    """
    spine = np.asarray(spine, dtype=float)
    profile = np.asarray(profile, dtype=float)
    d = np.linalg.norm(np.diff(spine, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    target = np.linspace(0, s[-1], n)
    x = np.interp(target, s, spine[:, 0])
    y = np.interp(target, s, spine[:, 1])
    r = np.interp(target, s, profile)
    return np.stack([x, y], axis=1), r


def round_poly(p, nd=2):
    return [[round(float(a), nd), round(float(b), nd)] for a, b in np.asarray(p)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    credits = json.load(open(os.path.join(SIL_DIR, "credits.json"), encoding="utf-8"))

    for entry in credits:
        key = entry["key"]
        png = os.path.join(SIL_DIR, f"{key}.png")
        shape = silhouette.derive(png, view=entry["view"], motion=entry["motion"])
        spine, profile = control_points(shape.spine, shape.profile)

        limbs = []
        for limb in shape.limbs:
            parts = split_limb_polygon(limb.polygon, limb.joints)
            limbs.append({
                "name": limb.name,
                "anchor": round(float(limb.anchor), 4),
                "side": int(limb.side),
                "parts": [{"poly": round_poly(p), "pivot": round_poly([piv])[0],
                           "tip": round_poly([tip])[0]} for p, piv, tip in parts],
            })

        doc = {
            "key": key, "label": entry["label"],
            "motion": entry["motion"], "view": entry["view"],
            "source": entry["source"], "author": entry["author"], "licence": entry["licence"],
            "spine": round_poly(spine), "profile": [round(float(r), 3) for r in profile],
            "outline": [round_poly(p) for p in shape.outline],
            "limbs": limbs,
        }
        path = os.path.join(OUT_DIR, f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

        segs = sum(len(l["parts"]) for l in limbs)
        print(f"{key:12s} {len(doc['outline'])} obrysů, páteř {len(spine)} bodů, "
              f"{len(limbs)} končetin / {segs} dílů, {os.path.getsize(path)//1024} kB")


if __name__ == "__main__":
    main()
