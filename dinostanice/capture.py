"""Turning a phone photo of a coloured-in sheet into a creature texture."""

from collections import Counter

import cv2
import numpy as np

from .shapes import SHEET_W_MM, SHEET_H_MM
from .markers import DICT, creature_index_of, marker_corner_points_mm
from .raster import creature_mask
from .creatures import CATALOGUE
from .creatures3d import CATALOGUE as CATALOGUE3D

WARP_PPM = 5.0
WARP_W = int(round(SHEET_W_MM * WARP_PPM))
WARP_H = int(round(SHEET_H_MM * WARP_PPM))

_detector = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())

# One marker fixes a homography exactly, so nothing looks wrong -- but extrapolating
# it across the whole sheet is unstable and has been measured to land the cut-out
# tens of millimetres off. Better to ask for a new photo.
MIN_MARKERS = 2
MAX_FIT_ERROR_MM = 1.5

_COUNT_CZ = {1: "jednu rohovou značku", 2: "dvě rohové značky", 3: "tři rohové značky"}


class CaptureError(Exception):
    pass


def known_indices():
    """Indexy tvoru, ke kterym existuje vytistena sablona.

    Obe vetve sdileji jeden prostor znacek: starsi tvorove maji indexy 0-7,
    ti z 3D modelu 8 a vys.
    """
    return set(range(len(CATALOGUE))) | {m.marker_index for m in CATALOGUE3D}


def detect_sheet(bgr, min_markers=MIN_MARKERS):
    """Locate the sheet and flatten it. Returns (creature_index, warped_bgr, n_markers)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        raise CaptureError("na fotce nejsou vidět žádné rohové značky")

    ids = ids.flatten().tolist()
    valid = known_indices()
    known = [i for i in ids if creature_index_of(i)[0] in valid]
    if not known:
        raise CaptureError("značky na fotce nepatří k žádné šabloně")
    votes = Counter(creature_index_of(i)[0] for i in known)
    creature_index, _ = votes.most_common(1)[0]

    expected = marker_corner_points_mm(creature_index)
    src, dst = [], []
    for quad, mid in zip(corners, ids):
        if mid in expected:
            src.append(quad.reshape(4, 2))
            dst.append(expected[mid])
    if not src:
        raise CaptureError("značky nepatří k žádné šabloně")

    n_markers = len(src)
    if n_markers < min_markers:
        raise CaptureError(
            f"vidím jen {_COUNT_CZ.get(n_markers, str(n_markers))} ze čtyř — "
            "vyfoť celý list, ať jsou vidět všechny čtyři rohy")

    src = np.concatenate(src).astype(np.float32)
    dst = np.concatenate(dst).astype(np.float32) * WARP_PPM
    method = cv2.RANSAC if len(src) >= 12 else 0
    H, _ = cv2.findHomography(src, dst, method, 3.0)
    if H is None:
        raise CaptureError("nepodařilo se srovnat list do roviny")

    fit = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    fit_error_mm = float(np.median(np.linalg.norm(fit - dst, axis=1))) / WARP_PPM
    if fit_error_mm > MAX_FIT_ERROR_MM:
        raise CaptureError("rohové značky nesedí k sobě — je list rovně a celý na fotce?")

    warped = cv2.warpPerspective(bgr, H, (WARP_W, WARP_H), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    return creature_index, warped, n_markers


def flatten_lighting(warped, mask):
    """Divide out the illumination gradient, estimated from the bare paper around the drawing."""
    paper = cv2.dilate(mask, np.ones((41, 41), np.uint8))
    lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
    l = lab[:, :, 0].astype(np.float32)

    known = l.copy()
    known[paper > 0] = np.nan
    # coarse grid median of paper-only pixels, then smooth back up to full size
    gh, gw = 12, 16
    cell = np.full((gh, gw), np.nan, np.float32)
    for r in range(gh):
        for c in range(gw):
            block = known[r * l.shape[0] // gh:(r + 1) * l.shape[0] // gh,
                          c * l.shape[1] // gw:(c + 1) * l.shape[1] // gw]
            vals = block[~np.isnan(block)]
            if vals.size > 50:
                cell[r, c] = np.median(vals)
    if np.all(np.isnan(cell)):
        return warped
    med = np.nanmedian(cell)
    cell[np.isnan(cell)] = med
    field = cv2.resize(cell, (l.shape[1], l.shape[0]), interpolation=cv2.INTER_CUBIC)
    field = cv2.GaussianBlur(field, (0, 0), 40)

    gain = np.clip(245.0 / np.maximum(field, 1.0), 0.6, 2.2)
    out = warped.astype(np.float32) * gain[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def sheet_texture(warped, creature, trim_mm=0.0):
    """The drawing cut out along the silhouette, still in full sheet coordinates.

    Rig building indexes the sheet in absolute millimetres, so it needs this
    rather than the cropped version below.
    """
    mask = creature_mask(creature, ppm=WARP_PPM)
    if trim_mm:
        k = int(round(trim_mm * WARP_PPM)) * 2 + 1
        mask = cv2.erode(mask, np.ones((k, k), np.uint8))
    flat = flatten_lighting(warped, mask)
    return np.dstack([flat, cv2.GaussianBlur(mask, (0, 0), 0.8)])


def extract_texture(warped, creature, trim_mm=0.0):
    """Cut the drawing out and crop it to its bounding box. Returns (rgba, bbox_mm)."""
    mask = creature_mask(creature, ppm=WARP_PPM)
    if trim_mm:
        k = int(round(trim_mm * WARP_PPM)) * 2 + 1
        mask = cv2.erode(mask, np.ones((k, k), np.uint8))

    flat = flatten_lighting(warped, mask)
    x, y, w, h = cv2.boundingRect(mask)
    pad = int(round(2 * WARP_PPM))
    x, y = max(0, x - pad), max(0, y - pad)
    w, h = min(mask.shape[1] - x, w + 2 * pad), min(mask.shape[0] - y, h + 2 * pad)

    crop = flat[y:y + h, x:x + w]
    alpha = mask[y:y + h, x:x + w]
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)

    rgba = np.dstack([crop, alpha])
    bbox_mm = (x / WARP_PPM, y / WARP_PPM, w / WARP_PPM, h / WARP_PPM)
    return rgba, bbox_mm


def ink_coverage(rgba):
    """Fraction of the silhouette that actually got coloured in."""
    bgr, a = rgba[:, :, :3], rgba[:, :, 3]
    inside = a > 128
    if inside.sum() == 0:
        return 0.0
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 1]
    coloured = ((gray < 215) | (sat > 45)) & inside
    return float(coloured.sum()) / float(inside.sum())
