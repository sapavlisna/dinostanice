/* Zasněžená náves o Mikuláši — malovaná krajina pro 2D plátno pod 3D tvory.

   ES modul s továrnou `create()`; vrací `{draw, drawFront, sun, depthScale}`
   stejně jako forest.js. Rozvržení (podíl výšky plátna):
     0,00–0,46  soumračná obloha, hvězdy, měsíc, vzdálené zasněžené kopce
     0,40–0,53  smrkový les v oparu a vzdálená řada chalup s kostelem
     0,50–1,00  sníh: náves s vyšlapanou stopou (pathX), plot, lucerny,
                sněhuláci, smrčky, boční chalupy a vánoční strom (po y řazené)
     0,70 0,815 0,93  dráhy tvorů — vše, co leží na zemi, má patu nad 0,69,
                takže tvorové jdou před kulisou, ne za ní
   Statické dílky jsou předkreslené, živé jsou hvězdy, kouř z komínů, mihotání
   oken a lucerny, světýlka na stromě a padající sníh (dál vzadu v draw(),
   vpředu v drawFront()). */

const SEED = 20261205;

const HORIZON = 0.46;
const GROUND_TOP = 0.50;
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
function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
function mix(a, b, k) {
  return [Math.round(lerp(a[0], b[0], k)), Math.round(lerp(a[1], b[1], k)), Math.round(lerp(a[2], b[2], k))];
}
function shade(c, k) { return [Math.round(c[0] * k), Math.round(c[1] * k), Math.round(c[2] * k)]; }

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

function waveFn(rand, octaves, baseFreq, persistence) {
  const parts = []; let f = baseFreq, a = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    parts.push([f, a, rand() * Math.PI * 2]);
    norm += a; f *= 2.13; a *= persistence;
  }
  return function (x) {
    let s = 0;
    for (let j = 0; j < parts.length; j++) s += parts[j][1] * Math.sin(x * parts[j][0] + parts[j][2]);
    return s / norm;
  };
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

// Vyšlapaná stopa přes náves: z dálky uprostřed ke spodnímu okraji. Trasy
// tvorů v scenes/mikulas/render.js ji sledují.
export function pathX(yf) {
  const u = clamp((yf - 0.53) / 0.47, 0, 1.2);
  return 0.47 - 0.10 * Math.pow(u, 0.9) + 0.03 * Math.sin(u * 5.0) * u;
}
export function pathHalf(yf) {
  return 0.012 + 0.140 * Math.pow(clamp((yf - 0.53) / 0.47, 0, 1.2), 1.5);
}

const P = {
  SKY: [[20, 22, 70], [52, 44, 112], [118, 72, 138], [214, 124, 126], [250, 178, 128]],
  HAZE: [196, 150, 168],
  SNOW: [238, 242, 252], SNOW_SHADE: [172, 184, 222], SNOW_DEEP: [138, 152, 204],
  PATH: [184, 186, 218], PATH_DARK: [140, 144, 190],
  SPRUCE: [28, 58, 66], SPRUCE_FAR: [52, 72, 108],
  WALLS: [[214, 164, 104], [182, 90, 72], [226, 206, 160], [132, 150, 178], [150, 172, 126], [196, 128, 96]],
  ROOF_SNOW: [244, 247, 255],
  WINDOW: [255, 218, 120], WINDOW_HOT: [255, 170, 60],
  WOOD: [112, 78, 54],
  ORNAMENT: [[220, 40, 52], [250, 200, 60], [70, 130, 230], [200, 70, 200], [60, 200, 140]],
};

// ----------------------------------------------------------------- stromy

// Smrk se sněhem: tmavé patro, na jeho horní části sněhová čepice
function drawSpruce(g, x, baseY, h, w, body, snow, rand, tiers) {
  tiers = tiers || (6 + Math.floor(rand() * 3));
  g.fillStyle = rgba(shade(body, 0.7), 1);
  g.fillRect(x - h * 0.016, baseY - h * 0.16, h * 0.032, h * 0.16);
  for (let i = 0; i < tiers; i++) {
    const f = i / tiers;
    const ty = baseY - h * 0.08 - f * h * 0.74;
    const tw = w * (1 - f * 0.80);
    const th = h * (0.27 - f * 0.07);
    g.fillStyle = rgba(body, 1);
    g.beginPath();
    g.moveTo(x, ty - th);
    g.lineTo(x + tw, ty);
    g.lineTo(x + tw * 0.35, ty + h * 0.02);
    g.lineTo(x - tw * 0.35, ty + h * 0.02);
    g.lineTo(x - tw, ty);
    g.closePath();
    g.fill();
    g.fillStyle = rgba(snow, 1);
    g.beginPath();
    g.moveTo(x, ty - th);
    g.lineTo(x + tw * 0.62, ty - th * 0.36);
    g.quadraticCurveTo(x + tw * 0.40, ty - th * 0.50, x + tw * 0.22, ty - th * 0.34);
    g.quadraticCurveTo(x + tw * 0.05, ty - th * 0.50, x - tw * 0.16, ty - th * 0.34);
    g.quadraticCurveTo(x - tw * 0.40, ty - th * 0.52, x - tw * 0.62, ty - th * 0.36);
    g.closePath();
    g.fill();
    g.fillStyle = rgba(mix(snow, P.SNOW_SHADE, 0.7), 0.55);
    g.beginPath();
    g.moveTo(x, ty - th);
    g.lineTo(x - tw * 0.62, ty - th * 0.36);
    g.lineTo(x - tw * 0.22, ty - th * 0.40);
    g.closePath();
    g.fill();
  }
}

function drawStar(g, x, y, r, col) {
  g.fillStyle = col;
  g.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + i * Math.PI / 5;
    const rr = i % 2 ? r * 0.42 : r;
    g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
  }
  g.closePath();
  g.fill();
}

// Vánoční strom: patra, girlandy, ozdoby a hvězda; vrací polohy světýlek
function drawXmasTree(g, x, baseY, h, rand) {
  const w = h * 0.34;
  const lights = [];
  g.fillStyle = 'rgba(70,90,150,0.30)';
  g.beginPath(); g.ellipse(x + w * 0.25, baseY + h * 0.005, w * 1.25, h * 0.045, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = rgba(P.WOOD, 1);
  g.fillRect(x - h * 0.028, baseY - h * 0.10, h * 0.056, h * 0.10);
  const tiers = 6;
  for (let i = 0; i < tiers; i++) {
    const f = i / tiers;
    const ty = baseY - h * 0.07 - f * h * 0.80;
    const tw = w * (1 - f * 0.78);
    const th = h * 0.26 * (1 - f * 0.25);
    const grad = g.createLinearGradient(x - tw, 0, x + tw, 0);
    grad.addColorStop(0, 'rgb(14,60,52)');
    grad.addColorStop(0.55, 'rgb(28,96,70)');
    grad.addColorStop(1, 'rgb(44,120,84)');
    g.fillStyle = grad;
    g.beginPath();
    g.moveTo(x, ty - th);
    g.lineTo(x + tw, ty);
    for (let k = 1; k <= 4; k++) {
      g.quadraticCurveTo(x + tw * (1 - (k - 0.5) / 4 * 2), ty + h * 0.03, x + tw * (1 - k / 4 * 2), ty);
    }
    g.closePath();
    g.fill();
    g.fillStyle = rgba(P.SNOW, 0.95);
    g.beginPath();
    g.moveTo(x, ty - th);
    g.lineTo(x + tw * 0.40, ty - th * 0.60);
    g.quadraticCurveTo(x + tw * 0.2, ty - th * 0.66, x + tw * 0.06, ty - th * 0.54);
    g.quadraticCurveTo(x - tw * 0.14, ty - th * 0.68, x - tw * 0.40, ty - th * 0.60);
    g.closePath();
    g.fill();
    // girlanda přes patro
    g.strokeStyle = 'rgba(250,206,80,0.95)';
    g.lineWidth = Math.max(1.2, h * 0.006);
    g.beginPath();
    g.moveTo(x - tw * 0.80, ty - th * 0.12);
    g.quadraticCurveTo(x, ty + th * 0.14, x + tw * 0.80, ty - th * 0.12);
    g.stroke();
    for (let k = 0; k < 4; k++) {
      const u = (k + 0.5) / 4;
      const px = x + tw * (u * 1.5 - 0.75);
      const py = ty - th * 0.08 + Math.sin(u * Math.PI) * th * 0.14;
      const col = P.ORNAMENT[(i + k) % P.ORNAMENT.length];
      g.fillStyle = rgba(col, 1);
      g.beginPath(); g.arc(px, py + h * 0.012, h * 0.0165, 0, Math.PI * 2); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.7)';
      g.beginPath(); g.arc(px - h * 0.005, py + h * 0.007, h * 0.0055, 0, Math.PI * 2); g.fill();
      lights.push({ x: px + h * 0.02, y: py - h * 0.016, col: col, ph: rand() * 6.28 });
    }
  }
  drawStar(g, x, baseY - h * 1.0, h * 0.055, 'rgb(255,214,84)');
  lights.push({ x, y: baseY - h * 1.0, col: [255, 220, 100], ph: 0, big: true });
  // dárky pod stromem
  const gifts = [[-0.17, 0.045, [200, 50, 60]], [0.02, 0.035, [60, 120, 210]], [0.16, 0.05, [70, 170, 110]]];
  for (const [dx, s, col] of gifts) {
    const gx = x + dx * h, gy = baseY + h * 0.005, gs = h * s;
    g.fillStyle = rgba(col, 1);
    g.fillRect(gx - gs, gy - gs * 1.5, gs * 2, gs * 1.5);
    g.fillStyle = 'rgba(250,224,120,1)';
    g.fillRect(gx - gs * 0.16, gy - gs * 1.5, gs * 0.32, gs * 1.5);
    g.fillRect(gx - gs, gy - gs * 0.95, gs * 2, gs * 0.28);
  }
  return lights;
}

// ------------------------------------------------------------------ domy

// Chalupa v čelním pohledu s viditelnou boční stěnou. Vrací okna a komín pro živé
// efekty (mihotání, kouř).
function drawHouse(g, o, rand) {
  const { x, by, w, h } = o;
  const haze = o.haze || 0;
  const hz = (c) => mix(c, P.HAZE, haze);
  const rh = o.roofH || h * 0.62;
  const side = o.side || 0;
  const sw = o.sw || w * 0.32;
  const wall = o.wall;
  const out = { lights: [], chimney: null };

  g.fillStyle = 'rgba(60,70,130,0.28)';
  g.beginPath(); g.ellipse(x + w / 2 + side * sw * 0.3, by + h * 0.03, w * 0.62 + sw * 0.5, h * 0.09, 0, 0, Math.PI * 2); g.fill();

  if (side) {
    const sx = side > 0 ? x + w : x;
    g.fillStyle = rgba(hz(shade(wall, 0.58)), 1);
    g.beginPath();
    g.moveTo(sx, by); g.lineTo(sx + side * sw, by - sw * 0.14);
    g.lineTo(sx + side * sw, by - h - sw * 0.14); g.lineTo(sx, by - h);
    g.closePath(); g.fill();
    const rx = (side > 0 ? x + w : x) + side * w * 0.10;
    g.fillStyle = rgba(hz(shade(P.ROOF_SNOW, 0.78)), 1);
    g.beginPath();
    g.moveTo(x + w / 2, by - h - rh);
    g.lineTo(rx, by - h);
    g.lineTo(rx + side * sw, by - h - sw * 0.14);
    g.lineTo(x + w / 2 + side * sw, by - h - rh - sw * 0.14);
    g.closePath(); g.fill();
    g.strokeStyle = rgba(hz([92, 98, 150]), 0.9);
    g.lineWidth = Math.max(1, h * 0.012);
    g.beginPath(); g.moveTo(rx, by - h); g.lineTo(rx + side * sw, by - h - sw * 0.14); g.stroke();
  }

  const wg = g.createLinearGradient(0, by - h, 0, by);
  wg.addColorStop(0, rgba(hz(shade(wall, 0.92)), 1));
  wg.addColorStop(1, rgba(hz(shade(wall, 0.74)), 1));
  g.fillStyle = wg;
  g.fillRect(x, by - h, w, h);
  g.fillStyle = rgba(hz(shade(wall, 0.55)), 0.35);
  for (let i = 1; i < 6; i++) g.fillRect(x, by - h + (h * i) / 6, w, Math.max(1, h * 0.008));

  const ov = w * 0.10;
  const rg = g.createLinearGradient(0, by - h - rh, 0, by - h);
  rg.addColorStop(0, rgba(hz(P.ROOF_SNOW), 1));
  rg.addColorStop(1, rgba(hz(mix(P.ROOF_SNOW, P.SNOW_SHADE, 0.45)), 1));
  g.fillStyle = rg;
  g.beginPath();
  g.moveTo(x + w / 2, by - h - rh);
  g.lineTo(x + w + ov, by - h + h * 0.02);
  g.lineTo(x - ov, by - h + h * 0.02);
  g.closePath(); g.fill();
  g.fillStyle = rgba(hz([84, 70, 96]), 1);
  g.fillRect(x - ov * 0.7, by - h + h * 0.02, w + ov * 1.4, h * 0.035);
  g.fillStyle = rgba(hz(P.ROOF_SNOW), 1);
  for (let i = 0; i < 7; i++) {
    const px = x - ov + ((w + 2 * ov) * (i + 0.5)) / 7;
    g.beginPath(); g.arc(px, by - h + h * 0.02, h * 0.035, Math.PI, 0); g.fill();
  }
  g.fillStyle = rgba(hz([210, 226, 255]), 0.9);
  for (let i = 0; i < 5; i++) {
    const px = x - ov * 0.6 + (w + ov * 1.2) * rand();
    const il = h * (0.03 + 0.05 * rand());
    g.beginPath();
    g.moveTo(px - h * 0.008, by - h + h * 0.055); g.lineTo(px + h * 0.008, by - h + h * 0.055); g.lineTo(px, by - h + h * 0.055 + il);
    g.closePath(); g.fill();
  }

  if (o.chimney !== false) {
    const cxm = x + w * (o.chimneyAt || 0.72), cw = w * 0.12;
    const cyBase = by - h - rh * (1 - Math.abs(cxm - (x + w / 2)) / (w / 2 + ov)) + h * 0.02;
    g.fillStyle = rgba(hz(shade(wall, 0.5)), 1);
    g.fillRect(cxm - cw / 2, cyBase - h * 0.22, cw, h * 0.26);
    g.fillStyle = rgba(hz(P.ROOF_SNOW), 1);
    g.beginPath(); g.ellipse(cxm, cyBase - h * 0.22, cw * 0.62, h * 0.032, 0, 0, Math.PI * 2); g.fill();
    out.chimney = { x: cxm, y: cyBase - h * 0.25, s: h };
  }

  const wins = o.windows || [[0.2, 0.30], [0.62, 0.30]];
  const ws = h * 0.20;
  for (const [fx, fy] of wins) {
    const cx = x + w * fx, cy = by - h * (1 - fy);
    const lit = o.lit !== false;
    if (lit) {
      const glow = g.createRadialGradient(cx + ws / 2, cy + ws / 2, 0, cx + ws / 2, cy + ws / 2, ws * 2.2);
      glow.addColorStop(0, rgba(P.WINDOW_HOT, 0.45 * (1 - haze * 0.5)));
      glow.addColorStop(1, rgba(P.WINDOW_HOT, 0));
      g.fillStyle = glow;
      g.fillRect(cx - ws * 2, cy - ws * 2, ws * 5, ws * 5);
    }
    g.fillStyle = rgba(hz(shade(wall, 0.4)), 1);
    g.fillRect(cx - ws * 0.08, cy - ws * 0.08, ws * 1.16, ws * 1.16);
    const win = g.createLinearGradient(0, cy, 0, cy + ws);
    win.addColorStop(0, rgba(mix(P.WINDOW, P.HAZE, haze * 0.4), 1));
    win.addColorStop(1, rgba(mix(P.WINDOW_HOT, P.HAZE, haze * 0.4), 1));
    g.fillStyle = lit ? win : rgba([60, 70, 120], 1);
    g.fillRect(cx, cy, ws, ws);
    g.fillStyle = rgba(hz(shade(wall, 0.38)), 1);
    g.fillRect(cx + ws * 0.46, cy, ws * 0.08, ws);
    g.fillRect(cx, cy + ws * 0.46, ws, ws * 0.08);
    g.fillStyle = rgba(P.ROOF_SNOW, 0.95);
    g.beginPath(); g.ellipse(cx + ws / 2, cy + ws * 1.1, ws * 0.7, ws * 0.12, 0, 0, Math.PI * 2); g.fill();
    if (lit) out.lights.push({ x: cx + ws / 2, y: cy + ws / 2, r: ws * 2.4, ph: rand() * 6.28 });
  }

  if (o.door !== false) {
    const dw = w * 0.16, dh = h * 0.42, dx = x + w * (o.doorAt || 0.42);
    g.fillStyle = rgba(hz([84, 56, 40]), 1);
    g.fillRect(dx, by - dh, dw, dh);
    g.fillStyle = rgba(hz([255, 190, 90]), 0.9 - haze * 0.4);
    g.fillRect(dx + dw * 0.18, by - dh * 0.88, dw * 0.64, dh * 0.34);
  }
  g.fillStyle = rgba(P.SNOW, 1);
  g.beginPath(); g.ellipse(x + w / 2, by + h * 0.005, w * 0.56, h * 0.045, 0, Math.PI, 0); g.fill();
  return out;
}

function drawChurch(g, x, by, s, haze, rand) {
  const hz = (c) => mix(c, P.HAZE, haze);
  const out = { lights: [], chimney: null };
  const wall = [220, 208, 190];
  const nw = s * 1.3, nh = s * 0.52;
  g.fillStyle = rgba(hz(shade(wall, 0.82)), 1);
  g.fillRect(x - nw / 2, by - nh, nw, nh);
  g.fillStyle = rgba(hz(P.ROOF_SNOW), 1);
  g.beginPath();
  g.moveTo(x - nw / 2 - s * 0.05, by - nh + s * 0.02); g.lineTo(x - nw * 0.3, by - nh - s * 0.22);
  g.lineTo(x + nw * 0.3, by - nh - s * 0.22); g.lineTo(x + nw / 2 + s * 0.05, by - nh + s * 0.02);
  g.closePath(); g.fill();
  const tw = s * 0.42, th = s * 1.05;
  const tx = x - nw * 0.28;
  g.fillStyle = rgba(hz(wall), 1);
  g.fillRect(tx - tw / 2, by - th, tw, th);
  g.fillStyle = rgba(hz(P.ROOF_SNOW), 1);
  g.beginPath();
  g.moveTo(tx - tw * 0.62, by - th + s * 0.02); g.lineTo(tx, by - th - s * 0.78); g.lineTo(tx + tw * 0.62, by - th + s * 0.02);
  g.closePath(); g.fill();
  g.fillStyle = rgba(hz(shade(P.ROOF_SNOW, 0.8)), 1);
  g.beginPath();
  g.moveTo(tx, by - th - s * 0.78); g.lineTo(tx + tw * 0.62, by - th + s * 0.02); g.lineTo(tx + tw * 0.12, by - th + s * 0.02);
  g.closePath(); g.fill();
  g.strokeStyle = rgba(hz([240, 200, 90]), 1);
  g.lineWidth = Math.max(1.2, s * 0.025);
  g.beginPath(); g.moveTo(tx, by - th - s * 0.78); g.lineTo(tx, by - th - s * 0.93);
  g.moveTo(tx - s * 0.05, by - th - s * 0.87); g.lineTo(tx + s * 0.05, by - th - s * 0.87); g.stroke();
  g.fillStyle = rgba(hz([250, 244, 220]), 1);
  g.beginPath(); g.arc(tx, by - th * 0.80, tw * 0.28, 0, Math.PI * 2); g.fill();
  g.strokeStyle = rgba(hz([60, 50, 70]), 1);
  g.lineWidth = Math.max(1, s * 0.012);
  g.beginPath(); g.moveTo(tx, by - th * 0.80); g.lineTo(tx, by - th * 0.80 - tw * 0.2);
  g.moveTo(tx, by - th * 0.80); g.lineTo(tx + tw * 0.14, by - th * 0.80); g.stroke();
  const arch = (cx, cy, aw, ah) => {
    const glow = g.createRadialGradient(cx, cy, 0, cx, cy, ah * 1.6);
    glow.addColorStop(0, rgba(P.WINDOW_HOT, 0.4));
    glow.addColorStop(1, rgba(P.WINDOW_HOT, 0));
    g.fillStyle = glow;
    g.fillRect(cx - ah * 1.6, cy - ah * 1.6, ah * 3.2, ah * 3.2);
    g.fillStyle = rgba(mix(P.WINDOW, P.HAZE, haze * 0.4), 1);
    g.beginPath();
    g.moveTo(cx - aw / 2, cy + ah / 2); g.lineTo(cx - aw / 2, cy - ah * 0.1);
    g.arc(cx, cy - ah * 0.1, aw / 2, Math.PI, 0); g.lineTo(cx + aw / 2, cy + ah / 2);
    g.closePath(); g.fill();
    out.lights.push({ x: cx, y: cy, r: ah * 1.6, ph: rand() * 6.28 });
  };
  for (let i = 0; i < 3; i++) arch(x - nw * 0.05 + i * nw * 0.22, by - nh * 0.55, s * 0.10, s * 0.24);
  arch(tx, by - th * 0.48, s * 0.09, s * 0.20);
  g.fillStyle = rgba(P.SNOW, 1);
  g.beginPath(); g.ellipse(x, by, nw * 0.7, s * 0.04, 0, Math.PI, 0); g.fill();
  return out;
}

// ------------------------------------------------------- lucerna, plot, sněhulák

function drawLamp(g, x, by, h) {
  g.fillStyle = 'rgba(60,70,130,0.3)';
  g.beginPath(); g.ellipse(x + h * 0.06, by, h * 0.18, h * 0.025, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = 'rgb(44,44,62)';
  g.fillRect(x - h * 0.012, by - h, h * 0.024, h);
  g.fillRect(x - h * 0.04, by - h * 0.06, h * 0.08, h * 0.06);
  const ly = by - h;
  g.fillStyle = 'rgb(44,44,62)';
  g.beginPath(); g.moveTo(x - h * 0.06, ly - h * 0.02); g.lineTo(x + h * 0.06, ly - h * 0.02); g.lineTo(x, ly - h * 0.11); g.closePath(); g.fill();
  const lg = g.createLinearGradient(0, ly, 0, ly + h * 0.12);
  lg.addColorStop(0, 'rgb(255,236,150)'); lg.addColorStop(1, 'rgb(255,190,80)');
  g.fillStyle = lg;
  g.fillRect(x - h * 0.045, ly - h * 0.02, h * 0.09, h * 0.12);
  g.strokeStyle = 'rgb(44,44,62)';
  g.lineWidth = Math.max(1, h * 0.012);
  g.strokeRect(x - h * 0.045, ly - h * 0.02, h * 0.09, h * 0.12);
  g.fillStyle = rgba(P.SNOW, 1);
  g.beginPath(); g.ellipse(x, ly - h * 0.11, h * 0.055, h * 0.016, 0, 0, Math.PI * 2); g.fill();
  return { x, y: ly + h * 0.04, r: h * 0.9 };
}

function drawFence(g, x0, x1, by, h, rise) {
  const n = Math.max(3, Math.round((x1 - x0) / (h * 0.55)));
  const yAt = (x) => by + rise * (x - x0) / (x1 - x0);
  g.fillStyle = 'rgba(60,70,130,0.25)';
  g.fillRect(x0, yAt(x0) + h * 0.01, x1 - x0, h * 0.05);
  for (const f of [0.35, 0.72]) {
    g.fillStyle = rgba(shade(P.WOOD, 0.9), 1);
    g.beginPath();
    g.moveTo(x0, yAt(x0) - h * f - h * 0.05); g.lineTo(x1, yAt(x1) - h * f - h * 0.05);
    g.lineTo(x1, yAt(x1) - h * f); g.lineTo(x0, yAt(x0) - h * f);
    g.closePath(); g.fill();
    g.fillStyle = rgba(P.SNOW, 0.95);
    g.beginPath();
    g.moveTo(x0, yAt(x0) - h * f - h * 0.05); g.lineTo(x1, yAt(x1) - h * f - h * 0.05);
    g.lineTo(x1, yAt(x1) - h * f - h * 0.075); g.lineTo(x0, yAt(x0) - h * f - h * 0.075);
    g.closePath(); g.fill();
  }
  for (let i = 0; i <= n; i++) {
    const px = lerp(x0, x1, i / n), py = yAt(px);
    const pw = h * 0.11;
    g.fillStyle = rgba(P.WOOD, 1);
    g.beginPath();
    g.moveTo(px - pw / 2, py); g.lineTo(px - pw / 2, py - h * 0.95); g.lineTo(px, py - h * 1.05); g.lineTo(px + pw / 2, py - h * 0.95); g.lineTo(px + pw / 2, py);
    g.closePath(); g.fill();
    g.fillStyle = rgba(shade(P.WOOD, 0.7), 0.7);
    g.fillRect(px - pw / 2, py - h * 0.95, pw * 0.3, h * 0.95);
    g.fillStyle = rgba(P.SNOW, 1);
    g.beginPath(); g.ellipse(px, py - h * 1.0, pw * 0.5, h * 0.03, 0, Math.PI, 0); g.fill();
  }
}

function ball(g, x, y, r, base) {
  const gr = g.createRadialGradient(x + r * 0.35, y - r * 0.4, r * 0.1, x, y, r * 1.05);
  gr.addColorStop(0, rgba(P.SNOW, 1));
  gr.addColorStop(0.55, rgba(mix(P.SNOW, base, 0.5), 1));
  gr.addColorStop(1, rgba(base, 1));
  g.fillStyle = gr;
  g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
}

function drawSnowman(g, x, by, h, kind) {
  g.fillStyle = 'rgba(60,70,130,0.3)';
  g.beginPath(); g.ellipse(x - h * 0.1, by, h * 0.38, h * 0.05, 0, 0, Math.PI * 2); g.fill();
  const r1 = h * 0.30, r2 = h * 0.22, r3 = h * 0.16;
  const y1 = by - r1 * 0.95, y2 = y1 - r1 * 0.80 - r2 * 0.55, y3 = y2 - r2 * 0.8 - r3 * 0.55;
  ball(g, x, y1, r1, P.SNOW_SHADE);
  ball(g, x, y2, r2, P.SNOW_SHADE);
  ball(g, x, y3, r3, P.SNOW_SHADE);
  g.strokeStyle = 'rgb(92,64,42)';
  g.lineCap = 'round';
  g.lineWidth = Math.max(1.5, h * 0.025);
  for (const sg of [-1, 1]) {
    g.beginPath(); g.moveTo(x + sg * r2 * 0.85, y2 - r2 * 0.1);
    g.lineTo(x + sg * (r2 + h * 0.20), y2 - r2 * 0.75 * (sg > 0 ? 1 : 0.4));
    g.lineTo(x + sg * (r2 + h * 0.27), y2 - r2 * (sg > 0 ? 1.1 : 0.6));
    g.moveTo(x + sg * (r2 + h * 0.20), y2 - r2 * 0.75 * (sg > 0 ? 1 : 0.4));
    g.lineTo(x + sg * (r2 + h * 0.26), y2 - r2 * (sg > 0 ? 0.45 : 0.1));
    g.stroke();
  }
  g.fillStyle = 'rgb(30,30,40)';
  for (const sg of [-1, 1]) { g.beginPath(); g.arc(x + sg * r3 * 0.38, y3 - r3 * 0.18, h * 0.02, 0, Math.PI * 2); g.fill(); }
  for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(x, y2 - r2 * 0.1 + i * r2 * 0.42, h * 0.02, 0, Math.PI * 2); g.fill(); }
  for (let i = 0; i < 5; i++) {
    const a = Math.PI * (0.2 + i * 0.15);
    g.beginPath(); g.arc(x + Math.cos(a) * r3 * 0.55, y3 + Math.sin(a) * r3 * 0.5 + r3 * 0.12, h * 0.012, 0, Math.PI * 2); g.fill();
  }
  g.fillStyle = 'rgb(250,130,40)';
  g.beginPath(); g.moveTo(x, y3 + r3 * 0.02); g.lineTo(x + h * 0.20, y3 + r3 * 0.20); g.lineTo(x, y3 + r3 * 0.30); g.closePath(); g.fill();
  const scarf = kind === 0 ? [206, 40, 54] : [60, 150, 90];
  g.fillStyle = rgba(scarf, 1);
  g.beginPath(); g.ellipse(x, y3 + r3 * 0.9, r3 * 1.1, r3 * 0.30, 0, 0, Math.PI * 2); g.fill();
  g.fillRect(x + r3 * 0.2, y3 + r3 * 0.9, r3 * 0.5, r3 * 1.4);
  if (kind === 0) {
    g.fillStyle = 'rgb(34,34,44)';
    g.fillRect(x - r3 * 0.95, y3 - r3 * 0.85, r3 * 1.9, r3 * 0.2);
    g.fillRect(x - r3 * 0.58, y3 - r3 * 1.75, r3 * 1.16, r3 * 0.95);
    g.fillStyle = 'rgb(180,40,50)';
    g.fillRect(x - r3 * 0.58, y3 - r3 * 1.05, r3 * 1.16, r3 * 0.16);
  } else {
    g.fillStyle = 'rgb(170,176,196)';
    g.beginPath(); g.moveTo(x - r3 * 0.8, y3 - r3 * 0.6); g.lineTo(x + r3 * 0.8, y3 - r3 * 0.6);
    g.lineTo(x + r3 * 0.6, y3 - r3 * 1.5); g.lineTo(x - r3 * 0.6, y3 - r3 * 1.5); g.closePath(); g.fill();
  }
}

// kupa sněhu: měkká elipsa, světlo shora zprava (měsíc), stín vlevo dole
function drift(g, x, y, rx, ry) {
  const gr = g.createRadialGradient(x + rx * 0.3, y - ry * 0.5, ry * 0.1, x, y, rx);
  gr.addColorStop(0, rgba(P.SNOW, 1));
  gr.addColorStop(0.65, rgba(mix(P.SNOW, P.SNOW_SHADE, 0.45), 1));
  gr.addColorStop(1, rgba(P.SNOW_SHADE, 0));
  g.fillStyle = gr;
  g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); g.fill();
}

// ---------------------------------------------------------------- továrna

export function create() {
  const spritesCache = {};
  function glowSprite(col, size) {
    const key = col.join(',') + ':' + size;
    if (spritesCache[key]) return spritesCache[key];
    const c = makeCanvas(size, size), g = c.getContext('2d');
    const gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gr.addColorStop(0, rgba(col, 1));
    gr.addColorStop(0.35, rgba(col, 0.35));
    gr.addColorStop(1, rgba(col, 0));
    g.fillStyle = gr;
    g.fillRect(0, 0, size, size);
    return (spritesCache[key] = c);
  }

  function buildSky(W, H, rand) {
    const c = makeCanvas(W, H * 0.62), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H * HORIZON);
    [0, 0.34, 0.62, 0.86, 1].forEach((s, i) => grad.addColorStop(s, rgba(P.SKY[i], 1)));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H * HORIZON + 2);
    const glow = g.createRadialGradient(W * 0.26, H * HORIZON, 0, W * 0.26, H * HORIZON, H * 0.55);
    glow.addColorStop(0, 'rgba(255,170,110,0.5)');
    glow.addColorStop(1, 'rgba(255,170,110,0)');
    g.fillStyle = glow;
    g.fillRect(0, 0, W, H * HORIZON + 2);
    const stars = [];
    for (let i = 0; i < 230; i++) {
      const y = Math.pow(rand(), 1.5) * H * 0.34;
      const x = rand() * W;
      const a = 0.25 + 0.55 * rand() * (1 - y / (H * 0.4));
      g.fillStyle = 'rgba(255,250,236,' + a + ')';
      g.fillRect(x, y, Math.max(1, H * 0.0013 * (0.6 + rand())), Math.max(1, H * 0.0013 * (0.6 + rand())));
      if (i < 46) stars.push({ x, y, ph: rand() * 6.28, sp: 0.8 + rand() * 1.8, r: H * (0.0016 + 0.0016 * rand()) });
    }
    const mx = W * 0.80, my = H * 0.15, mr = H * 0.046;
    const mg = g.createRadialGradient(mx, my, mr * 0.5, mx, my, mr * 7);
    mg.addColorStop(0, 'rgba(210,222,255,0.55)');
    mg.addColorStop(0.2, 'rgba(180,196,250,0.22)');
    mg.addColorStop(1, 'rgba(160,180,240,0)');
    g.fillStyle = mg;
    g.beginPath(); g.arc(mx, my, mr * 7, 0, Math.PI * 2); g.fill();
    const mc = makeCanvas(mr * 2.6, mr * 2.6), mg2 = mc.getContext('2d');
    mg2.fillStyle = 'rgb(252,248,226)';
    mg2.beginPath(); mg2.arc(mr * 1.3, mr * 1.3, mr, 0, Math.PI * 2); mg2.fill();
    mg2.globalCompositeOperation = 'destination-out';
    mg2.beginPath(); mg2.arc(mr * 1.3 + mr * 0.42, mr * 1.3 - mr * 0.2, mr * 0.88, 0, Math.PI * 2); mg2.fill();
    g.drawImage(mc, mx - mr * 1.3, my - mr * 1.3);
    return { canvas: c, stars };
  }

  function buildClouds(W, H, rand) {
    const y0 = Math.round(H * 0.06);
    const c = makeCanvas(W, H * 0.30), g = c.getContext('2d');
    g.translate(0, -y0);
    for (let i = 0; i < 7; i++) {
      const cx = rand() * W, cy = H * (0.12 + rand() * 0.22);
      const cw = H * (0.20 + rand() * 0.22), ch = cw * 0.10;
      for (const rp of [0, -W, W]) {
        for (let j = 0; j < 6; j++) {
          const u = j / 5 - 0.5;
          const px = cx + rp + u * cw, py = cy - Math.cos(u * 3) * ch * 0.4, pr = ch * (1.2 + rand() * 0.8) * (1 - Math.abs(u));
          const gr = g.createRadialGradient(px, py, 0, px, py, pr);
          gr.addColorStop(0, 'rgba(120,84,148,0.36)');
          gr.addColorStop(0.6, 'rgba(160,100,150,0.16)');
          gr.addColorStop(1, 'rgba(160,100,150,0)');
          g.fillStyle = gr;
          g.beginPath(); g.ellipse(px, py, pr * 2.2, pr, 0, 0, Math.PI * 2); g.fill();
        }
      }
    }
    return { canvas: c, y0 };
  }

  // kopce, les a vzdálená řada chalup s kostelem — vše v oparu
  function buildLand(W, H, rand) {
    const y0 = Math.round(H * 0.18);
    const c = makeCanvas(W, H * (0.58 - 0.18)), g = c.getContext('2d');
    g.translate(0, -y0);
    const lights = [], chimneys = [];
    const ridges = [
      { w: waveFn(rand, 4, 3.0 / W, 0.55), h: H * 0.10, base: H * (HORIZON + 0.01), col: [96, 90, 152], haze: 0.30 },
      { w: waveFn(rand, 5, 5.2 / W, 0.52), h: H * 0.065, base: H * (HORIZON + 0.03), col: [112, 116, 176], haze: 0.14 },
    ];
    for (const R of ridges) {
      g.beginPath();
      g.moveTo(0, R.base);
      for (let x = 0; x <= W; x += 3) {
        const n = 1 - Math.abs(R.w(x));
        g.lineTo(x, R.base - R.h * (0.25 + 0.75 * n * n));
      }
      g.lineTo(W, R.base); g.closePath();
      g.fillStyle = rgba(mix(R.col, P.HAZE, R.haze), 1);
      g.fill();
      g.save(); g.clip();
      const sn = g.createLinearGradient(0, R.base - R.h, 0, R.base - R.h * 0.4);
      sn.addColorStop(0, 'rgba(236,236,255,0.9)');
      sn.addColorStop(1, 'rgba(236,236,255,0)');
      g.fillStyle = sn;
      g.fillRect(0, R.base - R.h, W, R.h * 0.7);
      g.restore();
    }
    const hzg = g.createLinearGradient(0, H * (HORIZON - 0.03), 0, H * (HORIZON + 0.07));
    hzg.addColorStop(0, 'rgba(255,190,140,0)');
    hzg.addColorStop(0.5, 'rgba(255,190,140,0.35)');
    hzg.addColorStop(1, 'rgba(255,190,140,0)');
    g.fillStyle = hzg;
    g.fillRect(0, H * (HORIZON - 0.03), W, H * 0.10);

    const rows = [
      { base: 0.488, h: 0.062, haze: 0.62, dens: 0.020 },
      { base: 0.507, h: 0.085, haze: 0.45, dens: 0.026 },
    ];
    rows.forEach((B, i) => {
      const dark = mix(P.SPRUCE_FAR, P.HAZE, B.haze);
      const snow = mix(P.SNOW, P.HAZE, B.haze * 0.6);
      const baseY = H * B.base;
      g.fillStyle = rgba(dark, 1);
      g.fillRect(0, baseY - H * 0.01, W, H * 0.03);
      for (let x = -W * 0.02; x < W * 1.02; x += W * B.dens * (0.6 + rand() * 0.7)) {
        const th = H * B.h * (0.7 + rand() * 0.6);
        drawSpruce(g, x, baseY + H * 0.003 * rand(), th, th * 0.30, dark, snow, rand);
      }
    });

    // vzdálené chalupy mezi smrky a kostel
    const far = [];
    const nh = Math.round(W / (H * 0.17));
    for (let i = 0; i < nh; i++) far.push((i + 0.2 + rand() * 0.6) / nh * W);
    far.forEach((fx, i) => {
      if (Math.abs(fx - W * 0.40) < W * 0.07) return;
      const hh = H * (0.040 + rand() * 0.018), ww = H * (0.065 + rand() * 0.03);
      const r = drawHouse(g, { x: fx, by: H * 0.522, w: ww, h: hh, roofH: hh * 0.7, haze: 0.52, side: i % 2 ? 1 : -1, sw: ww * 0.3,
                               wall: P.WALLS[(i * 5 + 1) % P.WALLS.length], windows: [[0.25, 0.28], [0.62, 0.28]], door: false, chimneyAt: 0.28 + 0.4 * rand() }, rand);
      lights.push(...r.lights);
      if (r.chimney) chimneys.push(r.chimney);
    });
    const ch = drawChurch(g, W * 0.40, H * 0.524, H * 0.115, 0.45, rand);
    lights.push(...ch.lights);
    return { canvas: c, y0, lights, chimneys };
  }

  function buildGround(W, H, rand) {
    const y0 = Math.round(H * 0.26);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const lights = [], chimneys = [], tree = { lights: [] }, lamps = [];
    const wave = waveFn(rand, 4, 6.0 / W, 0.55);

    const base = g.createLinearGradient(0, H * GROUND_TOP, 0, H);
    base.addColorStop(0, rgba(mix(P.SNOW_SHADE, P.HAZE, 0.5), 0));
    base.addColorStop(0.04, rgba(mix(P.SNOW_SHADE, P.HAZE, 0.45), 1));
    base.addColorStop(0.22, rgba(mix(P.SNOW, P.SNOW_SHADE, 0.45), 1));
    base.addColorStop(0.60, rgba(mix(P.SNOW, P.SNOW_SHADE, 0.18), 1));
    base.addColorStop(1, rgba(P.SNOW, 1));
    g.fillStyle = base;
    g.fillRect(0, H * GROUND_TOP, W, H - H * GROUND_TOP);

    for (let i = 0; i < 140; i++) {
      const yy = H * lerp(0.52, 1.0, Math.pow(rand(), 0.85)), xx = rand() * W;
      const d = depthScale(yy / H);
      const rw = W * (0.03 + 0.12 * d) * (0.5 + rand());
      drift(g, xx, yy, rw, rw * 0.10);
      if (wave(xx + yy) > 0.1) {
        g.fillStyle = rgba(P.SNOW_DEEP, 0.07);
        g.beginPath(); g.ellipse(xx - rw * 0.2, yy + rw * 0.05, rw * 0.9, rw * 0.07, 0, 0, Math.PI * 2); g.fill();
      }
    }

    // vyšlapaná stopa
    const cx = (yf) => W * pathX(yf), hw = (yf) => W * pathHalf(yf);
    const left = [], right = [];
    for (let yy = 0.53; yy <= 1.005; yy += 0.01) {
      const wob = waveFn(rand, 2, 1, 0.5)(yy * 6) * 0.06 + 1;
      left.push([cx(yy) - hw(yy) * wob, H * yy]);
      right.push([cx(yy) + hw(yy) * wob, H * yy]);
    }
    const outline = () => {
      g.beginPath();
      left.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
      for (let i = right.length - 1; i >= 0; i--) g.lineTo(right[i][0], right[i][1]);
      g.closePath();
    };
    outline();
    const pg = g.createLinearGradient(0, H * 0.53, 0, H);
    pg.addColorStop(0, rgba(mix(P.PATH, P.HAZE, 0.4), 0.95));
    pg.addColorStop(1, rgba(P.PATH, 1));
    g.fillStyle = pg; g.fill();
    g.save(); outline(); g.clip();
    for (const off of [-0.5, 0.5]) {
      g.beginPath();
      for (let yy = 0.53; yy <= 1.005; yy += 0.01) {
        const px = cx(yy) + hw(yy) * off;
        if (yy === 0.53) g.moveTo(px, H * yy); else g.lineTo(px, H * yy);
      }
      g.strokeStyle = rgba(P.PATH_DARK, 0.5);
      g.lineWidth = Math.max(1, H * 0.007);
      g.stroke();
    }
    for (let i = 0; i < 70; i++) {
      const yf = 0.55 + Math.pow(rand(), 0.8) * 0.45;
      const px = cx(yf) + (rand() - 0.5) * 1.6 * hw(yf);
      const s = H * 0.012 * depthScale(yf) * (0.5 + rand());
      g.fillStyle = rgba(P.PATH_DARK, 0.30);
      g.beginPath(); g.ellipse(px, H * yf, s * 1.6, s * 0.5, 0, 0, Math.PI * 2); g.fill();
      g.fillStyle = rgba(P.SNOW, 0.5);
      g.beginPath(); g.ellipse(px + s * 0.3, H * yf - s * 0.2, s * 1.3, s * 0.3, 0, 0, Math.PI * 2); g.fill();
    }
    g.restore();
    // okraj stopy: nahrnutý sníh
    for (let i = 0; i < left.length; i += 2) {
      const d = depthScale(left[i][1] / H);
      drift(g, left[i][0] - W * 0.004, left[i][1], W * 0.03 * d + 3, W * 0.006 * d + 1);
      drift(g, right[i][0] + W * 0.004, right[i][1], W * 0.03 * d + 3, W * 0.006 * d + 1);
    }

    // světelné kaluže pod okny a lucernami (kreslí se pod předměty)
    const puddle = (x, y, rx, ry, a) => {
      const gr = g.createRadialGradient(x, y, 0, x, y, rx);
      gr.addColorStop(0, 'rgba(255,196,96,' + a + ')');
      gr.addColorStop(0.5, 'rgba(255,176,80,' + a * 0.4 + ')');
      gr.addColorStop(1, 'rgba(255,170,80,0)');
      g.save();
      g.translate(x, y); g.scale(1, ry / rx); g.translate(-x, -y);
      g.fillStyle = gr;
      g.beginPath(); g.arc(x, y, rx, 0, Math.PI * 2); g.fill();
      g.restore();
    };

    // předměty seřazené podle paty (y), nejdál první
    const items = [];
    const add = (y, fn) => items.push({ y, fn });

    const mids = [
      { x: -0.02, by: 0.625, w: 0.15, h: 0.20, side: 1, wall: P.WALLS[0], windows: [[0.15, 0.20], [0.60, 0.20]], doorAt: 0.38 },
      { x: 0.835, by: 0.605, w: 0.13, h: 0.17, side: -1, wall: P.WALLS[3], windows: [[0.18, 0.24], [0.62, 0.24]], doorAt: 0.40, chimneyAt: 0.3 },
      { x: 0.20, by: 0.575, w: 0.075, h: 0.095, side: 1, wall: P.WALLS[2], windows: [[0.2, 0.28], [0.62, 0.28]], door: false, haze: 0.18 },
      { x: 0.735, by: 0.568, w: 0.07, h: 0.085, side: -1, wall: P.WALLS[1], windows: [[0.2, 0.28], [0.62, 0.28]], door: false, haze: 0.2 },
      { x: 0.60, by: 0.552, w: 0.06, h: 0.07, side: 1, wall: P.WALLS[4], windows: [[0.25, 0.3], [0.62, 0.3]], door: false, haze: 0.32 },
    ];
    for (const m of mids) {
      add(m.by, () => {
        const r = drawHouse(g, { x: m.x * W, by: m.by * H, w: m.w * W, h: m.h * H, roofH: m.h * H * 0.66, side: m.side, sw: m.w * W * 0.30,
                                 wall: m.wall, windows: m.windows, door: m.door, doorAt: m.doorAt, chimneyAt: m.chimneyAt, haze: m.haze || 0 }, rand);
        lights.push(...r.lights);
        if (r.chimney) chimneys.push(r.chimney);
        for (const l of r.lights) puddle(l.x, m.by * H + H * 0.012, l.r * 1.2, l.r * 0.28, 0.32);
      });
    }

    const trees = [[0.285, 0.592, 0.15], [0.545, 0.575, 0.11], [0.69, 0.60, 0.17], [0.075, 0.675, 0.30], [0.97, 0.655, 0.27],
                   [0.325, 0.553, 0.10], [0.68, 0.545, 0.085], [0.17, 0.552, 0.10]];
    for (const [tx, ty, th] of trees) {
      add(ty, () => {
        const sc = th * H;
        g.fillStyle = 'rgba(60,70,130,0.28)';
        g.beginPath(); g.ellipse(tx * W + sc * 0.08, ty * H + 2, sc * 0.22, sc * 0.03, 0, 0, Math.PI * 2); g.fill();
        drawSpruce(g, tx * W, ty * H, sc, sc * 0.30, P.SPRUCE, P.SNOW, rand);
      });
    }

    add(0.640, () => {
      const tl = drawXmasTree(g, W * 0.62, H * 0.640, H * 0.36, rand);
      tree.lights = tl;
      puddle(W * 0.62, H * 0.655, H * 0.30, H * 0.07, 0.30);
    });

    for (const [lx, ly, lh] of [[0.405, 0.690, 0.22], [0.865, 0.675, 0.20], [0.255, 0.600, 0.14]]) {
      add(ly, () => {
        puddle(lx * W, ly * H + lh * H * 0.02, lh * H * 1.05, lh * H * 0.26, 0.42);
        lamps.push(drawLamp(g, lx * W, ly * H, lh * H));
      });
    }

    add(0.612, () => drawFence(g, W * 0.135, W * 0.335, H * 0.612, H * 0.05, H * 0.006));
    add(0.597, () => drawFence(g, W * 0.715, W * 0.83, H * 0.597, H * 0.045, -H * 0.004));
    add(0.675, () => drawSnowman(g, W * 0.255, H * 0.675, H * 0.20, 0));
    add(0.660, () => drawSnowman(g, W * 0.915, H * 0.662, H * 0.14, 1));

    items.sort((a, b) => a.y - b.y).forEach((it) => it.fn());

    // stopy v sněhu: dva řádky po stopě
    g.fillStyle = rgba(P.SNOW_SHADE, 0.7);
    for (let i = 0; i < 26; i++) {
      const yf = 0.60 + i * 0.015;
      const px = cx(yf) + (i % 2 ? 1 : -1) * hw(yf) * 0.2 + (rand() - 0.5) * hw(yf) * 0.12;
      const s = H * 0.011 * depthScale(yf);
      g.beginPath(); g.ellipse(px, H * yf, s * 0.8, s * 1.3, 0.3, 0, Math.PI * 2); g.fill();
    }

    const glints = [];
    for (let i = 0; i < 36; i++) {
      glints.push({ x: rand() * W, y: H * (0.56 + 0.43 * Math.pow(rand(), 0.8)), ph: rand() * 6.28, sp: 0.6 + rand() * 1.6 });
    }
    return { canvas: c, y0, lights, chimneys, tree, lamps, glints };
  }

  // popředí: větve smrku s sněhem v horních rozích a závěje u spodního okraje
  function buildFront(W, H, rand) {
    const c = makeCanvas(W, H), g = c.getContext('2d');
    const bough = (x, y, len, dir, rr) => {
      g.save();
      g.translate(x, y);
      g.rotate(dir);
      const sag = (f) => len * 0.10 * f * f;
      const n = 22;
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 1; i <= n; i++) {
          const f = i / n, px = len * f, py = sag(f);
          const nl = len * 0.15 * (1 - f * 0.6);
          if (pass === 0) {
            g.strokeStyle = rgba(mix([14, 44, 50], [30, 82, 72], rr()), 1);
            g.lineWidth = Math.max(1.5, len * 0.010);
            g.lineCap = 'round';
            for (let k = 0; k < 7; k++) {
              const a = -1.25 + k * 0.42 + (rr() - 0.5) * 0.2;
              g.beginPath();
              g.moveTo(px, py);
              g.lineTo(px + Math.sin(a) * nl * 0.5 + nl * 0.25, py + Math.cos(a + 1.57) * nl * 1.1 * (k % 2 ? 1 : -1) * 0.6 + Math.sin(a) * nl * 0.3);
              g.stroke();
            }
          } else {
            for (let k = 0; k < 3; k++) {
              const sx = px + (rr() - 0.5) * nl * 0.9, sy = py - nl * (0.12 + 0.34 * rr());
              const sr = nl * (0.16 + 0.22 * rr());
              g.fillStyle = rgba(mix(P.SNOW, P.SNOW_SHADE, rr() * 0.5), 0.96);
              g.beginPath(); g.ellipse(sx, sy, sr * 1.5, sr, 0, 0, Math.PI * 2); g.fill();
            }
          }
        }
        if (pass === 0) {
          g.strokeStyle = 'rgb(42,30,26)';
          g.lineWidth = Math.max(2, len * 0.022);
          g.beginPath(); g.moveTo(0, 0);
          for (let i = 1; i <= 12; i++) g.lineTo(len * i / 12, sag(i / 12));
          g.stroke();
        }
      }
      g.restore();
    };
    bough(-W * 0.01, H * 0.02, W * 0.26, 0.28, rand);
    bough(-W * 0.01, H * 0.10, W * 0.16, 0.50, rand);
    bough(W * 1.01, H * 0.015, W * 0.24, Math.PI - 0.30, rand);
    bough(W * 1.01, H * 0.09, W * 0.15, Math.PI - 0.52, rand);
    for (const [x, rx] of [[0.04, 0.16], [0.92, 0.18], [0.5, 0.30]]) {
      const y = H * 1.0;
      const gr = g.createRadialGradient(W * x, y, 0, W * x, y, W * rx);
      gr.addColorStop(0, rgba(P.SNOW, 1));
      gr.addColorStop(0.7, rgba(mix(P.SNOW, P.SNOW_SHADE, 0.35), 1));
      gr.addColorStop(1, rgba(P.SNOW_SHADE, 0));
      g.fillStyle = gr;
      g.save(); g.translate(0, y); g.scale(1, 0.14 * (W / H) * 0.4); g.translate(0, -y);
      g.beginPath(); g.arc(W * x, y, W * rx, 0, Math.PI * 2); g.fill(); g.restore();
    }
    return { canvas: c };
  }

  function buildFlakes(rand) {
    const layers = [
      { n: 150, size: [0.0016, 0.0030], speed: [0.030, 0.050], amp: 0.010, alpha: [0.45, 0.85], front: false },
      { n: 80, size: [0.0030, 0.0055], speed: [0.065, 0.100], amp: 0.016, alpha: [0.55, 0.95], front: true },
      { n: 22, size: [0.0090, 0.0160], speed: [0.150, 0.220], amp: 0.030, alpha: [0.35, 0.60], front: true },
    ];
    return layers.map((L) => ({
      front: L.front, amp: L.amp,
      flakes: Array.from({ length: L.n }, () => ({
        x: rand(), y: rand(), s: lerp(L.size[0], L.size[1], rand()), v: lerp(L.speed[0], L.speed[1], rand()),
        a: lerp(L.alpha[0], L.alpha[1], rand()), ph: rand() * 6.28, f: 0.4 + rand() * 0.9,
      })),
    }));
  }

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const sky = buildSky(W, H, rand);
    const clouds = buildClouds(W, H, rand);
    const land = buildLand(W, H, rand);
    const ground = buildGround(W, H, rand);
    const front = buildFront(W, H, rand);
    const flakes = buildFlakes(rand);
    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.5, H * 0.55, H * 0.40, W * 0.5, H * 0.55, H * 1.0);
    v.addColorStop(0, 'rgba(6,8,40,0)');
    v.addColorStop(1, 'rgba(6,8,40,0.38)');
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);
    const tint = makeCanvas(W, H), tg = tint.getContext('2d');
    const tgrad = tg.createLinearGradient(0, 0, 0, H);
    tgrad.addColorStop(0, 'rgba(30,30,110,0.10)');
    tgrad.addColorStop(1, 'rgba(60,70,160,0.06)');
    tg.fillStyle = tgrad;
    tg.fillRect(0, 0, W, H);
    const smoke = [...land.chimneys, ...ground.chimneys].map((ch) => ({ ...ch, ph: rand() * 20 }));
    return { W, H, sky, clouds, land, ground, front, flakes, vig, tint, smoke };
  }

  function drawSmoke(ctx, W, H, t, S) {
    const spr = glowSprite([214, 214, 236], 48);
    ctx.save();
    for (const ch of S.smoke) {
      const s = Math.max(6, ch.s * 0.26);
      for (let i = 0; i < 9; i++) {
        const p = ((t * 0.10 + i / 9 + ch.ph) % 1 + 1) % 1;
        const x = ch.x + p * ch.s * 0.9 + Math.sin(t * 0.7 + i + ch.ph) * s * 0.4 * p;
        const y = ch.y - p * ch.s * 1.25;
        const r = s * (0.5 + p * 1.5);
        ctx.globalAlpha = (1 - p) * (p < 0.08 ? p / 0.08 : 1) * 0.75;
        ctx.drawImage(spr, x - r, y - r, r * 2, r * 2);
      }
    }
    ctx.restore();
  }

  function drawGlows(ctx, W, H, t, S) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const warm = glowSprite([255, 170, 70], 64);
    const lists = [S.land.lights, S.ground.lights];
    for (const list of lists) {
      for (const l of list) {
        const a = 0.10 + 0.07 * Math.sin(t * 2.1 + l.ph) * Math.sin(t * 0.7 + l.ph * 2.0);
        ctx.globalAlpha = Math.max(0, a);
        ctx.drawImage(warm, l.x - l.r, l.y - l.r, l.r * 2, l.r * 2);
      }
    }
    for (const lp of S.ground.lamps) {
      ctx.globalAlpha = 0.34 + 0.05 * Math.sin(t * 3.1 + lp.x);
      ctx.drawImage(warm, lp.x - lp.r * 0.8, lp.y - lp.r * 0.8, lp.r * 1.6, lp.r * 1.6);
    }
    const tl = S.ground.tree.lights;
    const sizeH = H * 0.036;
    for (const l of tl) {
      const tw = 0.5 + 0.5 * Math.sin(t * (l.big ? 1.6 : 2.6) + l.ph);
      ctx.globalAlpha = l.big ? 0.65 : 0.25 + 0.55 * tw;
      const sp = glowSprite(l.col, 48);
      const r = l.big ? sizeH * 1.6 : sizeH * (0.45 + 0.4 * tw);
      ctx.drawImage(sp, l.x - r, l.y - r, r * 2, r * 2);
    }
    const star = glowSprite([255, 244, 214], 32);
    ctx.fillStyle = 'rgb(255,248,226)';
    for (const gl of S.ground.glints) {
      const a = Math.max(0, Math.sin(t * gl.sp + gl.ph));
      if (a < 0.7) continue;
      const k = (a - 0.7) / 0.3;
      const r = H * 0.006 * k;
      ctx.globalAlpha = 0.8 * k;
      ctx.fillRect(gl.x - r, gl.y - H * 0.0006, r * 2, H * 0.0012);
      ctx.fillRect(gl.x - H * 0.0006, gl.y - r, H * 0.0012, r * 2);
      ctx.drawImage(star, gl.x - r, gl.y - r, r * 2, r * 2);
    }
    ctx.restore();
  }

  function drawFlakes(ctx, W, H, t, S, front) {
    const spr = glowSprite([255, 255, 255], 32);
    ctx.save();
    for (const L of S.flakes) {
      if (L.front !== front) continue;
      for (const f of L.flakes) {
        const y = (((f.y + t * f.v) % 1.1) + 1.1) % 1.1 - 0.05;
        const x = (((f.x + Math.sin(t * f.f + f.ph) * L.amp + t * 0.004) % 1) + 1) % 1;
        const r = Math.max(1.2, f.s * H);
        ctx.globalAlpha = f.a;
        ctx.drawImage(spr, x * W - r, y * H - r, r * 2, r * 2);
      }
    }
    ctx.restore();
  }

  function draw(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;
    ctx.drawImage(S.sky.canvas, 0, 0);
    ctx.save();
    for (const s of S.sky.stars) {
      ctx.globalAlpha = 0.25 + 0.75 * Math.max(0, Math.sin(t * s.sp + s.ph));
      ctx.fillStyle = 'rgb(255,250,236)';
      ctx.fillRect(s.x - s.r, s.y - s.r * 0.25, s.r * 2, s.r * 0.5);
      ctx.fillRect(s.x - s.r * 0.25, s.y - s.r, s.r * 0.5, s.r * 2);
    }
    ctx.restore();
    const o1 = (t * W * 0.0012) % W;
    ctx.drawImage(S.clouds.canvas, -o1, S.clouds.y0);
    ctx.drawImage(S.clouds.canvas, W - o1, S.clouds.y0);
    ctx.drawImage(S.land.canvas, 0, S.land.y0);
    ctx.drawImage(S.ground.canvas, 0, S.ground.y0);
    drawSmoke(ctx, W, H, t, S);
    drawGlows(ctx, W, H, t, S);
    drawFlakes(ctx, W, H, t, S, false);
    ctx.drawImage(S.tint, 0, 0);
  }

  function drawFront(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    ctx.drawImage(state.front.canvas, 0, 0);
    drawFlakes(ctx, W, H, t, state, true);
    ctx.drawImage(state.vig, 0, 0);
  }

  return { draw, drawFront, sun: { x: 0.80, y: 0.15 }, depthScale };
}
