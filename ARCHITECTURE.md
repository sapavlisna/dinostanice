# DinoStanice — architektura

Domácí obdoba exponátu z Haus der Natur v Salzburgu. Dítě vybarví předtištěnou
šablonu, vyfotí ji mobilem a jeho dinosaurus se objeví v živé křídové krajině
na televizi, kde chodí / plave / letí mezi ostatními.

## Tok dat

    šablona (SVG, tisk)  ->  dítě vybarví  ->  foto mobilem
      -> POST /api/upload -> capture.detect_sheet()  (ArUco -> homografie -> srovnaný list)
      -> rig.build_rig()  (narovnané tělo + rozřezané končetiny)
      -> data/catch/<id>/{rig.json, body.png, limb_*.png}
      -> WebSocket broadcast -> scéna na TV přidá nového tvora

## Klíčová myšlenka

Obrys šablony není hádaný z fotky — je předem známý. Z jedné definice tvora
(obrys + páteřní křivka + profil tloušťky + končetiny) vzniká současně
**tisknutelný obrys**, **maska pro ořez textury** i **animační rig**. Proto
textura vždy přesně sedne na kostru, která ji rozhýbe.

Zvířata pocházejí z traceovaných CC0 siluet, takže obrys je daný bitmapou a
páteř s končetinami se z něj odvozují (`silhouette.py`). Tvar tedy může být
libovolný, ne jen trubka — proto se narovnaný pás ořezává **skutečnou maskou
trupu**, ne výpočtem z profilu: jinak by stegosaurovi zmizely ploténky
a triceratopsovi límec, o kterých profil (vepsaný kruh) nic neví.

Tělo se při stavbě rigu **narovná podél páteře** do rovného pásu (`body.png`):
osa x = vzdálenost podél páteře, osa y = kolmý offset. Renderer pak ohýbá
rovný pás podél libovolné animované křivky obyčejnými 2D transformacemi.

## Hotové moduly (needitovat bez důvodu)

- `dinostanice/shapes.py` — Creature/Limb, páteř, offset obrysu, klouby
- `dinostanice/creatures.py` — katalog 8 tvorů, načítaný z `data/shapes/*.json`
- `dinostanice/silhouette.py` — z bitmapy CC0 siluety odvodí obrys, páteř, profil
  a končetiny s klouby (skeletonizace + nejdelší cesta + segmentace podle větví)
- `dinostanice/raster.py` — maska a sjednocený obrys (fillPoly + findContours)
- `dinostanice/markers.py` — ArUco DICT_4X4_50, 4 rohy na list, ID = 4*index+roh
- `dinostanice/template.py` — šablona jako SVG (tisk) i raster (náhled/testy)
- `dinostanice/capture.py` — detekce listu, homografie, srovnání osvětlení, ořez textury.
  `detect_sheet()` vyžaduje **aspoň dvě značky** (`MIN_MARKERS`) a kontroluje, jak
  homografie sedí: jedna značka ji určí přesně, ale extrapolace přes celý list byla
  naměřena desítky milimetrů vedle — a tiše. `sheet_texture()` vrací kresbu v
  souřadnicích celého listu (to potřebuje `rig.py`), `extract_texture()` ořezanou.
- `dinostanice/synth.py` — syntetické vybarvení + simulovaná fotka (vývoj bez tiskárny)
- `dinostanice/rig.py` — narovnání těla, řezání končetin, zápis rig.json;
  `sheet_for_texture()` vyrábí `sheet.png` — celou kresbu jako neprůhledný obrázek
  s barvami rozlitými pár mm za obrys, protože 3D síť stojí na plném obrysu, kdežto
  ořez textury je o `TRIM_MM` uvnitř
- `dinostanice/inflate.py` — nafouknutí ploché masky do zaobleného 3D tělesa
- `dinostanice/model3d.py` — složení modelu z nafouknutých dílů (trup + končetiny)
- `dinostanice/quality.py` — hodnocení kvality fotky s českými radami pro fotícího
- `dinostanice/store.py` — úlovky v `data/catch/<id>/`

## 3D modely

Kresba je z boku, hloubka v ní není — musí se vymyslet. `inflate.py` ji vymýšlí
jako plyšák: pro každý bod se vezme vzdálenost `D` k obrysu a lokální poloměr
`R` (odečtený z mediální osy tvaru), a `z = sqrt(D * (2R - D))` je přesně kruhový
průřez trubky o poloměru `R`. Noha nakreslená 10 mm široká vyjde 10 mm hluboká,
stegosaurova ploténka zůstane plochá, a nic se neladí per tvor. Pole `R` je
Voronoi rozklad podle mediální osy, tedy nespojité — `_smooth_inside()` ho
rozmaže maskovaným blurem, jinak je zvíře pokryté slabými hrboly a fasetami.

**UV jsou pozice na listu.** Model si drží souřadnice v milimetrech na A4, takže
`u = x/297`, `v = 1 - y/210`. Z boku je model přesně ta kresba (IoU 0,98 proti
šabloně, hlídá test), otočením se stejné barvy přetáhnou přes hřbet.

### Jedna spojitá kůže, ne slepenec dílů

Celé zvíře se nafukuje **jako jeden kus**. První pokus nafukoval trup a každou
končetinu zvlášť a pak je rozestrčil do hloubky — jenže pak se trup musel
roztáhnout zpátky do nohových jamek, aby díly nedržely od sebe, a to roztažení
pověsilo pod břicho čtyři krátké pahýly. Zvíře vypadalo, že má osm nohou.

Hloubku ale nohy potřebují: na bokorysu jsou bližší a vzdálenější noha nakreslené
vedle sebe, takže naplacato je model lepenkový výřez. Každá noha proto dostane
**váhové pole** — 1 uvnitř nohy, plynule k 0 u kyčle (`BLEND_MM`) — a v hloubce
se posune podle té váhy (`LIMB_SPREAD`). Kůže se přes rameno plynule zkosí místo
aby se rozpadla. Tytéž váhy pohánějí chůzi: vrchol se otáčí kolem kyčle o váhu
krát úhel kroku, takže noha se v kyčli ohne bez jakékoli kostry.

U tvora kresleného **zhora** (pteranodon) se nic nerozestrkává — levé a pravé
křídlo už jsou od sebe v kresbě a osa hloubky míří nahoru.

### Které části jsou končetiny

Neurčuje to segmentace podle větví skeletonu (ta občas z nohy udělá 7mm pahýl),
ale silueta: `limb_regions()` bere všechno, co přesahuje **trubku z profilu
tloušťky**. Dvě nohy z páru drží pohromadě přes pás břicha mezi nimi, takže se
ten shluk rozdělí podle nejbližší deklarované končetiny; a každý podíl se omezí
na kus, který se dotýká vlastního polygonu té končetiny — díky tomu se
stegosaurovy ploténky, které taky přesahují profil, ale nikdy se nehýbou,
nepřihlásí jako nohy. Deklarovaná končetina už dodá jen stranu těla a kyčel.

Vypéct: `python tools/make_model3d.py [klíč...]` → `data/models3d/<key>.json`
(jeden díl: `pos`/`nrm`/`uv`/`idx` + `spine_t`, `limb_id`, `limb_w`, `limbs`).
Prohlížeč: `/3d` (`web/model3d.html` + `model3d.js`, three.js ve `web/vendor/`).
Snímky pro posouzení bez televize: `python tools/shot3d.py [--catch id] [--flat]`.

Kde metoda **nefunguje**: plachetnice. Nafukování předpokládá měkké oblé tělo,
takže z trupu a plachet udělá sedací vak. Zvířata ano, vyrobené předměty ne.

## Obrácený postup: předloha z 3D modelu (zkouška na T-Rexovi)

Souběžná větev, která otáčí směr toku. Místo aby se hloubka dopočítávala
z ploché siluety, vychází se z hotového **rigovaného 3D modelu** a předloha
z něj vypadne jako vedlejší produkt:

    trex.glb (CC0, 6 animací) -> póza (skinning) -> ortogonální bokorys
      -> obrys + vnitřní linky -> předloha k tisku (SVG + ArUco)
      -> dítě vybarví -> foto -> textura planárně na model (UV = pozice na listu)
      -> model se animuje vlastní kostrou

Co tím padá: nafukování `inflate.py`, odhad páteře ze skeletonu, dogenerování
druhého páru nohou, ohýbání narovnaného pásu. Zvíře má skutečný objem a
skutečnou chůzi od autora modelu.

Klíčové je, že **UV jsou pozice na listu v pozici předlohy**. Předloha vzniká
projekcí modelu na list, takže obrácená projekce sedne přesně; textura pak
jede s modelem do libovolné pózy a úhlu.

- `dinostanice/gltf.py` — vlastní GLB loader a linear blend skinning (numpy,
  bez závislostí). `Model.posed(anim, t)` vrátí vrcholy a normály v pozici.
- `dinostanice/orthoview.py` — z-buffer rasterizace do ortogonálního pohledu.
  `View.sample()` interpoluje libovolný atribut vrcholů (kvůli UV),
  `outline_edges()` rozloží kresbu na obrys, hloubkové skoky a hranice materiálů.
- `dinostanice/modelsheet.py` — z pohledu udělá polygony v milimetrech na listu
  a `Placement`, což je právě ten převod mm ↔ souřadnice modelu. Oblasti
  k vybarvení nejsou hranové pixely, ale souvislé plochy, které nerozděluje
  ani hranice materiálu, ani skok v hloubce.
- `tools/model_sheet.py` — vyrobí `data/templates/trex3d.svg`, náhled a
  `data/shapes3d/trex3d.json`.
- `tools/model_paint_demo.py` — uzavře kruh bez tiskárny: syntetické vybarvení,
  textura, snímky z různých úhlů a fází animace.
- `dinostanice/glbexport.py` — zapíše kopii GLB s doplněným `TEXCOORD_0`.
  Model z internetu UV nemá; tady jsou to pozice vrcholů na listu.
- `tools/model_export3d.py` → `data/models3d/trex3d.glb` + ukázková textura.
- `web/dino3d.js`, stránka `/dino3d` — three.js `GLTFLoader` + `AnimationMixer`.
  Kostru i animace nese GLB, prohlížeč jen hodí na model vybarvenou fotku
  (`texture.flipY = false`, protože glTF má počátek UV vlevo nahoře).

- `dinostanice/creatures3d.py` — katalog osmi tvorů; `axes`/`flip` u každého
  volí projekci (chodec bokorys, letec shora s rozpětím křídel po šířce listu). Indexy značek 8-13
  navazují na osm tvorů staré větve, aby už vytištěné listy platily dál. Proto
  taky `markers.py` přešel na `DICT_4X4_100`: je to nadmnožina `DICT_4X4_50`
  (prvních 50 kódů je shodných), takže se rozšířil prostor, ale nic se nepřepsalo.

Póza předlohy se hledá sama (`best_pose`): projde se cyklus chůze a vezme se
okamžik s nejlepším vyplněním listu **po fitu**, ne v pixelech — natažený
sauropod má velkou siluetu, ale na papíře z něj zbude tenký pruh. Pouštět do
výběru i ostatní animace se neosvědčilo: `Attack` sice list vyplní nejlíp, ale
tvora překroutí (sauropodovi přehodí ocas přes tělo, stegosaurovi schová
ploténky). Vyplnění není totéž co čitelnost.

### Ptakoještěr: kostra dopsaná ke geometrii

Animovaný pterosaur pod otevřenou licencí neexistuje, statický ano — proto mu
`tools/make_pteranodon.py` kostru dopisuje. Postup, který by šel použít na
jakýkoli souměrný model bez rigu:

1. **Rozdělení scény** — zdroj obsahuje tři pterosaury rozsekané na 56 dílů.
   Spojují se překrývající se obálky primitiv, ne jejich těžiště: křídlo má
   těžiště daleko od těla, takže shlukování podle středů je slepí špatně.
2. **Narovnání** — osy z PCA nestačí, tvor je zachycený uprostřed mávnutí
   a rozptyl proto míří šikmo. Hledá se rovina souměrnosti: pro směry na
   polokouli se spočítá překryv voxelové masky s jejím zrcadlem a vezme se
   maximum. Mávnutí souměrnost neporuší, naklonění os ano.
3. **Zrcadlení poloviny** — předloha se kreslí shora, takže musí být souměrná,
   jinak by dítě dostalo tvora s jedním křídlem nahoře a druhým dole.
4. **Kostra z geometrie** — trup, hlava a dvě dvoudílná křídla; váhy se
   přelévají podle vzdálenosti od osy souměrnosti, součet je vždy 1. Který
   konec je hlava, rozhoduje **objem obálky**, ne počet vrcholů — nohy
   s roztaženými prsty mají 10 642 vrcholů proti 6 816 hlavovým, ale objem
   0,09 proti 1,02.
5. **Klip letu** — křídla rotují kolem osy letu, špička se za ramenem opožďuje
   o `LAG` cyklu, takže mávnutí probíhá vlnou a ne jako prkno.

`glbexport.write_skinned()` z toho složí GLB s kostrou, vahami a animací.

### Z fotky zpátky na model

`capture.py` je společné oběma větvím — ArUco, homografie, srovnání listu.
`known_indices()` mu říká, které indexy značek existují; starší tvorové mají
0-7, ti z modelů 8 a výš. Podle indexu se pipeline rozvětví (`server.process`):

- starý tvor → `rig.build_rig()`, jak to bylo vždycky,
- tvor z modelu → `capture3d.save_catch()`: žádný rig se nestaví, model kostru
  má. Ze srovnaného listu se udělá textura (`build_texture`) a uloží
  `texture.png` + `model.json`.

Textura projde týmž `to_texture()` jako ukázkové: osvětlení se narovná jen
uvnitř kresby, tištěné linky se zaretušují okolní barvou a barva se rozlije
kousek za obrys. Registrace je zadarmo — předloha vznikla promítnutím modelu na
list, takže UV modelu **jsou** souřadnice na papíře.

`meta.json` nese `kind`: `rig` nebo `model`. Scéna na televizi umí obojí —
`rig` kreslí jako 2D pásy do plátna s krajinou, `model` posílá do WebGL vrstvy
nad ní (viz níže). Zblízka a s ovládáním se na tvora dá koukat v `/dino3d`,
kde je ve skupině **Úlovky** vedle katalogu.

Klipy se hledají podle holého jména (`Model.clip`), ne skládáním z prefixu:
FBX export jim dává jméno armatury, které se model od modelu liší
(`Armature|TRex_Walk` proti `CharacterArmature|Fast_Flying`).

Oko se dokresluje, modely ho nemají — nese ho barva materiálu, ne geometrie.
`auto_eye()` ho položí do obálky vrcholů, které visí na jointu `Head`, a ověří,
že bod padl dovnitř kresby; když ne, posouvá ho k těžišti hlavy.

Letec se kreslí shora a oko mu neleží před tělem, ale na ose souměrnosti
(`eye_bias={"forward": 0.5}`) — jinak `auto_eye` míří do strany od hlavy,
tedy mimo kresbu.

Kde to drhne: černý obrys z papíru se při otočení protahuje přes hřbet, takže
se z textury musí vymazat (`to_texture()` ho zaretušuje okolní barvou).
Apatosaurus je na list příliš protáhlý (poměr 4:1 proti kreslicí ploše 1,6:1),
takže z něj zbývá tenký pruh — jiná póza to nespraví, jen ho zamotá.

## Formát rig.json

```json
{ "name": "...", "creature": "sauropod", "label": "Brachiosaurus",
  "motion": "walk|swim|fly|sail", "view": "side|top", "ppm": 5.0,
  "body": {
    "image": "body.png",
    "length_mm": 269.6,        // délka páteře včetně přesahu za zaoblené konce
    "half_mm": 28.0,           // poloviční výška pásu; obrázek je samples x round(2*half_mm*ppm)
    "samples": 1327,           // šířka pásu v px == počet vzorků podél páteře
    "radius_mm": [ ... ],      // poloměr v každém vzorku (samples hodnot)
    "spine_mm": [[x,y], ...]   // páteř na listu (samples bodů) — PLNOHODNOTNÁ geometrie
  },
  "limbs": [ { "name": "front", "anchor": 0.55, "side": 0, "phase": 0.0, "segments": [
      { "image": "limb_front_0.png",
        "origin_mm": [x,y],    // levý horní roh výřezu v mm na listu
        "pivot_mm":  [x,y],    // kloub, kolem kterého segment rotuje
        "tip_mm":    [x,y],    // konec segmentu = pivot dalšího segmentu
        "length_mm": 33.0 } ] } ] }
```

Tuhé tělo (loď) má místo `length_mm/half_mm/...` klíč `"rigid": true`
plus `origin_mm` a `size_mm` — kreslí se jako jeden obrázek.

Souřadnice v mm odpovídají listu A4 na šířku (297 x 210). Pixel <-> mm přes `ppm`.

Na co si dát pozor:

- `spine_mm` **není jen referenční** — klidová póza se z ní musí složit tak, že
  vyjde přesně původní křivka. Kdo si tvora narovná do tětivy hlava–ocas, ztratí
  sklon ocasu i krku. Proto je uložená na 3 desetinná místa: vzorky leží 1/ppm mm
  od sebe a hrubší zaokrouhlení zašumí numerickou tečnu mezi sousedy.
- Páteř **přesahuje za oba konce** o poloměr zaoblení, s profilem
  `sqrt(r² - d²)`. Bez toho by čenich a hrot ocasu — což jsou oblouky čepiček,
  ne trubka — v `body.png` vůbec nebyly a renderer je nemá jak dokreslit.
- `anchor` je vyplněný i u končetin s explicitním `outline` (dopočítá se z pivotu).
- `side`: 0 = blízká strana, 1 = vzdálená (kreslí se za tělem).
- Šablona má u čtyřnožce jen dvě nohy; druhý pár si renderer dogeneruje sám
  s fázovým posunem a ztmavením.

## Kontrakty mezi částmi (dodržet!)

### Pozadí (`web/backdrop.js`)
```js
window.Backdrop = {
  draw(ctx, W, H, t),          // vykreslí krajinu; t = čas v sekundách
  drawFront(ctx, W, H, t),     // kapradí a vinětace — patří až PŘED tvory
  sun: {x, y},                 // kde je slunce, v podílu plátna
  zones: {                     // pásma v podílu výšky plátna (0 = nahoře)
    sky:   {y0, y1},           // kde létají letci
    shore: {y0, y1},           // kde chodí suchozemci (popředí)
    shoreFar: {y0, y1},        // pruh písku za lagunou
    water: {y0, y1},           // kde plavou plavci
    surface: {y0, y1}          // hladina pro lodě
  },
  depthScale(yFrac)            // -> násobek velikosti podle hloubky scény
};
```

### Renderer tvora (`web/rigrender.js`)
```js
window.Rig = {
  load(baseUrl)                // -> Promise<RigInstance>, baseUrl = složka s rig.json
};
// RigInstance.draw(ctx, {x, y, scale, flip, t, phase})
// RigInstance.motion, .label, .sizeMm
```

### 3D vrstva scény (`web/scene3d.js`)
```js
Scene3D.init(canvas)                       // -> false, když prohlížeč neumí WebGL
Scene3D.resize(W, H)
Scene3D.spawn({glb, texture, motion, clip, breaks})
                                           // -> handle: .length, .height, .sizePx,
                                           //    .duration, .strideBodies, .breakDur
Scene3D.place(handle, {x, y, scale, face, depth})   // face -1..1, mezi tím se otáčí
Scene3D.speed(handle, timeScale)
Scene3D.blend(handle, name, weight)        // prolnutí zastávky přes chůzi
Scene3D.restart(handle, name)              // skok od začátku
Scene3D.remove(handle)
Scene3D.render(dt)                         // dt bere od scény, ať pohyb a animace
                                           // po zaškubnutí nerozejdou
```
Kamera je **ortografická a nastavená v pixelech obrazovky** (levý horní roh je
počátek, svislá osa jde dolů jako v canvasu). Scéna tak umísťuje tvory ve
stejných souřadnicích, ve kterých kreslí krajinu, a nemusí řešit perspektivu.

Modely koukají na +Z; `place` je natáčí kolem Y podle směru chůze, ne
zrcadlením — zrcadlit by znamenalo obrátit i texturu. Chodec je natočený lehce
k divákovi (0,34 rad), letec víc (0,95 rad) a ještě nakloněný, protože z čistého
profilu jsou z něj jen dvě čárky.

Měřítko se váže na `sizePx` — odmocninu z plochy siluety, ne na délku. Kdyby
všichni měli stejnou délku, apatosaurus (samý krk a ocas) by vedle tyranosaura
vypadal jako ještěrka.

Dvě věci, na kterých se to dá lehce rozbít:

- **Měřítko se počítá z bind pózy** (`measure()`), ne z `Box3.setFromObject()`.
  Ten se u skinovaných meshů ptá na `SkinnedMesh.boundingBox`, který vychází
  z aktuální pózy a už nese transformaci skeletu — ta se pak přiloží ještě
  jednou. Obálka vyjde o dva řády větší a s prohozenými osami. Navíc by tvor
  s každým krokem měnil velikost.
- **Zem je `y = 0` v modelu**, ne spodek obálky. Triceratops má bind pózu, která
  sahá pět jednotek pod počátek, a vznášel by se nad pískem.

### Scéna (`web/scene.js`)
Používá Backdrop, Rig i Scene3D a rozhoduje jen o tom, kdo je kde. Připojí se na
`ws://<host>/ws`, přijímá `{"type":"add","id","url","creature","kind"}` a přidá
tvora do scény. Suchozemci padnou z 35 % na vzdálený břeh (`zones.shoreFar`),
aby scéna měla hloubku. Pro ladění vystavuje `window.DinoScene.where()` — kdo je
kde — a `window.DinoScene.add()`, kterým si `tools/shot_scene.py` doplní tvory
z katalogu.

Scéna se doplňuje z katalogu (`AMBIENT_MIN`), aby televize nesvítila naprázdno,
než něco přinesou děti — ukázkové textury vypadají jako vybarvené, takže je
poznat, o co jde. Jakmile dorazí úlovek, jeden tvor z katalogu ustoupí; po
smazání úlovku se scéna zase doplní. Počet tvorů tak zůstává stálý a úlovky
katalog postupně vytlačí.

Plátna leží ve třech vrstvách: krajina (2D) → tvorové z modelů (WebGL) →
popředí (2D). Bez toho by dinosaurus stál nad kapradím, ne v něm. 2D rigy se
kreslí do spodní vrstvy, takže jsou vždycky za 3D tvory — až starou větev
vymažeme, přestane to platit.

Chodec z 3D modelu nemá rychlost zvolenou, ale spočítanou z animace, aby po
písku neklouzal. Klipy šlapou na místě, takže `Scene3D.spawn` z nich odečte
**délku kroku** (`strideBodies`, v délkách těla na jeden cyklus): noha, která se
v modelu sune dozadu nejrychleji, je ta, co stojí na zemi, a kolik za cyklus
ujede, tolik se musí posunout tvor. Scéna pak jen vybere tempo cyklu blízko
přirozeného tempa druhu (`STRIDE_RATE`, `GAIT_RATE`) a rychlost po scéně z něj
dopočítá — chodidla tak sedí na zemi u každého modelu, ať má krok a cyklus
jakkoli dlouhý. Rozdíly mezi druhy zůstanou: apatosaurus se plouží, drobný
velociraptor si vykračuje.

Hádaná rychlost byla vidět: modely se v délce kroku i délce cyklu liší tak, že
jeden a týž odhad znamenal u tyranosaura o 40 % pomalejší pohyb, než jak šlapal,
a u apatosaura sedmkrát rychlejší. `Scene3D.spawn` navíc **odřízne mrtvý konec
klipu** — velociraptorova chůze má za odkráčeným cyklem půl cyklu nehybné pózy,
takže se uprostřed chůze zastavoval a přesto se posouval dál.

2D rigy si tempo kroku vezou na ujeté dráze samy (`rigrender._travelMm`);
plavcům a letcům scéna posílá `speed`, aby rychlejší mával křídly častěji.

Automat se dá přebít z ladicího panelu (`web/tune.js`, klávesa `d`): u každého
druhu ve scéně jde nastavit `rate` (tempo animace, rychlost jde s ním, ať
chodidla drží) a `speed` (násobek dopočítané rychlosti, tím se sladění naopak
rozladí). `applyGait()` je jediné místo, kde se obojí do tvora dostane, takže
změna platí okamžitě i pro tvory, kteří už ve scéně jsou. Hodnoty drží
`localStorage`.

Aby scéna nebyla přehlídka (všichni pořád vpřed, nikdo nikdy nestojí), chodec
si během chůze dělá **zastávky** — konstanty `REST` v `web/scene.js`:

- **stání** (klip `Idle` z katalogu) na 3–9 s, každých 11–34 s chůze,
- **skok** (klip `Jump`) místo stání s šancí 35 %, na jednu délku klipu,
- **otočka** po stání s šancí 45 %: `face` přejde z −1 na 1, tvor se na místě
  přehoupne čelem k divákovi na druhou stranu a jde zpátky.

Zastávka se **prolíná**, nepřehazuje: obě pózy běží pořád, mění se jen jejich
váhy (`Scene3D.blend`). Nemusí se tak řešit, ve které fázi kroku se tvor
zastavil. Podíl zastavené pózy (`mix`) krátí stejným dílem rychlost po scéně
i tempo animace, takže při zpomalování chodidla drží na zemi zrovna tak jako za
chůze. Dokud se tvor otáčí, `mix` zůstává na jedničce — otáčí se na místě, ne
v pohybu. Prolínaná póza se drží, dokud se nedomixuje; jinak by skákající tvor
cuknul do stojací pózy ve chvíli, kdy skok skončí.

Chodec se navíc `drift`em sune po pásu břehu dopředu a dozadu (podíl vodorovné
rychlosti), na kraji pásu se odrazí. Bez toho jdou všichni po jedné lince zleva
doprava. Hloubka se tím mění, a s ní i to, kolik pixelů je jeden krok, takže se
rychlost každý snímek přepočítá z `natural` a aktuálního `bodyFrac`.

Za okrajem tvor obejde scénu dokola, místo aby se odrazil — a při té příležitosti
**prohodí pás** (`swapBand`): kdo šel vzadu za lagunou, vrací se vepředu. Přeskok
padne za okraj obrazovky, takže ho není vidět. Odraz vypadal
přirozeně, ale všichni se odrážejí od téhož místa a časem se sesypou do jednoho
hloučku; takhle si rozestupy drží napořád, protože každý chodí jinak rychle.

### Lišta dole (`web/roster.js`)
Vlevo obsazení scény po typech, vpravo posledních pět příchodů a odchodů: typ a
jméno z odeslané fotky, u tvorů z katalogu `-`. Přírůstky a odchody se dějí samy
(úlovek od dětí, doplněk z katalogu, tvor, který ustoupil úlovku) a bez výpisu se
nedá poznat, co scéna zrovna udělala. `addActor`/`dropActor` jsou jediná dvě
místa, která do lišty hlásí, takže se nemůže rozejít s obsazením. Klávesa `i`.

### Server (`server.py`)
- `GET /`         -> web/scene.html (fullscreen na TV)
- `GET /pridat`   -> web/upload.html (mobil: fotoaparát + odeslání)
- `GET /sablony`  -> web/sablony.html: přehled předloh s náhledy, tiskem
  a prokliky na `/dino3d#<klíč>`. Seznam dodává `GET /api/templates`
  z toho, co leží v `data/templates/`.
- `POST /api/upload` (multipart `photo`) -> zpracuje, uloží, broadcast
- `GET /api/rigs` -> seznam dosavadních úlovků
- `WS  /ws`       -> události scény
- statika: `/catch/...` z `data/catch/`, `/web/...` z `web/`,
  `/templates/...` z `data/templates/`, `/models3d/...` z `data/models3d/`

## Prostředí

Windows 11, PowerShell 5.1. Python 3.13 **globální, bez venv** — cv2 4.13
(s aruco), numpy, fastapi, uvicorn, PIL jsou nainstalované.

V Dockeru běží totéž na `python:3.13-slim`: `Dockerfile` + `docker-compose.yml`,
port 8100 (8000 drží jiný projekt), `data/catch` bind mountnutý ven. Opencv je
`opencv-contrib-python-headless` — aruco je v contribu a headless varianta
nepotřebuje libGL. Major verze je **připnutá na 4.x**: cv2 5.0 se nainstaluje
a upload projde, ale těch 143 testů proti němu neběželo. Jediná systémová
závislost je `libglib2.0-0`, bez ní se cv2 neimportuje. Node 24 k dispozici,
ale frontend je čisté ES moduly bez build kroku a bez CDN (poběží offline).

## Konvence

- Kód a identifikátory anglicky, texty pro uživatele česky (s diakritikou).
- Komentáře jen tam, kde *proč* není zřejmé z kódu. Žádné dekorativní hlavičky.
- Neřešit zpětnou kompatibilitu.
- Pracovní/dočasné soubory do `out/` (je v .gitignore-duchu), ne mimo projekt.
