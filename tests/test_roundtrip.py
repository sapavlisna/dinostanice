"""Is rig.unwrap_body's straightened body strip informationally honest?

Paint small dots at known millimetre positions on a canonical (unphotographed)
sheet, unwrap it, and check two things quantitatively, in millimetres:
1) each dot lands at the strip row/column its own spine-sample/offset predicts;
2) scattering the strip back onto a blank sheet -- using literally the same
   per-pixel sheet coordinates unwrap_body computed to sample it in the first
   place, just read the other way round -- reproduces each dot's original
   position. Any smearing or misregistration in the unwrap would show up here
   as a position error much larger than one strip pixel's worth of millimetres.
"""

import cv2
import numpy as np
import pytest

from dinostanice import creatures as cr, rig
from dinostanice.capture import WARP_PPM
from dinostanice.raster import creature_mask
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM, body_centerline, resample_profile

PPM = WARP_PPM
SPINE_BODIED = [c for c in cr.CATALOGUE if c.outline is None]  # everything but the rigid ship

# one warped pixel is 1/PPM mm; allow a couple of pixels of slack for the paint
# circle's own radius, remap interpolation and integer scatter rounding.
MAX_POSITION_ERROR_MM = 2.5 / PPM


def _arclen(points):
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def _geometry(creature, ppm=PPM):
    """Take the geometry straight from unwrap_body's exported metadata.

    Reproducing it here instead would mean keeping a second copy of the
    implementation in step with the first -- including details like sampling
    past the tube's end caps -- and would test the copy rather than the contract.
    """
    W, H = int(round(SHEET_W_MM * ppm)), int(round(SHEET_H_MM * ppm))
    _, meta = rig.unwrap_body(np.zeros((H, W, 4), np.uint8), creature, ppm=ppm)
    line = np.asarray(meta["spine_mm"], dtype=float)
    radii = np.asarray(meta["radius_mm"], dtype=float)
    tang = np.gradient(line, axis=0)
    tang = tang / np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    normal = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    return line, radii, normal


def _scatter_back(strip, line, normal, offsets, ppm, shape):
    """Inverse of unwrap_body's cv2.remap: for every strip pixel, paint its colour at the
    sheet-space coordinate unwrap_body would have sampled it from -- i.e. run the same
    analytic mapping the other way (scatter instead of gather).
    """
    canvas = np.zeros(shape, np.uint8)
    strip_w = strip.shape[1]
    cols = np.arange(strip_w)
    for r, off in enumerate(offsets):
        dst = line + normal * off
        xs = np.round(dst[:, 0] * ppm).astype(int)
        ys = np.round(dst[:, 1] * ppm).astype(int)
        valid = (xs >= 0) & (xs < shape[1]) & (ys >= 0) & (ys < shape[0])
        canvas[ys[valid], xs[valid]] = strip[r, cols[valid]]
    return canvas


@pytest.mark.parametrize("creature", SPINE_BODIED, ids=[c.key for c in SPINE_BODIED])
def test_unwrap_roundtrip_preserves_dot_positions(creature):
    line, radii, normal = _geometry(creature)
    W, H = int(round(SHEET_W_MM * PPM)), int(round(SHEET_H_MM * PPM))
    sheet = np.zeros((H, W, 4), np.uint8)

    n = len(radii)
    candidates = [int(n * f) for f in (0.12, 0.35, 0.6, 0.85)]
    sample_cols = [c for c in candidates if c < n and radii[c] > 3.0]
    assert len(sample_cols) >= 3, "creature profile too thin to place safe test dots"
    colors = [(255, 40, 40, 255), (40, 220, 40, 255), (40, 40, 255, 255), (40, 220, 220, 255)]

    dots_mm = []
    for col, color in zip(sample_cols, colors):
        offset_mm = 0.4 * radii[col]
        pt_mm = line[col] + normal[col] * offset_mm
        dots_mm.append((col, offset_mm, pt_mm, color))
        cv2.circle(sheet, (int(round(pt_mm[0] * PPM)), int(round(pt_mm[1] * PPM))), 3, color, -1)
    sheet[:, :, 3] = creature_mask(creature, ppm=PPM)

    strip, meta = rig.unwrap_body(sheet, creature, ppm=PPM)
    offsets = np.linspace(-meta["half_mm"], meta["half_mm"], strip.shape[0])

    for col, offset_mm, pt_mm, color in dots_mm:
        expected_row = int(np.argmin(np.abs(offsets - offset_mm)))
        window = strip[max(0, expected_row - 4):expected_row + 5, max(0, col - 4):col + 5, :3]
        dist = np.linalg.norm(window.astype(int) - np.array(color[:3]), axis=2)
        assert dist.min() < 60, f"{creature.key}: dot at column {col} not found near predicted strip row {expected_row}"

    canvas = _scatter_back(strip, line, normal, offsets, PPM, sheet.shape)
    for col, offset_mm, pt_mm, color in dots_mm:
        target = np.array(color[:3])
        dist = np.linalg.norm(canvas.astype(int)[:, :, :3] - target, axis=2)
        ys, xs = np.nonzero(dist < 40)
        assert len(xs) > 0, f"{creature.key}: dot at column {col} vanished after mapping the strip back onto the sheet"
        centroid_mm = np.array([xs.mean(), ys.mean()]) / PPM
        err_mm = float(np.linalg.norm(centroid_mm - pt_mm))
        assert err_mm < MAX_POSITION_ERROR_MM, (
            f"{creature.key}: round-tripped dot at column {col} is {err_mm:.3f}mm from its original position"
        )
