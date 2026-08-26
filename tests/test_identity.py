"""scribble -> photograph -> detect_sheet must recover the right creature for every catalogue entry."""

import pytest

from dinostanice import creatures as cr


@pytest.mark.parametrize("creature_index", range(len(cr.CATALOGUE)), ids=[c.key for c in cr.CATALOGUE])
def test_identity_recovered(captured, creature_index):
    creature, photo, idx, warped, n = captured(creature_index)
    assert idx == creature_index, (
        f"expected {cr.CATALOGUE[creature_index].key!r} (index {creature_index}), "
        f"got index {idx} ({cr.CATALOGUE[idx].key if idx < len(cr.CATALOGUE) else '??'})"
    )
    assert n == 4, f"expected all 4 markers on an undistorted synthetic photo, saw {n}"
