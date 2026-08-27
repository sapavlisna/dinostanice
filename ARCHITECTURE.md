# DinoStanice — architektura

Domácí obdoba exponátu z Haus der Natur v Salzburgu. Dítě vybarví předtištěnou
šablonu, vyfotí ji mobilem a jeho dinosaurus se objeví v živé křídové krajině
na televizi, kde chodí / plave / letí mezi ostatními.

## Tok dat

    trex.glb (CC0, rigovaný, 6 animací)
      -> ortogonální bokorys -> obrys + vnitřní linky -> šablona (SVG, tisk)
      -> dítě vybarví  ->  foto mobilem
      -> POST /api/upload -> capture.detect_sheet()  (ArUco -> homografie -> srovnaný list)
      -> capture3d.save_catch()  (barvy z papíru jako textura na kůži modelu)
      -> data/catch/<id>/{model.json, texture.png, meta.json}
      -> WebSocket broadcast -> scéna na TV přidá nového tvora

## Klíčová myšlenka

Předloha není nakreslená ani hádaná — **vzniká promítnutím hotového 3D modelu
na list**. Tím je registrace zadarmo: kde na papíře leží bod, tam má na modelu
svoje UV (`u = x/297`, `v = 1 - y/210`). Vybarvená fotka se tedy nasadí na
model jednou planární transformací a drží ve všech pózách a úhlech.

Hloubka se z kresby nedopočítává, protože ji nikdo dopočítávat nemusí: model
má skutečný objem i skutečnou chůzi od autora. Z boku je model přesně ta
kresba, otočením se stejné barvy přetáhnou přes hřbet.

Obrys šablony je proto **předem známý** — je uložený v `data/shapes3d/<key>.json`
spolu s převodem milimetry ↔ souřadnice modelu (`Placement`). Nic z toho se
z fotky nezjišťuje; z fotky se čte jenom to, kde list je (rohové značky) a jaké
barvy na něm jsou.

## Hotové moduly (needitovat bez důvodu)

- `dinostanice/shapes.py` — rozměry listu (A4 na šířku) a šířka tištěné linky
- `dinostanice/markers.py` — ArUco DICT_4X4_100, 4 rohy na list, ID = 4*index+roh
- `dinostanice/creatures3d.py` — katalog tvorů (viz níž)
- `dinostanice/gltf.py` — vlastní GLB loader a linear blend skinning (numpy)
- `dinostanice/orthoview.py` — z-buffer rasterizace do ortogonálního pohledu
- `dinostanice/modelsheet.py` — z pohledu udělá předlohu: polygony v milimetrech,
  `Placement` (mm ↔ model), oko; `rasterise()` nakreslí tištěný list jako bitmapu
  (náhledy a syntetické fotky v testech), `to_texture()` udělá z vybarveného
  listu texturu
- `dinostanice/glbexport.py` — zapíše kopii GLB s doplněným `TEXCOORD_0` (pozice
  vrcholů na listu) a případně s dopsanou kostrou
- `dinostanice/capture.py` — detekce listu a homografie, srovnání osvětlení.
  `detect_sheet()` vyžaduje **aspoň dvě značky** (`MIN_MARKERS`) a kontroluje, jak
  homografie sedí: jedna značka ji určí přesně, ale extrapolace přes celý list byla
  naměřena desítky milimetrů vedle — a tiše.
- `dinostanice/capture3d.py` — ze srovnaného listu textura pro model, míra
  vybarvení, zápis úlovku
- `dinostanice/synth.py` — syntetické vybarvení + simulovaná fotka (vývoj bez tiskárny)
- `dinostanice/quality.py` — hodnocení kvality fotky s českými radami; server jím
  po neúspěšné detekci nahradí obecné „nepovedlo se" konkrétní radou, co udělat
  s fotkou jinak (`_capture_advice`)
- `dinostanice/store.py` — úlovky v `data/catch/<id>/`, koš `data/trash/`,
  odmítnuté fotky `data/rejected/`
- `dinostanice/scenes.py` — registr scén (krajin): klíč, popisek a `catalogue`
  (kterou sadu tvorů scéna přijímá); server z něj servíruje `GET /api/scenes`

## Jak se dělá předloha

Podrobněji k jednotlivým krokům (`python tools/model_sheet.py [klíč...]`):

- `Model.posed(anim, t)` (`gltf.py`) vrátí vrcholy a normály v pozici.
- `View.sample()` (`orthoview.py`) interpoluje libovolný atribut vrcholů (kvůli
  UV), `outline_edges()` rozloží kresbu na obrys, hloubkové skoky a hranice
  materiálů.
- `modelsheet.build()` z toho udělá polygony v milimetrech na listu a
  `Placement`, což je právě ten převod mm ↔ souřadnice modelu. Oblasti
  k vybarvení nejsou hranové pixely, ale souvislé plochy, které nerozděluje
  ani hranice materiálu, ani skok v hloubce.
- `tools/model_sheet.py` — vyrobí `data/templates/<key>.svg`, náhled a
  `data/shapes3d/<key>.json`.
- `tools/model_paint_demo.py` — uzavře kruh bez tiskárny: syntetické vybarvení,
  textura, snímky z různých úhlů a fází animace.
- `tools/model_export3d.py` → `data/models3d/<key>.glb` + ukázková textura.
  Model z internetu UV nemá; tady jsou to pozice vrcholů na listu
  (`glbexport.write_with_uv`).
- `web/dino3d.js`, stránka `/dino3d` — three.js `GLTFLoader` + `AnimationMixer`.
  Kostru i animace nese GLB, prohlížeč jen hodí na model vybarvenou fotku
  (`texture.flipY = false`, protože glTF má počátek UV vlevo nahoře).
  Snímky pro posouzení bez televize: `python tools/shot3d.py --creature trex3d`.

Póza předlohy se hledá sama (`best_pose`): projde se cyklus chůze a vezme se
okamžik s nejlepším vyplněním listu **po fitu**, ne v pixelech — natažený
apatosaurus má velkou siluetu, ale na papíře z něj zbude tenký pruh. Pouštět do
výběru i ostatní animace se neosvědčilo: `Attack` sice list vyplní nejlíp, ale
tvora překroutí (apatosaurovi přehodí ocas přes tělo, stegosaurovi schová
ploténky). Vyplnění není totéž co čitelnost.

### Katalog tvorů (`dinostanice/creatures3d.py`)

Osm tvorů; `axes`/`flip` u každého volí projekci — chodec bokorys, letec shora
s rozpětím křídel po šířce listu.

Výjimkou je **drak**: shora z něj byla Rorschachova skvrna — rozpětí křídel je
větší než tělo, takže po fitu na list zbyla z hlavy boule na hraně a oko
skončilo jako tečka uprostřed těla. Kreslí se proto bokorysem jako chodci
(v póze `Death` t=0,37, kde drží křídlo rozepjaté v rovině listu). Na letce
to jde jen tam, kde tvor má kromě křídel i tělo a hlavu; pteranodon je samé
křídlo a z boku by z něj byl tenký profil.

Indexy značek začínají na **8**: prvních osm patřilo první, zrušené větvi
projektu (kresba → ohýbaný 2D pás). Zůstávají volné pro další tvory a tyhle se
**nepřečíslovávají** — index je natvrdo v rohových značkách na už vytištěných
listech. Proto taky `markers.py` přešel na `DICT_4X4_100`: je to nadmnožina
`DICT_4X4_50` (prvních 50 kódů je shodných), takže se rozšířil prostor, ale nic
se nepřepsalo.

Vedle geometrie nese katalog i **vlastnosti druhu pro scénu**:
`scene` říká, do které sady tvorů (krajiny) model patří — marker index
zůstává globální, šablona identifikuje tvora, scéna jen říká, koho přijme.
`stride_rate` je cílové tempo chůze v délkách těla za sekundu (paleo odhad
per druh); `clip_for` mapuje role klipů (`move`/`stand`/`jump`) na jména
v GLB, protože se model od modelu liší. Všechno se propíše do
`data/models3d/catalogue3d.json` (`scene`, `strideRate`, `clipFor`, `clips`,
`pose`, `size`), odkud si to bere scéna přes `GET /api/dino3d?scene=`.

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

`capture.detect_sheet()` najde list, srovná ho do roviny a z ID značek řekne,
který tvor to je; `known_indices()` mu vymezuje, které indexy vůbec existují
(katalog `creatures3d.py`, dnes 8-15). Žádný rig se nestaví — model kostru má.
`capture3d.save_catch()` ze srovnaného listu udělá texturu (`build_texture`)
a uloží `texture.png` + `model.json`.

Textura projde týmž `to_texture()` jako ukázkové: osvětlení se narovná jen
uvnitř kresby, tištěné linky se zaretušují okolní barvou a barva se rozlije
kousek za obrys. Registrace je zadarmo — předloha vznikla promítnutím modelu na
list, takže UV modelu **jsou** souřadnice na papíře.

`meta.json` nese druh, jméno z fotky, míru vybarvení, počet nalezených značek
a `session` (které televizi úlovek patří). Zblízka a s ovládáním se na tvora dá
koukat v `/dino3d`, kde je ve skupině **Úlovky** vedle katalogu.

Klipy se hledají podle holého jména (`Model.clip`), ne skládáním z prefixu:
FBX export jim dává jméno armatury, které se model od modelu liší
(`Armature|TRex_Walk` proti `CharacterArmature|Fast_Flying`).

Oko se dokresluje, modely ho nemají — nese ho barva materiálu, ne geometrie.
`auto_eye()` ho položí do obálky vrcholů, které visí na jointu `Head`, a ověří,
že bod padl dovnitř kresby; když ne, posouvá ho k těžišti hlavy.

Letec se kreslí shora a oko mu neleží před tělem, ale na ose souměrnosti
(`eye_bias={"centre_x": True}`) — jinak `auto_eye` míří do strany od hlavy,
tedy mimo kresbu.

Kde to drhne: černý obrys z papíru se při otočení protahuje přes hřbet, takže
se z textury musí vymazat (`to_texture()` ho zaretušuje okolní barvou).
Apatosaurus je na list příliš protáhlý (poměr 4:1 proti kreslicí ploše 1,6:1),
takže z něj zbývá tenký pruh — jiná póza to nespraví, jen ho zamotá.

## Kontrakty mezi částmi (dodržet!)

### Definice scény (`web/scenes/<key>.js`)

Scéna je data. `scene.js` nezná žádné zóny ani konstanty krajiny — všechno
čte z ES modulu s definicí, který se importuje dynamicky podle klíče:

```js
export default {
  key: 'cretaceous',           // musí sedět s registrem na serveru (scenes.py)
  label: 'Křídová laguna',
  catalogue: 'cretaceous',     // sada tvorů (Model3D.scene), kterou scéna přijímá
  backdrop: async () => ...,   // továrna na kreslič krajiny (viz níže)
  lighting: { hemi, sun, fill },  // světla 3D vrstvy (Scene3D.setLighting)
  bands: [                     // pásy: y0/y1 v podílu výšky plátna
    { name: 'shore', y0: 0.80, y1: 0.95, motions: ['walk'], lane: 'near' },
    ...                        // `motions` = kdo se v pásu smí pohybovat,
  ],                           // `lane` odlišuje víc pásů téhož pohybu
  motions: {                   // chování a měřítka per typ pohybu:
    walk: { sizeFraction, baseSpeed, strideRate,
            drift, driftRefHeight, farChance, rest: {...} },
    fly: { ..., bob: true }, swim: {...}, sail: {...},
  },
  paths: [ ... ],              // volitelné trasy chodců (viz Scéna)
  ambientMin: 6,               // na kolik tvorů doplňovat z katalogu
};
```

`strideRate` v `motions` je jen default cílového tempa chodce (těl/s) — per
druh ho přebíjí `strideRate` z katalogu, protože tempo je vlastnost druhu,
ne krajiny. `rest` říká, jak často a jak dlouho chodec zastavuje; pohyb bez
`rest` nezastaví nikdy (letec by spadl).

Přidání scény = záznam v `dinostanice/scenes.py` (registr pro server) + tenhle
JS modul + případně nový backdrop. Noční laguna (`cretaceous_night.js`) je
levný důkaz mechanismu: spread denní definice, jiný backdrop-variant a světla.

### Pozadí (`web/backdrops/<name>.js`)

ES modul s továrnou `create(variant)` — křídová krajina má varianty `'day'`
a `'night'` (měsíc, hvězdy, tlumená paleta). Vrací instanci:

```js
{
  draw(ctx, W, H, t),          // vykreslí krajinu; t = čas v sekundách
  drawFront(ctx, W, H, t),     // kapradí a vinětace — patří až PŘED tvory
  sun: {x, y},                 // kde je slunce, v podílu plátna
  depthScale(yFrac)            // -> násobek velikosti podle hloubky scény
}
```

Pásma (dřívější `zones`) tu už **nejsou** — kde kdo smí chodit, je vlastnost
scény, ne malby, a žije v `bands` v definici scény.

### 3D vrstva scény (`web/scene3d.js`)
```js
Scene3D.init(canvas)                       // -> null, nebo chybová hláška bez WebGL
Scene3D.setLighting(cfg)                   // světla z definice scény (hemi/sun/fill)
Scene3D.resize(W, H)
Scene3D.spawn({id, glb, texture, motion, clip, breaks})
                                           // -> handle: .length, .height, .sizePx,
                                           //    .duration, .strideBodies, .breakDur
Scene3D.place(handle, {x, y, scale, face, depth})   // face -1..1, mezi tím se otáčí
Scene3D.speed(handle, timeScale)
Scene3D.walked(handle, dt)                 // délky těla ušlé za dt — po fázové
                                           // křivce klipu, ne průměrem
Scene3D.blend(handle, name, weight)        // prolnutí zastávky přes chůzi
Scene3D.restart(handle, name)              // skok od začátku
Scene3D.remove(handle)
Scene3D.render(dt)                         // dt bere od scény, ať pohyb a animace
                                           // po zaškubnutí nerozejdou
Scene3D.onNote(fn)                         // hlášky pro uživatele (ztráta kontextu)
Scene3D.info()                             // počty textur/geometrií (testy, kiosk)
```
Kamera je **ortografická a nastavená v pixelech obrazovky** (levý horní roh je
počátek, svislá osa jde dolů jako v canvasu). Scéna tak umísťuje tvory ve
stejných souřadnicích, ve kterých kreslí krajinu, a nemusí řešit perspektivu.

Modely koukají na +Z; `place` je natáčí kolem Y podle směru chůze, ne
zrcadlením — zrcadlit by znamenalo obrátit i texturu. Natočení a kotva jsou
per typ pohybu v tabulce `MOTION`: chodec je natočený lehce k divákovi
(`turn` 0,34 rad), letec víc (0,95 rad) a ještě nakloněný kolem osy pohledu
(`bank`), protože z čistého profilu jsou z něj jen dvě čárky. `anchor` říká,
za co tvor visí: chodec za nohy na `y = 0`, letec/plavec/loď za střed těla.

Měřítko se váže na `sizePx` — odmocninu z plochy siluety, ne na délku. Kdyby
všichni měli stejnou délku, apatosaurus (samý krk a ocas) by vedle tyranosaura
vypadal jako ještěrka.

Provozní pojistky (kiosk běží týdny bez dozoru):

- **`webglcontextlost`** — reset GPU driveru je reálný scénář; bez
  `preventDefault()` se kontext už nikdy neobnoví, tak se scéna po hlášce
  raději celá načte znovu.
- **Textury se počítají referenčně** (`texCache` s refcountem): tentýž úlovek
  ve scéně dvakrát sdílí texturu a `remove()` ji uvolní až s posledním
  odkazem. Ukázkové textury z `/models3d/` se drží napořád (`keep`).
- `remove()` uklízí i skeleton (bone texturu) a materiál — geometrie je
  sdílená z `glbCache` a zůstává.

Dvě věci, na kterých se to dá lehce rozbít:

- **Měřítko se počítá z bind pózy** (`measure()`), ne z `Box3.setFromObject()`.
  Ten se u skinovaných meshů ptá na `SkinnedMesh.boundingBox`, který vychází
  z aktuální pózy a už nese transformaci skeletu — ta se pak přiloží ještě
  jednou. Obálka vyjde o dva řády větší a s prohozenými osami. Navíc by tvor
  s každým krokem měnil velikost.
- **Zem je `y = 0` v modelu**, ne spodek obálky. Triceratops má bind pózu, která
  sahá pět jednotek pod počátek, a vznášel by se nad pískem.

### Scéna (`web/scene.js`)

Jeden generický stroj nad aktivní definicí scény: používá Backdrop a Scene3D
a rozhoduje jen o tom, kdo je kde. Výběr scény: `?scene=` v URL
přebíjí, jinak platí hodnota session ze serveru (`GET /api/scene/active`);
zprávou `scene` z WS se přepíná za běhu — tvorové odejdou zmenšením do
ztracena, krajina se prolne do nové (`XFADE_S`), 3D vrstva dostane nová světla
a přivedou se úlovky a doplňky nové scény. Úlovky cizí krajiny se nenačítají
a nemažou — čekají na přepnutí zpátky.

**Session**: TV bez `?s=` je domácí default `tv`; `?s=<id>` oddělí druhou
obrazovku s vlastním QR, úlovky a broadcastem. Scéna posílá session do všech
API volání i do WS.

Připojí se na `ws://<host>/ws?s=<sid>` a přijímá:

- `add {id, url, creature, label, name}` — nový úlovek. Vstupuje **vždy
  zleva** (teamLab vzor — mobil po uploadu říká „sleduj levý kraj") a nese
  ~6 s jmenovku se jménem z fotky. Tvorové obnovení po reloadu a doplňky
  z katalogu vstupují potichu a rozsazuje je zlatý řez, ne náhoda — náhodných
  šest čísel se často sesype do jednoho rohu.
- `remove {id}` — tvor **odejde odehraně**: opustí trasu, otočí se k bližšímu
  okraji a dojde/doletí/dopluje za něj vlastním tempem; teprve za okrajem se
  uvolní zdroje. Záchranná brzda: když se `EXIT_TIMEOUT_S` nehne z místa,
  spadne na starý fade.
- `feed {x}` — krmení z mobilu: na přední břeh spadne trs kapradí (kreslený
  procedurálně, žádný asset), chodci bez trasy v okruhu k němu zamíří,
  u jídla postojí (stávající rest mašinerie) a vrátí se k driftu. Tvor na
  trase drží řád scény a jídlo ignoruje; letci a plavci nereagují.
- `settings {ambient}` — zapnutí/vypnutí doplňování z katalogu (z `/rezim`).
  Vypnutí nemaže, jen se přestane doplňovat.
- `cleared` — stanice vyprázdněna: úlovky odejdou (odehraně, s jedním souhrnným
  záznamem v liště), doplňky z katalogu zůstanou.
- `scene {scene}` — přepnutí krajiny za běhu (viz výše).
- `idle {seconds_left}` / `sleep` / `wake` — uspávání session (viz Server).
  Spánek je jen ztmavení + velké QR; nic se nemaže a rAF smyčka jede dál.

Události z výpadku WS jsou ztracené, proto se po každém (re)connectu stav
**rekonciliuje** se serverem podle id: chybějící úlovky se přivedou, ty, které
server už nezná, odejdou; katalogových tvorů se to netýká. Spojení drží
keepalive ping (25 s) — server na něj neodpovídá, ale pravidelný send drží NAT
při životě a na mrtvém TCP se neodeslaná data nahromadí, až OS socket zavře;
reconnect pak jede s exponenciálním backoffem (3 s → 30 s). Ve smyčce snímků
je záchytná síť: `requestAnimationFrame` se přeplánuje dřív, než může cokoli
spadnout, a 30 chyb po sobě znamená reload — jedna výjimka nesmí televizi
zastavit navždy.

Scéna se doplňuje z katalogu (`ambientMin` z definice scény), aby televize
nesvítila naprázdno, než něco přinesou děti — ukázkové textury vypadají jako
vybarvené, takže je poznat, o co jde. Jakmile dorazí úlovek, jeden tvor
z katalogu ustoupí; po smazání úlovku se scéna zase doplní. Počet tvorů tak
zůstává stálý a úlovky katalog postupně vytlačí.

Plátna leží ve třech vrstvách: krajina (2D) → tvorové z modelů (WebGL) →
popředí (2D). Bez toho by dinosaurus stál nad kapradím, ne v něm.

#### Rychlost chůze: měřená, fázově vázaná

Chodec z 3D modelu nemá rychlost zvolenou, ale spočítanou z animace, aby po
písku neklouzal. Klipy šlapou na místě, takže `Scene3D.spawn` z nich odečte
**délku kroku** (`strideBodies`, v délkách těla na jeden cyklus): noha, která se
v modelu sune dozadu nejrychleji, je ta, co stojí na zemi, a kolik za cyklus
ujede, tolik se musí posunout tvor. Scéna pak jen vybere tempo cyklu blízko
přirozeného tempa druhu (`strideRate` z katalogu, default z definice scény,
pojistka `GAIT_RATE`) a rychlost po scéně z něj dopočítá — chodidla tak sedí
na zemi u každého modelu, ať má krok a cyklus jakkoli dlouhý. Rozdíly mezi
druhy zůstanou: apatosaurus se plouží, drobný velociraptor si vykračuje.

Průměrná rychlost ale nestačí: stojná noha se v klipu nesune konstantně,
takže tvor posouvaný průměrem uvnitř cyklu pořád klouže. `strideOf` proto
vedle celkové dráhy ukládá i **kumulativní křivku posunu po fázi klipu**
a `Scene3D.walked(handle, dt)` z ní čte, kolik délek těla tvor ušel za
konkrétní úsek cyklu — scéna posouvá tvora přesně tak, jak zrovna šlape.
`walked` čte `timeScale`, takže zpomalení do zastávky je v tom zdarma.
Prokluz drží kolem 1 % ujeté dráhy; regresní brána je `tools/gait_report.py`
(Playwright nad běžící scénou, fail při >3 % nebo tempu mimo cíl druhu).

Hádaná rychlost byla vidět: modely se v délce kroku i délce cyklu liší tak, že
jeden a týž odhad znamenal u tyranosaura o 40 % pomalejší pohyb, než jak šlapal,
a u apatosaura sedmkrát rychlejší. `Scene3D.spawn` navíc **odřízne mrtvý konec
klipu** (`trimTail`) — velociraptorova chůze má za odkráčeným cyklem půl cyklu
nehybné pózy, takže se uprostřed chůze zastavoval a přesto se posouval dál.

Plavcům a letcům se krok neměří — nemají chodidla, po kterých by šlo poznat
prokluz. Ti dostanou tempo z jedné náhody se svou rychlostí, takže rychlejší
tvor zároveň častěji mává křídly.

Automat se dá přebít z ladicího panelu (`web/tune.js`, klávesa `d`): u každého
druhu ve scéně jde nastavit `rate` (tempo animace, rychlost jde s ním, ať
chodidla drží) a `speed` (násobek dopočítané rychlosti, tím se sladění naopak
rozladí). `applyGait()` je jediné místo, kde se obojí do tvora dostane, takže
změna platí okamžitě i pro tvory, kteří už ve scéně jsou. Hodnoty drží
`localStorage`.

#### Zastávky, pásy, trasy

Aby scéna nebyla přehlídka (všichni pořád vpřed, nikdo nikdy nestojí), chodec
si během chůze dělá **zastávky** — konfigurace `rest` v definici scény:

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
**prohodí lane** (`swapBand`): kdo šel vzadu za lagunou, vrací se vepředu. Přeskok
padne za okraj obrazovky, takže ho není vidět. Odraz vypadal
přirozeně, ale všichni se odrážejí od téhož místa a časem se sesypou do jednoho
hloučku; takhle si rozestupy drží napořád, protože každý chodí jinak rychle.

Část chodců (`ROUTE_CHANCE`, 50 %) dostane při příchodu **trasu** — lomenou
čáru z pole `paths` v definici scény (`loop` dokola / ping-pong, `species`
omezí na druh, body s `do: 'walk' | 'stop' | 'turn'` a `dwell`). Trasa je
autorita nad pásy: žádné obcházení okraje, žádný swapBand, žádný náhodný rest —
zastávky a otočky určují waypointy, odchod a návrat řeší body za okrajem,
které si autor nakreslil sám. Nový tvor se na trasu zavěsí v nejbližším místě
(`snapRoute`), ať se všichni nesesypou na start; vzdálenost po čáře se měří
izotropně (y škálované poměrem stran), aby svislý kus nebyl „zadarmo". Trasy
se kreslí editorem v ladicím panelu (`d` → sekce Trasy, `Tune.pathsFor`);
„kopírovat JSON" vysype pole k vložení do definice scény, rozpracovaná verze
žije v `localStorage`.

Pro ladění vystavuje `window.DinoScene`: `where()` (kdo je kde, včetně pásu,
trasy a tempa), `add()`, `feed()`, `gpu()`, `switchScene()` a debug vstupy do
spacího UI — používá je `tools/shot_scene.py`, `tools/gait_report.py`
i Playwright testy.

### Lišta dole (`web/roster.js`)
Vlevo obsazení scény po typech, vpravo posledních pět příchodů a odchodů: typ a
jméno z odeslané fotky, u tvorů z katalogu `-`. Přírůstky a odchody se dějí samy
(úlovek od dětí, doplněk z katalogu, tvor, který ustoupil úlovku) a bez výpisu se
nedá poznat, co scéna zrovna udělala. `addActor`/`dropActor` jsou jediná dvě
místa, která do lišty hlásí, takže se nemůže rozejít s obsazením. Klávesa `i`.

### Server (`server.py`)

Stránky:

- `GET /`         -> web/scene.html (fullscreen na TV; `?s=` volí session)
- `GET /pridat`   -> web/upload.html (mobil: foto + jméno + krmení + správa
  úlovků; otevření přes QR se `?s=` počítá jako aktivita session)
- `GET /dino3d`   -> prohlížeč modelů a úlovků (three.js)
- `GET /sablony`  -> přehled předloh s náhledy, tiskem a prokliky na `/dino3d#<klíč>`
- `GET /rezim`    -> režim stanice: přepínání krajin, ukázkoví tvorové,
  vyprázdnění stanice

API:

- `POST /api/upload` (multipart `photo`, `name`, `s`) -> zpracuje, uloží,
  broadcast do session. Úlovek z jiné krajiny, než jaká na TV běží, se uloží
  a vrátí se s `note` („přepni krajinu a objeví se") — nic se nezahazuje,
  jen se neposílá scéně.
- `GET /api/rigs?s=&scene=` -> úlovky session, volitelně jen ty patřící dané
  krajině; `DELETE /api/rigs/{id}` maže (přes koš).
- `GET /api/dino3d?scene=` -> katalog modelů, volitelně filtrovaný na sadu tvorů
- `GET /api/templates` -> předlohy (jde se přes katalog, ne přes obsah adresáře)
- `GET /api/scenes` -> registr krajin pro /rezim
- `GET/POST /api/scene/active` -> aktivní krajina session; default session ji
  persistuje ve `data/state.json`, ostatní po restartu spadnou na default
- `GET/POST /api/scene/settings` -> `ambient` (doplňování z katalogu), globální,
  ve `state.json`
- `POST /api/scene/reset` -> smaže úlovky JEN dané session a pošle jediné
  `cleared` (ne N zpráv `remove`)
- `POST /api/feed` -> hodí do scény jídlo (broadcast `feed`), rate-limit
  `FEED_COOLDOWN_S` per session
- `POST /api/session/touch`, `GET /api/session/{sid}` -> budíček / stav session
- `GET /api/qr?s=` -> PNG s QR na `/pridat` (ne-default session dostane `?s=`)
- `WS  /ws?s=`    -> události scény (viz výše)
- statika: `/catch/...` z `data/catch/`, `/web/...` z `web/`,
  `/templates/...` z `data/templates/`, `/models3d/...` z `data/models3d/`

**Sessions.** `Session` dataclass (klienti, `last_seen`, `sleeping`, aktivní
`scene`, rate-limit krmení) v `Hub`, per session broadcast. Neznámá session
tiše vzniká při prvním dotyku — tak přežije i restart serveru. Hlídač
nečinnosti (`idle_tick`): bez aktivity (sken QR, upload, touch, krmení)
`IDLE_WARN_S` → odpočet na TV, `IDLE_SLEEP_S` → `sleep`; probuzení je zase jen
aktivita. Default session `tv` je z uspávání vyjmutá (`IDLE_EXEMPT`) — domácí
televize má svítit pořád. Session bez klientů a aktivity > `SESSION_TTL_S` se
zahodí z paměti (úlovky na disku zůstávají). Uspání NENÍ mazání.

**Limity a odolnost.** HTTP middleware odmítne upload podle `Content-Length`
dřív, než Starlette začne multipart sypat do temp souboru (parser sám limit
nemá); `decode_photo` kontroluje rozměry z hlavičky **před** plnou alokací
(`MAX_PIXELS` — dekompresní bomba nesmí propadnout ani do cv2 fallbacku,
`imdecode` žádný limit nemá), poměr stran (`MAX_ASPECT`) a velké fotky zmenší
(`MAX_SIDE`). Pipeline běží v threadpoolu pod semaforem (`MAX_CONCURRENT` = 2
— exponát obsluhuje jedno dítě po druhém, fronta je správně). Broadcast jde
paralelně s timeoutem 2 s: televize v suspendu drží half-open TCP a sériové
`await send_json` by pověsilo odpověď na upload; klient, kterému se nedoručí,
se odpojí. Všechno podstatné se loguje (`logging`, logger `dinostanice`).

**Koš a odmítnuté fotky.** Smazání úlovku je dvoufázové: `delete_catch`
atomicky odstaví adresář na `<id>.deleted` (na Windows může StaticFiles držet
otevřený soubor a rmtree by nechal půlrozpad), `purge_deleted` ho pak přesune
do `data/trash/` — jsou to dětské výtvory a omylem spuštěný reset je nesmí
zničit. Koš se čistí po `TRASH_KEEP_DAYS` (30 dní) a v Dockeru je bind
mountnutý na hostitele (`shutil.move` kvůli EXDEV přes hranici mountů).
Odmítnuté fotky (`CaptureError` i pády) se ukládají do `data/rejected/`
(posledních 50) — jsou to nejcennější testovací data. Když se list nenajde,
`quality.assess` nahradí obecnou hlášku konkrétní českou radou (rozmazané,
daleko, málo značek, nevybarvené…).

## Prostředí

Windows 11, PowerShell 5.1. Python 3.13 **globální, bez venv** — cv2 4.13
(s aruco), numpy, fastapi, uvicorn, PIL jsou nainstalované.

V Dockeru běží totéž na `python:3.13-slim`: `Dockerfile` + `docker-compose.yml`,
port 8100 (8000 drží jiný projekt); bind mounty `data/catch`, `data/trash`
a `data/state.json` (soubor musí na hostiteli existovat před prvním startem,
jinak si Docker místo něj udělá adresář). Opencv je
`opencv-contrib-python-headless` — aruco je v contribu a headless varianta
nepotřebuje libGL. Major verze je **připnutá na 4.x**: cv2 5.0 se nainstaluje
a upload projde, ale testy proti němu neběžely. Jediná systémová
závislost je `libglib2.0-0`, bez ní se cv2 neimportuje. Node 24 k dispozici,
ale frontend je čisté ES moduly bez build kroku a bez CDN (poběží offline).

Testy: `python -m pytest -q` — 132 testů; `tests/test_server.py` (36 testů)
jede end-to-end přes FastAPI TestClient se syntetickými fotkami, žádný běžící
server není potřeba. Chůzi ve scéně hlídá `tools/gait_report.py` (Playwright,
potřebuje běžící server).

## Konvence

- Kód a identifikátory anglicky, texty pro uživatele česky (s diakritikou).
- Komentáře jen tam, kde *proč* není zřejmé z kódu. Žádné dekorativní hlavičky.
- Neřešit zpětnou kompatibilitu.
- Pracovní/dočasné soubory do `out/` (je v .gitignore-duchu), ne mimo projekt.
