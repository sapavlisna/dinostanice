"""rasterise -> scribble -> photograph -> detect_sheet must recover the right creature for every catalogue entry."""

import pytest

import helpers as H
from dinostanice.creatures3d import BY_MARKER


@pytest.mark.parametrize("key", H.ALL_KEYS)
def test_identity_recovered(captured, key):
    sheet, photo, idx, warped, n = captured(key)
    got = BY_MARKER[idx].key if idx in BY_MARKER else f"neznámý index {idx}"
    assert idx == sheet.index, (
        f"expected {key!r} (index {sheet.index}), got {got}")
    assert n == 4, f"expected all 4 markers on an undistorted synthetic photo, saw {n}"
