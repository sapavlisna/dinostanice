/* Definice scény „Akvárium" — scéna jako data (viz komentář v cretaceous.js).

   Celá scéna je jeden vodní pás rozdělený na čtyři dráhy v různých hloubkách:
   ryba jednu dostane při příchodu, drží se v jejím okolí a na jinou přeskočí
   až za okrajem obrazovky (swapBand). Ryby se tedy míjejí v hloubce a nemusí
   se řešit kolizní fronta jako u chodců — plavec nikdy nezastaví.

   Co k plavání přidávají `motions.swim` proti chodci:
     scale/scaleDefault  relativní velikost druhu (sizePx modelu je
                         normalizovaný, takže bez mapy by byl žralok stejně
                         velký jako klaun)
     speedSize/beatSize  exponenty velikosti: rychlost roste s velikostí
                         POMALEJI než tělo (velká ryba se sune, malá švihá),
                         tempo animace naopak s velikostí klesá — malá ryba
                         mrská ocasem hustěji
     wave/waveRate       mírné vlnění ve svislé ose (dech plavce)
     sway/swayRate       pomalý drift mezi hloubkami kolem přidělené dráhy
     chase               jak rychle ryba mění hloubku za jídlem a zpátky
     dash                zrychlení, když ryba zabere za jídlem
     dodge               o kolik si dvě ryby v téže hloubce uhnou při míjení
     turnEvery           odstup otoček (bez zastavení, viz turnMoving)
     turnMoving          otočka se nedělá na místě: ryba do ní zpomalí, projde
                         čelem k divákovi a zabere na druhou stranu
     spin                jak dlouho otočka trvá
     turn                natočení k divákovi v radiánech (viz cretaceous.js)

   `rest` tu záměrně NENÍ: plavec nemá do čeho prolnout (katalog mu dává jen
   klip plavání) a hlavně nemá proč stát — žádné zastávky, žádné lehání,
   žádná kolizní fronta. `paths` taky ne, ryby plavou volně. */

export default {
  backdrop: async () => (await import('/web/backdrops/aquarium.js')).create(),
  lighting: {
    // pod vodou je světlo modré a rozptýlené: silná obloha, slabší směrové
    // světlo shora (od hladiny) a modrozelené doplňkové zezdola od písku
    hemi: { sky: 0xa8e4ff, ground: 0x0e4a68, intensity: 1.30 },
    sun: { color: 0xd8f4ff, intensity: 1.15, position: [-0.2, 1.5, 0.8] },
    fill: { color: 0x2e86bd, intensity: 0.55, position: [0.7, -0.4, 0.5] },
  },
  bands: [
    // Pás vody mezi hladinou (0.075) a pískem (0.665). Čtyři dráhy s rozestupem
    // ~0.12 výšky: ryba se od své dráhy vzdálí nejvýš o `sway`, takže hloubky
    // zůstanou rozeznatelné a ryby si při míjení nelezou do těla.
    { name: 'water', y0: 0.150, y1: 0.660, motions: ['swim'],
      lanes: [0.235, 0.360, 0.485, 0.605] },
  ],
  motions: {
    swim: {
      // ryba je proti dinosaurovi drobná; velikost per druh dolaďuje `scale`
      sizeFraction: 0.140, baseSpeed: 0.070,
      // 25°, o pět stupňů méně než chodec: ryba má na obrazovce jen stovku px
      // a poznává se podle siluety, kterou natočení krátí — ve 30° se mečounovi
      // zkrátí meč a perutýnovi se vějíř trnů sbalí do svazku
      // (out/turn_swim_sheet.png), ve 25° obojí drží a bok už dá objem
      turn: 0.436,
      // Axolotl je dlouhy jako ctverzubec (dospelec ~25 cm), ale mnohem
      // stihlejsi — a `scale` skaluje odmocninu z plochy siluety, ne delku.
      // Pri 0,68 by na obrazovce byl o treti delsi nez ctverzubec; 0,52 mu da
      // stejnou delku (zmereno: 218 px proti 217 px na sirce 1920) a stihlost
      // si nechá.
      scale: {
        clownfish: 0.58, butterflyfish: 0.55, angelfish: 0.60, guppy: 0.48,
        puffer: 0.68, lionfish: 0.66, anglerfish: 0.74, seahorse: 0.50,
        axolotl: 0.52,
        turtle: 0.90, ray: 1.10, manta: 1.30, swordfish: 1.05,
        barracuda: 1.00, shark: 1.45, whale: 1.60, orca: 1.55,
      },
      scaleDefault: 0.85,
      speedSize: 0.45, beatSize: -0.55,
      wave: 0.0075, waveRate: [0.9, 1.8],
      sway: 0.030, swayRate: [0.045, 0.13],
      // uhnutí je půlka na každou rybu, takže rozestup dvou míjejících se
      // ryb je 2×`dodge` — pod rozestupem drah (0.125), aby uhýbající ryba
      // nedoplavala na hloubku souseda
      chase: 0.15, dash: 1.7, dodge: 0.055,
      turnEvery: [11, 28], turnMoving: true, spin: 0.45,
    },
  },
  /* Krmení: v akváriu padá jídlo k hladině a klesá ke dnu, ryby v okolí za ním
     plavou do hloubky. `bites` je, kolik ryb se u něj vystřídá, než ho snědí;
     kdo zabere, jde do toho rychleji (`dash`) a v rychlejším klipu (role `fast`
     z katalogu). */
  food: {
    motion: 'swim', sink: true, look: 'flakes',
    top: 0.11, floor: 0.655, sinkRate: 0.045, life: 18, bites: 5,
  },
  ambientMin: 8,
};
