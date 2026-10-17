"""Scéna = složka `scenes/<key>/`. Kontrakty, které musí platit pro každou,
aby se nová scéna dala přidat bez sahání do kódu."""

import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from dinostanice import creatures3d, markers, scenes

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("sc", scenes.SCENES, ids=lambda s: s.key)
def test_every_scene_has_render_and_texts(sc):
    assert (ROOT / "scenes" / sc.key / "render.js").is_file()
    assert len(sc.nouns) == 3 and all(sc.nouns)
    assert sc.invite.get("title") and sc.invite.get("sub")
    assert sc.accusative and sc.feedHint and sc.feedBusy


@pytest.mark.parametrize("sc", scenes.SCENES, ids=lambda s: s.key)
def test_every_scene_has_printable_creatures(sc):
    own = [m for m in creatures3d.CATALOGUE if m.scene == sc.catalogue]
    assert own, f"scéna {sc.key} nemá žádného tvora"
    for m in own:
        assert (ROOT / "data/templates" / f"{m.key}.svg").is_file(), m.key


def test_marker_indices_fit_the_dictionary():
    idx = [m.marker_index for m in creatures3d.CATALOGUE]
    assert len(set(idx)) == len(idx)
    assert min(idx) >= creatures3d.FIRST_MARKER
    assert max(idx) <= markers.MAX_CREATURE_INDEX


def test_marker_registry_is_never_reused():
    reg = scenes.load_markers()
    assert len(set(reg.values())) == len(reg), "dva tvorové sdílí index značky"


def test_wider_dictionary_keeps_printed_markers():
    """Vytištěné listy nesou kódy ze 4X4_100 — větší slovník je musí znát stejně."""
    small = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100).bytesList
    assert np.array_equal(markers.DICT.bytesList[:len(small)], small)


def test_shared_catalogue_inherits_texts():
    night = scenes.BY_KEY["cretaceous_night"]
    day = scenes.BY_KEY["cretaceous"]
    assert night.catalogue == "cretaceous"
    assert night.nouns == day.nouns and night.invite == day.invite


def test_scene_without_texts_is_rejected(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "scene.json").write_text(json.dumps({"label": "X"}), encoding="utf-8")
    with pytest.raises(scenes.SceneError, match="chybí"):
        scenes.load(str(tmp_path))


def test_creature_without_marker_is_reported():
    sc = scenes.Scene("x", "X", "", "x", creatures=({"key": "nikdo", "label": "N",
                                                     "glb": "n.glb"},))
    with pytest.raises(creatures3d.CatalogueError, match="scena.py import x"):
        creatures3d.build([sc], {})


def test_dumps_round_trips():
    for sc in scenes.SCENES:
        path = os.path.join(scenes.SCENES_DIR, sc.key, "scene.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert json.loads(scenes.dumps(data)) == data
