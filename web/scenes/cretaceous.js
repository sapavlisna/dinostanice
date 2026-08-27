/* Definice scény „Křídová laguna" — scéna jako data.

   scene.js nezná žádné zóny ani konstanty krajiny; všechno čte odsud:

     key        klíč scény (musí sedět s registrem na serveru, scenes.py)
     catalogue  sada tvorů (Model3D.scene), kterou scéna doplňuje a přijímá
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
     lengthFraction  podíl šířky obrazovky pro 2D rig v nejbližším plánu
     sizeFraction    totéž pro 3D tvory (odmocnina z plochy siluety)
     baseSpeed       rychlost v podílu šířky/s pro tvory bez měřeného kroku
     strideRate      default cílového tempa chodce (těl/s); per druh ho
                     přebíjí `strideRate` z katalogu (vlastnost druhu)
     drift           podíl vodorovné rychlosti pro svislé sunutí po pásu
     driftRefHeight  výška pásu, pro kterou platí plný drift
     farChance       šance, že nový tvor padne na vedlejší (far) lane
     bob             sinusové houpání (letci)
     rest            zastávky/otočky; bez něj tvor nikdy nezastaví

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
  key: 'cretaceous',
  label: 'Křídová laguna',
  catalogue: 'cretaceous',
  backdrop: async () => (await import('../backdrops/cretaceous.js')).create('day'),
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
      lengthFraction: 0.17, sizeFraction: 0.234, baseSpeed: 0.030,
      strideRate: [0.12, 0.22],
      farChance: 0.35,
      rest: { walk: [11, 34], stand: [3, 9], fade: 0.7, jumpFade: 0.25,
              jump: 0.35, turn: 0.45, spin: 0.5 },
    },
    // letec je vysoko, kde je perspektivni zmenseni nejvetsi, tak dostava vic
    fly: { lengthFraction: 0.24, sizeFraction: 0.334, baseSpeed: 0.055, bob: true },
    swim: { lengthFraction: 0.19, baseSpeed: 0.030 },
    sail: { lengthFraction: 0.15, baseSpeed: 0.018 },
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
