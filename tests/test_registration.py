"""How precisely does detect_sheet's homography line the paper up with its canonical frame?

Measured directly and honestly: markers are re-detected in the already-warped
output and compared, in millimetres, to their known canonical sheet positions
(dinostanice.markers.marker_corner_points_mm) -- ground truth, independent of
anything internal to capture.py.
"""

import pytest

import helpers as H
from dinostanice import creatures as cr

# capture.WARP_PPM is 5.0 px/mm, so one warped pixel is 0.2mm; sub-pixel corner
# localisation noise alone should keep this well under half a millimetre on a
# clean synthetic photo with no lens distortion (see out/robustness_report.md
# for how this grows once markers are occluded or the shot is degraded).
# The synthetic model has no lens distortion or paper curl, so this bound is a
# best case, not a guarantee for real phone photos.
MAX_BASELINE_ERROR_MM = 0.75


@pytest.mark.parametrize("creature_index", range(len(cr.CATALOGUE)), ids=[c.key for c in cr.CATALOGUE])
def test_registration_error_on_clean_photo(captured, creature_index):
    creature, photo, idx, warped, n = captured(creature_index)
    assert idx == creature_index
    err = H.registration_error_mm(warped, creature_index)
    assert err is not None
    assert err < MAX_BASELINE_ERROR_MM, f"registration off by {err:.3f}mm for {creature.key}"
