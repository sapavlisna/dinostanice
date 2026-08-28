# Zdroje modelů

Předlohy k vybarvení se generují z hotových 3D modelů, takže jediný cizí
materiál v projektu jsou právě ty modely.

Až na ptakoještěra jsou všechny od [Quaternia](https://quaternius.com/) a pod
**CC0 1.0**; staženo přes poly.pizza, protože tamní kopie jsou v GLB i
s kostrou. CC0 nevyžaduje uvedení autora — je tu z úcty k jeho práci, ne
z licenční povinnosti.

## Křídová laguna

Pack **Animated Dinosaurs**, každý model rigovaný se šesti animacemi
(Idle, Walk, Run, Attack, Jump, Death).

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

## Ryby (akvárium)

Ze stejné dílny a rovněž **CC0 1.0** je i rybí šestice. Prvních pět nese
společnou armaturu `Fish_Armature` se šesti klipy (Swimming_Normal,
Swimming_Fast, Swimming_Impulse, Attack, Death, Out_Of_Water) — až na žraloka,
který má vlastní kostru a tři klipy. Manta pochází z packu
[Animated Fish Bundle](https://poly.pizza/bundle/Animated-Fish-Bundle-ZkGbjS8m8g)
a nese jediný klip Swim.

| soubor | tvor | zdroj |
|---|---|---|
| `data/models_src/clownfish.glb` | Klaunská rybka | [poly.pizza](https://poly.pizza/m/769fHo3eEB) |
| `data/models_src/shark.glb` | Žralok | [poly.pizza](https://poly.pizza/m/YYsK3gRCBZ) |
| `data/models_src/puffer.glb` | Čtverzubec | [poly.pizza](https://poly.pizza/m/UKHtgpxTOk) |
| `data/models_src/swordfish.glb` | Mečoun | [poly.pizza](https://poly.pizza/m/7hMOlBjln0) |
| `data/models_src/lionfish.glb` | Perutýn | [poly.pizza](https://poly.pizza/m/czsz9Baw86) |
| `data/models_src/manta.glb` | Manta | [poly.pizza](https://poly.pizza/m/yzD8b7ZHZm) |

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

## Axolotl

| soubor | tvor | autor | licence | zdroj |
|---|---|---|---|---|
| `data/models_src/axolotl_static.glb` | axolotl bez kostry | **vildurr** | **CC BY 4.0** | [Sketchfab](https://sketchfab.com/3d-models/axolotl-normal-and-ao-map-1f8197423fdb4949b59acc82979d04bb) |

**Tenhle model vyžaduje uvedení autora** — stejně jako ptakoještěr není CC0.
Rigovaný axolotl pod otevřenou licencí neexistuje: Quaternius žádného
obojživelníka nemá, na poly.pizza axolotl není vůbec (jen Salamander od Poly by
Google, Newt a Tetra), OpenGameArt ani Wikimedia nic, na itch.io jsou axolotlové
placení a CC0 balíčky (Gobkit, KayKit) žádného nemají. Animovaní axolotlové jsou
na Sketchfabu, ale všichni pod CC-BY a všichni jen pro přihlášené.

Stažení proto vede přes **[Objaverse](https://huggingface.co/datasets/allenai/objaverse)**
(Allen AI), což je veřejná kopie CC-licencovaných Sketchfab modelů na
HuggingFace — soubor `glbs/000-107/1f8197423fdb4949b59acc82979d04bb.glb`. UID
v Objaverse je totožné se Sketchfab UID, takže se licence i autor dají ověřit
na původní stránce modelu; ověřeno přes Sketchfab API (`license.slug = "by"`).

Model přišel bez kostry (jediný mesh, 9 342 trojúhelníků, jeden materiál).
Kostru, rozdělení na části a klip plavání mu dopisuje `tools/make_axolotl.py`;
`data/models_src/axolotl.glb` je odvozenina, na kterou se vztahuje tatáž
licence.

## Knihovny

`web/vendor/GLTFLoader.js`, `BufferGeometryUtils.js`, `OrbitControls.js`,
`SkeletonUtils.js` a `three.module.min.js` jsou z three.js r169 (MIT), stažené
lokálně, aby scéna běžela offline.

Krajina, animace a veškerý kód jsou vlastní tvorba.
