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
# Chodci: `move` chuze, `stand` stani, ostatni role nesou cinnosti planovace
# ve scene (web/scenelogic.js): `run` zaber, `look` rozhlednuti, `sit`/`lie`
# prehrane jednou a podrzene (vstavani = tyz klip pozpatku), `sleep` smycka
# vlezle, `play` dupnuti/hra. Sit, LieDown, Sleep a LookAround dopisuje
# tools/blender_clips.py, `eat` jsou klipy pastvy z balicku zvirat. Povinna je
# jen `move`; roli, jejiz klip model nema, export z katalogu vypusti a scena
# cinnost nenabidne (resolve_roles). `clip_for: {"lie": null}` roli vypne
# i tam, kde by jinak padla na nahradni klip.
CLIP_FOR_DEFAULT = {
    "walk": {"move": "Walk", "stand": "Idle", "jump": "Jump", "run": "Run",
             "look": "LookAround", "sit": "Sit", "lie": "LieDown",
             "sleep": "Sleep", "play": "Attack", "eat": "Eating"},
    "fly": {"move": "Flying"},
    # Plavci: `move` je klidne plavani, `fast` sprint. Kdo `fast` nema (manta
    # nese jediny klip), prepise si ho zpatky na `move` — scena tak nemusi
    # hadat, jestli role existuje.
    "swim": {"move": "Swim", "fast": "Fast"},
    "sail": {"move": "Sail"},
}

REQUIRED_ROLES = {"move"}

# Nahradni klip, kdyz model hlavni nema. Lehnuti puvodne hral Death (prehrany
# jednou a podrzeny) — maji ho vsichni chodci katalogu; apatosaurus ho nese
# pod cizim jmenem "Armature|Stegosaurus_Death", ale kanaly miri na jeho
# vlastni kostru a model si opravdu lehne (overeno pres gltf.Model.posed).
ROLE_FALLBACK = {"lie": ["Death"]}


def resolve_roles(roles: dict, shorts) -> tuple[dict, list]:
    """Role, ktere model opravdu unese, a seznam chybejicich volitelnych rolí.

    Povinna role zustava i bez klipu (at kontrola nahlas spadne). Spanek
    navazuje na konec LieDown — po nahradnim Death by se tvor pri usnuti
    prevalil, takze s nahradnim lehnutim spanek odpada."""
    shorts = set(shorts)
    out, missing = {}, []
    for role, name in roles.items():
        if name is None:
            continue
        if name in shorts or role in REQUIRED_ROLES:
            out[role] = name
            continue
        alt = next((a for a in ROLE_FALLBACK.get(role, []) if a in shorts), None)
        if alt:
            out[role] = alt
        else:
            missing.append(role)
    if out.get("lie") in ROLE_FALLBACK["lie"] and "sleep" in out:
        del out["sleep"]
        missing.append("sleep")
    return out, missing


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
    # Prepis nabidky cinnosti planovace pro tento druh (vahy, delky), sloucene
    # pres motions.<typ>.activities z render.js sceny — viz web/scenelogic.js.
    activities: dict = field(default_factory=dict)

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
