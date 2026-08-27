"""Finding the coloured-in sheet in a phone photo and flattening it.

Which creature it is comes out of the corner markers, so one photo answers both
questions at once. Turning the flattened sheet into a texture is capture3d's job.
"""

from collections import Counter

import cv2
import numpy as np

from .shapes import SHEET_W_MM, SHEET_H_MM
from .markers import DICT, creature_index_of, marker_corner_points_mm
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

    Indexy 0-7 patrily prvni, zrusene vetvi projektu; zustavaji volne pro
    dalsi tvory, protoze listy 3D tvoru jsou vytistene s indexy 8 a vys a
    precislovani by je zneplatnilo.
    """
    return {m.marker_index for m in CATALOGUE3D}


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
