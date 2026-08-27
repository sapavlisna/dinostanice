"""capture3d.ink_coverage must tell an untouched printed template apart from a coloured-in one.

Coverage is measured inside the whole drawing area, printed lines included, so
the number never starts at zero -- how much of the drawing the outline, the
internal lines and the eye take up is a property of each template. The question
"did the child colour anything in" is therefore asked against that template's
own printed baseline (quality.printed_coverage), and this module pins down both
halves: that the baseline really is where a blank sheet lands, and that colouring
moves the number well above it.
"""

import pytest

import helpers as H
from dinostanice import capture, capture3d, quality, synth

OUT_SIZE = (1200, 900)
PPM = 6.0


def _coverage(sheet):
    """Coverage as the live pipeline sees it: photographed, then flattened."""
    photo = synth.photograph(sheet.img, seed=1, out_size=OUT_SIZE)
    idx, warped, n = capture.detect_sheet(photo)
    assert idx == sheet.index
    return capture3d.ink_coverage(warped, sheet.shape)


@pytest.mark.parametrize("key", H.SWEEP_KEYS + ["triceratops3d"])
def test_uncoloured_template_reads_as_its_printed_baseline(key):
    """A blank sheet lands at (just under) the printed baseline -- never above it.

    Photographing softens the printed lines, so the photo reads a touch lower
    than the rasterised template; that is why the "is it coloured" test has a
    margin instead of comparing for equality.
    """
    sheet = H.sheet(key, strokes=0, ppm=PPM)
    base = quality.printed_coverage(key)
    cov = _coverage(sheet)
    assert 0.02 < base < 0.15, f"printed baseline for {key} out of expected range: {base:.4f}"
    assert cov - base < quality.UNCOLOURED_MIN_EXTRA, (
        f"blank {key} should read as ~uncoloured, got {cov:.4f} vs baseline {base:.4f}")


@pytest.mark.parametrize("key", H.SWEEP_KEYS + ["triceratops3d"])
def test_scribbled_template_reads_as_clearly_coloured(key):
    # 40 tahu = list, ktery dite skutecne vybarvovalo. Mereno +0.08 az +0.13
    # nad baseline podle tvora (nejmene ma triceratops, ktery ma z katalogu
    # nejmensi kresbu, takze na nej padne nejmene tahu).
    sheet = H.sheet(key, seed=1, ppm=PPM, strokes=40)
    extra = _coverage(sheet) - quality.printed_coverage(key)
    assert extra > quality.UNCOLOURED_MIN_EXTRA * 2, (
        f"a scribbled-over {key} sheet should read as clearly coloured, got +{extra:.4f}")


def test_coverage_increases_with_more_strokes():
    key = "trex3d"
    light = _coverage(H.sheet(key, seed=2, ppm=PPM, strokes=6))
    heavy = _coverage(H.sheet(key, seed=2, ppm=PPM, strokes=40))
    assert heavy > light


def test_fully_filled_sheet_reads_as_almost_all_ink():
    """Upper end of the scale: a sheet coloured edge to edge must not saturate
    somewhere in the middle, otherwise the whole measure would be useless for
    telling "barely touched" from "properly coloured"."""
    sheet = H.sheet("trex3d", strokes=0, ppm=PPM)
    mask = capture3d.sheet_mask(sheet.shape, PPM)
    sheet.img[mask > 0] = (70, 170, 90)
    assert _coverage(sheet) > 0.95
