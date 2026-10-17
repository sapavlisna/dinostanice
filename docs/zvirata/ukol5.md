# Úkol 5 — AI tvar + šablona kostry (B4 + B3)

**Verdikt: ano, s výhradami.** Zajíc z Hyper3D Rodinu, navlečený nástrojem
`tools/blender_bind.py` na kostru lišky, je ve scéně `les`. Chodí, rozhlíží se,
hraje si, běží a skáče. Prokluz je 2,6–2,9 % (liška 2,6 %), upload vybarvené
předlohy funguje a předloha je čitelná. Navlečení dalšího zvířete s hotovým
nástrojem trvá asi 30–45 minut, většinou je to odečítání landmarks. Výhrady:
styl je „hranatý králík“ a ne čistý Quaternius, žraní je vypnuté a tvar
z Rodinu potřeboval ruční řez (vousy).

## Dvě cesty ke tvaru

| | A: Flux → Hunyuan3D-2 (HF Space) | **B: Hyper3D Rodin (Blender MCP)** ← vybraný |
|---|---|---|
| vstup | obrázek z FLUX.1-schnell (`tmp/gen_flux/hare_7.png`) | jen text (prompt níž) |
| čas | Flux ~4 s, Hunyuan ~1–2 min (frontu na ZeroGPU nepočítám) | 2–3 min na úlohu |
| pokusy | 1 použitelný | 3 úlohy, použitelná 1. Ve 2. a 3. ležel zajíc s ušima do stran |
| surový tvar | 5,7 MB, realistický zajíc, dlouhé nohy (taková byla předloha) | 23 k trojúhelníků, kostičkový kreslený králík, krátké nohy, velký kulatý ocas, **vousy jako dvě prkna skrz hlavu** |
| úklid | řez vousů, decimace na 1 800 | řez tunelu vousů skrz hlavu + zalepení děr (`fill_holes`), decimace na 2 400 + `dissolve` 5° → 1 980 trojúhelníků |
| nohy po navlečení | ×1,10 (delší než liščí) | ×0,87 (kratší) |
| předloha | čitelná, zajíc jako zajíc, ale „srnka“ | z Walk chaotická, s `poses: ["Idle"]` čistý obrys králíka, 4 vnitřní linky |
| licence | Hunyuan3D-2: Tencent Hunyuan Community License, **území výslovně vylučuje EU, UK a Jižní Koreu**. FLUX.1-schnell: Apache 2.0 | Hyper3D ToS čl. 5: výstup Rodinu se „neomezuje“. Čl. 1 ale váže komerční export na tarif (viz CREDITS.md) |

Prompt B: *„low-poly flat-shaded stylised hare, simple faceted cartoon game
asset like Quaternius animals, standing on all four legs in a neutral side
profile pose, long upright ears, short fluffy round tail, short legs, compact
body, solid flat colours, no texture detail“*, `bbox_condition [1, 0.4, 0.8]`.

**Proč B:**
- Stylově je blíž Quaterniovi: velké ploché fazety, krátké nohy, nic realistického.
- Kritika z recenze (srnčí nohy, „sochařský“ povrch) se ho netýká.
- Licence nemá územní háček. U Hunyuanu je výstup pro stanici v Česku formálně mimo licenci.
- Proti mluví jen předloha z Walk. Ta se spravila pózou Idle.

Oba výsledky:
- **Ve scéně nad sebou** (A nahoře, B dole): `tmp/cmp/scene_hunyuan_vs_rodin.png`.
  Jednotlivě `tmp/shots/hy_sheet_les_zajic.png` a `tmp/shots/final_sheet_les_zajic.png`
  (walk, eat, look, play, run, stand).
- **Předlohy** (A, B, pro srovnání liška): `tmp/cmp/sheets_side_by_side.png`.
- **Surové tvary**: `tmp/cmp/hy_raw.png`, `tmp/cmp/rodin_raw.png`.
- **Po navlečení s klouby (Idle)**: `tmp/cmp/hy_bound_views.png`, `tmp/cmp/rodin_bound_views.png`.
- Nepovedené úlohy Rodinu: `tmp/rodin/rodin_text2_all.png`, `rodin_text3_all.png`.

A zůstává jen v `tmp/` (`tmp/work/hy_bound.glb`, mapa `tmp/work/zajic_hunyuan_bindmap.json`).

## `tools/blender_bind.py` — co se změnilo proti první verzi

První verze ohýbala tvar *do* liščí kostry, takže z každého zvířete udělala
lišku s jiným povrchem: dlouhé tenké nohy, liščí krk. Teď se **kostra
přizpůsobí tvaru** a klipy zůstanou platné:

1. Tvar se zvětší podle délky trupu (`scale_by`) a postaví se na zem předlohy.
2. `Body` se posune na výšku hřbetu tvaru, v klidu i ve všech klipech.
   Pohupování se zmenší v poměru nohou.
3. **Nohy se zkrátí jedním poměrem k = výška kyčle nová / původní.** Proč
   jeden poměr: stojící tlapka se v klipu posouvá k× rychlostí těla. S k vpředu
   0,856 a vzadu 0,881 měl zajíc prokluz 3,2 %, s jedním k = 0,868 má 2,6–2,9 %.
   Tlapky pak sedí ±0,02 nad/pod zemí (0,6 % výšky).
4. Uzly nohy a tlapky mají posuny × k. **IK tlapky** jsou v Quaterniovi
   kořenové kosti (sourozenci `Body`), takže se přepočítají v každém snímku
   každého klipu: IK = kyčel_nová + k·(IK − kyčel_původní). Natočení kloubů
   jsou stejná, takže je to přesně konec zkrácené nohy. Kontrola: mezera mezi
   `*LowerLeg_end` a IK je 0,093, u lišky 0,108 × 0,868. Krok je k× kratší
   a scéna ho měří z koncových kostí, takže prokluz se nemění.
5. `fit`: krk, hlava, uši a ocas dostanou délku podle landmarks (zajíc: krk
   ×0,62, uši ×1,88, ocas ×2,6). Posun uzlu se bere od jeho rodiče v glTF.
   Liščí uši visí na `Neck3`, ne na `Head`.
6. `aim`: uši se natočí ke konci svého řetězu na tvaru. Liščí uši míří šikmo
   do stran, zaječí nahoru, oprava je 29°. Ke klíčům natočení `Ear1` se zprava
   přinásobí stálý kvaternion, takže vrtění uší zůstává. Tohle je **jediná
   výjimka**. Ostatní natočení jsou bajtově stejná jako u lišky, ověřeno
   porovnáním všech kanálů.
7. Tvar se ohne do nové klidové kostry (segmenty, bone heat Blenderu),
   inverse bind se přepočítá. Materiály podle převažující kosti (uši, hlava,
   ocas, přední/zadní nohy, tělo) dávají předloze vnitřní linky.

GLB s klipy se Blenderem neimportuje ani neexportuje. Nástroj přepisuje přímo
JSON a BIN kopie předlohy, takže nehrozí přepočet klipů (past z úkolu 3)
a nepotřebuje opravu zavěšení na kost z `blender_normalize.py`. Blender
slouží jen k načtení zdroje, decimaci, zalepení děr a vahám. Běh trvá
3–5 s a je deterministický (dvakrát po sobě bajtově stejný GLB).

Nové volby zdroje:
- svaření zdvojených vrcholů (švy UV): Rodin by se jinak rozpadl na 1 900 „kusů“,
- `dissolve` (planární decimace, větší fazety),
- `fill_holes`.

`tools/bind_views.py` kreslí tvar s mřížkou z boku, zepředu a shora:
- `--map` přidá landmarks z mapy,
- u hotového GLB kreslí klouby a pózu klipu (`--clip`, `--t`).

### Jak navléct další zvíře (≈ 30–45 min)

```
# 1. surový tvar -> tmp/, mapa pro úklid (source, rotate_y, faces, dissolve, cut, fill_holes)
blender -b --factory-startup --python tools/blender_bind.py -- tools/bindmaps/<z>_tvar.json data/models_src/<z>_tvar.glb --prep
python tools/bind_views.py data/models_src/<z>_tvar.glb tmp/<z>_prep.png
# 2. tools/bindmaps/<z>.json: zkopírovat zajic.json, přepsat landmarks podle mřížky (~20 bodů, .L se zrcadlí)
python tools/bind_views.py data/models_src/<z>_tvar.glb tmp/<z>_prep.png --map tools/bindmaps/<z>.json
# 3. navléct rovnou do vstupu importu a importovat bez Blenderu
blender -b --factory-startup --python tools/blender_bind.py -- tools/bindmaps/<z>.json scenes/les/modely/<z>.glb
python tools/bind_views.py scenes/les/modely/<z>.glb tmp/<z>_walk.png --clip Walk --t 0.3
python tools/scena.py import les --bez-blenderu
```

`--bez-blenderu` je důležité. Import přes Blender by GLB znovu prohnal
`blender_normalize.py`, tedy importem a exportem.

## Žraní (bod 3)

Za ohnutou hlavu nemohlo navlečení. Je to liščí klip `Eating` na zvířeti
s krátkým krkem a velkou hlavou se vztyčenýma ušima. Hlava se zanoří mezi
přední nohy a uši se sklopí dopředu jako zobák. Totéž dělá u obou tvarů
i `Idle_2_HeadLow` a `Attack`. Zkrácení krku (`fit`, ×0,62) pomohlo jen
trochu (`tmp/work/rodin_clips.png`, řádky Eating a HeadLow). Proto je ve
`scene.json` `"eat": null`. U jídla zajíc stojí a rozhlíží se, pastva se
nenabízí. `play` (Attack) zůstal, protože ve hře je krátký a čte se jako
„dupnutí“.

## Ověření

- `python tools/scena.py import les --bez-blenderu` zpracuje jen zajíce,
  protože `scenes/les/modely/` je v `.gitignore` a leží tam jen on.
  Značka 35 zůstala. Ostatní `data/templates/*.svg`, `data/shapes3d/*.json`
  ani GLB lesních zvířat se nezměnily (`git status`). Katalog dostal jen
  záznam zajíce.
- Izolovaný server :8135, Playwright, swiftshader:
  - syntetická vybarvená předloha (`H.sheet('zajic', seed=3, ppm=6, strokes=40)`
    + `synth.photograph`) vrátila upload 200, 4 značky, pokrytí 0,126,
  - úlovek nese vlastní texturu,
  - konzole bez chyb.
- Snímky činností: `tmp/shots/final_zajic_{walk,eat,look,play,run,jump,stand}.png`,
  přehled `tmp/shots/final_sheet_les_zajic.png`, vybarvený list
  `tmp/shots/final_zajic_vybarveny_list.jpg`.
- `gait_report` les, dva běhy:

| druh | prokluz | těl/s | cíl |
|---|---|---|---|
| zajic | 2,9 / 2,6 % | 0,476 / 0,358 | 0,35–0,50 |
| fox (stejné klipy) | 2,6 / 2,6 % | | |

  Pejsek (shiba) v jednom běhu znovu 3,2 %. Je to známé z úkolů 2 a 4,
  se zajícem to nesouvisí.
- `python -m pytest -q`: 253 passed.

## Otevřené

- **Styl:** Rodin dal kostičkového kreslené králíka, ne Quaterniovu
  geometrii. Vedle lišky působí robustněji a hlava je velká. Ve hře je to
  roztomilé a z boku jasné, ale „stejný balíček“ to není.
- **Kvalita Rodinu je loterie.** Vyšla 1 ze 3 úloh a i ta měla prkna vousů
  skrz hlavu. Řez je ruční (box v jednotkovém rámci) a po zalepení zůstala
  na hlavě šikmá plocha (z boku nevadí). Free-trial kredity jsou omezené.
- **Flux přes HF Space** narazil během úkolu na kvótu ZeroGPU (bez HF tokenu).
  Cestu „low-poly obrázek → Rodin z obrázku“ jsem proto nezkoušel.
- Sit/LieDown/Sleep zajíc nemá. `tools/clipmaps/fox.json` a oprava
  v `blender_clips.py` (IK tlapka bez rodiče) jsou z předchozího pokusu
  připravené, ale klipy na zajíce zapojené nejsou. Šlo by to přes
  `blender_clips.py` na `data/models_src/zajic.glb`, tam ale Blender GLB
  exportuje (past z úkolu 3 pro neanimované kosti tady nehrozí, kanály mají
  všechny kosti).
- Liščí klip Walk je klus psovité šelmy, ne zaječí poskakování. Vlastní
  „hop“ by byl další klip pro `blender_clips.py`.
- Tlapky v klipech sedí do 0,13 jednotky pod zemí, liška do 0,04. Kreslené
  tlapky Rodinu jsou ploché a nižší než liščí `FF`.
