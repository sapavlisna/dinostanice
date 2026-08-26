"""Synthetic coloured-in sheets and simulated phone photos.

Lets the whole pipeline be developed and regression-tested without a printer,
and produces stand-in textures for animation work.
"""

import cv2
import numpy as np

from .template import rasterise
from .raster import creature_mask
from .shapes import SHEET_W_MM, SHEET_H_MM

CRAYONS = [
    (60, 60, 210), (40, 140, 240), (60, 170, 90), (200, 120, 40),
    (30, 200, 230), (150, 70, 160), (70, 200, 240), (200, 80, 90),
]


def scribble(creature, creature_index, ppm=6.0, seed=0, sloppiness=1.0, strokes=26):
    """A template with crayon scribbles roughly inside the silhouette."""
    rng = np.random.default_rng(seed)
    sheet = rasterise(creature, creature_index, ppm=ppm)
    mask = creature_mask(creature, ppm=ppm)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return sheet

    layer = sheet.copy()
    for _ in range(strokes):
        colour = CRAYONS[rng.integers(len(CRAYONS))]
        i = rng.integers(len(xs))
        px, py = float(xs[i]), float(ys[i])
        angle = rng.uniform(0, 2 * np.pi)
        width = int(rng.integers(3, 9) * ppm / 6.0) + 1
        pts = [(px, py)]
        for _ in range(int(rng.integers(8, 26))):
            angle += rng.normal(0, 0.9)
            step = rng.uniform(6, 16) * ppm / 6.0
            px += np.cos(angle) * step
            py += np.sin(angle) * step
            pts.append((px, py))
        poly = np.round(np.array(pts)).astype(np.int32)
        stroke = np.zeros(mask.shape, np.uint8)
        cv2.polylines(stroke, [poly], False, 255, width, cv2.LINE_AA)
        # children colour past the outline, but only a little
        allowed = cv2.dilate(mask, np.ones((int(9 * sloppiness) * 2 + 1,) * 2, np.uint8))
        stroke = cv2.bitwise_and(stroke, allowed)
        alpha = (stroke.astype(np.float32) / 255.0 * rng.uniform(0.35, 0.75))[:, :, None]
        layer = (layer * (1 - alpha) + np.array(colour, np.float32) * alpha).astype(np.uint8)

    # the heavy black felt-tip pass children love
    for _ in range(int(rng.integers(2, 6))):
        i = rng.integers(len(xs))
        px, py = float(xs[i]), float(ys[i])
        angle = rng.uniform(0, 2 * np.pi)
        pts = [(px, py)]
        for _ in range(int(rng.integers(4, 12))):
            angle += rng.normal(0, 1.2)
            step = rng.uniform(8, 20) * ppm / 6.0
            px += np.cos(angle) * step
            py += np.sin(angle) * step
            pts.append((px, py))
        poly = np.round(np.array(pts)).astype(np.int32)
        stroke = np.zeros(mask.shape, np.uint8)
        cv2.polylines(stroke, [poly], False, 255, int(3 * ppm / 6.0) + 2, cv2.LINE_AA)
        stroke = cv2.bitwise_and(stroke, cv2.dilate(mask, np.ones((9, 9), np.uint8)))
        layer[stroke > 60] = (30, 28, 26)

    grain = rng.normal(0, 3.0, layer.shape[:2])[:, :, None]
    return np.clip(layer.astype(np.float32) + grain, 0, 255).astype(np.uint8)


def photograph(sheet, seed=0, out_size=(2016, 1512), tilt=1.0, blur=1.0):
    """Simulate holding a phone over the sheet: perspective, lighting, blur, noise, JPEG."""
    rng = np.random.default_rng(seed + 977)
    H, W = sheet.shape[:2]
    ow, oh = out_size

    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    inset_x, inset_y = ow * 0.10, oh * 0.10
    jitter = np.float32([
        [rng.normal(0, 0.05 * ow), rng.normal(0, 0.05 * oh)] for _ in range(4)
    ]) * tilt
    dst = np.float32([[inset_x, inset_y], [ow - inset_x, inset_y],
                      [ow - inset_x, oh - inset_y], [inset_x, oh - inset_y]]) + jitter

    M = cv2.getPerspectiveTransform(src, dst)
    bg = np.full((oh, ow, 3), 190, np.uint8)
    bg = (bg.astype(np.float32) + rng.normal(0, 6, bg.shape)).clip(0, 255).astype(np.uint8)
    img = cv2.warpPerspective(sheet, M, (ow, oh), dst=bg.copy(),
                              borderMode=cv2.BORDER_TRANSPARENT, flags=cv2.INTER_CUBIC)

    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    cx, cy = rng.uniform(0.2, 0.8) * ow, rng.uniform(0.2, 0.8) * oh
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / np.hypot(ow, oh)
    shade = (1.06 - 0.42 * r ** 1.3)
    img = np.clip(img.astype(np.float32) * shade[:, :, None], 0, 255).astype(np.uint8)

    if blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), 0.8 * blur)
    img = np.clip(img.astype(np.float32) + rng.normal(0, 3.5, img.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR) if ok else img
