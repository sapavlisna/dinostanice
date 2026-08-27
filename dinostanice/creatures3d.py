"""Katalog tvoru stavenych z hotovych 3D modelu.

Vsechny modely jsou CC0 od Quaternia (viz CREDITS.md). Pozice predlohy i oko
se dopocitavaji, ladi se jen vyjimky. Klipy se hledaji podle holeho jmena
(`Model.clip`), protoze prefix armatury se model od modelu lisi.

Indexy znacek navazuji na osm tvoru stare vetve (0-7), aby se uz vytistene
listy nezneplatnily.
"""
from dataclasses import dataclass, field

# Ktery klip z `clips` hraje kterou roli ve scene. Default per motion; model,
# ktery ma klipy pojmenovane jinak, si roli prepise pres `clip_for`.
# `lie` = lehnuti pri cekani (Death prehrany jednou a podrzeny, vstavani
# pozpatku). Death maji vsichni chodci katalogu — apatosaurus ho nese pod
# cizim jmenem "Armature|Stegosaurus_Death", ale kanaly miri na jeho vlastni
# kostru a model si opravdu lehne (overeno pres gltf.Model.posed).
CLIP_FOR_DEFAULT = {
    "walk": {"move": "Walk", "stand": "Idle", "jump": "Jump", "lie": "Death"},
    "fly": {"move": "Flying"},
    "swim": {"move": "Swim"},
    "sail": {"move": "Sail"},
}


@dataclass
class Model3D:
    key: str
    label: str
    glb: str
    marker_index: int
    motion: str = "walk"
    # Do ktere sady tvoru (Scene.catalogue v scenes.py) model patri. Marker
    # index zustava globalni — sablona identifikuje tvora, scena jen rika,
    # koho prijme.
    scene: str = "cretaceous"
    # Cilove tempo chuze v delkach tela za sekundu (paleo odhad per druh,
    # viz out/audit/animator.md) — vlastnost druhu, ne sceny. None = default
    # z definice sceny.
    stride_rate: tuple | None = None
    # Vyjimky z CLIP_FOR_DEFAULT (role -> klic v `clips`).
    clip_for: dict = field(default_factory=dict)
    # Bokorys pro chodce, pohled shora pro letce: rozepjata kridla jsou z boku
    # jen tenky profil, ze ktereho neni co vybarvovat.
    axes: tuple = (2, 1, 0)
    flip: tuple = (1, -1, 1)
    eye_bias: dict = field(default_factory=dict)
    # Kandidati na pozu predlohy. Zustava u chuze zamerne: pusteni vsech animaci
    # do vyberu sice list vyplni lip, ale Attack tvora prekroutí — sauropodovi
    # premaluje ocas pres telo a stegosaurovi schova plotenky.
    poses: tuple = ("Walk",)
    anim: str | None = None      # natvrdo zvolena animace, jinak se vybira
    time: float | None = None    # natvrdo zvoleny cas, jinak se vybira

    def candidates(self, model) -> list:
        names = [self.anim] if self.anim else list(self.poses)
        return [c for c in (model.clip(n) for n in names) if c]

    def clip_roles(self) -> dict:
        return {**CLIP_FOR_DEFAULT.get(self.motion, {}), **self.clip_for}


CATALOGUE = [
    Model3D("trex3d", "Tyrannosaurus", "trex.glb", 8,
            stride_rate=(0.11, 0.18)),
    Model3D("velociraptor3d", "Velociraptor", "velociraptor.glb", 9,
            stride_rate=(0.30, 0.40)),
    Model3D("triceratops3d", "Triceratops", "triceratops.glb", 10,
            stride_rate=(0.12, 0.18)),
    Model3D("stegosaurus3d", "Stegosaurus", "stegosaurus.glb", 11,
            stride_rate=(0.12, 0.18)),
    Model3D("parasaurolophus3d", "Parasaurolophus", "parasaurolophus.glb", 12,
            stride_rate=(0.14, 0.25)),
    Model3D("apatosaurus3d", "Apatosaurus", "apatosaurus.glb", 13,
            stride_rate=(0.04, 0.06)),
    # Letec se kresli shora a natoceny tak, aby rozpeti kridel — jeho nejvetsi
    # rozmer — leželo po sirce listu.
    # Letci se kresli shora, takze oko nelezi pred telem, ale na ose
    # soumernosti listu (centre_x) — bbox hlavy je kvuli hrebeni ci rohum
    # nesoumerny a forward=0.5 by oko poslal mimo osu.
    # Drak ma pozu natvrdo: best_pose vybira podle vyplneni listu a trefi
    # kridla uprostred mavnuti, ze kterych dite draka nepozna. Flying_Idle
    # v t=0.125 je okamzik s nejvetsim rozpetim — kridla vodorovne
    # rozprostrena, membrany viditelne shora.
    Model3D("drak3d", "Drak", "dragon.glb", 14, motion="fly",
            axes=(0, 2, 1), flip=(1, 1, -1), poses=("Flying_Idle",),
            anim="Flying_Idle", time=0.125,
            eye_bias={"centre_x": True, "down": 0.3}),
    # Ptakojester prisel bez kostry, tu mu dopisuje tools/make_pteranodon.py
    Model3D("pteranodon3d", "Pteranodon", "pteranodon.glb", 15, motion="fly",
            axes=(0, 2, 1), flip=(1, -1, -1), poses=("Flying",),
            eye_bias={"centre_x": True, "down": 0.55}),
]

BY_KEY = {m.key: m for m in CATALOGUE}
