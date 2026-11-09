/* Definice scény „Les" — scéna jako data. Hlavička vysvětluje pole stejně
   jako scenes/cretaceous/render.js; zvlášť pro les je `motions.walk.scale`
   (poměr velikostí druhů) a krajina z web/backdrops/forest.js.

   Původní popis polí:

   scene.js nezná žádné zóny ani konstanty krajiny; všechno čte odsud.
   Jméno, sada tvorů (`catalogue`) a texty pro děti jsou ve vedlejším
   scene.json — scene.js je k definici přimíchá z /api/scenes.

     backdrop   async továrna na kreslič krajiny {draw, drawFront, sun, depthScale}
     lighting   světla 3D vrstvy (Scene3D.setLighting)
     bands      pásy scény: y0/y1 v podílu výšky plátna, `motions` říká, kdo
                se v pásu smí pohybovat, `lane` odlišuje víc pásů téhož pohybu.
                `lanes` (bod 2) dělá z pásu diskrétní vodorovné dráhy: seznam
                y hodnot (nebo počet), tvor jednu dostane při spawnu a drží ji
                bez driftu; na jinou přeskočí až za okrajem obrazovky.
                `rateScale` (bod 1) škáluje cílové TEMPO chodců na pásu —
                vzdálený břeh je pomalejší, ale chodidla drží na zemi,
                protože rychlost se z tempa dopočítává
     motions    chování a měřítka per typ pohybu (viz níže)
     ambientMin na kolik tvorů scénu doplnit z katalogu

   motions.<typ>:
     sizeFraction    velikost tvora v nejbližším plánu jako podíl šířky
                     obrazovky (odmocnina z plochy siluety)
     baseSpeed       rychlost v podílu šířky/s pro tvory bez měřeného kroku
     strideRate      default cílového tempa chodce (těl/s); per druh ho
                     přebíjí `strideRate` z katalogu (vlastnost druhu)
     drift           podíl vodorovné rychlosti pro svislé sunutí po pásu
     driftRefHeight  výška pásu, pro kterou platí plný drift
     farChance       šance, že nový tvor padne na vedlejší (far) lane
     bob             sinusové houpání (letci)
     turn/bank       (volitelně) natočení modelu k divákovi v radiánech a
                     náklon kolem osy pohledu; bez nich platí default 3D
                     vrstvy (MOTION v scene3d.js). Úhel je vlastnost vzhledu
                     krajiny, ne 3D vrstvy — proto se ladí tady.
     rest            umožňuje zastavit (kolizní fronta, dwell na trase,
                     krmení) a otočit se na místě; bez něj tvor nezastaví
                     nikdy. Náhodné zastávky "jen tak" neexistují — tvor
                     jde, dokud nemá důvod stát. `stand` = délka postání
                     u jídla (a default dwellu na trase), `fade` prolnutí
                     do stání, `spin` rychlost otočky.

   paths (volitelné) — trasy chodců (bod 9). Část chodců (ne všichni) dostane
   při příchodu trasu a jde po ní místo volného bloumání po pásu:
     name     jméno trasy
     loop     true = dokola, false = ping-pong (na konci se otočí)
     species  klíč druhu, pro který trasa platí; null = kdokoli
     points   lomená čára v podílech obrazovky (x šířky, y výšky); body smí
              za okraj (±0.25). `do`: 'walk' projde, 'stop' postojí
              (`dwell` = [min,max] s), 'turn' obrátí směr průchodu.
   Trasy jsou prostě napsané tady v datech (editor byl zrušen); trasa vedená
   po y některé dráhy se počítá i do kolizí na té dráze. */

import { trailX } from '/web/backdrops/forest.js';

const TRAIL = (y) => ({ x: +trailX(y).toFixed(3), y, do: 'walk' });

export default {
  backdrop: async () => (await import('/web/backdrops/forest.js')).create(),
  lighting: {
    hemi: { sky: 0xcfe2ff, ground: 0x5c5b3a, intensity: 1.05 },
    // slunce je na malovane obloze vpravo nahore, at stiny sedi
    sun: { color: 0xfff0d4, intensity: 2.1, position: [0.62, 1.35, 0.95] },
    fill: { color: 0x9fc4e8, intensity: 0.5, position: [-0.8, 0.3, 0.6] },
  },
  bands: [
    { name: 'sky', y0: 0.06, y1: 0.38, motions: ['fly'] },
    // vybarveni ptaci pouzivaji jen pasovou praci scene (pozice dava updateBird)
    { name: 'birds', y0: 0.05, y1: 0.50, motions: ['bird'] },
    { name: 'butterflies', y0: 0.46, y1: 0.86, motions: ['butterfly'] },
    // zadni louka pod lesem; lezi mezi 0,525 a 0,565 a 3D tvor stoji nohama
    // presne na yFrac, musi se tam vejit. Dve drahy: uzky pas vic linek
    // neunese. Zadni louka jde na ~3/4 tempa (je dal, bod 1).
    { name: 'shoreFar', y0: 0.525, y1: 0.565, motions: ['walk'], lane: 'far',
      lanes: [0.532, 0.558], rateScale: 0.75 },
    // tri drahy predni louky: rozestup 0.065 vysky (~58 px na FHD) drzi
    // linky chodidel zretelne oddelene, telesny prekryv resi z-order podle y
    { name: 'shore', y0: 0.80, y1: 0.95, motions: ['walk'], lane: 'near',
      lanes: [0.815, 0.88, 0.945] },
  ],
  motions: {
    walk: {
      sizeFraction: 0.234, baseSpeed: 0.030,
      // 30° od čistého profilu: dinosaurus je na obrazovce vysoký stovky px,
      // takže se vejde i bližší bok a předek hrudi — z ploché kulisy je objem.
      // Od ~45° se textura na čelních plochách roztahuje do šmouhy (kresba na
      // listu je bokorys, UV = pozice na listu), viz out/turn_strop_walk_sheet.png.
      turn: 0.524,
      strideRate: [0.12, 0.22],
      farChance: 0.35,
      // Poměr velikostí druhů: `sizePx` je odmocnina z plochy siluety, takže
      // bez mapy by zajíc vyšel stejně velký jako kůň. Hodnoty jsou přibližná
      // délka těla vůči koni (1,0), mírně přiblížená k sobě, aby zajíc
      // a liška na dětské obrazovce pořád šli rozeznat.
      scale: {
        horse: 1.0, stag: 0.92, alpaca: 0.80, deer: 0.66,
        wolf: 0.60, shiba_inu: 0.50, fox: 0.46, zajic: 0.36,
      },
      scaleDefault: 0.7,
      rest: { stand: [3, 9], fade: 0.7, spin: 0.5 },
      // planovac cinnosti: vetsinu casu chuze, zastaveni ma duvod (podivat
      // se na deti, rozhlednout se, odpocinout si az po delsi chuzi);
      // pole popisuje hlavicka scenes/cretaceous/render.js
      activities: {
        walk: { weight: 8, dur: [14, 30] },
        stand: { weight: 1, dur: [2, 4] },
        look: { weight: 3, dur: [2, 3.5] },
        lookaround: { weight: 2 },
        sit: { weight: 1.2, dur: [5, 9], after: 40 },
        lie: { weight: 0.8, dur: [5, 9], after: 70 },
        sleep: { chance: 0.5, dur: [8, 15], fade: 0.8 },
        jump: { weight: 0.4 },
        play: { weight: 0.4 },
        run: { weight: 0.8, dur: [1.5, 3], speed: 1.8, waitWeight: 0 },
        eat: { weight: 2, dur: [4, 8] },
        greet: { dur: [2.5, 4] },
        wait: { every: [3, 7], bored: 10 },
      },
    },
    // letec je vysoko, kde je perspektivni zmenseni nejvetsi, tak dostava vic
    // ptak sedi na vetvi blizko diveka a letu je malicky: sizeFraction je
    // zamerne vetsi nez u chodcu, aby z nej mel vybarvovatel radost
    bird: { sizeFraction: 0.24, baseSpeed: 0.03, turn: 0.45 },
    // motylek se kresli zepredu (turn pi/2), rozpeti je zhruba sizeFraction
    butterfly: { sizeFraction: 0.12, baseSpeed: 0.07, turn: 1.5708 },
    fly: { sizeFraction: 0.334, baseSpeed: 0.055, bob: true },
    swim: { baseSpeed: 0.030 },
    sail: { baseSpeed: 0.018 },
  },
  paths: [
    // Trasy vedou po louce a hlavně po cestičce z forest.js (trailX), takže
    // zvířata nechodí jen sem a tam po vodorovných dráhách. Okraje za obrazovkou
    // (x −0,2 / 1,2) dovolí zvířeti odejít z obrazu a vrátit se.
    {
      // po cestičce z dálky k divákovi, uprostřed postojí a rozhlédne se
      name: 'cestička', loop: false, species: null,
      points: [
        TRAIL(0.56), TRAIL(0.64),
        { ...TRAIL(0.74), do: 'stop', dwell: [3, 8] },
        TRAIL(0.84), TRAIL(0.925),
      ],
    },
    {
      // z lesa vpravo šikmo přes louku na cestičku a pryč doleva dole
      name: 'z lesa na louku', loop: false, species: null,
      points: [
        { x: 1.20, y: 0.548, do: 'walk' },
        { x: 0.82, y: 0.568, do: 'walk' },
        { ...TRAIL(0.68), do: 'stop', dwell: [3, 6] },
        { x: 0.36, y: 0.86, do: 'walk' },
        { x: -0.20, y: 0.92, do: 'walk' },
      ],
    },
    {
      // mezi kmeny: zastávka pod každým stromem, na který sedají ptáci
      name: 'ke kmenům', loop: false, species: null,
      points: [
        { x: 0.25, y: 0.85, do: 'stop', dwell: [5, 10] },
        { x: 0.55, y: 0.83, do: 'walk' },
        { x: 0.85, y: 0.85, do: 'stop', dwell: [5, 10] },
      ],
    },
    {
      // zadní louka pod lesem, uprostřed postojí
      name: 'zadní louka', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.545, do: 'walk' },
        { x: 0.50, y: 0.545, do: 'stop', dwell: [4, 9] },
        { x: 1.20, y: 0.545, do: 'walk' },
      ],
    },
    {
      name: 'přední louka', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.88, do: 'walk' },
        { x: 0.46, y: 0.88, do: 'stop', dwell: [3, 8] },
        { x: 1.20, y: 0.88, do: 'walk' },
      ],
    },
  ],
  // co spadne zvirecim z mobilu: jablka / seno / cukrovi; kazde zvire si vezme jedno soust
  food: { look: 'apples', bites: 4 },
  ambientMin: 6,
};
