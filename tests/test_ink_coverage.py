"""ink_coverage must tell an untouched printed template apart from a coloured-in one."""

import pytest

import helpers as H
from dinostanice import creatures as cr
from dinostanice.capture import WARP_PPM, extract_texture, ink_coverage
from dinostanice.template import rasterise


# extract_texture()'s untrimmed crop hugs the printed outline itself, and that
# dark line reads as "ink" too (measured ~0.04-0.06 on an untouched template) --
# trim_mm pulls the cut in past it, same as server.py's own TRIM_MM does.
TRIM_MM = 0.6


@pytest.mark.parametrize("creature_index", [0, 1, 4], ids=["sauropod", "trex", "ship"])
def test_uncoloured_template_has_near_zero_coverage(creature_index):
    creature = cr.CATALOGUE[creature_index]
    blank = rasterise(creature, creature_index, ppm=WARP_PPM, with_markers=False, with_label=False)
    rgba, _bbox = extract_texture(blank, creature, trim_mm=TRIM_MM)
    coverage = ink_coverage(rgba)
    assert coverage < 0.02, f"blank template should read as ~uncoloured, got {coverage:.3f}"


@pytest.mark.parametrize("creature_index", [0, 1, 4], ids=["sauropod", "trex", "ship"])
def test_scribbled_template_has_substantial_coverage(creature_index):
    creature, sheet = H.scribbled_sheet(creature_index, seed=1, ppm=WARP_PPM, strokes=26)
    rgba, _bbox = extract_texture(sheet, creature, trim_mm=TRIM_MM)
    coverage = ink_coverage(rgba)
    assert coverage > 0.05, f"a scribbled-over sheet should read as clearly coloured, got {coverage:.3f}"


def test_coverage_increases_with_more_strokes():
    creature_index = 1
    _, light = H.scribbled_sheet(creature_index, seed=2, ppm=WARP_PPM, strokes=6)
    _, heavy = H.scribbled_sheet(creature_index, seed=2, ppm=WARP_PPM, strokes=40)
    creature = cr.CATALOGUE[creature_index]
    cov_light = ink_coverage(extract_texture(light, creature, trim_mm=TRIM_MM)[0])
    cov_heavy = ink_coverage(extract_texture(heavy, creature, trim_mm=TRIM_MM)[0])
    assert cov_heavy > cov_light
