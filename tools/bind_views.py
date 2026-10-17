"""Náhled tvaru s mřížkou pro odečítání landmarks do tools/bindmaps/<zvíře>.json.

    python tools/bind_views.py PREP.glb out.png                  bok + zepředu + shora
    python tools/bind_views.py PREP.glb out.png --map MAPA.json  i s landmarks z mapy
    python tools/bind_views.py HOTOVY.glb out.png --clip Walk --t 0.3

PREP.glb je výstup `blender_bind.py ... --prep` (jednotkový rámec: délka 1,
stojí na y=0, hlava k +Z). Mřížka po 0,05, popisky po 0,1. U hotového
(skinovaného) GLB se kreslí póza klipu a klouby kostry.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dinostanice.gltf import Model  # noqa: E402

SKIP = ("Pole", "Root", "Station", "Armature")


def landmarks(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for k, lm in cfg.get("landmarks", {}).items():
        out[k] = np.array(lm["at"], float)
        if re.search(r"\.L(?=$|_)", k) and lm.get("mirror", True):
            out[re.sub(r"\.L(?=$|_)", ".R", k)] = out[k] * [-1, 1, 1]
    return out


def view(v, tris, points, a, b, depth, size, flip=False, step=0.05):
    lo, hi = v.min(0), v.max(0)
    S = size / max(hi[a] - lo[a], hi[b] - lo[b])
    w, h = int((hi[a] - lo[a]) * S) + 80, int((hi[b] - lo[b]) * S) + 80
    sx = -1 if flip else 1
    x0 = hi[a] if flip else lo[a]

    def P(p):
        return int((p[a] - x0) * sx * S) + 40, int((hi[b] - p[b]) * S) + 40

    im = np.full((h, w, 3), 255, np.uint8)
    for axis, lo_, hi_ in ((a, lo[a], hi[a]), (b, lo[b], hi[b])):
        for g in np.arange(np.floor(lo_ / step) * step, hi_ + step, step):
            q = P(np.eye(3)[axis] * g)
            major = round(g / step) % 2 == 0
            col = (180, 180, 255) if major else (228, 228, 228)
            if axis == a:
                cv2.line(im, (q[0], 0), (q[0], h), col, 1)
                if major:
                    cv2.putText(im, f"{g:.1f}", (q[0] + 2, 12), 0, 0.35, (0, 0, 200), 1)
            else:
                cv2.line(im, (0, q[1]), (w, q[1]), col, 1)
                if major:
                    cv2.putText(im, f"{g:.1f}", (2, q[1] - 2), 0, 0.35, (0, 0, 200), 1)
    order = np.argsort(v[tris].mean(1)[:, depth] * (1 if depth != 1 else -1))
    for tri in tris[order]:
        pts = np.array([P(v[i]) for i in tri], np.int32)
        cv2.fillPoly(im, [pts], (150, 170, 150))
        cv2.polylines(im, [pts], True, (110, 130, 110), 1)
    for n, p in points.items():
        q = P(p)
        cv2.circle(im, q, 4, (0, 0, 255), -1)
        cv2.putText(im, n, (q[0] + 4, q[1] - 3), 0, 0.33, (200, 0, 0), 1)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("out")
    ap.add_argument("--map")
    ap.add_argument("--clip")
    ap.add_argument("--t", type=float, default=0.0)
    ap.add_argument("--size", type=int, default=900)
    args = ap.parse_args()
    m = Model(args.glb)
    points = {}
    if m.skin_joints is not None:
        clip = m.clip(args.clip) if args.clip else None
        v, _ = m.posed(clip, args.t)
        W = m.global_matrices(clip, args.t)
        points = {n: W[i][:3, 3] for i, n in enumerate(m.node_names)
                  if not n.startswith(SKIP) and i in set(m.skin_joints)}
    else:
        v = m.positions.copy()
    if args.map:
        points = landmarks(args.map)
    side = view(v, m.indices, {k: p for k, p in points.items() if not k.endswith(".R")},
                2, 1, 0, args.size)
    front = view(v, m.indices, points, 0, 1, 2, args.size // 2, flip=True)
    top = view(v, m.indices, {}, 2, 0, 1, args.size)
    H = max(side.shape[0], front.shape[0])
    pad = lambda im, hh, ww: cv2.copyMakeBorder(  # noqa: E731
        im, 0, hh - im.shape[0], 0, ww - im.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255))
    row = np.hstack([pad(side, H, side.shape[1]), pad(front, H, front.shape[1])])
    out = np.vstack([row, pad(top, top.shape[0], row.shape[1])])
    cv2.imwrite(args.out, out)
    print(args.out)


if __name__ == "__main__":
    main()
