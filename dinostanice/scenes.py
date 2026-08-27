"""Registr scén (krajin) na televizi.

Přidání scény = jeden záznam sem + JS soubory `web/scenes/<key>.js`
(definice: bands, motions, lighting, backdrop import) a případně nový
backdrop modul ve `web/backdrops/`. Server z registru servíruje
`GET /api/scenes` a rozhoduje, které tvory scéna přijme.

`catalogue` je klíč sady tvorů (Model3D.scene v creatures3d.py): víc scén
smí sdílet touž sadu — noční laguna ukazuje stejné dinosaury jako denní.
"""

from dataclasses import dataclass

DEFAULT_SCENE = "cretaceous"


@dataclass(frozen=True)
class Scene:
    key: str
    label: str
    subtitle: str
    catalogue: str


SCENES = [
    Scene("cretaceous", "Křídová laguna",
          "Slunečná pláž s lagunou, sopkou a jehličnatým pralesem.",
          "cretaceous"),
    Scene("cretaceous_night", "Noční laguna",
          "Táž krajina za soumraku — měsíc, hvězdy a dinosauři v šeru.",
          "cretaceous"),
]

BY_KEY = {s.key: s for s in SCENES}


def clean_scene(raw):
    """Neznámý nebo prázdný klíč spadne do defaultní scény."""
    return raw if raw in BY_KEY else DEFAULT_SCENE
