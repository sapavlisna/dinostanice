# Úkol 3 — Vlastní klipy v Blenderu (B2)

**Verdikt: ano.** Sedni/lehni/spi jsou z boku jasně poznat, kresba se nikde
netrhá a skript prošel beze změny kódu na šesti modelech (dvě mapy kostí).

## Co vzniklo

- `tools/blender_clips.py` — headless Blender. Vezme GLB a mapu kostí a vyrobí
  GLB s novými klipy **Sit**, **LieDown**, **Sleep** a **LookAround**.
- `tools/clipmaps/trex.json` (`plan: biped`), `tools/clipmaps/triceratops.json`
  (`plan: quadruped`) — mapy kostí: root, tělo, páteř, krk, hlava, ocas a nohy
  `front_*`/`back_*` (horní a dolní kost, chodidlo, u rukou dvounožce `"ik": false`).
- `tools/clips_preview.py` — kontrola: čísla přes `dinostanice.gltf.Model`
  a náhledy přes stejné promítání textury, jaké používá stanice.
- `data/models_src/trex_clips.glb` (471 kB, originál 337 kB) a
  `data/models_src/triceratops_clips.glb` (443 kB, originál 310 kB). Originály
  zůstaly, jak byly. Katalog ani `scene.json` jsem neměnil.

```
blender -b --factory-startup --python tools/blender_clips.py -- data/models_src/trex.glb tools/clipmaps/trex.json data/models_src/trex_clips.glb
python tools/clips_preview.py trex3d data/models_src/trex_clips.glb          # 4 obrázky do tmp/clips/
python tools/clips_preview.py trex3d data/models_src/trex_clips.glb --rychle # jen pruhy z boku
```

Jeden model trvá v Blenderu asi 7 s.

## Jak to funguje

- **Pózy se zadávají v osách zvířete, ne kostí.** „Dopředu“ je směr od
  kyčlí k hlavě v Idle, „nahoru“ je svislice. Parametr `pitch` +20 tedy
  znamená „nos nahoru o 20°“ pro jakoukoli kost bez ohledu na to, jak má
  natočené vlastní osy (a ty jsou u modelů převedených z FBX dost divoké).
  Úhel pro řetěz (páteř, krk) se rozdělí mezi jeho kosti, ocas se ohýbá
  plynule od kořene ke špičce. Pózy jsou v `POSES` (biped/quadruped)
  a `tweaks` v mapě je umí přepsat u jednoho modelu.
- **Nohy řeší dvoukloubové IK.** Tělo se spustí a nakloní, chodidlo zůstane na
  zemi (nebo se posune: `*_dx`, `*_tuck` = pod kyčel) a koleno se ohne na tu
  stranu, kam je ohnuté v Idle, *ve světě*, ne s tělem. Jinak by se při posazení
  triceratopsovi přetočily lokty dopředu. Když by koleno skončilo pod zemí
  (lehnutí), posune se po kružnici nahoru, ne do strany od těla.
- **Zem:** po každém snímku se spočítá nejnižší vrchol deformované sítě a celé
  zvíře se posune, aby leželo na zemi Idle. Spodek v `posed()` drží ±0,6 %
  velikosti zvířete.
- **Navázání:** Sit a LieDown začínají přesně v prvním snímku Idle (rozdíl
  kloubů 0,00 %), LookAround běží *nad* Idle (dvě jeho délky, takže smyčka
  sedí i s pohupováním). Sleep je smyčka (konec = začátek).

### Dvě pasti, které by jinak rozbily původní klipy

1. **Blender při exportu mění i původní klipy.** Modely jsou z FBX2glTF a kosti,
   které daný klip neanimuje, three.js nechává v pozici z uzlů GLB, kdežto
   Blender je vrací do své klidové pózy (vazební). Po obyčejném importu
   a exportu se tak u T-rexe posunul ocas o 1,5 jednotky do strany a pravá
   noha o 2,7 jednotky (1–2 % velikosti). Proto se nové akce exportují zvlášť
   a do kopie původního GLB se jen **připíšou** (`merge_animations`, uzly se
   párují podle jména). `clips_preview.py` kontroluje, že původní klipy jsou
   bajtově stejné.
2. **Klidová póza se bere z uzlů GLB.** Skript nejdřív naimportuje kopii bez
   animací (tím má každá kost pózu z uzlu) a teprve na ni přidá křivky Idle.
   Proto nové klipy navazují na Idle tak, jak ho kreslí three.js.

## Jak klipy vypadají

Náhledy: řádek = klip, sloupce = 25/50/75/100 % délky, v pevném rámci podle
Idle (čára = zem). Soubory jsou v `tmp/` (ten se necommituje):

- `tmp/clips/trex3d_pruhy_0.png`, `trex3d_pruhy_35.png` — ukázková textura
  (pruhy, na nich je vidět každé roztržení), z boku a natočený o 35°
- `tmp/clips/trex3d_vybarveni_0.png`, `trex3d_vybarveni_35.png` — syntetické
  dětské vybarvení (`H.sheet(key, strokes=40)` → `to_texture`)
- totéž pro `triceratops3d_*`
- `tmp/clips/prehled_6_modelu.png` — konečné pózy všech šesti dinosaurů
- `tmp/three/trex_three.png`, `triceratops_three.png` — totéž v three.js
  (GLTFLoader z `web/vendor`, UV jako `model_export3d.py`, vybarvená textura):
  GLB se načte bez chyb v konzoli, klipy jsou v seznamu animací a pózy sedí
  s Python náhledy

| klip | délka | T-rex | triceratops |
|---|---|---|---|
| **Sit** (jednorázový, drží) | 1,25 s | dřepne si na paty, trup se zvedne o 24°, ocas leží na zemi jako opěra — „klokan“ | psí sed: zadek na zemi, přední nohy rovně, hlava nahoře |
| **LieDown** (jednorázový, drží) | 1,75 s | přes podřep si lehne na břicho, hlavu skoro na zem, ocas po zemi | nohy se složí pod tělo, břicho a ocas na zemi, hlava dole |
| **Sleep** (smyčka) | 3,2 s | leží, hlava úplně dole a trochu natočená, ocas stočený k tělu, dýchání ±1,3 % | totéž |
| **LookAround** (smyčka nad Idle) | 2× Idle (5,0 / 5,1 s) | krk a hlava doleva (asi 48° s náklonem), drží, doprava, drží, zpět | totéž |

Z boku (jak je vidí TV) jsou sed, leh a spánek na první pohled odlišné od
stání i od sebe navzájem. Kresba drží: pruhy se v ohybech jen plynule
zhušťují nebo roztahují, nikde se netrhají a netáhnou přes hřbet.

## Kritérium

- **Póz si všimne dítě — ano.** Sedí/leží je z boku jednoznačné. Spí vs. leží
  rozhoduje hlava úplně dole a stočený ocas; víc by pomohl přidaný „Zzz“ ve
  scéně (úkol 4), oči zavřít nejdou (modely nemají kosti víček).
- **Kresba drží — ano**, v pruzích i ve vybarvení, z boku i šikmo. Jediná
  vada: při lehnutí T-rexe se stehno zamáčkne do boku a při pohledu šikmo
  (35°) je vidět záhyb. Z boku není vidět.
- **Přenos jen změnou mapy — ano.** Všechny Quaternius dinosauři mají stejná
  jména kostí, takže jsem nad stejnými mapami pustil i velociraptora
  a parasaurolopha (mapa T-rexe) a stegosaura a apatosaura (mapa triceratopse),
  bez jediné změny kódu (`tmp/clips/prehled_6_modelu.png`). Všechno vyšlo
  použitelně, jen apatosaurus v sedu kroutí dlouhý krk a ocas nahoru
  a stegosaurus má v sedu hlavu moc nízko. To se ladí přes `tweaks` v mapě,
  ne v kódu. U cizí kostry s jinými jmény se mapa vyplní ručně (asi 10 řádků).

## Otevřené

- **Sleep nezačíná tam, kde LieDown skončil** (rozdíl kloubů 11–12 %: hlava
  a ocas se ještě dotočí). Ve scéně se to musí prolnout delším crossfadem
  (~0,8 s), nebo se může přidat krátký přechodový klip.
- **Vstávání** se nevyrábí. Ve scéně jde LieDown/Sit pustit pozpátku
  (`timeScale = -1`), nebo se dá snadno doplnit jako další klip ve stejném
  skriptu.
- Stretch/Shake (volitelné) nejsou: pro dítě nejsou z boku moc čitelné, takže
  dávám přednost úkolu 4.
- Nové klipy klíčují všechny kosti v každém druhém snímku (T/R/S). Proto je GLB
  asi o 135 kB větší. Šlo by to zmenšit vypuštěním konstantních kanálů, ale
  zatím to nevadí.
- `gait_report` jsem nespouštěl. Scéna ani katalog se nezměnily a chůze
  zůstala bajtově stejná.
