/* Planovac cinnosti chodcu — cista logika bez DOM a three.js, at jde testovat
   v Node (`node --test tests/js`). scene.js ji vola kazdy snimek a provadi
   prikazy, ktere vrati (prehraj klip, otoc hlavu…).

   Tvor si vybira dalsi cinnost z nabidky sveho druhu. Nabidka (vahy, delky)
   je v datech sceny (render.js `motions.walk.activities`), druh ji smi
   prepsat (`activities` u tvora ve scene.json). Cinnost, jejiz klip druh
   nema, se nenabizi; bez klipu stani se tvor nezastavi nikdy — zastaveni
   bez pozy, do ktere se da prolnout, by ho zmrazilo v pulce kroku.

   Druhy cinnosti (kod, ne data — urcuji, jak se cinnost odehraje):
     move   walk, run         tvor jde; run prolne chuzi do klipu Run
     still  stand, look,      stoji v Idle; look/greet navic otoci hlavu
            eat, greet        k detem (Scene3D.look)
     clip   lookaround,       klip se pusti od zacatku a dohraje (rozhlednuti,
            jump, play        skok, dupnuti), pak zpatky do stani
     pose   sit, lie          klip jednou dolu a podrzet, vstavani = tyz klip
                              pozpatku; z lehu muze tvor usnout (sleep,
                              delsi prolnuti, protoze konec LieDown neni
                              zacatek Sleep) */

export const KIND = {
  walk: 'move', run: 'move',
  stand: 'still', look: 'still', eat: 'still', greet: 'still',
  lookaround: 'clip', jump: 'clip', play: 'clip',
  sit: 'pose', lie: 'pose',
};

// role klipu (clipFor z katalogu), kterou cinnost potrebuje
export const ROLE = {
  run: 'run', stand: 'stand', look: 'stand', eat: 'stand', greet: 'stand',
  lookaround: 'look', jump: 'jump', play: 'play', sit: 'sit', lie: 'lie',
  sleep: 'sleep',
};

const HEAD = new Set(['look', 'greet']);
const POSE_FADE = 0.3;

export function span(r, rnd = Math.random) {
  if (typeof r === 'number') return r;
  if (!r) return 0;
  return r[0] + rnd() * (r[1] - r[0]);
}

/* Nabidka sceny prepsana nabidkou druhu, po cinnostech (melke slouceni:
   druh smi zmenit jen vahu a delku si nechat ze sceny). */
export function mergeTable(scene, species) {
  const out = {};
  for (const src of [scene || {}, species || {}]) {
    for (const [k, v] of Object.entries(src)) {
      out[k] = v && typeof v === 'object' && !Array.isArray(v)
        ? { ...(out[k] || {}), ...v } : v;
    }
  }
  return out;
}

/* Co umi tvor: `clips` = {role: delka klipu v s} jen pro role, ktere druh
   ma, `head` = ma kost hlavy pro pohled k detem. */
export function caps({ clips = {}, head = false } = {}) {
  return { clips, head, canStop: clips.stand > 0 };
}

/* Cinnosti, ktere tvor s danymi klipy vubec muze dostat. */
export function offered(table, cp) {
  const out = [];
  for (const name of Object.keys(table || {})) {
    const kind = KIND[name];
    if (!kind) continue;
    const role = table[name].role || ROLE[name];
    if (role && !(cp.clips[role] > 0)) continue;
    if (kind !== 'move' && !cp.canStop) continue;
    if (name === 'look' && !cp.head) continue;
    out.push(name);
  }
  return out;
}

/* Co prichazi v uvahu v dane situaci:
     free  tvor jde a rozhoduje se, co dal (walk = jit dal)
     wait  stoji ve fronte a nudi se — jen na miste; sit/lie az po `bored` s
     stop  zastavka trasy delky `left` s — co se do ni vejde */
export function candidates(table, names, ctx) {
  const where = ctx.where || 'free';
  const out = [];
  for (const name of names) {
    const spec = table[name] || {};
    const kind = KIND[name];
    if (name === 'eat' || name === 'greet') continue;
    if (where === 'free') {
      if (kind === 'pose' && spec.after && (ctx.sinceRest || 0) < spec.after) continue;
      if (kind !== 'move' && ctx.onScreen === false) continue;
    } else {
      if (kind === 'move') continue;
      if (where === 'wait' && kind === 'pose') {
        const bored = (table.wait && table.wait.bored) || 0;
        if ((ctx.waited || 0) < bored) continue;
      }
      if (where === 'stop') {
        if (kind === 'pose' && (ctx.left || 0) < 2 * (ctx.clips[spec.role || ROLE[name]] || 0) + 1.5) continue;
        if (kind === 'clip' && (ctx.left || 0) < (ctx.clips[spec.role || ROLE[name]] || 0)) continue;
      }
    }
    const w = where === 'free' ? spec.weight : (spec.waitWeight ?? spec.weight);
    if (w > 0) out.push([name, w]);
  }
  return out;
}

export function pick(table, names, ctx, rnd = Math.random) {
  const list = candidates(table, names, ctx);
  const total = list.reduce((s, [, w]) => s + w, 0);
  if (!total) return null;
  let r = rnd() * total;
  for (const [name, w] of list) {
    if ((r -= w) < 0) return name;
  }
  return list[list.length - 1][0];
}

/* Nova cinnost. `dur` prebije delku z dat (zastavka trasy, jidlo), `ext`
   = stoji, dokud trva vnejsi duvod (kolizni fronta). */
export function begin(name, table, cp, now, rnd = Math.random, opts = {}) {
  const spec = (table && table[name]) || {};
  const kind = KIND[name] || 'still';
  const role = spec.role || ROLE[name] || 'stand';
  const act = {
    name, kind, role, start: now, phase: kind === 'move' ? 'go' : 'stop',
    until: 0, ext: !!opts.ext, pose: { stand: 1 }, fade: POSE_FADE,
    dur: opts.dur != null ? opts.dur : span(spec.dur, rnd), cut: false,
  };
  if (kind === 'move') act.until = now + act.dur;
  if (kind === 'pose') {
    // delka zastavky zahrnuje sednuti i vstani, drzi se jen zbytek
    const clip = cp.clips[role] || 0;
    if (opts.dur != null) act.dur = Math.max(1.5, opts.dur - 2 * clip);
  }
  return act;
}

/* Prerusi cinnost (odchod, jidlo, otocka ze setkani): stani skonci hned,
   lezici/sedici tvor nejdriv vstane, rozehrany klip dohraje. */
export function interrupt(act) {
  if (!act) return;
  act.cut = true;
  if (act.kind === 'move' || act.phase === 'stop') { act.phase = 'done'; return; }
  if (act.kind === 'still' && act.phase === 'hold') act.until = -Infinity;
  if (act.phase === 'hold' && act.kind === 'pose') act.until = -Infinity;
  if (act.phase === 'sleep' || act.phase === 'sleepIn') act.until = -Infinity;
}

/* Jeden krok cinnosti. env: {now, stopped (mix dosedl na stani a tvor se
   neotaci), released (vnejsi duvod stat skoncil), sleep: {chance, dur, fade}
   nebo null, kdyz spanek neni nabizeny}. Vraci prikazy pro scenu:
     {do: 'play', clip, reverse}  jednorazove prehrani s podrzenim (Scene3D.playClamped)
     {do: 'restart', clip}        smycku od zacatku (Scene3D.restart)
     {do: 'look', on}             hlava k detem / zpatky */
export function advance(act, env, cp, rnd = Math.random) {
  const cmds = [];
  const now = env.now;
  const clipDur = cp.clips[act.role] || 0;
  // vic prechodu v jednom snimku (kratke klipy pri velkem dt)
  for (let guard = 0; guard < 6; guard++) {
    const before = act.phase;
    step(act, env, cmds, now, clipDur, rnd);
    if (act.phase === before || act.phase === 'done') break;
  }
  return cmds;
}

function step(act, env, cmds, now, clipDur, rnd) {
  switch (act.phase) {
    case 'go':
      if (now >= act.until) act.phase = 'done';
      return;
    case 'stop':
      if (!env.stopped) return;
      if (act.kind === 'still') {
        act.phase = 'hold';
        act.until = now + act.dur;
        if (HEAD.has(act.name)) cmds.push({ do: 'look', on: true });
      } else if (act.kind === 'clip') {
        act.phase = 'clip';
        act.pose = { [act.role]: 1 };
        act.fade = POSE_FADE;
        act.until = now + clipDur * Math.max(1, act.loops || 1);
        cmds.push({ do: 'restart', clip: act.role });
      } else {
        act.phase = 'down';
        act.pose = { [act.role]: 1 };
        act.fade = POSE_FADE;
        act.until = now + clipDur;
        cmds.push({ do: 'play', clip: act.role, reverse: false });
      }
      return;
    case 'hold':
      if (act.kind === 'still') {
        const over = act.ext ? env.released || act.until === -Infinity : now >= act.until;
        if (!over) return;
        if (HEAD.has(act.name)) cmds.push({ do: 'look', on: false });
        act.phase = 'done';
        return;
      }
      if (now < act.until) return;
      if (act.role === 'lie' && env.sleep && !act.cut && rnd() < (env.sleep.chance || 0)) {
        act.phase = 'sleepIn';
        act.pose = { sleep: 1 };
        act.fade = env.sleep.fade || 0.8;
        act.until = now + act.fade;
        act.sleepFor = span(env.sleep.dur, rnd);
        cmds.push({ do: 'restart', clip: 'sleep' });
        return;
      }
      standUp(act, now, clipDur, cmds);
      return;
    case 'down':
      if (now < act.until) return;
      if (act.cut) { standUp(act, now, clipDur, cmds); return; }
      act.phase = 'hold';
      act.until = now + act.dur;
      return;
    case 'sleepIn':
      if (now < act.until && act.until !== -Infinity) return;
      act.phase = 'sleep';
      act.until = act.cut ? now : now + act.sleepFor;
      return;
    case 'sleep':
      if (now < act.until) return;
      act.phase = 'sleepOut';
      act.pose = { [act.role]: 1 };
      act.until = now + act.fade;
      return;
    case 'sleepOut':
      if (now < act.until) return;
      standUp(act, now, clipDur, cmds);
      return;
    case 'up':
    case 'clip':
      if (now < act.until) return;
      act.phase = 'out';
      act.pose = { stand: 1 };
      act.fade = POSE_FADE;
      act.until = now + POSE_FADE;
      return;
    case 'out':
      if (now >= act.until) act.phase = 'done';
      return;
    default:
      act.phase = 'done';
  }
}

function standUp(act, now, clipDur, cmds) {
  act.phase = 'up';
  act.pose = { [act.role]: 1 };
  act.fade = POSE_FADE;
  act.until = now + clipDur;
  cmds.push({ do: 'play', clip: act.role, reverse: true });
}

/* Planovac jednoho tvora. `p` je jeho stav ({act, walkUntil, waitNext,
   restEnd, greet}), env popisuje situaci ve scene:
     now, stopped       viz advance
     hold               vnejsi duvod stat: 'queue' | 'route' | 'food' | ''
     holdLeft           kolik zbyva (fronta: Infinity)
     canDecide          tvor smi zacit neco noveho (neodchazi, nejde za jidlem,
                        neotaci se)
     onScreen           cely tvor je v obraze (zastavovat za okrajem nema smysl)
     greetReady         novy ulovek je cely v obraze — pozdravi deti
     exiting            odchazi: nic noveho, rozehrane se prerusi
   Vraci prikazy jako advance. */
export function plan(p, env, table, cp, names, rnd = Math.random) {
  const cmds = [];
  const now = env.now;
  if (p.act && env.exiting && !p.act.cut) interrupt(p.act);
  if (p.act) {
    cmds.push(...advance(p.act, {
      now, stopped: env.stopped, released: env.hold !== 'queue',
      sleep: names.includes('lie') && cp.clips.sleep > 0 ? table.sleep : null,
    }, cp, rnd));
    if (p.act.phase === 'done') {
      const a = p.act;
      p.act = null;
      if (a.kind === 'pose') p.restEnd = now;
      if (!a.ext && a.name !== 'eat') p.walkUntil = now + span((table.walk || {}).dur, rnd);
    } else if (p.act.ext && p.act.phase === 'hold' && env.hold === 'queue'
               && now >= (p.waitNext || 0)) {
      // fronta trva: misto stani obcas neco na miste (rozhlednuti, skok…)
      const name = pick(table, names, { where: 'wait', waited: now - p.act.start,
                                        clips: cp.clips }, rnd);
      p.waitNext = now + span((table.wait || {}).every || [3, 7], rnd);
      if (name && name !== 'stand') {
        p.act = begin(name, table, cp, now, rnd);
        cmds.push(...advance(p.act, { now, stopped: env.stopped, released: false }, cp, rnd));
      }
    }
    return cmds;
  }
  if (env.exiting) return cmds;
  if (env.hold && cp.canStop) {
    if (env.hold === 'queue') {
      p.act = begin('stand', table, cp, now, rnd, { ext: true });
      p.waitNext = now + span((table.wait || {}).every || [3, 7], rnd);
    } else if (env.hold === 'food') {
      p.act = begin(names.includes('eat') ? 'eat' : 'stand', table, cp, now, rnd,
                    { dur: Math.max(1, env.holdLeft) });
    } else {
      const name = pick(table, names, { where: 'stop', left: env.holdLeft, clips: cp.clips }, rnd)
                || 'stand';
      p.act = begin(name, table, cp, now, rnd, { dur: Math.max(1, env.holdLeft) });
    }
  } else if (p.greet && env.greetReady && cp.canStop && env.canDecide) {
    p.greet = false;
    p.act = begin('greet', table, cp, now, rnd);
  } else if (now >= (p.walkUntil || 0) && env.canDecide) {
    const name = pick(table, names, {
      where: 'free', onScreen: env.onScreen,
      sinceRest: now - (p.restEnd ?? p.born ?? 0),
    }, rnd);
    if (!name || name === 'walk') {
      p.walkUntil = now + span((table.walk || {}).dur || [10, 20], rnd);
    } else {
      p.act = begin(name, table, cp, now, rnd);
    }
  }
  if (p.act) cmds.push(...advance(p.act, { now, stopped: env.stopped, released: env.hold !== 'queue' }, cp, rnd));
  return cmds;
}

/* Ma tvor stat? (cil `mix`: 1 = stoji, 0 = jde) */
export function wantsStill(p) {
  return !!(p.act && p.act.kind !== 'move');
}

/* Vahy poz uvnitr stani: kazda se blizi cili o `step` (= dt / fade) a soucet
   se srovna na jednicku, at se pri prolinani tvor nepropadne do chuze. */
export function blendToward(weights, target, step) {
  const keys = new Set([...Object.keys(weights), ...Object.keys(target)]);
  const out = {};
  let sum = 0;
  for (const k of keys) {
    const w = weights[k] || 0, t = target[k] || 0;
    const v = w + Math.max(-step, Math.min(step, t - w));
    if (v > 1e-4) { out[k] = v; sum += v; }
  }
  if (sum <= 0) return { ...target };
  for (const k of Object.keys(out)) out[k] /= sum;
  return out;
}

export function toward(value, goal, step) {
  return value + Math.max(-step, Math.min(step, goal - value));
}

/* Tempo klipu chuze: zastaveni (mix) ho krati stejne jako rychlost po scene,
   takze pri zpomalovani chodidla drzi na zemi. */
export function walkTimeScale(rate, mix) {
  return rate * (1 - mix);
}

/* Posun za snimek pri prolinani chuze do behu: kazdy klip ujde svou drahu
   po vlastni krivce kroku a vazi se stejne jako jeho poza (runK). */
export function travel(walkStep, runStep, runK) {
  return (1 - runK) * walkStep + runK * runStep;
}

/* Hlidac zaseknuti: tvor, ktery ma jit (mix < 0.5), a presto se `limit`
   sekund nepohnul. `w` je stav hlidace pro jednoho tvora. */
export function stuckWatch(w, { now, x, mix, moving = true }, limit = 3, eps = 1e-4) {
  if (!moving || mix >= 0.5 || w.x == null || Math.abs(x - w.x) > eps) {
    w.x = x;
    w.since = now;
    return false;
  }
  return now - w.since > limit;
}
