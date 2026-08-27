# Zdroje modelů

Předlohy k vybarvení se generují z hotových 3D modelů, takže jediný cizí
materiál v projektu jsou právě ty modely.

Všechny kromě ptakoještěra jsou z packu **Animated Dinosaurs** od
[Quaternia](https://quaternius.com/), pod **CC0 1.0**, každý rigovaný se šesti
animacemi (Idle, Walk, Run, Attack, Jump, Death). Staženo přes poly.pizza,
protože tamní kopie je v GLB i s kostrou. CC0 nevyžaduje uvedení autora —
je tu z úcty k jeho práci, ne z licenční povinnosti.

| soubor | tvor | zdroj |
|---|---|---|
| `data/models_src/trex.glb` | Tyrannosaurus | [poly.pizza](https://poly.pizza/m/UYtneO5FpF) |
| `data/models_src/velociraptor.glb` | Velociraptor | [poly.pizza](https://poly.pizza/m/cnlGH2UcDd) |
| `data/models_src/triceratops.glb` | Triceratops | [poly.pizza](https://poly.pizza/m/IGvrUqGrRM) |
| `data/models_src/stegosaurus.glb` | Stegosaurus | [poly.pizza](https://poly.pizza/m/eFcNbOlpvl) |
| `data/models_src/parasaurolophus.glb` | Parasaurolophus | [poly.pizza](https://poly.pizza/m/KeeQrrouRK) |
| `data/models_src/apatosaurus.glb` | Apatosaurus | [poly.pizza](https://poly.pizza/m/fvo0x8Zk3z) |
| `data/models_src/dragon.glb` | Drak (létající) | [poly.pizza](https://poly.pizza/m/LlwD0QNUPj) |

Drak není z dinosauřího packu, ale ze stejné dílny — je to druhý létající tvor.

## Ptakoještěr

| soubor | tvor | autor | licence | zdroj |
|---|---|---|---|---|
| `data/models_src/pterosaurs_scene.glb` | scéna tří pterosaurů | **Hoai Nguyen** | **CC BY 4.0** | [poly.pizza](https://poly.pizza/m/1tuiNTr4-MX) |

**Tenhle model vyžaduje uvedení autora** — na rozdíl od ostatních není CC0.
Přišel bez kostry: animovaný pterosaur se pod otevřenou licencí sehnat nedá
(Quaternius žádného létajícího pravěkého tvora nemá, na poly.pizza jsou
pterosauři statičtí a na Sketchfabu jsou sice animovaní, ale všichni pod CC-BY
a ke stažení jen po přihlášení). Kostru i mávání křídly mu proto dopisuje
`tools/make_pteranodon.py`; `data/models_src/pteranodon.glb` je odvozenina,
na kterou se vztahuje tatáž licence.

## Knihovny

`web/vendor/GLTFLoader.js`, `BufferGeometryUtils.js`, `OrbitControls.js`,
`SkeletonUtils.js` a `three.module.min.js` jsou z three.js r169 (MIT), stažené
lokálně, aby scéna běžela offline.

Krajina, animace a veškerý kód jsou vlastní tvorba.
