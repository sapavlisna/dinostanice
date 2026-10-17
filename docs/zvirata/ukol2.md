# Úkol 2 — Testovací scéna „Les“ z Quaternia

**Verdikt: ano.** Všech 12 zvířat z balíčku prošlo `tools/scena.py import les`.
Ve scéně jich zůstalo 7. Předlohy jsou čitelné, prokluz je u všech pod 3 %
a upload vybarvené předlohy funguje. Bez úprav kódu ale balíček neprošel:
narazil na čtyři obecné chyby v pipeline (viz níž). Po jejich opravě už další
zvíře nepotřebuje žádný zásah do kódu, jen řádek ve `scene.json`.

## Zdroj

*Ultimate Animated Animal Pack* (Quaternius, CC0), 12 GLB z poly.pizza bundle
`x-ILAPXeUYiS` (přímé odkazy `static.poly.pizza/<uuid>.glb` z dat stránky).
Zdroje jsou ve `scenes/les/modely/`, ten je nově v `.gitignore`
(`scenes/*/modely/`). Ve stromu jsou jen srovnaná GLB v `data/models_src/`.

## Klipy

Všechna zvířata mají kostru `AnimalArmature` (51 kloubů) a stejnou sadu klipů:

- **kopytníci** (alpaka, srnka, jelen, kůň, a vyřazení býk, kráva, osel, bílý kůň):
  `Attack_Headbutt, Attack_Kick, Death, Eating, Gallop, Gallop_Jump, Idle, Idle_2,
  Idle_Headlow, Idle_HitReact_Left, Idle_HitReact_Right, Jump_toIdle, Walk`
- **psovité** (liška, vlk, pejsek Shiba Inu, a vyřazený husky):
  `Attack, Death, Eating, Gallop, Gallop_Jump, Idle, Idle_2, Idle_2_HeadLow,
  Idle_HitReact_Left, Idle_HitReact_Right, Jump_ToIdle, Walk`

Výchozí role sedí bez `clip_for`: move=Walk, stand=Idle, jump=Gallop_Jump
(krátké jméno „Jump“) a lie=Death. Krátká jména podle `split("_")[-1]` jsou
ošklivá (`Idle_2` → „2“, `Idle_HitReact_Left` → „Left“), ale nic nekazí. Klipy
Eating, Idle_Headlow a Gallop se pro plánovač činností (úkol 4) přímo nabízejí.

## Co import hlásil a co se opravilo

1. **„chodec nemá kosti nohou (foot/toe/paw/hoof)“** u všech 12. Noha končí
   kostí `*LowerLeg`, chodidlo v kostře není. Oprava: když model chodidla nemá,
   bere se jako chodidlo koncový bod nohy `*Leg*_end` (`feetOf()` ve
   `web/scene3d.js`, totéž pravidlo v kontrole `tools/scena.py`). Dinosauři
   chodidla mají, takže se jich to netýká. `gait_report.py` teď čte chodidla
   z `m3.feet`, aby měřil přesně ty kosti, ze kterých scéna počítá krok.
2. **Koncové body nohou skončily u kolen a jelenovy parohy visely nad hlavou.**
   Je to chyba glTF importu v Blenderu 5.1: potomka kloubu převádí na potomka
   špičky kosti a odečte délku kosti vynásobenou měřítkem armatury
   (Quaternius ji má ve 100×). `blender_normalize.py` ten rozdíl vrací
   u všech objektů zavěšených na kost. Ověřeno číselně proti zdrojovému GLB,
   sedí na 1e-5.
3. **Jelen neměl na předloze parohy.** Parohy jsou samostatný mesh zavěšený
   na kost `Head` bez skinu a `dinostanice.gltf` bere jen vážené vrcholy.
   `blender_normalize.py` teď takový mesh převede na skin s jedinou kostí
   (výpis `RIGID Stag_Horns -> skin Head`).
4. **Ve scéně byla zvířata stokrát menší, tedy neviditelná.** `measure()`
   ve `web/scene3d.js` počítá velikost z geometrie × `matrixWorld` uzlu meshe.
   Blender ale věší skinovaný mesh pod armaturu ve 100×, kdežto kreslí se
   klouby × inverse bind. Oprava je v importu (`bind_mesh_nodes()` v
   `tools/scena.py`): uzel skinovaného meshe dostane přesně transformaci
   klidové pózy. Kresba se tím nemění a stávající modely se nedotkne.
   Oprava přímo v `measure()` by u ryb posunula velikost o 3–5 % (u nich se
   klidová a vazební póza kloubu 0 liší).

K tomu dvě drobnosti v `blender_normalize.py`:

- Balíček nese každý klip dvakrát (`Walk` i `AnimalArmature|Walk`, liší se
  o desetitisíciny). Duplikáty se mažou, takže GLB je skoro poloviční
  (liška 1,13 → 0,79 MB).
- `tests/test_server.py` měl natvrdo množinu scén `{cretaceous, aquarium}`.
  Teď ji bere z registru scén, aby přidání scény testy nerozbilo.

Do `markers.json` přidělil import indexy 23–34 všem 12. Vyřazeným zvířatům
(bull 24, cow 25, donkey 27, husky 30, white_horse 33) indexy zůstávají, aby
se nerecyklovaly.

## Výběr a ladění (scene.json)

| klíč | jméno | značka | ladění |
|---|---|---|---|
| alpaca | Alpaka | 23 | `stride_rate` [0.30, 0.45] |
| deer | Srnka | 26 | `stride_rate` [0.30, 0.45] |
| fox | Liška | 28 | `stride_rate` [0.35, 0.50] |
| horse | Kůň | 29 | `stride_rate` [0.30, 0.45] |
| shiba_inu | Pejsek | 31 | `stride_rate` [0.35, 0.50] |
| stag | Jelen | 32 | `stride_rate` [0.30, 0.45], `eye_bias` {forward 0.8, down 0.75} |
| wolf | Vlk | 34 | `stride_rate` [0.35, 0.50] |

- `axes`/`flip`, `rotate_y`, `poses` ani `eye_joint` (`Head`) nebylo třeba měnit.
  Všichni koukají k +Z a póza z Walk vyšla čitelně.
- `stride_rate` je nutný. Přirozené tempo klipu Walk je 0,57–0,81 těl/s
  a s výchozím 0,12–0,22 ze scény by zvířata šla zpomaleně (timeScale ~0,25).
- U jelena se oko posouvá ručně, protože parohy patří ke kosti Head a natáhnou
  obálku hlavy. Bez posunu sedělo oko u kořene parohů.
- Texty: zvíře / zvířata / zvířat, „Přidej své zvířátko“, „zvířátka na televizi
  se seběhnou“, „Zvířátka ještě žvýkají…“. Proč mají zvířata výjimky, popisuje
  `scenes/les/POZNAMKY.md`.

**Vyřazená:** bílý kůň (silueta shodná s koněm), býk (z boku k nerozeznání od
krávy, rohy jsou malé), kráva (farma, a s býkem byl jeden navíc), osel (z boku
bez výrazných uší, vypadá jako kůň) a husky (druhý pes, Shiba je čitelnější
díky stočenému ocasu).

**Předlohy** (`out/<klíč>_sheet.png`): alpaka (dlouhý krk), srnka, liška
(huňatý ocas, špičatý čenich) a pejsek (stočený ocas) jsou z boku jasně
poznat. Kůň je čitelný. Jelen s parohy je poznat, jen vyšel menší, protože
parohy zvětší výšku. Vlk má ve vybrané fázi chůze sníženou hlavu, ale jako
vlk či pes je poznat.

## Ověření na izolovaném serveru (:8132)

- `python -m pytest -q`: 248 passed.
- `tools/gait_report.py --url "http://127.0.0.1:8132/tv?scene=les"`, 60 s,
  vše OK:

| druh | prokluz | těl/s | cíl |
|---|---|---|---|
| alpaca | 1,6 % | 0,331 | 0,30–0,45 |
| deer | 1,3 % | 0,421 | 0,30–0,45 |
| fox | 2,7 % | 0,435 | 0,35–0,50 |
| horse | 1,5 % | 0,435 | 0,30–0,45 |
| shiba_inu | 2,7 % | 0,454 | 0,35–0,50 |
| stag | 1,3 % | 0,446 | 0,30–0,45 |
| wolf | 2,7 % | 0,436 | 0,35–0,50 |

- Kontrola, že se křídová laguna nezhoršila (`?scene=cretaceous`): vše OK,
  prokluz 1,2–1,8 %. Cíle se teď filtrují podle scény z URL, protože scéna
  zná jen svůj katalog.
- Upload: stanice `tv` přepnutá přes admin API na `les`, syntetická vybarvená
  předloha (`H.sheet(key, seed=3, ppm=6, strokes=40)` + `synth.photograph`).
  Jelen: 200, `stag-…`, 4 značky, pokrytí 0,166. Liška: 200, `fox-2a2f`,
  4 značky. Úlovky ve scéně nesou svou texturu `/catch/<id>/texture.png`.
  V konzoli nebyla žádná chyba.

Screenshoty (pracovní kopie, `tmp/`):

- `tmp/les_scena.png`: scéna po startu, katalogová zvířata s ukázkovými
  texturami (jelen, liška, vlk), krajina laguny.
- `tmp/les_upload_stag.png`: dva nahraní jeleni s vybarvenou texturou,
  parohy na hlavě, chodí po břehu.
- `tmp/les_upload_fox.png`: scéna po uploadu lišky.
- `tmp/les_ulovky.png`: jen úlovky, katalog odebraný.
- `tmp/sheets_all.png` / `tmp/sheets_sel.png`: náhledy předloh všech 12,
  resp. vybraných 7.

## Otevřené

- Prokluz 2,7 % u psovitých je těsně pod hranicí. Zlepšit by ho mohlo zúžení
  `stride_rate` nebo měření špičkou kopyta místo `_end`, které leží asi
  0,3 jednotky nad zemí.
- Role `lie` = Death: zvíře se skácí na bok. U dinosaurů to prochází,
  u srnky to může vypadat jako smrt. Lepší klip v balíčku není, to je
  práce pro úkol 3.
- Oprava importu Blenderu (bod 2) je nastavená podle chování verze 5.1.
  Kdyby to Blender opravil, korekce by začala vadit. Je ale omezená na glTF
  vstup a armatury s měřítkem různým od 1.
- Krajina je pořád laguna se sopkou.
