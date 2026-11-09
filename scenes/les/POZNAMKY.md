# Poznámky k tvorům scény `les`

Testovací scéna z Quaterniova **Ultimate Animated Animal Pack** (CC0). Krajina
je vlastní, `web/backdrops/forest.js` (louka s cestičkou pod lesem, bez vody).

Kmeny s ptáky a cestička jsou ve `web/backdrops/forest.js`: dva štíhlé kmeny
před scénou (kreslí se nad tvory, zvíře za nimi zajde) a na jejich větvích sedají
2D ptáci (sýkora, červenka, modřinka, sojka, vrabec). Rozvrh ptáka je čistá
funkce času (`birdState`): pryč → přílet → sedí a rozhlíží se → odlet. Trasy
chodců v `render.js` (`paths`) sledují cestičku přes `trailX()` z téhož souboru,
takže po úpravě cestičky se trasy posunou s ní.

Poměr velikostí druhů je v `render.js` v `motions.walk.scale` (kůň 1,0 → zajíc
0,36), protože `sizePx` modelu je odmocnina z plochy siluety a bez mapy vychází
všichni stejně velcí. Výchozí zbarvení je ve `scene.json` v bloku `paint`.

## Všichni

Kostra nemá chodidla — noha končí kostí `*LowerLeg`. Krok se proto měří ze
špiček nohou (`FrontLowerLeg.L_end`…, viz `feetOf()` ve `web/scene3d.js`).
`stride_rate` je nastavený blízko přirozenému tempu klipu Walk (0,57–0,81 těl/s
při timeScale 1); s výchozím 0,12–0,22 ze scény by zvířata šla zpomaleně.
Psovité šelmy (liška, vlk, pejsek) jdou o kousek svižněji.

## stag

Parohy jsou samostatný mesh zavěšený na kost Head (bez skinu); import je
převádí na skin s jedinou kostí. Patří tak k hlavě, a proto obálka hlavy sahá
až do parohů — oko by skončilo u jejich kořene, `eye_bias` ho posouvá dolů
a dopředu do hlavy.

## Ptáček (`bird`)

Vlastní model z `tools/make_bird.py` (žádný volný ptačí model nemá kostru ani let):
nízkopolygonový zpěvný pták s kostrou, klipem `Fly` (rozevře a mává křídly) a `Perch`
(složená křídla, rozhlíží se). Složená póza je klidová, v ní se kreslí předloha
(bokorys) a sezení je jen jiná váha téhož modelu, takže při přistání a vzletu se
křídla skládají a rozkládají sama. Motion `bird` nemá chůzi: `updateBird` ve
`web/scene.js` ho nechá přiletět, usednout na volné místo na větvi
(`backdrop.perches` / `backdrop.claim` z `forest.js`), chvíli sedět a odletět.
Dvojrozměrní ptáci sedí na týchž místech, proto si místo předem zabere.
Ve scéně se ptáčci sami nedoplňují (jen vybarvení).

## Odložená alpaka

Alpaka do lesa nepatří, proto je ve `scene.json` pod klíčem `parked` (loader ho
ignoruje), ne mezi `creatures`. Nic se nemaže: zůstává model
(`data/models_src/alpaca.glb`), vyexportované GLB a textura v `data/models3d/`,
tvar předlohy, šablona k tisku a index značky v `scenes/markers.json` (ten se
nikdy nevrací). Až bude scéna, kam patří, stačí záznam přesunout do `creatures`
té scény a pustit `python tools/model_export3d.py alpaca`.
