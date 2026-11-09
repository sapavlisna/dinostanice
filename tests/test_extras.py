"""Doplňky (ptáček, motýlek): okénka v rohu listu každého zvířete scény.

Dětem nemá list propadnout na doplňky: okénko leží v rohu, vedle zvířete, a uloží se,
jen když je vybarvené. Tady se hlídá, že okénka jsou na všech listech, nikde se
nedotýkají zvířete, značek ani sebe, a že cesta „vybarvené okénko na fotce -> ulovek"
funguje a nevybarvené okénko nic neuloží.
"""

import cv2
import numpy as np
import pytest

import helpers as H
from dinostanice import capture, capture3d, modelsheet, synth
from dinostanice.creatures3d import CATALOGUE, BY_KEY
from dinostanice.markers import CORNER_ORIGINS, MARKER_MM
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

EXTRAS = [m for m in CATALOGUE if m.extra]
HOSTS = [m for m in CATALOGUE if not m.extra and any(e.scene == m.scene for e in EXTRAS)]


def _mini_mask(shape, slot, ppm):
    ex = capture3d.load_shape(slot["key"])
    outline, _ = modelsheet.extra_polys(ex, slot)
    h, w = int(round(SHEET_H_MM * ppm)), int(round(SHEET_W_MM * ppm))
    mask = np.zeros((h, w), np.uint8)
    for poly in outline:
        cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
    return mask


def test_extras_exist_and_are_not_offered_as_templates():
    assert {m.key for m in EXTRAS} >= {"bird", "butterfly"}
    assert HOSTS, "žádné zvíře, které by doplňky nést mělo"


@pytest.mark.parametrize("key", [m.key for m in HOSTS])
def test_every_host_sheet_has_a_free_window_for_each_extra(key):
    spec = BY_KEY[key]
    shape = capture3d.load_shape(key)
    wanted = {e.key for e in EXTRAS if e.scene == spec.scene}
    assert {s["key"] for s in shape.extras} == wanted, (
        f"{key}: okénko chybí ({sorted(wanted - {s['key'] for s in shape.extras})})")

    res = 2.0
    body = np.zeros((int(SHEET_H_MM * res), int(SHEET_W_MM * res)), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * res).astype(np.int32)], 1)
    rects = []
    for slot in shape.extras:
        x, y, w, h = slot["rect"]
        assert 0 <= x and x + w <= SHEET_W_MM and 0 <= y and y + h <= SHEET_H_MM - 10
        # zvíře se okénka nedotýká
        sub = body[int(y * res):int((y + h) * res) + 1, int(x * res):int((x + w) * res) + 1]
        assert not sub.any(), f"{key}: okénko {slot['key']} zasahuje do obrysu"
        # rohové značky taky ne
        for ox, oy in CORNER_ORIGINS:
            assert (x + w < ox or x > ox + MARKER_MM or y + h < oy or y > oy + MARKER_MM), \
                f"{key}: okénko {slot['key']} zasahuje do značky"
        # a miniatura je dost velká na vybarvení
        assert max(w, h) >= 30
        rects.append((x, y, w, h))
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                    or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]), f"{key}: okénka se překrývají"


def _photo_with_bird_coloured(key):
    spec = BY_KEY[key]
    shape = capture3d.load_shape(key)
    extras_shapes = {s["key"]: capture3d.load_shape(s["key"]) for s in shape.extras}
    ppm = 6.0
    img = modelsheet.rasterise(shape, spec.marker_index, ppm=ppm, extras_shapes=extras_shapes)
    bird = next(s for s in shape.extras if s["key"] == "bird")
    img = synth.scribble(img, _mini_mask(shape, bird, ppm), ppm=ppm, seed=3, strokes=40)
    photo = synth.photograph(img, seed=1, out_size=(1200, 900))
    return spec, shape, photo


def test_coloured_window_becomes_a_catch_and_blank_one_does_not(tmp_path):
    spec, shape, photo = _photo_with_bird_coloured(HOSTS[0].key)
    idx, warped, _ = capture.detect_sheet(photo)
    assert idx == spec.marker_index
    found = {e["key"]: e for e in capture3d.extra_sheets(warped, shape)}
    assert found["bird"]["coverage"] >= capture3d.EXTRA_MIN_COVERAGE
    for k, e in found.items():
        if k != "bird":
            assert e["coverage"] < capture3d.EXTRA_MIN_COVERAGE, (
                f"nevybarvené okénko {k} se tváří jako vybarvené: {e['coverage']:.3f}")

    bird = found["bird"]
    capture3d.save_extra_catch(tmp_path / "bird", bird["sheet"], bird["shape"],
                               BY_KEY["bird"], "Pepa")
    tex = cv2.imread(str(tmp_path / "bird" / "texture.png"))
    mask = capture3d.sheet_mask(bird["shape"], capture3d.TEXTURE_PPM) > 0
    hsv = cv2.cvtColor(cv2.resize(tex, (mask.shape[1], mask.shape[0])), cv2.COLOR_BGR2HSV)
    assert (hsv[..., 1][mask] > 60).mean() > 0.10, "textura ptáčka je po přenosu bílá"


def test_blank_sheet_makes_no_extras():
    spec = HOSTS[0]
    shape = capture3d.load_shape(spec.key)
    extras_shapes = {s["key"]: capture3d.load_shape(s["key"]) for s in shape.extras}
    img = modelsheet.rasterise(shape, spec.marker_index, ppm=6.0, extras_shapes=extras_shapes)
    photo = synth.photograph(img, seed=1, out_size=(1200, 900))
    _, warped, _ = capture.detect_sheet(photo)
    assert all(e["coverage"] < capture3d.EXTRA_MIN_COVERAGE
               for e in capture3d.extra_sheets(warped, shape))
