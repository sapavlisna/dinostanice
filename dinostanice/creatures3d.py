"""Katalog tvoru stavenych z hotovych 3D modelu.

Vsechny modely jsou CC0 od Quaternia (viz CREDITS.md). Pozice predlohy i oko
se dopocitavaji, ladi se jen vyjimky. Klipy se hledaji podle holeho jmena
(`Model.clip`), protoze prefix armatury se model od modelu lisi.

Indexy znacek zacinaji na osmi: prvnich osm patrilo prvni, zrusene vetvi
projektu. Zustavaji volne pro dalsi tvory a tyhle se neprecisluji — listy
jsou vytistene a index je na nich natvrdo v rohovych znackach. Ryby proto
dostaly 16-21, ne recyklovanou nulu.
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
    # Drak se kresli bokorysem jako chodci, i kdyz ve scene leti. Shora z nej
    # byla Rorschachova skvrna: rozpeti kridel je vetsi nez telo, takze po fitu
    # na list zbyla z hlavy boule na hrane a oko skoncilo jako tecka uprostred
    # tela. Z boku ma hlavu s rohem a otevrenou hubou, oko na spravnem miste
    # a kridlo jako plachtu se zebry — na rozdil od pteranodona, ktery je same
    # kridlo, ma drak dost tela a hlavy, aby ho dite poznalo. Poza je natvrdo
    # z Death (t=0.37): drak se v nem naklani dopredu s rozepjatym kridlem,
    # takze membrana lezi v rovine listu a ma plochu k vybarveni. Ve Flying_Idle
    # drzi kridla podel tela a z boku z nich zbyva uzky profil.
    Model3D("drak3d", "Drak", "dragon.glb", 14, motion="fly",
            poses=("Death",), anim="Death", time=0.37),
    # Ptakojester prisel bez kostry, tu mu dopisuje tools/make_pteranodon.py.
    # Kresli se shora a natoceny tak, aby rozpeti kridel — jeho nejvetsi rozmer
    # — leželo po sirce listu; z boku by z nej byl jen tenky profil. Proto oko
    # nelezi pred telem, ale na ose soumernosti listu (centre_x): bbox hlavy je
    # kvuli hrebeni nesoumerny a forward=0.5 by oko poslal mimo osu.
    Model3D("pteranodon3d", "Pteranodon", "pteranodon.glb", 15, motion="fly",
            axes=(0, 2, 1), flip=(1, -1, -1), poses=("Flying",),
            eye_bias={"centre_x": True, "down": 0.55}),

    # --- akvarium -----------------------------------------------------------
    # Klice jsou bez suffixu "3d": ten u dinosauru odlisoval 3D vetev od
    # zrusene 2D (kresba -> ohybany pas), ktera uz neexistuje, takze u novych
    # tvoru je zbytecny.
    #
    # Indexy 16-21, ne 0-7. Prvnich osm je sice volnych, ale doma jeste lezi
    # vytistene listy zrusene vetve s temi indexy v rohovych znackach — kdyby
    # se recyklovaly, poznal by se stary list jako ryba.
    #
    # Ryby se kresli bokorysem: rybi profil je nejcitelnejsi silueta a ma
    # velke plochy k vybarveni. Vyjimka je manta (viz jeji zaznam).
    # `stride_rate` zustava None zamerne: je to tempo chuze v delkach tela za
    # sekundu, odvozene z kroku. Plavec zemi nedotyka, takze u nej neni z ceho
    # tempo pocitat — rychlost i frekvenci vlneni urcuje scena.
    #
    # Rybi armatura Quaterniova packu ma jointy Main1..Main6 (Main1 = hlava),
    # zadny "Head"; zralok a manta "Head" maji.
    #
    # Ctyri druhy z rybi armatury maji oko jako vlastni material, takze uz ho
    # do kresby vnasi vnitrni linka — velky krouzek na hlave. Tistene oko je
    # jim proto zornicka a `eye_bias` ho posadi do stredu toho krouzku;
    # vychozich forward=0,68 / down=0,34 mirilo mimo (rybi Main1 je cela
    # predni pulka tela, ne hlava, takze zlomky jeji obalky vychazi jinam).
    Model3D("clownfish", "Klaunská rybka", "clownfish.glb", 16, motion="swim",
            scene="aquarium", poses=("Swimming_Normal",), eye_joint="Main1",
            eye_bias={"forward": 0.74, "down": 0.59}, clip_for={"move": "Normal"}),
    Model3D("shark", "Žralok", "shark.glb", 17, motion="swim",
            scene="aquarium", poses=("Swim",)),
    Model3D("puffer", "Čtverzubec", "puffer.glb", 18, motion="swim",
            scene="aquarium", poses=("Swimming_Normal",), eye_joint="Main1",
            eye_bias={"forward": 0.72, "down": 0.31}, clip_for={"move": "Normal"}),
    Model3D("swordfish", "Mečoun", "swordfish.glb", 19, motion="swim",
            scene="aquarium", poses=("Swimming_Normal",), eye_joint="Main1",
            eye_bias={"forward": 0.20, "down": 0.38}, clip_for={"move": "Normal"}),
    Model3D("lionfish", "Perutýn", "lionfish.glb", 20, motion="swim",
            scene="aquarium", poses=("Swimming_Normal",), eye_joint="Main1",
            eye_bias={"forward": 0.41, "down": 0.73}, clip_for={"move": "Normal"}),
    # Manta se kresli shora jako pteranodon: z boku je to 1 mm tenka placka,
    # ze ktere neni co vybarvovat (fill 0,05 proti 0,21 shora). Rozpeti kridel
    # lezi po svisle ose listu, telo i bicikovity ocas po vodorovne. Hloubkove
    # znamenko -1 obraci pohled na hrbet (material "Top"), ne na bile bricho.
    # Oko nesedi na ose soumernosti jako u pteranodona, ale u kraje hlavy —
    # tam ho manta doopravdy ma, po strane za rohatym hlavovym lalokem. Ma
    # jediny klip Swim, takze `fast` padne zpatky na nej.
    Model3D("manta", "Manta", "manta.glb", 21, motion="swim",
            scene="aquarium", axes=(2, 0, 1), flip=(1, -1, -1),
            eye_bias={"forward": 0.30, "down": 0.18},
            poses=("Swim",), clip_for={"fast": "Swim"}),
]

BY_KEY = {m.key: m for m in CATALOGUE}
BY_MARKER = {m.marker_index: m for m in CATALOGUE}
