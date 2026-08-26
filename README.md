# DinoStanice

Domácí obdoba exponátu z Haus der Natur v Salzburgu: dítě vybarví předtištěnou
šablonu, vyfotí ji mobilem — a jeho dinosaurus obživne v křídové krajině na
televizi, kde chodí, plave nebo létá mezi ostatními.

## Jak to spustit

V Dockeru:

```powershell
cd E:\ClaudeProjects\DinoStanice
docker compose up -d --build      # scéna na http://localhost:8100/
docker compose logs -f            # co se děje
docker compose down               # konec
```

Port je **8100**, protože 8000 na tomhle stroji drží `fs25-modssearcher`.
Přepíše se proměnnou `DINO_PORT` (v `.env` nebo na příkazové řádce).
Úlovky se přes bind mount ukládají rovnou do `data/catch/`, takže přestavbu
image přežijí.

Nebo přímo, bez kontejneru:

```powershell
.\start.ps1              # volitelně -Port 8080
```

Skript vypíše dvě adresy: **scénu** (otevři na PC vyvedeném do televize, klávesa
`F` přepne na celou obrazovku) a **stránku pro mobil**. V rohu scény svítí QR
kód, kterým se mobil připojí sám, a pod ním odkaz na `/sablony` — přehled všech
předloh s náhledy, tiskem a prokliky na 3D modely.

Klávesy ve scéně: `F` celá obrazovka, `H` skryje QR nápovědu, `I` lištu dole,
`D` otevře ladicí panel s tempem a rychlostí jednotlivých druhů (viz níže).

Dole běží lišta: vlevo kolik je ve scéně kterého tvora, vpravo posledních pět
příchodů a odchodů (`+`/`−`, typ a jméno z odeslané fotky; u tvorů z katalogu
jméno není, tak je tam `-`).

## Co tvorové ve scéně dělají

Chodci nejdou pořád dokola: každých 11–34 s se zastaví a 3–9 s postojí, občas
místo toho vyskočí a po stání se skoro v polovině případů otočí a jdou zpátky.
Když obejdou scénu dokola, vrací se druhým pásem — kdo šel vzadu za lagunou, jde
podruhé vepředu, takže se každý aspoň jednou ukáže zblízka.
Zastavení se plynule prolne do klidové pózy z katalogu, takže se nikdo nezasekne
v půlce kroku. Kromě toho se každý sune šikmo po pásu břehu, aby nešli všichni
po jedné lince.

## Ladění chůze

Klávesa `D` ve scéně vytáhne panel, kde se dá u každého druhu za běhu měnit:

- **tempo** — tempo animace. Rychlost po scéně jde s ním, aby chodidla zůstala
  na zemi: tvor jen šlape rychleji a odpovídajícím dílem ujde víc.
- **rychlost** — násobek dopočítané rychlosti. Tímhle se sladění chodidel
  naopak rozladí; je to šroubek pro případ, že měřený krok sedí špatně.

Prázdné pole znamená automat (v šedém textu je vidět, co si scéna spočítala
sama). Vpravo svítí, co z toho vyšlo: rychlost v px/s, jak dlouho trvá přejezd
obrazovky, délka jednoho cyklu a naměřená délka kroku v délkách těla. Nastavení
drží `localStorage`, takže přežije reload, a tlačítko **kopírovat JSON** vysype
hodnoty, které se dají zapéct do scény natrvalo.

## Jak vytisknout šablony

Otevři `/sablony` — jsou tam všechny předlohy s náhledem a tlačítkem
k tisku. Vyrobit znovu: `python tools/model_sheet.py`.

Tiskni **na 100 %**, žádné „přizpůsobit stránce" — na měřítku záleží, rozměry
v milimetrech drží celou pipeline pohromadě. Na každém listu je nahoře kontrolní
úsečka 100 mm, kterou si po tisku můžeš přeměřit pravítkem.

## Jak fotit (měřeno, ne odhadnuto)

- **Zblízka** — list ať vyplní většinu záběru, bezpečně přes 30 % šířky.
  Pod ~20 % značky přestanou být čitelné. Tohle je druhý nejkřehčí článek.
- **Zaostřeno** — klepni na displej. Rozmazání je vůbec nejkřehčí místo celého
  řetězce.
- Na čem naopak **nezáleží**: náklon kamery, stíny, nerovnoměrné světlo,
  kvalita JPEG, otočení listu vzhůru nohama. To všechno pipeline zvládá.
- Všechny **čtyři černé čtverečky v rozích** ať jsou vidět. Se dvěma to ještě
  projde, s jedním pipeline schválně odmítne — z jediné značky vychází
  registrace až o desítky milimetrů vedle, a to potichu.

## Jak to funguje

Obrys šablony se z fotky nehádá — je předem známý. `dinostanice/shapes.py`
generuje z jediné definice tvora (páteřní křivka + profil tloušťky + končetiny)
současně **tisknutelný obrys**, **masku pro ořez kresby** i **animační kostru**.
Proto textura vždy přesně sedne na to, co ji rozhýbe.

Tělo se při stavbě rigu **narovná podél páteře** do rovného pásu: osa x je
vzdálenost podél páteře, osa y kolmý offset. Renderer pak ohýbá rovný pás podél
libovolné animované křivky obyčejnými 2D transformacemi. Končetiny jsou tuhé
díly rotující kolem kloubů.

```
šablona (SVG, tisk) → dítě vybarví → foto mobilem
  → POST /api/upload → detect_sheet()  (ArUco → homografie → srovnaný list)
  → build_rig()      (narovnané tělo + rozřezané končetiny)
  → data/catch/<id>/ → WebSocket → scéna přidá tvora
```

Podrobnosti a kontrakty mezi částmi jsou v [ARCHITECTURE.md](ARCHITECTURE.md).

## Co je v katalogu

Osm šablon. Brachiosaurus, Tyrannosaurus, Stegosaurus a Triceratops chodí po
břehu, Plesiosaurus plave v laguně, Pteranodon a letadlo létají, plachetnice se
houpe na hladině.

Dinosauři vycházejí z **CC0 siluet z [PhyloPic](https://www.phylopic.org/)**
(autoři v [CREDITS.md](CREDITS.md)). Z bitmapy siluety se automaticky odvodí
páteř, tloušťka i končetiny s klouby — `dinostanice/silhouette.py` skeletonizuje
tvar, vezme nejdelší cestu jako páteř a větve mimo ni jako nohy. Výsledek se
předpočítá do `data/shapes/*.json`, protože skeletonizace je na každý import
příliš pomalá.

Přidat dalšího dinosaura znamená stáhnout siluetu a spustit dvě věci:

```powershell
python tools/fetch_silhouettes.py --free-only   # stáhne kandidáty + licence
python tools/build_catalogue.py                 # odvodí z nich geometrii
```

Pak už jen zapsat klíč do `CATALOGUE` v `dinostanice/creatures.py`. **Pozor:**
ID značek se přidělují podle pořadí v `CATALOGUE`, takže přeházení seznamu
znehodnotí všechny už vytištěné listy.

Plachetnice a letadlo se kreslí v `tools/make_vehicles.py` — skládají se
z primitiv do bitmapy a pak trasují, protože ručně kladené body polygonu vedle
traceované siluety vypadají hrubě.

## 3D modely nafouknuté z kresby

**Vypečené modely jsou smazané** — nahradila je větev, která vychází z hotových
3D modelů (níž). `/3d` proto hlásí, že žádný model není hotový; vrátí se jedním
během `python tools/make_model3d.py`. Metoda samotná je pořád v kódu a pod testy.

`http://<adresa>:8100/3d` ukáže úlovek jako otáčitelný 3D model. Hloubka se
v kresbě nenachází, takže se dopočítá „jako u plyšáka": co je dál od obrysu, to
víc vystoupí z papíru. Z boku je model přesně ta kresba, otočením se barvy
přetáhnou přes hřbet.

```powershell
python tools/make_model3d.py            # vypeče všechny do data/models3d/
python tools/shot3d.py --catch trex-1a85    # snímky ze čtyř úhlů do out/
```

Celé zvíře je **jedna spojitá kůže**; nohy se do hloubky rozestrkávají váhovým
polem, které u kyčle plyne k nule, takže se kůže přes rameno zkosí místo aby se
rozpadla. Tytéž váhy ohýbají nohu v kyčli při chůzi.

Zvířatům to sluší; **plachetnici ne** — z trupu a plachet vyjde sedací vak,
protože nafukování počítá s měkkým oblým tělem.

## Zkouška: předloha z 3D modelu

Obrácený postup — místo aby se z ploché siluety dopočítávala hloubka, vychází se
z hotových rigovaných modelů (`data/models_src/*.glb`, CC0 od Quaternia)
a předloha z nich vypadne jako bokorys. Zvíře pak má skutečný objem a chůzi od
autora modelu, ne dopočítanou.

Osm tvorů: Tyrannosaurus, Velociraptor, Triceratops, Stegosaurus,
Parasaurolophus, Apatosaurus a dva létající — drak a ptakoještěr. Póza předlohy se vybírá sama — projde se cyklus
chůze a vezme se okamžik, kdy tvar nejlíp vyplní list (rozkročené nohy jsou
čitelnější a pro texturu vydatnější). Oko se dokresluje, modely žádné nemají.

```powershell
python tools/model_sheet.py            # předlohy: data/templates/*.svg
python tools/model_export3d.py         # modely pro prohlížeč + ukázkové textury
python tools/model_paint_demo.py       # kontrola bez tiskárny: snímky z úhlů
python tools/make_pteranodon.py        # ptakoještěr: kostra a let z holé geometrie
```

Létající tvor se kreslí **shora** a natočený tak, aby rozpětí křídel leželo po
šířce listu — z boku jsou křídla jen tenký profil, ze kterého není co vybarvovat.

Živě na `http://<adresa>:8100/dino3d` — výběr tvora, všechny animace,
otáčení myší. Běží vedle staré pipeline, která zůstává beze změny.

### Na televizi

Vybarvený tvor se objeví rovnou ve scéně: chodí po břehu, létá nad lagunou.
Krajina zůstává malovaná do 2D plátna, tvorové se kreslí do průhledné WebGL
vrstvy nad ní a kapradí v popředí je zase nad nimi, takže dinosaurus stojí
v trávě a ne nad ní. Kamera je ortografická a nastavená v pixelech obrazovky,
takže obě vrstvy sedí bez dopočítávání perspektivy.

Než něco přinesou děti, scéna se doplní tvory z katalogu s ukázkovými texturami,
aby televize nesvítila naprázdno. Každý úlovek jednoho z nich vystřídá.

```powershell
python tools/shot_scene.py             # snímky scény bez televize (out/scena_*.png)
python tools/shot_scene.py --demo      # navíc doplní celý katalog
```

## Vývoj bez tiskárny

`dinostanice/synth.py` umí vyrobit syntetickou vybarvenou šablonu i simulovanou
fotku mobilem (perspektiva, osvětlení, rozostření, šum, JPEG). Celá pipeline se
tak dá vyvíjet a regresně testovat, aniž by kdokoli něco vytiskl:

```powershell
python -m pytest -q          # 143 testů, ~100 s
```

`out/robustness_report.md` shrnuje, kde přesně se snímání láme a proč.

## Struktura

| cesta | co to je |
|---|---|
| `dinostanice/` | pipeline: tvary, šablony, snímání, rig, kvalita, úložiště |
| `dinostanice/silhouette.py` | odvození páteře a končetin z bitmapy siluety |
| `dinostanice/inflate.py`, `model3d.py` | nafouknutí kresby do 3D a složení modelu |
| `data/models3d/` | modely pro prohlížeč: GLB s UV, textury, katalog |
| `data/silhouettes/` | zdrojové siluety + `credits.json` s licencemi |
| `data/shapes/` | předpočítaná geometrie tvorů |
| `web/` | scéna na TV, renderer, animace, krajina, stránka pro mobil, tisk |
| `web/scene3d.js` | 3D tvorové ve scéně: ortokamera v pixelech, klonování modelů |
| `tools/print_sheets.py` | tisková sada PDF |
| `tests/` | regresní sada nad syntetickými daty |
| `data/templates/` | vygenerované šablony (SVG + PDF k tisku), server je vydává na `/templates` |
| `data/catch/` | úlovky — co děti nafotily |
| `out/` | pracovní výstupy, náhledy, reporty |
