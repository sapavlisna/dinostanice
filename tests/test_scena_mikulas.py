"""Scéna Mikulášská: postavy z tools/make_mikulas.py projdou katalogem a mají,
co scéna u chodce čte (chodidla pro krok, krk a hlavu pro pohled, klipy rolí)."""
import re

import pytest

from dinostanice import scenes
from dinostanice.creatures3d import BY_KEY, resolve_roles
from dinostanice.gltf import Model

KEYS = ["mik_mikulas", "mik_andel", "mik_cert"]


def test_scena_je_v_registru():
    sc = scenes.BY_KEY["mikulas"]
    assert [c["key"] for c in sc.creatures] == KEYS
    assert sc.catalogue == "mikulas"


@pytest.mark.parametrize("key", KEYS)
def test_postava_ma_kostru_klipy_a_chodidla(key):
    spec = BY_KEY[key]
    model = Model(f"data/models_src/{spec.glb}")
    names = model.node_names
    assert any(re.search(r"foot|toe", n, re.I) for n in names)
    assert sum(bool(re.search(r"neck", n, re.I)) for n in names) == 1
    assert sum(bool(re.search(r"head", n, re.I)) for n in names) == 1
    shorts = {full.split("|")[-1] for full in model.animations}
    roles, missing = resolve_roles(spec.clip_roles(), shorts)
    assert {"move", "stand", "run", "look", "play"} <= set(roles)
    assert roles["play"] == "Wave"
    assert not {"sit", "lie", "sleep"} & set(roles)


def test_mikulas_nebezi_ani_neskace():
    spec = BY_KEY["mik_mikulas"]
    assert spec.activities["run"]["weight"] == 0
    assert spec.clip_roles()["jump"] is None
