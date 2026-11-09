/* Květnatá louka — malovaná krajina pro 2D plátno pod 3D tvory (broučí svět).

   ES modul s továrnou `create()`; vrací `{draw, drawFront, sun, depthScale}`
   stejně jako forest.js, takže scéna jen vymění cestu v render.js.

   Rozvržení drží stejné pásy jako les, ať se dráhy z render.js nemění:
     0,00–0,44  modrá obloha s mráčky, slunce vpravo nahoře
     0,34–0,50  tři vrstvy kopců v oparu (lány řepky, vzdálené stromořadí není)
     0,45–0,57  zadní louka — tady jdou zadní dráhy (0,532 / 0,558)
     0,58–0,79  střední louka: souvislá tráva, trsy květů, kameny — kreslí se
                POD tvory
     0,80–0,95  přední louka — přední dráhy (0,815 / 0,88 / 0,945)
     od 0,96    vysoká stébla a velké květy v rozích, kreslí se NAD tvory
                (drawFront), stébla se vlní ve větru
   Přes trávu se pomalu valí vlna větru (světlé a tmavé pruhy). */

const SEED = 20260611;

const HORIZON = 0.44;
const GROUND_TOP = 0.445;

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

const P = {
  SKY_TOP: [48, 124, 214], SKY_MID: [112, 184, 242], SKY_LOW: [190, 226, 248],
  SKY_HAZE: [236, 244, 236],
  RIDGE: [[158, 196, 214], [128, 180, 164], [104, 166, 96]],
  RAPE: [232, 210, 84],
  GRASS_FAR: [150, 196, 98], GRASS_MID: [110, 176, 62], GRASS_NEAR: [78, 148, 44],
  GRASS_DARK: [40, 106, 36], GRASS_LIGHT: [184, 222, 96],
  ROCK: [132, 130, 122], ROCK_LIT: [182, 178, 164], MOSS: [88, 140, 54],
  DAISY: [252, 252, 248], DAISY_EYE: [248, 190, 36],
  POPPY: [226, 36, 28], POPPY_DARK: [168, 18, 22],
  CLOVER: [226, 108, 172], CLOVER_ALT: [244, 244, 232],
  DANDE: [252, 208, 20], DANDE_DARK: [236, 164, 12],
  BELL: [110, 108, 226], BELL_DARK: [70, 66, 176],
  STEM: [64, 138, 44],
  vignette: 'rgba(16,40,10,0.18)',
};

// ------------------------------------------------------------ ground bits

// Trsy trávy se kreslí po řádcích do jedné cesty na barvu (`buckets`), aby
// vykreslení desítek tisíc stébel zabralo zlomek vteřiny.
function addTuft(buckets, rand, x, y, s, blades) {
  for (let i = 0; i < blades; i++) {
    const sp = blades === 1 ? 0 : (i / (blades - 1) - 0.5) * 2;
    const b = buckets[Math.floor(rand() * buckets.length)].path;
    b.moveTo(x + sp * s * 0.18, y);
    b.quadraticCurveTo(x + sp * s * 0.40, y - s * 0.6, x + sp * s * (0.62 + rand() * 0.3), y - s * (0.75 + rand() * 0.45));
  }
}

function makeBuckets(cols) {
  return cols.map(c => ({ col: c, path: new Path2D() }));
}

function flushBuckets(g, buckets, lw) {
  g.lineCap = 'round';
  g.lineWidth = lw;
  for (const b of buckets) {
    g.strokeStyle = b.col;
    g.stroke(b.path);
    b.path = new Path2D();
  }
}

function stem(g, x, y, hx, hy, w, col) {
  g.strokeStyle = col;
  g.lineWidth = w;
  g.lineCap = 'round';
  g.beginPath();
  g.moveTo(x, y);
  g.quadraticCurveTo(x + (hx - x) * 0.15, y + (hy - y) * 0.55, hx, hy);
  g.stroke();
}

function leafPair(g, x, y, len, col) {
  g.fillStyle = col;
  for (const sg of [-1, 1]) {
    g.beginPath();
    g.moveTo(x, y);
    g.quadraticCurveTo(x + sg * len * 0.55, y - len * 0.55, x + sg * len, y - len * 0.30);
    g.quadraticCurveTo(x + sg * len * 0.55, y - len * 0.20, x, y);
    g.fill();
  }
}

// Kopretina: bílé okvětní lístky kolem žlutého středu, pohled mírně shora.
function daisy(g, x, y, r, rand) {
  if (r < 1.8) {
    g.fillStyle = rgba(P.DAISY, 1);
    g.beginPath(); g.arc(x, y, Math.max(0.8, r), 0, Math.PI * 2); g.fill();
    return;
  }
  const n = 13, sq = 0.72;
  const rot = rand() * 6.28;
  for (let ring = 0; ring < 2; ring++) {
    g.fillStyle = ring ? rgba(P.DAISY, 1) : rgba([218, 226, 232], 1);
    for (let i = 0; i < n; i++) {
      const a = rot + (i / n) * Math.PI * 2 + ring * 0.24;
      const rr = r * (ring ? 0.98 : 1.02);
      g.beginPath();
      g.ellipse(x + Math.cos(a) * rr * 0.58, y + Math.sin(a) * rr * 0.58 * sq,
                rr * 0.46, rr * 0.19, a, 0, Math.PI * 2);
      g.fill();
    }
  }
  g.fillStyle = rgba(P.DAISY_EYE, 1);
  g.beginPath(); g.ellipse(x, y, r * 0.34, r * 0.34 * sq, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = rgba([210, 140, 20], 0.7);
  g.beginPath(); g.ellipse(x + r * 0.07, y + r * 0.05, r * 0.2, r * 0.2 * sq, 0, 0, Math.PI * 2); g.fill();
}

// Vlčí mák: sytě rudá miska ze čtyř lupenů a tmavý střed.
function poppy(g, x, y, r, rand) {
  if (r < 1.8) {
    g.fillStyle = rgba(P.POPPY, 1);
    g.beginPath(); g.arc(x, y, Math.max(0.9, r), 0, Math.PI * 2); g.fill();
    return;
  }
  const rot = rand() * 6.28;
  for (let i = 0; i < 4; i++) {
    const a = rot + i * Math.PI / 2;
    const px = x + Math.cos(a) * r * 0.5, py = y + Math.sin(a) * r * 0.42;
    g.fillStyle = rgba(P.POPPY_DARK, 1);
    g.beginPath(); g.ellipse(px, py, r * 0.64, r * 0.56, a, 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba(P.POPPY, 1);
    g.beginPath(); g.ellipse(px - r * 0.03, py - r * 0.04, r * 0.58, r * 0.50, a, 0, Math.PI * 2); g.fill();
  }
  g.fillStyle = 'rgba(250,120,100,0.35)';
  g.beginPath(); g.ellipse(x - r * 0.25, y - r * 0.3, r * 0.3, r * 0.14, -0.4, 0, Math.PI * 2); g.fill();
  g.fillStyle = 'rgb(36,26,30)';
  g.beginPath(); g.ellipse(x, y, r * 0.24, r * 0.2, 0, 0, Math.PI * 2); g.fill();
  g.strokeStyle = 'rgb(36,26,30)';
  g.lineWidth = Math.max(1, r * 0.06);
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * Math.PI * 2;
    g.beginPath();
    g.moveTo(x + Math.cos(a) * r * 0.2, y + Math.sin(a) * r * 0.17);
    g.lineTo(x + Math.cos(a) * r * 0.36, y + Math.sin(a) * r * 0.30);
    g.stroke();
  }
}

// Jetel: kulatá hlavička z drobných kvítků, pod ní trojlist.
function clover(g, x, y, r, rand, white) {
  const col = white ? P.CLOVER_ALT : P.CLOVER;
  if (r < 1.8) {
    g.fillStyle = rgba(col, 1);
    g.beginPath(); g.arc(x, y, Math.max(0.9, r * 0.85), 0, Math.PI * 2); g.fill();
    return;
  }
  const n = 16;
  for (let i = 0; i < n; i++) {
    const a = rand() * 6.28, d = Math.sqrt(rand()) * r * 0.62;
    const px = x + Math.cos(a) * d, py = y + Math.sin(a) * d * 0.9;
    g.fillStyle = rgba(mix(col, i % 2 ? [255, 255, 255] : P.CLOVER_ALT, i % 2 ? 0.0 : 0.15), 1);
    g.beginPath(); g.ellipse(px, py, r * 0.30, r * 0.20, a, 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba(mix(col, [120, 40, 90], 0.35), 0.55);
    g.beginPath(); g.arc(px + r * 0.05, py + r * 0.07, r * 0.10, 0, Math.PI * 2); g.fill();
  }
}

// Pampeliška: žlutá chmýřitá hvězda, někde už bílá „pouš".
function dandelion(g, x, y, r, rand, puff) {
  if (r < 1.8) {
    g.fillStyle = rgba(puff ? [236, 238, 232] : P.DANDE, 1);
    g.beginPath(); g.arc(x, y, Math.max(0.9, r), 0, Math.PI * 2); g.fill();
    return;
  }
  if (puff) {
    g.fillStyle = 'rgba(238,240,236,0.55)';
    g.beginPath(); g.arc(x, y, r * 0.95, 0, Math.PI * 2); g.fill();
    g.strokeStyle = 'rgba(250,250,246,0.9)';
    g.lineWidth = Math.max(1, r * 0.06);
    for (let i = 0; i < 26; i++) {
      const a = i / 26 * Math.PI * 2 + rand() * 0.2;
      g.beginPath();
      g.moveTo(x + Math.cos(a) * r * 0.1, y + Math.sin(a) * r * 0.1);
      g.lineTo(x + Math.cos(a) * r * 0.98, y + Math.sin(a) * r * 0.98);
      g.stroke();
      g.fillStyle = 'rgba(255,255,255,0.95)';
      g.beginPath(); g.arc(x + Math.cos(a) * r * 0.98, y + Math.sin(a) * r * 0.98, Math.max(0.6, r * 0.07), 0, Math.PI * 2); g.fill();
    }
    g.fillStyle = 'rgba(150,140,110,0.8)';
    g.beginPath(); g.arc(x, y, r * 0.1, 0, Math.PI * 2); g.fill();
    return;
  }
  const sq = 0.78;
  for (let ring = 0; ring < 2; ring++) {
    const n = ring ? 16 : 20;
    g.fillStyle = rgba(ring ? P.DANDE : P.DANDE_DARK, 1);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + ring * 0.2;
      const rr = r * (ring ? 0.66 : 0.98);
      g.beginPath();
      g.ellipse(x + Math.cos(a) * rr * 0.55, y + Math.sin(a) * rr * 0.55 * sq, rr * 0.46, rr * 0.11, a, 0, Math.PI * 2);
      g.fill();
    }
  }
  g.fillStyle = rgba([255, 232, 90], 1);
  g.beginPath(); g.ellipse(x, y, r * 0.2, r * 0.16, 0, 0, Math.PI * 2); g.fill();
}

// Zvonek: stonek se sklání, na něm visí tři čtyři zvonky.
function bellflower(g, x, y, h, r, rand, lean) {
  const tx = x + lean * h, ty = y - h;
  stem(g, x, y, tx, ty, Math.max(1, r * 0.16), rgba(mix(P.STEM, [30, 90, 40], 0.3), 1));
  const n = r < 2.6 ? 2 : 4;
  for (let i = 0; i < n; i++) {
    const f = 1 - i * 0.2;
    const bx = x + (tx - x) * f + (i % 2 ? 1 : -1) * r * 0.55;
    const by = y - h * f * 0.97 + r * (0.5 + i * 0.15);
    if (r < 2.6) {
      g.fillStyle = rgba(P.BELL, 1);
      g.beginPath(); g.ellipse(bx, by, Math.max(0.9, r * 0.5), Math.max(1.2, r * 0.75), 0, 0, Math.PI * 2); g.fill();
      continue;
    }
    g.fillStyle = rgba(P.BELL_DARK, 1);
    g.beginPath();
    g.moveTo(bx - r * 0.18, by - r * 0.7);
    g.quadraticCurveTo(bx - r * 0.78, by + r * 0.1, bx - r * 0.84, by + r * 0.82);
    g.lineTo(bx + r * 0.84, by + r * 0.82);
    g.quadraticCurveTo(bx + r * 0.78, by + r * 0.1, bx + r * 0.18, by - r * 0.7);
    g.closePath(); g.fill();
    g.fillStyle = rgba(P.BELL, 1);
    g.beginPath();
    g.moveTo(bx - r * 0.12, by - r * 0.68);
    g.quadraticCurveTo(bx - r * 0.60, by + r * 0.1, bx - r * 0.66, by + r * 0.72);
    g.lineTo(bx + r * 0.50, by + r * 0.72);
    g.quadraticCurveTo(bx + r * 0.42, by + r * 0.1, bx + r * 0.12, by - r * 0.68);
    g.closePath(); g.fill();
    g.fillStyle = rgba(mix(P.BELL, [255, 255, 255], 0.4), 0.9);
    g.beginPath(); g.ellipse(bx - r * 0.2, by + r * 0.1, r * 0.1, r * 0.32, 0.2, 0, Math.PI * 2); g.fill();
    g.fillStyle = rgba(P.BELL_DARK, 1);
    g.beginPath(); g.ellipse(bx, by + r * 0.82, r * 0.84, r * 0.2, 0, 0, Math.PI * 2); g.fill();
  }
}

const KINDS = ['daisy', 'poppy', 'clover', 'dandelion', 'bell'];

// Bod na kvadratické křivce (A, řídicí B, konec E).
function quad(t, ax, ay, bx, by, ex, ey) {
  const k = 1 - t;
  return [k * k * ax + 2 * k * t * bx + t * t * ex, k * k * ay + 2 * k * t * by + t * t * ey];
}

// List stébla: čepel od A k E prověšená dolů, se střední žilkou a světlým
// horním okrajem. Vrací bod na horní straně v poměru `at` — tam si sedne kobylka.
function blade(g, ax, ay, sg, len, wid, col, at) {
  const bx = ax + sg * len * 0.55, by = ay - len * 0.26;
  const ex = ax + sg * len, ey = ay + len * 0.10;
  g.beginPath();
  g.moveTo(ax, ay);
  g.quadraticCurveTo(bx, by - wid, ex, ey);
  g.quadraticCurveTo(bx, by + wid, ax, ay);
  const gr = g.createLinearGradient(0, by - wid, 0, by + wid);
  gr.addColorStop(0, rgba(mix(col, P.GRASS_LIGHT, 0.45), 1));
  gr.addColorStop(1, rgba(mix(col, P.GRASS_DARK, 0.35), 1));
  g.fillStyle = gr;
  g.fill();
  g.strokeStyle = rgba(mix(col, P.GRASS_LIGHT, 0.7), 0.55);
  g.lineWidth = Math.max(1, wid * 0.14);
  g.beginPath();
  g.moveTo(ax, ay);
  g.quadraticCurveTo(bx, by, ex, ey);
  g.stroke();
  const [px, py] = quad(at, ax, ay, bx, by - wid * 0.9, ex, ey);
  return [px, py - wid * 0.25];
}

// Stéblo s listy: (x,y) = pata, h = výška. Do `reg` zapíše místo na největším
// listu, kam může kobylka vyskočit.
function stalk(g, x, y, h, lean, rand, reg) {
  const cx = x + lean * h * 0.2, cy = y - h * 0.55, hx = x + lean * h, hy = y - h;
  const col = mix(P.STEM, P.GRASS_MID, 0.3 + rand() * 0.3);
  g.strokeStyle = rgba(mix(col, P.GRASS_DARK, 0.3), 1);
  g.lineWidth = Math.max(1.5, h * 0.024);
  g.lineCap = 'round';
  g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(cx, cy, hx, hy); g.stroke();
  const side = rand() < 0.5 ? -1 : 1;
  const leaves = [[0.30, -side, 0.5, 0.04], [0.50, side, 0.7, 0.055], [0.72, -side, 0.36, 0.035]];
  let main = null;
  for (const [t, sg, k, wk] of leaves) {
    const [ax, ay] = quad(t, x, y, cx, cy, hx, hy);
    const len = h * k * (0.85 + rand() * 0.3);
    const at = blade(g, ax, ay, sg, len, len * wk * 2.2, col, 0.58);
    if (k >= 0.69) main = { at, ay };
  }
  // klas na špičce
  g.fillStyle = rgba(mix(P.GRASS_LIGHT, P.RAPE, 0.35), 1);
  for (let i = 0; i < 6; i++) {
    const [px, py] = quad(1 - i * 0.025, x, y, cx, cy, hx, hy);
    g.beginPath();
    g.ellipse(px + (i % 2 ? 1 : -1) * h * 0.012, py, h * 0.014, h * 0.032, (i % 2 ? 1 : -1) * 0.4, 0, Math.PI * 2);
    g.fill();
  }
  if (reg && main) reg({ kind: 'leaf', x: main.at[0], y: y, lift: y - main.at[1] - h * 0.05 });
}

const SOIL_TOP = 0.785;

// Pruh hlíny u spodního okraje: nerovný horní okraj, vlhké a suché fleky, zrnka a
// praskliny. Zrnka rostou směrem k divákovi.
function soil(g, W, H, rand, edge) {
  const topY = x => H * SOIL_TOP + edge(x) * H * 0.010;
  g.save();
  g.beginPath();
  g.moveTo(0, H * 1.01);
  for (let x = 0; x <= W; x += 4) g.lineTo(x, topY(x));
  g.lineTo(W, H * 1.01);
  g.closePath();
  const gr = g.createLinearGradient(0, H * SOIL_TOP, 0, H);
  gr.addColorStop(0, 'rgb(124,90,60)');
  gr.addColorStop(0.5, 'rgb(100,72,48)');
  gr.addColorStop(1, 'rgb(72,50,34)');
  g.fillStyle = gr;
  g.fill();
  g.clip();
  for (let i = 0; i < 70; i++) {
    const yy = H * lerp(SOIL_TOP, 1.0, rand());
    const rw = W * (0.02 + 0.08 * depthScale(yy / H)) * (0.5 + rand());
    g.fillStyle = rand() < 0.55 ? 'rgba(52,36,24,0.22)' : 'rgba(176,138,96,0.16)';
    g.beginPath(); g.ellipse(rand() * W, yy, rw, rw * 0.16, 0, 0, Math.PI * 2); g.fill();
  }
  const tones = [[58, 40, 28], [128, 94, 62], [176, 140, 100], [96, 68, 44]];
  const n = Math.round(W * H / 190);
  for (let i = 0; i < n; i++) {
    const yf = lerp(SOIL_TOP, 1.0, Math.pow(rand(), 0.8));
    const s = H * (0.0012 + 0.0042 * depthScale(yf)) * (0.5 + rand());
    g.fillStyle = rgba(tones[Math.floor(rand() * tones.length)], 0.45 + rand() * 0.4);
    g.beginPath(); g.ellipse(rand() * W, H * yf, s * (1 + rand()), s * 0.6, rand() * 3, 0, Math.PI * 2); g.fill();
  }
  g.strokeStyle = 'rgba(40,26,16,0.38)';
  for (let i = 0; i < 16; i++) {
    let x = rand() * W, y = H * lerp(SOIL_TOP + 0.03, 0.98, rand());
    g.lineWidth = Math.max(1, H * 0.0016 * depthScale(y / H) * 1.6);
    g.beginPath(); g.moveTo(x, y);
    for (let k = 0; k < 6; k++) { x += (rand() - 0.3) * H * 0.04; y += (rand() - 0.5) * H * 0.012; g.lineTo(x, y); }
    g.stroke();
  }
  g.restore();
}

// Kamínek na hlíně: stín, hrbolatý tvar, světlo shora.
function pebble(g, x, y, w, rand) {
  const h = w * (0.45 + rand() * 0.25);
  const base = [[150, 146, 136], [178, 166, 142], [122, 114, 106], [164, 134, 102], [138, 140, 130]][Math.floor(rand() * 5)];
  g.fillStyle = 'rgba(40,24,12,0.38)';
  g.beginPath(); g.ellipse(x + w * 0.12, y + h * 0.1, w * 1.05, h * 0.34, 0, 0, Math.PI * 2); g.fill();
  g.beginPath();
  for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.5) {
    const rr = 1 + (rand() - 0.5) * 0.18;
    g.lineTo(x + Math.cos(a) * w * rr, y - h * 0.5 + Math.sin(a) * h * 0.5 * rr);
  }
  g.closePath();
  const gr = g.createLinearGradient(x - w, y - h, x + w, y + h * 0.4);
  gr.addColorStop(0, rgba(mix(base, [255, 250, 235], 0.25), 1));
  gr.addColorStop(1, rgba(mix(base, [50, 36, 28], 0.35), 1));
  g.fillStyle = gr;
  g.fill();
  g.fillStyle = 'rgba(255,252,240,0.30)';
  g.beginPath(); g.ellipse(x - w * 0.25, y - h * 0.72, w * 0.38, h * 0.16, -0.3, 0, Math.PI * 2); g.fill();
  if (rand() < 0.4) {
    g.strokeStyle = 'rgba(60,50,44,0.35)';
    g.lineWidth = Math.max(1, w * 0.04);
    g.beginPath(); g.moveTo(x - w * 0.3, y - h * 0.6); g.lineTo(x + w * 0.1, y - h * 0.3); g.stroke();
  }
}

// Květ s dříkem: (x,y) = pata stonku, h = výška stonku, r = poloměr hlavy.
// `reg` (volitelný) dostane hlavu velkého květu jako místo k přistání.
function plant(g, kind, x, y, h, r, rand, lean, reg) {
  const sw = Math.max(1, r * 0.17);
  const col = rgba(mix(P.STEM, P.GRASS_DARK, rand() * 0.4), 1);
  if (kind === 'stalk') {
    stalk(g, x, y, h, lean, rand, reg);
    return;
  }
  if (kind === 'bell') {
    bellflower(g, x, y, h, r, rand, lean);
    return;
  }
  const hx = x + lean * h, hy = y - h;
  if (reg) reg({ kind: 'flower', x: hx, y: hy - r * 0.3 });
  if (r >= 2.4) {
    leafPair(g, x, y, Math.max(3, h * 0.38), rgba(mix(P.STEM, P.GRASS_DARK, 0.3), 1));
    if (kind === 'clover') leafPair(g, x + r * 0.5, y, h * 0.3, rgba(P.GRASS_MID, 1));
  }
  stem(g, x, y, hx, hy, sw, col);
  if (kind === 'daisy') daisy(g, hx, hy, r, rand);
  else if (kind === 'poppy') poppy(g, hx, hy, r, rand);
  else if (kind === 'clover') clover(g, hx, hy, r, rand, rand() < 0.35);
  else dandelion(g, hx, hy, r, rand, rand() < 0.22);
}

function rock(g, x, y, w, rand, wob) {
  const h = w * (0.50 + rand() * 0.25);
  g.fillStyle = 'rgba(30,70,24,0.32)';
  g.beginPath(); g.ellipse(x, y + h * 0.05, w * 1.05, h * 0.2, 0, 0, Math.PI * 2); g.fill();
  g.beginPath();
  for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.25) {
    const rr = 1 + 0.14 * wob(a * 3);
    const py = Math.sin(a);
    g.lineTo(x + Math.cos(a) * w * rr, y - h * 0.5 + py * h * 0.5 * rr * (py < 0 ? 1 : 0.7));
  }
  g.closePath();
  g.fillStyle = rgba(mix(P.ROCK, [76, 78, 72], rand() * 0.4), 1);
  g.fill();
  g.beginPath();
  g.ellipse(x - w * 0.15, y - h * 0.72, w * 0.52, h * 0.24, -0.25, 0, Math.PI * 2);
  g.fillStyle = rgba(P.ROCK_LIT, 0.55);
  g.fill();
  g.beginPath();
  g.ellipse(x + w * 0.05, y - h * 0.92, w * 0.55, h * 0.18, 0, Math.PI, Math.PI * 2);
  g.fillStyle = rgba(P.MOSS, 0.9);
  g.fill();
}

// ---------------------------------------------------------------- factory

export function create() {
  function buildSky(W, H) {
    const c = makeCanvas(W, H * 0.62), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H * HORIZON);
    grad.addColorStop(0.00, rgba(P.SKY_TOP, 1));
    grad.addColorStop(0.45, rgba(P.SKY_MID, 1));
    grad.addColorStop(0.85, rgba(P.SKY_LOW, 1));
    grad.addColorStop(1.00, rgba(P.SKY_HAZE, 1));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H * HORIZON + 2);
    const sx = W * 0.80, sy = H * 0.13, sr = H * 0.26;
    const glow = g.createRadialGradient(sx, sy, 0, sx, sy, sr);
    glow.addColorStop(0.00, 'rgba(255,252,236,0.95)');
    glow.addColorStop(0.12, 'rgba(255,248,214,0.55)');
    glow.addColorStop(0.50, 'rgba(255,244,210,0.14)');
    glow.addColorStop(1.00, 'rgba(255,244,210,0)');
    g.fillStyle = glow;
    g.beginPath(); g.arc(sx, sy, sr, 0, Math.PI * 2); g.fill();
    g.fillStyle = 'rgba(255,254,246,0.96)';
    g.beginPath(); g.arc(sx, sy, H * 0.026, 0, Math.PI * 2); g.fill();
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
      const puffs = o.flat ? 7 : 9;
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
          const gr = g.createRadialGradient(0, -pr * 0.2, pr * 0.1, 0, 0, pr);
          gr.addColorStop(0, 'rgba(255,255,255,' + o.alpha + ')');
          gr.addColorStop(0.55, 'rgba(250,252,255,' + o.alpha * 0.55 + ')');
          gr.addColorStop(1, 'rgba(250,252,255,0)');
          g.save();
          g.translate(px, py);
          if (o.flat) g.scale(2.6, 0.55);
          g.fillStyle = gr;
          g.beginPath(); g.arc(0, 0, pr, 0, Math.PI * 2); g.fill();
          g.restore();
        }
        // šedomodré spodky, ať mráček má objem
        if (!o.flat) {
          for (let j = 1; j < puffs - 1; j += 2) {
            const px = cx + rp + seeds[j][0], py = cy + seeds[j][1] + seeds[j][2] * 0.5, pr = seeds[j][2] * 0.7;
            const gr = g.createRadialGradient(px, py, pr * 0.1, px, py, pr);
            gr.addColorStop(0, 'rgba(150,176,206,' + o.alpha * 0.22 + ')');
            gr.addColorStop(1, 'rgba(150,176,206,0)');
            g.fillStyle = gr;
            g.beginPath(); g.arc(px, py, pr, 0, Math.PI * 2); g.fill();
          }
        }
      }
    }
    return { canvas: c, y0: y0 };
  }

  // Tři vrstvy kopců: čím dál, tím víc v oparu. Na středním kopci pár
  // žlutých lánů řepky, na bližším pruhy polí.
  function buildLand(W, H, rand) {
    const y0 = Math.round(H * 0.16);
    const c = makeCanvas(W, H * (0.62 - 0.16)), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;

    const ridges = [
      { w: waveFn(rand, 4, 2.4 / W, 0.55), h: H * 0.115, base: H * (HORIZON + 0.010), col: P.RIDGE[0], haze: 0.46 },
      { w: waveFn(rand, 5, 4.1 / W, 0.52), h: H * 0.085, base: H * (HORIZON + 0.022), col: P.RIDGE[1], haze: 0.26 },
      { w: waveFn(rand, 5, 6.6 / W, 0.50), h: H * 0.052, base: H * (HORIZON + 0.034), col: P.RIDGE[2], haze: 0.10 },
    ];
    ridges.forEach((R, ri) => {
      const top = (xx) => R.base - R.h * (0.25 + 0.75 * Math.pow(1 - Math.abs(R.w(xx)), 2));
      g.beginPath();
      g.moveTo(0, R.base);
      for (x = 0; x <= W; x += 3) g.lineTo(x, top(x));
      g.lineTo(W, R.base);
      g.closePath();
      const body = mix(R.col, P.SKY_HAZE, R.haze);
      const gr = g.createLinearGradient(0, R.base - R.h, 0, R.base);
      gr.addColorStop(0, rgba(mix(body, [255, 255, 240], 0.18), 1));
      gr.addColorStop(1, rgba(mix(body, P.SKY_HAZE, 0.22), 1));
      g.fillStyle = gr;
      g.fill();
      if (ri > 0) {
        g.save();
        g.clip();
        const patches = ri === 1 ? 7 : 11;
        for (let k = 0; k < patches; k++) {
          const px = rand() * W, pw = W * (0.03 + rand() * 0.05);
          const py = R.base - R.h * (0.10 + rand() * 0.34);
          const ph = R.h * (0.10 + rand() * 0.10);
          const yellow = rand() < (ri === 1 ? 0.5 : 0.3);
          const col = yellow ? mix(P.RAPE, P.SKY_HAZE, R.haze + 0.12) : mix(P.GRASS_LIGHT, body, 0.45);
          g.fillStyle = rgba(col, yellow ? 0.8 : 0.55);
          g.beginPath();
          g.moveTo(px, py);
          g.lineTo(px + pw, py - ph * 0.15);
          g.lineTo(px + pw * 1.12, py + ph);
          g.lineTo(px - pw * 0.1, py + ph * 1.1);
          g.closePath();
          g.fill();
        }
        g.restore();
      }
    });

    const hz = g.createLinearGradient(0, H * (HORIZON - 0.03), 0, H * (HORIZON + 0.07));
    hz.addColorStop(0, 'rgba(244,248,236,0)');
    hz.addColorStop(0.5, 'rgba(244,248,236,0.5)');
    hz.addColorStop(1, 'rgba(244,248,236,0)');
    g.fillStyle = hz;
    g.fillRect(0, H * (HORIZON - 0.03), W, H * 0.10);
    return { canvas: c, y0: y0 };
  }

  // Souvislá tráva s květy od obzoru k spodnímu okraji. Řádky se kreslí
  // odzadu dopředu a květy, které do řádku padnou, se vkládají mezi ně —
  // pata stonku je tak vždy zakrytá trávou o řádek blíž.
  function buildGround(W, H, rand) {
    const y0 = Math.round(H * GROUND_TOP);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const aspect = W / H;

    const topWave = waveFn(rand, 4, 5.0 / W, 0.55);
    g.beginPath();
    g.moveTo(0, H);
    for (let x = 0; x <= W; x += 4) g.lineTo(x, H * (GROUND_TOP + 0.004) - topWave(x) * H * 0.014);
    g.lineTo(W, H);
    g.closePath();
    g.clip();

    const base = g.createLinearGradient(0, H * GROUND_TOP, 0, H);
    base.addColorStop(0.00, rgba(P.GRASS_FAR, 0));
    base.addColorStop(0.03, rgba(mix(P.GRASS_FAR, P.RIDGE[2], 0.4), 1));
    base.addColorStop(0.18, rgba(P.GRASS_FAR, 1));
    base.addColorStop(0.55, rgba(P.GRASS_MID, 1));
    base.addColorStop(1.00, rgba(P.GRASS_NEAR, 1));
    g.fillStyle = base;
    g.fillRect(0, H * GROUND_TOP, W, H - H * GROUND_TOP);

    const patch = waveFn(rand, 4, 6.0 / W, 0.55);
    for (let i = 0; i < 180; i++) {
      const yy = H * lerp(0.47, 1.0, Math.pow(rand(), 0.85));
      const xx = rand() * W;
      const d = depthScale(yy / H);
      const rw = W * (0.02 + 0.10 * d) * (0.5 + rand());
      const rh = rw * 0.17;
      g.fillStyle = patch(xx + yy * 0.3) > 0 ? rgba(P.GRASS_LIGHT, 0.14) : rgba(P.GRASS_DARK, 0.12);
      g.beginPath(); g.ellipse(xx, yy, rw, rh, 0, 0, Math.PI * 2); g.fill();
    }

    // květy: druh určují „záplaty" (každý druh má svůj šum), takže vznikají
    // makové a kopretinové mezičky, jetel a pampelišky jsou rozptýlené
    const fieldFn = KINDS.map(() => waveFn(rand, 3, 9.0 / W, 0.55));
    const flowers = [];
    const FL = Math.round(800 * aspect / 1.78);
    for (let i = 0; i < FL; i++) {
      const yf = lerp(0.465, SOIL_TOP - 0.01, Math.pow(rand(), 0.62));
      const d = depthScale(yf);
      const px = rand() * W;
      let best = 0, bv = -9;
      for (let k = 0; k < KINDS.length; k++) {
        const v = fieldFn[k](px * 1.3 + yf * 700) + rand() * 0.85;
        if (v > bv) { bv = v; best = k; }
      }
      const r = H * (0.0016 + 0.0110 * Math.pow(d, 1.25)) * (0.7 + rand() * 0.6);
      flowers.push({ kind: KINDS[best], x: px, y: H * yf, r,
                     h: r * (3.2 + rand() * 3.4), lean: (rand() - 0.5) * 0.35 });
    }

    // Místa k přistání (podíly plátna): hlavy velkých květů pro čmeláka, listy
    // stébel pro kobylku. Registrují se při kreslení (`plant` → `reg`).
    const spots = [];
    const reg = (sp) => spots.push({ kind: sp.kind, x: sp.x / W, y: sp.y / H, lift: sp.lift ? sp.lift / H : 0 });

    // velké květy na vysokých stoncích — místa, kde si čmelák sedne
    const HERO = ['daisy', 'daisy', 'poppy', 'dandelion', 'clover'];
    const nHero = Math.round(30 * aspect / 1.78);
    for (let i = 0; i < nHero; i++) {
      const yf = lerp(0.56, 0.77, Math.pow(rand(), 0.8));
      const d = depthScale(yf);
      const r = H * (0.016 + 0.030 * d) * (0.8 + rand() * 0.5);
      flowers.push({ kind: HERO[Math.floor(rand() * HERO.length)], x: W * (0.04 + 0.92 * (i + rand()) / nHero),
                     y: H * yf, r, h: Math.min(r * (3 + rand() * 3.5), H * (yf - 0.49)), lean: (rand() - 0.5) * 0.3, land: true });
    }
    // stébla s listy: u hlíny (kobylka se na ně dostane z dráhy) a pár dál v louce
    const nEdge = Math.round(8 * aspect / 1.78);
    for (let i = 0; i < nEdge + 6; i++) {
      const edgeStalk = i < nEdge;
      const yf = edgeStalk ? lerp(0.715, 0.775, rand()) : lerp(0.60, 0.70, rand());
      const d = depthScale(yf);
      flowers.push({ kind: 'stalk', x: W * (edgeStalk ? 0.06 + 0.88 * (i + rand()) / nEdge : rand()), y: H * yf,
                     r: 0, h: H * 0.27 * Math.pow(d, 0.9) * (0.8 + rand() * 0.4),
                     lean: (rand() - 0.5) * 0.25, land: edgeStalk });
    }
    flowers.sort((a, b) => a.y - b.y);

    const edge = waveFn(rand, 4, 7.0 / W, 0.55);
    const pebbles = [];
    const nPeb = Math.round(150 * aspect / 1.78);
    for (let i = 0; i < nPeb; i++) {
      const yf = lerp(SOIL_TOP + 0.012, 0.99, Math.pow(rand(), 0.9));
      const d = depthScale(yf);
      pebbles.push({ x: rand() * W, y: H * yf, w: H * (0.005 + 0.05 * Math.pow(d, 1.3) * Math.pow(rand(), 1.8)) });
    }
    pebbles.sort((a, b) => a.y - b.y);
    let soilDone = false;

    const wob = waveFn(rand, 3, 1.2, 0.5);
    const rocks = [];
    for (let i = 0; i < Math.round(aspect * 3); i++) {
      const yf = 0.60 + rand() * 0.18;
      rocks.push({ x: rand() * W, y: H * yf, w: H * (0.03 + 0.10 * depthScale(yf)) });
    }
    rocks.sort((a, b) => a.y - b.y);

    const bucketCols = [
      rgba(P.GRASS_DARK, 0.95), rgba(mix(P.GRASS_DARK, P.GRASS_MID, 0.55), 0.95),
      rgba(P.GRASS_MID, 0.95), rgba(mix(P.GRASS_MID, P.GRASS_LIGHT, 0.5), 0.95),
      rgba(P.GRASS_LIGHT, 0.9),
    ];
    let fi = 0, ri = 0;
    let yy = H * 0.455;
    while (yy < H * 1.01) {
      const yf = yy / H;
      const d = depthScale(yf);
      const s = H * (0.0075 + 0.058 * Math.pow(d, 1.5));
      // od horního okraje hlíny dál už trávu jen zřídka: dole je hlína a kamínky
      const onSoil = yf > SOIL_TOP + 0.004;
      if (!soilDone && yf > SOIL_TOP - 0.004) {
        soilDone = true;
        soil(g, W, H, rand, edge);
        for (const p of pebbles) pebble(g, p.x, p.y, p.w, rand);
      }
      const step = s * 0.42 * (onSoil ? 14 : 1);
      const buckets = makeBuckets(bucketCols);
      for (let xx = -s; xx < W + s; xx += step * (0.6 + rand() * 0.8)) {
        addTuft(buckets, rand, xx, yy + (rand() - 0.5) * s * 0.2, s * (0.7 + rand() * 0.6) * (onSoil ? 0.5 : 1), 3 + Math.floor(rand() * 2));
      }
      flushBuckets(g, buckets, Math.max(1, s * 0.085));
      while (fi < flowers.length && flowers[fi].y <= yy + s * 0.2) {
        const f = flowers[fi++];
        plant(g, f.kind, f.x, f.y, f.h, f.r, rand, f.lean, f.land ? reg : undefined);
      }
      while (ri < rocks.length && rocks[ri].y <= yy) {
        const r = rocks[ri++];
        rock(g, r.x, r.y, r.w, rand, wob);
      }
      yy += s * 0.30;
    }
    while (fi < flowers.length) {
      const f = flowers[fi++];
      plant(g, f.kind, f.x, f.y, f.h, f.r, rand, f.lean, f.land ? reg : undefined);
    }
    const mist = g.createLinearGradient(0, H * 0.43, 0, H * 0.53);
    mist.addColorStop(0, 'rgba(240,248,232,0.55)');
    mist.addColorStop(1, 'rgba(240,248,232,0)');
    g.fillStyle = mist;
    g.fillRect(0, H * 0.43, W, H * 0.10);
    return { canvas: c, y0: y0, spots };
  }

  // Zeleň NAD tvory: vysoká stébla a velké květy u spodního okraje, hustší
  // v rozích; uprostřed zůstává výhled na přední dráhy volný.
  function buildFront(W, H, rand) {
    const y0 = Math.round(H * 0.74);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    g.translate(0, -y0);
    const aspect = W / H;
    const edge = () => (rand() < 0.5 ? rand() * 0.22 : 1 - rand() * 0.22);

    const bucketCols = [
      rgba(P.GRASS_DARK, 1), rgba(mix(P.GRASS_DARK, P.GRASS_MID, 0.5), 1),
      rgba(P.GRASS_MID, 1), rgba(P.GRASS_LIGHT, 0.95),
    ];
    const bk = makeBuckets(bucketCols);
    const nT = Math.round(aspect * 46);
    for (let i = 0; i < nT; i++) {
      const x = W * (i % 3 === 0 ? rand() : edge());
      const central = x > W * 0.22 && x < W * 0.78;
      addTuft(bk, rand, x, H * (0.992 + rand() * 0.02), H * (central ? 0.026 + rand() * 0.014 : 0.05 + rand() * 0.055), 6);
    }
    flushBuckets(g, bk, Math.max(1.5, H * 0.0045));

    const nF = Math.round(aspect * 11);
    const items = [];
    for (let i = 0; i < nF; i++) {
      const x = W * edge();
      const r = H * (0.016 + rand() * 0.016);
      items.push({ kind: KINDS[Math.floor(rand() * rand() * KINDS.length * 1.4) % KINDS.length], x,
                   y: H * (1.0 + rand() * 0.015), r, h: H * (0.10 + rand() * 0.12), lean: (rand() - 0.5) * 0.22 });
    }
    items.sort((a, b) => a.y - b.y);
    for (const f of items) plant(g, f.kind, f.x, f.y, f.h, f.r, rand, f.lean);

    const bk2 = makeBuckets(bucketCols);
    for (let i = 0; i < Math.round(aspect * 18); i++) {
      addTuft(bk2, rand, W * edge(), H * 1.01, H * (0.07 + rand() * 0.05), 5);
    }
    flushBuckets(g, bk2, Math.max(1.5, H * 0.005));
    return { canvas: c, y0: y0 };
  }

  // Vlna větru: vodorovně se posouvají pruhy světla a stínu, jednou předkreslené.
  function buildWind(W, H, rand) {
    const y0 = Math.round(H * 0.47);
    const c = makeCanvas(W, H - y0), g = c.getContext('2d');
    const bands = 9;
    for (let i = 0; i < bands; i++) {
      const cx = (i + rand() * 0.6) / bands * W;
      const bw = W * (0.045 + rand() * 0.04);
      const light = i % 2 === 0;
      const skew = (H - y0) * (0.18 + rand() * 0.08);
      for (const rp of [-W, 0, W]) {
        const x0 = cx + rp;
        const gr = g.createLinearGradient(x0 - bw, 0, x0 + bw, 0);
        const col = light ? '255,250,170' : '20,80,30';
        const al = light ? 0.15 : 0.12;
        gr.addColorStop(0, 'rgba(' + col + ',0)');
        gr.addColorStop(0.5, 'rgba(' + col + ',' + al + ')');
        gr.addColorStop(1, 'rgba(' + col + ',0)');
        g.fillStyle = gr;
        g.beginPath();
        g.moveTo(x0 - bw + skew * 0.2, 0);
        g.lineTo(x0 + bw + skew * 0.2, 0);
        g.lineTo(x0 + bw - skew * 0.8, H - y0);
        g.lineTo(x0 - bw - skew * 0.8, H - y0);
        g.closePath();
        g.fill();
      }
    }
    return { canvas: c, y0: y0 };
  }

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const sky = buildSky(W, H);
    const far = buildClouds(W, H, rand, { count: 8, y0: 0.05, y1: 0.16, size: 0.11, alpha: 0.34, flat: true, band: [0, 0.23] });
    const near = buildClouds(W, H, rand, { count: 6, y0: 0.13, y1: 0.31, size: 0.17, alpha: 0.80, flat: false, band: [0.02, 0.37] });
    const land = buildLand(W, H, rand);
    const ground = buildGround(W, H, rand);
    const front = buildFront(W, H, rand);
    const wind = buildWind(W, H, rand);

    const blades = [];
    for (let i = 0; i < 46; i++) {
      const edge = rand() < 0.5 ? rand() * 0.26 : 1 - rand() * 0.26;
      const x = i % 3 === 0 ? rand() : edge;
      const central = x > 0.26 && x < 0.74;
      blades.push({ x, y: 1.0 + rand() * 0.01, h: central ? 0.03 + rand() * 0.02 : 0.07 + rand() * 0.09,
                    lean: (rand() - 0.5) * 0.8, ph: rand() * Math.PI * 2, sp: 0.5 + rand() * 0.6,
                    tone: Math.floor(rand() * 3) });
    }
    const flies = [];
    for (let i = 0; i < 5; i++) {
      flies.push({ cx: 0.15 + rand() * 0.7, cy: 0.50 + rand() * 0.07, ax: 0.05 + rand() * 0.10, ay: 0.01 + rand() * 0.02,
                   sp: 0.10 + rand() * 0.08, ph: rand() * 6.28,
                   col: [[252, 252, 248], [250, 214, 64], [250, 250, 248], [240, 140, 60], [150, 190, 250]][i] });
    }
    const motes = [];
    for (let i = 0; i < 40; i++) {
      motes.push({ x: rand(), y: 0.45 + rand() * 0.5, sp: 0.004 + rand() * 0.010, dr: rand() * 6.28, r: 0.6 + rand() * 1.6, ph: rand() * 6.28 });
    }

    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.5, H * 0.55, H * 0.45, W * 0.5, H * 0.55, H * 1.0);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, P.vignette);
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);

    return { W, H, sky, vig, cloudFar: far, cloudNear: near, land, ground, front, wind, blades, flies, motes,
             spots: ground.spots, claims: new Map() };
  }

  function drawBlades(ctx, W, H, t, S) {
    ctx.save();
    ctx.lineCap = 'round';
    for (let i = 0; i < S.blades.length; i++) {
      const B = S.blades[i];
      const x = B.x * W, y = B.y * H, h = B.h * H;
      const sway = Math.sin(t * B.sp + B.ph) * 0.12 + B.lean * 0.25;
      ctx.strokeStyle = B.tone === 0 ? rgba(P.GRASS_LIGHT, 0.95) : (B.tone === 1 ? rgba(P.GRASS_MID, 1) : rgba(P.GRASS_DARK, 1));
      ctx.lineWidth = Math.max(1.5, H * 0.0034);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(x + h * sway * 0.6, y - h * 0.6, x + h * (sway + B.lean * 0.4), y - h);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawLife(ctx, W, H, t, S) {
    ctx.save();
    for (const m of S.motes) {
      const y = ((m.y - t * m.sp) % 1 + 1) % 1 * 0.55 + 0.45;
      const x = (m.x + Math.sin(t * 0.2 + m.dr) * 0.02) * W;
      ctx.globalAlpha = 0.35 + 0.35 * Math.sin(t * 1.3 + m.ph);
      ctx.fillStyle = 'rgba(255,252,220,1)';
      ctx.beginPath(); ctx.arc(x, y * H, H * 0.0014 * m.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    for (const f of S.flies) {
      const u = t * f.sp + f.ph;
      const x = (f.cx + Math.sin(u) * f.ax + Math.sin(u * 2.3) * f.ax * 0.3) * W;
      const y = (f.cy + Math.sin(u * 1.4) * f.ay) * H;
      const flap = Math.abs(Math.sin(t * 9 + f.ph));
      const s = H * 0.0075;
      ctx.fillStyle = rgba(f.col, 0.95);
      for (const sg of [-1, 1]) {
        ctx.beginPath();
        ctx.ellipse(x + sg * s * 0.45 * flap, y, s * 0.55 * (0.25 + flap * 0.75), s * 0.8, sg * 0.35, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(40,30,24,0.9)';
      ctx.fillRect(x - s * 0.06, y - s * 0.45, s * 0.12, s * 0.9);
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
    const ow = (t * W * 0.018) % W;
    ctx.drawImage(S.wind.canvas, ow, S.wind.y0);
    ctx.drawImage(S.wind.canvas, ow - W, S.wind.y0);
  }

  function drawFront(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    ctx.drawImage(state.front.canvas, 0, state.front.y0);
    drawBlades(ctx, W, H, t, state);
    drawLife(ctx, W, H, t, state);
    ctx.drawImage(state.vig, 0, 0);
  }

  // Místa k přistání (viz buildGround): `kind` 'flower' pro čmeláka, 'leaf' pro
  // kobylku (`lift` = výška listu nad patou stébla). `claim` místo zabere do času.
  function perches(t) {
    if (!state) return [];
    return state.spots.map((sp, i) => ({ ...sp, free: !((state.claims.get(i) || 0) > t) }));
  }

  function claim(i, until) {
    if (state) state.claims.set(i, until);
  }

  return { draw, drawFront, sun: { x: 0.80, y: 0.13 }, depthScale, perches, claim };
}
