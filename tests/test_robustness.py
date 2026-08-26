"""Where does detect_sheet actually break?

Each axis below is swept independently (tests/helpers.py provides the knobs
that dinostanice.synth.photograph() doesn't expose on its own) against two
representative creatures -- trex (thin organic limbs) and ship (large rigid
outline) -- at a reduced 1200x900 working resolution to keep the whole suite
fast; the identity/registration tests already cover full resolution and all
six creatures. Boundary values here were located by manual sweeps (see
out/_explore_bounds*.py and out/robustness_report.md) and are asserted with a
safety margin on both sides so the tests aren't flaky right at the edge.
"""

import itertools

import numpy as np
import pytest

import helpers as H
from dinostanice import capture, synth

OUT_SIZE = (1200, 900)
CREATURES = [1, 4]  # trex, ship
RELIABLE_ERROR_MM = 1.5  # ceiling for registration error whenever >=3 markers were used (see test_registration.py)


def _sheet(ci, seed=0):
    return H.scribbled_sheet(ci, seed=seed)


def _try(photo, ci):
    try:
        idx, warped, n = capture.detect_sheet(photo)
        return idx == ci, n, warped
    except capture.CaptureError:
        return False, 0, None


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("tilt", [0.5, 1.5, 3.0], ids=["tilt_mild", "tilt_moderate", "tilt_strong"])
def test_tilt_within_bounds_succeeds(creature_index, tilt):
    creature, sheet = _sheet(creature_index)
    photo = synth.photograph(sheet, seed=0, tilt=tilt, out_size=OUT_SIZE)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"tilt={tilt} should still register for {creature.key}"
    if n >= 3:
        err = H.registration_error_mm(warped, creature_index)
        assert err is not None and err < RELIABLE_ERROR_MM


@pytest.mark.parametrize("creature_index", CREATURES)
def test_tilt_extreme_can_fail(creature_index):
    """Boundary: random corner jitter this strong pushes a marker out of frame (measured ~tilt>=4.5)."""
    creature, sheet = _sheet(creature_index)
    photo = synth.photograph(sheet, seed=0, tilt=6.0, out_size=OUT_SIZE)
    ok, n, warped = _try(photo, creature_index)
    assert not ok, f"tilt=6.0 was expected to break detection for {creature.key} (got n={n})"


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("sigma", [1, 2, 3], ids=["blur_mild", "blur_moderate", "blur_heavy"])
def test_blur_within_bounds_succeeds(creature_index, sigma):
    creature, sheet = _sheet(creature_index)
    photo = H.blur_extra(synth.photograph(sheet, seed=0, blur=0.0, out_size=OUT_SIZE), sigma)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"extra blur sigma={sigma} should still register for {creature.key}"


@pytest.mark.parametrize("creature_index", CREATURES)
def test_blur_extreme_fails(creature_index):
    """Boundary: extra Gaussian blur sigma>=~5-6px at this resolution reliably breaks ArUco detection."""
    creature, sheet = _sheet(creature_index)
    photo = H.blur_extra(synth.photograph(sheet, seed=0, blur=0.0, out_size=OUT_SIZE), 8)
    ok, n, warped = _try(photo, creature_index)
    assert not ok, f"heavy blur was expected to break detection for {creature.key} (got n={n})"


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("quality", [40, 15, 5], ids=["jpeg_medium", "jpeg_low", "jpeg_very_low"])
def test_jpeg_compression_is_not_the_weak_link(creature_index, quality):
    """Even heavy re-compression barely moves registration error -- ArUco copes fine with block artefacts here."""
    creature, sheet = _sheet(creature_index)
    photo = H.recompress(synth.photograph(sheet, seed=0, out_size=OUT_SIZE), quality)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"jpeg quality={quality} should still register for {creature.key}"
    if n >= 3:
        err = H.registration_error_mm(warped, creature_index)
        assert err is not None and err < RELIABLE_ERROR_MM


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("strength", [0.5, 0.9, 1.05], ids=["light_mild", "light_strong", "light_extreme"])
def test_uneven_light_gradient_tolerated(creature_index, strength):
    """cv2's ArUco thresholding is locally adaptive, so a slow global gradient -- even a strong one -- doesn't defeat it."""
    creature, sheet = _sheet(creature_index)
    photo = H.uneven_light(synth.photograph(sheet, seed=0, out_size=OUT_SIZE), strength, 0.0, seed=0)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"illumination gradient strength={strength} should still register for {creature.key}"


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("unevenness", [0.6, 1.5, 2.0], ids=["uneven_mild", "uneven_strong", "uneven_extreme"])
def test_patchy_light_tolerated(creature_index, unevenness):
    creature, sheet = _sheet(creature_index)
    photo = H.uneven_light(synth.photograph(sheet, seed=0, out_size=OUT_SIZE), 0.8, unevenness, seed=0)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"patchy light unevenness={unevenness} should still register for {creature.key}"


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("k", [0, 1, 2, 3], ids=["rot_0", "rot_90", "rot_180", "rot_270"])
def test_rotation_invariant(creature_index, k):
    """Marker IDs (and hence which corner is which) are read from the bit pattern, not image orientation."""
    creature, sheet = _sheet(creature_index)
    photo = synth.photograph(H.rotate_sheet(sheet, k), seed=0, out_size=OUT_SIZE)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"rotation k={k} should not affect identification for {creature.key}"
    assert n == 4
    err = H.registration_error_mm(warped, creature_index)
    assert err is not None and err < RELIABLE_ERROR_MM


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("n_hidden", [1, 2], ids=["hide_1", "hide_2"])
def test_partial_marker_occlusion_still_detects(creature_index, n_hidden):
    """Two matched markers (8 correspondences) are enough to register the sheet."""
    creature, sheet = _sheet(creature_index)
    corners = list(range(n_hidden))  # which corners are covered doesn't matter, only how many
    occluded = H.occlude_corners(sheet, ppm=6.0, corners=corners)
    photo = synth.photograph(occluded, seed=0, out_size=OUT_SIZE)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"hiding {n_hidden} marker(s) should still allow detection for {creature.key}"
    assert n >= capture.MIN_MARKERS


@pytest.mark.parametrize("creature_index", CREATURES)
def test_single_marker_is_refused(creature_index):
    """A lone marker pins a homography exactly, so nothing looks wrong -- but
    extrapolating it across the whole sheet was measured tens of millimetres off.
    The pipeline must ask for a better photo rather than cut the drawing wrong.
    """
    creature, sheet = _sheet(creature_index)
    occluded = H.occlude_corners(sheet, ppm=6.0, corners=[0, 1, 2])
    photo = synth.photograph(occluded, seed=0, out_size=OUT_SIZE)
    try:
        _, _, n = capture.detect_sheet(photo)
    except capture.CaptureError:
        return
    assert n >= capture.MIN_MARKERS, "a single marker must never register a sheet"


def test_min_markers_threshold_is_enforced():
    """The guard itself, independent of how well occlusion happens to hide things."""
    creature, sheet = _sheet(CREATURES[0])
    photo = synth.photograph(sheet, seed=0, out_size=OUT_SIZE)
    capture.detect_sheet(photo, min_markers=4)  # all four are visible here
    with pytest.raises(capture.CaptureError):
        capture.detect_sheet(photo, min_markers=5)


@pytest.mark.parametrize("creature_index", CREATURES)
def test_all_markers_hidden_fails_cleanly(creature_index):
    creature, sheet = _sheet(creature_index)
    occluded = H.occlude_corners(sheet, ppm=6.0, corners=[0, 1, 2, 3])
    photo = synth.photograph(occluded, seed=0, out_size=OUT_SIZE)
    ok, n, warped = _try(photo, creature_index)
    assert not ok
    assert n == 0


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("strength", [0.5, 0.8, 1.0], ids=["shadow_mild", "shadow_strong", "shadow_max"])
def test_hand_shadow_over_corner_tolerated(creature_index, strength):
    """A soft radial darkening over one corner (like a hand's shadow, not an actual finger on the marker)
    doesn't defeat detection either, for the same local-adaptive-threshold reason as uneven light.
    """
    creature, sheet = _sheet(creature_index)
    photo = synth.photograph(sheet, seed=0, out_size=OUT_SIZE)
    shadowed = H.shadow_corner(photo, 0, strength)
    ok, n, warped = _try(shadowed, creature_index)
    assert ok, f"corner shadow strength={strength} should still register for {creature.key}"


@pytest.mark.parametrize("creature_index", CREATURES)
@pytest.mark.parametrize("frac", [0.5, 0.3], ids=["distance_ok", "distance_far"])
def test_holding_phone_farther_away_still_works(creature_index, frac):
    creature, sheet = _sheet(creature_index)
    photo0 = synth.photograph(sheet, seed=0, out_size=OUT_SIZE)
    photo = H.zoom_out(photo0, frac)
    ok, n, warped = _try(photo, creature_index)
    assert ok, f"sheet filling {frac:.0%} of the frame should still register for {creature.key}"


@pytest.mark.parametrize("creature_index", CREATURES)
def test_holding_phone_too_far_away_fails(creature_index):
    """Boundary: below roughly a fifth of the frame's linear size, markers become too small to read (measured)."""
    creature, sheet = _sheet(creature_index)
    photo0 = synth.photograph(sheet, seed=0, out_size=OUT_SIZE)
    photo = H.zoom_out(photo0, 0.12)
    ok, n, warped = _try(photo, creature_index)
    assert not ok, f"sheet filling only 12% of the frame was expected to fail for {creature.key}"
