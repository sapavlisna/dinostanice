# Louka — čmelák a beruška bokem, hlína a stébla, věrnější textury

Stav k 2026-10-30. Podklad: snímky scény `out/louka-analyza/pred_*.png`, kód
`web/scene.js` (`updateButterfly`), `web/scene3d.js`, `web/backdrops/louka.js`,
`tools/make_louka_bugs.py`, `tools/make_ladybug.py`, `dinostanice/paint.py`.

## Analýza

**1. Proč je čmelák hlavou nahoru (a proč to oprava `turn` nespravila).**
Čmelák i beruška jsou modelované jako *letci shora*: hlava k +Z, hřbet k divákovi,
křídla roztažená v rovině obrazovky (stejná konvence jako motýl). Na obrazovce tedy
vždy vidíme jejich hřbet a tělo stojí svisle. `turn` otáčí kolem svislé osy — model
leží v rovině obrazovky, takže se jen zploští do čáry (komentář ve `scene3d.js` to
říká přímo). Moje úprava `turn: 0.15` z minula proto nemohla pomoct a čmeláka by
nanejvýš zhoršila. Správná oprava je jiný model, ne jiný úhel.

Totéž platí pro **šablonu na tisk**: list čmeláka a berušky je pohled shora a textura
se na model promítá shora. Bokorys proto znamená i nový list pro děti. V `data/catch`
je jen trojice dinosaurů, žádný vybarvený čmelák ani beruška — migrace není potřeba.

**2. Let není vodorovný.** `updateButterfly` volí cíle náhodně v pásu y 0,46–0,82 a
rychlost je kvůli poměru stran podobná ve směru x i y, takže letí šikmo nahoru a dolů.
Přistávací místa (`land`) jsou náhodné body v trávě, ne skutečná stébla.

**3. Pozadí.** `louka.js` kreslí souvislý kobereček drobných kytek (kopretiny, máky,
zvonky, jetel) a pár šedých kamenů — nic vysokého, na co by tvor mohl sednout, a žádná
zem. Spodní dráhy (y 0,815 / 0,88 / 0,945) vedou travou, takže šnek a had lezou
„v kytkách". V lese už existuje mechanismus míst k přistání (`backdrop.perches` +
`claim`, používá pták) — dá se znovu použít.

**4. Textury vypadají jako plastelína.** Výchozí textura = jedna plochá barva + měkké
skvrny + jemné zrno (`paint.py`), promítnutá z listu. Materiál je jednotný
`MeshStandardMaterial` s `roughness 0.88` — chybí lesk krovek a chitinu, průsvitná
křídla, srst, šupiny, články. Důležité: UV jsou vázané na list, takže **materiál a
výšková mapa se dají dodat per druh** a zdědí je i tvor vybarvený dítětem (barvy
z papíru + věrný povrch druhu).

## Plán

### Fáze 1 — čmelák a beruška bokem, vodorovný let, menší
1. `make_louka_bugs.py::build_bumblebee` a `make_ladybug.py`: nová konvence chodce
   (stojí na ose Z, kouká k −Y), křídla/krovky mávají nahoru–dolů kolem podélné osy,
   klipy `Fly` a `Rest` (složená křídla). Čmelák navíc nohy pod tělem.
2. Přegenerovat bokorysy a listy: `data/shapes3d/{bumblebee,ladybug}.json`,
   `data/templates/*.svg`, `data/models3d/*.glb`, `catalogue3d.json`, `axes/flip`
   ve `scenes/louka/scene.json`.
3. Nový typ pohybu `insect` místo sdíleného `butterfly` (motýl z lesa zůstane čelem):
   `MOTION.insect` v `scene3d.js` s `turn ≈ 0,3`, kotva za střed; sklon nosu podle
   svislé rychlosti (max ±0,15 rad) místo `bank`.
4. `updateButterfly` → vodorovný let: cíle ve výšce `y ± 0,03`, nová výška jen
   občas a pozvolna, svislá rychlost silně tlumená, jemné houpání sinusem.
5. Velikost: `scale` per druh (čmelák ~0,75×, beruška ~0,8×), po přegenerování
   přeměřit, protože `sizePx` se mění s novou siluetou.
6. Ověření: `shot_scene.py` (třeba 12 snímků v řadě, sledovat směr hlavy a sklon),
   `pytest`, kontrola šablony tiskem/`model_sheet.py`.

### Fáze 2 — pozadí: větší květy, stébla, hlína a kameny
1. Střední louka (`louka.js`): ~70 % méně drobných kytek; místo nich méně, ale větší
   květy na vyšších stoncích a vysoká stébla s listy; tráva zůstává jako podklad.
2. Spodní pás (y ≈ 0,79–0,97): hlína (barva se zrnem, tmavé vlhké skvrny, praskliny),
   kamínky různých velikostí se stínem a světlou hranou, zřídka stéblo. Přechod do
   trávy měkký, s nízkými stébly. Dráhy `near` se nemění — šnek, had, mravenec a
   housenka lezou po hlíně. Pozor na QR panel vpravo dole a `drawFront` od 0,96.
3. `perches(t)` + `claim` pro louku: místa = hlavičky květů a špičky stébel (deterministicky
   ze `SEED`, x se posouvá s vlněním větru). Čmelák přistane na květu (klip `Rest`),
   po čase odletí; místo je obsazené, dokud sedí.
4. Kobylka: nový typ bodu trasy `hop` — skok z hlíny na široký šikmý list stébla
   (parabola na obrazovce, hloubka podle paty, výška jako `lift`), pár sekund sedí,
   pak seskočí. Do `build_legged` přibude klip `Jump` (přikrčení, výskok, natažené
   zadní nohy, dopad). List je nakreslený pod tvory, aby kobylka nezmizela.
5. Ověření: snímky louky, soubory `scenes/louka/render.js` (dráhy a pásy),
   test, že čmelák nikdy neobsadí obsazené místo.

### Fáze 3 — věrnější textury a materiály
1. Materiál per druh ve `scene.json` (`material: {roughness, bump}`) a podpora
   v `scene3d.js`: lesklé krovky a chitin (roughness ~0,25), srst čmeláka a mokrý
   šnek (~0,3), šupiny hada a články housenky přes výškovou mapu.
2. `paint.py`: druhý výstup `<druh>_bump.png` ve stejných UV; vzory podle druhu —
   srst (jemný šum podél těla, rozmazané pruhy žlutá/černá/bílý ocásek), šupiny
   (kosočtverce), články, spirála ulity, žilkovaná křídla, pravidelné tečky berušky
   s tmavším lemem. Barvy z fotek: čmelák žlutooranžová a hnědočerná, kobylka
   zelená s hnědým hřbetem, had užovka se světlým břichem.
3. Průsvitná křídla: nejdřív bez alfa (světlá šedomodrá se žilkami); alfa jen pokud
   to půjde bez rozbití dětských úlovků (rozhodnutí níž).
4. Ověření: přiblížené snímky před/po (`shot3d.py`) i ve skutečné velikosti na
   1080p — beruška je tam ~100 px, takže detail pod tuto velikost nemá smysl;
   důraz na barvu, lesk a siluetu.

### Pořadí
Fáze 1 → 3 → 2. Fáze 3 sdílí přegenerování listů s fází 1, fáze 2 je největší
a nejméně riziková, proto až poslední. Po každé fázi nasazení do Dockeru a snímky.

## K rozhodnutí
- **Bokorys opravdu?** Změní se list pro děti (čmelák a beruška bokem místo shora).
  Levnější náhrada: pootočit stávající model o 90° v rovině obrazovky — poletí
  vodorovně, ale uvidíš ho shora, ne z boku.
- **Průsvitná křídla s alfa** — hezčí, ale dětská textura je fotka papíru bez alfa;
  řešení je maska křídel dle UV. Jde to, jen to prodlouží fázi 3.
- **Kobylka sedí na listu** (vodorovně), ne přilepená ke stonku — uvěřitelnější a
  jednodušší. Stačí?
