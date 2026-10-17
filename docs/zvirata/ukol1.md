# Úkol 1 — Hlava k dětem (A2)

## Co je hotové

- `web/scene3d.js`: při `spawn` se najdou kosti `Neck` a `Head` (regex `/neck/i`, `/head/i`,
  bez `_end`; když hlava chybí, zkusí se `Main1`; když chybí i ta, pohled se tiše vypne,
  `handle.look = null`). Nové API `Scene3D.look(handle, weight, opts)`: cílová váha 0..1,
  `opts` smí přepsat `max` (strop v rad), `pitch` a `fade`. V `render()` se po
  `mixer.update()` přičte rotace a po vykreslení se kosti vrátí na hodnotu z klipu.
  Rotace se počítá ve světě (kolem osy „nahoru“ tvora, směr k divákovi = +Z) a do
  lokálního prostoru kosti se převádí přes světovou rotaci rodiče, takže nezáleží na
  orientaci os kostí v modelu. Rozdělení 40 % krk / 60 % hlava, mírný náklon dolů
  (0,12 rad při plném natočení) kolem boku už natočené hlavy. Výchozí strop 35°
  (`max: 0.61`), prolnutí 0,6 s.
- `web/scene.js`: `lookAround(a)` v `rest()`. Stojící chodec (pauza, `mix ≥ 0.99`, bez
  zábavy, neotáčí se) si jednou za zastavení hodí kostkou podle
  `motions.walk.look.chance` a na `hold` sekund se podívá. Při rozchodu, otočce nebo
  zábavě se hlava vrací. Zábava (lehnutí/skok) nezačne, dokud se tvor dívá. Zastávka,
  která za méně než `hold[0]` končí, pohled nespustí (bylo by z toho cuknutí). Úlovek od
  dětí (ne-silent příchod) se podívá vždy, když poprvé zastaví. `where()` vrací
  i příznak `looking`.
- Ladicí vstup `DinoScene.debugLook(i, deg)` zastaví tvora i a natočí mu hlavu na
  pevný úhel. `debugLook(i, null)` ho zase pustí.
- `scenes/cretaceous/render.js`:
  `motions.walk.look = { chance: 0.5, hold: [1.5, 3.5], max: 0.61, fade: 0.6 }` a popis
  v hlavičce. Noční scéna data přebírá.

## Měření

**gait_report** (izolovaný server :8131, 60 s), prokluz před → po:

| druh | před | po |
|---|---|---|
| trex3d | 1,5 % | 1,5 % |
| velociraptor3d | 1,5 % | 1,3 % |
| triceratops3d | 1,4 % | 1,6 % |
| stegosaurus3d | 1,4 % | 1,6 % |
| parasaurolophus3d | 1,5 % | 1,5 % |
| apatosaurus3d | 1,4 % | 1,3 % |

Všechny druhy vyšly OK, rozdíly jsou šum mezi běhy. Pohled sahá jen na kosti krku
a hlavy po výpočtu kroku, chodidla neovlivňuje. Výstupy jsou v `tmp/gait_before.txt`
a `tmp/gait_after.txt`.

**Přirozené chování** (`tmp/look_watch.py`, 75 s, nový úlovek + krmení,
`tmp/look_watch.txt`): proběhlo 17 pohledů. Nový velociraptor se podíval hned při
prvním zastavení (v 6,2 s) a pak ještě dvakrát. Konzole byla bez chyb ve všech
bězích.

`python -m pytest -q`: 218 passed.

## Screenshoty (`tmp/`)

Textura je syntetická fotka listu nahraná přes `/api/upload`.

- `look_sheet.png` a `look_head_sheet.png`: T-rex, velociraptor a triceratops na
  0/20/35/50°, řídká kresba (`strokes=40`, pokrytí ~16 %). První je celé tělo, druhý
  výřez hlavy při 2× rozlišení.
- `dense_sheet.png` a `dense_head_sheet.png`: totéž na 0/20/25/35° s hustou kresbou
  (`strokes=160`, pokrytí ~36 %), na které je rozmazání nejlépe vidět.
- Jednotlivé snímky: `look_[head_]<druh>_<úhel>.png` a `dense_[head_]<druh>_<úhel>.png`.
- `natural_new_1.png`, `natural_new_2.png`: nový úlovek se v běžném provozu dívá
  na děti.

Co je na nich vidět:
- Krk nikde nevypadá zlomený. Ohyb se rozloží mezi krk a hlavu a hlava se natáčí
  přirozeně, i na 50°.
- 20°: bez problému u všech tří druhů.
- 35°: hlava je zřetelně otočená k divákovi a obličej je čitelný. Na temeni čenichu
  a na čele se ale přidávají **vodorovné pruhy** (protažené tahy z bokorysu). Nejvíc
  je to vidět u velociraptora s hustou kresbou. Pruhy na jeho čenichu jsou ovšem
  vidět **už na 0°**. Způsobuje je natočení těla o 30° (`turn: 0.524`), pohled
  hlavou je jen zvětšuje. U T-rexe se rozšíří světlá plocha čela, u triceratopse
  límec drží a kresba čenichu se trochu protáhne.
- 50° (jen pro srovnání): čelo a čenich už jsou viditelně šmouha. Strop 35° má tedy
  smysl.

## Verdikt

**ANO, s výhradou.** Funkce dělá, co má: hlava i krk se natáčejí plynule, tělo zůstává
v profilu, scéna je bez chyb a `gait_report` se nezměnil. Kritérium „bez šmouhy na
čele“ spolehlivě platí do 20–25°. Na 35° se u husté kresby přidají protažené pruhy na
temeni čenichu. Šmouha to ještě není, ale je to hranice. Výchozí strop jsem nechal na
35°, jak říká plán. Pokud Pavel na televizi uzná pruhy za rušivé, stačí v `render.js`
nastavit `look.max: 0.44` (25°).

## Otevřené problémy

- Nový úlovek se dívá „při prvním zastavení“ a to bývá často ve frontě u levého okraje,
  kde je napůl mimo obraz (`natural_new_1.png`). Lepší by bylo krátké „pozdravné“
  zastavení, až bude celý na scéně. To je ale nová zastávka, patří spíš do úkolu 4
  (plánovač).
- V kolizní frontě není konec stání předem známý. Pohled tam občas skončí po 0,3 s
  a projeví se jen jako náznak pootočení.
- Letci a plavci nezastavují, takže se nedívají. Kód pro `Main1` u ryb je připravený,
  ale nevyzkoušený.
- Vyhodnocení rozmazání je zatím jen od oka z výřezů, číselná metrika nebyla.
