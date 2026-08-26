# PLAN — audit a vylepšení DinoStanice

Syntéza nálezů z auditu 8 rolí (2026-08-26). Podklady: `out/audit/*.md`
(architekt, backend, frontend, tester, animator, ux, siluety, researcher).
Priority podle Pavlových přání; body 3 (stabilita) a 12 (testy) jsou vsunuté
z review, protože jsou levné a chrání všechno ostatní.

Legenda stavu: ☐ čeká · ◐ rozpracováno · ☑ hotovo · ✗ odloženo

---

## 1. ☐ Klouzání chodidel — fázově vázaná rychlost  [priorita 1a]

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

## 2. ☐ Přirozené tempo per druh  [priorita 1b, po bodu 1]

- `STRIDE_RATE` per druh (trex 0.11–0.18, apatosaurus 0.05–0.09, … tabulka
  v `out/audit/animator.md`), `GAIT_RATE` rozšířit na 0.4–1.8 (dnes cíle
  ořezává — trex se vždy zarazil o min 0.6, proto vůbec dostal BAKED).
- `BAKED` po bodu 1 přeladit jen přes `rate`.
- `tmp/mereni_chuze.py` povýšit na `tools/gait_report.py`: regresní kontrola
  prokluzu (≤ 2 %) + report těl/s, px/s, přejezd, cyklus per druh proti cílům.
- Do `DinoScene.where()` přidat `speedPx`, `bodiesPerS`, `cycle`.

Závislosti: bod 1 (bez něj ladění temp nemá smysl). Odhad: S.

## 3. ☐ Kritická stabilita TV a serveru  [vsunuto z review — levné, chrání exponát]

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

## 4. ☐ Vrstvy scény + zákaz chůze po vodě  [priorita 2]

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

## 5. ☐ UX: QR sekce + reset + start od nuly  [priorita 3]

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

## 6. ☐ Sessions s auto-cleanup  [priorita 4]

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

## 7. ☐ Opravy siluet a šablon  [priorita 6, ale nezávislé — lze kdykoli]

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
- Tenké dvojlinkové fragmenty: filtr podle šířky (`4*plocha/obvod < 2 mm`) — M,
  může počkat.
- Ověření: přegenerovat, `out/audit_siluet/` náhledy očima, audit skript znovu.

Závislosti: žádné. Odhad: M (vč. regenerace a vizuální kontroly).

## 8. ☐ Více scén + katalog per scéna  [priorita 5]

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

## 9. ☐ Trasy zvířat (waypointy per scéna)  [priorita 1c — přirozený pohyb]

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

## 10. ☐ Mrtvý kód — úklid  [priorita 7]

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
   zatím NECHAT zamrzlou (doma existují staré výtisky 0–7), jen zdokumentovat
   v ARCHITECTURE jako „zamrzlé, odstranit až se vyhodí staré listy".

Závislosti: žádné. Odhad: M.

## 11. ☐ Nápady z rešerše (volitelné, nice-to-have)  [priorita 7]

Podle `out/audit/researcher.md`, nejvyšší poměr efekt/práce:
- Ohlášený vstup nového úlovku (vždy zleva za okrajem) + jmenovka nad tvorem
  na pár sekund; mobil po uploadu: „sleduj levý kraj televize!" (teamLab vzor). S
- „Hodit žrádlo" z mobilu → chodci k němu zamíří (jediná interakce s TV). M
- Útěk býložravce před blížícím se trexem / vyplašení skokem (ekosystém). M
- Rotace úlovků nad kapacitu („odešel na výlet, vrátí se") místo vytlačení. M
- Odchod tvora vždy odehrát (odejde za okraj), nikdy pop. S

## 12. ☐ Testy  [průběžně, podle `out/audit/tester.md`]

- HNED (S): oživit `test_roundtrip` — filtr `if not c.rigid` (dnes se celý
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

## Rozhodnutí učiněná bez Pavla (k revizi)

- Session cleanup úlovky NEMAŽE — scéna „usne", data zůstanou (mazání dětských
  výtvorů automatem je destruktivní; explicitní reset existuje v bodu 5).
- `quality.py` se zapojuje, ne maže.
- Stará 2D rig větev a `inflate.py`/`model3d.py` se zatím nemažou (staré
  výtisky doma, znalost pod testy) — jen se odpojí `/3d` stránka mrtvá daty.
- Obrys šablon se zvětší o ~2 mm ven → nové výtisky se rozejdou se starými;
  starým výtiskům pomůže větší bleed v to_texture (fallback zůstane).
