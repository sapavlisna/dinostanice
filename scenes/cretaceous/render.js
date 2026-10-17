/* Definice scény „Křídová laguna" — scéna jako data.

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
                     krmení, činnosti) a otočit se na místě; bez něj tvor
                     nezastaví nikdy. `stand` = délka postání u jídla
                     (a default dwellu na trase), `fade` prolnutí do stání,
                     `spin` rychlost otočky.
     look            (volitelně) pohled k dětem: strop `max` (rad) a prolnutí
                     `fade` pro natočení krku a hlavy (činnosti look, greet).
     activities      nabídka plánovače činností (web/scenelogic.js), druh ji
                     smí přepsat polem `activities` ve scene.json. Každá
                     činnost: `weight` (váha při rozhodování za chůze),
                     `waitWeight` (váha při čekání ve frontě, default weight),
                     `dur` [min,max] s. Navíc: walk.dur = jak dlouho jde mezi
                     rozhodnutími (walk.weight = šance jít dál), sit/lie.after
                     = nejdřív po tolika s od posledního sednutí/lehnutí,
                     sleep.chance = šance usnout z lehu (fade = prolnutí),
                     run.speed = násobek rychlosti chůze, greet = zastavení
                     nového úlovku, eat = u jídla (a pastva, má-li druh klip),
                     wait.every/bored = jak často si čekající ve frontě něco
                     vybere a po kolika s smí i sednout/lehnout. Činnost,
                     ke které druh nemá klip, se nenabízí.

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
  backdrop: async () => (await import('/web/backdrops/cretaceous.js')).create('day'),
  lighting: {
    hemi: { sky: 0xcfe2ff, ground: 0x5c5b3a, intensity: 1.05 },
    // slunce je na malovane obloze vpravo nahore, at stiny sedi
    sun: { color: 0xfff0d4, intensity: 2.1, position: [0.62, 1.35, 0.95] },
    fill: { color: 0x9fc4e8, intensity: 0.5, position: [-0.8, 0.3, 0.6] },
  },
  bands: [
    { name: 'sky', y0: 0.06, y1: 0.38, motions: ['fly'] },
    // pruh pisku mezi lesem a lagunou, aby chodci mohli i za vodou; lezi mezi
    // 0,516 a 0,570 a 3D tvor stoji nohama presne na yFrac, musi se tam vejit.
    // Dve drahy: uzky pas vic linek neunese, tvor je i zmenseny vysoky desitky
    // px a linky by splyvaly. Zadni breh jde na ~3/4 tempa (je dal, bod 1).
    { name: 'shoreFar', y0: 0.525, y1: 0.565, motions: ['walk'], lane: 'far',
      lanes: [0.532, 0.558], rateScale: 0.75 },
    { name: 'water', y0: 0.645, y1: 0.755, motions: ['swim'] },
    { name: 'surface', y0: 0.645, y1: 0.745, motions: ['sail'] },
    // tri drahy predniho brehu: rozestup 0.065 vysky (~58 px na FHD) drzi
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
      rest: { stand: [3, 9], fade: 0.7, spin: 0.5 },
      // stojici chodec se obcas podiva na deti (jen krk a hlava, strop `max`
      // v rad — vic uz ukaze rozmazane celo, telo je samo natocene o `turn`)
      look: { max: 0.61, fade: 0.6 },
      // planovac cinnosti: vetsinu casu chuze, zastaveni ma duvod (podivat
      // se na deti, rozhlednout se, odpocinout si az po delsi chuzi)
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
        eat: { weight: 1, dur: [4, 8] },
        greet: { dur: [2.5, 4] },
        wait: { every: [3, 7], bored: 10 },
      },
    },
    // letec je vysoko, kde je perspektivni zmenseni nejvetsi, tak dostava vic
    fly: { sizeFraction: 0.334, baseSpeed: 0.055, bob: true },
    swim: { baseSpeed: 0.030 },
    sail: { baseSpeed: 0.018 },
  },
  paths: [
    // ukázka: rovná procházka po prostřední dráze předního břehu (y 0.88)
    // s jednou zastávkou — vede po dráze, takže nekříží ostatní linky a
    // vodorovný průběh drží prokluz chodidel na nule
    {
      name: 'přední břeh', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.88, do: 'walk' },
        { x: 0.46, y: 0.88, do: 'stop', dwell: [3, 8] },
        { x: 1.20, y: 0.88, do: 'walk' },
      ],
    },
  ],
  ambientMin: 6,
};
