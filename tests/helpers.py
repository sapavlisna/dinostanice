"""Shared synthesis + measurement utilities for the capture pipeline test suite.

Builds on dinostanice.synth but exposes each degradation (tilt, illumination,
blur, JPEG quality, rotation, marker occlusion, hand shadow) as an independent,
composable knob so robustness boundaries can be swept one axis at a time --
synth.photograph() bundles several of these into one fixed recipe.
"""

import cv2
import numpy as np

from functools import lru_cache

from dinostanice import creatures as cr
from dinostanice.markers import DICT, CORNER_ORIGINS, MARKER_MM, marker_corner_points_mm
from dinostanice.capture import WARP_PPM
from dinostanice.synth import scribble

_detector = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())


@lru_cache(maxsize=None)
def _scribbled_sheet_cached(creature_index, seed, ppm, strokes):
    creature = cr.CATALOGUE[creature_index]
    return creature, scribble(creature, creature_index, ppm=ppm, seed=seed, strokes=strokes)


def scribbled_sheet(creature_index, seed=0, ppm=6.0, strokes=26):
    """A synthetic coloured-in sheet for one catalogue entry. scribble() is the slow step of the
    whole pipeline (per-stroke mask dilation), so results are memoised per (creature, seed, ppm,
    strokes) -- callers get a fresh copy each time so nothing can mutate the cached original.
    """
    creature, sheet = _scribbled_sheet_cached(creature_index, seed, ppm, strokes)
    return creature, sheet.copy()


def occlude_corners(sheet_bgr, ppm, corners, fill=(210, 190, 170)):
    """Paint a skin-toned rectangle over the marker at each corner index (0=TL,1=TR,2=BR,3=BL).

    Simulates a finger covering that corner while the photo is taken. Applied
    before photograph() so the perspective warp carries it along realistically.
    """
    out = sheet_bgr.copy()
    for c in corners:
        ox, oy = CORNER_ORIGINS[c]
        pad = 3.0  # mm border beyond the marker itself, like a fingertip's contact patch
        x0, y0 = int((ox - pad) * ppm), int((oy - pad) * ppm)
        x1, y1 = int((ox + MARKER_MM + pad) * ppm), int((oy + MARKER_MM + pad) * ppm)
        cv2.rectangle(out, (x0, y0), (x1, y1), fill, -1)
    return out


def shadow_corner(bgr, corner, strength, radius_frac=0.35):
    """Darken a soft radial patch near one image corner, like a hand's shadow falling across it."""
    h, w = bgr.shape[:2]
    cx = w * (0.0 if corner in (0, 3) else 1.0)
    cy = h * (0.0 if corner in (0, 1) else 1.0)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (radius_frac * np.hypot(w, h))
    gain = 1.0 - strength * np.clip(1.0 - r, 0.0, 1.0)
    out = bgr.astype(np.float32) * gain[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def uneven_light(bgr, strength, unevenness, seed=0):
    """Extra directional gradient plus dark blobs, for sweeping illumination quality independently of synth.photograph's own fixed vignette."""
    rng = np.random.default_rng(seed + 4242)
    h, w = bgr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    angle = rng.uniform(0, 2 * np.pi)
    grad = (xx * np.cos(angle) + yy * np.sin(angle)) / np.hypot(w, h)
    field = 1.0 + strength * grad
    if unevenness > 0:
        for _ in range(3):
            bx, by = rng.uniform(0, w), rng.uniform(0, h)
            br = rng.uniform(0.15, 0.4) * np.hypot(w, h)
            blob = np.exp(-((xx - bx) ** 2 + (yy - by) ** 2) / (2 * br ** 2))
            field = field - unevenness * strength * blob
    field = np.clip(field, 0.12, 2.5)
    out = bgr.astype(np.float32) * field[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def recompress(bgr, quality):
    """Re-encode as JPEG at a given quality, simulating a more aggressively compressed upload."""
    ok, enc = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    assert ok
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def blur_extra(bgr, sigma):
    """Additional Gaussian blur on top of whatever synth.photograph already applied, simulating camera shake / bad focus."""
    if sigma <= 0:
        return bgr
    return cv2.GaussianBlur(bgr, (0, 0), sigma)


def rotate_sheet(sheet_bgr, k):
    """Rotate the coloured sheet by k*90 degrees before photographing -- the paper placed sideways or upside down."""
    if k % 4 == 0:
        return sheet_bgr
    op = {1: cv2.ROTATE_90_CLOCKWISE, 2: cv2.ROTATE_180, 3: cv2.ROTATE_90_COUNTERCLOCKWISE}[k % 4]
    return cv2.rotate(sheet_bgr, op)


def registration_error_mm(warped_bgr, creature_index):
    """Mean corner error (mm) of markers re-detected in an already-warped image vs. their known
    canonical sheet positions. A ground-truth, units-of-millimetres measurement of how precisely
    detect_sheet's homography aligned the paper -- independent of anything internal to capture.py.
    Returns None if no markers belonging to this creature were found in the warped result.
    """
    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(gray)
    if ids is None:
        return None
    expected = marker_corner_points_mm(creature_index)
    errs = []
    for quad, mid in zip(corners, ids.flatten().tolist()):
        if mid in expected:
            got_mm = quad.reshape(4, 2) / WARP_PPM
            errs.extend(np.linalg.norm(got_mm - expected[mid], axis=1).tolist())
    return float(np.mean(errs)) if errs else None


def zoom_out(bgr, frac, bg=190):
    """Shrink the photographed frame to `frac` of its size and pad back out to the original
    canvas -- simulates holding the phone farther from the sheet than synth.photograph's fixed framing.
    """
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, (max(1, int(w * frac)), max(1, int(h * frac))), interpolation=cv2.INTER_AREA)
    canvas = np.full_like(bgr, bg)
    sh, sw = small.shape[:2]
    y0, x0 = (h - sh) // 2, (w - sw) // 2
    canvas[y0:y0 + sh, x0:x0 + sw] = small
    return canvas


def full_sheet_rgba(rgba_crop, bbox_mm, ppm=WARP_PPM):
    """Place a cropped RGBA texture back at its bbox on a blank full-sheet canvas.

    build_rig indexes pixels by sheet millimetres, so it needs the whole sheet;
    this mirrors server.py's own sheet_rgba() without importing server.py (which
    pulls in FastAPI/uvicorn/qrcode, none of which the test suite should need).
    """
    from dinostanice.shapes import SHEET_W_MM, SHEET_H_MM
    full = np.zeros((int(round(SHEET_H_MM * ppm)), int(round(SHEET_W_MM * ppm)), 4), np.uint8)
    x, y = int(round(bbox_mm[0] * ppm)), int(round(bbox_mm[1] * ppm))
    h, w = rgba_crop.shape[:2]
    full[y:y + h, x:x + w] = rgba_crop
    return full


def raw_marker_count(bgr):
    """How many ArUco markers are detectable in a photo at all, with no attempt to match them to a creature."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, ids, _ = _detector.detectMarkers(gray)
    return 0 if ids is None else len(ids)
