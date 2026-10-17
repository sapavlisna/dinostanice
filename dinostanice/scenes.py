"""Registr scén (krajin) na televizi — načtený ze složek `scenes/<key>/`.

Scéna je složka:

    scenes/<key>/scene.json   jméno, popis, pořadí, texty pro děti, tvorové
    scenes/<key>/render.js    vykreslení (backdrop, světla, pásy, pohyb, krmení)
    scenes/<key>/POZNAMKY.md  proč mají tvorové v scene.json výjimky (volitelné)

Přidat scénu = přidat složku (`python tools/scena.py nova <key> --z <vzor>`).
Server z registru servíruje `GET /api/scenes` a rozhoduje, které tvory scéna
přijme.

`catalogue` je klíč sady tvorů: víc scén smí sdílet touž sadu — noční laguna
ukazuje stejné dinosaury jako denní. Sadu vlastní scéna stejného klíče (ta má
v scene.json `creatures`); scéna, která jen sdílí, od ní dědí i texty, pokud
si je nepřepíše.
"""

import json
import os
from dataclasses import dataclass, field

from . import paths

SCENES_DIR = os.path.join(paths.resource_root(), "scenes")
MARKERS_PATH = os.path.join(SCENES_DIR, "markers.json")

# texty, které scéna sdílející cizí sadu tvorů zdědí od jejího vlastníka
INHERITED = ("nouns", "accusative", "invite", "feedHint", "feedBusy")
REQUIRED = ("label", "subtitle") + INHERITED


class SceneError(ValueError):
    pass


@dataclass(frozen=True)
class Scene:
    key: str
    label: str
    subtitle: str
    catalogue: str
    order: int = 100
    # tvary slova pro 1 / 2–4 / 5+ ("dinosaurus", "dinosauři", "dinosaurů")
    nouns: tuple = ()
    accusative: str = ""        # "Vyfoť dinosaura", "Přidat rybu"
    invite: dict = field(default_factory=dict)   # QR na televizi {title, sub}
    feedHint: str = ""          # pod tlačítkem žrádla na mobilu
    feedBusy: str = ""          # když děti krmí moc často
    creatures: tuple = ()       # syrové záznamy tvorů ze scene.json

    def public(self) -> dict:
        return {"key": self.key, "label": self.label, "subtitle": self.subtitle,
                "catalogue": self.catalogue, "order": self.order,
                "nouns": list(self.nouns), "accusative": self.accusative,
                "invite": dict(self.invite), "feedHint": self.feedHint,
                "feedBusy": self.feedBusy}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(root=SCENES_DIR) -> list:
    raw = {}
    for key in sorted(os.listdir(root)):
        path = os.path.join(root, key, "scene.json")
        if os.path.isfile(path):
            raw[key] = _read_json(path)
    if not raw:
        raise SceneError(f"ve {root} není žádná scéna (scenes/<key>/scene.json)")

    out = []
    for key, d in raw.items():
        cat = d.get("catalogue", key)
        owner = raw.get(cat)
        if owner is None:
            raise SceneError(f"scéna {key}: sada tvorů {cat!r} nemá vlastní složku")
        if cat != key and d.get("creatures"):
            raise SceneError(f"scéna {key} sdílí sadu {cat!r}, vlastní tvory mít nesmí")
        merged = {k: owner[k] for k in INHERITED if k in owner} | d
        missing = [k for k in REQUIRED if not merged.get(k)]
        if missing:
            raise SceneError(f"scéna {key}: ve scene.json chybí {', '.join(missing)}")
        out.append(Scene(key=key, label=merged["label"], subtitle=merged["subtitle"],
                         catalogue=cat, order=int(merged.get("order", 100)),
                         nouns=tuple(merged["nouns"]), accusative=merged["accusative"],
                         invite=merged["invite"], feedHint=merged["feedHint"],
                         feedBusy=merged["feedBusy"],
                         creatures=tuple(d.get("creatures", ()))))
    return sorted(out, key=lambda s: (s.order, s.key))


def load_markers(path=MARKERS_PATH) -> dict:
    try:
        return _read_json(path)
    except FileNotFoundError:
        return {}


SCENES = load()
BY_KEY = {s.key: s for s in SCENES}
DEFAULT_SCENE = SCENES[0].key


def clean_scene(raw):
    """Neznámý nebo prázdný klíč spadne do defaultní scény."""
    return raw if raw in BY_KEY else DEFAULT_SCENE


def dumps(data) -> str:
    """JSON pro scene.json: odsazený, ale krátké seznamy a slovníky na řádku."""
    def flat(v):
        return not isinstance(v, (dict, list, tuple))

    def enc(v, ind):
        pad = "  " * ind
        if isinstance(v, dict):
            one = "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: "
                                  f"{json.dumps(x, ensure_ascii=False)}"
                                  for k, x in v.items()) + "}"
            if all(flat(x) for x in v.values()) and len(one) + len(pad) < 88:
                return one
            items = [f"{pad}  {json.dumps(k, ensure_ascii=False)}: {enc(x, ind + 1)}"
                     for k, x in v.items()]
            return "{\n" + ",\n".join(items) + f"\n{pad}}}"
        if isinstance(v, (list, tuple)):
            if all(flat(x) for x in v):
                return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
            return "[\n" + ",\n".join(f"{pad}  {enc(x, ind + 1)}" for x in v) + f"\n{pad}]"
        return json.dumps(v, ensure_ascii=False)
    return enc(data, 0) + "\n"
