"""Shared synthesis + measurement utilities for the capture pipeline test suite.

Builds on dinostanice.synth but exposes each degradation (tilt, illumination,
blur, JPEG quality, rotation, marker occlusion, hand shadow) as an independent,
composable knob so robustness boundaries can be swept one axis at a time --
synth.photograph() bundles several of these into one fixed recipe.

The sheet under test is a real catalogue template: modelsheet.rasterise() draws
exactly what gets printed (outline, internal lines, eye, corner markers) from
data/shapes3d, and synth.scribble() colours it in. So the whole chain
"paper -> photo -> creature" is exercised without a printer.
"""

from functools import lru_cache
from typing import NamedTuple

import cv2
import numpy as np

from dinostanice import capture3d, modelsheet
from dinostanice.capture import WARP_PPM
from dinostanice.creatures3d import BY_KEY, CATALOGUE
from dinostanice.markers import DICT, CORNER_ORIGINS, MARKER_MM, marker_corner_points_mm
from dinostanice.synth import scribble

_detector = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())

# Dva zástupci pro sweepy: T-Rex (kompaktní tvor s tenkými končetinami) a
# apatosaurus (protáhlý, kresba jde skoro přes celý list). Detekce visí na
# rohových značkách, které jsou u obou stejné, takže sweepy nemusí projet
# celý katalog — identitu a registraci hlídají testy nad všemi tvory.
SWEEP_KEYS = ["trex3d", "apatosaurus3d"]

ALL_KEYS = [m.key for m in CATALOGUE]


class Sheet(NamedTuple):
    """Vybarvený (nebo nedotčený) list jednoho tvora z katalogu."""

    spec: object          # creatures3d.Model3D
    shape: object         # modelsheet.SheetShape
    img: np.ndarray       # BGR list v `ppm` px/mm

    @property
    def key(self):
        return self.spec.key

    @property
    def index(self):
        return self.spec.marker_index


@lru_cache(maxsize=None)
def _sheet_cached(key, seed, ppm, strokes):
    spec = BY_KEY[key]
    shape = capture3d.load_shape(key)
    img = modelsheet.rasterise(shape, spec.marker_index, ppm=ppm)
    if strokes:
        img = scribble(img, capture3d.sheet_mask(shape, ppm), ppm=ppm, seed=seed,
                       strokes=strokes)
    return Sheet(spec, shape, img)


def sheet(key, seed=0, ppm=6.0, strokes=26):
    """Synthetic sheet for one catalogue entry; strokes=0 leaves it untouched.

    scribble() is the slow step of the whole pipeline (per-stroke mask
    dilation), so results are memoised per (creature, seed, ppm, strokes) --
    callers get a fresh copy of the image so nothing can mutate the cached one.
    """
    s = _sheet_cached(key, seed, ppm, strokes)
    return s._replace(img=s.img.copy())


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
