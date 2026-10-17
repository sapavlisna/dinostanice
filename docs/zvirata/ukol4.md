# Úkol 4 — Plánovač činností (A1)

**Verdikt: ano.** Scéna běžela 10 minut (zrychleně ×3, tedy 30 minut scénického
času) a k tomu 3 minuty v reálném čase. Žádné zvíře se nezaseklo, v konzoli nebyla
žádná chyba a `gait_report` drží prokluz pod 3 % u všech dinosaurů. Testy jsou
zelené: pytest 249 a Node 18. Jedna výhrada se týká lesa: pejsek (shiba) má prokluz
na hraně 2,6–3,1 % i při čisté chůzi. Takhle ho naměřil už úkol 2, není to
způsobené plánovačem (podrobnosti dole).

## Jak to funguje

Příznaky `pause`/`fun` jsou pryč. Každý chodec má **plánovač**
(`web/scenelogic.js`). Je to čistý ES modul bez DOM a three.js. `scene.js` ho volá
každý snímek a provádí příkazy, které plánovač vrátí: přehraj klip, pusť klip
pozpátku, otoč hlavu.

- Zvíře **většinou jde**. Po `walk.dur` sekundách chůze (14–30 s) si podle vah vybere
  další činnost. Jít dál má samo váhu 8, takže zhruba v polovině případů zvíře jde
  dál.
- **Zastavení má důvod.** Zvíře se podívá na děti, rozhlédne se, sedne si nebo si
  lehne (to až po delší chůzi, `after` 40/70 s) a z lehu může usnout. Dál může
  vyskočit, dupnout si (Attack jako hra), krátce si zaběhnout (Run) nebo se popást
  (Eating, jen v lese).
- **Pozdrav:** nový úlovek od dětí se jednou zastaví a podívá na děti. Stane se to
  až ve chvíli, kdy je celý v obraze (`inView`: celé tělo mezi 4 % a 96 % šířky),
  ne ve frontě u okraje. Tím se uzavírá otevřený problém z úkolu 1.
- **Vnější důvody stát zůstaly:** kolizní fronta, zastávka trasy a jídlo. Plánovač do
  nich jen vybere, co zvíře na místě dělá:
  - ve frontě nejdřív stojí a každých 3–7 s si něco vybere na místě; sednout nebo
    lehnout si smí až po 10 s čekání (`wait.bored`),
  - na zastávce trasy jen to, co se vejde do `dwell`,
  - u jídla `eat`.
- **Nikdo nezamrzne v půlce kroku.** Bez role `stand` (klip Idle) plánovač nenabídne
  nic, co zvíře zastaví. Takový chodec se ve frontě otočí místo zastavení a otáčí se
  v chůzi. Letci a plavci nemají `rest`, takže se nezastaví nikdy.

Druhy činností jsou v kódu (`KIND`), protože určují, jak se činnost odehraje:

| druh | činnosti | průběh |
|---|---|---|
| move | walk, run | jde; run prolne chůzi do klipu Run (0,5 s) |
| still | stand, look, eat, greet | stojí v Idle; look/greet otočí krk a hlavu (`Scene3D.look`); eat hraje Eating, má-li ho druh |
| clip | lookaround, jump, play | klip od začátku, dohraje se, pak zpět do stání |
| pose | sit, lie | klip jednou dolů a podržet (`playClamped`); vstávání je týž klip pozpátku (timeScale −1) |

Fáze póz: `stop` (mix → 1) → `down` → `hold` → [jen lie: `sleepIn` → `sleep` →
`sleepOut`] → `up` → `out` → `done`. Spánek existuje **jen z lehu**. Do Sleep a zpět se
prolíná 0,8 s, protože konec LieDown není začátek Sleep (poznámka z úkolu 3). Spící
zvíře má nad sebou malé „Zzz“ (2D ve fx vrstvě, jako jmenovky).

Přerušení (odchod, jídlo) proběhne podle stavu zvířete:
- stojící zvíře rovnou pustí,
- ležící nebo spící nejdřív vstane,
- rozehraný klip se dohraje.

Kdo sedí, když přiletí jídlo, se k němu otočí, až když vstane. Otočka ze setkání na
dráze se nikdy nevybere u zvířete v klipu nebo v póze.

Pózy uvnitř stání se prolínají vlastními váhami (`blendToward`, normalizované na
součet 1). `mix` dál krátí tempo i posun stejným dílem, takže chodidla drží.

**Běh:** `scene3d.js` teď měří krok i u klipu Run (`gaits: ['run']`,
`walkedBreak`, `breakNatural`). Posun při prolínání je
`(1−runK)·chůze + runK·běh`, každá složka po vlastní křivce kroku. Tempo klipu Run se
volí tak, aby běh byl `run.speed`× rychlejší než chůze, ale drží se v mezích
0,5–1,4. `gait_report` snímky záběhu vynechává, protože mají jiný cíl tempa. Prokluz
běhu jsem změřil zvlášť (viz níže).

## Formát dat

`scenes/<scéna>/render.js`, `motions.walk.activities` (popis je v hlavičce
`scenes/cretaceous/render.js`):

```js
activities: {
  walk: { weight: 8, dur: [14, 30] },          // dur = chůze mezi rozhodnutími
  stand: { weight: 1, dur: [2, 4] },
  look: { weight: 3, dur: [2, 3.5] },           // pohled k dětem (strop v motions.walk.look)
  lookaround: { weight: 2 },                    // délka = klip
  sit: { weight: 1.2, dur: [5, 9], after: 40 }, // after = s od posledního sedu/lehu
  lie: { weight: 0.8, dur: [5, 9], after: 70 },
  sleep: { chance: 0.5, dur: [8, 15], fade: 0.8 },
  jump: { weight: 0.4 },
  play: { weight: 0.4 },
  run: { weight: 0.8, dur: [1.5, 3], speed: 1.8, waitWeight: 0 },
  eat: { weight: 1, dur: [4, 8] },              // u jídla vždy, pastva jen s klipem Eating
  greet: { dur: [2.5, 4] },
  wait: { every: [3, 7], bored: 10 },           // čekání ve frontě
}
```

Druh nabídku přepíše ve `scene.json`:
`{"key": "trex3d", ..., "activities": {"sit": {"weight": 0}, "run": {"speed": 2.5}}}`.
Slučuje se po činnostech. Pole se propíše do `catalogue3d.json` (`Model3D.activities`).

**Role klipů** (`dinostanice/creatures3d.py`, `CLIP_FOR_DEFAULT["walk"]`):

- výchozí mapování: `move` Walk, `stand` Idle, `jump` Jump, `run` Run,
  `look` LookAround, `sit` Sit, `lie` LieDown, `sleep` Sleep, `play` Attack,
  `eat` Eating;
- povinná je jen `move`. Roli bez klipu export vypustí (`resolve_roles`) a scéna
  činnost nenabídne;
- `lie` bez LieDown padá na Death (a pak se nenabízí spánek);
- `clip_for: {"lie": null}` roli vypne úplně;
- `tools/scena.py` hlásí chybějící volitelné role jako varování (`!`), ne jako chybu.
  Import nově odhadne i Gallop, Eating, Sit… (`ROLE_GUESS`) a chybějící volitelné
  role chodce nepřesměruje na Walk.

## Klipy

`tools/blender_clips.py` jsem pustil na všech šest křídových chodců. Mapy kostí:

- `trex.json` pro trexe, velociraptora a parasaurolopha,
- `triceratops.json` pro triceratopse,
- nové `stegosaurus.json` a `apatosaurus.json`, kopie mapy triceratopse s `tweaks`
  pro sed. Apatosaurovi v sedu vystřelil krk mimo obraz (pitch 32 → 14, krk −16),
  stegosaurovi jsem zvedl hlavu.

Výstupem jsou `data/models_src/<model>_clips.glb`. `clips_preview.py` potvrdil, že
původní klipy jsou bajtově beze změny a nové začínají v Idle (0,00 %). Sleep proti
Idle 14–25 %, proto je tam to prolnutí.

`scenes/cretaceous/scene.json` ukazuje na `_clips` verze. Přeexportoval jsem jen šest
dinosaurů (`model_export3d.py <klíče>`). UV a póza Walk jsou v nových
`data/models3d/*.glb` číselně stejné jako dřív (max. rozdíl 0,0).

- **Textury ukázky jsem vrátil z gitu.** `model_paint_demo` je při exportu
  nedeterministická (asi 4 % pixelů se liší i se stejným seedem) a s klipy nesouvisí.
- `data/templates` ani `data/shapes3d` se nezměnily (`git diff zvirata` je prázdný).
- `model_sheet.py` jsem nespouštěl.

**Les** (po sloučení úkolu 2), `clip_for` ve `scenes/les/scene.json`:

- `run` Gallop, `look` Idle_2, `eat` Eating,
- `play`: Attack u lišky, pejska a vlka; Attack_Headbutt u alpaky, srnky, koně
  a jelena,
- `lie: null`, takže lehnutí přes Death se nenabízí (srnka na boku vypadá jako
  mrtvá). Sit a Sleep v balíčku nejsou, takže odpadnou samy.

Katalog jsem pro les přepsal jen indexem (`--index-only`), GLB lesních zvířat se
nezměnila. `jump` zůstal na „Jump“, což je u těchto modelů Gallop_Jump. Ve stoje
vypadá použitelně (skok vpřed a dopad), ale Jump_toIdle by možná seděl líp.

## Testy

- `tests/js/scenelogic.test.js` (18 testů, `node --test "tests/js/*.test.js"`, Node
  24): ověřuje tohle:
  - nabídka podle klipů; bez Idle nic, co zastaví; look jen s kostí hlavy,
  - přepis z druhu,
  - spánek jen z lehu,
  - sit/lie až po delší chůzi,
  - sekvence sednout → držet → vstát pozpátku,
  - leh → spánek s prolnutím 0,8 → probuzení → vstát,
  - přerušení spícího (nejdřív vstane, mix drží 1),
  - fronta (stojí, vybírá na místě, nikdy neběží, po uvolnění jde),
  - pozdrav přesně jednou a až v obraze,
  - zastávka trasy vybere jen to, co se vejde,
  - 10 simulovaných minut (převážně chůze, každá činnost skončí do 40 s).
- **Povýšený `tmp/test_zastaveni.py`:**
  - plynulé zastavení: tempo monotónně klesá, trvá ≥ 0,6 s,
  - stojící chodec se neposune ani o kousek,
  - po činnosti se zase rozejde,
  - letec (bez klipu stání) nezastaví ani při 20 000 krocích s frontami a zastávkami.
- `tests/test_scenelogic_js.py` pouští Node sadu z pytestu (bez Node se přeskočí).
  Příkaz je i v README.

## Měření (izolovaný server :8134, swiftshader)

**gait_report, prokluz** (60 s):

| druh | před | po (1. běh) | po (2. běh) |
|---|---|---|---|
| trex3d | 1,9 % | 1,4 % | 1,6 % |
| velociraptor3d | 1,3 % | 1,2 % | 1,3 % |
| triceratops3d | 2,2 % | 1,4 % | 1,9 % |
| stegosaurus3d | 1,3 % | 1,2 % | 1,2 % |
| parasaurolophus3d | 1,7 % | 1,7 % | 1,4 % |
| apatosaurus3d | 1,4 % | 1,9 % | 2,0 % |

Les (`?scene=les`), tři běhy po změně proti číslům z úkolu 2:

| druh | úkol 2 | po |
|---|---|---|
| alpaca | 1,6 % | 2,7 / 1,5 / 1,7 % |
| deer | 1,3 % | 1,6 / 1,3 / 1,1 % |
| fox | 2,7 % | 2,7 / 2,8 / 2,6 % |
| horse | 1,5 % | 1,8 / 2,1 / 1,6 % |
| shiba_inu | 2,7 % | 2,7 / **3,1** / 2,8 % |
| stag | 1,3 % | 1,0 / 1,1 / 1,1 % |
| wolf | 2,7 % | 2,8 / 2,5 / 2,4 % |

Shiba ve 2. běhu přelezla hranici. Kontrolní běh, který počítá jen snímky čisté chůze
(timeScale ≥ 99,9 % tempa, bez prolínání), dal 2,9 %. Je to tedy vlastnost její
chůze, stejně jako ji našel úkol 2. Plánovač na krok nesahá.

**Prokluz během běhu** (`tmp/run_slip.py`, záběh vynucený u všech, 900 snímků):

- dinosauři 0,4–1,2 %,
- les 0,1–2,0 %.

Rychlost běhu ale vychází **2–3,9× chůze**, ne 1,8×. Tempo Run padá na spodní mez 0,5,
protože klipy Run jsou rychlé (viz otevřené).

**Dlouhé běhy** (`tmp/long_run.py`). Hlídač zaseknutí běží v každém snímku přímo ve
stránce: chodec s mix < 0,5, který se 3 scénické sekundy neposunul. Do běhů přicházely
úlovky z vybarvených listů a dvakrát krmení.

| běh | scénický čas | zaseknutí | chyby | podíl chůze | spuštěné činnosti |
|---|---|---|---|---|---|
| reálný čas 3 min, přeplněná scéna (16 úlovků) | 179 s | 0 | 0 | 0,68 | stand 263, look 25, lookaround 22, eat 9, play 4, run 3, sit 2, greet 2 |
| 10 min ×3 | 1787 s | 0 | 0 | — | stand 525, look 147, lookaround 98, run 46, jump 33, play 22, sit 19, lie 8, eat 8, greet 4, sleep 3 |
| 4 min ×3, běžná scéna (6 ukázek + 2 úlovky) | 720 s | 0 | 0 | **0,80** | look 27, stand 34, run 10, sit 9, lookaround 9, play 6, jump 4, lie 2, sleep 2, greet 2, eat 1 |
| les 4 min ×3 | 720 s | 0 | 0 | 0,75 | stand 107, look 51, eat 34, lookaround 19, play 10, run 7, jump 6, greet 3 |

„stand“ jsou skoro všechno krátká čekání v kolizní frontě (fronta se uvolní po 0,8 s
a zastaví znovu). Totéž se dělo i dřív. První verze měřiče vzorkovala `where()`
jednou za sekundu a při zrychlení hlásila falešná podezření. Zvíře stálo, za zbytek
sekundy ušlo méně než 0,001 a zaokrouhlené x vyšlo stejně. Hlídač v každém snímku
pak ve stejných scénách nenašel nic.

## Screenshoty (`tmp/shots/`)

Textura je syntetická fotka listu (`H.sheet(key, seed=3, strokes=40)`
→ `synth.photograph` → `/api/upload`).

- `sheet_trex3d.png`, `sheet_triceratops3d.png`, `sheet_velociraptor3d.png`:
  walk, look, lookaround, sit, lie, jump, play, run vedle sebe.
- `sheet_les_deer.png`, `sheet_les_fox.png`, `sheet_les_horse.png`: walk, look (Idle
  + hlava), lookaround (Idle_2), eat (Eating), jump, play, run (Gallop), stand.
- Jednotlivé snímky `cretaceous_<druh>_<činnost>.png` a `les_<druh>_<činnost>.png`,
  včetně `*_sleep.png` (spánek se „Zzz“), `*_greet.png`, `*_eat.png`, `*_stand.png`.

Co je vidět:
- Sed, leh a spánek jsou z boku jednoznačné a kresba drží.
- Pohled k dětem je z profilu nenápadný (strop 35° z úkolu 1).
- Lesní pastva a cval vypadají přirozeně.
- „Zzz“ je malé a sedí nad hlavou.

## Otevřené problémy

- **Běh je rychlejší, než říkají data.** Klipy Run (dinosauři) i Gallop (les) mají
  nativní tempo 4–7× chůze. S dolní mezí tempa 0,5 vychází záběh 2–3,9× rychlejší
  (stegosaurus a apatosaurus nejvíc). Zpomalit víc by vypadalo jako zpomalený film.
  Lepší cesta je nižší `run.weight` nebo `run.speed` u těžkých druhů, případně
  `activities: {"run": {"weight": 0}}` ve scene.json.
- **Kolizní fronta** v přeplněné scéně (16+ úlovků) rozdělí čekání na desítky krátkých
  zastavení a podíl chůze klesne na 0,68. Řešením je dráhová logika, ne plánovač.
- Čekání ve frontě smí vybrat činnost i za okrajem obrazovky. Neškodí to, jen je to
  zbytečné.
- Shiba (a psovití obecně) má prokluz na hraně 3 %. Je to z úkolu 2 a týká se chůze,
  ne plánovače.
- `jump` v lese hraje Gallop_Jump. Jump_toIdle jsem nezkoušel.
- Textury ukázky z `model_paint_demo` nejsou deterministické. Proto jsem je nechal
  z gitu, export by je zbytečně změnil.
