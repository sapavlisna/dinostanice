# Poznámky ke scéně `betlem`

Noční Betlém: hvězda s ohonem a paprskem, město na kopci vlevo, chlévek se skálou,
jesličkami a Svatou rodinou vpravo, ohniště pastýřů s ohradou vlevo. Krajina je
`web/backdrops/betlem.js`, vše je kreslené canvasem; postavy (Marie, Josef, pastýři)
jsou jen malované siluety, 3D jsou jen zvířata.

## Dráhy a trasy

Pod chlévkem a ohništěm nejsou žádné dráhy: tvor se kreslí vždy NAD malovanou
krajinou, takže by za chlévkem procházel střechou. Chodí se jen před ním, ve dvou
dráhách střední (0,715 / 0,775) a dvou přední (0,855 / 0,915). Trasy v `render.js`
sledují cestu přes `trailX()` z `betlem.js` a končí po stranách jeslí (osel vlevo
na x 0,555, vůl vpravo na 0,745, aby nestáli před Svatou rodinou). Velbloud
přichází zprava a staví se k palmám, ovce míří k ohništi a koza na svah vlevo.

Poměr velikostí je v `motions.walk.scale` (velbloud 1,0, vůl 0,78, osel 0,66,
koza 0,52, ovce 0,50).

## Světla

Studený měsíc zleva (`sun`), teplo z jeslí a ohně zprava a zepředu (`fill`).
Teplý přechod přes tvory u chlévku a ohně navíc kreslí `drawFront` jako
poloprůhlednou záři.

## Tvorové

Osel a vůl jsou původní Quaternius (*Ultimate Animated Animal Pack*, CC0) včetně
klipů. Ovce, velbloud a koza v packu nejsou, vznikly **Hyper3D Rodin → úklid →
`tools/blender_bind.py`** stejně jako zajíc v lese (viz `docs/zvirata/ukol5.md`):

| tvor | kostra a klipy | mapa |
|---|---|---|
| ovce | alpaka | `tools/bindmaps/sheep.json` |
| velbloud | alpaka | `tools/bindmaps/camel.json` |
| koza | jelen (srnka) | `tools/bindmaps/goat.json` |

Mapy vznikly nástrojem `tools/make_bindmap.py` (vzor `zajic.json` + ruční body
z `bind_views.py`). `poses: ["Idle"]` mají tvorové s navlečeným tvarem, protože
ze Walk vychází rozkročené nohy a předloha je zmatená; osel a vůl mají Walk jako
zvířata v lese.

Rodin potřeboval tři pokusy na ovci a dva na velblouda a kozu: prompt s
`bbox_condition` dal placatá tělesa (velbloud bez krku a hrbu, kozel jako krabice),
prompt bez ní a s důrazem na „čtyři oddělené nohy s mezerami, vidět hrb / rohy“
vyšel dobře hned. Surové výstupy Rodinu se necommitují (`tmp/betlem/rodin/`).

## Co je slabé

- Ovce je vlněná koule na tenkých nohách, hlava splývá s tělem; Eating zanoří hlavu
  do hrudi (u vlněné ovce to nevadí, u zajíce bylo důvodem `eat: null`).
- Velbloud má alpačí chůzi a vzpřímený ocas, není to klus velblouda.
- `gait_report`: prokluz sheep / camel / bull se pohybuje kolem hranice 3 %
  (bull je původní Quaternius, takže jde o vlastnost modelu, ne navlečení).

## Anděl a hvězda nad chlévem (doplňky)

`betlem_andel` (model z Mikulášské, `mik_andel.glb`) a `star` (`tools/make_star.py`,
plochá pěticípá hvězda) jsou doplňky jako ptáček a motýlek v Lese: nemají vlastní list,
jejich okénko je v rohu listu každého zvířete a uloží se, jen když je dítě vybarví.
Navíc tu jsou vždycky (`ambientExtras` v `render.js`): anděl se vznáší nad střechou
chlévku, hvězda visí na ohonu velké malované hvězdy. Vybarvení se přidávají na další
místa (`motions.hover.spots` / `motions.twinkle.spots`), kdo se nevejde, dostane
náhodný bod v `area`. Pohyb dělá `updateHover` ve `web/scene.js`.
