"""Z 3D modelu vyrobi predlohu k vybarveni: SVG k tisku, PNG nahled, JSON s mapovanim.

    python tools/model_sheet.py                       # cely katalog
    python tools/model_sheet.py trex3d                # jen vybrane
    python tools/model_sheet.py trex3d --anim Attack --time 0.75
"""
import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dinostanice import modelsheet as ms
from dinostanice.creatures3d import BY_KEY, CATALOGUE, Model3D
from dinostanice.gltf import Model
from dinostanice.markers import CORNER_ORIGINS, MARKER_MM, marker_bits, marker_ids
from dinostanice.modelsheet import DETAIL_MM
from dinostanice.shapes import LINE_MM, SHEET_H_MM, SHEET_W_MM

ROOT = Path(__file__).resolve().parent.parent


def to_svg(shape: ms.SheetShape, marker_index: int, extras_shapes: dict | None = None) -> str:
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
    for slot in shape.extras:
        ex = (extras_shapes or {}).get(slot["key"])
        x, y, bw, bh = slot["rect"]
        out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="3" '
                   f'fill="none" stroke="#999" stroke-width="0.4" stroke-dasharray="2 1.6"/>')
        label = ex.label if ex else slot["key"]
        out.append(f'<text x="{x + bw / 2:.2f}" y="{y + 3.4:.2f}" font-family="Verdana,sans-serif" '
                   f'font-size="3" fill="#888" text-anchor="middle">+ {label}</text>')
        if ex is not None:
            outline, regions = ms.extra_polys(ex, slot)
            for poly, w in ([(p, ms.EXTRA_DETAIL_MM) for p in regions]
                            + [(p, ms.EXTRA_LINE_MM) for p in outline]):
                pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in poly)
                out.append(f'<polygon points="{pts}" fill="none" stroke="#111" '
                           f'stroke-width="{w}" stroke-linejoin="round"/>')
            if ex.eye:
                f, off = slot["scale"], slot["offset"]
                ex_x, ex_y, ex_r = ex.eye
                out.append(f'<circle cx="{ex_x * f + off[0]:.2f}" cy="{ex_y * f + off[1]:.2f}" '
                           f'r="{ex_r * f:.2f}" fill="none" stroke="#111" '
                           f'stroke-width="{ms.EXTRA_DETAIL_MM}"/>')
    for corner, mid in enumerate(marker_ids(marker_index)):
        ox, oy = CORNER_ORIGINS[corner]
        bits = marker_bits(mid)
        cell = MARKER_MM / bits.shape[0]
        for r in range(bits.shape[0]):
            for c in range(bits.shape[1]):
                if bits[r, c]:
                    out.append(f'<rect x="{ox + c * cell:.3f}" y="{oy + r * cell:.3f}" '
                               f'width="{cell:.3f}" height="{cell:.3f}" fill="#000"/>')
    hint = ""
    if shape.extras:
        names = " / ".join((extras_shapes or {}).get(e["key"]).label.lower()
                           if (extras_shapes or {}).get(e["key"]) else e["key"] for e in shape.extras)
        hint = f" &#183; vybarvené okénko přidá i: {names}"
    out.append(f'<text x="{SHEET_W_MM / 2:.1f}" y="{SHEET_H_MM - 6:.1f}" '
               f'font-family="Verdana,sans-serif" font-size="{6 if not hint else 4.6}" fill="#999" '
               f'text-anchor="middle">{shape.label} &#183; vybarvi mě a vyfoť{hint}</text>')
    out.append("</svg>")
    return "\n".join(out)


def build_one(spec: Model3D, anim: str | None = None, time: float | None = None) -> ms.SheetShape:
    model = Model(ROOT / "data/models_src" / spec.glb)
    if anim:
        clip = model.clip(anim)
        t = time if time is not None else (spec.time or 0.0)
    elif spec.anim and spec.time is not None:
        clip, t = model.clip(spec.anim), spec.time
    else:
        clip, t = ms.best_pose(model, spec.candidates(model), axes=spec.axes, flip=spec.flip)
        t = time if time is not None else t
    shape = ms.build(model, key=spec.key, label=spec.label, anim=clip, time=t, ppm=14.0,
                     axes=spec.axes, flip=spec.flip, eye_joint=spec.eye_joint,
                     eye_bias=spec.eye_bias)

    # doplnky sceny (ptacek, motylek) dostanou okenko v rohu kazdeho jineho listu
    extras = {}
    if not spec.extra:
        for e in CATALOGUE:
            path = ROOT / f"data/shapes3d/{e.key}.json"
            if e.extra and e.scene == spec.scene and path.exists():
                extras[e.key] = ms.load(path)
        shape.extras = ms.place_extras(shape, list(extras.values()))
        missed = [k for k in extras if k not in {x["key"] for x in shape.extras}]
        for k in missed:
            print(f"  ! {spec.key}: okenko pro {k} se na list nevejde")

    (ROOT / "data/shapes3d").mkdir(exist_ok=True)
    ms.save(shape, ROOT / f"data/shapes3d/{spec.key}.json")
    (ROOT / f"data/templates/{spec.key}.svg").write_text(
        to_svg(shape, spec.marker_index, extras), encoding="utf-8")
    cv2.imwrite(str(ROOT / f"out/{spec.key}_sheet.png"),
                ms.rasterise(shape, extras_shapes=extras))
    return shape


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="klice z katalogu; prazdne = vsechny")
    ap.add_argument("--anim", default=None, help="jmeno animace, napr. Attack")
    ap.add_argument("--time", type=float, default=None)
    args = ap.parse_args()

    specs = [BY_KEY[k] for k in args.keys] if args.keys else CATALOGUE
    specs = sorted(specs, key=lambda m: not m.extra)       # doplnky prvni: hostitele z nich cerpaji
    for spec in specs:
        shape = build_one(spec, args.anim, args.time)
        eye = "oko ano" if shape.eye else "OKO SE NENASLO"
        pose = shape.anim.split("_")[-1]
        print(f"{spec.key:20} {pose:8} t={shape.time:.2f}  "
              f"{len(shape.regions):>2} vnitrnich linek  {eye}")


if __name__ == "__main__":
    main()
