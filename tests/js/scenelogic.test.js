// Planovac cinnosti bez prohlizece: node --test tests/js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as L from '../../web/scenelogic.js';

const TABLE = {
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
};
const DINO = { stand: 2.5, jump: 1.2, run: 0.8, look: 5, sit: 1.25, lie: 1.75,
               sleep: 3.2, play: 1.3 };

function rng(seed = 1) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

/* Jeden tvor jako ve scene.js: mix se blizi cili s prolnutim FADE, rychlost
   i tempo klipu jdou s (1 - mix), stoji = mix dosedl na jednicku. */
function walker(clips = DINO, opts = {}) {
  const cp = L.caps({ clips, head: opts.head ?? true });
  return {
    cp, names: L.offered(TABLE, cp), x: 0.5, mix: 0, hold: '', holdUntil: 0,
    p: { act: null, born: 0, restEnd: null, walkUntil: opts.walkUntil ?? 0,
         greet: !!opts.greet },
  };
}

const FADE = 0.7, RATE = 0.4, DT = 0.05;

function tick(w, now, rnd, env = {}) {
  if (w.hold && now > w.holdUntil) w.hold = '';
  const cmds = L.plan(w.p, {
    now, stopped: w.mix >= 0.99, hold: w.hold,
    holdLeft: w.hold === 'queue' ? Infinity : w.holdUntil - now,
    canDecide: true, onScreen: true, greetReady: env.greetReady ?? true,
    exiting: !!env.exiting,
  }, TABLE, w.cp, w.names, rnd);
  const still = L.wantsStill(w.p) && w.cp.canStop;
  w.mix = L.toward(w.mix, still ? 1 : 0, DT / FADE);
  const ts = L.walkTimeScale(RATE, w.mix);
  w.x += ts * DT * 0.1;
  return { cmds, ts };
}

test('activity without its clip is never offered', () => {
  const names = L.offered(TABLE, L.caps({ clips: { stand: 2, jump: 1 }, head: true }));
  assert.deepEqual(names.sort(), ['eat', 'greet', 'jump', 'look', 'stand', 'walk'].sort());
  // eat bez klipu pastvy = stani u jidla
  assert.equal(L.roleOf('eat', TABLE.eat, L.caps({ clips: { stand: 2 } })), 'stand');
  assert.equal(L.roleOf('eat', TABLE.eat, L.caps({ clips: { stand: 2, eat: 6 } })), 'eat');
});

test('a walker without an Idle clip is offered nothing that stops it', () => {
  const names = L.offered(TABLE, L.caps({ clips: { run: 0.8, jump: 1, sit: 1 } }));
  assert.deepEqual(names.sort(), ['run', 'walk']);
});

test('look at the kids needs a head bone', () => {
  assert.ok(!L.offered(TABLE, L.caps({ clips: DINO, head: false })).includes('look'));
  assert.ok(L.offered(TABLE, L.caps({ clips: DINO, head: true })).includes('look'));
});

test('species overrides weights but keeps the rest of the scene table', () => {
  const t = L.mergeTable(TABLE, { sit: { weight: 0 }, run: { speed: 2.5 } });
  assert.equal(t.sit.weight, 0);
  assert.deepEqual(t.sit.dur, [5, 9]);
  assert.equal(t.run.speed, 2.5);
  assert.equal(t.run.weight, 0.8);
  assert.ok(!L.candidates(t, L.offered(t, L.caps({ clips: DINO, head: true })),
                          { where: 'free', sinceRest: 1000, clips: DINO })
    .some(([n]) => n === 'sit'));
});

test('sleep is only reached through lying down, never picked directly', () => {
  const names = L.offered(TABLE, L.caps({ clips: DINO, head: true }));
  for (const where of ['free', 'wait', 'stop']) {
    const c = L.candidates(TABLE, names, { where, sinceRest: 1e6, waited: 1e6, left: 100, clips: DINO });
    assert.ok(!c.some(([n]) => n === 'sleep' || n === 'greet'), where);
  }
});

test('sit and lie wait until the animal has walked for a while', () => {
  const names = L.offered(TABLE, L.caps({ clips: DINO, head: true }));
  const early = L.candidates(TABLE, names, { where: 'free', sinceRest: 10, clips: DINO }).map(([n]) => n);
  const late = L.candidates(TABLE, names, { where: 'free', sinceRest: 100, clips: DINO }).map(([n]) => n);
  assert.ok(!early.includes('sit') && !early.includes('lie'));
  assert.ok(late.includes('sit') && late.includes('lie'));
});

// tmp/test_zastaveni.py: plynule zastaveni, stojici chodec se nehybe,
// letec nezastavi nikdy, tvor se zase rozejde
test('stop is smooth, a stopped walker does not move, and it walks on', () => {
  const w = walker();
  w.p.act = L.begin('stand', TABLE, w.cp, 0, rng(), { dur: 3 });
  const speeds = [];
  let now = 0;
  while (w.mix < 1) { now += DT; speeds.push(tick(w, now, rng()).ts); }
  for (let i = 1; i < speeds.length; i++) assert.ok(speeds[i] <= speeds[i - 1] + 1e-12);
  assert.ok(speeds.length >= 0.6 / DT, 'zastaveni trva aspon pul sekundy');
  const x0 = w.x;
  for (let i = 0; i < 20; i++) { now += DT; tick(w, now, rng()); }
  assert.equal(w.x, x0);
  for (let i = 0; i < 200 && w.p.act; i++) { now += DT; tick(w, now, rng()); }
  assert.equal(w.p.act, null);
  for (let i = 0; i < 40; i++) { now += DT; tick(w, now, rng()); }
  assert.equal(w.mix, 0);
  assert.ok(w.x > x0);
});

test('a flier (no stand clip) never stops, even when held or greeting', () => {
  const w = walker({}, { head: false, greet: true });
  const r = rng(3);
  let now = 0;
  for (let i = 0; i < 20000; i++) {
    now += DT;
    if (i % 500 === 0) { w.hold = i % 1000 ? 'route' : 'queue'; w.holdUntil = now + 4; }
    tick(w, now, r);
    assert.equal(w.mix, 0);
  }
});

test('sit plays once, holds, stands up with the clip reversed', () => {
  const w = walker();
  w.p.act = L.begin('sit', TABLE, w.cp, 0, rng());
  const seen = [], cmds = [];
  let now = 0;
  while (w.p.act && now < 60) {
    now += DT;
    const ph = w.p.act.phase;
    if (seen[seen.length - 1] !== ph) seen.push(ph);
    cmds.push(...tick(w, now, rng()).cmds);
  }
  assert.deepEqual(seen, ['stop', 'down', 'hold', 'up', 'out']);
  assert.deepEqual(cmds, [{ do: 'play', clip: 'sit', reverse: false },
                          { do: 'play', clip: 'sit', reverse: true }]);
  assert.ok(w.p.restEnd > 0);
});

test('lying animal may fall asleep with a long crossfade and wakes before standing', () => {
  const w = walker();
  const always = () => 0;          // sleep.chance vzdy padne
  w.p.act = L.begin('lie', TABLE, w.cp, 0, rng());
  const seen = [];
  let now = 0, fade = null;
  while (w.p.act && now < 120) {
    now += DT;
    const a = w.p.act;
    if (seen[seen.length - 1] !== a.phase) seen.push(a.phase);
    if (a.phase === 'sleepIn') fade = a.fade;
    tick(w, now, always);
  }
  assert.deepEqual(seen, ['stop', 'down', 'hold', 'sleepIn', 'sleep', 'sleepOut', 'up', 'out']);
  assert.equal(fade, 0.8);
});

test('interrupting a sleeping animal makes it wake and stand up, not pop', () => {
  const w = walker();
  w.p.act = L.begin('lie', TABLE, w.cp, 0, rng());
  let now = 0;
  while (w.p.act.phase !== 'sleep' && now < 60) { now += DT; tick(w, now, () => 0); }
  assert.equal(w.p.act.phase, 'sleep');
  const seen = [];
  let first = true, low = 1;
  while (w.p.act && now < 80) {
    now += DT;
    if (seen[seen.length - 1] !== w.p.act.phase) seen.push(w.p.act.phase);
    low = Math.min(low, w.mix);
    tick(w, now, () => 0, { exiting: first });
    first = false;
  }
  assert.deepEqual(seen, ['sleep', 'sleepOut', 'up', 'out']);
  assert.equal(low, 1, 'stoji az do konce vstavani');
});

test('queue: stands while blocked, picks something to do, walks when released', () => {
  const w = walker();
  const r = rng(7);
  let now = 0;
  const names = new Set();
  for (let i = 0; i < 1200; i++) {        // minuta ve fronte
    now += DT;
    w.hold = 'queue';
    w.holdUntil = now + 0.8;
    tick(w, now, r);
    if (w.p.act) names.add(w.p.act.name);
  }
  assert.ok(names.has('stand'));
  assert.ok(names.size >= 3, [...names].join());
  assert.ok(!names.has('run') && !names.has('walk'));
  for (let i = 0; i < 400 && w.p.act; i++) { now += DT; tick(w, now, r); }
  assert.equal(w.p.act, null);
});

test('new animal greets the kids once, when fully in view', () => {
  const w = walker(DINO, { greet: true, walkUntil: 1e9 });
  let now = 0;
  for (let i = 0; i < 40; i++) { now += DT; tick(w, now, rng(), { greetReady: false }); }
  assert.equal(w.p.act, null);
  const cmds = [];
  let greets = 0;
  for (let i = 0; i < 400; i++) {
    now += DT;
    const before = w.p.act;
    cmds.push(...tick(w, now, rng(), { greetReady: true }).cmds);
    if (w.p.act && w.p.act !== before && w.p.act.name === 'greet') greets++;
  }
  assert.equal(greets, 1);
  assert.deepEqual(cmds.filter(c => c.do === 'look').map(c => c.on), [true, false]);
});

test('route stop picks an activity that fits the dwell', () => {
  const w = walker(DINO, { walkUntil: 1e9 });
  for (let seed = 1; seed < 200; seed++) {
    w.p.act = null;
    w.hold = 'route';
    w.holdUntil = 3;
    L.plan(w.p, { now: 0, stopped: false, hold: 'route', holdLeft: 3, canDecide: true,
                  onScreen: true }, TABLE, w.cp, w.names, rng(seed));
    assert.ok(['stand', 'look', 'jump', 'play'].includes(w.p.act.name), w.p.act.name);
  }
});

test('ten simulated minutes: mostly walking, every activity ends, no freeze', () => {
  const w = walker();
  const r = rng(11);
  let now = 0, walking = 0, longest = 0, started = 0;
  const count = {};
  for (let i = 0; i < 10 * 60 / DT; i++) {
    now += DT;
    const before = w.p.act;
    tick(w, now, r);
    if (w.p.act && w.p.act !== before) {
      count[w.p.act.name] = (count[w.p.act.name] || 0) + 1;
      started = now;
    }
    if (w.p.act) longest = Math.max(longest, now - started);
    if (w.mix < 0.5) walking++;
  }
  const share = walking * DT / now;
  assert.ok(share > 0.6 && share < 0.97, `chuze ${share.toFixed(2)}`);
  assert.ok(longest < 40, `nejdelsi cinnost ${longest.toFixed(1)} s`);
  assert.ok(Object.keys(count).length >= 4, JSON.stringify(count));
});

test('pose weights stay normalised while crossfading', () => {
  let w = { stand: 1 };
  for (let i = 0; i < 30; i++) {
    w = L.blendToward(w, { lie: 1 }, 0.05);
    const sum = Object.values(w).reduce((a, b) => a + b, 0);
    assert.ok(Math.abs(sum - 1) < 1e-9);
  }
  assert.ok(w.lie > 0.99);
});

test('run blends the two gaits by their own stride', () => {
  assert.equal(L.travel(0.1, 0.3, 0), 0.1);
  assert.equal(L.travel(0.1, 0.3, 1), 0.3);
  assert.ok(Math.abs(L.travel(0.1, 0.3, 0.5) - 0.2) < 1e-12);
});

test('stuck watch fires only for a walker that should move and does not', () => {
  const s = {};
  assert.equal(L.stuckWatch(s, { now: 0, x: 0.5, mix: 0 }), false);
  assert.equal(L.stuckWatch(s, { now: 2, x: 0.5, mix: 0 }), false);
  assert.equal(L.stuckWatch(s, { now: 3.5, x: 0.5, mix: 0 }), true);
  assert.equal(L.stuckWatch(s, { now: 4, x: 0.5, mix: 1 }), false);
  assert.equal(L.stuckWatch(s, { now: 9, x: 0.5, mix: 1 }), false);
});
