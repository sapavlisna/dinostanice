"""Výchozí zbarvení druhů z louky: nové vzory v paint.py a výšková mapa k nim.

Barevný list i výšková mapa se píšou do stejných souřadnic listu, takže bump
sedí na každé zvíře druhu — i na to, které vybarvilo dítě.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from dinostanice import modelsheet as ms
from dinostanice.creatures3d import BY_KEY
from dinostanice.paint import paint_body, paint_relief

ROOT = Path(__file__).resolve().parent.parent
PPM = 3.0
SIZE = (int(210 * PPM), int(297 * PPM))
LOUKA = [k for k, m in BY_KEY.items() if m.scene == "louka"]


@pytest.fixture(scope="module")
def shapes():
    return {k: ms.load(ROOT / f"data/shapes3d/{k}.json") for k in LOUKA}


@pytest.mark.parametrize("key", LOUKA)
def test_louka_species_paint_inside_the_outline_only(key, shapes):
    spec = BY_KEY[key]
    img = paint_body(shapes[key], spec.paint, PPM, SIZE, side_view=tuple(spec.axes) == (2, 1, 0), key=key)
    assert img.shape == (*SIZE, 3) and img.dtype == np.uint8
    body = np.zeros(SIZE, np.uint8)
    import cv2
    for poly in shapes[key].outline:
        cv2.fillPoly(body, [np.round(poly * PPM).astype(np.int32)], 1)
    assert (img[body == 0] == 255).all()
    assert img[body > 0].std() > 8      # ne jedna plocha barvy


@pytest.mark.parametrize("key", [k for k in LOUKA if BY_KEY[k].paint.get("relief")])
def test_relief_is_flat_outside_the_body_and_varies_inside(key, shapes):
    spec = BY_KEY[key]
    relief = paint_relief(shapes[key], spec.paint, PPM, SIZE, key)
    assert relief.shape == (*SIZE, 3) and relief.dtype == np.uint8
    assert (relief[..., 0] == relief[..., 1]).all()
    import cv2
    body = np.zeros(SIZE, np.uint8)
    for poly in shapes[key].outline:
        cv2.fillPoly(body, [np.round(poly * PPM).astype(np.int32)], 1)
    assert (relief[body == 0] == 128).all()
    assert relief[body > 0].std() > 3


def test_painting_is_deterministic(shapes):
    spec = BY_KEY["snail"]
    a = paint_body(shapes["snail"], spec.paint, PPM, SIZE, True, "snail")
    b = paint_body(shapes["snail"], spec.paint, PPM, SIZE, True, "snail")
    assert (a == b).all()


def test_catalogue_publishes_bump_and_material_for_painted_species():
    index = {e["key"]: e for e in json.loads((ROOT / "data/models3d/catalogue3d.json").read_text(encoding="utf-8"))}
    for key in LOUKA:
        spec = BY_KEY[key]
        if spec.paint.get("relief"):
            assert index[key]["bump"] == f"/models3d/{key}_bump.png"
            assert (ROOT / "data/models3d" / f"{key}_bump.png").exists()
        assert index[key].get("material", {}) == spec.material
