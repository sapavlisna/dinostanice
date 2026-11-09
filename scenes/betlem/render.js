/* Definice scény „Betlém" — noční krajina s chlévkem, ohništěm pastýřů
   a cestou, po které zvířata chodí k jesličkám. Pole jsou popsaná
   v scenes/les/render.js a scenes/cretaceous/render.js; tady je jen to, co
   je pro Betlém jinak:

     - dvě sady drah před chlévkem (střední 0,715 / 0,775, přední 0,855 / 0,915);
       za chlévkem dráha není, protože tvor se kreslí vždy NAD malovanou
       krajinou a procházel by střechou
     - světla: studený měsíc zleva, teplá záře chlévku zprava
     - trasy ke chlévku, k ohništi a na stání po stranách jeslí
     - poměr velikostí druhů (`scale`): velbloud největší, ovce a koza malé */

import { trailX } from '/web/backdrops/betlem.js';

const TRAIL = (y) => ({ x: +trailX(y).toFixed(3), y, do: 'walk' });

export default {
  backdrop: async () => (await import('/web/backdrops/betlem.js')).create(),
  lighting: {
    hemi: { sky: 0x5a6aa8, ground: 0x2c2436, intensity: 0.95 },
    // měsíc svítí zleva shora, ať stíny sedí na malovanou oblohu
    sun: { color: 0xb4c4ff, intensity: 1.15, position: [-0.62, 1.25, 0.95] },
    // teplo z jeslí a od ohně z pravé strany a zpředu
    fill: { color: 0xffb06a, intensity: 1.25, position: [0.95, 0.30, 0.75] },
  },
  bands: [
    // dráhy před chlévkem: střední jde na ~7/8 tempa (je dál), přední na plné
    { name: 'near', y0: 0.84, y1: 0.95, motions: ['walk'], lane: 'near',
      lanes: [0.855, 0.915] },
    { name: 'mid', y0: 0.69, y1: 0.80, motions: ['walk'], lane: 'far',
      lanes: [0.715, 0.775], rateScale: 0.88 },
    // andel a hvezdy se vznaseji nad chlevem, pasy jen pro bookkeeping (polohu dava updateHover)
    { name: 'sky', y0: 0.08, y1: 0.45, motions: ['hover', 'twinkle'] },
  ],
  motions: {
    // andel se vznasi nad chlevkem (chlevek je ~0,51–0,78 sirky, strecha ~0,43 vysky)
    hover: {
      sizeFraction: 0.30, bob: 0.014,
      spots: [{ x: 0.645, y: 0.285 }, { x: 0.745, y: 0.31 }, { x: 0.545, y: 0.32 }],
      area: { x: [0.5, 0.8], y: [0.2, 0.36] },
    },
    // vybarvene hvezdy poletuji kolem velke malovane hvezdy
    twinkle: {
      sizeFraction: 0.13, bob: 0.01, pulse: 0.07,
      spots: [{ x: 0.70, y: 0.13 }, { x: 0.43, y: 0.18 }, { x: 0.83, y: 0.22 }, { x: 0.30, y: 0.10 },
              { x: 0.58, y: 0.24 }],
      area: { x: [0.15, 0.9], y: [0.06, 0.28] },
    },
    walk: {
      sizeFraction: 0.234, baseSpeed: 0.030,
      turn: 0.524,
      strideRate: [0.12, 0.22],
      farChance: 0.45,
      // `sizePx` je odmocnina z plochy siluety, takže bez mapy by měla ovce
      // stejnou velikost jako velbloud. Hodnoty odpovídají délce těla vůči
      // velbloudu (1,0), mírně přiblížené, ať ovce a koza na obrazovce zůstanou
      // poznat.
      scale: {
        camel: 1.0, bull: 0.78, donkey: 0.66, goat: 0.52, sheep: 0.50,
      },
      scaleDefault: 0.7,
      rest: { stand: [3, 9], fade: 0.7, spin: 0.5 },
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
        run: { weight: 0.5, dur: [1.5, 3], speed: 1.8, waitWeight: 0 },
        eat: { weight: 2.5, dur: [4, 8] },
        greet: { dur: [2.5, 4] },
        wait: { every: [3, 7], bored: 10 },
      },
    },
    swim: { baseSpeed: 0.030 },
    sail: { baseSpeed: 0.018 },
  },
  paths: [
    // Trasy sledují cestu z betlem.js (trailX) a končí po stranách jeslí,
    // aby zvířata nestála před Svatou rodinou. Okraje za obrazovkou
    // (x −0,2 / 1,2) dovolí zvířeti odejít z obrazu a vrátit se.
    {
      // cestou z popředí ke chlévku, tam postojí a rozhlédne se
      name: 'ke chlévku', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.95, do: 'walk' },
        TRAIL(0.90), TRAIL(0.82), TRAIL(0.77),
        { x: 0.445, y: 0.755, do: 'stop', dwell: [5, 10] },
      ],
    },
    {
      // zprava k chlévku z pastvy
      name: 'z pastvy', loop: false, species: null,
      points: [
        { x: 1.20, y: 0.90, do: 'walk' },
        { x: 0.98, y: 0.86, do: 'walk' },
        { x: 0.80, y: 0.82, do: 'walk' },
        { x: 0.665, y: 0.80, do: 'stop', dwell: [4, 8] },
      ],
    },
    {
      // osel stojí vlevo od jeslí
      name: 'osel u jeslí', loop: false, species: 'donkey',
      points: [
        { x: -0.20, y: 0.93, do: 'walk' },
        TRAIL(0.86), TRAIL(0.78),
        { x: 0.555, y: 0.742, do: 'stop', dwell: [10, 20] },
      ],
    },
    {
      // vůl stojí vpravo od jeslí
      name: 'vůl u jeslí', loop: false, species: 'bull',
      points: [
        { x: 1.20, y: 0.88, do: 'walk' },
        { x: 0.96, y: 0.84, do: 'walk' },
        { x: 0.84, y: 0.78, do: 'walk' },
        { x: 0.745, y: 0.742, do: 'stop', dwell: [10, 20] },
      ],
    },
    {
      // velbloudi tří králů přijdou zprava a postojí u stromů
      name: 'králové', loop: false, species: 'camel',
      points: [
        { x: 1.20, y: 0.78, do: 'walk' },
        { x: 1.02, y: 0.775, do: 'walk' },
        { x: 0.93, y: 0.77, do: 'stop', dwell: [8, 16] },
      ],
    },
    {
      // ovce se vracejí k ohništi pastýřů
      name: 'k ohništi', loop: false, species: 'sheep',
      points: [
        { x: -0.20, y: 0.72, do: 'walk' },
        { x: 0.12, y: 0.725, do: 'walk' },
        { x: 0.255, y: 0.72, do: 'stop', dwell: [6, 14] },
      ],
    },
    {
      // koza pase na svahu pod ohrazením
      name: 'svah', loop: false, species: 'goat',
      points: [
        { x: -0.20, y: 0.715, do: 'walk' },
        { x: 0.20, y: 0.715, do: 'stop', dwell: [4, 9] },
        { x: 0.40, y: 0.72, do: 'walk' },
      ],
    },
    {
      // přední louka přes celou obrazovku
      name: 'přední cesta', loop: false, species: null,
      points: [
        { x: -0.20, y: 0.915, do: 'walk' },
        { x: 0.50, y: 0.915, do: 'stop', dwell: [3, 8] },
        { x: 1.20, y: 0.915, do: 'walk' },
      ],
    },
  ],
  // co spadne zvirecim z mobilu: jablka / seno / cukrovi; kazde zvire si vezme jedno soust
  food: { look: 'hay', bites: 4 },
  ambientMin: 6,
  // nad chlevem je vzdycky andel a hvezda (vybarvene se pridavaji k nim)
  ambientExtras: ['betlem_andel', 'star'],
};
