"""Uzavre kruh: vybarveny list -> textura na 3D modelu -> jine pozy a uhly.

Kresli se syntetickym vybarvenim (pruhy a puntiky), aby bylo videt, jestli
textura sedi i po rozhybani modelu. Bez tiskarny a bez fotoaparatu.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dinostanice import modelsheet as ms
from dinostanice import orthoview as ov
from dinostanice.gltf import Model
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

ROOT = Path(__file__).resolve().parent.parent
PPM = 6.0


def paint_sheet(shape: ms.SheetShape) -> np.ndarray:
    """Syntetycky vybarveny list — to, co by odevzdalo dite."""
    W, H = int(SHEET_W_MM * PPM), int(SHEET_H_MM * PPM)
    img = np.full((H, W, 3), 255, np.uint8)
    body = np.zeros((H, W), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * PPM).astype(np.int32)], 1)

    ys, xs = np.mgrid[0:H, 0:W]
    stripes = ((xs // int(9 * PPM)) % 2).astype(bool)
    base = np.where(stripes[..., None], np.array([70, 170, 90]), np.array([40, 120, 200]))
    img[body > 0] = base[body > 0]

    rng = np.random.default_rng(7)
    for _ in range(60):
        cx, cy = rng.integers(0, W), rng.integers(0, H)
        if body[cy, cx]:
            cv2.circle(img, (int(cx), int(cy)), int(rng.integers(2, 5) * PPM),
                       (40, 230, 250), -1, cv2.LINE_AA)
    img[body == 0] = 255

    for poly in shape.regions:
        cv2.polylines(img, [np.round(poly * PPM).astype(np.int32)], True, (30, 30, 30), 2, cv2.LINE_AA)
    for poly in shape.outline:
        cv2.polylines(img, [np.round(poly * PPM).astype(np.int32)], True, (20, 20, 20), 3, cv2.LINE_AA)
    if shape.eye:
        x, y, r = shape.eye
        cv2.circle(img, (int(x * PPM), int(y * PPM)), int(r * PPM), (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, (int(x * PPM), int(y * PPM)), int(r * PPM * 0.5), (20, 20, 20), -1, cv2.LINE_AA)
        cv2.circle(img, (int(x * PPM), int(y * PPM)), int(r * PPM), (20, 20, 20), 2, cv2.LINE_AA)
    return img


def texture_uv(model: Model, shape: ms.SheetShape) -> np.ndarray:
    """UV kazdeho vrcholu = kde lezi na listu v poze predlohy."""
    verts, _ = model.posed(shape.anim or None, shape.time)
    mm = shape.placement.to_mm(verts)
    return np.stack([mm[:, 0] * PPM, mm[:, 1] * PPM], axis=1)


def shot(model: Model, uv_px: np.ndarray, sheet: np.ndarray, anim: str, t: float,
         yaw_deg: float, width: int = 620) -> np.ndarray:
    verts, normals = model.posed(anim, t)
    a = np.radians(yaw_deg)
    rot = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    verts = verts @ rot.T
    normals = normals @ rot.T
    view = ov.render(verts, model.indices, normals, width=width, margin=0.06)
    px = view.sample(model.indices, uv_px)
    H, W = view.mask.shape
    out = np.full((H, W, 3), 255, np.uint8)
    xi = np.clip(px[..., 0].astype(int), 0, sheet.shape[1] - 1)
    yi = np.clip(px[..., 1].astype(int), 0, sheet.shape[0] - 1)
    colour = sheet[yi, xi].astype(float)
    shade = 0.55 + 0.45 * np.clip(view.normal @ np.array([-0.6, 0.5, 0.62]), 0, 1)
    out[view.mask] = np.clip(colour * shade[..., None], 0, 255).astype(np.uint8)[view.mask]
    return out


def main() -> None:
    shape = ms.load(ROOT / "data/shapes3d/trex3d.json")
    model = Model(ROOT / "data/models_src/trex.glb")
    sheet = paint_sheet(shape)
    cv2.imwrite(str(ROOT / "out/trex3d_painted.png"), sheet)
    tex = ms.to_texture(sheet, shape, PPM)

    uv = texture_uv(model, shape)
    shots = [
        ("Armature|TRex_Walk", 0.7, 0),
        ("Armature|TRex_Walk", 0.7, 35),
        ("Armature|TRex_Walk", 0.7, 90),
        ("Armature|TRex_Walk", 0.15, 12),
        ("Armature|TRex_Run", 0.4, 25),
        ("Armature|TRex_Attack", 0.75, 8),
    ]
    tiles = [shot(model, uv, tex, a, t, y) for a, t, y in shots]
    h = max(t.shape[0] for t in tiles) + 12
    w = max(t.shape[1] for t in tiles) + 12
    grid = np.full((h * 2, w * 3, 3), 255, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, 3)
        y0 = r * h + (h - t.shape[0]) // 2
        x0 = c * w + (w - t.shape[1]) // 2
        grid[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
    cv2.imwrite(str(ROOT / "out/trex3d_shots.png"), grid)
    print("out/trex3d_painted.png\nout/trex3d_shots.png")


if __name__ == "__main__":
    main()
