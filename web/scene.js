/* The living scene: keeps the cast, moves them through their habitats and
   listens for new arrivals. Drawing the landscape is backdrop's job, posing a
   3D creature is scene3d's; this file only decides who is where.

   Tvor postaveny z hotoveho 3D modelu se kresli do WebGL vrstvy nad krajinou,
   stary ohybany 2D rig primo do platna s krajinou. Scena s obema pracuje
   stejne — lisi se az posledni krok, vykresleni. */

import * as Scene3D from './scene3d.js';
import * as Tune from './tune.js';
import * as Roster from './roster.js';

/* Session (bod 6): TV bez `?s=` je domaci default "tv" — dnesni chovani jedne
   televize. `?s=<id>` oddeli druhou obrazovku: vlastni QR, vlastni ulovky,
   vlastni broadcast. Neznamou session si server tise zalozi. */
const SID = new URLSearchParams(location.search).get('s') || 'tv';
const SIDQ = 's=' + encodeURIComponent(SID);

const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d', { alpha: false });
const fx = document.getElementById('stagefx');
const fxCtx = fx.getContext('2d');
const gl = document.getElementById('stage3d');
const toastEl = document.getElementById('toast');
const errEl = document.getElementById('err');
const hintEl = document.getElementById('hint');

const MAX_ACTORS = 18;
// Jen pojistka proti grotesknimu tempu animace; cil urcuje strideRate
// z katalogu (per druh) nebo z definice sceny (default per motion).
const GAIT_RATE = { min: 0.4, max: 1.8 };
// Jak dlouho trvaji prechody scen: odchod tvora (zmenseni do ztracena)
// a prolnuti krajin.
const LEAVE_S = 0.8;
const XFADE_S = 1.6;
// Odchod se odehrava (bod 11): tvor dojde/doleti/dopluje za okraj vlastnim
// tempem; kdyz se EXIT_TIMEOUT_S nehne z mista (bug, zasek), spadne na
// stary fade. TAG_S je jmenovka nad novym ulovkem.
const EXIT_TIMEOUT_S = 20;
const TAG_S = 6;
// Krmeni z mobilu (bod 11): jidlo pada FEED_FALL_S, pak lezi FEED_LIFE_S;
// chodce lakas do vzdalenosti FEED_RADIUS, u jidla je od FEED_REACH.
const FEED_FALL_S = 1.0;
const FEED_LIFE_S = 15;
const FEED_RADIUS = 0.3;
const FEED_REACH = 0.04;

/* Scena jako data (bod 8): vsechno, co je vlastnost krajiny — pasy, chovani
   pohybu, osvetleni, backdrop — zije v definici web/scenes/<key>.js. scene.js
   je jeden genericky stroj nad aktivni definici. Vyber sceny: `?scene=` v URL
   prebiji, jinak plati hodnota session ze serveru; zpravou `scene` z WS se
   prepina za behu. */
const SCENE_OVERRIDE = new URLSearchParams(location.search).get('scene') || '';
const DEFAULT_SCENE = 'cretaceous';
let sceneDef = null;      // aktivni definice sceny
let backdrop = null;      // instance kreslice krajiny {draw, drawFront, ...}
let xfade = null;         // { old, t, buf } — prolnuti stare krajiny do nove
let switching = false;    // behem prepnuti se nedoplnuje ani neobnovuje

function motionCfg(motion) {
  const m = (sceneDef && sceneDef.motions) || {};
  return m[motion] || m.walk || {};
}

const actors = [];
const byKey = new Map();
let ambientQueue = [];
let ambientSeq = 0;
let spawnSeq = 0;
let has3D = false;
let dpr = 1, W = 0, H = 0, lastFrame = 0, sceneTime = 0;
// Prazdna vs ukazkova krajina (bod c) — pri vypnutem se ambientni tvorove
// nemazou, jen se prestanou doplnovat; init hodnota se nacte z /api/scene/settings.
let ambientEnabled = true;

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
}
window.addEventListener('resize', resize);

/* Pasy aktivni sceny, ktere umi dany pohyb. Chodec nikdy nespadne do vody,
   protoze zadny walk pas ji neobsahuje. Kdyz scena pro pohyb zadny pas nema
   (definice se nenacetla), plati nouzovy pas uprostred, at nic nespadne. */
function bandsFor(motion) {
  const all = (sceneDef && sceneDef.bands) || [];
  const fit = all.filter(b => (b.motions || []).includes(motion));
  return fit.length ? fit
                    : [{ name: 'nouze', y0: 0.55, y1: 0.85, motions: [motion] }];
}

/* Novy tvor padne s sanci farChance na nekterou vedlejsi lane (vzdaleny breh),
   at ma scena hloubku; jinak jde hlavni (blizkou) lane. */
function pickBand(motion) {
  const fit = bandsFor(motion);
  if (fit.length === 1) return fit[0];
  const near = fit.find(b => b.lane !== 'far') || fit[0];
  const rest = fit.filter(b => b !== near);
  return Math.random() < (motionCfg(motion).farChance || 0)
    ? rest[Math.floor(Math.random() * rest.length)] : near;
}

/* Svisly drift se skaluje vyskou pasu: v uzkem vzdalenem brehu by tvor s plnym
   driftem kmital mezi okraji kazde ~4 s. Reference je vyska predniho brehu. */
function driftFor(band, motion) {
  const cfg = motionCfg(motion);
  if (!cfg.drift) return 0;
  return (Math.random() * 2 - 1) * cfg.drift
       * Math.min(1, (band.y1 - band.y0) / (cfg.driftRefHeight || 0.15));
}

function depthScale(yFrac) {
  if (backdrop && backdrop.depthScale) return backdrop.depthScale(yFrac);
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

/* Trasy (bod 9): tvor s trasou jde po lomené čáře z definice scény (případně
   přepsané editorem v ladicím panelu, viz Tune.pathsFor). Souřadnice bodů
   jsou podíly obrazovky; vzdálenost po čáře se měří izotropně (y škálované
   poměrem stran), aby svislý kus úsečky nebyl "zadarmo". Trasa je autorita
   nad pásy: autor ji kreslí po břehu, scéna ji tvrdě neclampuje. */
const ROUTE_CHANCE = 0.5;   // jen část chodců, ať scéna není vláček po lince

function aspect() {
  return W ? H / W : 0.5625;
}

function segCount(path) {
  return path.loop ? path.points.length : path.points.length - 1;
}

function segAt(path, seg) {
  const pts = path.points;
  return [pts[seg % pts.length], pts[(seg + 1) % pts.length]];
}

function segLen(path, seg) {
  const [p0, p1] = segAt(path, seg);
  return Math.hypot(p1.x - p0.x, (p1.y - p0.y) * aspect()) || 1e-6;
}

/* Nejbližší místo na trase k dané pozici — nový tvor se na trasu zavěsí tam,
   kde zrovna je (příchozí od okraje na její ocas za okrajem, doplněk
   z katalogu kdekoli po délce), takže se všichni nesesypou na start. */
function snapRoute(path, x, y) {
  const k = aspect();
  let best = { seg: 0, s: 0, d: Infinity };
  for (let i = 0; i < segCount(path); i++) {
    const [p0, p1] = segAt(path, i);
    const dx = p1.x - p0.x, dy = (p1.y - p0.y) * k;
    const len2 = dx * dx + dy * dy || 1e-9;
    const s = Math.max(0, Math.min(1, ((x - p0.x) * dx + (y - p0.y) * k * dy) / len2));
    const d = Math.hypot(x - p0.x - s * dx, (y - p0.y) * k - s * dy);
    if (d < best.d) best = { seg: i, s, d };
  }
  return best;
}

function routePos(a) {
  const [p0, p1] = segAt(a.route.path, a.route.seg);
  a.xFrac = p0.x + (p1.x - p0.x) * a.route.s;
  a.yFrac = p0.y + (p1.y - p0.y) * a.route.s;
  const dx = (p1.x - p0.x) * a.route.dir;
  if (dx) a.dir = dx > 0 ? 1 : -1;   // svislý úsek směr pohledu nemění
}

/* Posun po trase o `go` (podíl šířky obrazovky, z fázově vázaného `walked`).
   Na dosaženém waypointu se vykoná jeho `do`: stop zapne stávající rest
   mašinerii s dwell intervalem, turn obrátí směr průchodu; konec trasy
   znamená u loop pokračovat dokola, jinak ping-pong. */
function followRoute(a, go) {
  const r = a.route, pts = r.path.points;
  const n = segCount(r.path);
  if (n < 1) return;
  if (r.seg >= n) { r.seg = n - 1; r.s = 1; }   // editor mohl body smazat
  let left = go;
  let guard = pts.length * 2 + 4;   // dva turn body vedle sebe nesmí zacyklit
  while (left > 0 && guard-- > 0) {
    const len = segLen(r.path, r.seg);
    const room = (r.dir > 0 ? 1 - r.s : r.s) * len;
    if (left < room) { r.s += r.dir * left / len; break; }
    left -= room;
    const at = r.dir > 0 ? (r.seg + 1) % pts.length : r.seg;   // dosažený bod
    const pt = pts[at] || {};
    if (pt.do === 'turn') {
      // zůstává na témže segmentu, jen jím jde zpátky
      r.s = r.dir > 0 ? 1 : 0;
      r.dir = -r.dir;
    } else if (r.dir > 0) {
      if (r.seg + 1 < n) { r.seg += 1; r.s = 0; }
      else if (r.path.loop) { r.seg = 0; r.s = 0; }
      else { r.dir = -1; r.s = 1; }
    } else {
      if (r.seg > 0) { r.seg -= 1; r.s = 1; }
      else if (r.path.loop) { r.seg = n - 1; r.s = 1; }
      else { r.dir = 1; r.s = 0; }
    }
    if (pt.do === 'stop' && !a.pause) {
      const R = motionCfg(a.motion).rest;
      if (R && (!a.m3 || a.m3.action)) {
        a.pause = 'stand';
        a.fade = R.fade;
        a.restUntil = sceneTime + span(pt.dwell || R.stand);
        break;   // zbytek kroku propadne, tvor zastavuje
      }
    }
  }
}

/* Přiřazení trasy při příchodu: jen chodci, jen když scéna trasu pro jeho
   druh má, a i pak jen s šancí ROUTE_CHANCE — zbytek bloumá postaru po
   pásech, ať má scéna obojí. */
function pickRoute(a) {
  if (a.motion !== 'walk' || !sceneDef || Math.random() >= ROUTE_CHANCE) return null;
  const fit = Tune.pathsFor(sceneDef).filter(p =>
    (!p.species || p.species === a.key) && p.points.length >= 2);
  if (!fit.length) return null;
  const path = fit[Math.floor(Math.random() * fit.length)];
  const { seg, s } = snapRoute(path, a.xFrac, a.yFrac);
  const [p0, p1] = segAt(path, seg);
  // po trase se vydá směrem, kterým už byl otočený, pokud to segment dovolí
  const dir = (p1.x - p0.x) * a.dir >= 0 ? 1 : -1;
  return { path, seg, s, dir };
}

function addActor(what, opts) {
  // dedup podle id: race pri startu (connect bezi soubezne s restoreCast) nebo
  // rekonciliace po reconnectu nesmi privest tehoz tvora dvakrat
  if (what.id && actors.some(a => a.id === what.id)) {
    if (what.m3) Scene3D.remove(what.m3);    // uz nacteny klon nesmi leaknout
    return null;
  }
  const motion = what.motion || 'walk';
  const cfg = motionCfg(motion);
  const band = pickBand(motion);
  const yFrac = band.y0 + Math.random() * (band.y1 - band.y0);
  // Novy ulovek (ne-silent) ma ohlaseny vstup: vzdy zleva, at dite vi, kam
  // koukat (teamLab vzor) — mobil po uploadu rika „sleduj levy kraj".
  const silent = !!(opts && opts.silent);
  const dir = silent ? (Math.random() < 0.5 ? 1 : -1) : 1;
  // rychlost i tempo cyklu maji jednu spolecnou nahodu, aby rychlejsi tvor
  // zaroven casteji maval kridly nebo vesloval
  const pace = 0.75 + Math.random() * 0.5;
  const actor = {
    ...what, motion, yFrac, dir, band, pace,
    // Tvory, kteri uz ve sceně "byli" (obnovene ulovky, doplnek z katalogu),
    // rozsazuje zlaty rez, ne nahoda: nahodnych sest cisel se casto sesype do
    // jednoho rohu a pul obrazovky zustane prazdna.
    xFrac: silent ? (spawnSeq++ * 0.6180339887 + 0.1) % 1 : -0.15,
    phase: Math.random(),
    speed: (cfg.baseSpeed || 0.03) * pace,
    bob: Math.random() * Math.PI * 2,
    // prvni zastavka az za chvili, at scena po nacteni nezacne stat;
    // pohyb bez `rest` v definici sceny nezastavuje nikdy
    restAt: cfg.rest ? sceneTime + span(cfg.rest.walk) : Infinity,
    restUntil: 0,
    pause: '',
    shown: '',
    fade: cfg.rest ? cfg.rest.fade : 0.7,
    mix: 0,
    face: dir,
    drift: driftFor(band, motion),
    born: sceneTime,
    label: what.label || 'tvor',
    who: (opts && opts.who) || '',
    ambient: !!(opts && opts.ambient),
    // jmenovka nad novym ulovkem: jen kdyz fotka nese jmeno a vstup se ohlasuje
    tagUntil: !silent && opts && opts.who ? sceneTime + TAG_S : 0,
  };
  actor.autoRate = 1;
  actor.autoSpeed = actor.speed;
  if (actor.m3 && actor.m3.strideBodies) {
    // Chodec: tempo cyklu se vybere kolem prirozeneho tempa druhu a rychlost po
    // scene se z nej dopocita, ne naopak — chodidla tak zustanou na zemi.
    // Cilove tempo (tel/s) je vlastnost druhu (katalog), default dava scena.
    actor.natural = actor.m3.strideBodies / actor.m3.duration;   // delek tela/s
    const [lo, hi] = actor.strideRate || cfg.strideRate || [0.12, 0.22];
    const want = lo + Math.random() * (hi - lo);
    actor.autoRate = Math.max(GAIT_RATE.min, Math.min(GAIT_RATE.max, want / actor.natural))
                   * (0.94 + 0.12 * Math.random());
    actor.autoSpeed = actor.natural * actor.autoRate * bodyFrac(actor);
  } else if (actor.m3) {
    actor.autoRate = pace;         // letec: rychleji maka kridly, rychleji leti
  }
  actor.route = pickRoute(actor);
  if (actor.route) {
    routePos(actor);
    actor.face = actor.dir;
    actor.drift = 0;
    actor.restAt = Infinity;   // zastávky určují waypointy, ne náhoda
  }
  applyGait(actor);
  actors.push(actor);
  while (liveCount() > MAX_ACTORS) {
    // nejdriv odejde doplnek z katalogu, teprve pak nejstarsi ulovek —
    // odchod se odehrava (beginExit), zdroje drzi az do dropActor
    const victim = actors.find(a => a.ambient && !a.exiting && !a.leaving)
                || actors.find(a => !a.exiting && !a.leaving);
    if (!victim || victim === actor) break;
    beginExit(victim);
  }
  while (actors.length > MAX_ACTORS + 6) {
    // tvrdy strop na drzene zdroje: nahromadene odchazejici zmizi hned
    const i = actors.findIndex(a => a.exiting || a.leaving);
    dropActor(i >= 0 ? i : 0);
  }
  Roster.event('in', actor.label, actor.who);
  Roster.cast(actors);
  return actor;
}

/* Obsazeni sceny bez odchazejicich: odchazejici tvor uz se nepocita, aby
   topUp/makeRoom necekaly, az dojde k okraji (Scene3D zdroje ale drzi
   az do dropActor). */
function liveCount() {
  let n = 0;
  for (const a of actors) if (!a.exiting && !a.leaving) n++;
  return n;
}

/* Odchod vzdy odehrat (bod 11): tvor opusti trasu, otoci se k blizsimu okraji
   a odejde/odleti/odpluje za nej vlastnim tempem; dropActor az za okrajem.
   Zachranna brzda: kdyz se do EXIT_TIMEOUT_S nedostane ven, fade jako drive. */
function beginExit(a, quiet) {
  if (!a || a.exiting || a.leaving) return;
  a.exiting = true;
  a.exitWatch = { x: a.xFrac, at: sceneTime };   // hlidac „nehybe se"
  a.quietOut = !!quiet;
  a.route = null;
  a.feed = null;
  a.pause = '';
  a.restUntil = 0;
  a.restAt = Infinity;
  a.drift = 0;
  a.dir = a.xFrac >= 0.5 ? 1 : -1;
}

/* Podil sirky obrazovky, ktery zabere telo tvora — z nej se pocita rychlost po
   scene, aby vzdaleny tvor slapal stejne a jen se posouval pomaleji. */
function bodyFrac(a) {
  const cfg = motionCfg(a.motion);
  return (cfg.sizeFraction || motionCfg('walk').sizeFraction || 0.234)
       * depthScale(a.yFrac) * a.m3.length / a.m3.sizePx;
}

/* Tempo cyklu a rychlost po scene. Obojí se dá přeladit v ladicím panelu
   (klávesa d): `rate` je tempo animace, `speed` násobek dopočítané rychlosti.
   Když se mění jen tempo, rychlost jde s ním, aby chodidla zůstala na zemi. */
function applyGait(a) {
  const t = Tune.of(a.key);
  a.rate = t.rate || a.autoRate;
  a.speedMul = t.speed || 1;
  a.speed = a.autoSpeed * (a.rate / a.autoRate) * a.speedMul;
}

function dropActor(i) {
  const [gone] = actors.splice(i, 1);
  if (!gone) return;
  if (gone.m3) Scene3D.remove(gone.m3);
  // `−` v liste az pri skutecnem zmizeni; hromadny reset ma jeden souhrnny
  // zaznam misto N jednotlivych (quietOut)
  if (!gone.quietOut) Roster.event('out', gone.label, gone.who);
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
  // dve soubezna volani by prelila ambientMin; behem prepnuti sceny se ceka
  if (topping || switching || !has3D || !byKey.size || !ambientEnabled) return;
  topping = true;
  try {
    while (liveCount() < ((sceneDef && sceneDef.ambientMin) || 0)) {
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
  if (liveCount() <= ((sceneDef && sceneDef.ambientMin) || 0)) return;
  beginExit(actors.find(a => a.ambient && !a.exiting && !a.leaving));
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
  a.drift = driftFor(a.band, a.motion);
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
  // Zastavovat se umi jen pohyb, ktery ma v definici sceny `rest` (a 3D tvor
  // k tomu pozu, do ktere jde prolnout) — letec by spadl.
  const R = motionCfg(a.motion).rest;
  const can = R && (!a.m3 || a.m3.action);
  if (can && !a.pause && sceneTime > a.restAt) {
    const jump = a.m3 && a.m3.breakDur.jump && Math.random() < R.jump;
    a.pause = jump ? 'jump' : 'stand';
    a.fade = jump ? R.jumpFade : R.fade;
    a.restUntil = sceneTime + (jump ? a.m3.breakDur.jump : span(R.stand));
    if (jump) Scene3D.restart(a.m3, 'jump');
  }
  if (R && a.pause && sceneTime > a.restUntil) {
    // na trase o otočkách i dalších zastávkách rozhodují waypointy, ne náhoda
    if (!a.route && a.pause === 'stand' && Math.random() < R.turn) a.dir = -a.dir;
    a.pause = '';
    a.restAt = a.route ? Infinity : sceneTime + span(R.walk);
  }

  // Prolinana poza se drzi, dokud se nedomixuje: kdyby se prepnula hned, jak
  // skok skonci, skacici tvor by cuknul do stojaci pozy.
  if (!a.mix) a.shown = a.pause;
  a.face = toward(a.face, a.dir, dt / ((R && R.spin) || 0.5));
  const target = a.pause || a.face !== a.dir ? 1 : 0;
  a.mix = toward(a.mix, target, dt / a.fade);
  if (a.m3) {
    Scene3D.speed(a.m3, a.rate * (1 - a.mix));
    Scene3D.blend(a.m3, a.shown || 'stand', a.mix);
  }
}

function update(dt) {
  // odchazejici tvorove: fade (prepnuti sceny / zachranna brzda) zmizi po
  // doztraceni, odehrany odchod az za okrajem obrazovky
  for (let i = actors.length - 1; i >= 0; i--) {
    const a = actors[i];
    if (a.leaving && sceneTime - a.leaving > LEAVE_S) { dropActor(i); continue; }
    if (a.exiting && !a.leaving) {
      if (a.xFrac > 1.3 || a.xFrac < -0.3) {
        dropActor(i);
        topUp();
      } else if (Math.abs(a.xFrac - a.exitWatch.x) > 0.02) {
        a.exitWatch = { x: a.xFrac, at: sceneTime };
      } else if (sceneTime - a.exitWatch.at > EXIT_TIMEOUT_S) {
        a.leaving = sceneTime;   // zasek (bug, stop) → fade jako drive
      }
    }
  }
  updateFoods();
  for (const a of actors) {
    // krmeni: chodec bez trasy v okruhu k jidlu zamiri; u jidla postoji
    // (stavajici rest maserie) a pak se vrati k driftu
    if (a.feed) {
      if (a.feed.gone) {
        a.feed = null;
      } else if (Math.abs(a.xFrac - a.feed.x) < FEED_REACH) {
        const R = motionCfg(a.motion).rest;
        if (R && (!a.m3 || a.m3.action) && !a.pause) {
          a.pause = 'stand';
          a.fade = R.fade;
          a.restUntil = sceneTime + span(R.stand);
          a.restAt = sceneTime + span(R.walk);
        }
        a.feed = null;
      } else {
        a.dir = a.feed.x > a.xFrac ? 1 : -1;
      }
    }
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
    if (a.route && a.route.path.points.length >= 2) {
      // Trasa je autorita: zadne obchazeni okraje ani swapBand — odchod a
      // navrat resi body za okrajem, ktere si autor nakreslil sam.
      followRoute(a, go);
      routePos(a);
      continue;
    }
    a.xFrac += a.dir * go;
    // Za okrajem tvor obejde scenu dokola, misto aby se odrazil. Odraz vypadal
    // prirozene, ale vsichni se odrazeji od tehoz mista a casem se sesypou do
    // jednoho hloucku; takhle si rozestupy drzi napovad, protoze kazdy chodi
    // jinak rychle. Odchazejici tvor se neotaci ani neteleportuje — jde ven.
    if (!a.exiting) {
      if (a.xFrac > 1.25) { a.xFrac = -0.25; swapBand(a); }
      if (a.xFrac < -0.25) { a.xFrac = 1.25; swapBand(a); }
    }
    const cfg = motionCfg(a.motion);
    if (cfg.bob) {
      a.yFrac += Math.sin(sceneTime * 0.35 + a.bob) * 0.012 * dt;
      a.yFrac = Math.max(a.band.y0, Math.min(a.band.y1, a.yFrac));
    } else if (a.drift) {
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

/* Krmeni z mobilu (bod 11): zprava `feed` shodi na predni breh trs kapradi.
   Pada FEED_FALL_S, po dopadu si ho vsimnou chodci bez trasy v okruhu
   FEED_RADIUS (tvor na trase drzi rad sceny a ignoruje ho), po FEED_LIFE_S
   se doztraci a vsichni se vrati k driftu. Letci/plavci nereaguji. */
const foods = [];

function dropFood(x) {
  const fit = bandsFor('walk');
  const band = fit.find(b => b.lane !== 'far') || fit[0];
  foods.push({
    x: Math.max(0.05, Math.min(0.95, x)),
    y: band.y0 + (0.3 + Math.random() * 0.4) * (band.y1 - band.y0),
    born: sceneTime, claimed: false, gone: false,
  });
}

function updateFoods() {
  for (let i = foods.length - 1; i >= 0; i--) {
    const f = foods[i];
    const age = sceneTime - f.born;
    if (!f.claimed && age >= FEED_FALL_S) {
      f.claimed = true;      // laka az po dopadu, ne behem letu vzduchem
      for (const a of actors) {
        if (a.motion !== 'walk' || a.route || a.exiting || a.leaving) continue;
        if (Math.abs(a.xFrac - f.x) < FEED_RADIUS) a.feed = f;
      }
    }
    if (age > FEED_FALL_S + FEED_LIFE_S) {
      f.gone = true;
      foods.splice(i, 1);
    }
  }
}

/* Trs kapradi kresleny primo do fx vrstvy — zadny asset. */
function drawFern(c, x, y, s, alpha) {
  c.save();
  c.globalAlpha = alpha;
  c.translate(x, y);
  c.lineCap = 'round';
  c.fillStyle = 'rgba(24, 20, 10, 0.28)';
  c.beginPath();
  c.ellipse(0, s * 0.05, s * 0.55, s * 0.13, 0, 0, Math.PI * 2);
  c.fill();
  for (let i = -2; i <= 2; i++) {
    const ang = -Math.PI / 2 + i * 0.38;
    const len = s * (1 - Math.abs(i) * 0.14);
    const ex = Math.cos(ang) * len, ey = Math.sin(ang) * len;
    c.strokeStyle = '#2f7a3d';
    c.lineWidth = Math.max(1.5, s * 0.07);
    c.beginPath();
    c.moveTo(0, 0);
    c.quadraticCurveTo(ex * 0.4, ey * 0.75, ex, ey);
    c.stroke();
    c.strokeStyle = '#48a75c';
    c.lineWidth = Math.max(1, s * 0.05);
    for (let k = 1; k <= 4; k++) {
      const px = ex * k / 5, py = ey * k / 5 * 0.9;
      const ll = s * 0.22 * (1 - k / 6);
      c.beginPath();
      c.moveTo(px, py);
      c.lineTo(px - ll, py - ll * 0.35);
      c.moveTo(px, py);
      c.lineTo(px + ll, py - ll * 0.35);
      c.stroke();
    }
  }
  c.restore();
}

function drawFoods() {
  for (const f of foods) {
    const age = sceneTime - f.born;
    const t = Math.min(1, age / FEED_FALL_S);
    const y = (f.y - 0.4 * (1 - t * t)) * H;       // pad shora se zrychlenim
    const fade = Math.min(1, (FEED_FALL_S + FEED_LIFE_S - age) / 2);
    drawFern(fxCtx, f.x * W, y, W * 0.035 * depthScale(f.y), Math.max(0, fade));
  }
}

/* Jmenovka nad novym ulovkem (bod 11): poloprupustna tmava pilulka s bilym
   jmenem z fotky, sleduje tvora ~TAG_S sekund, pismo skalovane s hloubkou. */
function drawTags() {
  for (const a of actors) {
    if (!a.tagUntil || sceneTime >= a.tagUntil || !a.who || a.leaving) continue;
    const scale = depthScale(a.yFrac);
    const cfg = motionCfg(a.motion);
    let top;
    if (a.m3) {
      const s = W * (cfg.sizeFraction || motionCfg('walk').sizeFraction || 0.234)
              * scale / a.m3.sizePx;
      top = a.yFrac * H - a.m3.height * s;
    } else {
      top = a.yFrac * H - W * (cfg.lengthFraction || 0.17) * scale * 0.75;
    }
    const alpha = Math.max(0, Math.min(1, (a.tagUntil - sceneTime) / 0.5,
                                       (sceneTime - a.born) / 0.5));
    const fs = Math.max(12, Math.round(17 * scale));
    const x = a.xFrac * W;
    const cy = Math.max(fs, top - fs * 1.2);
    fxCtx.save();
    fxCtx.globalAlpha = alpha * 0.9;
    fxCtx.font = `600 ${fs}px "Segoe UI", system-ui, sans-serif`;
    fxCtx.textAlign = 'center';
    fxCtx.textBaseline = 'middle';
    const w = fxCtx.measureText(a.who).width;
    const padX = fs * 0.7, padY = fs * 0.42;
    fxCtx.fillStyle = 'rgba(8, 22, 30, 0.6)';
    fxCtx.beginPath();
    if (fxCtx.roundRect) {
      fxCtx.roundRect(x - w / 2 - padX, cy - fs / 2 - padY,
                      w + 2 * padX, fs + 2 * padY, fs);
    } else {
      fxCtx.rect(x - w / 2 - padX, cy - fs / 2 - padY, w + 2 * padX, fs + 2 * padY);
    }
    fxCtx.fill();
    fxCtx.fillStyle = '#f2f6f8';
    fxCtx.fillText(a.who, x, cy);
    fxCtx.restore();
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

/* Krajina, pripadne prolnuti stare do nove pri prepnuti sceny: stara se
   kresli primo, nova do bufferu a pres ni s rostouci alfou — jeji kreslic
   si uvnitr nastavuje vlastni globalAlpha, takze pruhledne primo kreslit
   nejde. Buffer zije jen po dobu prechodu. */
function drawBackdrop(dt) {
  if (xfade && (xfade.t += dt / XFADE_S) >= 1) xfade = null;
  if (xfade && backdrop) {
    xfade.old.draw(ctx, W, H, sceneTime);
    if (!xfade.buf || xfade.buf.width !== canvas.width
                   || xfade.buf.height !== canvas.height) {
      xfade.buf = document.createElement('canvas');
      xfade.buf.width = canvas.width;
      xfade.buf.height = canvas.height;
    }
    const bctx = xfade.buf.getContext('2d');
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    backdrop.draw(bctx, W, H, sceneTime);
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = Math.min(1, xfade.t);
    ctx.drawImage(xfade.buf, 0, 0);
    ctx.restore();
  } else if (backdrop) {
    backdrop.draw(ctx, W, H, sceneTime);
  } else {
    ctx.fillStyle = '#123';
    ctx.fillRect(0, 0, W, H);
  }
}

function draw(dt) {
  drawBackdrop(dt);

  const order = actors.slice().sort((a, b) => a.yFrac - b.yFrac);
  for (const a of order) {
    const scale = depthScale(a.yFrac);
    const targetPx = W * (motionCfg(a.motion).lengthFraction || 0.17) * scale;
    const age = sceneTime - a.born;
    let pop = age < 0.9 ? 0.72 + 0.28 * Math.min(1, age / 0.9) : 1;
    // odchod pri prepnuti sceny: zmenseni do ztracena, obraceny "pop"
    if (a.leaving) pop *= Math.max(0, 1 - (sceneTime - a.leaving) / LEAVE_S);
    const x = a.xFrac * W, y = a.yFrac * H;

    if (a.m3) {
      // u 3D tvora je yFrac primo cara, na ktere stoji nohama
      const s = W * (motionCfg(a.motion).sizeFraction
                     || motionCfg('walk').sizeFraction || 0.234) * scale / a.m3.sizePx;
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
  if (backdrop && backdrop.drawFront) backdrop.drawFront(fxCtx, W, H, sceneTime);
  drawFoods();
  drawTags();
  Tune.drawOverlay(fxCtx, W, H);   // editor tras; mimo editaci nekresli nic
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
  // role klipu (pohyb, stani, skok) rika katalog — jmena se nehadaji ve scene
  const cf = spec.clipFor || {};
  const clip = spec.clips[cf.move] || spec.pose;
  const breaks = cf.stand || cf.jump
    ? { stand: spec.clips[cf.stand], jump: spec.clips[cf.jump] }
    : undefined;
  const m3 = await Scene3D.spawn({
    id: item.id, glb: spec.glb, motion: spec.motion, clip, breaks,
    texture: item.texture || (item.url || `/catch/${item.id}/`) + 'texture.png',
  });
  return addActor({ m3, id: item.id, key: spec.key, strideRate: spec.strideRate,
                    motion: spec.motion, label: spec.label }, opts);
}

function arrive(item, opts) {
  return item.kind === 'model' ? loadModel(item, opts) : loadRig(item, opts);
}

async function catalogue() {
  try {
    const scope = sceneDef ? '?scene=' + encodeURIComponent(sceneDef.catalogue) : '';
    const list = await (await fetch('/api/dino3d' + scope)).json();
    byKey.clear();
    ambientQueue = [];
    for (const e of list) byKey.set(e.key, e);
  } catch (e) {
    note('katalog: ' + e.message);
  }
}

async function fetchSettings() {
  try {
    const s = await (await fetch('/api/scene/settings')).json();
    ambientEnabled = !!s.ambient;
  } catch (e) {
    /* necháme výchozí (zapnuto) — scéna se dá ladit i bez serveru */
  }
}

/* Reset z /rezim (bod d): ulovky zmizi, ambientni doplnky z katalogu
   zustanou. Jeden souhrnny zaznam v listě mísi vypadá lip nez zaplaveni N
   jednotlivymi "odešel". */
function clearCatches() {
  // odchod se odehrava i tady; quiet drzi jeden souhrnny zaznam v liste
  for (const a of actors) {
    if (!a.ambient) beginExit(a, true);
  }
  Roster.event('note', 'Stanice vyprázdněna');
  topUp();
}

async function fetchCast() {
  // scoped na scenu: ulovky cizi krajiny se nenacitaji (a nemazou) — objevi
  // se zase po prepnuti zpatky
  const scope = sceneDef ? '&scene=' + encodeURIComponent(sceneDef.key) : '';
  const res = await fetch('/api/rigs?' + SIDQ + scope);
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
  // pred nactenim definice sceny (boot) a behem prepnuti se nerekonciliuje —
  // fetchCast by bez sceny prinesl i ulovky cizi krajiny
  if (switching || !sceneDef) return;
  let items;
  try {
    items = await fetchCast();
  } catch (e) {
    return;
  }
  if (!items) return;
  const known = new Set(items.map(i => i.id));
  for (const a of actors) {
    if (!a.ambient && !known.has(a.id)) beginExit(a);
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

async function loadSceneDef(key) {
  return (await import(`./scenes/${key}.js`)).default;
}

/* Přepnutí scény za běhu (zpráva `scene` z WS): tvorové odejdou zmenšením do
   ztracena, krajina se prolne do nové, 3D vrstva dostane nové osvětlení a po
   odchodu staré sestavy se přivedou úlovky a doplňky nové scény. Úlovky cizí
   krajiny se nenačítají a nemažou — čekají na přepnutí zpátky. */
async function switchScene(key) {
  if (!key || switching || (sceneDef && sceneDef.key === key)) return;
  switching = true;
  try {
    const def = await loadSceneDef(key);
    const bd = await def.backdrop();
    for (const a of actors) if (!a.leaving) a.leaving = sceneTime;
    if (backdrop) xfade = { old: backdrop, t: 0, buf: null };
    sceneDef = def;
    backdrop = bd;
    Scene3D.setLighting(def.lighting);
    await catalogue();
    toast('Krajina: ' + def.label);
    // novou sestavu privest az kdyz stara odejde (update ji doztraci)
    setTimeout(async () => {
      switching = false;
      try {
        await restoreCast();
      } finally {
        topUp();
      }
    }, (LEAVE_S + 0.4) * 1000);
  } catch (e) {
    switching = false;
    note('scéna: ' + (e && e.message || e));
  }
}

let wsDelay = 3000;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(proto + '://' + location.host + '/ws?' + SIDQ);
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
      qrArrived();      // zmenseni patri kazdemu prirustku, bez ohledu na kind
      idleHide();       // upload = touch na serveru, odpocet uz nebezi
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
      for (const a of actors) {
        if (a.id === msg.id) beginExit(a);
      }
      topUp();
    } else if (msg.type === 'feed') {
      dropFood(typeof msg.x === 'number' ? msg.x : 0.5);
    } else if (msg.type === 'settings') {
      ambientEnabled = !!msg.ambient;
      if (ambientEnabled) topUp();
    } else if (msg.type === 'cleared') {
      clearCatches();
    } else if (msg.type === 'scene') {
      switchScene(msg.scene);
    } else if (msg.type === 'idle') {
      idleWarn(msg.seconds_left);
    } else if (msg.type === 'sleep') {
      sleepScene();
    } else if (msg.type === 'wake') {
      wakeScene();
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
  scene: () => sceneDef,           // editor tras edituje aktivni scenu
  read: () => {
    const rows = new Map();
    for (const a of actors) {
      let r = rows.get(a.key);
      if (!r) rows.set(a.key, r = { key: a.key, label: a.label, count: 0,
                                    autoRate: 0, rate: 0, px: 0, cycle: 0,
                                    autoSpeed: 1,
                                    stride: a.m3 ? a.m3.strideBodies : 0 });
      r.count++;
      r.autoRate += a.autoRate;
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

/* QR panel v pravem hornim rohu (bod a): plny prvnich QR_FULL_MS po startu,
   pak mini; hned mini po prvnim WS `add`; po QR_IDLE_MS klidu (zadny `add`)
   se jednou na QR_REMIND_MS plynule pripomene. Casy se daji docasne zkratit
   pres window.QR_*_MS pred nactenim stranky (Playwright), zdrojak zustava
   netknuty. Klavesa H je rucni override: prebiji vzhled uplnym skryti/
   zobrazenim a od prvniho stisku natrvalo vypne automatiku. */
const QR_FULL_MS = window.QR_FULL_MS || 90000;
const QR_IDLE_MS = window.QR_IDLE_MS || 10 * 60000;
const QR_REMIND_MS = window.QR_REMIND_MS || 20000;

let qrManual = false;
let qrShrinkTimer = 0, qrIdleTimer = 0, qrRemindTimer = 0;

function qrSetMini(mini) {
  hintEl.classList.toggle('mini', mini);
}

function qrScheduleIdleRemind() {
  clearTimeout(qrIdleTimer);
  qrIdleTimer = setTimeout(() => {
    if (!qrManual) {
      qrSetMini(false);
      qrRemindTimer = setTimeout(() => { if (!qrManual) qrSetMini(true); }, QR_REMIND_MS);
    }
    qrScheduleIdleRemind();       // pripominka se opakuje po kazdych QR_IDLE_MS klidu
  }, QR_IDLE_MS);
}

function qrArrived() {
  clearTimeout(qrShrinkTimer);
  clearTimeout(qrRemindTimer);
  if (!qrManual) qrSetMini(true);
  qrScheduleIdleRemind();         // klid se pocita znovu od posledniho prirustku
}

function qrInit() {
  qrShrinkTimer = setTimeout(() => { if (!qrManual) qrSetMini(true); }, QR_FULL_MS);
  qrScheduleIdleRemind();
}

/* Uspavani (bod 6). Server posila `idle` s odpoctem (prubezne, kazdy tick),
   pak `sleep`; probuzeni skenem QR / touch prijde jako `wake`. Nic se nemaze
   a rAF smycka jede dal — spanek je jen ztmaveni + velke QR. Default session
   "tv" server neuspava, tyhle stavy tam nikdy neprijdou. */
const idleEl = document.getElementById('idlebar');
const sleepEl = document.getElementById('sleep');
let idleDeadline = 0, idleTicker = 0;

function fmtLeft(s) {
  const m = Math.floor(s / 60), ss = Math.max(0, Math.floor(s % 60));
  return m + ':' + String(ss).padStart(2, '0');
}

function idleRender() {
  const left = Math.max(0, (idleDeadline - performance.now()) / 1000);
  idleEl.textContent = 'Stanice za ' + fmtLeft(left)
                     + ' usne 🌙 — naskenuj QR, ať zůstane vzhůru';
}

function idleWarn(secondsLeft) {
  idleDeadline = performance.now() + (secondsLeft || 0) * 1000;
  idleRender();
  idleEl.classList.add('show');
  if (!idleTicker) idleTicker = setInterval(idleRender, 500);
  if (!qrManual) qrSetMini(false);   // velke QR, at jde naskenovat pres mistnost
}

function idleHide() {
  clearInterval(idleTicker);
  idleTicker = 0;
  idleEl.classList.remove('show');
}

function sleepScene() {
  idleHide();
  document.body.classList.add('sleeping');
  sleepEl.classList.add('show');
}

function wakeScene() {
  idleHide();
  document.body.classList.remove('sleeping');
  sleepEl.classList.remove('show');
  if (!qrManual) { qrSetMini(false); qrInit(); }  // probuzeni = novy start panelu
}

function qrToggleManual() {
  qrManual = true;
  clearTimeout(qrShrinkTimer);
  clearTimeout(qrIdleTimer);
  clearTimeout(qrRemindTimer);
  hintEl.style.opacity = hintEl.style.opacity === '0' ? '1' : '0';
}

document.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (e.target.tagName === 'INPUT') return;      // v panelu se pise
  if (k === 'd') Tune.toggle();
  if (k === 'i') Roster.toggle();
  if (k === 'f') {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  }
  if (k === 'h') qrToggleManual();
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
    route: a.route ? a.route.path.name || '' : null,
    kind: a.m3 ? 'model' : 'rig', ambient: a.ambient,
    exiting: !!a.exiting, feeding: !!a.feed,
    x: +a.xFrac.toFixed(3), y: +a.yFrac.toFixed(3), dir: a.dir,
    // tempo za plne chuze (bez zastavek), at se da merit bez sahani do kosti
    speedPx: +(a.speed * W).toFixed(1),
    bodiesPerS: a.natural ? +(a.natural * a.rate * a.speedMul).toFixed(4) : null,
    cycle: a.m3 && a.m3.duration ? +(a.m3.duration / a.rate).toFixed(3) : null,
  })),
  foods: () => foods.map(f => ({ x: f.x, y: +f.y.toFixed(3),
                                 age: +(sceneTime - f.born).toFixed(2) })),
  feed: dropFood,                  // rucni krmeni (Playwright/ladeni)
  ambient: () => ambientEnabled,   // pro ladeni a testy bodu c)
  session: () => SID,
  scene: () => sceneDef && sceneDef.key,   // aktivni krajina (bod 8)
  switchScene,                             // rucni prepnuti (Playwright/ladeni)
  // ladici vstupy do spaciho UI (Playwright): server je jediny, kdo tyhle
  // stavy doopravdy ridi, ale vizual se musi dat prohlednout i bez cekani
  debugIdle: (s) => idleWarn(s == null ? 120 : s),
  debugSleep: sleepScene,
  debugWake: wakeScene,
};

const qr = document.getElementById('qr');
qr.src = '/api/qr?' + SIDQ;
qr.onerror = () => { hintEl.style.display = 'none'; };
document.getElementById('sleepqr').src = qr.src;

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

/* Start: nejdriv zjistit, jaka krajina plati (?scene= prebiji hodnotu session
   ze serveru), nacist jeji definici a backdrop, pak katalog a ulovky. Scena
   se da ladit i bez serveru — pak plati default. */
async function boot() {
  let key = SCENE_OVERRIDE;
  if (!key) {
    try {
      key = (await (await fetch('/api/scene/active?' + SIDQ)).json()).scene;
    } catch (e) { /* bez serveru plati default */ }
  }
  try {
    sceneDef = await loadSceneDef(key || DEFAULT_SCENE);
  } catch (e) {
    try {
      sceneDef = await loadSceneDef(DEFAULT_SCENE);
      note('scéna ' + key + ' se nenačetla, jede ' + DEFAULT_SCENE);
    } catch (e2) {
      die('Definice scény se nenačetla: ' + (e2 && e2.message || e2));
      window.__ready = true;
      return;
    }
  }
  Scene3D.setLighting(sceneDef.lighting);
  try {
    backdrop = await sceneDef.backdrop();
  } catch (e) {
    note('krajina: ' + (e && e.message || e));
  }
  await Promise.all([catalogue(), fetchSettings()]);
  await restoreCast();
  await topUp();
  window.__ready = true;
}

boot();
connect();
requestAnimationFrame(frame);
qrInit();
