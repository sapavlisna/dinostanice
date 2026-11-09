/* Betlém — malovaná noční krajina pro 2D plátno pod 3D tvory.

   ES modul s továrnou `create()`; vrací `{draw, drawFront, sun, depthScale}`
   stejně jako forest.js, takže scéna jen vymění cestu v render.js.

   Rozvržení (podíl výšky plátna):
     0,00–0,44  hvězdná obloha, Betlémská hvězda s ohonem a paprskem, měsíc
     0,30–0,46  kopce a město Betlém vlevo, cypřiše a palmy vpravo
     0,44–0,66  step za chlévkem: ohniště pastýřů a ovčí ohrada vlevo,
                chlévek se skalou a jesličkami vpravo (podlaha na 0,665)
     0,69–0,80  střední dráhy — chodí se tu před chlévkem (0,715 / 0,775)
     0,84–0,95  přední dráhy (0,855 / 0,915)
     od 0,96    kameny a tráva v rozích, kreslí se NAD tvory (drawFront)
   Cesta se vine z popředí vlevo k chlévku; trasy v render.js ji sledují
   přes `trailX()`. Svatá rodina a pastýři jsou jen malované postavy. */

const SEED = 20261224;

const HORIZON = 0.44;
const DEPTH_MIN = 0.35;
const DEPTH_SKY_TOP = 0.30;

// chlévek: střed (podíl šířky), podlaha (podíl výšky), velikost v násobcích H
export const STABLE = { x: 0.645, floor: 0.665, u: 0.60 };
// hvězda nad chlévkem a ohniště pastýřů
const STAR = { x: 0.575, y: 0.125 };
const FIRE = { x: 0.215, y: 0.595 };

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
function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
function mix(a, b, k) {
  return [Math.round(lerp(a[0], b[0], k)), Math.round(lerp(a[1], b[1], k)),
          Math.round(lerp(a[2], b[2], k))];
}

function waveFn(rand, octaves, baseFreq, persistence) {
  const parts = []; let f = baseFreq, a = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    parts.push([f, a, rand() * Math.PI * 2]);
    norm += a; f *= 2.07; a *= persistence;
  }
  return function (x) {
    let s = 0;
    for (let j = 0; j < parts.length; j++) s += parts[j][1] * Math.sin(x * parts[j][0] + parts[j][2]);
    return s / norm;
  };
}

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

function depthScale(yFrac) {
  const y = clamp(yFrac, 0, 1);
  if (y <= HORIZON) {
    const k = 1 - y / HORIZON;
    return DEPTH_MIN - (DEPTH_MIN - DEPTH_SKY_TOP) * k * k;
  }
  const u = (y - HORIZON) / (1 - HORIZON);
  return DEPTH_MIN + (1 - DEPTH_MIN) * Math.pow(u, 1.6);
}

// Cesta z popředí vlevo ke chlévku; trasy v scenes/betlem/render.js ji sledují.
export function trailX(yf) {
  const u = clamp((yf - 0.68) / 0.32, 0, 1.2);
  return 0.575 - 0.355 * Math.pow(u, 0.85) + 0.030 * Math.sin(u * 4.6) * u;
}
export function trailHalf(yf) {
  return 0.014 + 0.120 * Math.pow(clamp((yf - 0.68) / 0.32, 0, 1.2), 1.4);
}

const P = {
  SKY: [[5, 8, 30], [11, 20, 56], [28, 40, 92], [66, 70, 128], [128, 100, 136], [196, 134, 118]],
  HILL_FAR: [40, 46, 96], HILL_MID: [28, 34, 72], HILL_NEAR: [20, 26, 54],
  TOWN: [34, 40, 82], TOWN_LIT: [58, 66, 118],
  WARM: [255, 196, 110], WARM_HOT: [255, 230, 160],
  GROUND_FAR: [66, 70, 110], GROUND_MID: [64, 70, 92], GROUND_NEAR: [38, 46, 62],
  GRASS: [[44, 70, 78], [58, 86, 84], [36, 58, 66], [76, 96, 84]],
  PATH: [150, 134, 130], PATH_DARK: [104, 94, 100], PATH_LIGHT: [196, 170, 140],
  ROCK: [52, 56, 84], ROCK_LIT: [96, 104, 150],
  WOOD: [96, 66, 44], WOOD_DARK: [50, 34, 28], STRAW: [196, 156, 84], STRAW_DARK: [120, 90, 52],
  PALM: [14, 34, 52], PALM_LIT: [64, 100, 112],
  vignette: 'rgba(2,4,20,0.46)',
};

// ------------------------------------------------------------ pieces

function ellipse(g, x, y, rx, ry, col, rot) {
  g.fillStyle = col;
  g.beginPath(); g.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), rot || 0, 0, Math.PI * 2); g.fill();
}

function glow(g, x, y, r, col, a, sy) {
  g.save();
  g.translate(x, y);
  if (sy) g.scale(1, sy);
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, r);
  gr.addColorStop(0, rgba(col, a));
  gr.addColorStop(0.35, rgba(col, a * 0.45));
  gr.addColorStop(1, rgba(col, 0));
  g.fillStyle = gr;
  g.beginPath(); g.arc(0, 0, r, 0, Math.PI * 2); g.fill();
  g.restore();
}

function tuft(g, x, y, s, color, rand, blades) {
  g.strokeStyle = color;
  g.lineCap = 'round';
  g.lineWidth = Math.max(1, s * 0.09);
  const n = blades || 5;
  for (let i = 0; i < n; i++) {
    const sp = (i / (n - 1) - 0.5) * 2;
    g.beginPath();
    g.moveTo(x + sp * s * 0.18, y);
    g.quadraticCurveTo(x + sp * s * 0.45, y - s * 0.6, x + sp * s * (0.7 + rand() * 0.3), y - s * (0.75 + rand() * 0.45));
    g.stroke();
  }
}

function rock(g, x, y, w, rand, wob, lit) {
  const h = w * (0.5 + rand() * 0.25);
  g.fillStyle = 'rgba(4,8,24,0.45)';
  g.beginPath(); g.ellipse(x, y + h * 0.05, w * 1.05, h * 0.2, 0, 0, Math.PI * 2); g.fill();
  g.beginPath();
  for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.25) {
    const rr = 1 + 0.16 * wob(a * 3);
    const py = Math.sin(a);
    g.lineTo(x + Math.cos(a) * w * rr, y - h * 0.5 + py * h * 0.5 * rr * (py < 0 ? 1 : 0.7));
  }
  g.closePath();
  g.fillStyle = rgba(mix(P.ROCK, [14, 16, 36], rand() * 0.45), 1);
  g.fill();
  g.beginPath();
  g.ellipse(x - w * 0.18, y - h * 0.72, w * 0.5, h * 0.22, -0.25, 0, Math.PI * 2);
  g.fillStyle = rgba(lit || P.ROCK_LIT, 0.45);
  g.fill();
}

function bush(g, x, y, s, rand, col) {
  g.fillStyle = 'rgba(4,10,24,0.35)';
  g.beginPath(); g.ellipse(x, y + s * 0.02, s * 1.0, s * 0.16, 0, 0, Math.PI * 2); g.fill();
  for (let i = 0; i < 7; i++) {
    const u = (i / 6 - 0.5) * 2;
    const r = s * (0.40 + rand() * 0.2) * (1 - Math.abs(u) * 0.35);
    g.fillStyle = rgba(mix(col, [8, 16, 40], 0.25 + rand() * 0.2), 1);
    g.beginPath(); g.arc(x + u * s * 0.8, y - r * 0.55, r, 0, Math.PI * 2); g.fill();
  }
  for (let i = 0; i < 5; i++) {
    const u = (i / 4 - 0.5) * 2;
    const r = s * (0.26 + rand() * 0.12) * (1 - Math.abs(u) * 0.3);
    g.fillStyle = rgba(mix(col, [140, 170, 150], 0.18), 0.9);
    g.beginPath(); g.arc(x + u * s * 0.7 - r * 0.2, y - r * 0.95 - s * 0.14, r, 0, Math.PI * 2); g.fill();
  }
}

// Peřený list: zakřivená osa se zubatým okrajem, `droop` ho nechá víc svěsit.
function frond(g, topX, topY, a, L, col, rim, droop) {
  const ex = topX + Math.cos(a) * L, ey = topY + Math.sin(a) * L * 0.55 + L * (0.20 + 0.28 * Math.abs(Math.cos(a))) * droop;
  const mx = topX + Math.cos(a) * L * 0.55, my = topY + Math.sin(a) * L * 0.75 - L * 0.06 * droop;
  const up = [], dn = [];
  for (let k = 0; k <= 14; k++) {
    const t = k / 14;
    const bx = (1 - t) * (1 - t) * topX + 2 * (1 - t) * t * mx + t * t * ex;
    const by = (1 - t) * (1 - t) * topY + 2 * (1 - t) * t * my + t * t * ey;
    const w = L * 0.13 * Math.pow(Math.sin(Math.PI * Math.min(1, t * 1.05 + 0.02)), 0.7) * (k % 2 ? 1 : 0.55);
    up.push([bx, by - w]); dn.push([bx, by + w * 0.8]);
  }
  g.fillStyle = rgba(col, 1);
  g.beginPath();
  up.forEach((p, k) => (k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
  for (let k = dn.length - 1; k >= 0; k--) g.lineTo(dn[k][0], dn[k][1]);
  g.closePath();
  g.fill();
  if (rim) {
    g.strokeStyle = rgba(rim, 0.55);
    g.lineWidth = Math.max(1, L * 0.010);
    g.beginPath();
    up.forEach((p, k) => (k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
    g.stroke();
  }
}

// Datlová palma: štíhlý kmen s prstenci a koruna z peřených listů.
function palm(g, x, baseY, h, lean, rand, col, rim) {
  col = col || P.PALM;
  const topX = x + lean * h, topY = baseY - h;
  const cx = x + lean * h * 0.15, cy = baseY - h * 0.55;
  const w0 = h * 0.034, w1 = h * 0.020;
  g.fillStyle = rgba(mix(col, [40, 30, 36], 0.45), 1);
  g.beginPath();
  g.moveTo(x - w0, baseY);
  g.quadraticCurveTo(cx - w0, cy, topX - w1, topY);
  g.lineTo(topX + w1, topY);
  g.quadraticCurveTo(cx + w0, cy, x + w0, baseY);
  g.closePath();
  g.fill();
  g.strokeStyle = rgba(mix(col, [120, 90, 70], 0.5), 0.55);
  g.lineWidth = Math.max(1, h * 0.004);
  for (let i = 1; i < 16; i++) {
    const t = i / 16;
    const px = lerp(lerp(x, cx, t), lerp(cx, topX, t), t);
    const py = lerp(lerp(baseY, cy, t), lerp(cy, topY, t), t);
    const w = lerp(w0, w1, t);
    g.beginPath(); g.moveTo(px - w, py); g.lineTo(px + w * 0.9, py - h * 0.006); g.stroke();
  }
  const fr = 11;
  for (let i = 0; i < fr; i++) {
    const a = -Math.PI + (i + 0.5) / fr * Math.PI + (rand() - 0.5) * 0.18;
    frond(g, topX, topY, a, h * (0.30 + rand() * 0.10), mix(col, [4, 10, 24], rand() * 0.3), rim, 1);
  }
  ellipse(g, topX, topY + h * 0.008, h * 0.028, h * 0.022, rgba(mix(col, [90, 70, 50], 0.4), 1));
}

function cypress(g, x, baseY, h, w, col, rim) {
  g.fillStyle = col;
  g.beginPath();
  g.moveTo(x, baseY - h);
  g.bezierCurveTo(x + w * 0.9, baseY - h * 0.75, x + w * 1.1, baseY - h * 0.25, x + w * 0.5, baseY);
  g.lineTo(x - w * 0.5, baseY);
  g.bezierCurveTo(x - w * 1.1, baseY - h * 0.25, x - w * 0.9, baseY - h * 0.75, x, baseY - h);
  g.closePath();
  g.fill();
  if (rim) {
    g.strokeStyle = rgba(rim, 0.5);
    g.lineWidth = Math.max(1, w * 0.12);
    g.beginPath();
    g.moveTo(x, baseY - h);
    g.bezierCurveTo(x - w * 0.9, baseY - h * 0.75, x - w * 1.0, baseY - h * 0.3, x - w * 0.5, baseY - h * 0.02);
    g.stroke();
  }
}

// Postava v siluetě: stojící nebo sedící, s kápí, rukávem a holí; `lit` = ze které
// strany ji osvětluje oheň (-1 vlevo, +1 vpravo), `face` kam se dívá.
function person(g, x, footY, h, o) {
  const robe = o.robe, skin = o.skin || [222, 172, 134], lit = o.lit || 0;
  const warm = o.warm || P.WARM;
  const sit = !!o.sit, face = o.face == null ? 1 : o.face;
  const bodyH = sit ? h * 0.56 : h * 0.80;
  const topW = h * 0.115, botW = sit ? h * 0.27 : h * 0.20;
  const sy = footY - bodyH;
  g.fillStyle = 'rgba(4,8,22,0.4)';
  g.beginPath(); g.ellipse(x, footY, botW * 1.25, h * 0.03, 0, 0, Math.PI * 2); g.fill();
  const cloak = () => {
    g.beginPath();
    g.moveTo(x - botW, footY);
    g.bezierCurveTo(x - botW * 0.95, footY - bodyH * 0.45, x - topW * 1.5, sy + bodyH * 0.12, x - topW, sy + h * 0.015);
    g.quadraticCurveTo(x, sy - h * 0.035, x + topW, sy + h * 0.015);
    g.bezierCurveTo(x + topW * 1.5, sy + bodyH * 0.12, x + botW * 0.95, footY - bodyH * 0.45, x + botW, footY);
    g.closePath();
  };
  cloak();
  g.fillStyle = rgba(robe, 1);
  g.fill();
  if (sit) {
    for (const kx of [-0.5, 0.5]) {
      g.fillStyle = rgba(mix(robe, [0, 0, 0], 0.12), 1);
      g.beginPath(); g.ellipse(x + face * h * (0.12 + kx * 0.06), footY - h * 0.075, h * 0.12, h * 0.085, 0, 0, Math.PI * 2); g.fill();
    }
  }
  g.save();
  cloak();
  g.clip();
  if (lit) {
    const lg = g.createLinearGradient(x + lit * botW, 0, x - lit * botW * 0.2, 0);
    lg.addColorStop(0, rgba(mix(robe, warm, 0.6), 0.85));
    lg.addColorStop(1, rgba(mix(robe, warm, 0.6), 0));
    g.fillStyle = lg;
    g.fillRect(x - botW * 1.2, sy - h * 0.1, botW * 2.4, bodyH + h * 0.2);
  }
  g.strokeStyle = rgba(mix(robe, [0, 0, 0], 0.4), 0.55);
  g.lineWidth = Math.max(1, h * 0.012);
  for (let k = -2; k <= 2; k++) {
    g.beginPath(); g.moveTo(x + k * topW * 0.5, sy + h * 0.06); g.quadraticCurveTo(x + k * botW * 0.55, footY - bodyH * 0.4, x + k * botW * 0.48, footY); g.stroke();
  }
  if (o.belt) {
    g.fillStyle = rgba(o.belt, 1);
    g.fillRect(x - botW, footY - bodyH * 0.50, botW * 2, h * 0.022);
  }
  g.restore();
  // rukáv a ruka s holí
  const hy = sy - h * 0.075;
  if (o.staff) {
    const dir = o.staff, sx2 = x + dir * h * 0.215;
    g.strokeStyle = rgba(P.WOOD, 1);
    g.lineWidth = Math.max(1.5, h * 0.024);
    g.lineCap = 'round';
    g.beginPath(); g.moveTo(sx2 + dir * h * 0.01, footY + h * 0.012); g.lineTo(sx2, footY - h * 1.04); g.stroke();
    g.beginPath(); g.arc(sx2 - dir * h * 0.05, footY - h * 1.04, h * 0.05, dir > 0 ? -0.2 : Math.PI + 0.2, dir > 0 ? Math.PI * 1.2 : -Math.PI * 0.2, dir < 0); g.stroke();
    g.strokeStyle = rgba(mix(robe, [0, 0, 0], 0.1), 1);
    g.lineWidth = Math.max(2, h * 0.062);
    g.beginPath(); g.moveTo(x + dir * topW * 0.9, sy + h * 0.05); g.quadraticCurveTo(x + dir * h * 0.2, sy + h * 0.14, sx2, sy + bodyH * 0.42); g.stroke();
    ellipse(g, sx2, sy + bodyH * 0.42, h * 0.028, h * 0.028, rgba(skin, 1));
  }
  // kápě s obličejem
  g.fillStyle = rgba(o.hood || robe, 1);
  g.beginPath();
  g.ellipse(x - face * h * 0.01, hy + h * 0.012, h * 0.098, h * 0.108, 0, 0, Math.PI * 2);
  g.fill();
  g.beginPath();
  g.moveTo(x - face * h * 0.06, hy + h * 0.05); g.lineTo(x - face * h * 0.14, hy + h * 0.17); g.lineTo(x + face * h * 0.0, hy + h * 0.12);
  g.closePath(); g.fill();
  ellipse(g, x + face * h * 0.028, hy + h * 0.024, h * 0.062, h * 0.074, rgba(mix(skin, [30, 16, 20], 0.25), 1));
  ellipse(g, x + face * h * 0.036, hy + h * 0.026, h * 0.052, h * 0.066, rgba(skin, 1));
  if (lit) ellipse(g, x + face * h * 0.036, hy + h * 0.026, h * 0.052, h * 0.066, rgba(warm, lit === face ? 0.24 : 0.07));
  if (o.beard) {
    ellipse(g, x + face * h * 0.036, hy + h * 0.082, h * 0.040, h * 0.046, rgba(o.beard, 1));
    ellipse(g, x + face * h * 0.036, hy + h * 0.050, h * 0.052, h * 0.030, rgba(skin, 1));
  }
}

// ------------------------------------------------------------ town

function townHouse(g, x, baseY, w, h, col, litCol, rand, wins, kind) {
  g.fillStyle = rgba(col, 1);
  if (kind === 'dome') {
    g.fillRect(x, baseY - h, w, h);
    g.beginPath(); g.ellipse(x + w / 2, baseY - h, w * 0.46, w * 0.40, 0, Math.PI, Math.PI * 2); g.fill();
    g.fillRect(x + w / 2 - w * 0.02, baseY - h - w * 0.58, w * 0.04, w * 0.20);
  } else if (kind === 'tower') {
    g.fillRect(x, baseY - h, w, h);
    g.beginPath();
    g.moveTo(x - w * 0.12, baseY - h); g.lineTo(x + w / 2, baseY - h - w * 0.75); g.lineTo(x + w * 1.12, baseY - h);
    g.closePath(); g.fill();
  } else {
    g.fillRect(x, baseY - h, w, h);
    g.fillRect(x - w * 0.04, baseY - h - h * 0.07, w * 1.08, h * 0.08);
  }
  g.fillStyle = rgba(litCol, 0.55);
  g.fillRect(x, baseY - h, Math.max(1, w * 0.07), h);
  const n = Math.max(0, Math.floor(w * h / 220 * (0.4 + rand() * 0.6)));
  for (let i = 0; i < n; i++) {
    const wx = x + w * (0.14 + rand() * 0.64), wy = baseY - h * (0.12 + rand() * 0.72);
    const ws = Math.max(1.5, w * 0.075);
    if (rand() < 0.62) wins.push({ x: wx, y: wy, s: ws, ph: rand() * 6.28, on: rand() < 0.8 });
  }
}

// ---------------------------------------------------------------- factory

export function create() {
  function buildSky(W, H, rand) {
    const c = makeCanvas(W, H * 0.62), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H * HORIZON);
    P.SKY.forEach((col, i) => grad.addColorStop(i / (P.SKY.length - 1), rgba(col, 1)));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H * 0.62);
    // mléčná dráha: šikmý pás měkkých skvrn
    g.save();
    g.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 70; i++) {
      const t = rand();
      const x = W * (0.05 + t * 0.9), y = H * (0.30 - t * 0.22) + (rand() - 0.5) * H * 0.06;
      glow(g, x, y, H * (0.05 + rand() * 0.07), [120, 130, 220], 0.025 + rand() * 0.025, 0.55);
    }
    g.restore();
    const stars = [];
    for (let i = 0; i < 330; i++) {
      const x = rand() * W, y = Math.pow(rand(), 1.25) * H * 0.43;
      const bright = rand();
      const r = H * (0.0011 + bright * bright * 0.0017);
      const a = (0.35 + 0.65 * bright) * (1 - y / (H * 0.5));
      const warm = rand() < 0.25;
      g.fillStyle = warm ? rgba([255, 226, 190], a) : rgba([214, 226, 255], a);
      g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
      if (bright > 0.82) stars.push({ x: x / W, y: y / H, r, ph: rand() * 6.28, sp: 0.8 + rand() * 1.6, warm });
    }
    // horizont: teplý opar od města
    const hz = g.createLinearGradient(0, H * (HORIZON - 0.09), 0, H * (HORIZON + 0.03));
    hz.addColorStop(0, 'rgba(232,150,120,0)');
    hz.addColorStop(0.7, 'rgba(232,150,120,0.22)');
    hz.addColorStop(1, 'rgba(232,150,120,0.05)');
    g.fillStyle = hz;
    g.fillRect(0, H * (HORIZON - 0.09), W, H * 0.12);
    return { canvas: c, stars };
  }

  function buildMoon(W, H) {
    const s = H * 0.30, c = makeCanvas(s * 2, s * 2), g = c.getContext('2d');
    g.fillStyle = 'rgb(236,240,255)';
    g.beginPath(); g.arc(s, s, H * 0.032, 0, Math.PI * 2); g.fill();
    g.globalCompositeOperation = 'destination-out';
    g.beginPath(); g.arc(s + H * 0.020, s - H * 0.008, H * 0.029, 0, Math.PI * 2); g.fill();
    g.globalCompositeOperation = 'destination-over';
    glow(g, s - H * 0.012, s + H * 0.004, s, [150, 170, 255], 0.30);
    g.globalCompositeOperation = 'source-over';
    return { canvas: c, r: s };
  }

  // Kopce, město Betlém vlevo a vzdálené cypřiše: vše za stepí.
  function buildLand(W, H, rand) {
    const y0 = Math.round(H * 0.20);
    const c = makeCanvas(W, H * (0.64 - 0.20)), g = c.getContext('2d');
    g.translate(0, -y0);
    const wins = [];
    let x;

    const far = waveFn(rand, 4, 3.0 / W, 0.55);
    g.beginPath();
    g.moveTo(0, H * HORIZON + 4);
    for (x = 0; x <= W; x += 3) {
      const n = 1 - Math.abs(far(x));
      g.lineTo(x, H * (HORIZON - 0.012) - H * 0.085 * (0.25 + 0.75 * n * n));
    }
    g.lineTo(W, H * HORIZON + 4);
    g.closePath();
    g.fillStyle = rgba(mix(P.HILL_FAR, P.SKY[4], 0.18), 1);
    g.fill();

    // pahorek s městem: hladký kopec vlevo, nad ním domy v několika řadách
    const hillX0 = W * -0.02, hillX1 = W * 0.50;
    const hillTop = H * 0.325, hillBase = H * (HORIZON + 0.012);
    const hill = (xx) => {
      const u = clamp((xx - hillX0) / (hillX1 - hillX0), 0, 1);
      return hillBase - (hillBase - hillTop) * Math.pow(Math.sin(Math.PI * Math.pow(u, 0.80)), 0.75) * (1 - 0.18 * u);
    };
    g.beginPath();
    g.moveTo(hillX0, hillBase + 4);
    for (x = hillX0; x <= hillX1; x += 3) g.lineTo(x, hill(x));
    g.lineTo(hillX1, hillBase + 4);
    g.closePath();
    g.fillStyle = rgba(P.HILL_MID, 1);
    g.fill();

    const rows = [
      { dy: 0.000, hMin: 0.016, hMax: 0.040, shade: 0.00, step: 0.014 },
      { dy: 0.020, hMin: 0.018, hMax: 0.044, shade: 0.18, step: 0.013 },
      { dy: 0.040, hMin: 0.020, hMax: 0.050, shade: 0.34, step: 0.012 },
    ];
    for (let ri = rows.length - 1; ri >= 0; ri--) {
      const R = rows[ri];
      const col = mix(P.TOWN, P.HILL_MID, R.shade);
      const lit = mix(P.TOWN_LIT, P.HILL_MID, R.shade);
      for (x = hillX0 + W * 0.02; x < hillX1 - W * 0.03; x += W * R.step * (0.7 + rand() * 0.9)) {
        const by = hill(x) + H * R.dy * (1 - ri * 0.1) + H * 0.01;
        if (by > hillBase) continue;
        const w = W * (0.010 + rand() * 0.016), h = H * (R.hMin + rand() * (R.hMax - R.hMin));
        const r = rand();
        townHouse(g, x, by + H * 0.012, w, h, col, lit, rand, wins, r < 0.12 ? 'dome' : (r < 0.20 ? 'tower' : 'box'));
      }
    }
    // hradba podél úpatí
    g.fillStyle = rgba(mix(P.TOWN, P.HILL_MID, 0.4), 1);
    g.fillRect(hillX0, hillBase - H * 0.012, hillX1 - hillX0, H * 0.016);

    // pravý hřeben a vzdálené cypřiše
    const near = waveFn(rand, 5, 4.6 / W, 0.5);
    g.beginPath();
    g.moveTo(W * 0.45, H * HORIZON + 6);
    for (x = W * 0.45; x <= W; x += 3) {
      const u = (x - W * 0.45) / (W * 0.55);
      const n = 1 - Math.abs(near(x));
      g.lineTo(x, H * (HORIZON + 0.01) - H * 0.065 * (0.3 + 0.7 * n * n) * Math.min(1, u * 3));
    }
    g.lineTo(W, H * HORIZON + 6);
    g.closePath();
    g.fillStyle = rgba(mix(P.HILL_NEAR, P.HILL_MID, 0.3), 1);
    g.fill();
    for (let i = 0; i < 14; i++) {
      const cx = W * (0.50 + rand() * 0.48);
      const h = H * (0.03 + rand() * 0.03);
      cypress(g, cx, H * (HORIZON + 0.012 + rand() * 0.006), h, h * 0.13, rgba(mix([14, 26, 44], P.HILL_NEAR, 0.4), 1), null);
    }
    const hz = g.createLinearGradient(0, H * (HORIZON - 0.03), 0, H * (HORIZON + 0.025));
    hz.addColorStop(0, 'rgba(210,140,120,0)');
    hz.addColorStop(0.55, 'rgba(210,140,120,0.20)');
    hz.addColorStop(1, 'rgba(210,140,120,0)');
    g.fillStyle = hz;
    g.fillRect(0, H * (HORIZON - 0.03), W, H * 0.055);
    return { canvas: c, y0, wins };
  }

  // Skalní návrší za chlévkem: nerovný hřbet, vrstvy skály, úpatí se vymaže do
  // průhledna, takže se rozplyne do stepi a nevypadá jako stůl.
  function paintHill(g, W, H, rand) {
    const u = H * STABLE.u, sx = W * STABLE.x, fy = H * STABLE.floor;
    const wob = waveFn(rand, 3, 1.4, 0.5);
    const rockTop = fy - u * 0.42, hw2 = u * 1.10, baseY = fy - u * 0.01;
    const ox = Math.floor(sx - hw2 - 4), oy = Math.floor(rockTop - u * 0.12);
    const hc = makeCanvas(hw2 * 2 + 8, fy + u * 0.10 - oy), h = hc.getContext('2d');
    h.translate(-ox, -oy);
    const big = waveFn(rand, 3, 2.2, 0.6);
    const hillPts = [];
    for (let k = 0; k <= 90; k++) {
      const t = k / 90, xx = sx + (t - 0.5) * hw2 * 2;
      const prof = Math.pow(Math.sin(Math.PI * Math.pow(t, 0.9)), 0.62);
      const bump = (big(t * 9) * 0.045 + wob(t * 26) * 0.012) * u;
      hillPts.push([xx, baseY - (baseY - rockTop) * prof + bump * Math.sqrt(prof)]);
    }
    const hillPath = () => {
      h.beginPath();
      h.moveTo(sx - hw2, baseY + u * 0.08);
      hillPts.forEach((p) => h.lineTo(p[0], p[1]));
      h.lineTo(sx + hw2, baseY + u * 0.08);
      h.closePath();
    };
    hillPath();
    const rg = h.createLinearGradient(sx - hw2, 0, sx + hw2, 0);
    rg.addColorStop(0, rgba(mix(P.HILL_MID, [70, 78, 130], 0.55), 1));
    rg.addColorStop(0.45, rgba([34, 38, 74], 1));
    rg.addColorStop(1, rgba([26, 28, 60], 1));
    h.fillStyle = rg;
    h.fill();
    h.save();
    hillPath();
    h.clip();
    for (let i = 0; i < 16; i++) {
      const yy = rockTop + (baseY - rockTop) * (i + rand() * 0.6) / 16;
      const ph = rand() * 6.28, amp = u * (0.006 + rand() * 0.012);
      h.beginPath();
      for (let xx = sx - hw2; xx <= sx + hw2; xx += 8) h.lineTo(xx, yy + Math.sin(xx / (u * 0.13) + ph) * amp);
      h.strokeStyle = rand() < 0.5 ? rgba([110, 120, 180], 0.16) : rgba([6, 8, 24], 0.30);
      h.lineWidth = u * (0.006 + rand() * 0.012);
      h.stroke();
    }
    for (let i = 0; i < 70; i++) {
      const rx = sx + (rand() - 0.5) * hw2 * 1.9, ry = rockTop + rand() * (baseY - rockTop);
      const rw = u * (0.025 + rand() * 0.06);
      h.fillStyle = rand() < 0.5 ? rgba([96, 106, 160], 0.16) : rgba([8, 10, 28], 0.26);
      h.beginPath(); h.ellipse(rx, ry, rw, rw * 0.38, (rand() - 0.5) * 0.5, 0, Math.PI * 2); h.fill();
    }
    glow(h, sx, fy - u * 0.30, u * 0.45, [255, 170, 100], 0.14, 0.8);
    h.restore();
    h.strokeStyle = rgba([130, 142, 200], 0.40);
    h.lineWidth = Math.max(1, u * 0.004);
    h.beginPath();
    hillPts.slice(8, 40).forEach((p, k) => (k ? h.lineTo(p[0], p[1]) : h.moveTo(p[0], p[1])));
    h.stroke();
    h.globalCompositeOperation = 'destination-out';
    const fade = h.createLinearGradient(0, baseY - u * 0.16, 0, baseY + u * 0.02);
    fade.addColorStop(0, 'rgba(0,0,0,0)');
    fade.addColorStop(1, 'rgba(0,0,0,1)');
    h.fillStyle = fade;
    h.fillRect(sx - hw2 - 4, baseY - u * 0.16, hw2 * 2 + 8, u * 0.30);
    g.drawImage(hc, ox, oy);
  }

  // Chlévek: skála, doškovou střechu, trámy, jesle a Svatou rodinu.
  // Vrací i body, kde se v draw() rozsvěcí plameny a záře.
  function paintStable(g, W, H, rand) {
    const u = H * STABLE.u, sx = W * STABLE.x, fy = H * STABLE.floor;
    // vnitřek: tmavé dřevo prozářené ohněm jeslí
    const iw = u * 0.58, ih = u * 0.255;
    const ix = sx - iw / 2, iy = fy - ih;
    g.fillStyle = rgba([34, 22, 24], 1);
    g.fillRect(ix, iy, iw, ih + 1);
    const wg = g.createRadialGradient(sx + u * 0.01, fy - u * 0.07, u * 0.01, sx + u * 0.01, fy - u * 0.07, u * 0.34);
    wg.addColorStop(0, 'rgba(255,196,110,0.95)');
    wg.addColorStop(0.35, 'rgba(214,126,62,0.70)');
    wg.addColorStop(1, 'rgba(60,30,24,0)');
    g.fillStyle = wg;
    g.fillRect(ix, iy, iw, ih + 1);
    // prkna zadní stěny
    g.strokeStyle = rgba([30, 18, 16], 0.5);
    g.lineWidth = Math.max(1, u * 0.004);
    for (let k = 1; k < 14; k++) {
      g.beginPath(); g.moveTo(ix + iw * k / 14, iy); g.lineTo(ix + iw * k / 14 + (rand() - 0.5) * 2, fy); g.stroke();
    }
    // podlaha ze slámy
    const fg = g.createLinearGradient(0, fy - u * 0.03, 0, fy + u * 0.02);
    fg.addColorStop(0, rgba(P.STRAW_DARK, 1));
    fg.addColorStop(1, rgba(mix(P.STRAW, [255, 210, 130], 0.2), 1));
    g.fillStyle = fg;
    g.fillRect(ix - u * 0.02, fy - u * 0.026, iw + u * 0.04, u * 0.045);
    g.strokeStyle = rgba([240, 196, 110], 0.5);
    g.lineWidth = Math.max(1, u * 0.003);
    for (let k = 0; k < 90; k++) {
      const hx = ix + rand() * iw, hy = fy - u * 0.02 + rand() * u * 0.035, l = u * (0.015 + rand() * 0.022);
      g.beginPath(); g.moveTo(hx, hy); g.lineTo(hx + l * (rand() < 0.5 ? 1 : -1), hy - l * 0.35); g.stroke();
    }

    // balíky sena po stranách
    for (const [bx, bw, bh] of [[ix + u * 0.012, u * 0.105, u * 0.07], [ix + iw - u * 0.125, u * 0.105, u * 0.075],
                                [ix + u * 0.11, u * 0.08, u * 0.052]]) {
      const by = fy - u * 0.005 - bh;
      g.fillStyle = rgba(mix(P.STRAW_DARK, [60, 38, 28], 0.2), 1);
      g.fillRect(bx, by, bw, bh);
      g.fillStyle = rgba(P.STRAW, 0.9);
      g.fillRect(bx, by, bw, bh * 0.28);
      g.strokeStyle = rgba(P.WOOD_DARK, 0.7);
      g.lineWidth = Math.max(1, u * 0.004);
      g.beginPath(); g.moveTo(bx + bw * 0.3, by); g.lineTo(bx + bw * 0.3, by + bh); g.moveTo(bx + bw * 0.7, by); g.lineTo(bx + bw * 0.7, by + bh); g.stroke();
      g.strokeStyle = rgba([240, 190, 110], 0.5);
      for (let k = 0; k < 14; k++) {
        const lx = bx + rand() * bw, ly = by + rand() * bh;
        g.beginPath(); g.moveTo(lx, ly); g.lineTo(lx + (rand() - 0.5) * bw * 0.25, ly - bh * 0.15); g.stroke();
      }
    }

    // jesle: dřevěný žlab na zkřížených nohách, v něm seno a zářící Ježíšek
    const mx = sx + u * 0.012, my = fy - u * 0.012;
    g.strokeStyle = rgba(P.WOOD, 1);
    g.lineWidth = Math.max(2, u * 0.012);
    g.lineCap = 'round';
    g.beginPath();
    g.moveTo(mx - u * 0.075, my); g.lineTo(mx + u * 0.045, my - u * 0.052);
    g.moveTo(mx + u * 0.075, my); g.lineTo(mx - u * 0.045, my - u * 0.052);
    g.stroke();
    g.fillStyle = rgba(mix(P.WOOD, [230, 150, 90], 0.25), 1);
    g.beginPath();
    g.moveTo(mx - u * 0.105, my - u * 0.056);
    g.lineTo(mx + u * 0.105, my - u * 0.056);
    g.lineTo(mx + u * 0.082, my - u * 0.018);
    g.lineTo(mx - u * 0.082, my - u * 0.018);
    g.closePath();
    g.fill();
    g.fillStyle = rgba([255, 220, 130], 1);
    g.beginPath();
    g.moveTo(mx - u * 0.100, my - u * 0.056);
    g.quadraticCurveTo(mx, my - u * 0.092, mx + u * 0.100, my - u * 0.056);
    g.closePath();
    g.fill();
    // dítě v peřince
    ellipse(g, mx, my - u * 0.070, u * 0.052, u * 0.022, rgba([248, 240, 226], 1), -0.04);
    ellipse(g, mx + u * 0.030, my - u * 0.078, u * 0.019, u * 0.019, rgba([246, 202, 160], 1));
    ellipse(g, mx + u * 0.030, my - u * 0.082, u * 0.021, u * 0.015, rgba([255, 244, 220], 0.9), 0.3);
    const baby = { x: mx + u * 0.01, y: my - u * 0.07 };

    // Marie klečící vlevo od jeslí: modrý plášť, bílý šátek
    const mxm = mx - u * 0.17, mFoot = fy - u * 0.003;
    g.fillStyle = 'rgba(8,6,16,0.4)';
    g.beginPath(); g.ellipse(mxm, mFoot, u * 0.085, u * 0.014, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba([48, 82, 164], 1);
    g.beginPath();
    g.moveTo(mxm - u * 0.085, mFoot);
    g.quadraticCurveTo(mxm - u * 0.085, mFoot - u * 0.09, mxm - u * 0.030, mFoot - u * 0.150);
    g.quadraticCurveTo(mxm + u * 0.010, mFoot - u * 0.176, mxm + u * 0.038, mFoot - u * 0.146);
    g.quadraticCurveTo(mxm + u * 0.090, mFoot - u * 0.08, mxm + u * 0.092, mFoot);
    g.closePath();
    g.fill();
    g.fillStyle = rgba([126, 168, 236], 0.8);
    g.beginPath();
    g.moveTo(mxm + u * 0.092, mFoot);
    g.quadraticCurveTo(mxm + u * 0.090, mFoot - u * 0.08, mxm + u * 0.038, mFoot - u * 0.146);
    g.lineTo(mxm + u * 0.020, mFoot - u * 0.140);
    g.quadraticCurveTo(mxm + u * 0.060, mFoot - u * 0.07, mxm + u * 0.052, mFoot);
    g.closePath();
    g.fill();
    ellipse(g, mxm + u * 0.012, mFoot - u * 0.172, u * 0.034, u * 0.038, rgba([250, 246, 236], 1));
    ellipse(g, mxm + u * 0.026, mFoot - u * 0.166, u * 0.021, u * 0.027, rgba([238, 184, 146], 1));
    ellipse(g, mxm + u * 0.022, mFoot - u * 0.178, u * 0.027, u * 0.014, rgba([250, 246, 236], 1), -0.2);
    g.strokeStyle = rgba([238, 184, 146], 1);
    g.lineWidth = Math.max(2, u * 0.012);
    g.beginPath(); g.moveTo(mxm + u * 0.045, mFoot - u * 0.115); g.quadraticCurveTo(mxm + u * 0.075, mFoot - u * 0.085, mxm + u * 0.105, mFoot - u * 0.082); g.stroke();
    // svatozář
    g.strokeStyle = rgba([255, 226, 150], 0.85);
    g.lineWidth = Math.max(1, u * 0.004);
    g.beginPath(); g.ellipse(mxm + u * 0.014, mFoot - u * 0.174, u * 0.047, u * 0.050, 0, 0, Math.PI * 2); g.stroke();

    // Josef vpravo: hnědý plášť, hůl, lucerna
    person(g, mx + u * 0.205, fy - u * 0.003, u * 0.205,
           { robe: [138, 86, 52], hood: [86, 54, 38], skin: [226, 178, 138], beard: [58, 40, 30], staff: 1, lit: -1, face: -1 });

    // trámy: dva sloupy a průvlak
    const postW = u * 0.034;
    for (const px of [sx - iw / 2 - postW * 0.2, sx + iw / 2 - postW * 0.8]) {
      const pg = g.createLinearGradient(px, 0, px + postW, 0);
      pg.addColorStop(0, rgba(P.WOOD_DARK, 1));
      pg.addColorStop(0.5, rgba(mix(P.WOOD, [30, 22, 34], 0.25), 1));
      pg.addColorStop(1, rgba(mix(P.WOOD, [210, 130, 70], 0.2), 1));
      g.fillStyle = pg;
      g.fillRect(px, iy - u * 0.02, postW, ih + u * 0.03);
      g.strokeStyle = rgba([20, 12, 12], 0.5);
      g.lineWidth = Math.max(1, u * 0.003);
      for (let k = 0; k < 7; k++) {
        const yy = iy + rand() * ih;
        g.beginPath(); g.moveTo(px + postW * rand(), yy); g.lineTo(px + postW * rand(), yy + u * 0.03); g.stroke();
      }
    }
    g.fillStyle = rgba(mix(P.WOOD_DARK, P.WOOD, 0.4), 1);
    g.fillRect(sx - iw / 2 - u * 0.03, iy - u * 0.034, iw + u * 0.06, u * 0.036);
    g.fillStyle = rgba([210, 130, 70], 0.28);
    g.fillRect(sx - iw / 2 - u * 0.03, iy - u * 0.034, iw + u * 0.06, u * 0.008);

    // střecha: dvouspádová došková, silný okraj vpředu
    const eaveY = iy - u * 0.030, apexY = fy - u * 0.405, halfW = u * 0.395;
    const roofPath = () => {
      g.beginPath();
      g.moveTo(sx - halfW, eaveY + u * 0.018);
      g.quadraticCurveTo(sx - halfW * 0.55, eaveY - u * 0.05, sx - u * 0.02, apexY + u * 0.01);
      g.lineTo(sx, apexY - u * 0.012);
      g.lineTo(sx + u * 0.02, apexY + u * 0.01);
      g.quadraticCurveTo(sx + halfW * 0.55, eaveY - u * 0.05, sx + halfW, eaveY + u * 0.018);
      g.lineTo(sx + halfW * 0.96, eaveY + u * 0.058);
      g.quadraticCurveTo(sx, eaveY + u * 0.036, sx - halfW * 0.96, eaveY + u * 0.058);
      g.closePath();
    };
    roofPath();
    const tg = g.createLinearGradient(sx - halfW, 0, sx + halfW, 0);
    tg.addColorStop(0, rgba([124, 100, 74], 1));
    tg.addColorStop(0.5, rgba([88, 68, 52], 1));
    tg.addColorStop(1, rgba([70, 52, 44], 1));
    g.fillStyle = tg;
    g.fill();
    g.save();
    roofPath();
    g.clip();
    for (let k = 0; k < 520; k++) {
      const rx = sx + (rand() - 0.5) * halfW * 2, ry = apexY + rand() * (eaveY + u * 0.06 - apexY);
      const l = u * (0.022 + rand() * 0.034);
      const side = rx < sx ? -1 : 1;
      const a = Math.PI / 2 - side * 0.5 + (rand() - 0.5) * 0.25;
      g.strokeStyle = rand() < 0.5 ? rgba([186, 150, 98], 0.34) : rgba([34, 24, 24], 0.42);
      g.lineWidth = Math.max(1, u * 0.0034);
      g.beginPath(); g.moveTo(rx, ry); g.lineTo(rx + Math.cos(a) * l * 0.6, ry + Math.sin(a) * l); g.stroke();
    }
    // měsíční odlesk na levém spádu a teplý nádech od jeslí na podstřeší
    const sh = g.createLinearGradient(0, apexY, 0, eaveY + u * 0.06);
    sh.addColorStop(0, 'rgba(160,176,255,0.20)');
    sh.addColorStop(1, 'rgba(255,170,90,0.20)');
    g.fillStyle = sh;
    g.fillRect(sx - halfW, apexY, halfW, eaveY + u * 0.06 - apexY);
    const under = g.createLinearGradient(0, eaveY - u * 0.01, 0, eaveY + u * 0.06);
    under.addColorStop(0, 'rgba(0,0,0,0)');
    under.addColorStop(1, 'rgba(6,2,4,0.55)');
    g.fillStyle = under;
    g.fillRect(sx - halfW, eaveY - u * 0.01, halfW * 2, u * 0.08);
    g.restore();
    g.strokeStyle = rgba([212, 176, 120], 0.5);
    g.lineWidth = Math.max(1, u * 0.004);
    g.beginPath();
    g.moveTo(sx - halfW * 0.96, eaveY + u * 0.058);
    g.quadraticCurveTo(sx, eaveY + u * 0.036, sx + halfW * 0.96, eaveY + u * 0.058);
    g.stroke();

    // lucerny pod střechou
    const lanterns = [];
    for (const lx of [sx - u * 0.22, sx + u * 0.27]) {
      const ly = iy + u * 0.050;
      g.strokeStyle = rgba([20, 14, 14], 1);
      g.lineWidth = Math.max(1, u * 0.004);
      g.beginPath(); g.moveTo(lx, iy - u * 0.004); g.lineTo(lx, ly - u * 0.020); g.stroke();
      g.fillStyle = rgba([40, 30, 28], 1);
      g.fillRect(lx - u * 0.013, ly - u * 0.020, u * 0.026, u * 0.005);
      g.fillStyle = rgba([255, 214, 130], 1);
      g.fillRect(lx - u * 0.010, ly - u * 0.015, u * 0.020, u * 0.030);
      g.fillStyle = rgba([40, 30, 28], 1);
      g.fillRect(lx - u * 0.013, ly + u * 0.015, u * 0.026, u * 0.005);
      lanterns.push({ x: lx, y: ly });
    }
    return { baby, lanterns, mouth: { x: mx, y: my - u * 0.05 }, u, sx, fy, apexY };
  }

  // Louka, cesta a vše, co leží NA zemi nebo za tvory: tráva, kameny, ohrada,
  // pastýři u ohně, palmy, chlévek se skálou.
  function buildGround(W, H, rand) {
    const y0 = Math.round(H * 0.16);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;

    // horní okraj stepi se vlní, ať obzor není přímka
    const edge = waveFn(rand, 4, 9.0 / W, 0.55);
    const base = g.createLinearGradient(0, H * (HORIZON - 0.02), 0, H);
    base.addColorStop(0.00, rgba(mix(P.GROUND_FAR, P.SKY[4], 0.25), 1));
    base.addColorStop(0.08, rgba(mix(P.GROUND_FAR, P.SKY[4], 0.10), 1));
    base.addColorStop(0.16, rgba(P.GROUND_FAR, 1));
    base.addColorStop(0.45, rgba(P.GROUND_MID, 1));
    base.addColorStop(1.00, rgba(P.GROUND_NEAR, 1));
    g.fillStyle = base;
    g.beginPath();
    g.moveTo(0, H);
    for (x = 0; x <= W; x += 4) g.lineTo(x, H * (HORIZON - 0.002) + edge(x) * H * 0.009);
    g.lineTo(W, H);
    g.closePath();
    g.fill();

    paintHill(g, W, H, rand);

    const patch = waveFn(rand, 4, 6.0 / W, 0.55);
    for (let i = 0; i < 170; i++) {
      const yy = H * lerp(0.455, 1.0, Math.pow(rand(), 0.85));
      const xx = rand() * W;
      const d = depthScale(yy / H);
      const rw = W * (0.02 + 0.10 * d) * (0.5 + rand());
      g.fillStyle = patch(xx + yy * 0.3) > 0 ? 'rgba(130,140,190,0.10)' : 'rgba(4,10,26,0.14)';
      g.beginPath(); g.ellipse(xx, yy, rw, rw * 0.16, 0, 0, Math.PI * 2); g.fill();
    }

    // vzdálená pole: stříbrnější plochy a pár keřů na obzoru
    for (let i = 0; i < 46; i++) {
      const xx = rand() * W, yy = H * (0.455 + rand() * 0.06);
      const sz = H * (0.004 + rand() * 0.006);
      ellipse(g, xx, yy, sz * 1.9, sz * 0.8, rgba([30, 40, 70], 0.75));
      ellipse(g, xx - sz * 0.3, yy - sz * 0.45, sz * 1.2, sz * 0.6, rgba([46, 60, 84], 0.7));
    }

    // ovčí ohrada vlevo za ohništěm: tyče, dvě příčky a pár malovaných ovcí
    const penY = H * 0.545, penX0 = W * 0.045, penX1 = W * 0.305;
    g.fillStyle = 'rgba(14,20,50,0.35)';
    g.beginPath(); g.ellipse((penX0 + penX1) / 2, penY + H * 0.004, (penX1 - penX0) / 2 * 1.02, H * 0.012, 0, 0, Math.PI * 2); g.fill();
    for (let i = 0; i < 16; i++) {
      const sxp = W * 0.0035 * 0 + (penX0 + (penX1 - penX0) * i / 15);
      const sh = H * 0.017;
      ellipse(g, sxp, penY + H * 0.0005 - sh * 0.1, H * 0.0016, H * 0.001, rgba([20, 20, 40], 0.5));
    }
    const sheepPen = [[0.075, 0.53, 1], [0.105, 0.54, -1], [0.145, 0.532, 1], [0.185, 0.543, -1], [0.225, 0.535, 1], [0.262, 0.542, 1]];
    for (const [fx, fyy, face] of sheepPen) {
      const sx0 = W * fx, sy0 = H * fyy, s = H * 0.0165;
      ellipse(g, sx0, sy0 - s * 0.55, s * 0.95, s * 0.62, rgba([226, 224, 218], 1));
      ellipse(g, sx0 - face * s * 0.2, sy0 - s * 0.80, s * 0.70, s * 0.45, rgba([245, 243, 236], 0.9));
      ellipse(g, sx0 + face * s * 0.95, sy0 - s * 0.82, s * 0.30, s * 0.28, rgba([56, 48, 52], 1));
      g.strokeStyle = rgba([50, 44, 48], 1);
      g.lineWidth = Math.max(1, s * 0.16);
      for (const lx of [-0.5, -0.15, 0.2, 0.55]) {
        g.beginPath(); g.moveTo(sx0 + lx * s, sy0 - s * 0.2); g.lineTo(sx0 + lx * s, sy0 + s * 0.12); g.stroke();
      }
    }
    g.strokeStyle = rgba([78, 56, 48], 1);
    g.lineCap = 'round';
    g.lineWidth = Math.max(1, H * 0.0022);
    for (const ry of [0.019, 0.010]) {
      g.beginPath(); g.moveTo(penX0, penY - H * ry); g.lineTo(penX1, penY - H * ry); g.stroke();
    }
    g.lineWidth = Math.max(1.5, H * 0.0032);
    for (let i = 0; i < 16; i++) {
      const sxp = penX0 + (penX1 - penX0) * i / 15 + (rand() - 0.5) * 2;
      g.beginPath(); g.moveTo(sxp, penY + H * 0.002); g.lineTo(sxp + (rand() - 0.5) * 2, penY - H * 0.024); g.stroke();
    }

    // cesta k chlévku
    const cx = (yf) => W * trailX(yf);
    const hw = (yf) => W * trailHalf(yf);
    const left = [], right = [];
    const wobP = waveFn(rand, 2, 1, 0.5);
    for (let yy = 0.665; yy <= 1.005; yy += 0.01) {
      const wb = wobP(yy * 5) * 0.06 + 1;
      left.push([cx(yy) - hw(yy) * wb, H * yy]);
      right.push([cx(yy) + hw(yy) * wb, H * yy]);
    }
    const outline = () => {
      g.beginPath();
      left.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
      for (let i = right.length - 1; i >= 0; i--) g.lineTo(right[i][0], right[i][1]);
      g.closePath();
    };
    outline();
    const pg = g.createLinearGradient(0, H * 0.66, 0, H);
    pg.addColorStop(0, rgba(mix(P.PATH, P.PATH_LIGHT, 0.7), 1));
    pg.addColorStop(0.25, rgba(P.PATH, 1));
    pg.addColorStop(1, rgba(mix(P.PATH, [30, 36, 70], 0.4), 1));
    g.fillStyle = pg;
    g.fill();
    g.save();
    outline();
    g.clip();
    for (const off of [-0.45, 0.45]) {
      g.beginPath();
      for (let yy = 0.665; yy <= 1.005; yy += 0.01) {
        const px = cx(yy) + hw(yy) * off;
        if (yy === 0.665) g.moveTo(px, H * yy); else g.lineTo(px, H * yy);
      }
      g.strokeStyle = rgba(P.PATH_DARK, 0.5);
      g.lineWidth = Math.max(1, H * 0.006);
      g.stroke();
    }
    for (let i = 0; i < 760; i++) {
      const yf = 0.665 + Math.pow(rand(), 0.8) * 0.335;
      const px = cx(yf) + (rand() - 0.5) * 2 * hw(yf);
      const d = depthScale(yf);
      const s = H * 0.0012 * (0.5 + d * 3) * (0.6 + rand());
      g.fillStyle = rand() < 0.5 ? rgba(P.PATH_DARK, 0.55) : rgba(P.PATH_LIGHT, 0.55);
      g.beginPath(); g.ellipse(px, H * yf, s * 1.5, s, 0, 0, Math.PI * 2); g.fill();
    }
    g.restore();
    for (let i = 0; i < 200; i++) {
      const yf = 0.67 + Math.pow(rand(), 0.85) * 0.33;
      const side = rand() < 0.5 ? -1 : 1;
      const px = cx(yf) + side * hw(yf) * (0.92 + rand() * 0.2);
      const d = depthScale(yf);
      tuft(g, px, H * yf, H * (0.008 + 0.030 * d), rgba(mix(P.GRASS[2], P.GRASS[1], rand()), 1), rand, 4);
    }

    // tráva a drobné kamínky po celé stepi
    for (let i = 0; i < 600; i++) {
      const yf = lerp(0.46, 1.0, Math.pow(rand(), 0.7));
      const px = rand() * W;
      if (yf > 0.665 && Math.abs(px - cx(yf)) < hw(yf) * 0.9) continue;
      const d = depthScale(yf);
      tuft(g, px, H * yf, H * (0.006 + 0.026 * d) * (0.7 + rand() * 0.6),
           rgba(mix(P.GRASS[0], P.GRASS[3], rand() * 0.8), 0.95), rand, 4 + Math.floor(rand() * 3));
    }
    for (let i = 0; i < 260; i++) {
      const yf = lerp(0.47, 1.0, Math.pow(rand(), 0.7));
      const px = rand() * W;
      if (yf > 0.665 && Math.abs(px - cx(yf)) < hw(yf)) continue;
      const d = depthScale(yf);
      ellipse(g, px, H * yf, H * 0.0035 * (0.5 + d * 2) * (0.6 + rand()), H * 0.0016 * (0.5 + d * 2), rgba(mix(P.ROCK, P.ROCK_LIT, rand()), 0.55));
    }

    // palmy, cypřiše a keře za chlévkem a po jeho stranách
    const wobR = waveFn(rand, 3, 1.2, 0.5);
    const warmRim = [150, 110, 90];
    const treeAt = (kind, fx, fy2, h, lean) => {
      if (kind === 'palm') palm(g, W * fx, H * fy2, H * h, lean, rand, P.PALM, warmRim);
      else cypress(g, W * fx, H * fy2, H * h, H * h * 0.12, rgba([12, 28, 42], 1), [80, 96, 110]);
    };
    treeAt('cyp', 0.435, 0.610, 0.20, 0);
    treeAt('palm', 0.405, 0.605, 0.27, 0.09);
    treeAt('cyp', 0.462, 0.615, 0.14, 0);
    treeAt('palm', 0.865, 0.612, 0.32, -0.08);
    treeAt('palm', 0.905, 0.600, 0.25, 0.07);
    treeAt('cyp', 0.940, 0.610, 0.19, 0);
    treeAt('palm', 0.972, 0.618, 0.30, -0.06);
    treeAt('cyp', 0.835, 0.612, 0.13, 0);
    treeAt('palm', 0.035, 0.600, 0.22, 0.08);
    treeAt('cyp', 0.335, 0.592, 0.15, 0);

    const stable = paintStable(g, W, H, rand);

    // zemina před chlévkem: světlá skvrna od ohně, ošlapaná sláma
    const pool = g.createRadialGradient(W * STABLE.x, H * STABLE.floor + H * 0.02, 0, W * STABLE.x, H * STABLE.floor + H * 0.02, W * 0.26);
    pool.addColorStop(0, 'rgba(255,190,100,0.46)');
    pool.addColorStop(0.4, 'rgba(214,130,70,0.20)');
    pool.addColorStop(1, 'rgba(214,130,70,0)');
    g.save();
    g.translate(0, H * (STABLE.floor + 0.02));
    g.scale(1, 0.34);
    g.translate(0, -H * (STABLE.floor + 0.02));
    g.fillStyle = pool;
    g.fillRect(W * (STABLE.x - 0.3), H * (STABLE.floor - 0.10), W * 0.6, H * 0.5);
    g.restore();
    for (let i = 0; i < 90; i++) {
      const px = W * (STABLE.x + (rand() - 0.5) * 0.30), py = H * (STABLE.floor + 0.006 + rand() * 0.07);
      const l = H * (0.006 + rand() * 0.01);
      g.strokeStyle = rgba([222, 176, 100], 0.45);
      g.lineWidth = Math.max(1, H * 0.0018);
      g.beginPath(); g.moveTo(px, py); g.lineTo(px + l * (rand() < 0.5 ? 1 : -1), py - l * 0.3); g.stroke();
    }

    // ohniště pastýřů: kameny, polena, pastýři v teple ohně
    const fx0 = W * FIRE.x, fy0 = H * FIRE.y;
    const fpool = g.createRadialGradient(fx0, fy0, 0, fx0, fy0, W * 0.15);
    fpool.addColorStop(0, 'rgba(255,170,80,0.50)');
    fpool.addColorStop(0.5, 'rgba(220,110,50,0.18)');
    fpool.addColorStop(1, 'rgba(220,110,50,0)');
    g.save();
    g.translate(0, fy0); g.scale(1, 0.34); g.translate(0, -fy0);
    g.fillStyle = fpool;
    g.fillRect(fx0 - W * 0.16, fy0 - W * 0.16, W * 0.32, W * 0.32);
    g.restore();
    const fh = H * 0.20;
    person(g, fx0 - H * 0.082, fy0 + H * 0.012, fh * 0.85, { robe: [92, 62, 88], hood: [60, 40, 62], sit: true, lit: 1, face: 1, staff: -1 });
    person(g, fx0 + H * 0.090, fy0 + H * 0.016, fh * 0.80, { robe: [70, 84, 110], hood: [44, 54, 78], sit: true, lit: -1, face: -1, beard: [40, 30, 28] });
    person(g, fx0 + H * 0.196, fy0 - H * 0.010, fh * 1.00, { robe: [120, 90, 62], hood: [82, 58, 44], lit: -1, face: -1, staff: 1, beard: [52, 38, 30] });
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2;
      rock(g, fx0 + Math.cos(a) * H * 0.034, fy0 + H * 0.004 + Math.sin(a) * H * 0.010, H * 0.0095, rand, wobR, [210, 140, 90]);
    }
    g.strokeStyle = rgba([60, 40, 32], 1);
    g.lineWidth = Math.max(2, H * 0.006);
    g.lineCap = 'round';
    g.beginPath(); g.moveTo(fx0 - H * 0.026, fy0 + H * 0.004); g.lineTo(fx0 + H * 0.026, fy0 - H * 0.004);
    g.moveTo(fx0 - H * 0.024, fy0 - H * 0.005); g.lineTo(fx0 + H * 0.024, fy0 + H * 0.006); g.stroke();

    // keře a kameny před chlévkem (střední plán, pod tvory)
    const mids = [[0.12, 0.74, 'bush'], [0.33, 0.70, 'rock'], [0.90, 0.72, 'bush'], [0.96, 0.78, 'rock'], [0.045, 0.68, 'rock'], [0.40, 0.745, 'bush']];
    for (const [fx, fyy, kind] of mids) {
      const d = depthScale(fyy);
      if (kind === 'bush') bush(g, W * fx, H * fyy, H * (0.030 + 0.055 * d), rand, [42, 66, 70]);
      else rock(g, W * fx, H * fyy, H * (0.025 + 0.06 * d), rand, wobR);
    }
    return { canvas: c, y0, stable };
  }

  // Popředí NAD tvory: tmavé kameny, tráva a listy v rozích
  function buildFront(W, H, rand) {
    const y0 = Math.round(H * 0.74);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const wob = waveFn(rand, 3, 1.2, 0.5);
    const aspect = W / H;
    for (const [fx, s] of [[0.012, 0.14], [0.985, 0.12], [0.10, 0.07], [0.90, 0.075]]) {
      rock(g, W * fx, H * 1.015, H * s, rand, wob, [90, 100, 150]);
    }
    bush(g, W * 0.045, H * 1.01, H * 0.10, rand, [34, 56, 62]);
    bush(g, W * 0.955, H * 1.01, H * 0.09, rand, [34, 56, 62]);
    for (let i = 0; i < Math.round(aspect * 28); i++) {
      const edge = rand() < 0.5 ? rand() * 0.26 : 0.74 + rand() * 0.26;
      tuft(g, W * edge, H * (0.985 + rand() * 0.02), H * (0.05 + 0.04 * rand()),
           rgba(mix(P.GRASS[0], P.GRASS[2], rand() * 0.8), 1), rand, 6);
    }
    return { canvas: c, y0 };
  }

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const sky = buildSky(W, H, rand);
    const moon = buildMoon(W, H);
    const land = buildLand(W, H, rand);
    const ground = buildGround(W, H, rand);
    const front = buildFront(W, H, rand);

    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.55, H * 0.55, H * 0.40, W * 0.55, H * 0.55, H * 1.00);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, P.vignette);
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);

    const flies = [];
    for (let i = 0; i < 26; i++) {
      flies.push({ cx: rand(), cy: 0.52 + rand() * 0.45, ax: 0.02 + rand() * 0.05, ay: 0.015 + rand() * 0.04,
                   sp: 0.10 + rand() * 0.16, ph: rand() * 6.28, tw: 0.8 + rand() * 1.4 });
    }
    const sparks = [];
    for (let i = 0; i < 16; i++) sparks.push({ ph: rand(), sp: 0.35 + rand() * 0.4, dx: (rand() - 0.5) * 2, r: 0.8 + rand() * 1.2 });
    const dust = [];
    for (let i = 0; i < 14; i++) dust.push({ ph: rand(), sp: 0.04 + rand() * 0.05, dx: (rand() - 0.5) * 0.04, r: 0.7 + rand() * 1.1 });
    const shoot = { next: 8 + rand() * 12 };
    return { W, H, sky, moon, land, ground, front, vig, flies, sparks, dust, shoot, rand };
  }

  // --------------------------------------------------------------- dynamic

  // Betlémská hvězda: paprsek k střeše, ohon do dálky, pulzující záře a kříž
  // dlouhých paprsků; kreslí se pod krajinu, takže se paprsek ztrácí ve střeše.
  function drawStar(ctx, W, H, t, S) {
    const sx = W * STAR.x, sy = H * STAR.y;
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.3), fl = 0.5 + 0.5 * Math.sin(t * 3.1 + 1.7);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    // ohon: dlouhý zakřivený pruh do pravého horního rohu
    const tl = Math.min(W * 0.46, H * 0.9);
    const ex = sx + tl, ey = sy - tl * 0.12;
    const tg = ctx.createLinearGradient(sx, sy, ex, ey);
    tg.addColorStop(0, 'rgba(255,238,190,' + (0.42 + 0.08 * pulse) + ')');
    tg.addColorStop(0.35, 'rgba(255,214,150,0.16)');
    tg.addColorStop(1, 'rgba(255,200,140,0)');
    ctx.fillStyle = tg;
    ctx.beginPath();
    ctx.moveTo(sx, sy - H * 0.010);
    ctx.quadraticCurveTo(sx + tl * 0.55, sy - H * 0.040 - tl * 0.025, ex, ey - H * 0.040);
    ctx.lineTo(ex, ey + H * 0.040);
    ctx.quadraticCurveTo(sx + tl * 0.50, sy + H * 0.030 + tl * 0.002, sx, sy + H * 0.010);
    ctx.closePath();
    ctx.fill();
    for (let i = 0; i < 18; i++) {
      const p = (i / 18 + t * 0.025) % 1;
      const px = sx + tl * (0.06 + p * 0.9), py = sy - tl * 0.12 * p - Math.sin(p * 9 + i) * H * 0.012;
      ctx.fillStyle = 'rgba(255,236,190,' + (0.5 * (1 - p) * (0.5 + 0.5 * Math.sin(t * 2 + i * 1.9))) + ')';
      ctx.beginPath(); ctx.arc(px, py, H * 0.0014 * (1.4 - p), 0, Math.PI * 2); ctx.fill();
    }
    // záře a paprsky
    glow(ctx, sx, sy, H * (0.20 + 0.025 * pulse), [255, 232, 170], 0.55 + 0.12 * pulse);
    glow(ctx, sx, sy, H * 0.06, [255, 252, 232], 0.95);
    const rays = [[0, 0.16, 0.012], [Math.PI / 2, 0.21, 0.014], [Math.PI, 0.16, 0.012], [Math.PI * 1.5, 0.12, 0.012],
                  [Math.PI / 4, 0.075, 0.008], [Math.PI * 0.75, 0.075, 0.008], [Math.PI * 1.25, 0.075, 0.008], [Math.PI * 1.75, 0.075, 0.008]];
    rays.forEach((r, i) => {
      const L = H * r[1] * (0.86 + 0.14 * (i % 2 ? fl : pulse));
      const w = H * r[2];
      const gr = ctx.createLinearGradient(sx, sy, sx + Math.cos(r[0]) * L, sy + Math.sin(r[0]) * L);
      gr.addColorStop(0, 'rgba(255,252,232,0.95)');
      gr.addColorStop(1, 'rgba(255,230,170,0)');
      ctx.fillStyle = gr;
      ctx.beginPath();
      const px = -Math.sin(r[0]) * w, py = Math.cos(r[0]) * w;
      ctx.moveTo(sx + px, sy + py);
      ctx.lineTo(sx + Math.cos(r[0]) * L, sy + Math.sin(r[0]) * L);
      ctx.lineTo(sx - px, sy - py);
      ctx.closePath();
      ctx.fill();
    });
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = 'rgb(255,254,244)';
    ctx.beginPath(); ctx.arc(sx, sy, H * 0.0105, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // Paprsek od hvězdy na střechu chlévku; kreslí se nad krajinou, aby se
  // neztratil za skálou, a k střeše slábne.
  function drawBeam(ctx, W, H, t, S) {
    const sx = W * STAR.x, sy = H * STAR.y;
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.3);
    const ST = S.ground.stable;
    const tx = ST.sx, ty = ST.apexY + ST.u * 0.02;
    const wTop = H * 0.006, wBot = ST.u * 0.17;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const bg = ctx.createLinearGradient(sx, sy, tx, ty);
    bg.addColorStop(0, 'rgba(255,240,196,' + (0.30 + 0.05 * pulse) + ')');
    bg.addColorStop(0.60, 'rgba(255,226,170,' + (0.10 + 0.03 * pulse) + ')');
    bg.addColorStop(1, 'rgba(255,214,150,0)');
    ctx.fillStyle = bg;
    const dx = tx - sx, dy = ty - sy, len = Math.hypot(dx, dy), nx = -dy / len, ny = dx / len;
    ctx.beginPath();
    ctx.moveTo(sx + nx * wTop, sy + ny * wTop);
    ctx.lineTo(tx + nx * wBot, ty + ny * wBot);
    ctx.lineTo(tx - nx * wBot, ty - ny * wBot);
    ctx.lineTo(sx - nx * wTop, sy - ny * wTop);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawSkyLife(ctx, W, H, t, S) {
    ctx.save();
    for (const s of S.sky.stars) {
      const a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * s.sp + s.ph));
      ctx.fillStyle = s.warm ? 'rgba(255,230,196,' + a + ')' : 'rgba(220,232,255,' + a + ')';
      const x = s.x * W, y = s.y * H, r = s.r * (1.1 + a * 0.5);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      if (s.r > H * 0.0022) {
        ctx.strokeStyle = 'rgba(230,238,255,' + a * 0.5 + ')';
        ctx.lineWidth = Math.max(0.6, s.r * 0.35);
        ctx.beginPath(); ctx.moveTo(x - r * 3.2, y); ctx.lineTo(x + r * 3.2, y); ctx.moveTo(x, y - r * 3.2); ctx.lineTo(x, y + r * 3.2); ctx.stroke();
      }
    }
    // občasná padající hvězda
    const sh = S.shoot;
    if (t > sh.next) {
      const p = (t - sh.next) / 1.1;
      if (p >= 1) { sh.next = t + 14 + S.rand() * 22; sh.sx = 0.08 + S.rand() * 0.5; sh.sy = 0.04 + S.rand() * 0.14; }
      else {
        if (sh.sx == null) { sh.sx = 0.15; sh.sy = 0.08; }
        const x = (sh.sx + p * 0.16) * W, y = (sh.sy + p * 0.07) * H;
        const g = ctx.createLinearGradient(x, y, x - W * 0.09, y - H * 0.04);
        g.addColorStop(0, 'rgba(255,255,255,' + (1 - p) + ')');
        g.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.strokeStyle = g; ctx.lineWidth = Math.max(1, H * 0.0025);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - W * 0.09, y - H * 0.04); ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawWindows(ctx, W, H, t, S) {
    const L = S.land;
    ctx.save();
    ctx.translate(0, L.y0);
    for (const w of L.wins) {
      if (!w.on) continue;
      const a = 0.65 + 0.35 * Math.sin(t * (1.2 + (w.ph % 1)) + w.ph * 3);
      ctx.fillStyle = 'rgba(255,200,110,' + (0.55 + 0.4 * a) + ')';
      ctx.fillRect(w.x, w.y, w.s, w.s * 1.25);
    }
    ctx.restore();
  }

  function flicker(t, k) {
    return 0.80 + 0.12 * Math.sin(t * 7.3 + k) + 0.08 * Math.sin(t * 13.1 + k * 2.3) + 0.04 * Math.sin(t * 23.7 + k * 5.1);
  }

  // Oheň a záře: přidává se světlem nad statickou krajinu, pod tvory.
  function drawFire(ctx, W, H, t, S) {
    const ST = S.ground.stable;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const fl = flicker(t, 0);
    // záře jeslí a lucerny
    glow(ctx, ST.baby.x, ST.baby.y, ST.u * 0.26, [255, 200, 120], 0.30 * fl);
    glow(ctx, ST.baby.x, ST.baby.y, ST.u * 0.07, [255, 244, 210], 0.55 + 0.1 * Math.sin(t * 1.7));
    for (let i = 0; i < ST.lanterns.length; i++) {
      const l = ST.lanterns[i];
      glow(ctx, l.x, l.y, ST.u * 0.085, [255, 190, 100], 0.55 * flicker(t, i * 3 + 1));
    }
    glow(ctx, ST.sx, H * STABLE.floor + H * 0.03, W * 0.20, [255, 170, 90], 0.14 * fl, 0.30);

    // oheň pastýřů
    const fx = W * FIRE.x, fy = H * FIRE.y, fh = H * 0.052;
    const f2 = flicker(t, 4);
    glow(ctx, fx, fy - fh * 0.5, H * 0.20, [255, 160, 70], 0.34 * f2);
    glow(ctx, fx, fy + H * 0.008, W * 0.11, [255, 150, 70], 0.22 * f2, 0.32);
    for (let i = 0; i < 6; i++) {
      const ph = i * 1.37;
      const sway = Math.sin(t * (3.2 + i * 0.6) + ph) * fh * 0.12;
      const hh = fh * (0.55 + 0.45 * (0.5 + 0.5 * Math.sin(t * (5 + i) + ph))) * (i === 2 ? 1.15 : 0.9 - Math.abs(i - 2.5) * 0.08);
      const bx = fx + (i - 2.5) * fh * 0.22, ww = fh * (0.20 - Math.abs(i - 2.5) * 0.02);
      const cols = [[255, 110, 40, 0.75], [255, 170, 60, 0.85], [255, 232, 150, 0.9]];
      for (let k = 0; k < 3; k++) {
        const s = 1 - k * 0.28;
        ctx.fillStyle = 'rgba(' + cols[k][0] + ',' + cols[k][1] + ',' + cols[k][2] + ',' + cols[k][3] * 0.8 + ')';
        ctx.beginPath();
        ctx.moveTo(bx - ww * s, fy);
        ctx.quadraticCurveTo(bx - ww * s * 1.1 + sway * 0.4, fy - hh * 0.5 * s, bx + sway * s, fy - hh * s);
        ctx.quadraticCurveTo(bx + ww * s * 1.1 + sway * 0.4, fy - hh * 0.5 * s, bx + ww * s, fy);
        ctx.closePath();
        ctx.fill();
      }
    }
    for (let i = 0; i < S.sparks.length; i++) {
      const sp = S.sparks[i];
      const p = (sp.ph + t * sp.sp) % 1;
      const x = fx + (sp.dx * fh * 0.6) * p + Math.sin(t * 2 + i) * fh * 0.15 * p;
      const y = fy - fh * 0.5 - p * fh * 3.4;
      ctx.fillStyle = 'rgba(255,' + Math.round(180 - p * 80) + ',90,' + (0.95 * (1 - p)) + ')';
      ctx.beginPath(); ctx.arc(x, y, Math.max(0.6, H * 0.0014 * sp.r * (1 - p * 0.6)), 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  function draw(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;
    ctx.drawImage(S.sky.canvas, 0, 0);
    drawSkyLife(ctx, W, H, t, S);
    ctx.drawImage(S.moon.canvas, W * 0.135 - S.moon.r, H * 0.135 - S.moon.r);
    drawStar(ctx, W, H, t, S);
    ctx.drawImage(S.land.canvas, 0, S.land.y0);
    drawWindows(ctx, W, H, t, S);
    ctx.drawImage(S.ground.canvas, 0, S.ground.y0);
    drawBeam(ctx, W, H, t, S);
    drawFire(ctx, W, H, t, S);
  }

  function drawFront(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;
    ctx.drawImage(S.front.canvas, 0, S.front.y0);
    // teplé světlo z chlévku obtéká tvory před ním
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    glow(ctx, W * STABLE.x, H * (STABLE.floor + 0.06), W * 0.20, [255, 170, 90], 0.07 * flicker(t, 2), 0.50);
    glow(ctx, W * FIRE.x, H * (FIRE.y + 0.05), W * 0.10, [255, 160, 80], 0.07 * flicker(t, 5), 0.50);
    ctx.restore();
    // světlušky a jiskry
    ctx.save();
    for (const f of S.flies) {
      const u = t * f.sp + f.ph;
      const x = (f.cx + Math.sin(u) * f.ax + Math.sin(u * 2.3) * f.ax * 0.3) * W;
      const y = (f.cy + Math.sin(u * 1.4) * f.ay) * H;
      const a = 0.2 + 0.8 * Math.max(0, Math.sin(t * f.tw + f.ph * 2));
      glow(ctx, x, y, H * 0.012, [255, 236, 140], 0.65 * a);
      ctx.fillStyle = 'rgba(255,250,200,' + a + ')';
      ctx.beginPath(); ctx.arc(x, y, Math.max(0.8, H * 0.0018), 0, Math.PI * 2); ctx.fill();
    }
    for (const d of S.dust) {
      const p = (d.ph + t * d.sp) % 1;
      const x = (0.62 + d.dx * 6 + Math.sin(t * 0.4 + d.ph * 9) * 0.04) * W;
      const y = (STABLE.floor - 0.02 - p * 0.30) * H;
      ctx.fillStyle = 'rgba(255,214,150,' + (0.55 * Math.sin(Math.PI * p)) + ')';
      ctx.beginPath(); ctx.arc(x, y, Math.max(0.7, H * 0.0012 * d.r), 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
    ctx.drawImage(S.vig, 0, 0);
  }

  return { draw, drawFront, sun: { x: STAR.x, y: STAR.y }, depthScale };
}
