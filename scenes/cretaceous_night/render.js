/* „Noční laguna" — táž krajina za soumraku. Levný důkaz mechanismu více
   scén: stejné pásy, stejní tvorové (catalogue 'cretaceous'), jen backdrop
   v noční variantě a tlumené osvětlení 3D vrstvy. */

import day from '/scenes/cretaceous/render.js';

export default {
  ...day,
  backdrop: async () => (await import('/web/backdrops/cretaceous.js')).create('night'),
  lighting: {
    hemi: { sky: 0x33456e, ground: 0x1c2233, intensity: 0.62 },
    // mesic sviti z tehoz mista jako slunce ve dne
    sun: { color: 0xc7d6ff, intensity: 1.05, position: [0.62, 1.35, 0.95] },
    fill: { color: 0x40557a, intensity: 0.35, position: [-0.8, 0.3, 0.6] },
  },
};
