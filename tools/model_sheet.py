"""Z 3D modelu vyrobi predlohu k vybarveni: SVG k tisku, PNG nahled, JSON s mapovanim.

    python tools/model_sheet.py                       # cely katalog
    python tools/model_sheet.py trex3d                # jen vybrane
    python tools/model_sheet.py trex3d --anim Attack --time 0.75
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dinostanice import modelsheet as ms
from dinostanice.creatures3d import BY_KEY, CATALOGUE, Model3D
from dinostanice.gltf import Model
from dinostanice.markers import CORNER_ORIGINS, MARKER_MM, marker_bits, marker_ids
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

ROOT = Path(__file__).resolve().parent.parent
LINE_MM = 0.9
DETAIL_MM = 0.6


def to_svg(shape: ms.SheetShape, marker_index: int) -> str:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W_MM}mm" '
        f'height="{SHEET_H_MM}mm" viewBox="0 0 {SHEET_W_MM} {SHEET_H_MM}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    for poly, w in [(p, DETAIL_MM) for p in shape.regions] + [(p, LINE_MM) for p in shape.outline]:
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
        out.append(f'<polygon points="{pts}" fill="none" stroke="#111" '
                   f'stroke-width="{w}" stroke-linejoin="round"/>')
    if shape.eye:
        x, y, r = shape.eye
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="none" '
                   f'stroke="#111" stroke-width="{LINE_MM}"/>')
    for corner, mid in enumerate(marker_ids(marker_index)):
        ox, oy = CORNER_ORIGINS[corner]
        bits = marker_bits(mid)
        cell = MARKER_MM / bits.shape[0]
        for r in range(bits.shape[0]):
            for c in range(bits.shape[1]):
                if bits[r, c]:
                    out.append(f'<rect x="{ox + c * cell:.3f}" y="{oy + r * cell:.3f}" '
                               f'width="{cell:.3f}" height="{cell:.3f}" fill="#000"/>')
    out.append(f'<text x="{SHEET_W_MM / 2:.1f}" y="{SHEET_H_MM - 6:.1f}" '
               f'font-family="Verdana,sans-serif" font-size="6" fill="#999" '
               f'text-anchor="middle">{shape.label} &#183; vybarvi mě a vyfoť</text>')
    out.append("</svg>")
    return "\n".join(out)


def preview(shape: ms.SheetShape, ppm: float = 6.0) -> np.ndarray:
    img = np.full((int(SHEET_H_MM * ppm), int(SHEET_W_MM * ppm), 3), 255, np.uint8)
    for poly in shape.regions:
        cv2.polylines(img, [np.round(poly * ppm).astype(np.int32)], True, (17, 17, 17),
                      max(1, int(round(DETAIL_MM * ppm))), cv2.LINE_AA)
    for poly in shape.outline:
        cv2.polylines(img, [np.round(poly * ppm).astype(np.int32)], True, (17, 17, 17),
                      max(1, int(round(LINE_MM * ppm))), cv2.LINE_AA)
    if shape.eye:
        x, y, r = shape.eye
        cv2.circle(img, (int(x * ppm), int(y * ppm)), int(r * ppm), (17, 17, 17),
                   max(1, int(round(LINE_MM * ppm))), cv2.LINE_AA)
    return img


def build_one(spec: Model3D, anim: str | None = None, time: float | None = None) -> ms.SheetShape:
    model = Model(ROOT / "data/models_src" / spec.glb)
    if anim:
        clip = model.clip(anim)
        t = time if time is not None else (spec.time or 0.0)
    else:
        clip, t = ms.best_pose(model, spec.candidates(model), axes=spec.axes, flip=spec.flip)
        t = time if time is not None else t
    shape = ms.build(model, key=spec.key, label=spec.label, anim=clip, time=t, ppm=14.0,
                     axes=spec.axes, flip=spec.flip, eye_bias=spec.eye_bias)

    (ROOT / "data/shapes3d").mkdir(exist_ok=True)
    ms.save(shape, ROOT / f"data/shapes3d/{spec.key}.json")
    (ROOT / f"data/templates/{spec.key}.svg").write_text(
        to_svg(shape, spec.marker_index), encoding="utf-8")
    cv2.imwrite(str(ROOT / f"out/{spec.key}_sheet.png"), preview(shape))
    return shape


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="klice z katalogu; prazdne = vsechny")
    ap.add_argument("--anim", default=None, help="jmeno animace, napr. Attack")
    ap.add_argument("--time", type=float, default=None)
    args = ap.parse_args()

    specs = [BY_KEY[k] for k in args.keys] if args.keys else CATALOGUE
    for spec in specs:
        shape = build_one(spec, args.anim, args.time)
        eye = "oko ano" if shape.eye else "OKO SE NENASLO"
        pose = shape.anim.split("_")[-1]
        print(f"{spec.key:20} {pose:8} t={shape.time:.2f}  "
              f"{len(shape.regions):>2} oblasti  {eye}")


if __name__ == "__main__":
    main()
