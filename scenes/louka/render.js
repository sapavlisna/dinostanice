/* Definice scény „Louka" — scéna jako data. Hlavička vysvětluje pole stejně
   jako scenes/cretaceous/render.js; zvlášť pro louku je `motions.walk.scale`
   (poměr velikostí broučků) a krajina z web/backdrops/louka.js. Letí beruška
   a čmelák (`butterfly`), po louce se plazí a skáčou mravenec, kobylka,
   housenka, šnek a had (`walk`).

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

export default {
  backdrop: async () => (await import('/web/backdrops/louka.js')).create(),
  lighting: {
    hemi: { sky: 0xdcecff, ground: 0x6f8f3a, intensity: 1.15 },
    // slunce je na malovane obloze vpravo nahore, at stiny sedi
    sun: { color: 0xfff4dc, intensity: 2.4, position: [0.7, 1.4, 0.9] },
    fill: { color: 0xa8d0f0, intensity: 0.55, position: [-0.8, 0.3, 0.6] },
  },
  bands: [
    // beruska a cmelak poletuji nad celou loukou
    { name: 'butterflies', y0: 0.46, y1: 0.86, motions: ['butterfly'] },
    // zadni louka pod obzorem; lezi mezi 0,525 a 0,565 a 3D tvor stoji nohama
    // presne na yFrac, musi se tam vejit. Dve drahy: uzky pas vic linek
    // neunese. Zadni louka jde na ~3/4 tempa (je dal, bod 1).
    { name: 'shoreFar', y0: 0.525, y1: 0.565, motions: ['walk'], lane: 'far',
      lanes: [0.532, 0.558], rateScale: 0.75, except: ['snake', 'snail'] },
    // tri drahy predni louky: rozestup 0.065 vysky (~58 px na FHD) drzi
    // linky chodidel zretelne oddelene, telesny prekryv resi z-order podle y
    { name: 'shore', y0: 0.80, y1: 0.95, motions: ['walk'], lane: 'near',
      lanes: [0.815, 0.88, 0.945] },
  ],
  motions: {
    walk: {
      sizeFraction: 0.234, baseSpeed: 0.030,
      // 30° od čistého profilu, stejně jako v lese: z ploché kulisy je objem.
      turn: 0.524,
      // broučci se plazí: tempo je nízké, rychlost se z něj dopočítává
      strideRate: [0.05, 0.12],
      farChance: 0.35,
      // Poměr velikostí druhů: `sizePx` je odmocnina z plochy siluety, takže
      // bez mapy by mravenec vyšel stejně velký jako had. Je to broučí svět —
      // malí tvorové jsou malí, ale pořád čitelní na televizi.
      scale: {
        snake: 0.55, grasshopper: 0.45, caterpillar: 0.4, snail: 0.35, ant: 0.25,
      },
      scaleDefault: 0.4,
      rest: { stand: [3, 9], fade: 0.7, spin: 0.5 },
      // kobylka čas od času vyskočí z cesty na list stébla a zase seskočí
      perch: { species: ['grasshopper'], every: [14, 28], sit: [5, 11], hop: 0.85, arc: 0.05,
               reach: { x: 0.22, y: 0.22 } },
      // planovac cinnosti: vetsinu casu plazeni, zastaveni ma duvod (podivat
      // se na deti, rozhlednout se); co druh nema v klipech, se vyradi
      activities: {
        walk: { weight: 9, dur: [14, 30] },
        stand: { weight: 1.2, dur: [2, 4] },
        look: { weight: 3, dur: [2, 3.5] },
        lookaround: { weight: 2 },
        sleep: { chance: 0.3, dur: [8, 15], fade: 0.8 },
        eat: { weight: 2, dur: [4, 8] },
        greet: { dur: [2.5, 4] },
        wait: { every: [3, 7], bored: 10 },
      },
    },
    // beruska a cmelak jsou modely z listu (pohled shora); `side` je prehodi
    // do profilu, poletuji vodorovne
    butterfly: {
      sizeFraction: 0.12, baseSpeed: 0.07,
      // letí bokem (`side`), mírně natočený k divákovi, a skoro vodorovně
      side: true, turn: 0.4, vSpread: 0.05,
      scale: { bumblebee: 0.58, ladybug: 0.5 },
    },
    fly: { sizeFraction: 0.334, baseSpeed: 0.055, bob: true },
    swim: { baseSpeed: 0.030 },
    sail: { baseSpeed: 0.018 },
  },
  paths: [
    // Trasy vedou po louce: přední a zadní louka, kroužení a zastávky u květů.
    // Okraje za obrazovkou (x −0,2 / 1,2) dovolí broučkovi odejít z obrazu
    // a vrátit se.
    {
      // zadní louka pod obzorem, uprostřed postojí
      name: 'zadní louka', loop: false, species: null, except: ['snake'],
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
    {
      // od květu ke květu: cik-cak přes přední louku, u dvou kytek postojí
      name: 'od květu ke květu', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.84, do: 'walk' },
        { x: 0.22, y: 0.90, do: 'stop', dwell: [4, 8] },
        { x: 0.50, y: 0.83, do: 'walk' },
        { x: 0.74, y: 0.93, do: 'stop', dwell: [4, 8] },
        { x: 1.20, y: 0.86, do: 'walk' },
      ],
    },
    {
      // kroužení kolem trsu květů v popředí
      name: 'kolem trsu', loop: true, species: null,
      points: [
        { x: 0.34, y: 0.86, do: 'walk' },
        { x: 0.50, y: 0.82, do: 'walk' },
        { x: 0.66, y: 0.855, do: 'stop', dwell: [3, 6] },
        { x: 0.70, y: 0.91, do: 'walk' },
        { x: 0.50, y: 0.94, do: 'walk' },
        { x: 0.32, y: 0.915, do: 'stop', dwell: [3, 6] },
      ],
    },
    {
      // šikmo z dálky vpravo přes střední louku dopředu a pryč doleva
      name: 'přes louku', loop: false, species: null, except: ['snake'],
      points: [
        { x: 1.20, y: 0.548, do: 'walk' },
        { x: 0.80, y: 0.57, do: 'walk' },
        { x: 0.58, y: 0.70, do: 'stop', dwell: [3, 6] },
        { x: 0.34, y: 0.86, do: 'walk' },
        { x: -0.20, y: 0.92, do: 'walk' },
      ],
    },
    {
      // had se plazí zleva dopředu, uprostřed postojí a vpravo odchází nad QR
      // panelem (x > 0,70 a y > 0,78 je zakryté); vzadu by byl drobný a ztracený
      name: 'had', loop: false, species: 'snake',
      points: [
        { x: -0.25, y: 0.86, do: 'walk' },
        { x: 0.15, y: 0.90, do: 'walk' },
        { x: 0.42, y: 0.84, do: 'stop', dwell: [5, 9] },
        { x: 0.62, y: 0.77, do: 'walk' },
        { x: 0.90, y: 0.74, do: 'walk' },
        { x: 1.25, y: 0.74, do: 'walk' },
      ],
    },
    {
      // šnek: krátká cesta k jednomu květu, kde dlouho posedí
      name: 'šnek ke květu', loop: false, species: 'snail',
      points: [
        { x: 0.12, y: 0.90, do: 'walk' },
        { x: 0.40, y: 0.86, do: 'stop', dwell: [8, 14] },
        { x: 0.62, y: 0.88, do: 'walk' },
        { x: 0.40, y: 0.86, do: 'turn' },
      ],
    },
    {
      // mravenci chodí dokola po stejné stezce tam a zpět
      name: 'mravenčí stezka', loop: true, species: 'ant',
      points: [
        { x: -0.10, y: 0.945, do: 'walk' },
        { x: 0.30, y: 0.935, do: 'walk' },
        { x: 0.55, y: 0.945, do: 'stop', dwell: [2, 4] },
        { x: 1.10, y: 0.94, do: 'walk' },
        { x: 0.55, y: 0.945, do: 'walk' },
        { x: 0.30, y: 0.935, do: 'walk' },
      ],
    },
  ],
  // co spadne broucum z mobilu: jablka; kazdy brouk si vezme jedno soust
  food: { look: 'apples', bites: 4 },
  ambientMin: 6,
};
