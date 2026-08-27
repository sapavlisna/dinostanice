"""Kontrakty katalogu, ktere scena bere jako dane — bez nacitani GLB.

Scena si tvora sklada z `data/models3d/catalogue3d.json`: klip pro roli hleda
jako `spec.clips[spec.clipFor.move]`. Kdyz se role do `clips` netrefi, tvor se
ve scene tise nerozhybe, protoze `undefined` neni chyba. Zkratka jmena klipu
se pritom odvozuje z jeho glTF nazvu (`tools/model_export3d.py`) a ten se model
od modelu lisi — rybi armatura ma v prefixu podtrzitko, drakova ne — takze to
je presne misto, kde se to muze rozejit.
"""

import json
from pathlib import Path

import pytest

from dinostanice.creatures3d import BY_KEY, CATALOGUE

ROOT = Path(__file__).resolve().parent.parent
INDEX = json.loads((ROOT / "data/models3d/catalogue3d.json").read_text(encoding="utf-8"))
BY_INDEX_KEY = {e["key"]: e for e in INDEX}


def test_marker_indices_are_unique_and_outside_the_retired_range():
    idx = [m.marker_index for m in CATALOGUE]
    assert len(set(idx)) == len(idx)
    # 0-7 patri zrusene vetvi; vytistene listy s temi indexy jeste existuji
    assert min(idx) >= 8


def test_keys_are_unique():
    keys = [m.key for m in CATALOGUE]
    assert len(set(keys)) == len(keys)


def test_index_covers_the_whole_catalogue():
    assert BY_INDEX_KEY.keys() == BY_KEY.keys()


@pytest.mark.parametrize("key", list(BY_KEY))
def test_clip_roles_resolve_to_real_clips(key):
    entry = BY_INDEX_KEY[key]
    clips = entry["clips"]
    assert entry["clipFor"], f"{key}: zadna role klipu"
    assert "move" in entry["clipFor"], f"{key}: chybi role move"
    for role, short in entry["clipFor"].items():
        assert short in clips, (
            f"{key}: role {role!r} miri na {short!r}, ale klipy jsou "
            f"{sorted(clips)}")
        assert clips[short], f"{key}: klip {short!r} je prazdny"


@pytest.mark.parametrize("key", list(BY_KEY))
def test_generated_files_exist(key):
    spec = BY_KEY[key]
    for rel in (f"data/models_src/{spec.glb}", f"data/shapes3d/{key}.json",
                f"data/templates/{key}.svg", f"data/models3d/{key}.glb",
                f"data/models3d/{key}_texture.png"):
        assert (ROOT / rel).exists(), rel
