"""The 3D model has one contract: from the side it is the drawing.

If the silhouette drifts, the child's colouring stops landing where they put
it, so that is what these check -- plus the skin being one sound piece.
"""

import cv2
import numpy as np
import pytest

from dinostanice import inflate, model3d
from dinostanice.creatures import BY_KEY
from dinostanice.raster import creature_mask
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

KEY = "sauropod"
PPM = model3d.PPM


@pytest.fixture(scope="module")
def built():
    return model3d.build(BY_KEY[KEY])


def rasterise(part):
    """Silhouette of the model seen from the side, at sheet resolution."""
    img = np.zeros((int(SHEET_H_MM * PPM), int(SHEET_W_MM * PPM)), np.uint8)
    tris = np.asarray(part["pos"])[np.asarray(part["faces"])][:, :, :2]
    # one at a time: handing fillPoly the whole batch applies the even-odd rule
    # across it, and the back of the mesh then cancels out the front
    for tri in np.round(tris * PPM).astype(np.int32):
        cv2.fillConvexPoly(img, tri, 255)
    return img


def test_side_view_is_the_drawing(built):
    part, _ = built
    got = rasterise(part) > 0
    want = creature_mask(BY_KEY[KEY], ppm=PPM) > 0
    iou = (got & want).sum() / (got | want).sum()
    assert iou > 0.95, f"silueta modelu se rozešla se šablonou, IoU {iou:.3f}"


def test_depth_matches_drawn_width():
    """A tube drawn 20 mm across must come out 20 mm deep, give or take a pixel."""
    mask = np.zeros((400, 400), np.uint8)
    cv2.rectangle(mask, (60, 190), (340, 210), 255, -1)      # 20 px wide at ppm 1
    z = inflate.depth_field(mask, ppm=1.0)
    assert 9.0 < z.max() < 11.5, z.max()


def test_one_continuous_skin(built):
    """Separate parts meant sockets, and filling those hung stumps under the
    belly -- four extra legs. The skin has to stay in one piece."""
    part, _ = built
    faces = np.asarray(part["faces"])
    edges = np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    assert open_edges < len(faces) * 0.02, f"{open_edges} otevřených hran z {len(faces)}"


def test_mesh_has_no_stray_normals(built):
    part, _ = built
    assert np.allclose(np.linalg.norm(part["nrm"], axis=1), 1.0, atol=1e-3)
    assert np.isfinite(part["pos"]).all()


def test_limbs_are_pushed_apart_in_depth(built):
    """Otherwise the model is a cut-out with all four legs in one plane."""
    part, _ = built
    legs = part["limbs"]
    assert len(legs) == 4, [l["name"] for l in legs]
    near = [l for l in legs if l["side"] == 0]
    far = [l for l in legs if l["side"] == 1]
    assert len(near) == 2 and len(far) == 2
    assert min(l["pivot"][2] for l in near) > 4.0
    assert max(l["pivot"][2] for l in far) < -4.0


def test_legs_come_from_the_silhouette_not_the_segmentation(built):
    """The skeleton derivation loses one hind leg to a 7 mm stump. Regions taken
    from the drawing instead must show it at full length."""
    part, _ = built
    assert min(l["length_mm"] for l in part["limbs"]) > 25.0, \
        [(l["name"], l["length_mm"]) for l in part["limbs"]]


def test_uv_lands_on_the_sheet(built):
    part, _ = built
    uv = np.asarray(part["uv"])
    assert uv.min() >= -0.01 and uv.max() <= 1.01


def test_every_creature_builds():
    """A limb region that matches nothing, or a mask that will not inflate, must
    not wait until someone opens the page on the television."""
    for key in ("trex", "stegosaurus", "triceratops", "pteranodon", "plesiosaur",
                "ship", "plane"):
        part, notes = model3d.build(BY_KEY[key], spacing=4.0)
        doc = model3d.to_json(BY_KEY[key], part, notes)
        assert len(doc["limb_id"]) == len(part["pos"]), key
        assert len(doc["limb_w"]) == len(part["pos"]), key
        assert max(doc["limb_id"]) < len(doc["limbs"]), key
