/* Pohybové cykly. Každý vrací pózu: tečné úhly páteře (lokální prostor,
   x = od hlavy k ocasu, y dolů) a úhly/škály končetin. */

(function (global) {
  'use strict';

  const TAU = Math.PI * 2;

  function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
  function wrap(a) { return a - TAU * Math.round(a / TAU); }
  function smooth(v) { v = clamp01(v); return v * v * (3 - 2 * v); }

  function kindOf(name) {
    if (/wing/.test(name)) return 'wing';
    if (/prop/.test(name)) return 'prop';
    if (/sail/.test(name)) return 'sail';
    if (/mast/.test(name)) return 'mast';
    if (/fin_|_fin|flipper/.test(name)) return 'fin';
    if (/arm|hand/.test(name)) return 'arm';
    if (/leg|front|hind|foot|paw/.test(name)) return 'leg';
    if (/tail/.test(name)) return 'tail';
    return 'other';
  }

  const TUNE = {
    sauropod: { step: 1.55, neck: 0.085, tail: 0.055 },
    trex: { step: 1.05, neck: 0.050, tail: 0.075 },
    _default: { step: 1.25, neck: 0.070, tail: 0.060 },
  };

  const DUTY = 0.6;          // podíl cyklu, kdy noha stojí na zemi
  const EXCURSION = 0.45;    // rozkyv chodidla vůči tělu, v podílu dosahu nohy
  const LIFT = 0.16;         // zdvih ve švihu, v podílu dosahu nohy

  /* Končetiny se stejným jménem jsou jeden pár (blízká + vzdálená). Páry se
     očíslují od hlavy k ocasu, aby se dal rytmus odvodit z geometrie: přední
     pár je 0, zadní 1. */
  function unitsOf(rig) {
    if (rig._units) return rig._units;
    const anchor = Object.create(null);
    for (const l of rig.limbs) {
      const a = l.anchor === undefined || l.anchor === null ? 0.5 : l.anchor;
      if (!(l.name in anchor) || a < anchor[l.name]) anchor[l.name] = a;
    }
    const unit = Object.create(null);
    Object.keys(anchor).sort((a, b) => anchor[a] - anchor[b])
      .forEach((n, i) => { unit[n] = i; });
    rig._units = unit;
    return unit;
  }

  /* Chůze se počítá zpětnou kinematikou z geometrie v rig.json: chodidlo se
     v opoře posouvá dozadu rovnoměrně (proto tvor po zemi neplave) a kyčel se
     drží přesně tak vysoko, aby noha dosáhla, aniž by se natáhla na doraz. */
  function gaitOf(rig) {
    if (rig._gait) return rig._gait;
    const unit = unitsOf(rig);
    const legs = [];
    for (const l of rig.limbs) {
      if (kindOf(l.name) !== 'leg') continue;
      const seg = l.segments;
      const hip = seg[0].pivot_mm;
      const foot = seg[seg.length - 1].tip_mm;
      const lens = seg.map((s) => Math.hypot(s.tip_mm[0] - s.pivot_mm[0],
                                             s.tip_mm[1] - s.pivot_mm[1]));
      const rest = seg.map((s) => Math.atan2(s.tip_mm[1] - s.pivot_mm[1],
                                             s.tip_mm[0] - s.pivot_mm[0]));
      const reach = lens.reduce((a, b) => a + b, 0);
      legs.push({
        name: l.name, key: l.key, hip, foot, lens, rest, reach,
        dx0: foot[0] - hip[0], dy0: foot[1] - hip[1],
        // klus: úhlopříčná dvojice (přední blízká + zadní vzdálená) došlapuje spolu
        phase: (l.phase || 0) + 0.5 * ((unit[l.name] + (l.side || 0)) % 2),
        bend: 1,
      });
    }
    const spine = rig.body.spine_mm;
    const fwd = spine && spine[0][0] < spine[spine.length - 1][0] ? -1 : 1;
    const reach = legs.length
      ? legs.reduce((a, l) => a + l.reach, 0) / legs.length
      : bodyLength(rig) * 0.3;
    const excursion = EXCURSION * reach;
    const gait = {
      legs, fwd, excursion, lift: LIFT * reach,
      travel: excursion / DUTY,          // dráha tvora na jeden cyklus
    };
    for (const l of legs) {
      // Ohyb kolene se vybere podle nakreslené pózy: obě řešení dvoučlánkové
      // kinematiky vedou do stejného chodidla, ale jen jedno kopíruje kresbu.
      // Porovnat se musí obě — práh "do 90° od klidu" umí vybrat to druhé
      // a noha se pak při každém kroku přetočí a vyjede pod zem.
      const up = wrap(solveIk(l, l.foot[0], l.foot[1], 1)[0] - l.rest[0]);
      const dn = wrap(solveIk(l, l.foot[0], l.foot[1], -1)[0] - l.rest[0]);
      l.bend = Math.abs(up) <= Math.abs(dn) ? 1 : -1;
      l.maxSpan = 0.995 * l.reach;
    }
    rig._gait = gait;
    return gait;
  }

  function solveIk(leg, tx, ty, bend) {
    const l1 = leg.lens[0], l2 = leg.lens[1] || 0;
    let dx = tx - leg.hip[0], dy = ty - leg.hip[1];
    let d = Math.hypot(dx, dy) || 1e-6;
    const hi = l1 + l2 - 1e-4, lo = Math.abs(l1 - l2) + 1e-4;
    if (d > hi) { const k = hi / d; dx *= k; dy *= k; d = hi; }
    if (d < lo) { const k = lo / d; dx *= k; dy *= k; d = lo; }
    const base = Math.atan2(dy, dx);
    if (!l2) return [base];
    const acos = (v) => Math.acos(v < -1 ? -1 : v > 1 ? 1 : v);
    return [base + bend * acos((d * d + l1 * l1 - l2 * l2) / (2 * d * l1)),
            base - bend * acos((d * d + l2 * l2 - l1 * l1) / (2 * d * l2))];
  }

  function poseLeg(leg, st, tx, ty) {
    const phi = solveIk(leg, tx, ty, leg.bend);
    let acc = 0;
    for (let j = 0; j < st.angles.length; j++) {
      const want = phi[j] === undefined ? leg.rest[j] + acc : phi[j];
      st.angles[j] = want - leg.rest[j] - acc;
      acc += st.angles[j];
    }
  }

  function rest(st) {
    st.sx = 1;
    st.sy = 1;
    for (let j = 0; j < st.angles.length; j++) st.angles[j] = 0;
  }

  function bodyLength(rig) {
    const b = rig.body;
    if (b.length_mm) return b.length_mm;
    if (b.size_mm) return b.size_mm[0];
    return 200;
  }

  const frac = (v) => v - Math.floor(v);

  /* Fáze každé nohy plus výška, na kterou musí tělo klesnout, aby žádná
     opěrná noha nebyla natažená na doraz. */
  function legPhases(gait, ph) {
    let dip = 0, dipN = 0;
    const out = [];
    for (const leg of gait.legs) {
      const u = frac(ph + leg.phase);
      const stance = u < DUTY;
      const s = stance ? u / DUTY : (u - DUTY) / (1 - DUTY);
      const dx = stance ? gait.excursion * (0.5 - s)
                        : gait.excursion * (s - 0.5);
      out.push({ leg, dx, stance, s });
      if (stance) {
        const h = leg.dx0 + gait.fwd * dx;
        dip += leg.dy0 - Math.sqrt(Math.max(0, leg.maxSpan * leg.maxSpan - h * h));
        dipN++;
      }
    }
    return { legs: out, dip: dipN ? dip / dipN : 0 };
  }

  function walkLimbs(rig, gait, ph, step, dip, tgt) {
    for (const l of rig.limbs) {
      const st = tgt[l.key];
      if (!st) continue;
      rest(st);
      if (kindOf(l.name) === 'arm') {
        const p = TAU * (ph * 0.75 + 0.5 * (l.side || 0)) + 1.0;
        st.angles[0] = 0.15 * Math.sin(p) - 0.05;
        if (st.angles.length > 1) st.angles[1] = 0.13 * Math.sin(p + 1.9);
      }
    }
    for (const e of step.legs) {
      const st = tgt[e.leg.key];
      if (!st) continue;
      const lift = e.stance ? 0 : gait.lift * Math.sin(Math.PI * e.s);
      poseLeg(e.leg, st,
              e.leg.foot[0] + gait.fwd * e.dx,
              e.leg.foot[1] - dip - lift);
    }
  }

  function walk(rig, o, out) {
    const T = TUNE[rig.creature] || TUNE._default;
    const gait = gaitOf(rig);
    // fáze se veze na ujeté dráze, ne na čase — jinak noha po zemi klouže
    const ph = (o.distance !== undefined && gait.travel > 0
                ? o.distance / gait.travel
                : o.t / (T.step / o.speed)) + o.phase;
    const w = TAU * ph;
    const n = out.spine.length;
    for (let i = 0; i < n; i++) {
      const u = i / (n - 1);
      const wn = smooth((0.34 - u) / 0.34);
      const wt = smooth((u - 0.60) / 0.40);
      out.spine[i] = T.neck * wn * Math.sin(w * 0.5 + 0.6)
                   + T.tail * wt * Math.sin(w * 0.5 - 0.9);
    }
    const step = legPhases(gait, ph);
    out.rootDy = step.dip;
    out.rootRot = 0.012 * Math.sin(2 * w + 0.7);
    walkLimbs(rig, gait, ph, step, step.dip, out.limbs);
  }

  function swimLimbs(rig, o, ph, tgt) {
    const rowPeriod = 1.7 / o.speed;
    const unit = unitsOf(rig);
    for (const l of rig.limbs) {
      const st = tgt[l.key];
      if (!st) continue;
      rest(st);
      if (kindOf(l.name) !== 'fin') continue;
      // obě ploutve jednoho páru veslují spolu, zadní pár se opozdí za předním
      const p = TAU * (o.t / rowPeriod + ph + (l.phase || 0) + 0.3 * unit[l.name]);
      st.angles[0] = 0.40 * Math.sin(p);
      for (let j = 1; j < st.angles.length; j++) st.angles[j] = 0.16 * Math.sin(p - 0.8);
    }
  }

  function swim(rig, o, out) {
    const L = bodyLength(rig);
    const w = TAU * (o.t / (2.4 / o.speed) + o.phase);
    const n = out.spine.length;
    for (let i = 0; i < n; i++) {
      const u = i / (n - 1);
      const amp = 0.040 + 0.090 * u * u + 0.085 * smooth((0.30 - u) / 0.30);
      out.spine[i] = amp * Math.sin(w - TAU * 0.75 * u);
    }
    out.rootDy = 0.008 * L * Math.sin(w * 0.5 + 0.4);
    out.rootRot = 0.028 * Math.sin(w * 0.5 + 1.2);
    swimLimbs(rig, o, o.phase, out.limbs);
  }

  function flap(rig, o, out) {
    const period = 0.62 / o.speed;
    const f = Math.sin(TAU * (o.t / period + o.phase));
    const n = out.spine.length;
    const drift = TAU * 0.22 * o.t + o.phase * TAU;
    for (let i = 0; i < n; i++) {
      const u = i / (n - 1);
      out.spine[i] = 0.038 * smooth((u - 0.12) / 0.88) * Math.sin(drift - u * 1.4);
    }
    out.rootRot = 0.055 * Math.sin(TAU * 0.17 * o.t + o.phase * TAU);
    // rozpětí se v úvratích zkracuje, jak se křídlo naklání mimo rovinu pohledu
    const span = Math.cos(0.95 * f);
    for (const l of rig.limbs) {
      const st = out.limbs[l.key];
      if (!st) continue;
      rest(st);
      const k = kindOf(l.name);
      const side = l._side || 1;
      if (k === 'wing') {
        st.sy = span;
        st.angles[0] = 0.10 * f * side;
      } else if (k === 'tail') {
        st.angles[0] = 0.08 * side * Math.sin(TAU * (o.t / (period * 2) + o.phase));
      }
    }
  }

  function glide(rig, o, out) {
    const L = bodyLength(rig);
    const n = out.spine.length;
    const w = TAU * 0.30 * o.t + o.phase * TAU;
    for (let i = 0; i < n; i++) {
      out.spine[i] = 0.012 * Math.sin(w - (i / (n - 1)) * 0.8);
    }
    out.rootRot = 0.032 * Math.sin(TAU * 0.31 * o.t + o.phase * TAU)
                + 0.012 * Math.sin(TAU * 0.53 * o.t);
    out.rootDy = 0.013 * L * Math.sin(TAU * 0.27 * o.t + o.phase * 4);
    for (const l of rig.limbs) {
      const st = out.limbs[l.key];
      if (!st) continue;
      rest(st);
      if (kindOf(l.name) === 'prop') {
        const c = Math.cos(TAU * 7 * o.speed * o.t);
        st.sy = (c < 0 ? -1 : 1) * Math.max(0.14, Math.abs(c));
      }
    }
  }

  function fly(rig, o, out) {
    if ((rig.view || 'side') === 'top') flap(rig, o, out);
    else glide(rig, o, out);
  }

  function sail(rig, o, out) {
    const h = (rig.body.size_mm && rig.body.size_mm[1]) || 50;
    const n = out.spine.length;
    for (let i = 0; i < n; i++) out.spine[i] = 0;
    const w = TAU * 0.24 * o.speed * o.t + o.phase * TAU;
    out.rootRot = 0.055 * Math.sin(w) + 0.022 * Math.sin(w * 1.7 + 1.3);
    out.rootDy = 0.045 * h * Math.sin(w * 1.2 + 0.6);
    let idx = 0;
    for (const l of rig.limbs) {
      const st = out.limbs[l.key];
      if (!st) continue;
      rest(st);
      if (kindOf(l.name) === 'sail') {
        const p = w * 2.1 + idx * 1.7;
        idx++;
        st.sx = 1 + 0.055 * Math.sin(p);
        st.sy = 1 + 0.018 * Math.sin(p + 1.0);
      }
    }
  }

  const CYCLES = { walk, swim, fly, sail };

  function restAll(out) {
    for (let i = 0; i < out.spine.length; i++) out.spine[i] = 0;
    for (const k in out.limbs) rest(out.limbs[k]);
  }

  function pose(rig, o, out) {
    out.rootDx = 0;
    out.rootDy = 0;
    out.rootRot = 0;
    out.rootPivotX = 0;
    out.rootPivotY = 0;
    if (!o.speed) o.speed = 1;
    if (o.rest) {
      restAll(out);
      return out;
    }
    const cycle = CYCLES[rig.motion] || walk;
    cycle(rig, o, out);
    return out;
  }

  global.Anim = { pose, kindOf, gaitOf, unitsOf, TUNE };
})(window);
