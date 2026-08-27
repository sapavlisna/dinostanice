"""dinostanice.quality.assess() must flag exactly the failure modes measured in test_robustness.py,
with Czech advice a child (or their parent) can act on.

This is the module the server leans on when a photo can't be processed: instead
of "nepovedlo se" the child gets told what to do differently, so the advice
being both correct and Czech is the point of these tests.
"""

import helpers as H
from dinostanice import quality, synth

KEY = "trex3d"
OUT_SIZE = (1200, 900)


def _good_photo(seed=0):
    return synth.photograph(H.sheet(KEY, seed=seed).img, seed=seed, out_size=OUT_SIZE)


def _index():
    return H.sheet(KEY).index


def test_good_photo_is_ok_and_reports_full_markers():
    report = quality.assess(_good_photo())
    assert report.ok, report.advice
    assert report.n_markers == 4
    assert report.issues == []
    assert report.ink_coverage is None or report.ink_coverage > 0.0


def test_blurry_photo_is_blocked_with_czech_advice():
    photo = H.blur_extra(_good_photo(), 8)
    report = quality.assess(photo)
    assert not report.ok
    assert "blurry" in report.issues or "no_markers" in report.issues or "capture_failed" in report.issues
    assert any("rozmaz" in a for a in report.advice)
    # advice must be in Czech, not e.g. a bare exception message
    assert all(a == a.strip() and len(a) > 5 for a in report.advice)


def test_missing_markers_reported_with_count():
    occluded = H.occlude_corners(H.sheet(KEY).img, ppm=6.0, corners=[0, 1, 2])
    photo = synth.photograph(occluded, seed=0, out_size=OUT_SIZE)
    report = quality.assess(photo)
    assert report.n_markers == 1
    assert not report.ok
    assert "few_markers" in report.issues
    assert any("1 ze 4" in a for a in report.advice)


def test_no_markers_at_all_reported():
    occluded = H.occlude_corners(H.sheet(KEY).img, ppm=6.0, corners=[0, 1, 2, 3])
    photo = synth.photograph(occluded, seed=0, out_size=OUT_SIZE)
    report = quality.assess(photo)
    assert report.n_markers == 0
    assert not report.ok
    assert "no_markers" in report.issues


def test_photographed_too_far_away_flagged():
    # small enough that markers are visibly tiny but still individually detectable
    # (much farther and raw ArUco detection stops finding anything at all -- see
    # test_photographed_way_too_far_finds_no_markers below).
    photo = H.zoom_out(_good_photo(), 0.22)
    report = quality.assess(photo)
    assert not report.ok
    assert "too_far" in report.issues or "far" in report.issues


def test_photographed_way_too_far_finds_no_markers():
    photo = H.zoom_out(_good_photo(), 0.1)
    report = quality.assess(photo)
    assert not report.ok
    assert "no_markers" in report.issues


def test_ink_coverage_reported_for_coloured_sheet():
    report = quality.assess(_good_photo(), creature_index=_index())
    assert report.ink_coverage is not None
    assert report.ink_coverage > quality.printed_coverage(KEY)
    assert "uncoloured" not in report.issues


def test_ink_coverage_flags_blank_template():
    blank = H.sheet(KEY, strokes=0).img
    photo = synth.photograph(blank, seed=0, out_size=OUT_SIZE)
    report = quality.assess(photo, creature_index=_index())
    assert report.ink_coverage is not None
    assert report.ink_coverage - quality.printed_coverage(KEY) < quality.UNCOLOURED_MIN_EXTRA
    assert "uncoloured" in report.issues


def test_report_serialises_to_dict():
    d = quality.assess(_good_photo()).as_dict()
    assert set(d) == {"ok", "sharpness", "n_markers", "contrast", "marker_size_ratio",
                       "skew", "ink_coverage", "issues", "advice"}
