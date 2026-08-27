/* Křídová laguna — malovaná krajina pro 2D plátno pod 3D tvory.

   ES modul s továrnou `create(variant)`: 'day' je původní slunečná pláž,
   'night' táž krajina za soumraku (měsíc, hvězdy, tlumená paleta). Vrací
   instanci `{draw, drawFront, sun, depthScale}` — pásy scény (bands) tu
   nejsou, ty patří do definice scény ve web/scenes/. */

const SEED = 20260825;

// Layer boundaries as fractions of canvas height.
const HORIZON = 0.44;
const FOREST_TOP = 0.385;
const FOREST_BASE = 0.525;
const FAR_SAND_TOP = 0.515;
const WATER_TOP = 0.565;
const WATER_BOT = 0.780;
const WET_SAND_BOT = 0.845;
const SAND_BOT = 0.920;

const DEPTH_MIN = 0.35;
const DEPTH_SKY_TOP = 0.30;

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function lerp(a, b, k) { return a + (b - a) * k; }
function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }

function rgba(c, a) {
  return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')';
}
function mix(a, b, k) {
  return [Math.round(lerp(a[0], b[0], k)), Math.round(lerp(a[1], b[1], k)),
          Math.round(lerp(a[2], b[2], k))];
}

// Sum of sines: smooth, seeded, infinitely samplable terrain noise.
function waveFn(rand, octaves, baseFreq, persistence) {
  const parts = []; let f = baseFreq, a = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    parts.push([f, a, rand() * Math.PI * 2]);
    norm += a; f *= 2.13; a *= persistence;
  }
  return function (x) {
    let s = 0;
    for (let j = 0; j < parts.length; j++) {
      s += parts[j][1] * Math.sin(x * parts[j][0] + parts[j][2]);
    }
    return s / norm;
  };
}

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

// ------------------------------------------------------------------ trees

function drawFir(ctx, x, baseY, h, w, color, rand) {
  const tiers = 5 + Math.floor(rand() * 3);
  ctx.fillStyle = color;
  ctx.fillRect(x - h * 0.016, baseY - h * 0.20, h * 0.032, h * 0.20);
  for (let i = 0; i < tiers; i++) {
    const f = i / tiers;
    const ty = baseY - h * 0.10 - f * h * 0.72;
    const tw = w * (1 - f * 0.80);
    const th = h * (0.26 - f * 0.06);
    ctx.beginPath();
    ctx.moveTo(x, ty - th);
    ctx.lineTo(x + tw, ty);
    ctx.lineTo(x + tw * 0.35, ty + h * 0.02);
    ctx.lineTo(x - tw * 0.35, ty + h * 0.02);
    ctx.lineTo(x - tw, ty);
    ctx.closePath();
    ctx.fill();
  }
}

// Araucaria: bare trunk, a few branch whorls, rounded crown.
function drawAraucaria(ctx, x, baseY, h, w, color, rand) {
  ctx.fillStyle = color;
  const lean = (rand() - 0.5) * w * 0.5;
  ctx.beginPath();
  ctx.moveTo(x - h * 0.020, baseY);
  ctx.lineTo(x + h * 0.020, baseY);
  ctx.lineTo(x + lean + h * 0.011, baseY - h * 0.70);
  ctx.lineTo(x + lean - h * 0.011, baseY - h * 0.70);
  ctx.closePath();
  ctx.fill();
  const whorls = 3 + Math.floor(rand() * 2);
  for (let i = 0; i < whorls; i++) {
    const f = 0.45 + (i / whorls) * 0.32;
    const wy = baseY - h * f;
    const ww = w * (0.55 + rand() * 0.5) * (1 - (f - 0.45) * 0.7);
    ctx.beginPath();
    ctx.ellipse(x + lean * f / 0.7, wy, ww, h * 0.045, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.beginPath();
  ctx.ellipse(x + lean, baseY - h * 0.80, w * 0.72, h * 0.13, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawCycad(ctx, x, baseY, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x - h * 0.09, baseY - h * 0.42, h * 0.18, h * 0.42);
  const n = 9;
  for (let i = 0; i < n; i++) {
    const a = -Math.PI + (i + 0.5) / n * Math.PI;
    const len = h * (0.52 + 0.14 * Math.sin(i * 1.7));
    ctx.beginPath();
    ctx.moveTo(x, baseY - h * 0.40);
    ctx.quadraticCurveTo(x + Math.cos(a) * len * 0.6, baseY - h * 0.40 + Math.sin(a) * len * 0.9,
                         x + Math.cos(a) * len, baseY - h * 0.40 + Math.sin(a) * len * 0.35);
    ctx.lineWidth = Math.max(1, h * 0.05);
    ctx.strokeStyle = color;
    ctx.stroke();
  }
}

// ------------------------------------------------------------------ ferns

function frondPath(x, y, len, ang, bend, n) {
  const pts = []; let px = x, py = y, a = ang; const step = len / n;
  for (let i = 0; i <= n; i++) {
    pts.push([px, py, a]);
    a += bend / n;
    px += Math.cos(a) * step;
    py += Math.sin(a) * step;
  }
  return pts;
}

function drawFrond(ctx, x, y, len, ang, bend, color) {
  const n = 30, pts = frondPath(x, y, len, ang, bend, n);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineCap = 'round';
  ctx.lineWidth = Math.max(1, len * 0.016);
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i <= n; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.stroke();
  for (let i = 3; i <= n - 1; i++) {
    const s = i / n;
    const ll = len * 0.20 * Math.sin(Math.PI * Math.pow(s, 0.55));
    if (ll <= 0.8) continue;
    const a = pts[i][2];
    for (let sgn = -1; sgn <= 1; sgn += 2) {
      const la = a + sgn * (1.30 - s * 0.55);
      ctx.beginPath();
      ctx.moveTo(pts[i][0], pts[i][1]);
      ctx.quadraticCurveTo(
        pts[i][0] + Math.cos(la) * ll * 0.55 + Math.cos(a) * ll * 0.10,
        pts[i][1] + Math.sin(la) * ll * 0.55 + Math.sin(a) * ll * 0.10,
        pts[i][0] + Math.cos(la) * ll + Math.cos(a) * ll * 0.42,
        pts[i][1] + Math.sin(la) * ll + Math.sin(a) * ll * 0.42);
      ctx.lineWidth = Math.max(1, len * 0.014);
      ctx.stroke();
    }
  }
}

// ----------------------------------------------------------- static layers

const SKY_BAND = 0.62;
const LAND_BAND = [0.16, 0.62];
const SHORE_BAND = [0.52, 1.0];

function shoreEdge(edge, x, H) { return H * 0.011 * edge(x); }

function depthScale(yFrac) {
  const y = clamp(yFrac, 0, 1);
  if (y <= HORIZON) {
    const k = 1 - y / HORIZON;
    return DEPTH_MIN - (DEPTH_MIN - DEPTH_SKY_TOP) * k * k;
  }
  const u = (y - HORIZON) / (1 - HORIZON);
  return DEPTH_MIN + (1 - DEPTH_MIN) * Math.pow(u, 1.6);
}

// ---------------------------------------------------------------- palette

const DAY = {
  SKY_TOP: [26, 92, 156], SKY_MID: [116, 184, 224], SKY_LOW: [188, 220, 234],
  SKY_HAZE: [252, 226, 186],
  RIDGE_FAR: [138, 162, 190], RIDGE_NEAR: [96, 126, 148], VOLCANO: [92, 106, 122],
  FOREST_BANDS: [[112, 148, 128], [74, 116, 94], [46, 88, 66], [30, 68, 50]],
  SAND_FAR: [228, 208, 172], SAND_NEAR: [236, 216, 176], SAND_WET: [196, 172, 132],
  ROCK: [88, 80, 72], ROCK_LIT: [132, 122, 106],
  FERN_DARK: [30, 62, 40], FERN_MID: [52, 96, 52],
  cloud: [255, 255, 255], cloudMid: [250, 250, 255], cloudAlpha: 1,
  hazeGlow: '252,232,200', hazeMid: 0.55,
  smoke: '232,228,224', smokeAlpha: 0.42,
  grainDark: '150,128,96', grainLight: '255,246,224',
  rockEdge: 'rgba(216,200,170,0.55)',
  water: ['rgb(122,196,196)', 'rgb(56,150,180)', 'rgb(20,100,158)',
          'rgb(14,80,138)', 'rgb(36,140,172)', 'rgb(112,204,200)'],
  ripple: 'rgba(226,248,252,1)',
  glitter: ['rgba(255,246,214,0.30)', 'rgba(255,240,200,0.11)', 'rgba(255,236,190,0)'],
  spark: 'rgba(255,252,235,1)',
  foam: 'rgba(248,255,255,1)', foamAlpha: 1,
  vignette: 'rgba(10,20,35,0.30)',
};

const NIGHT = {
  SKY_TOP: [5, 9, 26], SKY_MID: [14, 26, 56], SKY_LOW: [30, 46, 80],
  SKY_HAZE: [62, 76, 108],
  RIDGE_FAR: [52, 62, 90], RIDGE_NEAR: [36, 46, 68], VOLCANO: [32, 38, 52],
  FOREST_BANDS: [[40, 56, 68], [28, 44, 54], [18, 32, 40], [11, 22, 29]],
  SAND_FAR: [100, 104, 126], SAND_NEAR: [106, 110, 130], SAND_WET: [72, 78, 98],
  ROCK: [38, 38, 50], ROCK_LIT: [66, 68, 88],
  FERN_DARK: [12, 26, 26], FERN_MID: [24, 44, 40],
  cloud: [176, 192, 226], cloudMid: [150, 168, 208], cloudAlpha: 0.45,
  hazeGlow: '96,112,150', hazeMid: 0.35,
  smoke: '160,164,192', smokeAlpha: 0.28,
  grainDark: '48,52,72', grainLight: '142,152,186',
  rockEdge: 'rgba(112,124,160,0.45)',
  water: ['rgb(48,88,104)', 'rgb(26,60,92)', 'rgb(12,38,70)',
          'rgb(9,30,58)', 'rgb(20,58,86)', 'rgb(44,86,104)'],
  ripple: 'rgba(178,200,235,1)',
  glitter: ['rgba(214,230,255,0.22)', 'rgba(200,220,255,0.08)', 'rgba(190,210,255,0)'],
  spark: 'rgba(228,238,255,1)',
  foam: 'rgba(198,215,240,1)', foamAlpha: 0.7,
  vignette: 'rgba(2,6,14,0.48)',
};

// ---------------------------------------------------------------- factory

export function create(variant = 'day') {
  const night = variant === 'night';
  const P = night ? NIGHT : DAY;

  function buildSky(W, H, rand) {
    const c = makeCanvas(W, H * SKY_BAND), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H * HORIZON);
    grad.addColorStop(0.00, rgba(P.SKY_TOP, 1));
    grad.addColorStop(0.42, rgba(P.SKY_MID, 1));
    grad.addColorStop(0.80, rgba(P.SKY_LOW, 1));
    grad.addColorStop(1.00, rgba(P.SKY_HAZE, 1));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H * HORIZON + 2);

    if (night) {
      // hvezdy jen nad horizontem; u obzoru je "opar", tak ridnou
      const stars = 170;
      for (let i = 0; i < stars; i++) {
        const sx0 = rand() * W;
        const sy0 = rand() * H * (HORIZON - 0.03) * Math.pow(rand(), 0.6);
        const rr = H * 0.0011 * (0.5 + rand());
        g.globalAlpha = 0.25 + rand() * 0.65;
        g.fillStyle = '#e8efff';
        g.beginPath();
        g.arc(sx0, sy0, rr, 0, Math.PI * 2);
        g.fill();
      }
      g.globalAlpha = 1;
    }

    const sx = W * 0.74, sy = H * 0.155;
    if (night) {
      // mesic: chladna zare + kotouc se srpkovym stinem
      const mr = H * 0.20;
      const glow = g.createRadialGradient(sx, sy, 0, sx, sy, mr);
      glow.addColorStop(0.00, 'rgba(222,232,255,0.85)');
      glow.addColorStop(0.12, 'rgba(206,220,255,0.40)');
      glow.addColorStop(0.50, 'rgba(190,208,255,0.12)');
      glow.addColorStop(1.00, 'rgba(190,208,255,0)');
      g.fillStyle = glow;
      g.beginPath();
      g.arc(sx, sy, mr, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = 'rgba(240,245,255,0.96)';
      g.beginPath();
      g.arc(sx, sy, H * 0.024, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = rgba(P.SKY_MID, 0.9);
      g.beginPath();
      g.arc(sx - H * 0.011, sy - H * 0.006, H * 0.020, 0, Math.PI * 2);
      g.fill();
    } else {
      const sr = H * 0.30;
      const glow = g.createRadialGradient(sx, sy, 0, sx, sy, sr);
      glow.addColorStop(0.00, 'rgba(255,250,226,0.95)');
      glow.addColorStop(0.10, 'rgba(255,244,206,0.55)');
      glow.addColorStop(0.45, 'rgba(255,236,196,0.18)');
      glow.addColorStop(1.00, 'rgba(255,236,196,0)');
      g.fillStyle = glow;
      g.beginPath();
      g.arc(sx, sy, sr, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = 'rgba(255,253,240,0.9)';
      g.beginPath();
      g.arc(sx, sy, H * 0.028, 0, Math.PI * 2);
      g.fill();
    }
    g.fillStyle = rgba(mix(P.SKY_HAZE, P.SAND_FAR, 0.6), 1);
    g.fillRect(0, H * HORIZON, W, H * SKY_BAND);
    return { canvas: c, sunX: sx, sunY: sy };
  }

  function buildClouds(W, H, rand, opts) {
    const y0 = Math.round(H * opts.band[0]);
    const c = makeCanvas(W, H * (opts.band[1] - opts.band[0])), g = c.getContext('2d');
    g.translate(0, -y0);
    const n = opts.count;
    const alpha = opts.alpha * P.cloudAlpha;
    for (let i = 0; i < n; i++) {
      const cx = rand() * W;
      const cy = H * (opts.y0 + rand() * (opts.y1 - opts.y0));
      const cw = H * opts.size * (0.6 + rand() * 0.9);
      const ch = cw * (opts.flat ? 0.14 : 0.30) * (0.7 + rand() * 0.6);
      const puffs = opts.flat ? 5 : 9;
      const seeds = [];
      for (let j = 0; j < puffs; j++) {
        const u = j / (puffs - 1) - 0.5;
        const bulge = Math.cos(u * Math.PI) * 0.9 + 0.1;
        seeds.push([u * cw * (0.9 + rand() * 0.3), -ch * bulge * (0.4 + rand() * 0.5),
                    ch * (0.55 + bulge * 0.7) * (0.8 + rand() * 0.4)]);
      }
      const reps = [0];
      if (cx > W - cw) reps.push(-W);
      if (cx < cw) reps.push(W);
      for (let r = 0; r < reps.length; r++) {
        for (let j = 0; j < puffs; j++) {
          const px = cx + reps[r] + seeds[j][0];
          const py = cy + seeds[j][1];
          const pr = seeds[j][2];
          const gr = g.createRadialGradient(px, py - pr * 0.2, pr * 0.1, px, py, pr);
          gr.addColorStop(0, rgba(P.cloud, alpha));
          gr.addColorStop(0.55, rgba(P.cloudMid, alpha * 0.55));
          gr.addColorStop(1, rgba(P.cloudMid, 0));
          g.fillStyle = gr;
          g.beginPath();
          g.arc(px, py, pr, 0, Math.PI * 2);
          g.fill();
        }
      }
    }
    return { canvas: c, y0: y0 };
  }

  function buildLand(W, H, rand) {
    const y0 = Math.round(H * LAND_BAND[0]);
    const c = makeCanvas(W, H * (LAND_BAND[1] - LAND_BAND[0])), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;

    // Two hazy mountain ridges plus a volcano.
    const ridges = [
      { w: waveFn(rand, 4, 3.1 / W, 0.55), h: H * 0.115, base: H * (HORIZON + 0.012), col: P.RIDGE_FAR, haze: 0.42 },
      { w: waveFn(rand, 5, 5.3 / W, 0.52), h: H * 0.075, base: H * (HORIZON + 0.030), col: P.RIDGE_NEAR, haze: 0.20 }
    ];
    for (let i = 0; i < ridges.length; i++) {
      const R = ridges[i];
      g.beginPath();
      g.moveTo(0, R.base);
      for (x = 0; x <= W; x += 3) {
        const n = 1 - Math.abs(R.w(x));
        g.lineTo(x, R.base - R.h * (0.25 + 0.75 * n * n));
      }
      g.lineTo(W, R.base);
      g.closePath();
      g.fillStyle = rgba(mix(R.col, P.SKY_HAZE, R.haze), 1);
      g.fill();
    }

    const vx = W * 0.185, vb = H * (HORIZON + 0.028), vh = H * 0.165, vw = H * 0.20;
    g.beginPath();
    g.moveTo(vx - vw, vb);
    g.lineTo(vx - vw * 0.16, vb - vh);
    g.lineTo(vx + vw * 0.18, vb - vh * 0.97);
    g.lineTo(vx + vw, vb);
    g.closePath();
    g.fillStyle = rgba(mix(P.VOLCANO, P.SKY_HAZE, 0.32), 1);
    g.fill();
    g.beginPath();
    g.moveTo(vx - vw * 0.16, vb - vh);
    g.lineTo(vx + vw * 0.18, vb - vh * 0.97);
    g.lineTo(vx + vw * 0.55, vb);
    g.lineTo(vx + vw * 0.05, vb);
    g.closePath();
    g.fillStyle = rgba(mix(P.VOLCANO, [20, 24, 30], 0.25), 0.35);
    g.fill();
    const sm = g.createRadialGradient(vx, vb - vh * 1.25, 0, vx, vb - vh * 1.25, H * 0.11);
    sm.addColorStop(0, 'rgba(' + P.smoke + ',' + P.smokeAlpha + ')');
    sm.addColorStop(1, 'rgba(' + P.smoke + ',0)');
    g.fillStyle = sm;
    g.beginPath();
    g.arc(vx, vb - vh * 1.25, H * 0.11, 0, Math.PI * 2);
    g.fill();

    // Haze band along the horizon.
    const hz = g.createLinearGradient(0, H * (HORIZON - 0.03), 0, H * (HORIZON + 0.075));
    hz.addColorStop(0, 'rgba(' + P.hazeGlow + ',0)');
    hz.addColorStop(0.45, 'rgba(' + P.hazeGlow + ',' + P.hazeMid + ')');
    hz.addColorStop(1, 'rgba(' + P.hazeGlow + ',0)');
    g.fillStyle = hz;
    g.fillRect(0, H * (HORIZON - 0.03), W, H * 0.105);

    // Forest: four depth bands, the far ones washed out by haze.
    const bands = [
      { top: FOREST_TOP + 0.020, base: FOREST_BASE - 0.052, h: 0.062, haze: 0.55, dens: 0.028 },
      { top: FOREST_TOP + 0.008, base: FOREST_BASE - 0.032, h: 0.080, haze: 0.34, dens: 0.034 },
      { top: FOREST_TOP - 0.004, base: FOREST_BASE - 0.012, h: 0.098, haze: 0.16, dens: 0.040 },
      { top: FOREST_TOP - 0.018, base: FOREST_BASE, h: 0.118, haze: 0.00, dens: 0.048 }
    ];
    for (let i = 0; i < bands.length; i++) {
      const B = bands[i];
      const col = rgba(mix(P.FOREST_BANDS[i], P.SKY_HAZE, B.haze), 1);
      const baseY = H * B.base;
      const ug = g.createLinearGradient(0, baseY - H * 0.020, 0, baseY + H * 0.010);
      ug.addColorStop(0, rgba(mix(P.FOREST_BANDS[i], P.SKY_HAZE, B.haze), 0));
      ug.addColorStop(0.55, col);
      ug.addColorStop(1, col);
      g.fillStyle = ug;
      g.fillRect(0, baseY - H * 0.020, W, H * 0.030);
      g.fillStyle = col;
      const step = W * B.dens;
      for (x = -step; x < W + step; x += step * (0.55 + rand() * 0.55)) {
        const th = H * B.h * (0.72 + rand() * 0.62);
        const tw = th * (0.26 + rand() * 0.12);
        const by = baseY + H * 0.004 * (rand() - 0.5);
        if (rand() < 0.30) drawAraucaria(g, x, by, th, tw, col, rand);
        else drawFir(g, x, by, th, tw, col, rand);
      }
    }

    // Far shore: sand strip with cycads.
    const fs = g.createLinearGradient(0, H * FAR_SAND_TOP, 0, H * (WATER_TOP + 0.005));
    fs.addColorStop(0, rgba(mix(P.SAND_FAR, P.SKY_HAZE, 0.25), 1));
    fs.addColorStop(1, rgba(mix(P.SAND_FAR, [180, 160, 128], 0.35), 1));
    g.fillStyle = fs;
    const sw = waveFn(rand, 3, 4.7 / W, 0.5);
    g.beginPath();
    g.moveTo(0, H * FAR_SAND_TOP);
    for (x = 0; x <= W; x += 4) {
      g.lineTo(x, H * WATER_TOP + H * 0.005 * (1.05 + sw(x)));
    }
    g.lineTo(W, H * FAR_SAND_TOP);
    g.closePath();
    g.fill();

    const cyc = Math.round(W / H * 7);
    for (let i = 0; i < cyc; i++) {
      const cxp = rand() * W;
      drawCycad(g, cxp, H * (FAR_SAND_TOP + 0.012 + rand() * 0.014),
                H * (0.030 + rand() * 0.016), rgba(mix(P.FOREST_BANDS[3], P.SKY_HAZE, 0.10), 1));
    }
    // Tiny fern tufts at the very top of the far sand strip: their base lies
    // above the far walking band (y0 = 0.525), so walkers there pass in front
    // of them — plants read as one depth further away.
    const tufts = Math.round(W / H * 9);
    for (let i = 0; i < tufts; i++) {
      fernClump(g, H, rand() * W, H * (0.516 + rand() * 0.008),
                H * (0.011 + rand() * 0.007), rand);
    }
    return { canvas: c, y0: y0 };
  }

  // A spit of land reaching into the lagoon and a small island: without them
  // the scene reads as flat horizontal stripes. Vraci polohu ostrova, at
  // buildIslandTrees muze jeho stromy prekreslit do popredi (bod 4).
  function drawHeadland(g, W, H, rand) {
    let x;
    const top = H * 0.556, tipX = W * 0.300, tipY = H * 0.612;
    const w1 = waveFn(rand, 3, 9.0 / W, 0.5);
    const grass = rgba(mix(P.FOREST_BANDS[2], P.SKY_HAZE, 0.12), 1);

    g.beginPath();
    g.moveTo(0, H * 0.552);
    for (x = 0; x <= tipX; x += 4) {
      const f = x / tipX;
      g.lineTo(x, lerp(top, tipY, Math.pow(f, 1.9)) + H * 0.007 * w1(x));
    }
    for (x = tipX; x >= 0; x -= 4) {
      const f2 = x / tipX;
      g.lineTo(x, lerp(H * 0.641, tipY, Math.pow(f2, 0.6)) + H * 0.003 * w1(x + 500));
    }
    g.closePath();
    const hg = g.createLinearGradient(0, H * 0.556, 0, H * 0.645);
    hg.addColorStop(0, grass);
    hg.addColorStop(0.55, rgba(mix(P.SAND_FAR, [170, 150, 118], 0.3), 1));
    hg.addColorStop(1, rgba(mix(P.SAND_WET, [120, 104, 80], 0.3), 1));
    g.fillStyle = hg;
    g.fill();

    g.save();
    g.clip();
    g.fillStyle = grass;
    g.beginPath();
    g.moveTo(-10, H * 0.58);
    for (x = 0; x <= tipX; x += 4) {
      g.lineTo(x, lerp(top, tipY, Math.pow(x / tipX, 1.9)) + H * (0.030 - 0.018 * x / tipX)
                  + H * 0.006 * w1(x + 90));
    }
    g.lineTo(tipX, 0); g.lineTo(-10, 0);
    g.closePath();
    g.fill();
    g.restore();

    for (let i = 0; i < 18; i++) {
      const tx = Math.pow(rand(), 1.2) * tipX * 0.92;
      const f3 = tx / tipX;
      const ty = lerp(top, tipY, Math.pow(f3, 1.9)) + H * (0.014 - 0.007 * f3);
      const th = H * (0.072 - f3 * 0.036) * (0.8 + rand() * 0.5);
      const col = rgba(mix(P.FOREST_BANDS[3], P.SKY_HAZE, 0.05), 1);
      if (rand() < 0.45) drawAraucaria(g, tx, ty, th, th * 0.30, col, rand);
      else drawFir(g, tx, ty, th, th * 0.32, col, rand);
    }

    const ix = W * 0.660, iy = H * 0.624, iw = W * 0.038, ih = H * 0.010;
    g.beginPath();
    g.ellipse(ix, iy, iw, ih, 0, 0, Math.PI * 2);
    g.fillStyle = rgba(mix(P.SAND_FAR, [176, 156, 122], 0.25), 1);
    g.fill();
    g.beginPath();
    g.ellipse(ix, iy - ih * 0.5, iw * 0.72, ih * 0.7, 0, 0, Math.PI * 2);
    g.fillStyle = rgba(mix(P.FOREST_BANDS[2], P.SKY_HAZE, 0.10), 1);
    g.fill();
    // Stromy ostrova se NEKRESLI sem: leží na výšce zadní chodecké dráhy
    // (shoreFar, y 0.532/0.558), takže musí zakrývat chodce před sebou —
    // to umí jen horní plátno nad 3D tvory. Kreslí je buildIslandTrees.
    // Nízké písčité tělo ostrova (iy±ih) zůstává tady: leží nad vodní čarou
    // (voda začíná až 0.645), plavce tedy nikdy nezakryje.
    return { ix, iy, iw, ih };
  }

  function buildShore(W, H, rand) {
    const y0 = Math.round(H * SHORE_BAND[0]);
    const c = makeCanvas(W, H * (SHORE_BAND[1] - SHORE_BAND[0])), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;
    const edge = waveFn(rand, 3, 5.1 / W, 0.5);

    const island = drawHeadland(g, W, H, rand);

    // Wet sand, then dry sand, then the rocky foreground shelf.
    const wg = g.createLinearGradient(0, H * WATER_BOT, 0, H * WET_SAND_BOT);
    wg.addColorStop(0, rgba(mix(P.SAND_WET, [120, 104, 80], 0.35), 1));
    wg.addColorStop(0.45, rgba(P.SAND_WET, 1));
    wg.addColorStop(1, rgba(mix(P.SAND_WET, P.SAND_NEAR, 0.85), 1));
    g.fillStyle = wg;
    g.beginPath();
    g.moveTo(0, H * (WET_SAND_BOT + 0.02));
    for (x = 0; x <= W; x += 4) g.lineTo(x, H * WATER_BOT + shoreEdge(edge, x, H));
    g.lineTo(W, H * (WET_SAND_BOT + 0.02));
    g.closePath();
    g.fill();

    const dg = g.createLinearGradient(0, H * WET_SAND_BOT, 0, H);
    dg.addColorStop(0, rgba(P.SAND_NEAR, 1));
    dg.addColorStop(0.55, rgba(mix(P.SAND_NEAR, [214, 190, 148], night ? 0.2 : 0.5), 1));
    dg.addColorStop(1, rgba(night ? [78, 82, 102] : [196, 172, 134], 1));
    g.fillStyle = dg;
    g.fillRect(0, H * WET_SAND_BOT - 1, W, H - H * WET_SAND_BOT + 1);

    // Sand grain / pebbles, denser and bigger towards the viewer.
    for (let i = 0; i < 2600; i++) {
      const t = rand();
      const yy = H * lerp(WATER_BOT + 0.01, 1.0, Math.pow(t, 0.7));
      const xx = rand() * W;
      const s = H * 0.0009 * (0.5 + Math.pow(t, 1.6) * 4.5);
      const dark = rand() < 0.5;
      g.fillStyle = dark ? 'rgba(' + P.grainDark + ',0.35)' : 'rgba(' + P.grainLight + ',0.45)';
      g.beginPath();
      g.ellipse(xx, yy, s * (1 + rand()), s * 0.7, 0, 0, Math.PI * 2);
      g.fill();
    }

    // Rocky shelf across the very bottom.
    const rockTop = waveFn(rand, 4, 6.3 / W, 0.55);
    g.beginPath();
    g.moveTo(0, H);
    for (x = 0; x <= W; x += 4) {
      g.lineTo(x, H * (SAND_BOT + 0.055) + H * 0.030 * rockTop(x));
    }
    g.lineTo(W, H);
    g.closePath();
    const rg = g.createLinearGradient(0, H * SAND_BOT, 0, H);
    rg.addColorStop(0, rgba(P.ROCK_LIT, 1));
    rg.addColorStop(0.35, rgba(P.ROCK, 1));
    rg.addColorStop(1, rgba(mix(P.ROCK, [20, 18, 16], 0.55), 1));
    g.fillStyle = rg;
    g.fill();

    // Faceted slabs give the shelf a rock reading instead of a mud reading.
    g.save();
    g.clip();
    for (let i = 0; i < 34; i++) {
      const sx0 = rand() * W;
      const sy0 = H * (SAND_BOT + 0.04 + rand() * 0.09);
      const sw0 = W * (0.03 + rand() * 0.09);
      const sh0 = H * (0.015 + rand() * 0.045);
      g.beginPath();
      g.moveTo(sx0, sy0);
      g.lineTo(sx0 + sw0 * (0.4 + rand() * 0.5), sy0 - sh0 * (0.5 + rand() * 0.6));
      g.lineTo(sx0 + sw0, sy0 + sh0 * (rand() - 0.3));
      g.lineTo(sx0 + sw0 * 0.55, sy0 + sh0);
      g.closePath();
      g.fillStyle = rand() < 0.5
        ? rgba(P.ROCK_LIT, 0.10 + rand() * 0.16)
        : rgba([26, 22, 20], 0.10 + rand() * 0.18);
      g.fill();
      g.strokeStyle = 'rgba(20,16,14,0.22)';
      g.lineWidth = Math.max(1, H * 0.0012);
      g.stroke();
    }
    g.restore();

    g.beginPath();
    for (x = 0; x <= W; x += 4) {
      const ry = H * (SAND_BOT + 0.055) + H * 0.030 * rockTop(x);
      if (x === 0) g.moveTo(x, ry); else g.lineTo(x, ry);
    }
    g.strokeStyle = P.rockEdge;
    g.lineWidth = Math.max(1, H * 0.0018);
    g.stroke();

    // Boulders, kept to the sides so the middle stays walkable.
    const boulders = Math.round(W / H * 6);
    for (let i = 0; i < boulders; i++) {
      const side = i % 2 === 0 ? rand() * 0.30 : 0.70 + rand() * 0.30;
      const bx = W * side;
      const by = H * (SAND_BOT + 0.01 + rand() * 0.07);
      const bw = H * (0.030 + rand() * 0.055);
      const bh = bw * (0.55 + rand() * 0.5);
      const wob = waveFn(rand, 3, 1.2, 0.5);
      g.beginPath();
      for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.22) {
        const rr = 1 + 0.16 * wob(a * 3);
        g.lineTo(bx + Math.cos(a) * bw * rr, by + Math.sin(a) * bh * rr);
      }
      g.closePath();
      g.fillStyle = rgba(mix(P.ROCK, [30, 28, 26], rand() * 0.4), 1);
      g.fill();
      g.beginPath();
      g.ellipse(bx - bw * 0.18, by - bh * 0.42, bw * 0.55, bh * 0.30, -0.3, 0, Math.PI * 2);
      g.fillStyle = rgba(P.ROCK_LIT, 0.45);
      g.fill();
    }

    // Mid-depth fern tufts at the waterline: base sits just above the near
    // walking band (y0 = 0.80), so every walker passes in front of them.
    const tufts = Math.round(W / H * 5);
    for (let i = 0; i < tufts; i++) {
      fernClump(g, H, rand() * W, H * (0.786 + rand() * 0.012),
                H * (0.032 + rand() * 0.022), rand);
    }
    return { canvas: c, edge: edge, y0: y0, island: island };
  }

  // Stromy ostrova (bod 4): kreslí se zvětšené do vlastního plátna, které
  // drawFront pak vrství NAD 3D tvory — jinak by chodec na zadní dráze
  // (shoreFar) šel před nimi, i když má zajít za ně. Sám ostrov (písek,
  // tráva) zůstává v buildShore — leží nad vodní čarou, takže plavce
  // v laguně zakrýt nemůže, jen koruny stromů to potřebují.
  function buildIslandTrees(W, H, rand, island) {
    const GROW = 1.4;
    const y0 = Math.round(island.iy - H * 0.10);
    const c = makeCanvas(W, island.iy + H * 0.02 - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const col = rgba(mix(P.FOREST_BANDS[3], P.SKY_HAZE, 0.05), 1);
    drawAraucaria(g, island.ix - island.iw * 0.2, island.iy - island.ih * 0.3,
                  H * 0.062 * GROW, H * 0.019 * GROW, col, rand);
    drawFir(g, island.ix + island.iw * 0.35, island.iy,
            H * 0.045 * GROW, H * 0.015 * GROW, col, rand);
    return { canvas: c, y0: y0 };
  }

  function fernClump(g, H, fx, fy, scale, rand) {
    const fronds = 6 + Math.floor(rand() * 4);
    for (let k = 0; k < fronds; k++) {
      const spread = (k / (fronds - 1) - 0.5) * 2;
      const ang = -Math.PI / 2 + spread * 0.85;
      const bend = spread * 0.85 + (rand() - 0.5) * 0.3;
      const col = rgba(mix(P.FERN_DARK, P.FERN_MID, rand() * 0.8), 1);
      drawFrond(g, fx, fy, scale * (0.75 + rand() * 0.5), ang, bend, col);
    }
    for (let b = 0; b < 5; b++) {
      const bl = (rand() - 0.5) * scale * 1.2;
      g.strokeStyle = rgba(P.FERN_MID, 0.7);
      g.lineWidth = Math.max(1, H * 0.002);
      g.beginPath();
      g.moveTo(fx + bl, fy);
      g.quadraticCurveTo(fx + bl * 1.4, fy - scale * 0.7, fx + bl * 2.2, fy - scale * 1.1);
      g.stroke();
    }
  }

  // Fern clumps hugging the bottom corners, in front of every creature —
  // drawn by drawFront into the top canvas.
  function buildFrontFerns(W, H, rand) {
    const y0 = Math.round(H * 0.70);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const clumps = Math.round(W / H * 5);
    for (let i = 0; i < clumps; i++) {
      const pos = i / Math.max(1, clumps - 1);
      const fx = W * (pos < 0.5 ? pos * 0.42 + rand() * 0.06 : 0.60 + (pos - 0.5) * 0.80 + rand() * 0.06);
      fernClump(g, H, fx, H * (0.965 + rand() * 0.05), H * (0.10 + rand() * 0.075), rand);
    }
    return { canvas: c, y0: y0 };
  }

  // -------------------------------------------------------------- runtime

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const sky = buildSky(W, H, rand);
    const far = buildClouds(W, H, rand, { count: 8, y0: 0.05, y1: 0.15, size: 0.11, alpha: 0.30, flat: true, band: [0, 0.23] });
    const near = buildClouds(W, H, rand, { count: 6, y0: 0.13, y1: 0.29, size: 0.17, alpha: 0.62, flat: false, band: [0.02, 0.37] });
    const land = buildLand(W, H, rand);
    const shore = buildShore(W, H, rand);
    const islandTrees = buildIslandTrees(W, H, rand, shore.island);
    const front = buildFrontFerns(W, H, rand);

    const ripples = [];
    const nRip = 150;
    for (let i = 0; i < nRip; i++) {
      ripples.push({
        p: rand(),
        cx: rand(),
        w: 0.025 + rand() * 0.085,
        len: 0.02 + rand() * 0.05,
        ph: rand() * Math.PI * 2,
        sp: 0.6 + rand() * 0.8,
        a: 0.25 + rand() * 0.55
      });
    }
    const sparks = [];
    for (let i = 0; i < 130; i++) {
      sparks.push({
        u: (rand() - 0.5),
        v: rand(),
        r: 0.4 + rand() * 1.6,
        ph: rand() * Math.PI * 2,
        sp: 0.7 + rand() * 2.2
      });
    }
    const blades = [];
    for (let i = 0; i < 22; i++) {
      blades.push({
        x: rand(),
        y: 0.93 + rand() * 0.07,
        h: 0.05 + rand() * 0.075,
        lean: (rand() - 0.5) * 0.8,
        ph: rand() * Math.PI * 2,
        sp: 0.5 + rand() * 0.6
      });
    }

    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.5, H * 0.52, H * 0.38, W * 0.5, H * 0.52, H * 0.95);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, P.vignette);
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);

    return {
      W: W, H: H, sky: sky, vig: vig, cloudFar: far, cloudNear: near, land: land,
      shore: shore.canvas, shoreY0: shore.y0, front: front, islandTrees: islandTrees,
      shoreEdge: function (x) { return shoreEdge(shore.edge, x, H); },
      ripples: ripples, sparks: sparks, blades: blades, waterGrad: null
    };
  }

  function waterGradient(ctx, H) {
    const g = ctx.createLinearGradient(0, H * WATER_TOP, 0, H * WATER_BOT);
    g.addColorStop(0.00, P.water[0]);
    g.addColorStop(0.09, P.water[1]);
    g.addColorStop(0.30, P.water[2]);
    g.addColorStop(0.58, P.water[3]);
    g.addColorStop(0.82, P.water[4]);
    g.addColorStop(1.00, P.water[5]);
    return g;
  }

  function drawWater(ctx, W, H, t, S) {
    const top = H * WATER_TOP, bot = H * WATER_BOT, hh = bot - top;
    if (!S.waterGrad) S.waterGrad = waterGradient(ctx, H);
    ctx.fillStyle = S.waterGrad;
    ctx.fillRect(0, top - 1, W, hh + H * 0.025);

    // Reflection of the far shore, sliced and wobbled.
    const refH = hh * 0.16, slices = 20;
    ctx.save();
    ctx.globalAlpha = 0.26;
    for (let i = 0; i < slices; i++) {
      const f = i / slices;
      const sh = refH / slices;
      const srcY = H * WATER_TOP - (f + 1 / slices) * refH;
      const dstY = top + f * sh;
      const dx = Math.sin(t * 0.55 + f * 5.5) * W * 0.0035 * (0.3 + f);
      ctx.globalAlpha = 0.30 * (1 - f * 0.85);
      ctx.drawImage(S.land.canvas, 0, srcY - S.land.y0, W, sh, dx, dstY, W, sh + 1);
    }
    ctx.restore();

    // Scattered ripple crests drifting slowly towards the viewer.
    ctx.save();
    ctx.lineCap = 'round';
    for (let i = 0; i < S.ripples.length; i++) {
      const R = S.ripples[i];
      const p = (R.p + t * 0.010 * R.sp) % 1;
      const yf = Math.pow(p, 1.6);
      const y = top + yf * hh;
      const fade = Math.pow(Math.sin(Math.PI * p), 0.5);
      const persp = 0.14 + 0.86 * yf;
      const half = W * R.w * persp;
      const cx = (R.cx + p * 0.03) % 1 * (W + 2 * half) - half;
      ctx.globalAlpha = R.a * fade * 0.42;
      ctx.strokeStyle = P.ripple;
      ctx.lineWidth = Math.max(0.7, H * 0.0022 * persp);
      ctx.beginPath();
      const wl = W * R.len * persp + 1;
      const amp = H * 0.0026 * persp;
      const steps = 14;
      for (let k = 0; k <= steps; k++) {
        const x = cx - half + (2 * half) * (k / steps);
        const taper = Math.sin(Math.PI * k / steps);
        const yy = y + Math.sin(x / wl + R.ph + t * 0.55 * R.sp) * amp * taper;
        if (k === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    }
    ctx.restore();

    // Sun (or moon) glitter path under the light source.
    ctx.save();
    const gx = S.sky.sunX;
    const col = ctx.createRadialGradient(gx, top, 0, gx, top, hh * 1.5);
    col.addColorStop(0, P.glitter[0]);
    col.addColorStop(0.45, P.glitter[1]);
    col.addColorStop(1, P.glitter[2]);
    ctx.fillStyle = col;
    ctx.fillRect(0, top, W, hh);
    for (let i = 0; i < S.sparks.length; i++) {
      const K = S.sparks[i];
      const v = K.v;
      const sy = top + Math.pow(v, 1.3) * hh;
      const spread = W * (0.035 + 0.13 * Math.pow(v, 1.3));
      const sx = gx + K.u * 2 * spread;
      let a = Math.sin(t * K.sp + K.ph);
      if (a <= 0) continue;
      a = Math.pow(a, 4) * 0.8;
      const rr = H * 0.0016 * K.r * (0.35 + v);
      ctx.globalAlpha = a;
      ctx.fillStyle = P.spark;
      ctx.beginPath();
      ctx.ellipse(sx, sy, rr * 2.6, rr * 0.7, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    // Foam at both shorelines.
    ctx.save();
    ctx.lineCap = 'round';
    const lines = [
      { base: 0, amp: H * 0.0016, w: W * 0.05, a: 0.30, sp: 0.5, wide: false },
      { base: 1, amp: H * 0.0035, w: W * 0.13, a: 0.80, sp: 0.32, wide: true },
      { base: 1, off: -H * 0.014, amp: H * 0.003, w: W * 0.085, a: 0.28, sp: 0.45, wide: false }
    ];
    for (let i = 0; i < lines.length; i++) {
      const L = lines[i];
      ctx.globalAlpha = L.a * P.foamAlpha * (0.75 + 0.25 * Math.sin(t * 0.4 + i));
      ctx.strokeStyle = P.foam;
      ctx.lineWidth = Math.max(1, H * 0.0022 * (L.wide ? 2.0 : 1));
      ctx.beginPath();
      for (let xx = 0; xx <= W; xx += 6) {
        const by = L.base ? bot + S.shoreEdge(xx) + (L.off || 0) : top;
        const yv = by + Math.sin(xx / L.w + t * L.sp) * L.amp
                      + Math.sin(xx / (L.w * 0.37) - t * L.sp * 1.7) * L.amp * 0.45;
        if (xx === 0) ctx.moveTo(xx, yv); else ctx.lineTo(xx, yv);
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawBlades(ctx, W, H, t, S) {
    ctx.save();
    ctx.lineCap = 'round';
    for (let i = 0; i < S.blades.length; i++) {
      const B = S.blades[i];
      const x = B.x * W, y = B.y * H, h = B.h * H;
      const sway = Math.sin(t * B.sp + B.ph) * 0.10 + B.lean * 0.25;
      ctx.strokeStyle = i % 3 === 0 ? rgba(P.FERN_MID, 0.85) : rgba(P.FERN_DARK, 0.9);
      ctx.lineWidth = Math.max(1, H * 0.0022);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(x + h * sway * 0.6, y - h * 0.6,
                           x + h * (sway + B.lean * 0.4), y - h);
      ctx.stroke();
    }
    ctx.restore();
  }

  function draw(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;

    ctx.drawImage(S.sky.canvas, 0, 0);

    const o1 = (t * W * 0.0016) % W;
    ctx.drawImage(S.cloudFar.canvas, -o1, S.cloudFar.y0);
    ctx.drawImage(S.cloudFar.canvas, W - o1, S.cloudFar.y0);
    const o2 = (t * W * 0.0034) % W;
    ctx.drawImage(S.cloudNear.canvas, -o2, S.cloudNear.y0);
    ctx.drawImage(S.cloudNear.canvas, W - o2, S.cloudNear.y0);

    ctx.drawImage(S.land.canvas, 0, S.land.y0);
    drawWater(ctx, W, H, t, S);
    ctx.drawImage(S.shore, 0, S.shoreY0);
  }

  function drawFront(ctx, W, H, t) {
    // Rostliny lezi ve trech hloubkach: trsy u vzdaleneho brehu a u vodni cary
    // se kresli do spodniho platna (draw), takze tvorove chodi PRED nimi, a
    // rohove kapradi s travou a vinetaci sem, do platna NAD 3D tvory —
    // dinosaurus tak stoji v zeleni, ne nad ni. Stromy ostrova v lagune (bod 4)
    // patri sem ze stejneho duvodu: lezi ve vysce zadni chodecke drahy, takze
    // musi zakryvat chodce pred sebou, ne byt zakryvany.
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    ctx.drawImage(state.islandTrees.canvas, 0, state.islandTrees.y0);
    ctx.drawImage(state.front.canvas, 0, state.front.y0);
    drawBlades(ctx, W, H, t, state);
    ctx.drawImage(state.vig, 0, 0);
  }

  return {
    draw,
    drawFront,
    // odkud sviti slunce/mesic na obloze, at ho 3D vrstva muze napodobit
    sun: { x: 0.74, y: 0.155 },
    depthScale,
  };
}
