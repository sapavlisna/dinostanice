"""Runtime photo-quality assessment.

Runs when the capture pipeline rejects a photo (server.process), so the
uploader can tell a child what to fix and let them retake the shot rather
than just failing. Works even on a photo where the sheet can't be located at
all -- everything except ink_coverage only needs raw ArUco detection.

Thresholds are not guessed: they come from sweeping dinostanice.capture.detect_sheet
against synthetic photos in tests/test_robustness.py (raw numbers and the full
sweep are in out/robustness_report.md). In short: extra Gaussian blur past
sigma ~= 6-7 (on a 2016x1512 photo; the effect is checked against a
resolution-normalised sharpness score here so it carries over to other
resolutions) reliably breaks marker detection, and holding the phone far
enough away that the sheet occupies less than roughly a fifth of the frame's
diagonal does too. Contrast and viewing-angle thresholds are conservative
heuristics -- the synthetic sweeps did not find failures driven by those alone
(cv2's ArUco thresholding turned out to be very tolerant of uneven light and
shadows), so they only ever produce a soft warning, never a hard block.
"""

import cv2
import numpy as np

from .capture import (MIN_MARKERS, CaptureError, detect_sheet, extract_texture,
                      ink_coverage as _ink_coverage)
from .markers import DICT

_detector = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())

NORM_LONG_SIDE = 1600     # sharpness is computed after resizing to this, so the threshold is resolution-independent
SHARP_FAIL = 1.5          # at/below this, detection reliably fails (measured: sigma>=7 extra blur -> norm_lap_var<=0.6)
SHARP_WARN = 15.0         # below this, still usually works but is well below a normal in-focus shot (baseline ~50-80)

MARKERS_MIN_OK = MIN_MARKERS  # capture.detect_sheet's own gate -- fewer than this is rejected downstream regardless

TOO_FAR_FAIL = 0.008      # avg marker side / image diagonal; measured failure at a sheet filling <~20% of the frame
TOO_FAR_WARN = 0.015      # comfortable margin above that

CONTRAST_WARN = 15.0      # heuristic: no synthetic failure was ever driven by contrast/lighting alone

SKEW_WARN = 0.35          # heuristic viewing-angle proxy from raw marker quads (diagonal-length asymmetry)

# mirrors server.py's own TRIM_MM: extract_texture()'s crop hugs the printed
# outline itself, and that dark line reads as "ink" (measured ~0.04-0.06
# coverage on an untouched template); eroding the mask past it before
# measuring is what lets an actually-blank sheet read near zero (~0.005).
INK_TRIM_MM = 0.6
UNCOLOURED_MAX_COVERAGE = 0.03

BLOCKING = frozenset(["blurry", "no_markers", "few_markers", "too_far", "capture_failed"])

ADVICE = {
    "blurry": "fotka je rozmazaná, zkus ji vyfotit znovu bez pohybu a se zaostřením na list",
    "soft": "fotka je trochu rozmazaná, přidrž telefon pevněji",
    "no_markers": "na fotce nejsou vidět žádné rohové značky, vyfoť celý list shora",
    "few_markers": "vidím jen {n} ze 4 rohových značek, vyfoť celý list tak, aby byly vidět všechny rohy",
    "too_far": "list je na fotce moc malý, přibliž telefon blíž k listu",
    "far": "zkus přiblížit telefon trochu víc k listu",
    "low_contrast": "fotka má málo kontrastu, foť ve víc osvětleném prostoru",
    "angled": "foť víc kolmo shora, ne moc ze strany",
    "uncoloured": "šablona vypadá nevybarvená, vybarvi ji pastelkami a vyfoť znovu",
    "capture_failed": "list se nepodařilo najít a srovnat, zkus ho vyfotit celý, rovně a zblízka",
}


class QualityReport:
    """Structured result of assess(); .ok tells the caller whether to proceed."""

    def __init__(self, ok, sharpness, n_markers, contrast, marker_size_ratio, skew, ink_cov, issues):
        self.ok = ok
        self.sharpness = sharpness
        self.n_markers = n_markers
        self.contrast = contrast
        self.marker_size_ratio = marker_size_ratio
        self.skew = skew
        self.ink_coverage = ink_cov
        self.issues = issues
        self.advice = [ADVICE[i].format(n=n_markers) for i in issues]

    def as_dict(self):
        return {
            "ok": self.ok, "sharpness": self.sharpness, "n_markers": self.n_markers,
            "contrast": self.contrast, "marker_size_ratio": self.marker_size_ratio,
            "skew": self.skew, "ink_coverage": self.ink_coverage,
            "issues": self.issues, "advice": self.advice,
        }


def _normalised_sharpness(bgr):
    h, w = bgr.shape[:2]
    scale = NORM_LONG_SIDE / max(h, w)
    if scale < 1.0:
        bgr = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _contrast(bgr):
    return float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).std())


def _raw_markers(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(gray)
    return [] if ids is None else list(zip(ids.flatten().tolist(), corners))


def _marker_size_ratio(bgr, markers):
    """Average marker side length as a fraction of the image diagonal -- a resolution-independent stand-in for "how close is the phone"."""
    if not markers:
        return 0.0
    diag = float(np.hypot(*bgr.shape[:2]))
    sides = []
    for _, quad in markers:
        pts = quad.reshape(4, 2)
        sides.extend(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1).tolist())
    return float(np.mean(sides)) / diag


def _skew_estimate(markers):
    """Mean relative difference between a marker quad's two diagonals -- 0 for a fronto-parallel square, grows with viewing angle."""
    if not markers:
        return None
    skews = []
    for _, quad in markers:
        pts = quad.reshape(4, 2)
        d1 = np.linalg.norm(pts[0] - pts[2])
        d2 = np.linalg.norm(pts[1] - pts[3])
        if max(d1, d2) > 1e-6:
            skews.append(abs(d1 - d2) / max(d1, d2))
    return float(np.mean(skews)) if skews else None


def assess(bgr, creature_index=None):
    """Evaluate one uploaded photo. Never raises -- always returns a QualityReport."""
    sharpness = _normalised_sharpness(bgr)
    contrast = _contrast(bgr)
    markers = _raw_markers(bgr)
    n_markers = len(markers)
    size_ratio = _marker_size_ratio(bgr, markers)
    skew = _skew_estimate(markers)

    issues = []
    if sharpness < SHARP_FAIL:
        issues.append("blurry")
    elif sharpness < SHARP_WARN:
        issues.append("soft")

    if n_markers == 0:
        issues.append("no_markers")
    elif n_markers < MARKERS_MIN_OK:
        issues.append("few_markers")

    if n_markers > 0 and size_ratio < TOO_FAR_FAIL:
        issues.append("too_far")
    elif n_markers > 0 and size_ratio < TOO_FAR_WARN:
        issues.append("far")

    if contrast < CONTRAST_WARN:
        issues.append("low_contrast")

    if skew is not None and skew > SKEW_WARN:
        issues.append("angled")

    coverage = None
    if "no_markers" not in issues:
        try:
            idx, warped, _n = detect_sheet(bgr)
            from .creatures import CATALOGUE
            if 0 <= idx < len(CATALOGUE) and (creature_index is None or idx == creature_index):
                rgba, _bbox = extract_texture(warped, CATALOGUE[idx], trim_mm=INK_TRIM_MM)
                coverage = _ink_coverage(rgba)
                if coverage < UNCOLOURED_MAX_COVERAGE:
                    issues.append("uncoloured")
        except CaptureError:
            issues.append("capture_failed")

    ok = not (BLOCKING & set(issues))
    return QualityReport(ok, sharpness, n_markers, contrast, size_ratio, skew, coverage, issues)
