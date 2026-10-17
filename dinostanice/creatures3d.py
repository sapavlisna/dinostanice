"""Katalog tvoru stavenych z hotovych 3D modelu.

Tvorove se zapisuji do `scenes/<sada>/scene.json` (pole `creatures`), proc ma
ktery vyjimky, stoji vedle v POZNAMKY.md. Zdroje a licence modelu jsou
v CREDITS.md. Pozice predlohy i oko se dopocitavaji, ladi se jen vyjimky.
Klipy se hledaji podle holeho jmena (`Model.clip`), protoze prefix armatury se
model od modelu lisi.

Index znacky NENI ve scene.json, ale v `scenes/markers.json` a prideluje ho
`tools/scena.py`: index je natvrdo vytisteny v rohovych znackach listu, takze
se nikdy neprecisluje ani nerecykluje. 0-7 patrily prvni, zrusene vetvi
projektu (doma jeste lezi jeji vytistene listy), proto se zacina na osmi.
"""
from dataclasses import dataclass, field

from . import scenes

# Ktery klip z `clips` hraje kterou roli ve scene. Default per motion; model,
# ktery ma klipy pojmenovane jinak, si roli prepise pres `clip_for`.
# `lie` = lehnuti pri cekani (Death prehrany jednou a podrzeny, vstavani
# pozpatku). Death maji vsichni chodci katalogu — apatosaurus ho nese pod
# cizim jmenem "Armature|Stegosaurus_Death", ale kanaly miri na jeho vlastni
# kostru a model si opravdu lehne (overeno pres gltf.Model.posed).
CLIP_FOR_DEFAULT = {
    "walk": {"move": "Walk", "stand": "Idle", "jump": "Jump", "lie": "Death"},
    "fly": {"move": "Flying"},
    # Plavci: `move` je klidne plavani, `fast` sprint. Kdo `fast` nema (manta
    # nese jediny klip), prepise si ho zpatky na `move` — scena tak nemusi
    # hadat, jestli role existuje.
    "swim": {"move": "Swim", "fast": "Fast"},
    "sail": {"move": "Sail"},
}


@dataclass
class Model3D:
    key: str
    label: str
    glb: str
    marker_index: int
    motion: str = "walk"
    # Do ktere sady tvoru (Scene.catalogue) model patri. Marker index zustava
    # globalni — sablona identifikuje tvora, scena jen rika, koho prijme.
    scene: str = ""
    # Cilove tempo chuze v delkach tela za sekundu (paleo odhad per druh,
    # viz out/audit/animator.md) — vlastnost druhu, ne sceny. None = default
    # z definice sceny.
    stride_rate: tuple | None = None
    # Vyjimky z CLIP_FOR_DEFAULT (role -> klic v `clips`).
    clip_for: dict = field(default_factory=dict)
    # Bokorys pro chodce, pohled shora pro letce: rozepjata kridla jsou z boku
    # jen tenky profil, ze ktereho neni co vybarvovat. Vyjimka je drak — ten ma
    # dost tela i hlavy, aby ho bokorys unesl, viz komentar u jeho zaznamu.
    axes: tuple = (2, 1, 0)
    flip: tuple = (1, -1, 1)
    eye_bias: dict = field(default_factory=dict)
    # Joint, z jehoz obalky se odvodi oko. Dinosauri a drak maji "Head", rybi
    # armatura Quaterniova packu jen "Main1".."Main6" (Main1 je hlavova).
    eye_joint: str = "Head"
    # Kandidati na pozu predlohy. Zustava u chuze zamerne: pusteni vsech animaci
    # do vyberu sice list vyplni lip, ale Attack tvora prekroutí — apatosaurovi
    # premaluje ocas pres telo a stegosaurovi schova plotenky.
    poses: tuple = ("Walk",)
    anim: str | None = None      # natvrdo zvolena animace, jinak se vybira
    time: float | None = None    # natvrdo zvoleny cas, jinak se vybira

    def candidates(self, model) -> list:
        names = [self.anim] if self.anim else list(self.poses)
        return [c for c in (model.clip(n) for n in names) if c]

    def clip_roles(self) -> dict:
        return {**CLIP_FOR_DEFAULT.get(self.motion, {}), **self.clip_for}


FIRST_MARKER = 8

TUPLES = ("axes", "flip", "poses", "stride_rate")


class CatalogueError(ValueError):
    pass


def build(scene_list=None, markers=None) -> list:
    """Tvorove ze vsech scen, ktere sadu vlastni, s indexy z markers.json."""
    scene_list = scenes.SCENES if scene_list is None else scene_list
    markers = scenes.load_markers() if markers is None else markers
    out = []
    for sc in scene_list:
        for raw in sc.creatures:
            d = {k: (tuple(v) if k in TUPLES and v is not None else v)
                 for k, v in raw.items()}
            key = d.get("key")
            if key not in markers:
                raise CatalogueError(
                    f"tvor {key} (scena {sc.key}) nema index znacky — spust "
                    f"python tools/scena.py import {sc.key}")
            try:
                out.append(Model3D(marker_index=markers[key], scene=sc.key, **d))
            except TypeError as e:
                raise CatalogueError(f"tvor {key} (scena {sc.key}): {e}") from e
    return out


CATALOGUE = build()
BY_KEY = {m.key: m for m in CATALOGUE}
BY_MARKER = {m.marker_index: m for m in CATALOGUE}
