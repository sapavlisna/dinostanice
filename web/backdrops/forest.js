/* Lesní mýtina — malovaná krajina pro 2D plátno pod 3D tvory.

   ES modul s továrnou `create()`; vrací `{draw, drawFront, sun, depthScale}`
   stejně jako cretaceous.js, takže scéna jen vymění cestu v render.js.

   Rozvržení drží stejné pásy jako laguna, ať se dráhy z render.js nemění:
     0,00–0,44  obloha, vzdálené kopce
     0,38–0,52  les ve čtyřech vrstvách (smrky, listnáče, břízy), vzdálené v oparu
     0,52–0,57  zadní louka — tady jdou zadní dráhy (0,532 / 0,558)
     0,58–0,79  střední louka: keře, pařezy, kameny, mladé stromky — kreslí se
                POD tvory, takže přední zvíře je zakryje (zadní dráha je
                nepřesahuje, jejich vršek leží pod 0,565)
     0,80–0,95  přední louka — přední dráhy (0,815 / 0,88 / 0,945)
     od 0,96    rostliny v rozích, kreslí se NAD tvory (drawFront)
   Cestička protíná louku z dálky do popředí, tvorové po ní chodí. */

const SEED = 20261017;

const HORIZON = 0.44;
const FOREST_TOP = 0.385;
const FOREST_BASE = 0.522;
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
  return [Math.round(lerp(a[0], b[0], k)), Math.round(lerp(a[1], b[1], k)),
          Math.round(lerp(a[2], b[2], k))];
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

// Cestička jde z dálky vpravo ke spodnímu okraji vlevo; trasy chodců ve
// scenes/les/render.js ji sledují, proto je to hladká funkce, ne náhoda.
export function trailX(yf) {
  const u = clamp((yf - 0.53) / 0.47, 0, 1.2);
  return 0.60 - 0.22 * Math.pow(u, 0.9) + 0.035 * Math.sin(u * 5.2) * u;
}
export function trailHalf(yf) {
  return 0.010 + 0.150 * Math.pow(clamp((yf - 0.53) / 0.47, 0, 1.2), 1.5);
}

const P = {
  SKY_TOP: [64, 134, 204], SKY_MID: [140, 200, 236], SKY_LOW: [204, 230, 238],
  SKY_HAZE: [250, 240, 212],
  RIDGE_FAR: [150, 178, 196], RIDGE_NEAR: [112, 150, 148],
  FOREST: [[126, 164, 142], [92, 138, 100], [62, 112, 68], [40, 88, 48]],
  LEAF: [[104, 166, 64], [138, 188, 76], [86, 140, 58], [176, 196, 70]],
  AUTUMN: [[222, 164, 52], [206, 118, 44]],
  TRUNK: [92, 66, 46], BIRCH: [232, 230, 220],
  GRASS_FAR: [156, 192, 104], GRASS_MID: [122, 170, 76], GRASS_NEAR: [92, 144, 60],
  GRASS_DARK: [52, 100, 42], GRASS_LIGHT: [176, 210, 100],
  PATH: [204, 174, 124], PATH_DARK: [160, 128, 90], PATH_LIGHT: [226, 202, 156],
  ROCK: [128, 126, 118], ROCK_LIT: [176, 172, 158], MOSS: [88, 132, 58],
  FLOWERS: [[252, 252, 246], [250, 214, 64], [236, 120, 156], [150, 120, 214], [240, 150, 56]],
  vignette: 'rgba(14,30,12,0.30)',
};

// ------------------------------------------------------------------ trees

function drawSpruce(ctx, x, baseY, h, w, color, rand) {
  const tiers = 6 + Math.floor(rand() * 3);
  ctx.fillStyle = color;
  ctx.fillRect(x - h * 0.016, baseY - h * 0.18, h * 0.032, h * 0.18);
  for (let i = 0; i < tiers; i++) {
    const f = i / tiers;
    const ty = baseY - h * 0.10 - f * h * 0.74;
    const tw = w * (1 - f * 0.82);
    const th = h * (0.26 - f * 0.06);
    ctx.beginPath();
    ctx.moveTo(x, ty - th);
    ctx.lineTo(x + tw, ty);
    ctx.lineTo(x + tw * 0.4, ty + h * 0.018);
    ctx.lineTo(x - tw * 0.4, ty + h * 0.018);
    ctx.lineTo(x - tw, ty);
    ctx.closePath();
    ctx.fill();
  }
}

// Listnáč: kmen a koruna z překrytých kruhů; světlejší kruhy nahoře vlevo
// (slunce je vpravo nahoře, ale zdálky je lepší čitelný volume než přesný stín).
function drawLeafy(ctx, x, baseY, h, w, trunk, crown, hi, rand) {
  ctx.fillStyle = trunk;
  ctx.beginPath();
  ctx.moveTo(x - h * 0.030, baseY);
  ctx.lineTo(x + h * 0.030, baseY);
  ctx.lineTo(x + h * 0.016, baseY - h * 0.46);
  ctx.lineTo(x - h * 0.016, baseY - h * 0.46);
  ctx.closePath();
  ctx.fill();
  const blobs = 6 + Math.floor(rand() * 3);
  const cy = baseY - h * 0.64;
  const pts = [];
  for (let i = 0; i < blobs; i++) {
    const a = (i / blobs) * Math.PI * 2 + rand() * 0.5;
    const r = w * (0.34 + rand() * 0.22);
    pts.push([x + Math.cos(a) * w * 0.40, cy + Math.sin(a) * h * 0.20, r]);
  }
  pts.push([x, cy - h * 0.06, w * 0.62]);
  ctx.fillStyle = crown;
  for (const p of pts) { ctx.beginPath(); ctx.arc(p[0], p[1], p[2], 0, Math.PI * 2); ctx.fill(); }
  if (hi) {
    ctx.fillStyle = hi;
    for (let i = 0; i < pts.length; i += 2) {
      const p = pts[i];
      ctx.beginPath();
      ctx.arc(p[0] - p[2] * 0.22, p[1] - p[2] * 0.26, p[2] * 0.62, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function drawBirch(ctx, x, baseY, h, w, crown, hi, rand) {
  const lean = (rand() - 0.5) * w * 0.35;
  ctx.fillStyle = rgba(P.BIRCH, 1);
  ctx.beginPath();
  ctx.moveTo(x - h * 0.020, baseY);
  ctx.lineTo(x + h * 0.020, baseY);
  ctx.lineTo(x + lean + h * 0.011, baseY - h * 0.74);
  ctx.lineTo(x + lean - h * 0.011, baseY - h * 0.74);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = 'rgba(40,36,30,0.75)';
  for (let i = 0; i < 6; i++) {
    const f = 0.06 + rand() * 0.6;
    ctx.fillRect(x + lean * f / 0.74 - h * 0.018, baseY - h * f, h * 0.036 * (0.5 + rand() * 0.5), Math.max(1, h * 0.012));
  }
  const cx = x + lean, cy = baseY - h * 0.80;
  ctx.fillStyle = crown;
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    ctx.beginPath();
    ctx.ellipse(cx + Math.cos(a) * w * 0.24, cy + Math.sin(a) * h * 0.11, w * 0.34, h * 0.13, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.beginPath();
  ctx.ellipse(cx, cy - h * 0.04, w * 0.46, h * 0.16, 0, 0, Math.PI * 2);
  ctx.fill();
  if (hi) {
    ctx.fillStyle = hi;
    ctx.beginPath();
    ctx.ellipse(cx - w * 0.12, cy - h * 0.08, w * 0.28, h * 0.09, -0.2, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ------------------------------------------------------------ ground bits

function tuft(ctx, x, y, s, color, rand, blades) {
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.lineWidth = Math.max(1, s * 0.09);
  const n = blades || 5;
  for (let i = 0; i < n; i++) {
    const sp = (i / (n - 1) - 0.5) * 2;
    ctx.beginPath();
    ctx.moveTo(x + sp * s * 0.18, y);
    ctx.quadraticCurveTo(x + sp * s * 0.45, y - s * 0.6, x + sp * s * (0.7 + rand() * 0.3), y - s * (0.75 + rand() * 0.45));
    ctx.stroke();
  }
}

function flower(ctx, x, y, r, col, rand) {
  ctx.fillStyle = rgba(col, 1);
  if (r < 1.6) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    return;
  }
  const petals = 5;
  for (let i = 0; i < petals; i++) {
    const a = (i / petals) * Math.PI * 2 + rand();
    ctx.beginPath();
    ctx.arc(x + Math.cos(a) * r * 0.7, y + Math.sin(a) * r * 0.55, r * 0.55, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = rgba([250, 200, 50], 1);
  ctx.beginPath(); ctx.arc(x, y, r * 0.42, 0, Math.PI * 2); ctx.fill();
}

function bush(ctx, x, y, s, rand, berries) {
  const cols = [P.LEAF[2], P.LEAF[0], P.LEAF[1]];
  ctx.fillStyle = 'rgba(30,60,24,0.28)';
  ctx.beginPath(); ctx.ellipse(x, y + s * 0.02, s * 1.0, s * 0.16, 0, 0, Math.PI * 2); ctx.fill();
  const n = 7;
  for (let i = 0; i < n; i++) {
    const u = (i / (n - 1) - 0.5) * 2;
    const r = s * (0.42 + rand() * 0.2) * (1 - Math.abs(u) * 0.35);
    ctx.fillStyle = rgba(mix(cols[0], P.GRASS_DARK, 0.25), 1);
    ctx.beginPath(); ctx.arc(x + u * s * 0.8, y - r * 0.55, r, 0, Math.PI * 2); ctx.fill();
  }
  for (let i = 0; i < n; i++) {
    const u = (i / (n - 1) - 0.5) * 2;
    const r = s * (0.30 + rand() * 0.14) * (1 - Math.abs(u) * 0.35);
    ctx.fillStyle = rgba(cols[1 + (i % 2)], 1);
    ctx.beginPath(); ctx.arc(x + u * s * 0.72 - r * 0.2, y - r * 0.95 - s * 0.14, r, 0, Math.PI * 2); ctx.fill();
  }
  if (berries) {
    for (let i = 0; i < 14; i++) {
      ctx.fillStyle = rgba(berries, 1);
      ctx.beginPath();
      ctx.arc(x + (rand() - 0.5) * s * 1.5, y - s * (0.2 + rand() * 0.7), Math.max(1.2, s * 0.05), 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function rock(ctx, x, y, w, rand, wob) {
  const h = w * (0.55 + rand() * 0.25);
  ctx.fillStyle = 'rgba(30,50,24,0.3)';
  ctx.beginPath(); ctx.ellipse(x, y + h * 0.05, w * 1.05, h * 0.2, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath();
  for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.25) {
    const rr = 1 + 0.14 * wob(a * 3);
    const py = Math.sin(a);
    ctx.lineTo(x + Math.cos(a) * w * rr, y - h * 0.5 + py * h * 0.5 * rr * (py < 0 ? 1 : 0.7));
  }
  ctx.closePath();
  ctx.fillStyle = rgba(mix(P.ROCK, [70, 70, 64], rand() * 0.4), 1);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(x - w * 0.15, y - h * 0.72, w * 0.52, h * 0.24, -0.25, 0, Math.PI * 2);
  ctx.fillStyle = rgba(P.ROCK_LIT, 0.55);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(x + w * 0.05, y - h * 0.92, w * 0.55, h * 0.18, 0, Math.PI, Math.PI * 2);
  ctx.fillStyle = rgba(P.MOSS, 0.9);
  ctx.fill();
}

function stump(ctx, x, y, w, rand) {
  const h = w * 0.85;
  ctx.fillStyle = 'rgba(30,50,24,0.3)';
  ctx.beginPath(); ctx.ellipse(x, y + 1, w * 0.95, w * 0.2, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = rgba(P.TRUNK, 1);
  ctx.beginPath();
  ctx.moveTo(x - w * 0.55, y);
  ctx.quadraticCurveTo(x - w * 0.42, y - h * 0.5, x - w * 0.46, y - h);
  ctx.lineTo(x + w * 0.46, y - h);
  ctx.quadraticCurveTo(x + w * 0.42, y - h * 0.5, x + w * 0.55, y);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = rgba([206, 170, 116], 1);
  ctx.beginPath(); ctx.ellipse(x, y - h, w * 0.46, w * 0.17, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = rgba([150, 112, 72], 1);
  ctx.lineWidth = Math.max(1, w * 0.04);
  for (let i = 1; i <= 2; i++) {
    ctx.beginPath(); ctx.ellipse(x, y - h, w * 0.46 * i / 3, w * 0.17 * i / 3, 0, 0, Math.PI * 2); ctx.stroke();
  }
  ctx.fillStyle = rgba(P.MOSS, 0.85);
  ctx.beginPath(); ctx.ellipse(x - w * 0.3, y - h * 0.12, w * 0.22, w * 0.1, 0, 0, Math.PI * 2); ctx.fill();
}

function log(ctx, x, y, len, rand) {
  const r = len * 0.12;
  ctx.fillStyle = 'rgba(30,50,24,0.3)';
  ctx.beginPath(); ctx.ellipse(x, y + 1, len * 0.52, r * 0.45, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = rgba(mix(P.TRUNK, [50, 36, 26], 0.2), 1);
  ctx.beginPath();
  ctx.moveTo(x - len / 2, y - r * 2);
  ctx.lineTo(x + len / 2, y - r * 2);
  ctx.lineTo(x + len / 2, y);
  ctx.lineTo(x - len / 2, y);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = rgba(P.TRUNK, 1);
  ctx.fillRect(x - len / 2, y - r * 2, len, r * 0.8);
  ctx.fillStyle = rgba([210, 176, 124], 1);
  ctx.beginPath(); ctx.ellipse(x + len / 2, y - r, r * 0.55, r, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = rgba([150, 112, 72], 1);
  ctx.lineWidth = Math.max(1, r * 0.12);
  ctx.beginPath(); ctx.ellipse(x + len / 2, y - r, r * 0.3, r * 0.58, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = rgba(P.MOSS, 0.9);
  ctx.beginPath(); ctx.ellipse(x - len * 0.15, y - r * 2, len * 0.14, r * 0.35, 0, Math.PI, Math.PI * 2); ctx.fill();
  for (let i = 0; i < 3; i++) mushroom(ctx, x - len * 0.3 + i * len * 0.12, y - r * 2, r * (0.35 + rand() * 0.2), [236, 232, 218]);
}

function mushroom(ctx, x, y, r, cap) {
  ctx.fillStyle = rgba([240, 232, 214], 1);
  ctx.fillRect(x - r * 0.18, y - r * 0.9, r * 0.36, r * 0.9);
  ctx.fillStyle = rgba(cap, 1);
  ctx.beginPath(); ctx.ellipse(x, y - r * 0.9, r * 0.7, r * 0.45, 0, Math.PI, Math.PI * 2); ctx.fill();
  if (cap[0] > 200 && cap[1] < 100) {
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.beginPath(); ctx.arc(x - r * 0.25, y - r * 1.1, r * 0.1, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(x + r * 0.2, y - r * 1.2, r * 0.08, 0, Math.PI * 2); ctx.fill();
  }
}

function fern(ctx, x, y, s, rand) {
  const n = 7;
  for (let k = 0; k < n; k++) {
    const sp = (k / (n - 1) - 0.5) * 2;
    const ang = -Math.PI / 2 + sp * 0.9;
    const len = s * (0.8 + rand() * 0.4);
    const col = rgba(mix(P.GRASS_DARK, P.LEAF[0], rand() * 0.7), 1);
    ctx.strokeStyle = col;
    ctx.lineWidth = Math.max(1, s * 0.03);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x, y);
    const ex = x + Math.cos(ang) * len + sp * len * 0.35, ey = y + Math.sin(ang) * len * 0.8;
    ctx.quadraticCurveTo(x + Math.cos(ang) * len * 0.5, y + Math.sin(ang) * len * 0.7, ex, ey);
    ctx.stroke();
    for (let i = 2; i < 10; i++) {
      const f = i / 10;
      const px = lerp(x, ex, f), py = lerp(y, ey, f) - Math.sin(f * 3) * len * 0.03;
      const ll = len * 0.22 * Math.sin(Math.PI * Math.pow(f, 0.6));
      for (let sg = -1; sg <= 1; sg += 2) {
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px + sg * ll, py - ll * 0.55);
        ctx.stroke();
      }
    }
  }
}

// ------------------------------------------------------------ trunks, birds

// Dva štíhlé kmeny těsně před scénou (kreslí se NAD tvory, zvíře za nimi
// zajde). Větve mají místa k sezení, spočítaná v perchSpots().
const TRUNKS = [
  { x: 0.17, w: 0.050, lean: 0.010, branches: [
    { y: 0.47, dx: 1, len: 0.21, rise: -0.020 },
    { y: 0.31, dx: -1, len: 0.15, rise: -0.030 },
    { y: 0.19, dx: 1, len: 0.14, rise: -0.040 }] },
  { x: 0.93, w: 0.050, lean: -0.008, branches: [
    { y: 0.50, dx: -1, len: 0.20, rise: -0.020 },
    { y: 0.35, dx: -1, len: 0.14, rise: -0.040 },
    { y: 0.22, dx: -1, len: 0.10, rise: -0.030 }] },
];

// bod na větvi v podílu `f` její délky; délka větve je v násobcích H
function branchPoint(T, B, f, W, H) {
  const tx = T.x * W + T.lean * W * (1 - B.y);
  return [tx + B.dx * B.len * H * f, B.y * H + B.rise * H * f + Math.sin(f * 3) * H * 0.006];
}

function perchSpots(W, H) {
  const out = [];
  for (const T of TRUNKS) {
    for (const B of T.branches) {
      for (const f of [0.48, 0.82]) {
        const [x, y] = branchPoint(T, B, f, W, H);
        out.push({ x: x / W, y: (y - H * 0.0075) / H, face: B.dx > 0 ? 1 : -1 });
      }
    }
  }
  return out;
}

// Dřevo (kmeny, větve) jde do předního plátna, listí do zadního: vybarvený 3D pták
// na větvi tak sedí nad listím, ale pod dřevem, a zvíře za kmenem zmizí.
function drawTrunks(W, H, rand) {
  const c = makeCanvas(W, H), g = c.getContext('2d');
  const cl = makeCanvas(W, H), gl = cl.getContext('2d');
  const crack = waveFn(rand, 4, 14 / H, 0.5);
  for (const T of TRUNKS) {
    const bw = (yy) => H * (T.w - 0.014 * (1 - yy / H));
    const xAt = (yy) => T.x * W + T.lean * W * (1 - yy / H) + crack(yy * 0.4) * H * 0.006;
    g.beginPath();
    for (let yy = -4; yy <= H + 4; yy += 6) g.lineTo(xAt(yy) - bw(yy) / 2, yy);
    for (let yy = H + 4; yy >= -4; yy -= 6) g.lineTo(xAt(yy) + bw(yy) / 2, yy);
    g.closePath();
    const bark = g.createLinearGradient(T.x * W - H * T.w / 2, 0, T.x * W + H * T.w / 2, 0);
    bark.addColorStop(0, 'rgb(44,32,26)');
    bark.addColorStop(0.55, 'rgb(64,46,34)');
    bark.addColorStop(0.85, 'rgb(98,72,50)');
    bark.addColorStop(1, 'rgb(70,50,36)');
    g.fillStyle = bark;
    g.fill();
    g.save();
    g.clip();
    for (let i = 0; i < 70; i++) {
      const yy = rand() * H, off = (rand() - 0.5) * 0.9;
      const len = H * (0.03 + rand() * 0.10);
      g.strokeStyle = rand() < 0.7 ? 'rgba(20,14,10,0.55)' : 'rgba(150,118,84,0.40)';
      g.lineWidth = Math.max(1, H * 0.0022);
      g.beginPath();
      g.moveTo(xAt(yy) + off * bw(yy), yy);
      g.lineTo(xAt(yy + len) + off * bw(yy + len) + (rand() - 0.5) * 3, yy + len);
      g.stroke();
    }
    for (let i = 0; i < 46; i++) {
      const yy = rand() * H;
      g.fillStyle = rgba(rand() < 0.55 ? [176, 184, 144] : [204, 196, 168], 0.8);
      g.beginPath();
      g.ellipse(xAt(yy) + (rand() - 0.5) * bw(yy) * 0.8, yy, H * 0.004 * (0.5 + rand()), H * 0.009 * (0.5 + rand()), 0, 0, Math.PI * 2);
      g.fill();
    }
    const moss = g.createLinearGradient(0, H * 0.80, 0, H);
    moss.addColorStop(0, rgba(P.MOSS, 0));
    moss.addColorStop(1, rgba(P.MOSS, 0.6));
    g.fillStyle = moss;
    g.fillRect(0, H * 0.80, W, H * 0.20);
    g.restore();
    for (const B of T.branches) {
      const steps = 14;
      const top = [], bot = [];
      for (let i = 0; i <= steps; i++) {
        const f = i / steps;
        const [px, py] = branchPoint(T, B, f, W, H);
        const th = H * lerp(0.016, 0.005, f);
        top.push([px, py - th / 2]);
        bot.push([px, py + th / 2]);
      }
      g.beginPath();
      top.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
      for (let i = bot.length - 1; i >= 0; i--) g.lineTo(bot[i][0], bot[i][1]);
      g.closePath();
      g.fillStyle = 'rgb(58,42,32)';
      g.fill();
      g.strokeStyle = 'rgba(120,92,64,0.5)';
      g.lineWidth = Math.max(1, H * 0.0018);
      g.beginPath();
      top.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
      g.stroke();
      const [ex, ey] = branchPoint(T, B, 1, W, H);
      for (let k = 0; k < 9; k++) {
        const a = rand() * Math.PI * 2, r = H * (0.012 + rand() * 0.028);
        const col = mix(P.LEAF[k % 4], P.GRASS_DARK, 0.15 + rand() * 0.2);
        gl.fillStyle = rgba(col, 1);
        gl.beginPath();
        gl.arc(ex + Math.cos(a) * H * 0.02, ey + Math.sin(a) * H * 0.02 - H * 0.01, r, 0, Math.PI * 2);
        gl.fill();
      }
    }
    for (let k = 0; k < 26; k++) {
      const a = rand() * Math.PI * 2, d = H * (0.04 + rand() * 0.16);
      const cx = xAt(0) + Math.cos(a) * d * 1.5, cy = H * 0.02 + Math.sin(a) * d * 0.55;
      const col = mix(P.LEAF[k % 4], P.GRASS_DARK, 0.1 + rand() * 0.3);
      gl.fillStyle = rgba(col, 1);
      gl.beginPath(); gl.arc(cx, cy, H * (0.035 + rand() * 0.05), 0, Math.PI * 2); gl.fill();
      gl.fillStyle = rgba(mix(col, [255, 250, 190], 0.28), 0.85);
      gl.beginPath(); gl.arc(cx - H * 0.012, cy - H * 0.014, H * (0.02 + rand() * 0.03), 0, Math.PI * 2); gl.fill();
    }
    g.fillStyle = 'rgb(48,34,26)';
    g.beginPath();
    g.moveTo(xAt(H) - bw(H) * 0.9, H);
    g.quadraticCurveTo(xAt(H) - bw(H) * 0.5, H * 0.95, xAt(H) - bw(H) * 0.5, H * 0.90);
    g.lineTo(xAt(H) + bw(H) * 0.5, H * 0.90);
    g.quadraticCurveTo(xAt(H) + bw(H) * 0.5, H * 0.95, xAt(H) + bw(H) * 0.9, H);
    g.closePath();
    g.fill();
  }
  return { wood: c, leaves: cl };
}

const SPECIES = {
  konadra: { top: [102, 128, 112], belly: [250, 214, 60], head: [24, 24, 30], cheek: [250, 250, 250], wing: [70, 94, 108], tail: [70, 94, 108], beak: [30, 30, 30] },
  cervenka: { top: [142, 102, 68], belly: [238, 232, 218], head: [142, 102, 68], cheek: [236, 112, 52], wing: [116, 82, 56], tail: [116, 82, 56], beak: [40, 30, 24], breast: [236, 112, 52] },
  modrinka: { top: [124, 172, 100], belly: [250, 226, 84], head: [236, 240, 246], cheek: [250, 250, 250], wing: [66, 118, 204], tail: [66, 118, 204], beak: [40, 40, 44], cap: [60, 120, 210] },
  sojka: { top: [206, 152, 132], belly: [226, 186, 168], head: [206, 152, 132], cheek: [230, 200, 186], wing: [40, 40, 50], tail: [40, 40, 50], beak: [40, 36, 36], patch: [58, 132, 226] },
  vrabec: { top: [152, 108, 66], belly: [222, 212, 198], head: [140, 90, 58], cheek: [238, 232, 222], wing: [120, 84, 52], tail: [120, 84, 52], beak: [60, 48, 40] },
};

function ell(g, x, y, rx, ry, rot, col) {
  g.fillStyle = rgba(col, 1);
  g.beginPath(); g.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), rot, 0, Math.PI * 2); g.fill();
}

// Pták v profilu; (x,y) = nohy při sezení / střed těla za letu, s = délka těla.
// pose: f směr pohledu, flap úhel křídla, fly, tilt (rad), turn 0..1 (hlava
// otočená přes rameno), peck 0..1 (předklon), tailUp 0..1
function drawBird(g, x, y, s, sp, pose) {
  const f = pose.f;
  g.save();
  g.translate(x, y);
  if (pose.fly) {
    g.rotate(pose.tilt * f);
    const a = pose.flap;
    g.fillStyle = rgba(mix(sp.wing, [0, 0, 0], 0.25), 1);
    g.beginPath();
    g.moveTo(-s * 0.02 * f, -s * 0.06);
    g.quadraticCurveTo(-s * 0.35 * f, -s * (0.45 * a + 0.1), -s * 0.20 * f - a * s * 0.05 * f, -s * (0.78 * a));
    g.quadraticCurveTo(-s * 0.06 * f, -s * (0.3 * a), s * 0.18 * f, -s * 0.04);
    g.closePath(); g.fill();
    ell(g, 0, 0, s * 0.40, s * 0.17, 0, sp.top);
    ell(g, 0, s * 0.05, s * 0.34, s * 0.11, 0, sp.belly);
    g.fillStyle = rgba(sp.tail, 1);
    g.beginPath();
    g.moveTo(-s * 0.30 * f, -s * 0.04); g.lineTo(-s * 0.74 * f, -s * 0.10); g.lineTo(-s * 0.74 * f, s * 0.07); g.lineTo(-s * 0.30 * f, s * 0.06);
    g.closePath(); g.fill();
    ell(g, s * 0.36 * f, -s * 0.07, s * 0.15, s * 0.13, 0, sp.head);
    ell(g, s * 0.40 * f, -s * 0.03, s * 0.08, s * 0.06, 0, sp.cheek);
    g.fillStyle = rgba(sp.beak, 1);
    g.beginPath();
    g.moveTo(s * 0.47 * f, -s * 0.10); g.lineTo(s * 0.62 * f, -s * 0.06); g.lineTo(s * 0.47 * f, -s * 0.02);
    g.closePath(); g.fill();
    g.fillStyle = 'rgb(18,18,20)';
    g.beginPath(); g.arc(s * 0.41 * f, -s * 0.10, Math.max(0.8, s * 0.025), 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba(sp.wing, 1);
    g.beginPath();
    g.moveTo(s * 0.10 * f, -s * 0.08);
    g.quadraticCurveTo(-s * 0.22 * f, -s * (0.55 * a + 0.1), -s * 0.34 * f - a * s * 0.06 * f, -s * (0.86 * a));
    g.quadraticCurveTo(-s * 0.14 * f, -s * (0.34 * a), s * 0.30 * f, -s * 0.02);
    g.closePath(); g.fill();
    if (sp.patch) {
      g.fillStyle = rgba(sp.patch, 1);
      g.beginPath(); g.ellipse(-s * 0.10 * f, -s * (0.34 * a + 0.06), s * 0.08, s * 0.05, 0, 0, Math.PI * 2); g.fill();
    }
  } else {
    const peck = pose.peck || 0;
    g.strokeStyle = 'rgb(90,70,56)';
    g.lineWidth = Math.max(1, s * 0.05);
    g.lineCap = 'round';
    for (const o of [-0.04, 0.10]) {
      g.beginPath(); g.moveTo(o * s * f, -s * 0.12); g.lineTo(o * s * f, 0); g.stroke();
      g.beginPath(); g.moveTo(o * s * f - s * 0.06 * f, 0); g.lineTo(o * s * f + s * 0.07 * f, 0); g.stroke();
    }
    g.save();
    g.translate(0, -s * 0.28);
    g.rotate((-0.28 + peck * 0.45) * f);
    g.fillStyle = rgba(sp.tail, 1);
    const tu = pose.tailUp || 0;
    g.beginPath();
    g.moveTo(-s * 0.26 * f, -s * 0.02);
    g.lineTo(-s * 0.74 * f, s * (0.10 - tu * 0.16));
    g.lineTo(-s * 0.72 * f, s * (0.20 - tu * 0.16));
    g.lineTo(-s * 0.24 * f, s * 0.12);
    g.closePath(); g.fill();
    ell(g, 0, 0, s * 0.38, s * 0.27, 0, sp.top);
    ell(g, s * 0.04 * f, s * 0.10, s * 0.31, s * 0.16, 0, sp.belly);
    if (sp.breast) ell(g, s * 0.22 * f, s * 0.04, s * 0.17, s * 0.19, 0, sp.breast);
    ell(g, -s * 0.06 * f, -s * 0.02, s * 0.25, s * 0.15, 0.2 * f, sp.wing);
    g.restore();
    const look = pose.turn || 0;
    const k = 1 - look * 1.6;
    const hx = s * 0.30 * f, hy = -s * (0.52 - peck * 0.12);
    ell(g, hx, hy, s * 0.17, s * 0.16, 0, sp.head);
    if (sp.cap) ell(g, hx - s * 0.01 * f, hy - s * 0.07, s * 0.15, s * 0.08, 0, sp.cap);
    ell(g, hx + s * 0.05 * f * k, hy + s * 0.05, s * 0.09, s * 0.07, 0, sp.cheek);
    g.fillStyle = rgba(sp.beak, 1);
    const bx = hx + s * 0.14 * f * k;
    g.beginPath();
    g.moveTo(bx, hy - s * 0.03);
    g.lineTo(bx + s * 0.15 * f * k, hy + s * 0.02);
    g.lineTo(bx, hy + s * 0.05);
    g.closePath(); g.fill();
    g.fillStyle = 'rgb(18,18,20)';
    g.beginPath(); g.arc(hx + s * 0.07 * f * k, hy - s * 0.02, Math.max(0.9, s * 0.032), 0, Math.PI * 2); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.9)';
    g.beginPath(); g.arc(hx + s * 0.08 * f * k, hy - s * 0.035, Math.max(0.4, s * 0.011), 0, Math.PI * 2); g.fill();
  }
  g.restore();
}

// Rozvrh ptáka je čistá funkce času: pryč → přílet → sedí → odlet. Nepotřebuje
// stav, takže po restartu scény se plynule rozjede.
const FLY_IN = 3.4, FLY_OUT = 2.8;

function curve(sx, sy, cx, cy, ex, ey, e) {
  const k = 1 - e;
  return [k * k * sx + 2 * k * e * cx + e * e * ex, k * k * sy + 2 * k * e * cy + e * e * ey,
          2 * k * (cx - sx) + 2 * e * (ex - cx), 2 * k * (cy - sy) + 2 * e * (ey - cy)];
}

function birdState(b, t, W, H, spots) {
  const total = b.away + FLY_IN + b.sit + FLY_OUT;
  const u = ((t + b.off) % total + total) % total;
  const sp = spots[b.spot];
  const px = sp.x * W, py = sp.y * H;
  if (u < b.away) return null;
  if (u < b.away + FLY_IN) {
    const p = (u - b.away) / FLY_IN;
    const e = 1 - Math.pow(1 - p, 2.2);
    const sx = b.fromX * W, sy = b.fromY * H;
    const [x, y, dx, dy] = curve(sx, sy, lerp(sx, px, 0.55), Math.min(sy, py) - H * 0.12, px, py, e);
    const land = clamp((p - 0.82) / 0.18, 0, 1);
    return { x, y, pose: { f: dx >= 0 ? 1 : -1, fly: true,
                           flap: Math.sin(t * lerp(13, 20, land) + b.ph) * (1 - land * 0.35) * 0.9 + 0.1,
                           tilt: clamp(Math.atan2(dy, Math.abs(dx)) * 0.7 - land * 0.5, -0.7, 0.8) } };
  }
  if (u < b.away + FLY_IN + b.sit) {
    const q = u - b.away - FLY_IN;
    const look = Math.max(0, Math.sin(q * b.lookRate + b.ph) - 0.55) / 0.45;
    const peck = Math.max(0, Math.sin(q * b.peckRate + b.ph * 2) - 0.8) / 0.2;
    const tail = Math.max(0, Math.sin(q * 1.7 + b.ph) - 0.7) / 0.3;
    const hop = Math.max(0, Math.sin(q * 0.6 + b.ph * 3) - 0.97) / 0.03;
    return { x: px, y: py - hop * H * 0.006,
             pose: { f: sp.face * b.mirror, fly: false, turn: look, peck, tailUp: tail } };
  }
  const p = (u - b.away - FLY_IN - b.sit) / FLY_OUT;
  const ex = b.toX * W, ey = b.toY * H;
  const [x, y, dx, dy] = curve(px, py, lerp(px, ex, 0.4), Math.min(py, ey) - H * 0.10, ex, ey, p * p);
  return { x, y, pose: { f: dx >= 0 ? 1 : -1, fly: true, flap: Math.sin(t * 17 + b.ph) * 0.9 + 0.1,
                         tilt: clamp(Math.atan2(dy, Math.abs(dx)) * 0.7, -0.7, 0.8) } };
}

// ---------------------------------------------------------------- factory

export function create() {
  function buildSky(W, H) {
    const c = makeCanvas(W, H * 0.62), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H * HORIZON);
    grad.addColorStop(0.00, rgba(P.SKY_TOP, 1));
    grad.addColorStop(0.42, rgba(P.SKY_MID, 1));
    grad.addColorStop(0.80, rgba(P.SKY_LOW, 1));
    grad.addColorStop(1.00, rgba(P.SKY_HAZE, 1));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H * HORIZON + 2);
    const sx = W * 0.74, sy = H * 0.155, sr = H * 0.30;
    const glow = g.createRadialGradient(sx, sy, 0, sx, sy, sr);
    glow.addColorStop(0.00, 'rgba(255,250,226,0.95)');
    glow.addColorStop(0.10, 'rgba(255,244,206,0.55)');
    glow.addColorStop(0.45, 'rgba(255,236,196,0.16)');
    glow.addColorStop(1.00, 'rgba(255,236,196,0)');
    g.fillStyle = glow;
    g.beginPath(); g.arc(sx, sy, sr, 0, Math.PI * 2); g.fill();
    g.fillStyle = 'rgba(255,253,240,0.92)';
    g.beginPath(); g.arc(sx, sy, H * 0.028, 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba(mix(P.SKY_HAZE, P.GRASS_FAR, 0.5), 1);
    g.fillRect(0, H * HORIZON, W, H * 0.2);
    return { canvas: c, sunX: sx, sunY: sy };
  }

  function buildClouds(W, H, rand, o) {
    const y0 = Math.round(H * o.band[0]);
    const c = makeCanvas(W, H * (o.band[1] - o.band[0])), g = c.getContext('2d');
    g.translate(0, -y0);
    for (let i = 0; i < o.count; i++) {
      const cx = rand() * W;
      const cy = H * (o.y0 + rand() * (o.y1 - o.y0));
      const cw = H * o.size * (0.6 + rand() * 0.9);
      const ch = cw * (o.flat ? 0.14 : 0.30) * (0.7 + rand() * 0.6);
      const puffs = o.flat ? 5 : 9;
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
      for (const rp of reps) {
        for (let j = 0; j < puffs; j++) {
          const px = cx + rp + seeds[j][0], py = cy + seeds[j][1], pr = seeds[j][2];
          const gr = g.createRadialGradient(px, py - pr * 0.2, pr * 0.1, px, py, pr);
          gr.addColorStop(0, 'rgba(255,255,255,' + o.alpha + ')');
          gr.addColorStop(0.55, 'rgba(250,250,255,' + o.alpha * 0.55 + ')');
          gr.addColorStop(1, 'rgba(250,250,255,0)');
          g.fillStyle = gr;
          g.beginPath(); g.arc(px, py, pr, 0, Math.PI * 2); g.fill();
        }
      }
    }
    return { canvas: c, y0: y0 };
  }

  // Kopce a čtyři vrstvy lesa. Vzdálené vrstvy se mísí s oparem, nejbližší je
  // sytě zelená; stromy v ní jsou největší a mají světlejší vršky korun.
  function buildLand(W, H, rand) {
    const y0 = Math.round(H * 0.16);
    const c = makeCanvas(W, H * (0.62 - 0.16)), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;

    const ridges = [
      { w: waveFn(rand, 4, 3.1 / W, 0.55), h: H * 0.105, base: H * (HORIZON + 0.012), col: P.RIDGE_FAR, haze: 0.40 },
      { w: waveFn(rand, 5, 5.3 / W, 0.52), h: H * 0.070, base: H * (HORIZON + 0.030), col: P.RIDGE_NEAR, haze: 0.18 },
    ];
    for (const R of ridges) {
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

    const hz = g.createLinearGradient(0, H * (HORIZON - 0.03), 0, H * (HORIZON + 0.075));
    hz.addColorStop(0, 'rgba(252,236,200,0)');
    hz.addColorStop(0.45, 'rgba(252,236,200,0.5)');
    hz.addColorStop(1, 'rgba(252,236,200,0)');
    g.fillStyle = hz;
    g.fillRect(0, H * (HORIZON - 0.03), W, H * 0.105);

    const bands = [
      { top: FOREST_TOP + 0.020, base: FOREST_BASE - 0.052, h: 0.064, haze: 0.55, dens: 0.026, leafy: 0.40 },
      { top: FOREST_TOP + 0.008, base: FOREST_BASE - 0.032, h: 0.082, haze: 0.34, dens: 0.032, leafy: 0.46 },
      { top: FOREST_TOP - 0.004, base: FOREST_BASE - 0.012, h: 0.102, haze: 0.16, dens: 0.040, leafy: 0.50 },
      { top: FOREST_TOP - 0.018, base: FOREST_BASE, h: 0.126, haze: 0.00, dens: 0.050, leafy: 0.52 },
    ];
    bands.forEach((B, i) => {
      const dark = mix(P.FOREST[i], P.SKY_HAZE, B.haze);
      const baseY = H * B.base;
      const ug = g.createLinearGradient(0, baseY - H * 0.020, 0, baseY + H * 0.010);
      ug.addColorStop(0, rgba(dark, 0));
      ug.addColorStop(0.55, rgba(dark, 1));
      ug.addColorStop(1, rgba(dark, 1));
      g.fillStyle = ug;
      g.fillRect(0, baseY - H * 0.020, W, H * 0.030);
      const step = W * B.dens;
      for (x = -step; x < W + step; x += step * (0.55 + rand() * 0.55)) {
        const th = H * B.h * (0.72 + rand() * 0.62);
        const tw = th * (0.28 + rand() * 0.14);
        const by = baseY + H * 0.004 * (rand() - 0.5);
        const r = rand();
        if (r < 1 - B.leafy) {
          g.fillStyle = rgba(dark, 1);
          drawSpruce(g, x, by, th, tw, rgba(dark, 1), rand);
        } else if (r < 1 - B.leafy * 0.35) {
          const crown = mix(mix(P.LEAF[(i + Math.floor(rand() * 3)) % 4], dark, 0.5 + 0.1 * (3 - i)), P.SKY_HAZE, B.haze * 0.5);
          drawLeafy(g, x, by, th, tw * 1.5, rgba(mix(P.TRUNK, dark, 0.5), 1), rgba(crown, 1),
                    i >= 2 ? rgba(mix(crown, [255, 250, 190], 0.28), 1) : null, rand);
        } else {
          const crown = mix(P.LEAF[1], dark, 0.45 + B.haze * 0.4);
          drawBirch(g, x, by, th, tw * 1.35, rgba(crown, 1),
                    i >= 2 ? rgba(mix(crown, [255, 250, 190], 0.3), 1) : null, rand);
        }
      }
      // pár podzimně zbarvených korun v blízkých vrstvách pro barevnou pestrost
      if (i >= 2) {
        for (let k = 0; k < 3 + i; k++) {
          const ax = rand() * W;
          const th = H * B.h * (0.8 + rand() * 0.4);
          const col = mix(P.AUTUMN[k % 2], dark, 0.30 + 0.1 * (3 - i));
          drawLeafy(g, ax, baseY, th, th * 0.42, rgba(mix(P.TRUNK, dark, 0.5), 1), rgba(col, 1),
                    rgba(mix(col, [255, 240, 150], 0.25), 1), rand);
        }
      }
    });
    return { canvas: c, y0: y0 };
  }

  // Louka, cestička a všechno, co leží NA zemi nebo za tvory: tráva, květiny,
  // střední plán (keře, pařezy, kameny, mladé stromky) a hustý lem pod lesem.
  function buildGround(W, H, rand) {
    const y0 = Math.round(H * GROUND_TOP);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const aspect = W / H;
    let x;

    // základ louky: perspektivní přechod; horní okraj průhledný, ať se zaplete
    // do paty lesa
    const base = g.createLinearGradient(0, H * GROUND_TOP, 0, H);
    base.addColorStop(0.00, rgba(P.GRASS_FAR, 0));
    base.addColorStop(0.05, rgba(mix(P.GRASS_FAR, P.FOREST[3], 0.25), 1));
    base.addColorStop(0.20, rgba(P.GRASS_FAR, 1));
    base.addColorStop(0.55, rgba(P.GRASS_MID, 1));
    base.addColorStop(1.00, rgba(P.GRASS_NEAR, 1));
    g.fillStyle = base;
    g.fillRect(0, H * GROUND_TOP, W, H - H * GROUND_TOP);

    // světlejší a tmavší skvrny trávy, ve vzdálenosti jemné, vpředu velké
    const patch = waveFn(rand, 4, 7.0 / W, 0.55);
    for (let i = 0; i < 160; i++) {
      const t = rand();
      const yy = H * lerp(0.53, 1.0, Math.pow(t, 0.85));
      const xx = rand() * W;
      const d = depthScale(yy / H);
      const rw = W * (0.02 + 0.10 * d) * (0.5 + rand());
      const rh = rw * 0.16;
      const light = patch(xx + yy * 0.3) > 0;
      g.fillStyle = light ? rgba(P.GRASS_LIGHT, 0.13) : rgba(P.GRASS_DARK, 0.11);
      g.beginPath(); g.ellipse(xx, yy, rw, rh, 0, 0, Math.PI * 2); g.fill();
    }

    // cestička: z dálky ke spodnímu okraji, ve středu se klikatí
    const cx = (yf) => W * trailX(yf);
    const hw = (yf) => W * trailHalf(yf);
    const left = [], right = [];
    for (let yy = 0.53; yy <= 1.005; yy += 0.01) {
      const wob = (waveFn(rand, 2, 1, 0.5)(yy * 5) * 0.05 + 1);
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
    pg.addColorStop(0, rgba(mix(P.PATH, P.SKY_HAZE, 0.3), 1));
    pg.addColorStop(1, rgba(P.PATH, 1));
    g.fillStyle = pg;
    g.fill();
    g.save();
    outline();
    g.clip();
    // koleje a kamínky
    for (const off of [-0.45, 0.45]) {
      g.beginPath();
      for (let yy = 0.53; yy <= 1.005; yy += 0.01) {
        const px = cx(yy) + hw(yy) * off;
        if (yy === 0.53) g.moveTo(px, H * yy); else g.lineTo(px, H * yy);
      }
      g.strokeStyle = rgba(P.PATH_DARK, 0.45);
      g.lineWidth = Math.max(1, H * 0.006);
      g.stroke();
    }
    for (let i = 0; i < 900; i++) {
      const yf = 0.53 + Math.pow(rand(), 0.8) * 0.47;
      const px = cx(yf) + (rand() - 0.5) * 2 * hw(yf);
      const d = depthScale(yf);
      const s = H * 0.0012 * (0.5 + d * 3) * (0.6 + rand());
      g.fillStyle = rand() < 0.5 ? rgba(P.PATH_DARK, 0.5) : rgba(P.PATH_LIGHT, 0.7);
      g.beginPath(); g.ellipse(px, H * yf, s * 1.5, s, 0, 0, Math.PI * 2); g.fill();
    }
    g.restore();
    // okraj cestičky zarůstá trávou
    for (let i = 0; i < 260; i++) {
      const yf = 0.54 + Math.pow(rand(), 0.85) * 0.46;
      const side = rand() < 0.5 ? -1 : 1;
      const px = cx(yf) + side * hw(yf) * (0.92 + rand() * 0.2);
      const d = depthScale(yf);
      tuft(g, px, H * yf, H * (0.008 + 0.034 * d), rgba(mix(P.GRASS_DARK, P.GRASS_MID, rand()), 1), rand, 4);
    }

    // květiny a trsy trávy po celé louce, hustší a větší blíž k divákovi
    const FL = 2000;
    for (let i = 0; i < FL; i++) {
      const t = rand();
      const yf = lerp(0.53, 1.0, Math.pow(t, 0.7));
      const d = depthScale(yf);
      const px = rand() * W;
      if (Math.abs(px - cx(yf)) < hw(yf) * 0.9) continue;
      const cluster = patch(px * 1.3 + yf * 900) > 0.15;
      if (!cluster && rand() < 0.6) continue;
      const col = P.FLOWERS[Math.floor(rand() * rand() * P.FLOWERS.length)];
      flower(g, px, H * yf, Math.max(0.9, H * 0.0014 * (0.6 + d * 3.2) * (0.7 + rand() * 0.6)), col, rand);
    }
    for (let i = 0; i < 380; i++) {
      const yf = lerp(0.535, 0.795, Math.pow(rand(), 0.8));
      const px = rand() * W;
      if (Math.abs(px - cx(yf)) < hw(yf) * 0.8) continue;
      const d = depthScale(yf);
      tuft(g, px, H * yf, H * (0.006 + 0.03 * d) * (0.7 + rand() * 0.6),
           rgba(mix(P.GRASS_DARK, P.GRASS_LIGHT, rand() * 0.7), 0.95), rand, 4 + Math.floor(rand() * 3));
    }

    // lem pod lesem: drobné kapradiny a keříky s patou nad zadními drahami
    for (let i = 0; i < Math.round(aspect * 16); i++) {
      const fx = rand() * W;
      const fy = H * (0.512 + rand() * 0.008);
      if (rand() < 0.5) fern(g, fx, fy, H * (0.012 + rand() * 0.008), rand);
      else bush(g, fx, fy, H * (0.014 + rand() * 0.01), rand, null);
    }

    // střední plán: patou 0,60–0,79, tedy mezi zadními a předními drahami
    const wob = waveFn(rand, 3, 1.2, 0.5);
    const items = [];
    const placed = (xx, yy) => items.some(([ax, ay]) => Math.abs(ax - xx) < W * 0.06 && Math.abs(ay - yy) < H * 0.06);
    const spots = Math.round(aspect * 9);
    for (let i = 0; i < spots; i++) {
      let xx, yy, tries = 0;
      do {
        xx = rand() * W; yy = H * (0.60 + rand() * 0.185); tries++;
      } while ((Math.abs(xx - cx(yy / H)) < hw(yy / H) * 1.25 || placed(xx, yy)) && tries < 20);
      items.push([xx, yy, rand()]);
    }
    items.sort((a, b) => a[1] - b[1]);
    for (const [xx, yy, r] of items) {
      const d = depthScale(yy / H);
      const s = H * (0.025 + 0.09 * d);
      if (r < 0.28) bush(g, xx, yy, s, rand, rand() < 0.5 ? [200, 40, 60] : null);
      else if (r < 0.46) rock(g, xx, yy, s * 0.9, rand, wob);
      else if (r < 0.60) stump(g, xx, yy, s * 0.75, rand);
      else if (r < 0.70) log(g, xx, yy, s * 2.2, rand);
      else if (r < 0.82) {
        const th = Math.min(H * (0.045 + 0.20 * d), H * 0.115);
        if (rand() < 0.5) drawSpruce(g, xx, yy, th, th * 0.34, rgba(mix(P.FOREST[3], P.LEAF[2], 0.2), 1), rand);
        else drawBirch(g, xx, yy, th, th * 0.62, rgba(P.LEAF[1], 1), rgba(mix(P.LEAF[1], [255, 250, 190], 0.3), 1), rand);
      } else {
        for (let k = 0; k < 4; k++) fern(g, xx + (k - 1.5) * s * 0.5, yy + (rand() - 0.5) * s * 0.2, s * 0.7, rand);
      }
      if (r > 0.28 && r < 0.6) {
        for (let k = 0; k < 3; k++) {
          mushroom(g, xx + (rand() - 0.5) * s * 1.4, yy + s * 0.05, s * (0.14 + rand() * 0.1),
                   rand() < 0.5 ? [214, 56, 50] : [226, 196, 150]);
        }
      }
    }

    return { canvas: c, y0: y0 };
  }

  // Zelenina NAD tvory: keře a kapradí v rozích a vysoká tráva u spodního okraje
  function buildFront(W, H, rand) {
    const y0 = Math.round(H * 0.66);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const aspect = W / H;
    const wob = waveFn(rand, 3, 1.2, 0.5);

    const corners = [[0.02, 0.10], [0.90, 0.99], [0.14, 0.26], [0.74, 0.88]];
    corners.forEach((cr, k) => {
      const x = W * (cr[0] + rand() * (cr[1] - cr[0]) * 0.5);
      const s = H * (0.09 + rand() * 0.04);
      if (k % 2 === 0) bush(g, x, H * (0.995 + rand() * 0.02), s * 1.5, rand, k === 0 ? [208, 44, 66] : null);
      else rock(g, x, H * 1.0, s * 1.2, rand, wob);
    });
    for (let i = 0; i < Math.round(aspect * 6); i++) {
      const pos = i / Math.max(1, Math.round(aspect * 6) - 1);
      const x = W * (pos < 0.5 ? pos * 0.4 + rand() * 0.06 : 0.62 + (pos - 0.5) * 0.76 + rand() * 0.06);
      fern(g, x, H * (0.975 + rand() * 0.04), H * (0.09 + rand() * 0.06), rand);
    }
    for (let i = 0; i < Math.round(aspect * 30); i++) {
      const edge = rand() < 0.5 ? rand() * 0.28 : 0.72 + rand() * 0.28;
      tuft(g, W * edge, H * (0.985 + rand() * 0.02), H * (0.05 + rand() * 0.04),
           rgba(mix(P.GRASS_DARK, P.GRASS_LIGHT, rand() * 0.6), 1), rand, 6);
    }
    for (let i = 0; i < 30; i++) {
      const edge = rand() < 0.5 ? rand() * 0.3 : 0.7 + rand() * 0.3;
      flower(g, W * edge, H * (0.96 + rand() * 0.04), H * (0.003 + rand() * 0.003),
             P.FLOWERS[Math.floor(rand() * P.FLOWERS.length)], rand);
    }
    return { canvas: c, y0: y0 };
  }

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const sky = buildSky(W, H);
    const far = buildClouds(W, H, rand, { count: 8, y0: 0.05, y1: 0.15, size: 0.11, alpha: 0.30, flat: true, band: [0, 0.23] });
    const near = buildClouds(W, H, rand, { count: 6, y0: 0.13, y1: 0.29, size: 0.17, alpha: 0.62, flat: false, band: [0.02, 0.37] });
    const land = buildLand(W, H, rand);
    const ground = buildGround(W, H, rand);
    const front = buildFront(W, H, rand);
    const trunks = drawTrunks(W, H, rand);
    const spots = perchSpots(W, H);
    const names = Object.keys(SPECIES);
    const order = spots.map((_, i) => i).sort(() => rand() - 0.5);
    const birds = [];
    for (let i = 0; i < 8; i++) {
      const spot = order[i];
      const fromLeft = spots[spot].x < 0.5 ? rand() < 0.7 : rand() < 0.3;
      const away = 14 + rand() * 30, sit = 12 + rand() * 20;
      birds.push({ spot, sp: SPECIES[names[i % names.length]], away, sit,
                   off: rand() * (away + sit + FLY_IN + FLY_OUT), ph: rand() * 6.28,
                   mirror: rand() < 0.2 ? -1 : 1,
                   fromX: fromLeft ? -0.06 : 1.06, fromY: 0.10 + rand() * 0.22,
                   toX: rand() < 0.5 ? -0.06 : 1.06, toY: 0.05 + rand() * 0.2,
                   lookRate: 1.1 + rand() * 0.8, peckRate: 0.9 + rand() * 0.9 });
    }

    const blades = [];
    for (let i = 0; i < 26; i++) {
      blades.push({ x: rand(), y: 0.94 + rand() * 0.06, h: 0.05 + rand() * 0.075, lean: (rand() - 0.5) * 0.8,
                    ph: rand() * Math.PI * 2, sp: 0.5 + rand() * 0.6 });
    }
    const flies = [];
    for (let i = 0; i < 5; i++) {
      flies.push({ cx: 0.15 + rand() * 0.7, cy: 0.58 + rand() * 0.25, ax: 0.05 + rand() * 0.10, ay: 0.02 + rand() * 0.04,
                   sp: 0.12 + rand() * 0.10, ph: rand() * 6.28, col: [P.FLOWERS[1], P.FLOWERS[2], [250, 250, 250], [255, 150, 60], [130, 170, 250]][i] });
    }
    const motes = [];
    for (let i = 0; i < 46; i++) {
      motes.push({ x: rand(), y: 0.35 + rand() * 0.6, sp: 0.004 + rand() * 0.01, dr: rand() * 6.28, r: 0.6 + rand() * 1.6, ph: rand() * 6.28 });
    }
    const leaves = [];
    for (let i = 0; i < 7; i++) {
      leaves.push({ x: rand(), p: rand(), sp: 0.012 + rand() * 0.012, sw: 0.02 + rand() * 0.03,
                    ph: rand() * 6.28, col: [P.AUTUMN[0], P.AUTUMN[1], [170, 190, 70]][i % 3] });
    }

    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.5, H * 0.52, H * 0.38, W * 0.5, H * 0.52, H * 0.95);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, P.vignette);
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);

    return { W, H, sky, vig, cloudFar: far, cloudNear: near, land, ground, front, trunks, spots, birds, claims: new Map(), blades, flies, motes, leaves };
  }

  function drawBlades(ctx, W, H, t, S) {
    ctx.save();
    ctx.lineCap = 'round';
    for (let i = 0; i < S.blades.length; i++) {
      const B = S.blades[i];
      const x = B.x * W, y = B.y * H, h = B.h * H;
      const sway = Math.sin(t * B.sp + B.ph) * 0.10 + B.lean * 0.25;
      ctx.strokeStyle = i % 3 === 0 ? rgba(P.GRASS_MID, 0.9) : rgba(P.GRASS_DARK, 0.9);
      ctx.lineWidth = Math.max(1, H * 0.0024);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(x + h * sway * 0.6, y - h * 0.6, x + h * (sway + B.lean * 0.4), y - h);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Sluneční paprsky skrz koruny: široké šikmé pruhy z obzoru vpravo nahoře,
  // pomalu se přelévá jejich průhlednost.
  function drawRays(ctx, W, H, t, S) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const sx = S.sky.sunX, sy = S.sky.sunY;
    for (let i = 0; i < 6; i++) {
      const a = 0.30 + i * 0.19;
      const spread = 0.045 + (i % 3) * 0.02;
      const al = 0.035 + 0.025 * Math.sin(t * 0.18 + i * 1.7);
      const g = ctx.createLinearGradient(sx, sy, sx - Math.cos(a) * W * 0.7, sy + Math.sin(a) * H * 1.1);
      g.addColorStop(0, 'rgba(255,244,200,' + al * 1.6 + ')');
      g.addColorStop(1, 'rgba(255,244,200,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(sx - Math.cos(a - spread) * W * 1.3, sy + Math.sin(a - spread) * H * 2.2);
      ctx.lineTo(sx - Math.cos(a + spread) * W * 1.3, sy + Math.sin(a + spread) * H * 2.2);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawLife(ctx, W, H, t, S) {
    ctx.save();
    for (const m of S.motes) {
      const y = ((m.y - t * m.sp) % 1 + 1) % 1 * 0.6 + 0.38;
      const x = (m.x + Math.sin(t * 0.2 + m.dr) * 0.02) * W;
      ctx.globalAlpha = 0.35 + 0.35 * Math.sin(t * 1.3 + m.ph);
      ctx.fillStyle = 'rgba(255,248,210,1)';
      ctx.beginPath(); ctx.arc(x, y * H, H * 0.0014 * m.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    for (const f of S.flies) {
      const u = t * f.sp + f.ph;
      const x = (f.cx + Math.sin(u) * f.ax + Math.sin(u * 2.3) * f.ax * 0.3) * W;
      const y = (f.cy + Math.sin(u * 1.4) * f.ay) * H;
      const flap = Math.abs(Math.sin(t * 9 + f.ph));
      const s = H * 0.011;
      ctx.fillStyle = rgba(f.col, 0.95);
      for (const sg of [-1, 1]) {
        ctx.beginPath();
        ctx.ellipse(x + sg * s * 0.45 * flap, y, s * 0.55 * (0.25 + flap * 0.75), s * 0.8, sg * 0.35, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(40,30,24,0.9)';
      ctx.fillRect(x - s * 0.06, y - s * 0.45, s * 0.12, s * 0.9);
    }
    for (const l of S.leaves) {
      const p = (l.p + t * l.sp) % 1;
      const x = (l.x + Math.sin(t * 0.6 + l.ph) * l.sw * 2) * W;
      const y = (0.12 + p * 0.85) * H;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.sin(t * 0.8 + l.ph) * 1.1);
      ctx.globalAlpha = Math.sin(Math.PI * p) * 0.9;
      ctx.fillStyle = rgba(l.col, 1);
      ctx.beginPath();
      ctx.ellipse(0, 0, H * 0.008, H * 0.0035, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
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
    ctx.drawImage(S.ground.canvas, 0, S.ground.y0);
    ctx.drawImage(S.trunks.leaves, 0, 0);
  }

  function drawFront(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    ctx.drawImage(state.front.canvas, 0, state.front.y0);
    drawBlades(ctx, W, H, t, state);
    ctx.drawImage(state.trunks.wood, 0, 0);
    for (const b of state.birds) {
      if ((state.claims.get(b.spot) || 0) > t) continue;
      const st = birdState(b, t, W, H, state.spots);
      if (st) drawBird(ctx, st.x, st.y, H * 0.036, b.sp, st.pose);
    }
    drawRays(ctx, W, H, t, state);
    drawLife(ctx, W, H, t, state);
    ctx.drawImage(state.vig, 0, 0);
  }

  // Místa k sezení pro vybarvené ptáky ze scény: `free` = nikdo tam teď ani
  // během příštích pár vteřin nesedí. `claim` místo zabere (dvojrozměrný pták
  // tam do té doby nechodí).
  function perches(t) {
    if (!state) return [];
    return state.spots.map((sp, i) => ({
      x: sp.x, y: sp.y, face: sp.face,
      free: !((state.claims.get(i) || 0) > t)
        && !state.birds.some(b => b.spot === i
          && (birdState(b, t, state.W, state.H, state.spots) || birdState(b, t + 6, state.W, state.H, state.spots))),
    }));
  }

  function claim(i, until) {
    if (state) state.claims.set(i, until);
  }

  return { draw, drawFront, sun: { x: 0.74, y: 0.155 }, depthScale, perches, claim };
}
