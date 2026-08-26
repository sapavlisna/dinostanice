"""Session-scoped fixtures shared across the capture pipeline test suite.

scribble() (mask dilation per stroke) and photograph() (perspective warp on a
2016x1512 canvas) are the expensive steps; caching them per (creature, seed)
keeps the whole suite comfortably under the ~90s budget even though several
test modules independently need "creature N's default synthetic photo".
"""

import pytest

import helpers as H
from dinostanice import capture
from dinostanice.synth import photograph


@pytest.fixture(scope="session")
def captured():
    """capture.detect_sheet() applied to each creature's default synthetic photo, cached by index."""
    cache = {}

    def get(creature_index, seed=0):
        key = (creature_index, seed)
        if key not in cache:
            creature, sheet = H.scribbled_sheet(creature_index, seed=seed)
            photo = photograph(sheet, seed=seed)
            idx, warped, n = capture.detect_sheet(photo)
            cache[key] = (creature, photo, idx, warped, n)
        return cache[key]

    return get
