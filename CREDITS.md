# Zdroje předloh

Siluety dinosaurů pocházejí z [PhyloPic](https://www.phylopic.org/) — otevřené
databáze vědecky posuzovaných siluet organismů. Všechny použité jsou uvolněné
pod **CC0 1.0** (veřejné vlastnictví), takže je lze použít bez podmínek.
Autoři jsou uvedení z úcty k jejich práci, ne z licenční povinnosti.

| šablona | taxon | autor | licence | zdroj |
|---|---|---|---|---|
| `sauropod` | Brachiosaurus | Mike Taylor | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/2431b273-7b21-482e-b971-70377686335d) |
| `trex` | Tyrannosaurus | Manuel Brea Lueiro | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/6a38b924-85c4-46b6-a04a-0e53f2f4d77f) |
| `stegosaurus` | Stegosaurus | Olivia Binfield | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/429d71d8-2940-449b-838b-a5b7f1733eba) |
| `triceratops` | Triceratops | Richard Rich | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/57d2507a-be74-453b-8522-f6993b2fc401) |
| `pteranodon` | Pteranodon | Dan Niel | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/0b4b95c2-615a-45df-adaa-a63fbd039eb2) |
| `plesiosaur` | Plesiosaurus | Arthur S. Brum | CC0 1.0 | [PhyloPic](https://www.phylopic.org/images/59ce4fbe-6a78-42cd-b168-fb03cf8d176d) |

Přesná UUID a odkazy jsou v `data/silhouettes/credits.json`, který generuje
`tools/fetch_silhouettes.py` (ten také stahuje kandidáty k výběru a zaznamenává
licenci každého z nich — nic se nepoužije, aniž by bylo jasné, odkud to je).

## 3D modely

Zkouška obráceného postupu (předloha se generuje z hotového 3D modelu, ne
naopak) stojí na animovaném low-poly modelu:

Všechny jsou z packu **Animated Dinosaurs** od [Quaternia](https://quaternius.com/),
pod **CC0 1.0**, každý rigovaný se šesti animacemi (Idle, Walk, Run, Attack,
Jump, Death). Staženo přes poly.pizza, protože tamní kopie je v GLB i s kostrou.

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

### Ptakoještěr

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

`web/vendor/GLTFLoader.js` a `BufferGeometryUtils.js` jsou z three.js r169 (MIT),
stažené lokálně, aby scéna běžela offline.

Plachetnice a letadlo nejsou z PhyloPic (ten obsahuje jen organismy) — jsou to
vlastní parametrické tvary definované v `dinostanice/creatures.py`.

Krajina, animace a veškerý kód jsou vlastní tvorba.
