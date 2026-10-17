# Živější zvířata a nové scény — možnosti a plán průzkumu

Stav k 2026-10-17. Cíl: zvířata, která chodí, zastaví se, otočí, podívají se na
děti, vyskočí, lehnou si, žerou… a postup, jak k tomu dělat nové scény bez
závislosti na tom, co zrovna jde stáhnout.

## Co je dnes a kde jsou hranice

**Chování** (`web/scene.js`) je sada příznaků, ne stavový automat: chůze, stání
(jen ve frontě, na zastávce trasy nebo u jídla), otočka na místě, a když zvíře
čeká, občas si lehne (klip Death zastavený na konci) nebo vyskočí. Letci a
plavci nikdy nezastaví. Hlava se nikam neotáčí — všechno jsou klipy.

**Klipy** máme jen ty, které přinesly stažené modely:

| sada | klipy | nevyužité |
|---|---|---|
| dinosauři (Quaternius) | Idle, Walk, Run, Jump, Attack, Death | Run, Attack |
| drak | Flying, Flying_Idle, Death, Headbutt, Yes, No… | skoro vše |
| ryby | Swimming_Normal/Fast/Impulse, Attack, Death | Impulse, Attack |
| manta, ptakoještěr, axolotl | jediný klip plavání/letu | — |

Chybí: sednout, lehnout (skutečně, ne „umřít“), spát, žrát, rozhlédnout se,
podívat se na diváka, hrát si.

**Tvrdá hranice z vybarvování:** textura je fotka listu promítnutá z boku (nebo
shora). Obě strany zvířete mají stejnou kresbu a čelo/hrudník jsou rozmazané.
Měřeno: do ~30° natočení k divákovi to drží, od 45° je hrudník a čelo šmouha,
nad 60° nečitelné. Z toho plyne:

- „podívat se na děti“ = **otočit hlavu/krk** o pár desítek stupňů, ne celé tělo;
- pózy daleko od pózy předlohy (útok, válení se) kresbu kroutí — každý nový
  klip je potřeba zkontrolovat na vybarvené textuře, ne na modelu;
- model musí mít čitelnou siluetu z boku (nebo shora) — to omezuje, jaké
  zvíře se vůbec hodí.

## Možnosti

### A. Chování ve scéně (kód, nezávislé na modelech)

1. **Plánovač činností** místo příznaků: každé zvíře si vybírá další činnost
   z nabídky svého druhu (jdi / zastav se a rozhlédni / podívej se na děti /
   žer / sedni / lehni / spi / vyskoč / zaběhni si / hraj si s jiným), s váhami
   a délkami v datech scény (`render.js`) a druhu (`scene.json`). Činnost, ke
   které druh nemá klip, se prostě nenabízí.
2. **Procedurální hlava:** po `mixer.update()` natočit kosti krku a hlavy
   k bodu před televizí (rozdělit úhel mezi krk a hlavu, omezit na ~35°).
   Bez knihovny, pár desítek řádků v `scene3d.js`. Funguje se všemi modely,
   které mají kost hlavy.
3. **Aditivní vrstvy** (three.js `AnimationUtils.makeClipAdditive`): dýchání,
   vrtění ocasem, mrknutí přes chůzi i stání — zvíře „žije“, i když stojí.
4. **Interakce:** býložravec uteče před T-rexem, nízký přelet ptakoještěra
   vyleká chodce, dvě zvířata se k sobě otočí a „pozdraví“ (nápady už jsou
   v `out/audit/researcher.md`).

### B. Odkud brát modely a klipy

| cesta | co dá | háček |
|---|---|---|
| **B1 Quaternius Ultimate Animated Animals** (CC0, glTF) | 12 zvířat (kráva, osel, alpaka, jelen, liška, pes, vlk, kůň…), ~12 klipů: Idle, Idle_2, Idle_Headlow, Walk, Gallop, Jump, Eating, Attack, Death… | žádné sedni/lehni/spi; jen farma/les |
| **B2 Vlastní klipy v Blenderu** na staženou kostru (bpy skript, Blender je v PC) | přesně ty klipy, které chceme, s našimi jmény | ruční/skriptová práce na každou kostru |
| **B3 Šablona kostry pro typ těla** (čtyřnožec, pták, ryba, hmyz, had) + generátor klipů v Blenderu | každé nové zvíře „navlečené“ na šablonu zdědí celou sadu klipů | nejvíc práce na začátku; navlékání tvaru na kostru je potřeba ladit |
| **B4 AI model** (Hunyuan3D/Rodin přes Blender MCP, Meshy, Tripo) | rychlý nový tvar zvířete v libovolném stylu | rig dají, klipy ne (Tripo/Meshy u zvířat jen chůze) → kombinovat s B3 |
| B5 Cizí balíčky (Kenney Cube Pets, Gobkit, Cozy Animals — CC0) | rychlá náhrada | jiný styl, 3–5 klipů |
| B6 Synty, Truebones | hodně zvířat / mocap | licence (instalace, žádné AI), jiný styl — nebrat |

Nové balíčky od Quaternia (od 2026-08) mají vlastní licenci QAL (volné použití,
nesmí se šířit jako assety) — pro stanici v pořádku, jen to hlídat v CREDITS.

### C. Nová scéna jako celek

Scéna = krajina (2D backdrop, zatím zůstává) + sada zvířat ve stejném stylu +
nabídka činností. Aby to vypadalo dobře, rozhoduje **jednotný styl** (low-poly,
plochá barva — sedí na vybarvování) a **čitelná silueta z boku**. Kandidáti:
Farma, Les, Savana, Džungle, Arktida, Hmyz/louka.

## Plán průzkumu (malé pokusy s jasným „ano/ne“)

Každý pokus na kopii dat (`tmp/`), na živou stanici až po schválení.

1. **Hlava k dětem** (A2) — T-rex a velociraptor: procedurální natočení krku
   a hlavy k divákovi při stání. *Ano, když:* na vybarvené textuře do 35° není
   šmouha a pohyb nepůsobí jako zlomený krk. ~půl dne.
2. **Quaternius farma/les** (B1) — stáhnout Ultimate Animated Animals, import
   `tools/scena.py import` do zkušební scény „Les“, ověřit jména klipů, předlohy
   (čitelnost z boku), `tools/gait_report.py` (prokluz < 3 %). *Ano, když:*
   aspoň 6 zvířat projde bez ručních výjimek a předlohy jsou pro děti poznat.
3. **Vlastní klipy v Blenderu** (B2) — na jednu kostru (liška nebo T-rex) skriptem
   přidat Sit, LieDown, Sleep, LookAround; export, kontrola ve scéně a na
   vybarvené textuře. *Ano, když:* klip vypadá přirozeně a skript jde pustit
   na další kostru téhož packu jen se změnou mapy kostí.
4. **Plánovač činností** (A1) — přepsat příznaky na činnosti s váhami v datech;
   nejdřív s dnešními dinosaury (+ Run, Attack jako „zaběhnout si“, „hrát si“),
   pak s klipy z bodu 3. Současně povýšit `tmp/test_zastaveni.py` na test.
   *Ano, když:* scéna 10 minut bez zaseknutí, žádné zvíře nezamrzne uprostřed
   kroku, `gait_report` drží.
5. **AI tvar + šablona kostry** (B4 + B3) — vygenerovat jedno zvíře, které
   v packu není (zajíc, ježek), navléct na kostru z bodu 3 a zdědit klipy.
   *Ano, když:* výsledek stylově sedí k Quaterniovi a navlečení zabere
   do hodiny. Když ne, nové scény se drží balíčků + B2.
6. **Aditivní život** (A3) a **interakce** (A4) — až po 4.

Rozhodovací body: po 1+2 se ví, jestli farma/les jde rychle; po 3 jestli umíme
vlastní klipy; po 5 jestli nové scény mohou mít libovolná zvířata.

## Standardní slovník klipů (návrh)

Role, na které se chování odkazuje (rozšíření `CLIP_FOR_DEFAULT`):
`move, run, stand, look, eat, sit, lie, sleep, jump, play, react`, u letců
`glide, land`, u plavců `fast, turn`. Druh mapuje role na svoje klipy ve
`scene.json` (`clip_for`) a import (`tools/scena.py`) hlásí, které role chybí.

---

# Pracovní plán

Větev `zvirata`. Každý úkol běží v **samostatné pracovní kopii (git worktree)**
na vlastní větvi `zvirata-<úkol>`, výsledek se slučuje do `zvirata`. Do `main`
až po Pavlově schválení.

## Společná pravidla pro všechny úkoly

- **Živá stanice je tabu.** Na `:8100` (kontejner `dinostanice`) ani na
  `data/catch`, `data/config`, `data/trash` hlavní kopie se nesahá, žádné
  `docker compose`. Ověřuje se na izolovaném serveru z vlastní pracovní kopie
  (`DINO_ADMIN_CODE=TEST42 python -m uvicorn server:app --port <port>`), porty:
  úkol 1 → 8131, úkol 2 → 8132, úkol 3 → 8133, úkol 4 → 8134, úkol 5 → 8135.
  Server se po sobě zastaví (podle PID na portu, nikdy hromadně).
- **Blender:** `E:\FS25-edit\blender-5.1.2-windows-x64\blender.exe`, jen
  headless (`-b`). Nikdy `taskkill /IM blender.exe` — zabil by i Pavlův Blender.
- Soubory jen uvnitř pracovní kopie (pracovní věci do `tmp/`, ten je v
  `.gitignore`). Disk `V:` je zakázaný.
- Kód jako okolní kód: komentáře jen tam, kde není zřejmé *proč*; žádné nové
  závislosti bez důvodu.
- `python -m pytest -q` musí zůstat zelený; `tools/gait_report.py` (proti
  izolovanému serveru, `--url http://127.0.0.1:<port>/tv?scene=cretaceous`)
  nesmí zhoršit prokluz nad 3 %.
- Vizuální ověření = screenshoty Playwrightem (swiftshader) do `tmp/`, včetně
  **vybarvené** textury (synteticky: `tests/helpers.py` → `H.sheet(key, strokes=40)`
  a upload přes `/pridat`), ne jen ukázkové.
- Na konci: commit do své větve (anglicky, krátce, proč), krátká zpráva
  `docs/zvirata/<úkol>.md` (co se zjistilo, čísla, screenshoty v textu
  popsané, verdikt ano/ne podle kritéria), a výsledek nahlásit.

## Úkol 1 — Hlava k dětem (A2)

**Cíl:** stojící chodec občas natočí krk a hlavu k divákovi (do kamery), chvíli
kouká, pak zpátky. Celé tělo se k divákovi neotáčí.

- `web/scene3d.js`: po `mixer.update()` v `render()` aplikovat na kosti krku
  a hlavy dodatečnou rotaci (yaw k divákovi + mírný pitch), rozdělenou
  např. 40 % krk / 60 % hlava, celkem omezenou (`look.max`, výchozí 35°),
  plynule (`look.fade`). API typu `Scene3D.look(m3, weight)`.
  Kosti najít podle jména (`/neck/i`, `/head/i`; u ryb `Main1`) při `spawn`,
  chybějící kost = funkce se tiše vypne.
- Směr „k divákovi“: kamera je ortografická, divák je na +Z (viz `place()`
  a `spin.rotation.y = face * yaw`). Počítat v lokálním prostoru kosti,
  ne naslepo `rotation.y`.
- `web/scene.js`: nová krátká činnost při stání (`waiting()` nebo zastávka
  u jídla): s pravděpodobností z dat scény (`motions.walk.look: {chance, hold:[min,max]}`
  v `scenes/cretaceous/render.js`) zvíře „koukne na děti“. Nová zvířata od
  dětí kouknou vždy krátce po příchodu, jakmile poprvé zastaví.
- Ladicí vstup `DinoScene.debugLook(i)` pro Playwright.
- **Kritérium:** screenshoty T-rexe, velociraptora a triceratopse s vybarvenou
  texturou při 0/20/35° — bez šmouhy na čele, krk nevypadá zlomený; scéna
  bez chyb v konzoli; `gait_report` beze změny.

## Úkol 2 — Testovací scéna „Les“ z Quaternia (B1)

**Cíl:** ověřit, že hotový CC0 balíček zvířat projde naší pipeline a dá
použitelnou scénu.

- Stáhnout **Ultimate Animated Animal Pack** (Quaternius, CC0) — glTF/GLB
  (poly.pizza bundle nebo quaternius.com). Uložit do
  `scenes/les/modely/` (velké zdroje necommitovat, jen to, co je potřeba
  pro import; zvážit `.gitignore` pro `scenes/*/modely/`).
- `python tools/scena.py nova les --z cretaceous --label "Les"`, upravit texty
  ve `scene.json` (zvíře/zvířata, žrádlo „zvířátka se seběhnou“ atd.).
- `python tools/scena.py import les` (s Blenderem). Zaznamenat, co import
  hlásí; doladit `clip_for`, `poses`, `eye_joint`, `axes` u každého zvířete.
- Vypsat skutečná jména klipů každého zvířete do zprávy (Idle, Eating,
  Gallop…).
- Prohlédnout náhledy předloh `out/<zvíře>_sheet.png` — je zvíře z boku pro
  dítě poznat? Vybrat 6–8 nejlepších, ostatní vyřadit.
- Krajina: zatím dočasně stejný backdrop jako křídová laguna (`render.js`
  zkopírovaný), nové kreslení krajiny není součást úkolu.
- `CREDITS.md`: zdroj a licence.
- Na izolovaném serveru: scéna `les` běží, zvířata chodí, `gait_report`
  pro les (`?scene=les`) — prokluz < 3 % (případně doplnit `stride_rate`).
- **Kritérium:** aspoň 6 zvířat projde importem bez ručních zásahů do kódu,
  předlohy jsou čitelné, prokluz < 3 %, upload vybarvené předlohy funguje.

## Úkol 3 — Vlastní klipy v Blenderu (B2)

**Cíl:** nástroj, který na existující kostru dopíše chybějící klipy.

- `tools/blender_clips.py` (headless bpy): vstup GLB + mapa kostí (JSON:
  které kosti jsou páteř, krk, hlava, ocas, nohy přední/zadní L/P), výstup GLB
  s přidanými akcemi **Sit, LieDown (lehnutí + držení), Sleep (leží, dýchá),
  LookAround (rozhlédnutí vlevo/vpravo), Stretch/Shake (volitelné)**. Klíčové
  snímky skriptem (rotace kostí), smyčky kde dávají smysl. Původní klipy
  zůstanou beze změny.
- Pokus na **T-rexovi** (`data/models_src/trex.glb`) a **triceratopsovi**
  (čtyřnožec) — mapa kostí pro každého v `tools/clipmaps/<model>.json`.
- Kontrola: `python tools/scena.py kontrola`-style načtení přes
  `dinostanice.gltf.Model` (klipy jsou vidět, `posed()` dává rozumný tvar),
  renderované náhledy póz (Blender render nebo Playwright v `/dino3d`)
  a **na vybarvené textuře** (lehnutí nesmí kresbu rozbít).
- Výstup **nepřepisuje** `data/models_src/*.glb` — ukládá do `tmp/` nebo
  `data/models_src/<model>_clips.glb`; zapojení do katalogu je až úkol 4.
- **Kritérium:** póz si všimne dítě (sedí/leží/spí je poznat), kresba drží,
  skript jde přenést na druhý model jen změnou mapy kostí.

## Úkol 4 — Plánovač činností (A1) — po úkolech 1 a 3

- `web/scene.js`: příznaky `pause/fun` nahradit činnostmi (walk, stand, look,
  eat, sit, lie, sleep, jump, run, play) s váhami/délkami z dat scény a druhu;
  činnost bez klipu se nenabízí; nic nesmí zamrznout v půlce kroku (chybějící
  Idle → zvíře nezastaví).
- `dinostanice/creatures3d.py`: rozšířit `CLIP_FOR_DEFAULT` o nové role;
  `tools/scena.py` hlásí chybějící role jako varování, ne chybu.
- Zapojit klipy z úkolu 3 pro T-rexe/triceratopse.
- Logiku plánovače vyčlenit tak, aby šla testovat bez prohlížeče
  (`web/scenelogic.js` + `node --test`, viz PLAN.md bod 12) a povýšit
  `tmp/test_zastaveni.py` na skutečný test.
- **Kritérium:** 10 min běhu bez zaseknutí a bez chyb, `gait_report` drží,
  testy zelené.

## Úkol 5 — AI tvar + šablona kostry (B4 + B3) — po úkolu 3

- Vygenerovat zajíce nebo ježka (Blender MCP Hunyuan3D/Rodin, případně
  Tripo) v low-poly stylu, navléct na kostru čtyřnožce z úkolu 3 (Blender:
  automatické váhy), zdědit klipy, import do scény `les`.
- **Kritérium:** stylově sedí k Quaterniovi, navlečení do hodiny práce,
  předloha čitelná.

## Pořadí a souběh

| vlna | úkoly | proč souběžně |
|---|---|---|
| 1 | 1, 2, 3 | každý sahá jinam (scene3d/scene.js · scenes/les + data · tools/blender_clips) |
| 2 | 4 | potřebuje 1 (look) a 3 (klipy) |
| 3 | 5, 6 | potřebuje 3; aditivní život a interakce staví na 4 |

Po každé vlně: sloučit do `zvirata`, pustit testy, krátká zpráva Pavlovi
se screenshoty a rozhodnutím, jestli pokračovat.
