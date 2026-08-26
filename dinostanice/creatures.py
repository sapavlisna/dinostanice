"""The catalogue. One entry per printable template.

The animals come from CC0 silhouettes (see CREDITS.md); their geometry is
precomputed by tools/build_catalogue.py into data/shapes/*.json. The boat and
the plane are hand-written parametric shapes -- PhyloPic only has organisms.

Marker IDs are allocated by position in CATALOGUE, so reordering it invalidates
every sheet already printed.
"""

import json
import os

from .shapes import Creature, Limb

SHAPES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "shapes")


def _load(key):
    with open(os.path.join(SHAPES_DIR, f"{key}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    limbs = []
    for l in doc["limbs"]:
        if l.get("parts"):
            limbs.append(Limb(name=l["name"], anchor=l["anchor"], side=l["side"],
                              parts=[(p["poly"], p["pivot"], p["tip"]) for p in l["parts"]]))
        else:
            limbs.append(Limb(name=l["name"], anchor=l.get("anchor"), side=l.get("side", 0),
                              outline=l["outline"], pivot=tuple(l["pivot"])))
    return Creature(key=doc["key"], label=doc["label"], spine=doc["spine"],
                    profile=doc["profile"], outline=doc["outline"], limbs=limbs,
                    motion=doc["motion"], view=doc["view"], rigid=doc.get("rigid", False),
                    details=doc.get("details", []))


SAUROPOD = _load("sauropod")
TREX = _load("trex")
STEGOSAURUS = _load("stegosaurus")
TRICERATOPS = _load("triceratops")
PTERANODON = _load("pteranodon")
PLESIOSAUR = _load("plesiosaur")

SHIP = _load("ship")
PLANE = _load("plane")

CATALOGUE = [SAUROPOD, TREX, STEGOSAURUS, TRICERATOPS, PTERANODON, PLESIOSAUR,
             SHIP, PLANE]
BY_KEY = {c.key: c for c in CATALOGUE}
