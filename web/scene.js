/* The living scene: keeps the cast, moves them through their habitats and
   listens for new arrivals. Drawing the landscape is backdrop's job, posing a
   3D creature is scene3d's; this file only decides who is where.

   Tvor postaveny z hotoveho 3D modelu se kresli do WebGL vrstvy nad krajinou,
   stary ohybany 2D rig primo do platna s krajinou. Scena s obema pracuje
   stejne — lisi se az posledni krok, vykresleni. */

import * as Scene3D from './scene3d.js';
import * as Tune from './tune.js';
import * as Roster from './roster.js';

const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d', { alpha: false });
const fx = document.getElementById('stagefx');
const fxCtx = fx.getContext('2d');
const gl = document.getElementById('stage3d');
const toastEl = document.getElementById('toast');
const errEl = document.getElementById('err');
const hintEl = document.getElementById('hint');

const MAX_ACTORS = 18;
// podil sirky obrazovky, ktery ma tvor zabrat v nejblizsim planu; letec je
// vysoko, kde je perspektivni zmenseni nejvetsi, tak dostava vic
const LENGTH_FRACTION = { walk: 0.17, swim: 0.19, fly: 0.24, sail: 0.15 };
// totez pro 3D tvory, kde se nemeri delka, ale odmocnina z plochy siluety
const SIZE_FRACTION = { walk: 0.234, fly: 0.334 };
// Defaultni pasy sceny, kdyz Backdrop zadne nedodal (ladeni bez krajiny).
// Stejny tvar jako Backdrop.bands: kazdy pas rika, ktere pohyby unese, a
// `lane` odlisuje vic pasu tehoz pohybu.
const FALLBACK_BANDS = [
  { name: 'sky', y0: 0.06, y1: 0.40, motions: ['fly'] },
  { name: 'shore', y0: 0.60, y1: 0.72, motions: ['walk'], lane: 'near' },
  { name: 'water', y0: 0.58, y1: 0.86, motions: ['swim'] },
  { name: 'surface', y0: 0.60, y1: 0.70, motions: ['sail'] },
];
// zakladni rychlost pohybu po scene v podilu sirky obrazovky za sekundu; chodec
// z 3D modelu si ji spocita sam z delky kroku, tohle plati pro ostatni
const BASE_SPEED = { walk: 0.030, swim: 0.030, fly: 0.055, sail: 0.018 };
// Kolik delek tela za sekundu ma ktery druh urazit — vychazi z paleo odhadu
// rychlosti chuze (viz out/audit/animator.md, sekce 2). U triceratopse a
// stegosaura je horni mez lehce pod paleo maximem, at scena nepusobi
// uspechane; velociraptor je kompromis, protoze scena normalizuje velikosti.
// Cyklus animace se smi zrychlit nebo zpomalit jen v rozmezi GAIT_RATE — po
// scene se pak tvor posouva presne tak, jak mu vyjdou kroky, takze nikdy
// neklouze.
const STRIDE_RATE = {
  trex3d: [0.11, 0.18],
  apatosaurus3d: [0.05, 0.09],
  triceratops3d: [0.17, 0.28],
  stegosaurus3d: [0.16, 0.26],
  velociraptor3d: [0.30, 0.40],
  parasaurolophus3d: [0.14, 0.25],
  default: [0.12, 0.22],
};
// Jen pojistka proti grotesknimu tempu animace; cil urcuje STRIDE_RATE.
const GAIT_RATE = { min: 0.4, max: 1.8 };
// Doladeno okem na televizi, klic je druh z katalogu. `rate` je tempo animace,
// `speed` nasobek dopoctene rychlosti. Cisla vypadnou z ladiciho panelu
// (klavesa d).
const BAKED = {};
// Zastavky. Bez nich to byla prehlidka: vsichni porad vpred, nikdo nikdy nestoji.
// `walk` je jak dlouho chodec jde, nez se zastavi, `stand` jak dlouho postoji,
// `fade` jak dlouho trva uklidneni (skok zacina rychleji, at se stihne odrazit).
// `jump` je sance, ze ze zastavky bude skok, `turn` ze se tvor po stani otoci a
// pujde zpatky.
const REST = {
  walk: [11, 34], stand: [3, 9], fade: 0.7, jumpFade: 0.25,
  jump: 0.35, turn: 0.45, spin: 0.5,
};
// Podil vodorovne rychlosti, kterym se chodec sune po pasu brehu dopredu nebo
// dozadu. Bez toho jdou vsichni po jedne lince zleva doprava. Plati pro pas
// vysoky DRIFT_REF_HEIGHT; uzsi pasy dostanou pomerne min (viz driftFor).
const DRIFT = 0.3;
const DRIFT_REF_HEIGHT = 0.15;
// Sance, ze chodec padne na vedlejsi (vzdalenou) lane misto hlavni.
const FAR_CHANCE = 0.35;
// Na kolik tvoru scenu doplnit z katalogu, nez neco prinesou deti. Prazdna
// krajina na televizi nikoho neprilaka a ukazkove textury vypadaji jako
// vybarvene, takze je poznat, o co jde.
const AMBIENT_MIN = 6;

const actors = [];
const byKey = new Map();
let ambientQueue = [];
let ambientSeq = 0;
let spawnSeq = 0;
let has3D = false;
let dpr = 1, W = 0, H = 0, lastFrame = 0, sceneTime = 0;

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  W = canvas.clientWidth;
  H = canvas.clientHeight;
  for (const c of [canvas, fx]) {
    c.width = Math.round(W * dpr);
    c.height = Math.round(H * dpr);
    c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  Scene3D.resize(W, H);
  if (window.Backdrop && Backdrop.resize) Backdrop.resize(W, H);
}
window.addEventListener('resize', resize);

/* Pasy, ktere umi dany pohyb. Kdyz je Backdrop nezna (nebo pro pohyb zadny
   nema), plati default — chodec tak nikdy nespadne do vody, protoze zadny
   walk pas ji neobsahuje. */
function bandsFor(motion) {
  const all = (window.Backdrop && Backdrop.bands) || FALLBACK_BANDS;
  let fit = all.filter(b => (b.motions || []).includes(motion));
  if (!fit.length) fit = FALLBACK_BANDS.filter(b => b.motions.includes(motion));
  return fit.length ? fit : [FALLBACK_BANDS[1]];
}

/* Novy tvor padne z FAR_CHANCE na nekterou vedlejsi lane (dnes vzdaleny breh),
   at ma scena hloubku; jinak jde hlavni (blizkou) lane. */
function pickBand(motion) {
  const fit = bandsFor(motion);
  if (fit.length === 1) return fit[0];
  const near = fit.find(b => b.lane !== 'far') || fit[0];
  const rest = fit.filter(b => b !== near);
  return Math.random() < FAR_CHANCE
    ? rest[Math.floor(Math.random() * rest.length)] : near;
}

/* Svisly drift se skaluje vyskou pasu: v uzkem vzdalenem brehu by tvor s plnym
   driftem kmital mezi okraji kazde ~4 s. Reference je vyska predniho brehu. */
function driftFor(band) {
  return (Math.random() * 2 - 1) * DRIFT
       * Math.min(1, (band.y1 - band.y0) / DRIFT_REF_HEIGHT);
}

function depthScale(yFrac) {
  if (window.Backdrop && Backdrop.depthScale) return Backdrop.depthScale(yFrac);
  return 0.35 + 0.65 * Math.max(0, Math.min(1, (yFrac - 0.35) / 0.55));
}

function bodyLengthMm(rig) {
  const s = rig.sizeMm;
  if (typeof s === 'number') return s;
  if (s && typeof s.w === 'number') return Math.max(s.w, s.h || 0);
  return 240;
}

function span([lo, hi]) {
  return lo + Math.random() * (hi - lo);
}

function addActor(what, opts) {
  // dedup podle id: race pri startu (connect bezi soubezne s restoreCast) nebo
  // rekonciliace po reconnectu nesmi privest tehoz tvora dvakrat
  if (what.id && actors.some(a => a.id === what.id)) {
    if (what.m3) Scene3D.remove(what.m3);    // uz nacteny klon nesmi leaknout
    return null;
  }
  const motion = what.motion || 'walk';
  const band = pickBand(motion);
  const yFrac = band.y0 + Math.random() * (band.y1 - band.y0);
  const dir = Math.random() < 0.5 ? 1 : -1;
  // rychlost i tempo cyklu maji jednu spolecnou nahodu, aby rychlejsi tvor
  // zaroven casteji maval kridly nebo vesloval
  const pace = 0.75 + Math.random() * 0.5;
  const actor = {
    ...what, motion, yFrac, dir, band, pace,
    // Tvory, kteri uz ve sceně "byli" (obnovene ulovky, doplnek z katalogu),
    // rozsazuje zlaty rez, ne nahoda: nahodnych sest cisel se casto sesype do
    // jednoho rohu a pul obrazovky zustane prazdna.
    xFrac: opts && opts.silent ? (spawnSeq++ * 0.6180339887 + 0.1) % 1
                               : (dir > 0 ? -0.15 : 1.15),
    phase: Math.random(),
    speed: (BASE_SPEED[motion] || BASE_SPEED.walk) * pace,
    bob: Math.random() * Math.PI * 2,
    // prvni zastavka az za chvili, at scena po nacteni nezacne stat
    restAt: sceneTime + span(REST.walk),
    restUntil: 0,
    pause: '',
    shown: '',
    fade: REST.fade,
    mix: 0,
    face: dir,
    drift: driftFor(band),
    born: sceneTime,
    label: what.label || 'tvor',
    who: (opts && opts.who) || '',
    ambient: !!(opts && opts.ambient),
  };
  actor.autoRate = 1;
  actor.autoSpeed = actor.speed;
  if (actor.m3 && actor.m3.strideBodies) {
    // Chodec: tempo cyklu se vybere kolem prirozeneho tempa druhu a rychlost po
    // scene se z nej dopocita, ne naopak — chodidla tak zustanou na zemi.
    actor.natural = actor.m3.strideBodies / actor.m3.duration;   // delek tela/s
    const [lo, hi] = STRIDE_RATE[actor.key] || STRIDE_RATE.default;
    const want = lo + Math.random() * (hi - lo);
    actor.autoRate = Math.max(GAIT_RATE.min, Math.min(GAIT_RATE.max, want / actor.natural))
                   * (0.94 + 0.12 * Math.random());
    actor.autoSpeed = actor.natural * actor.autoRate * bodyFrac(actor);
  } else if (actor.m3) {
    actor.autoRate = pace;         // letec: rychleji maka kridly, rychleji leti
  }
  applyGait(actor);
  actors.push(actor);
  while (actors.length > MAX_ACTORS) {
    // nejdriv odejde doplnek z katalogu, teprve pak nejstarsi ulovek
    const amb = actors.findIndex(a => a.ambient);
    dropActor(amb >= 0 ? amb : 0);
  }
  Roster.event('in', actor.label, actor.who);
  Roster.cast(actors);
  return actor;
}

/* Podil sirky obrazovky, ktery zabere telo tvora — z nej se pocita rychlost po
   scene, aby vzdaleny tvor slapal stejne a jen se posouval pomaleji. */
function bodyFrac(a) {
  return (SIZE_FRACTION[a.motion] || SIZE_FRACTION.walk)
       * depthScale(a.yFrac) * a.m3.length / a.m3.sizePx;
}

/* Tempo cyklu a rychlost po scene. Obojí se dá přeladit v ladicím panelu
   (klávesa d): `rate` je tempo animace, `speed` násobek dopočítané rychlosti.
   Když se mění jen tempo, rychlost jde s ním, aby chodidla zůstala na zemi. */
function applyGait(a) {
  const t = { ...BAKED[a.key], ...Tune.of(a.key) };
  a.rate = t.rate || a.autoRate;
  a.speedMul = t.speed || 1;
  a.speed = a.autoSpeed * (a.rate / a.autoRate) * a.speedMul;
}

function dropActor(i) {
  const [gone] = actors.splice(i, 1);
  if (!gone) return;
  if (gone.m3) Scene3D.remove(gone.m3);
  Roster.event('out', gone.label, gone.who);
  Roster.cast(actors);
}

function nextAmbient() {
  if (!ambientQueue.length) {
    ambientQueue = [...byKey.values()].sort(() => Math.random() - 0.5);
  }
  return ambientQueue.shift();
}

let topping = false;

async function topUp() {
  if (topping || !has3D || !byKey.size) return;  // dve soubezna volani by prelila AMBIENT_MIN
  topping = true;
  try {
    while (actors.length < AMBIENT_MIN) {
      const spec = nextAmbient();
      try {
        await loadModel({ kind: 'model', creature: spec.key, texture: spec.texture,
                          id: `katalog-${spec.key}-${ambientSeq++}` },
                        { silent: true, ambient: true });
      } catch (e) {
        note('katalog: ' + e.message);
        return;
      }
    }
  } finally {
    topping = false;
  }
}

function makeRoom() {
  // ulovek ma prednost pred tvorem z katalogu; ten odejde, at scena nezhoustne
  if (actors.length <= AMBIENT_MIN) return;
  const i = actors.findIndex(a => a.ambient);
  if (i >= 0) dropActor(i);
}

/* Po obchuzi scény přejde tvor na další lane téhož pohybu: kdo šel vzadu,
   vrací se vepředu. Každý dinosaurus se tak aspoň jednou ukáže zblízka a scéna
   nemá pořád stejné obsazení popředí. Pohyb s jedinou lane žádný přeskok nemá;
   přeskok padne za okraj obrazovky, takže ho není vidět. */
function swapBand(a) {
  const fit = bandsFor(a.motion);
  if (fit.length < 2) return;
  a.band = fit[(fit.indexOf(a.band) + 1) % fit.length];
  a.yFrac = a.band.y0 + Math.random() * (a.band.y1 - a.band.y0);
  a.drift = driftFor(a.band);
}

function toward(value, goal, step) {
  return value + Math.max(-step, Math.min(step, goal - value));
}

/* Zastavky a otocky.

   `mix` je podil zastavene pozy: rychlost po scene i tempo animace se jim krati
   stejne, takze pri zpomalovani chodidla drzi na zemi zrovna tak jako za chuze.
   Zastavit se muze jen ten, kdo ma do ceho prolnout — letec ne, ten by spadl.

   Otoceni se veze na zastavce: tvor se zastavi, na miste se prehoupne celem k
   divakovi na druhou stranu a pak jde zpatky. Dokud se otaci, drzi se `mix` na
   jednicce, aby se otacel na miste a ne v pohybu. */
function rest(a, dt) {
  const can = a.motion === 'walk' && (!a.m3 || a.m3.action);
  if (can && !a.pause && sceneTime > a.restAt) {
    const jump = a.m3 && a.m3.breakDur.jump && Math.random() < REST.jump;
    a.pause = jump ? 'jump' : 'stand';
    a.fade = jump ? REST.jumpFade : REST.fade;
    a.restUntil = sceneTime + (jump ? a.m3.breakDur.jump : span(REST.stand));
    if (jump) Scene3D.restart(a.m3, 'jump');
  }
  if (a.pause && sceneTime > a.restUntil) {
    if (a.pause === 'stand' && Math.random() < REST.turn) a.dir = -a.dir;
    a.pause = '';
    a.restAt = sceneTime + span(REST.walk);
  }

  // Prolinana poza se drzi, dokud se nedomixuje: kdyby se prepnula hned, jak
  // skok skonci, skacici tvor by cuknul do stojaci pozy.
  if (!a.mix) a.shown = a.pause;
  a.face = toward(a.face, a.dir, dt / REST.spin);
  const target = a.pause || a.face !== a.dir ? 1 : 0;
  a.mix = toward(a.mix, target, dt / a.fade);
  if (a.m3) {
    Scene3D.speed(a.m3, a.rate * (1 - a.mix));
    Scene3D.blend(a.m3, a.shown || 'stand', a.mix);
  }
}

function update(dt) {
  for (const a of actors) {
    rest(a, dt);
    if (a.natural) {
      // hloubka se mení chuzí po pásu, a s ní i to, kolik pixelů je jeden krok
      a.autoSpeed = a.natural * a.autoRate * bodyFrac(a);
      applyGait(a);
    }
    // 3D chodec jede po kumulativni krivce klipu, ne prumernou rychlosti —
    // stojna noha se v klipu nesune konstantne a prumer nechava chodidla
    // klouzat. `walked` cte timeScale, takze zastavka (mix) je v tom zdarma.
    const stepBodies = a.natural ? Scene3D.walked(a.m3, dt) : null;
    const go = stepBodies !== null
      ? stepBodies * bodyFrac(a) * a.speedMul
      : a.speed * (1 - a.mix) * dt;
    a.xFrac += a.dir * go;
    // Za okrajem tvor obejde scenu dokola, misto aby se odrazil. Odraz vypadal
    // prirozene, ale vsichni se odrazeji od tehoz mista a casem se sesypou do
    // jednoho hloucku; takhle si rozestupy drzi napovad, protoze kazdy chodi
    // jinak rychle.
    if (a.xFrac > 1.25) { a.xFrac = -0.25; swapBand(a); }
    if (a.xFrac < -0.25) { a.xFrac = 1.25; swapBand(a); }
    if (a.motion === 'fly') {
      a.yFrac += Math.sin(sceneTime * 0.35 + a.bob) * 0.012 * dt;
      a.yFrac = Math.max(a.band.y0, Math.min(a.band.y1, a.yFrac));
    } else if (a.motion === 'walk') {
      // Sunuti po pasu brehu: na kraji se odrazi, protoze za nim uz je voda
      // nebo les. Svisle se posouva pomerem `drift` k vodorovne rychlosti.
      a.yFrac += go * a.drift;
      if (a.yFrac < a.band.y0 || a.yFrac > a.band.y1) {
        a.yFrac = Math.max(a.band.y0, Math.min(a.band.y1, a.yFrac));
        a.drift = -a.drift;
      }
    }
  }
}

let fatal = false;

function note(msg) {
  if (fatal) return;
  errEl.textContent = msg;
  clearTimeout(note._t);
  // bezna stiznost nema na televizi svitit navzdy; fatalni z die() zustava
  note._t = setTimeout(() => { if (!fatal) errEl.textContent = ''; }, 15000);
}

function die(msg) {
  // fatalni hlaska uz se necha prepsat: jinak ji prekryje prvni nasledna
  // stiznost, ktera z ni jenom vyplyva
  fatal = true;
  errEl.classList.add('fatal');
  errEl.textContent = msg;
}

function draw(dt) {
  if (window.Backdrop) Backdrop.draw(ctx, W, H, sceneTime);
  else { ctx.fillStyle = '#123'; ctx.fillRect(0, 0, W, H); }

  const order = actors.slice().sort((a, b) => a.yFrac - b.yFrac);
  for (const a of order) {
    const scale = depthScale(a.yFrac);
    const targetPx = W * (LENGTH_FRACTION[a.motion] || 0.17) * scale;
    const age = sceneTime - a.born;
    const pop = age < 0.9 ? 0.72 + 0.28 * Math.min(1, age / 0.9) : 1;
    const x = a.xFrac * W, y = a.yFrac * H;

    if (a.m3) {
      // u 3D tvora je yFrac primo cara, na ktere stoji nohama
      const s = W * (SIZE_FRACTION[a.motion] || SIZE_FRACTION.walk) * scale / a.m3.sizePx;
      Scene3D.place(a.m3, { x, y, face: a.face, scale: s * pop,
                            depth: a.yFrac * 4000 - 2000 });
      continue;
    }

    const pxPerMm = targetPx / bodyLengthMm(a.rig);
    ctx.save();
    ctx.globalAlpha = Math.min(1, age / 0.4);
    try {
      a.rig.draw(ctx, { x, y, scale: pxPerMm * pop, flip: a.face < 0,
                        t: sceneTime, phase: a.phase, speed: a.pace * a.rate,
                        rest: a.mix > 0.5 });
    } catch (e) {
      note('render: ' + e.message);
    }
    ctx.restore();
  }

  Scene3D.render(dt);

  fxCtx.clearRect(0, 0, W, H);
  if (window.Backdrop && Backdrop.drawFront) Backdrop.drawFront(fxCtx, W, H, sceneTime);
}

let frameErrors = 0;

function frame(now) {
  // preplanovat driv, nez muze cokoli spadnout — jedna vyjimka nesmi scenu
  // na televizi zastavit navzdy
  requestAnimationFrame(frame);
  try {
    const dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1000) : 0;
    lastFrame = now;
    sceneTime += dt;
    update(dt);
    draw(dt);
    frameErrors = 0;
  } catch (e) {
    note('snímek: ' + (e && e.message || e));
    // opakovana chyba v kazdem snimku se sama nespravi; reload je posledni pomoc
    if (++frameErrors >= 30) location.reload();
  }
}

function toast(text) {
  toastEl.textContent = text;
  toastEl.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toastEl.classList.remove('show'), 4200);
}

async function loadRig(item, opts) {
  if (!window.Rig) throw new Error('rigrender.js není načtený');
  const rig = await Rig.load(item.url || '/catch/' + item.id + '/');
  return addActor({ rig, id: item.id, key: rig.creature || 'rig',
                    motion: rig.motion, label: rig.label }, opts);
}

async function loadModel(item, opts) {
  const spec = byKey.get(item.creature);
  if (!spec) throw new Error('neznámý model: ' + item.creature);
  if (!has3D) throw new Error('WebGL není k dispozici');
  const clip = spec.clips[spec.motion === 'fly' ? 'Flying' : 'Walk'] || spec.pose;
  const m3 = await Scene3D.spawn({
    id: item.id, glb: spec.glb, motion: spec.motion, clip,
    // do ceho prolnout, kdyz se chodec zastavi; letec zadnou nedostane
    breaks: spec.motion === 'walk' ? { stand: spec.clips.Idle, jump: spec.clips.Jump }
                                   : undefined,
    texture: item.texture || (item.url || `/catch/${item.id}/`) + 'texture.png',
  });
  return addActor({ m3, id: item.id, key: spec.key,
                    motion: spec.motion, label: spec.label }, opts);
}

function arrive(item, opts) {
  return item.kind === 'model' ? loadModel(item, opts) : loadRig(item, opts);
}

async function catalogue() {
  try {
    const list = await (await fetch('/api/dino3d')).json();
    for (const e of list) byKey.set(e.key, e);
  } catch (e) {
    note('katalog: ' + e.message);
  }
}

async function fetchCast() {
  const res = await fetch('/api/rigs');
  if (!res.ok) return null;
  const data = await res.json();
  // server zatim limit neumi; po tydnech provozu by scena bootovala minuty
  // a drzela vsechny textury, tak se bere jen cerstvy konec seznamu
  return (data.rigs || data).slice(-MAX_ACTORS);
}

async function restoreCast() {
  try {
    const items = await fetchCast();
    for (const item of (items || [])) {
      try {
        await arrive(item, { silent: true, who: item.name });
      } catch (e) {
        note('úlovek: ' + e.message);
      }
    }
  } catch (e) {
    /* scéna se dá ladit i bez běžícího serveru */
  }
}

/* Události z výpadku WS jsou ztracené, tak se po (re)connectu stav srovná se
   serverem podle id: chybějící úlovky se přivedou, úlovky, které server už
   nezná, odejdou. Katalogových (ambientních) tvorů se rekonciliace netýká. */
async function reconcile() {
  let items;
  try {
    items = await fetchCast();
  } catch (e) {
    return;
  }
  if (!items) return;
  const known = new Set(items.map(i => i.id));
  for (let i = actors.length - 1; i >= 0; i--) {
    if (!actors[i].ambient && !known.has(actors[i].id)) dropActor(i);
  }
  for (const item of items) {
    if (actors.some(a => a.id === item.id)) continue;
    try {
      await arrive(item, { silent: true, who: item.name });
      makeRoom();
    } catch (e) {
      note('úlovek: ' + e.message);
    }
  }
  topUp();
}

let wsDelay = 3000;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(proto + '://' + location.host + '/ws');
  let ping = 0;
  ws.onopen = () => {
    wsDelay = 3000;
    // Keepalive: server na ping neodpovida, takze watchdog na prijate zpravy
    // by zabijel zdrava, jen ticha spojeni. Pravidelny send ale drzi NAT pri
    // zivote a na mrtvem TCP spojeni se neodeslana data nahromadi, az OS
    // socket zavre — onclose pak spusti reconnect a rekonciliaci.
    ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, 25000);
    reconcile();
  };
  ws.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === 'add') {
      try {
        const a = await arrive(msg, { who: msg.name });
        if (a) {
          makeRoom();
          toast(msg.name ? msg.name + ' přivádí: ' + a.label + '!'
                         : 'Nový ' + a.label + ' dorazil!');
        }
      } catch (e) {
        note('add: ' + e.message);
      }
    } else if (msg.type === 'remove') {
      for (let i = actors.length - 1; i >= 0; i--) {
        if (actors[i].id === msg.id) dropActor(i);
      }
      topUp();
    }
  };
  ws.onclose = () => {
    clearInterval(ping);
    setTimeout(connect, wsDelay);
    wsDelay = Math.min(30000, wsDelay * 2);
  };
  ws.onerror = () => ws.close();
}

/* Ladici panel: co ukazat u kazdeho druhu, ktery je prave ve scene. Rychlost je
   v pixelech za sekundu, at se da porovnat s tim, co je videt. */
Tune.init({
  apply: () => actors.forEach(applyGait),
  read: () => {
    const rows = new Map();
    for (const a of actors) {
      let r = rows.get(a.key);
      if (!r) rows.set(a.key, r = { key: a.key, label: a.label, count: 0,
                                    autoRate: 0, rate: 0, px: 0, cycle: 0,
                                    autoSpeed: (BAKED[a.key] || {}).speed || 1,
                                    stride: a.m3 ? a.m3.strideBodies : 0 });
      r.count++;
      r.autoRate += (BAKED[a.key] || {}).rate || a.autoRate;
      r.rate += a.rate;
      r.px += a.speed * W;
      r.cycle += a.m3 && a.m3.duration ? a.m3.duration / a.rate : 0;
    }
    // vic jedincu tehoz druhu se lisi hloubkou i nahodou, tak prumer
    return [...rows.values()].map(r => ({
      ...r, autoRate: r.autoRate / r.count, rate: r.rate / r.count,
      px: r.px / r.count, cycle: r.cycle / r.count,
    }));
  },
});

document.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (e.target.tagName === 'INPUT') return;      // v panelu se pise
  if (k === 'd') Tune.toggle();
  if (k === 'i') Roster.toggle();
  if (k === 'f') {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  }
  if (k === 'h') hintEl.style.opacity = hintEl.style.opacity === '0' ? '1' : '0';
});

window.DinoScene = {
  actors,
  add: arrive,                 // rucni pridani tvora, pro tools/shot_scene.py
  drop: (id) => {              // rucni odebrani, zrcadli WS remove (pro testy)
    for (let i = actors.length - 1; i >= 0; i--) if (actors[i].id === id) dropActor(i);
  },
  gpu: () => Scene3D.info(),
  where: () => actors.map(a => ({
    label: a.label, key: a.key, motion: a.motion,
    band: a.band.name, lane: a.band.lane || null,
    kind: a.m3 ? 'model' : 'rig', ambient: a.ambient,
    x: +a.xFrac.toFixed(3), y: +a.yFrac.toFixed(3), dir: a.dir,
    // tempo za plne chuze (bez zastavek), at se da merit bez sahani do kosti
    speedPx: +(a.speed * W).toFixed(1),
    bodiesPerS: a.natural ? +(a.natural * a.rate * a.speedMul).toFixed(4) : null,
    cycle: a.m3 && a.m3.duration ? +(a.m3.duration / a.rate).toFixed(3) : null,
  })),
};

const qr = document.getElementById('qr');
qr.src = '/api/qr';
qr.onerror = () => { hintEl.style.display = 'none'; };

Roster.init();
Scene3D.onNote(note);
const glError = Scene3D.init(gl);
has3D = !glError;
if (glError) {
  die('Tenhle prohlížeč neumí WebGL, takže scéna zůstane prázdná. '
      + 'Zkus zapnout hardwarovou akceleraci (v Chrome chrome://gpu).');
  console.error('WebGL:', glError);
}
resize();
catalogue().then(restoreCast).then(topUp).then(() => { window.__ready = true; });
connect();
requestAnimationFrame(frame);
