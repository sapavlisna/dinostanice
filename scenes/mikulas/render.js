/* Definice scény „Mikulášská" — scéna jako data. Pole popisuje hlavička
   scenes/cretaceous/render.js, měřítka druhů (`motions.walk.scale`) a trasy
   po vyšlapané stopě hlavička scenes/les/render.js. Krajina je
   web/backdrops/mikulas.js: soumrak nad zasněženou návsí, dráhy tvorů leží
   před kulisou (y 0,70 / 0,815 / 0,93), všechno, co stojí na zemi, má patu výš.

   Postavy jsou lidé, ne zvířata: nelehnou si ani nespí (nemají klipy Sit,
   LieDown, Sleep), ale mávají (`play` = klip Wave), rozhlížejí se
   (`lookaround`) a čert skáče a běhá. Mikuláš běhat nebude (`activities.run`
   ve scene.json mu váhu vynuluje). */

import { pathX } from '/web/backdrops/mikulas.js';

const TRAIL = (y) => ({ x: +pathX(y).toFixed(3), y, do: 'walk' });

export default {
  backdrop: async () => (await import('/web/backdrops/mikulas.js')).create(),
  lighting: {
    // studený měsíční soumrak shora a teplé světlo oken a lucerny zleva
    hemi: { sky: 0xa8b4ec, ground: 0xe6e8f8, intensity: 1.0 },
    sun: { color: 0xc8d4ff, intensity: 1.55, position: [0.7, 1.25, 0.9] },
    fill: { color: 0xffb870, intensity: 0.75, position: [-0.8, 0.25, 0.7] },
  },
  bands: [
    // dráha před vánočním stromem a lucernami: pata stromu je v 0,64, lucerny
    // ve 0,69, takže tvor v 0,70 jde před nimi
    { name: 'shoreFar', y0: 0.685, y1: 0.715, motions: ['walk'], lane: 'far',
      lanes: [0.70], rateScale: 0.8 },
    { name: 'shore', y0: 0.78, y1: 0.96, motions: ['walk'], lane: 'near',
      lanes: [0.815, 0.93] },
  ],
  motions: {
    walk: {
      sizeFraction: 0.21, baseSpeed: 0.030,
      turn: 0.524,
      strideRate: [0.5, 0.7],
      farChance: 0.30,
      // postavy jsou štíhlé a vysoké, `sizePx` je odmocnina z plochy obdélníku
      // modelu; poměr výšek: Mikuláš 1,0, anděl o něco menší, čert nejmenší
      scale: { mik_mikulas: 1.0, mik_andel: 0.805, mik_cert: 0.78 },
      scaleDefault: 0.9,
      rest: { stand: [3, 9], fade: 0.7, spin: 0.5 },
      look: { max: 0.61, fade: 0.6 },
      activities: {
        walk: { weight: 8, dur: [14, 30] },
        stand: { weight: 1.2, dur: [2, 4] },
        look: { weight: 3, dur: [2, 3.5] },
        lookaround: { weight: 2 },
        jump: { weight: 0.4 },
        play: { weight: 1.2 },
        run: { weight: 0.6, dur: [1.5, 3], speed: 1.8, waitWeight: 0 },
        eat: { weight: 2, dur: [4, 8] },
        greet: { dur: [2.5, 4] },
        wait: { every: [3, 7], bored: 10 },
      },
    },
    fly: { sizeFraction: 0.30, baseSpeed: 0.055, bob: true },
  },
  paths: [
    {
      // po návsi rovně a uprostřed postojí (dráha 0,815)
      name: 'po návsi', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.815, do: 'walk' },
        { x: 0.42, y: 0.815, do: 'stop', dwell: [3, 8] },
        { x: 1.20, y: 0.815, do: 'walk' },
      ],
    },
    {
      // po vyšlapané stopě z dálky k divákovi, uprostřed postojí
      name: 'po stopě', loop: false, species: null,
      points: [
        TRAIL(0.70), TRAIL(0.76),
        { ...TRAIL(0.82), do: 'stop', dwell: [3, 7] },
        TRAIL(0.88), TRAIL(0.95),
      ],
    },
    {
      // k vánočnímu stromu: postojí pod ním a rozhlédne se
      name: 'k vánočnímu stromu', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.93, do: 'walk' },
        { x: 0.30, y: 0.90, do: 'walk' },
        { x: 0.52, y: 0.72, do: 'walk' },
        { x: 0.66, y: 0.70, do: 'stop', dwell: [5, 11] },
        { x: 1.20, y: 0.70, do: 'walk' },
      ],
    },
    {
      // Mikuláš obchází náves: dole zprava, nahoře k lucerně a pryč doleva
      name: 'Mikulášova obchůzka', loop: false, species: 'mik_mikulas',
      points: [
        { x: 1.20, y: 0.93, do: 'walk' },
        { x: 0.74, y: 0.93, do: 'stop', dwell: [4, 8] },
        { x: 0.46, y: 0.815, do: 'stop', dwell: [4, 8] },
        { x: -0.20, y: 0.815, do: 'walk' },
      ],
    },
    {
      // čert vyběhne zprava a vrací se zadem, kde číhá
      name: 'čert vyběhne', loop: false, species: 'mik_cert',
      points: [
        { x: 1.20, y: 0.815, do: 'walk' },
        { x: 0.74, y: 0.815, do: 'stop', dwell: [1.5, 3] },
        { x: 0.30, y: 0.93, do: 'walk' },
        { x: -0.20, y: 0.93, do: 'walk' },
      ],
    },
    {
      // anděl se zastaví pod stromem
      name: 'anděl u stromu', loop: false, species: 'mik_andel',
      points: [
        { x: -0.20, y: 0.70, do: 'walk' },
        { x: 0.50, y: 0.70, do: 'stop', dwell: [6, 12] },
        { x: 1.20, y: 0.70, do: 'walk' },
      ],
    },
  ],
  // co spadne zvirecim z mobilu: jablka / seno / cukrovi; kazde zvire si vezme jedno soust
  food: { look: 'sweets', bites: 4 },
  ambientMin: 5,
};
