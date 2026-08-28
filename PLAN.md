# PLAN — audit a vylepšení DinoStanice

Syntéza nálezů z auditu 8 rolí (2026-08-26). Podklady: `out/audit/*.md`
(architekt, backend, frontend, tester, animator, ux, siluety, researcher).
Priority podle Pavlových přání; body 3 (stabilita) a 12 (testy) jsou vsunuté
z review, protože jsou levné a chrání všechno ostatní.

Legenda stavu: ☐ čeká · ◐ rozpracováno · ☑ hotovo · ✗ odloženo

---

## 1. ☑ Klouzání chodidel — fázově vázaná rychlost  [priorita 1a]

Změřeno (`out/audit/animator.md`): stojná noha se v klipu hýbe 12–172 %
průměrné rychlosti (RMS ~50 %), konstantní rychlost scény tedy nemůže sedět
nikdy; BAKED `speed` 0.75/0.6 klouzání navíc zdvoj- až ztrojnásobuje
(trex 30 %, triceratops 51 % zpětného prokluzu).

- `web/scene3d.js`: `strideOf()` vrací a cachuje `{travel, cum}` (kumulativní
  posun stojné nohy po fázi klipu, 32 vzorků); `spawn()` uloží
  `handle.phaseCum`; nový export `Scene3D.walked(handle, dt)` — kolik těl tvor
  ujde za `dt` při aktuálním `timeScale` (čte `action.time`, neposouvá ho).
- `web/scene.js` `update()`: 3D chodec s `natural` jede po
  `walked()*bodyFrac*speedMul` místo `speed*(1-mix)*dt`; `applyGait` dostane
  `speedMul`; z `BAKED` smazat `speed` korekce.
- Interakce zdarma: mix zastávky (walked čte timeScale), drift/bodyFrac,
  tune.js rate. Pořadí `update → draw → Scene3D.render` už garantuje shodné dt.
- Ověření: `tmp/mereni_chuze.py` — zpětný prokluz má klesnout z 10–51 % na ≤ ~3 %.

Závislosti: žádné. Odhad: S/M (~40 řádků ve 2 souborech + měření).

## 2. ☑ Přirozené tempo per druh  [priorita 1b, po bodu 1]

- `STRIDE_RATE` per druh (trex 0.11–0.18, apatosaurus 0.05–0.09, … tabulka
  v `out/audit/animator.md`), `GAIT_RATE` rozšířit na 0.4–1.8 (dnes cíle
  ořezává — trex se vždy zarazil o min 0.6, proto vůbec dostal BAKED).
- `BAKED` po bodu 1 přeladit jen přes `rate`.
- `tmp/mereni_chuze.py` povýšit na `tools/gait_report.py`: regresní kontrola
  prokluzu (≤ 2 %) + report těl/s, px/s, přejezd, cyklus per druh proti cílům.
- Do `DinoScene.where()` přidat `speedPx`, `bodiesPerS`, `cycle`.

Závislosti: bod 1 (bez něj ladění temp nemá smysl). Odhad: S.

## 3. ☑ Kritická stabilita TV a serveru  [vsunuto z review — levné, chrání exponát]

Frontend (`out/audit/frontend.md`): scéna běží hodiny, dnes ji položí:
- A3 rAF smyčka bez záchytné sítě (výjimka = zamrzlá TV navždy) + A4 žádná
  reakce na `webglcontextlost` → reload.
- A1 `texCache` leak ~12 MB VRAM/úlovek (refcount + dispose) + A2 `restoreCast`
  bootuje všechny úlovky místo posledních 18 (`slice(-MAX_ACTORS)` + `?limit=`).
- A5 WS: rekonciliace podle `id` na `onopen`, dedup v `addActor`, ping/watchdog,
  backoff.
- B1 skeleton dispose, B2 glbCache nepamatovat rejected promise, B3 onError
  textury + náhradní, B4 topUp re-entrance, B6 remove všech výskytů id,
  B8 makeRoom priorita ambient, B9 auto-clear chybové hlášky.

Backend (`out/audit/backend.md`):
- P0-1 limit uploadu podle Content-Length před parsováním; P0-2 pixel budget
  před dekódováním + cv2 fallback jen pro neznámý formát; P0-3 semafor(1–2)
  kolem pipeline + `cv2.setNumThreads`; P0-4 broadcast s timeoutem přes gather.
- P1-5 logging (+ `data/rejected/` pro odmítnuté fotky); P1-6 degenerovaný
  poměr stran; P1-7 mazání přes `os.replace` na `<id>.deleted`; P1-8 kontrola
  `imwrite`/`imencode`.

Závislosti: žádné (bod 1 mění tatáž místa ve scene.js — koordinovat pořadí).
Odhad: M celkem (samé S položky + 2 M).

## 4. ☑ Vrstvy scény + zákaz chůze po vodě  [priorita 2]

- Zóny jako data: `bands: [{name, y0, y1, motions, lane}]` místo pěti pevných
  jmen (architekt A2); `zone()` a `swapBand` vybírají z dat („pásy, které umí
  tento pohyb"), FALLBACK_ZONES zmizí. Chodci tím dostanou formální zákaz vody:
  walk pásy jsou jen břehy, drift clampovaný na pás.
- Více vrstev popředí: `Backdrop.drawFront` rozdělit na vrstvy s hloubkou
  (např. kapradí za předním pásem × kapradí úplně vpředu), scéna kreslí tvory
  mezi ně podle `yFrac` — rostliny skutečně před i za tvory. Technicky: buď
  víc 2D pláten, nebo drawFront(ctx, W, H, t, layer).
- Drift škálovat výškou pásu (frontend C9 — kmitání v úzkém shoreFar).

Závislosti: žádné tvrdé; dělá základ pro body 8 (více scén) a 9 (trasy).
Odhad: M.

## 5. ☑ UX: QR sekce + reset + start od nuly  [priorita 3]

Podle `out/audit/ux.md` (a, c, d):
- a) QR panel: přesun do pravého horního rohu, stavy plný/mini (auto-zmenšení
  po ~90 s nebo po prvním `add`, připomenutí po 10 min klidu), `H` = override.
  Žádné nové API.
- c) Prázdná vs. ukázková scéna: přepínač `ambient` — `GET/POST
  /api/scene/settings`, broadcast `settings`, scéna přestane doplňovat
  (stávající tvorové odejdou přirozeně). Nová stránka `/rezim` (mobilní admin,
  odkaz ze `/sablony`).
- d) Reset: seznam úlovků s mazáním na `/pridat` (inline potvrzení, existující
  `DELETE /api/rigs/{id}`); „Vyprázdnit vše" na `/rezim` → nový
  `POST /api/scene/reset` + broadcast `cleared` (scéna vyprázdní a topUp).

Závislosti: žádné. Odhad: M.

## 6. ☑ Sessions s auto-cleanup  [priorita 4]

Kombinace architekt D1–D4 + UX e):
- Server: `sessions: dict[str, Session]` (id, scene, clients, last_seen),
  `/ws?s=`, broadcast per session, `Hub` zaniká. TV bez `?s=` → server založí
  a redirectne; implicitní default session = dnešní chování jedné TV.
- QR kóduje `/pridat?s=<sid>`; upload nese session; `meta.json` dostane
  `session`; `/api/rigs?s=` filtruje.
- Nečinnost = žádný sken QR ani upload 15 min → 2min varování na TV (banner
  s odpočtem: „naskenuj QR, ať stanice neusne"); prodloužení = otevření
  `/pridat` (touch) nebo tlačítko „Ještě chvíli" na mobilu.
- Cleanup = **uspání scény** (ztmavnutí + velké QR „Stanice spí"), úlovky se
  NEMAŽOU (rozhodnutí: mazání dětských výtvorů automatem je kruté; maže
  explicitní reset z bodu 5). Probuzení skenem QR.
- Restart serveru: `/ws` s neznámým sid session tiše založí — reconnect scény
  ji obnoví.

Závislosti: bod 5 (stránka /rezim, reset API). Odhad: L.

## 7. ☑ Opravy siluet a šablon  [priorita 6, ale nezávislé — lze kdykoli]

Podle `out/audit/siluety.md` (5 z 8 ok koliduje s obrysem):
- `auto_eye` (`modelsheet.py:157-186`): kontrola přes `cv2.distanceTransform`
  s odstupem ≥ r+linka (~2,9 mm) místo testu jednoho pixelu; letec: oko na osu
  `SHEET_W_MM/2`.
- Drak: zafixovat pózu `Flying_Idle` + ručně vybraný čas (čitelnost, ne fill).
- Obrys o chlup větší: `OUTLINE_GROW_MM` ≈ 1,5–2 mm dilatace masky před
  trasováním v `modelsheet.build` (`:224`); vnitřní oblasti z původní masky;
  UV/Placement zůstávají na projekci → hrana modelu vzorkuje uvnitř vybarvené
  plochy. POZOR: přegenerovat SVG + shapes3d.json naráz; staré výtisky se
  rozejdou o ~2 mm (zdokumentovat).
- Artefakt triceratopse: `_trace` filtrovat plochu po `approxPolyDP`.
- ☑ Zjednodušení šablon (nález 5): vnitřní kresba už nejsou obrysy oblastí,
  ale hranice mezi nimi (`_trace_lines`), takže silueta se nekreslí dvakrát;
  drobné a úzké oblasti propadnou sousedovi (`_regions`, `MIN_REGION_MM2`,
  `MIN_REGION_WIDTH_MM`). 4-22 oblastí → 0-6 linek na tvora.
- Ověření: přegenerovat, `out/audit_siluet/` náhledy očima, audit skript znovu.

Závislosti: žádné. Odhad: M (vč. regenerace a vizuální kontroly).

## 8. ☑ Více scén + katalog per scéna  [priorita 5]

Architekt (souhrn v `out/audit/architekt.md`):
- Scéna jako data: `web/scenes/<key>.js` (backdrop import, lighting, bands,
  motions, ambientMin); backdrop na ES modul; `Scene3D.setLighting()`;
  TURN/BANK/anchor per motion (swim/sail pro budoucí ryby/ponorky).
- Katalog: `scene`, `gait`, `clipFor` na Model3D → catalogue3d.json;
  BAKED a hádání jmen klipů se stěhuje do katalogu.
  `/api/scenes/{key}/catalogue` filtruje; marker index zůstává globální.
- Přepínání scén: UX b) — karty na `/rezim`, `POST /api/scene/active`,
  crossfade na TV, úlovky cizí scény se nenačítají (nemažou).
- rig.json a Scene3D transformační jádro se NEMĚNÍ.

Závislosti: bod 4 (bands), bod 5 (/rezim), bod 6 (session nese scénu).
Odhad: L. Druhá scéna jako obsah (akvárium) = samostatný budoucí projekt;
tady jen mechanismus + případně backdrop varianta „noc" jako levný důkaz.

## 9. ☑ Trasy zvířat (waypointy per scéna)  [priorita 1c — přirozený pohyb]

Podle `out/audit/animator.md` bod 3:
- Formát `paths` v definici scény (po bodu 8; do té doby `web/paths.json`):
  waypointy v podílech obrazovky, `do: walk|stop|turn`, `dwell`, `species`
  filtr, loop/ping-pong.
- Follower ve scene.js: posun po segmentech z `walked()` (bod 1), izotropní
  interpolace, `face` ze znaménka dx, stop/turn přes stávající `rest()`
  mašinerii; tvor bez trasy jede postaru (drift + swapBand fallback).
- Editor v `tune.js`: sekce „trasy", klik přidá waypoint, tažení posune, pravý
  klik smaže, klik na bod cykluje typ; kreslení do horního plátna přes
  `Tune.drawOverlay`; persistence localStorage + „kopírovat JSON".

Závislosti: bod 1 (walked), bod 4 (bands/vrstvy). Odhad: M.

## 10. ☑ Mrtvý kód — úklid  [priorita 7]

Podle `out/audit/backend.md` (mrtvý kód) — pořadí:
1. Gate: `capture.known_indices()` přepsat bez závislosti na starém
   `CATALOGUE` (jinak nejde odpojit nic).
2. Smazat jistoty: `smooth_closed`, `raw_marker_count`, `MAX_CREATURES`,
   soubor `NUL`.
3. Stránka `/3d` + `api_models3d` + `api_template_texture` +
   `model3d.html/js` + `rig.sheet_for_texture` (odpojené daty, bez odkazů).
   `inflate.py`/`model3d.py` + testy zatím NECHAT (jediný zdroj pravdy
   o metodě „jedna spojitá kůže") — rozhodnutí zapsat sem.
4. `quality.py`: ZAPOJIT do `process()` (české rady dětem mají hodnotu),
   sladit `MARKERS_MIN_OK` s `MIN_MARKERS` — ne smazat.
5. Stará 2D rig větev (`rig.py`, `creatures.py`, `rigrender.js`, `anim.js`…):
   ☑ SMAZÁNA (2026-08-27, Pavlovo rozhodnutí) — i `inflate.py`/`model3d.py`
   a generátory ze siluet. Indexy značek 0–7 jsou tím uvolněné pro budoucí
   tvory, 3D tvorové zůstávají na 8–15 (listy jsou vytištěné). Testy snímání,
   registrace, robustnosti a kvality přepsané nad 3D katalog, ne zrušené.

Závislosti: žádné. Odhad: M.

## 11. ☑ Nápady z rešerše (body 1, 2, 5 hotové; zbytek odloženo)  [priorita 7]

Podle `out/audit/researcher.md`, nejvyšší poměr efekt/práce:
- Ohlášený vstup nového úlovku (vždy zleva za okrajem) + jmenovka nad tvorem
  na pár sekund; mobil po uploadu: „sleduj levý kraj televize!" (teamLab vzor). S
- „Hodit žrádlo" z mobilu → chodci k němu zamíří (jediná interakce s TV). M
- Útěk býložravce před blížícím se trexem / vyplašení skokem (ekosystém). M
- Rotace úlovků nad kapacitu („odešel na výlet, vrátí se") místo vytlačení. M
- Odchod tvora vždy odehrát (odejde za okraj), nikdy pop. S

## 12. ◐ Testy  [průběžně, podle `out/audit/tester.md`]

- ☑ HNED (S): oživit `test_roundtrip` — filtr `if not c.rigid` (dnes se celý
  soubor tiše přeskakuje, prázdný parameter set).
- S bodem 3: server API testy (testclient + synth fotka): upload→catch+kind,
  vadná fotka→česká chyba, DELETE, WS broadcast, limity.
- S bodem 1/4: extrakce čisté logiky scény do `web/scenelogic.js` (bez DOM,
  bez three) + `node --test` — swapBand, rest/mix, applyGait, okraje.
- S bodem 6: testy izolace sessions.
- Povýšit `tmp/test_zastaveni.py` (má hotové invarianty) na řádný e2e test.
- Vizuální kontrola po každém bodu: `tools/shot_scene.py` (funguje, exit 1 při
  JS chybě); `tools/shot3d.py` má mrtvý default port 8000 → opravit/odstranit
  s bodem 10.

---

## Pořadí realizace (fáze 3)

1 → 2 → 3 (+ roundtrip fix) → 4 → 5 → 7 → 6 → 8 → 9 → 10 → 11 (výběr) → 12 průběžně.

Zdůvodnění: 1+2 je Pavlova priorita č. 1 a nemá závislosti; 3 je levná ochrana
všeho dalšího (a sahá do týchž souborů jako 1 — udělat hned po něm, ať se
nehádají); 4 je priorita 2; 5 priorita 3; 7 (siluety) je nezávislé a krátké,
vsune se před velké 6/8; 6 sessions staví na 5; 8 staví na 4+5+6; 9 na 1+4.

## Incident (2026-08-26 večer)

Při ověřování bodu 5 agent zavolal `POST /api/scene/reset` proti živému
kontejneru a nenávratně smazal 4 reálné úlovky (Kuba/Triceratops,
Dino/Triceratops, Pavel/Tyrannosaurus, Velociraptor). Záloha neexistovala
(`out/catch-zaloha` je starší sada, `.dockerignore` vylučuje data/catch
z image). Fotky zůstávají v mobilech — jde je nahrát znovu. Náprava:
mazání teď jde do `data/trash/` s 30denní retencí (commit a01c7a8).
Pravidlo pro další práci: destruktivní ověřování VÝHRADNĚ proti
izolovaným datům (TestClient + tmp_path), nikdy proti běžícímu serveru.

## Rozhodnutí učiněná bez Pavla (k revizi)

- Session cleanup úlovky NEMAŽE — scéna „usne", data zůstanou (mazání dětských
  výtvorů automatem je destruktivní; explicitní reset existuje v bodu 5).
- `quality.py` se zapojuje, ne maže.
- ~~Stará 2D rig větev a `inflate.py`/`model3d.py` se zatím nemažou~~ —
  překonáno: Pavel 2026-08-27 rozhodl celou větev smazat (je v git historii).
- Obrys šablon se zvětší o ~2 mm ven → nové výtisky se rozejdou se starými;
  starým výtiskům pomůže větší bleed v to_texture (fallback zůstane).

---

## Stav po fázi 3 (2026-08-27)

**Hotovo (commitnuto po bodech):** 1–11 dle výše; testová sada 132 testů
(po smazání staré větve; 36 serverových), regresní brány
`tools/gait_report.py` (prokluz/tempo) a `tools/shot_scene.py` (JS chyby,
snímky), `tools/shot3d.py` přesměrován na /dino3d.

**Zbývá / odloženo a proč:**
- Bod 12: extrakce `scenelogic.js` + Node testy — odloženo; scene.js se
  během přestavby měnil v každém bodu, extrakce by se opakovaně rozbíjela.
  Chování je kryté Playwright ověřeními a gait_report bránou. Vhodný
  samostatný úkol, až se scene.js usadí.
- Bod 12: povýšení `tmp/test_zastaveni.py` na řádný e2e test — odloženo
  (tatáž závislost na usazení scene.js).
- Bod 11: rotace úlovků „na výletě" nad kapacitu, útěk před trexem,
  suvenýr/kartička — nápady zapsané v out/audit/researcher.md, neděláno.
- Frontend review C6 (trimTail eps per kanál), C8 (rychlost letců dle
  hloubky) — vědomě odloženo (kvalita obrazu, ne stabilita). B5 (2D rig
  prolínání zastávky) padlo se smazáním staré větve.
- Backend review P1-9 retence data/catch (strop počtu úlovků) a P1-10
  autentizace/zúžení /catch statiky — vyžaduje Pavlovo rozhodnutí
  (domácí LAN vs. Tailscale expozice).
- Stará 2D rig větev: SMAZÁNA (viz bod 10.5).

## Pavlovy opravy po zhlédnutí TV (2026-08-27)

Devět bodů zpětné vazby, vše hotovo (commity 17b272f, 424ee48, tento):
1 zadní pás tempo ×0.75 · 2 diskrétní dráhy (3 vpředu, 2 vzadu, výběr dle
obsazenosti, drift zrušen) · 3 kolize na dráze (zastavení s hysterezí, občas
skok; protijdoucí — otočí se menší; cooldowny proti deadlockům) · 4 stromy
ostrova zvětšené do popředí — zadní chodci mizí za nimi · 5 uživatelský editor
tras odstraněn (trasy jen v definici scény) · 6 rozcestník /sablony + /rezim
na QR panelu, patička na /pridat · 7 mini QR panel drží mikrořádek /sablony ·
8 redesign /sablony (klik na obrázek = tisk) + /dino3d ?mode=walk ·
9 apatosaurus/triceratops/stegosaurus zpomaleni v katalogu; gait_report čte
cíle z catalogue3d.json.

---

## Akvarijní kolo (2026-08-27)

Druhá scéna a šest tvorů pro ni — důkaz, že „scéna jako data" nese i jinou
krajinu než laguna s dinosaury.

1. ☑ **Šest rybích druhů se šablonami** (`4027df0`): klaunská rybka, žralok,
   čtverzubec, mečoun, perutýn, manta. Modely Quaternius CC0, bokorys (rybí
   profil je nejčitelnější), výjimka manta — shora, z boku je to tenká placka
   bez plochy k vybarvení. Značky 16–21; uvolněné indexy 0–7 se nerecyklují,
   doma jsou vytištěné listy staré větve s těmi indexy. Rybí armatura nemá
   joint `Head` (jointy `Main1..Main6`), proto nové pole `eye_joint` v katalogu.
   Šablony vyplňují list lépe než dinosauří (0,21–0,53 proti 0,08–0,30).
2. ☑ **Scéna akvárium s plaveckým chováním** (`b4a1398`): jeden vodní pás
   (0,15–0,66 výšky) se čtyřmi hloubkovými drahami; plavec nikdy nezastaví,
   otáčí se za pohybu, vlní se a driftuje kolem své dráhy, míjejícím se rybám
   uhýbá. Žádné `rest` (není klip zastávky ani důvod stát), žádné `paths`.
   Nové parametry definice scény: `scale`/`scaleDefault`, `speedSize`/`beatSize`,
   `wave`, `sway`, `chase`, `dash`, `dodge`, `turnEvery`/`turnMoving`/`spin`,
   `food.sink`. Krmení padá na hladinu a klesá ke dnu, ryby za ním plavou
   do hloubky.
3. ☑ **Výzva na QR panelu patří scéně** (`a40b5b3`): `invite: {title, sub}`.
   Akvárium prosilo děti, ať přidají dinosaura.
4. ☑ **Oprava třepání ryb** (`cfd20e0`): uhýbání se rozhodovalo z aktuální
   hloubky, která obsahuje jak samotné uhnutí, tak vlnění plavce — uhnutí si
   tak rušilo vlastní podmínku a přepínalo 9–38× za sekundu. Teď se rozhoduje
   ze stabilní cílové hloubky (`swimTargetY`) a jednou začaté míjení se drží
   do skutečného minutí v x. Měřeno (14 ryb, 60 s scénického času): viditelné
   změny svislého směru 23,5 → 0,2 za sekundu, délka uhnutí 20 ms → 3–13 s.
   Vypadlo z toho i špatné rozpočítání ryb na dráhy (3+1 místo 2+2+2+2).
5. ☑ **Testy odstíněné od živého stavu stanice** (`7ff8f6e`): fixtury patchují
   `server.STATE_PATH` do `tmp_path`. Bez toho čtou živý `data/state.json`
   a při scéně `aquarium` celý balík zatuhne navždy na `ws.receive_json()` —
   křídový úlovek neprojde scoping filtrem broadcastu. Platilo to i před
   rybami. Sada je teď 175 testů.
6. ☑ **Smazáno 5044 řádků staré 2D větve** (`36d9779`): `rig.py`,
   `creatures.py`, `rigrender.js`, `anim.js`, generátory ze siluet, routy `/3d`.
   Robustnostní testy zůstaly — přepsané nad 3D katalog, ne zrušené.

**Otevřené věci:**
- Perutýní šablona je z šesti nejslabší: ostny se kreslí jako samostatné pásky
  a tělo se opticky rozpadá. Prošlo se všech 12 fází animace, lepší póza není.
  Nabídnutá výměna za praporečníka čeká na Pavlovo rozhodnutí.
- Konvoj: dvě stejně rychlé ryby na téže dráze drží uhnutí i 30 s a plavou
  vedle sebe. Je to klidné a čitelné, ale kdyby to působilo jako „ryba
  zapomněla na svou dráhu", dá se doplnit strop na délku uhnutí.
- Dva žraloci na téže dráze si mohou nepatrně překrýt hřbety nebo ocasy
  (jsou vyšší než rozestup 0,11); naživo neověřeno. `dodge` jde na 0,065
  bez rizika oscilací.
- Regresní brána na plavce (obdoba `gait_report.py`) neexistuje. Měřicí
  harness je hotový v `E:\tmp\dinofish\fish_report.py`, chybí jen prahy
  na změny `dodge`/s a p95 |dy/dt|.
- Strop 25 tvorů z `DICT_4X4_100` (4 značky na list): přechod na
  `DICT_4X4_250` zvedne strop na 62 bez zneplatnění vytištěných listů
  (prvních 100 kódů je bit-identických, minimální Hammingova vzdálenost
  zůstává 3/16). Rozhodne se, až se přiblížíme limitu.

---

## Pohled zešikma (2026-08-27)

☑ Natočení tvorů k divákovi je teď parametr definice scény (`motions.<typ>.turn`,
`bank`), ne konstanta ve 3D vrstvě — úhel patří ke vzhledu krajiny (commit
`ff6d862`). Chodci v křídě 30°, ryby v akváriu 25° (dřív oba 19,5°); ryba
dostává méně, protože se poznává podle siluety, kterou natočení krátí (meč
mečouna, vějíř trnů perutýna). Kontaktní listy pro každý druh a pět úhlů:
`out/turn_walk_sheet.png`, `out/turn_swim_sheet.png`.

Strop je změřený (`out/turn_strop_walk_sheet.png`): do ~30° drží kresba spojité
plochy, kolem 45–50° se čelo hrudi a předek lebky mění ve šmouhu (tam textura
z listu není, jen barva protažená od obrysu), nad 60° je z dětské kresby mapa
bez vzoru. Prokluz chodidel zůstal 1,1–2,1 %, protože `strideBodies` bere průmět
kroku — větší natočení samo zmenší dráhu na cyklus.

Nedělá se (čeká na zadání): manta zůstane při jakémkoli natočení plátek, její
rozpětí leží podél pohledu — pomohl by jen náklon per druh (mapa jako `scale`).
Druhá cesta k plastičnosti je světlo: protisvětlo od strany kamery by
nízkopolygonovým modelům oddělilo hrany víc než dalších pět stupňů.

---

## Axolotl do akvária (2026-08-28)

☑ Patnáctý tvor, marker **22**. Rigovaný axolotl pod otevřenou licencí
neexistuje (Quaternius nemá obojživelníka, poly.pizza axolotla nemá vůbec,
OpenGameArt/Wikimedia nic, itch.io jen placené, CC0 balíčky Gobkit/KayKit
taky ne), animovaní jsou jen na Sketchfabu a jen pro přihlášené. Vzal se tedy
statický **CC-BY model od vildurra** a stáhl se přes **Objaverse** na
HuggingFace — veřejnou kopii CC-licencovaných Sketchfab modelů, kde UID
souhlasí se Sketchfabem, takže se licence dá ověřit na původní stránce (a taky
se ověřila, přes API). Kostru mu dopisuje `tools/make_axolotl.py`.

Rozhodnuto měřením, ne dojmem:

- **Projekce: shora.** Bokorys vyplní list 0,17 — pod žralokem (0,21), který je
  z rybí šestice nejhorší — a všech šest žaberních stonků v něm splyne v jediný
  roh nad hlavou. Pohled shora dá 0,25, čtyři nohy s prsty a stonky rozložené do
  stran (15,6 % obrysových pixelů patří žábrám).
- **Žábry se v klipu natrvalo nezametají.** Dopředu podél hlavy by přidaly na
  obrysu 15,6 → 17,4 %, dozadu 13,4 %; vlastní poloha z modelu je nejlepší
  z boku i shora, takže se nic nevymýšlí — jen chvění.
- **Oko `down=0,46`.** Na listu je rozdíl proti 0,30 pár milimetrů (auto_eye si
  kroužek dotlačí dovnitř obrysu), na modelu obrovský: nižší hodnoty ho položí
  na bok lebky, kde je plocha skoro rovnoběžná s pohledem shora, a z kroužku je
  bílá rozmazaná čárka. 0,46 ho posadí na temeno, kde vyjde jako kulaté oko.
- **`scale = 0,52`** v `aquarium.js`. Axolotl je dlouhý jako čtverzubec
  (dospělec ~25 cm), ale mnohem štíhlejší, a `scale` škáluje odmocninu z plochy
  siluety, ne délku: 0,52 mu dá stejnou délku na obrazovce (218 px proti 217 px
  na šířce 1920) a štíhlost si nechá. Při 0,68 by byl o třetinu delší.

Sada je teď 179 testů (identita, registrace, role klipů a existence souborů
jedou nad celým katalogem, takže nový druh je přidal sám). Kolo naostro přes
TestClient prošlo (4 značky, `axolotl-…`, textura i model.json). Svislá
stabilita ve scéně změřena vedle ostatních: 2,4 změny svislého směru za sekundu
proti 1,7–2,2 u ryb, tedy žádné třepání. Kontaktní list `out/axolotl_kontakt.png`.

**Otevřené věci:**
- Vějíř žaber se v obrysu předlohy neurovná do vějíře: stonky jsou nad sebou
  a v pohledu shora se kryjí s předními nohami, takže dítě uvidí spíš „mlok
  s ozdobami" než žábry. Na modelu (a tedy na televizi) jsou žábry
  nepřehlédnutelné, viz `out/axolotl_shots.png`.
- Axolotl je ve skutečnosti tvor dna, ale drží přidělené dráhy jako ryby.
  Spodní dráha per druh by šla dodělat (`bands[].lanes` + preference v katalogu),
  ale kvůli jednomu druhu se nový mechanismus scény nezaváděl.
