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
    """capture.detect_sheet() applied to each creature's default synthetic photo, cached by key."""
    cache = {}

    def get(key, seed=0):
        ck = (key, seed)
        if ck not in cache:
            sheet = H.sheet(key, seed=seed)
            photo = photograph(sheet.img, seed=seed)
            idx, warped, n = capture.detect_sheet(photo)
            cache[ck] = (sheet, photo, idx, warped, n)
        return cache[ck]

    return get
