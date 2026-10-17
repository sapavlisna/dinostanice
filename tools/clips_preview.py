"""Kontrola klipů z tools/blender_clips.py: čísla a náhledy s vybarvenou texturou.

    python tools/clips_preview.py trex3d tmp/trex_clips.glb
    python tools/clips_preview.py triceratops3d tmp/triceratops_clips.glb --out tmp/prev

Vypíše, jestli původní klipy zůstaly beze změny, jestli nové klipy začínají
v póze Idle (žádný skok při prolnutí), jestli smyčky končí, kde začaly,
a kde má model v každé póze spodek (min y = zem). Náhledy: řádek na klip,
sloupce v čase, z boku a šikmo; jednou s ukázkovou texturou (pruhy — vidět
roztržení) a jednou se syntetickým dětským vybarvením.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import model_paint_demo as demo  # noqa: E402
from dinostanice import modelsheet as ms  # noqa: E402
from dinostanice import orthoview as ov  # noqa: E402
from dinostanice.creatures3d import BY_KEY  # noqa: E402
from dinostanice.gltf import Model  # noqa: E402

NEW = ("Sit", "LieDown", "Sleep", "LookAround")
LOOPS = ("Sleep", "LookAround")


def joints(model, anim, t):
    world = model.global_matrices(anim, t)
    return {model.node_names[j]: world[j][:3, 3] for j in model.skin_joints}


def jump(model, a, ta, b, tb):
    ja, jb = joints(model, a, ta), joints(model, b, tb)
    return max(float(np.linalg.norm(ja[k] - jb[k])) for k in ja)


def report(orig, model):
    ok = True
    for name, anim in orig.animations.items():
        new = model.animations.get(name)
        same = new is not None and all(
            np.array_equal(v[0], new.channels[n][p][0]) and np.array_equal(v[1], new.channels[n][p][1])
            for n, paths in anim.channels.items() for p, v in paths.items())
        ok &= same
        print(f"{name:40} {'beze změny' if same else 'ZMĚNĚNO'}")

    idle = model.clip("Idle")
    p0, _ = orig.posed(idle, 0.0)
    size = float(np.ptp(p0, axis=0).max())
    ground = float(p0[:, 1].min())
    print(f"Idle: zem y={ground:.3f}, velikost {size:.2f}")
    for short in NEW:
        full = model.clip(short)
        if full is None:
            print(f"{short:12} CHYBÍ")
            ok = False
            continue
        dur = model.animations[full].duration
        start = jump(model, full, 0.0, idle, 0.0)
        line = f"{short:12} {full:32} {dur:5.2f} s  start vs Idle {start / size:6.2%}"
        if short in LOOPS:
            line += f"  konec vs start {jump(model, full, dur, full, 0.0) / size:6.2%}"
        lows, spans = [], []
        for t in np.linspace(0, dur, 9):
            p, _ = model.posed(full, t)
            lows.append(p[:, 1].min() - ground)
            spans.append(np.ptp(p, axis=0).max() / size)
        line += (f"  spodek {min(lows) / size:+.3f}..{max(lows) / size:+.3f}"
                 f"  rozměr {min(spans):.2f}..{max(spans):.2f}")
        print(line)
    return ok


def textures(key, shape):
    stripes = ms.to_texture(demo.paint_sheet(shape), shape, demo.PPM)
    import helpers as H
    kid = H.sheet(key, strokes=40, ppm=demo.PPM).img
    return {"pruhy": stripes, "vybarveni": ms.to_texture(kid, shape, demo.PPM)}


def yawed(model, anim, t, yaw):
    verts, normals = model.posed(anim, t)
    a = np.radians(yaw)
    rot = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return verts @ rot.T, normals @ rot.T


def frame(model, yaw):
    """Společný rámec pro všechny snímky, aby lehnutí nevypadalo jako zvětšení."""
    verts, _ = yawed(model, model.clip("Idle"), 0.0, yaw)
    lo = np.array([verts[:, 2].min(), -verts[:, 1].max()])
    hi = np.array([verts[:, 2].max(), -verts[:, 1].min()])
    pad = 0.08 * (hi - lo).max()
    return lo - pad, hi + np.array([pad, 0.02 * pad])


def shot(model, uv_px, tex, anim, t, yaw, bounds, width):
    """Jako model_paint_demo.shot, jen v pevném rámci a se zemí."""
    verts, normals = yawed(model, anim, t, yaw)
    view = ov.render(verts, model.indices, normals, width=width, bounds=bounds)
    px = view.sample(model.indices, uv_px)
    H, W = view.mask.shape
    out = np.full((H, W, 3), 255, np.uint8)
    out[-2:] = 150
    xi = np.clip(px[..., 0].astype(int), 0, tex.shape[1] - 1)
    yi = np.clip(px[..., 1].astype(int), 0, tex.shape[0] - 1)
    shade = 0.55 + 0.45 * np.clip(view.normal @ np.array([-0.6, 0.5, 0.62]), 0, 1)
    colour = np.clip(tex[yi, xi].astype(float) * shade[..., None], 0, 255).astype(np.uint8)
    out[view.mask] = colour[view.mask]
    return out


def grid(tiles, cols):
    h = max(t.shape[0] for t in tiles) + 8
    w = max(t.shape[1] for t in tiles) + 8
    rows = (len(tiles) + cols - 1) // cols
    out = np.full((h * rows, w * cols, 3), 255, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y0, x0 = r * h + (h - t.shape[0]) // 2, c * w + (w - t.shape[1]) // 2
        out[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
    return out


def label(img, text):
    img = img.copy()
    cv2.putText(img, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
    return img


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="klíč tvora (data/shapes3d/<key>.json)")
    ap.add_argument("glb", help="GLB s doplněnými klipy")
    ap.add_argument("--out", default=str(ROOT / "tmp/clips"))
    ap.add_argument("--width", type=int, default=300)
    ap.add_argument("--rychle", action="store_true", help="jen pruhy z boku")
    args = ap.parse_args()

    spec = BY_KEY[args.key]
    orig = Model(ROOT / "data/models_src" / spec.glb)
    model = Model(args.glb)
    ok = report(orig, model)

    shape = ms.load(ROOT / f"data/shapes3d/{args.key}.json")
    uv = demo.texture_uv(model, shape)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    idle = model.clip("Idle")
    texs = textures(args.key, shape)
    if args.rychle:
        texs = {"pruhy": texs["pruhy"]}
    for tex_name, tex in texs.items():
        for yaw in ((0,) if args.rychle else (0, 35)):
            box = frame(model, yaw)
            tiles = [label(shot(model, uv, tex, idle, 0.0, yaw, box, args.width), "Idle")]
            tiles += [np.full((10, 10, 3), 255, np.uint8)] * 3
            for short in NEW:
                full = model.clip(short)
                dur = model.animations[full].duration
                for f in (0.25, 0.5, 0.75, 1.0):
                    t = dur * f
                    tiles.append(label(shot(model, uv, tex, full, t, yaw, box, args.width),
                                       f"{short} {t:.1f}s"))
            path = out / f"{args.key}_{tex_name}_{yaw}.png"
            cv2.imwrite(str(path), grid(tiles, 4))
            print(path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
