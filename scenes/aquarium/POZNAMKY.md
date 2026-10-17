# Poznámky k tvorům scény `aquarium`

Proč mají jednotliví tvoři v `scene.json` výjimky (pohled, oko, póza).
Přeneseno z komentářů dřívějšího `dinostanice/creatures3d.py`.

## ryby obecně + clownfish

Klice jsou bez suffixu "3d": ten u dinosauru odlisoval 3D vetev od zrusene 2D (kresba -> ohybany pas), ktera uz neexistuje, takze u novych tvoru je zbytecny.

Indexy 16-21, ne 0-7. Prvnich osm je sice volnych, ale doma jeste lezi vytistene listy zrusene vetve s temi indexy v rohovych znackach — kdyby se recyklovaly, poznal by se stary list jako ryba.

Ryby se kresli bokorysem: rybi profil je nejcitelnejsi silueta a ma velke plochy k vybarveni. Vyjimka je manta (viz jeji zaznam). `stride_rate` zustava None zamerne: je to tempo chuze v delkach tela za sekundu, odvozene z kroku. Plavec zemi nedotyka, takze u nej neni z ceho tempo pocitat — rychlost i frekvenci vlneni urcuje scena.

Rybi armatura Quaterniova packu ma jointy Main1..Main6 (Main1 = hlava), zadny "Head"; zralok a manta "Head" maji.

Ctyri druhy z rybi armatury maji oko jako vlastni material, takze uz ho do kresby vnasi vnitrni linka — velky krouzek na hlave. Tistene oko je jim proto zornicka a `eye_bias` ho posadi do stredu toho krouzku; vychozich forward=0,68 / down=0,34 mirilo mimo (rybi Main1 je cela predni pulka tela, ne hlava, takze zlomky jeji obalky vychazi jinam).

## manta

Manta se kresli shora jako pteranodon: z boku je to 1 mm tenka placka, ze ktere neni co vybarvovat (fill 0,05 proti 0,21 shora). Rozpeti kridel lezi po svisle ose listu, telo i bicikovity ocas po vodorovne. Hloubkove znamenko -1 obraci pohled na hrbet (material "Top"), ne na bile bricho. Oko nesedi na ose soumernosti jako u pteranodona, ale u kraje hlavy — tam ho manta doopravdy ma, po strane za rohatym hlavovym lalokem. Ma jediny klip Swim, takze `fast` padne zpatky na nej.

## axolotl

Axolotl prisel bez kostry, tu mu dopisuje tools/make_axolotl.py (zdroj je axolotl_static.glb). Kresli se shora jako manta a v pozi, ktera je pro predlohu udelana na miru (klip "Sheet", stejny pripad jako drak).

Shora ma tvor ctyri nohy s prsty i placatou hlavu, ale ve vlastni poloze modelu lezi vejir zaber presne tam, kde predni noha, a v obrysu s ni splyne — na listu je pak mlok se ctyrma nohama a jedinou poznavaci znacku axolotla dite nevidi. Poza proto sklopi horni stonek do roviny listu, rozlozi stonky do vejire a predni nohu odklopi dozadu: vejir vyjde jako tri samostatne prsty pred nohou (vyplneni listu 0,197 proti 0,191, vnitrni linky 4 proti 6).

Bokorys se zkousel znovu, i s vejirem rozevrenym vzhuru a stocenym telem: zabry jsou z boku sice citelne, ale vyplneni konci na 0,13 (proti 0,197) a v kresbe zbyde jedna velka plocha (1-4 vnitrni linky) a misto ctyr nohou dve nezretelne placky. Vyplneni neni totez co citelnost, jenze tady bokorys prohrava na oboji.

Hloubkove znamenko -1 obraci pohled na hrbet, ne na bricho.

Oko: `down` posouva po sirce listu (svisla osa je tady sirka tvora), `forward` po delce. Auto_eye si krouzek stejne dotlaci dovnitr obrysu, takze na listu je rozdil mezi 0,3 a 0,46 par milimetru — na modelu je ale obrovsky. Nizsi hodnoty poslou oko na bok lebky, kde je plocha skoro rovnobezna s pohledem shora, a z krouzku se stane bila rozmazana carka; 0,46 ho polozi na temeno hlavy, kde vyjde jako kulate oko (viz out/axolotl_model_*.png). Kostra ma vlastni joint "Head", `eye_joint` tedy zustava vychozi.
