/* Definice scény „Křídová laguna" — scéna jako data.

   scene.js nezná žádné zóny ani konstanty krajiny; všechno čte odsud:

     key        klíč scény (musí sedět s registrem na serveru, scenes.py)
     catalogue  sada tvorů (Model3D.scene), kterou scéna doplňuje a přijímá
     backdrop   async továrna na kreslič krajiny {draw, drawFront, sun, depthScale}
     lighting   světla 3D vrstvy (Scene3D.setLighting)
     bands      pásy scény: y0/y1 v podílu výšky plátna, `motions` říká, kdo
                se v pásu smí pohybovat, `lane` odlišuje víc pásů téhož pohybu
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
     rest            zastávky/otočky; bez něj tvor nikdy nezastaví */

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
    // 0,516 a 0,570 a 3D tvor stoji nohama presne na yFrac, musi se tam vejit
    { name: 'shoreFar', y0: 0.525, y1: 0.565, motions: ['walk'], lane: 'far' },
    { name: 'water', y0: 0.645, y1: 0.755, motions: ['swim'] },
    { name: 'surface', y0: 0.645, y1: 0.745, motions: ['sail'] },
    { name: 'shore', y0: 0.80, y1: 0.95, motions: ['walk'], lane: 'near' },
  ],
  motions: {
    walk: {
      lengthFraction: 0.17, sizeFraction: 0.234, baseSpeed: 0.030,
      strideRate: [0.12, 0.22],
      drift: 0.3, driftRefHeight: 0.15, farChance: 0.35,
      rest: { walk: [11, 34], stand: [3, 9], fade: 0.7, jumpFade: 0.25,
              jump: 0.35, turn: 0.45, spin: 0.5 },
    },
    // letec je vysoko, kde je perspektivni zmenseni nejvetsi, tak dostava vic
    fly: { lengthFraction: 0.24, sizeFraction: 0.334, baseSpeed: 0.055, bob: true },
    swim: { lengthFraction: 0.19, baseSpeed: 0.030 },
    sail: { lengthFraction: 0.15, baseSpeed: 0.018 },
  },
  ambientMin: 6,
};
