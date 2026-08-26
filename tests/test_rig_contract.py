"""rig.build_rig must produce a rig.json matching the ARCHITECTURE.md schema for every creature:
required keys present, body.png dimensions matching the declared samples/half_mm/ppm, every limb
segment's image file present and readable, and tip_mm of one segment == pivot_mm of the next.
"""

import json
import os

import cv2
import numpy as np
import pytest

import helpers as H
from dinostanice import creatures as cr, rig
from dinostanice.capture import WARP_PPM, extract_texture

TOL_MM = 0.02  # rig.json rounds to 2 decimals, so two equal values can differ by this much after rounding


@pytest.fixture(scope="module")
def built_rigs(tmp_path_factory):
    """Build every creature's rig once (module-scoped) and hand back {key: (rig_dict, out_dir)}."""
    out = {}
    for idx, creature in enumerate(cr.CATALOGUE):
        _, sheet = H.scribbled_sheet(idx, seed=3, ppm=WARP_PPM, strokes=10)
        rgba_crop, bbox_mm = extract_texture(sheet, creature)
        full_rgba = H.full_sheet_rgba(rgba_crop, bbox_mm)
        out_dir = tmp_path_factory.mktemp(f"rig_{creature.key}")
        rig_dict = rig.build_rig(full_rgba, creature, str(out_dir), name=f"test-{creature.key}")
        out[creature.key] = (rig_dict, out_dir)
    return out


@pytest.mark.parametrize("creature", cr.CATALOGUE, ids=[c.key for c in cr.CATALOGUE])
def test_rig_has_required_top_level_keys(built_rigs, creature):
    rig_dict, out_dir = built_rigs[creature.key]
    for key in ("name", "creature", "label", "motion", "view", "ppm", "sheet_mm", "body", "limbs"):
        assert key in rig_dict, f"rig.json for {creature.key} is missing {key!r}"
    assert rig_dict["creature"] == creature.key
    assert (out_dir / "rig.json").exists()


@pytest.mark.parametrize("creature", cr.CATALOGUE, ids=[c.key for c in cr.CATALOGUE])
def test_rig_json_round_trips_through_disk(built_rigs, creature):
    rig_dict, out_dir = built_rigs[creature.key]
    with open(out_dir / "rig.json", encoding="utf-8") as f:
        from_disk = json.load(f)
    assert from_disk == rig_dict


@pytest.mark.parametrize("creature", cr.CATALOGUE, ids=[c.key for c in cr.CATALOGUE])
def test_body_image_matches_declared_dimensions(built_rigs, creature):
    rig_dict, out_dir = built_rigs[creature.key]
    body = rig_dict["body"]
    img = cv2.imread(str(out_dir / body["image"]), cv2.IMREAD_UNCHANGED)
    assert img is not None, f"{body['image']} missing or unreadable for {creature.key}"

    if body.get("rigid"):
        assert "size_mm" in body and "origin_mm" in body
        w_mm, h_mm = body["size_mm"]
        assert img.shape[1] == pytest.approx(w_mm * rig_dict["ppm"], abs=2)
        assert img.shape[0] == pytest.approx(h_mm * rig_dict["ppm"], abs=2)
    else:
        for key in ("length_mm", "half_mm", "samples", "radius_mm", "spine_mm"):
            assert key in body, f"non-rigid body for {creature.key} is missing {key!r}"
        assert img.shape[1] == body["samples"], (
            f"body.png width {img.shape[1]} should equal samples {body['samples']} for {creature.key}"
        )
        expected_h = round(2 * body["half_mm"] * rig_dict["ppm"])
        assert img.shape[0] == expected_h, (
            f"body.png height {img.shape[0]} should be round(2*half_mm*ppm)={expected_h} for {creature.key}"
        )
        assert len(body["radius_mm"]) == body["samples"]
        assert len(body["spine_mm"]) == body["samples"]


@pytest.mark.parametrize("creature", cr.CATALOGUE, ids=[c.key for c in cr.CATALOGUE])
def test_limb_segment_images_exist_and_are_valid(built_rigs, creature):
    rig_dict, out_dir = built_rigs[creature.key]
    assert len(rig_dict["limbs"]) == len(creature.limbs)
    for limb in rig_dict["limbs"]:
        assert limb["segments"], f"limb {limb['name']} of {creature.key} has no segments"
        for seg in limb["segments"]:
            path = out_dir / seg["image"]
            assert path.exists(), f"missing {seg['image']} for limb {limb['name']} of {creature.key}"
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            assert img is not None and img.size > 0
            assert img.shape[2] == 4, f"{seg['image']} should have an alpha channel"
            for key in ("origin_mm", "pivot_mm", "tip_mm", "length_mm"):
                assert key in seg


@pytest.mark.parametrize("creature", cr.CATALOGUE, ids=[c.key for c in cr.CATALOGUE])
def test_segment_tip_equals_next_pivot(built_rigs, creature):
    rig_dict, out_dir = built_rigs[creature.key]
    for limb in rig_dict["limbs"]:
        segs = limb["segments"]
        for a, b in zip(segs, segs[1:]):
            assert a["tip_mm"] == pytest.approx(b["pivot_mm"], abs=TOL_MM), (
                f"{creature.key}/{limb['name']}: tip_mm {a['tip_mm']} != next pivot_mm {b['pivot_mm']}"
            )
