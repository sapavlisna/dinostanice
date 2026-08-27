/* Akvárium — podvodní krajina pro 2D plátno pod 3D rybami.

   Stejný kontrakt jako křídová laguna: ES modul s továrnou `create(variant)`,
   která vrací `{draw, drawFront, sun, depthScale}`. Statická malba se kreslí
   jednou do offscreen pláten (při změně rozměru), každý snímek se přes ni
   táhnou jen levné animované vrstvy — hladina, světelné kužely, kaustika na
   písku, bublinky a prach ve vodě.

   Vrstvení je stejný trik jako u stromů poloostrova v křídové laguně: co má
   patu POD drahami ryb (přední chaluhy, korálový trs v rozích), se kreslí do
   předního plátna, které `drawFront` vrství NAD ryby. Zadní chaluhy a korály
   u vzdálené hrany písku zůstávají v zadním plátně, takže ryba plave před
   nimi. Bez toho by ryba plavala „přes obrázek", ne v akváriu. */

const SEED = 20260827;

// Hranice vrstev jako podíl výšky plátna.
const SURFACE = 0.075;        // hladina (vodní čára zdola)
const FLOOR_BACK = 0.665;     // kde začíná písečné dno — nejdál od diváka
const FRONT_TOP = 0.32;       // horní hrana předního plátna (vrcholy chaluh)
const LIGHT_X = 0.42;         // odkud shora prosvítá světlo do vody

const DEPTH_MIN = 0.42;

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

// Součet sinů: hladký, seedovaný, libovolně vzorkovatelný šum.
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

// ---------------------------------------------------------------- paleta

const P = {
  // svisly gradient vody: [podil vysky, barva]
  WATER: [
    [0.000, [188, 238, 246]],
    [SURFACE, [116, 206, 220]],
    [0.240, [48, 146, 186]],
    [0.480, [22, 100, 152]],
    [0.660, [12, 66, 116]],
    [1.000, [7, 40, 80]],
  ],
  SAND_FAR: [126, 146, 152],
  SAND_NEAR: [216, 196, 156],
  SAND_RIDGE: [244, 232, 200],
  SAND_SHADE: [92, 78, 56],
  ROCK: [72, 82, 92],
  ROCK_LIT: [124, 138, 146],
  KELP_DARK: [14, 54, 54],
  KELP_MID: [34, 100, 78],
  KELP_LIT: [72, 140, 96],
  CORAL: [[198, 98, 112], [214, 136, 74], [146, 100, 176], [206, 176, 92]],
  ANEMONE: [222, 148, 168],
  RAY: '224,248,255',
  SPARK: 'rgba(236,252,255,1)',
  VIGNETTE: 'rgba(2,16,34,0.42)',
};

function waterAt(yFrac) {
  const st = P.WATER;
  const y = clamp(yFrac, 0, 1);
  for (let i = 1; i < st.length; i++) {
    if (y <= st[i][0]) {
      const k = (y - st[i - 1][0]) / (st[i][0] - st[i - 1][0] || 1);
      return mix(st[i - 1][1], st[i][1], k);
    }
  }
  return st[st.length - 1][1];
}

/* Jak daleko je bod na dně: 1 u vzdálené hrany písku, 0 u divákova okraje.
   Vzdálené věci se rozpouštějí ve vodě (murk), jinak by dno bylo plakát. */
function farness(yFrac) {
  return clamp(1 - (yFrac - FLOOR_BACK) / (1.02 - FLOOR_BACK), 0, 1);
}

function murk(col, yFrac, k) {
  return mix(col, waterAt(yFrac), k * farness(yFrac));
}

function depthScale(yFrac) {
  const y = clamp(yFrac, 0, 1);
  if (y <= SURFACE) return DEPTH_MIN;
  const u = (y - SURFACE) / (1 - SURFACE);
  return DEPTH_MIN + (1 - DEPTH_MIN) * Math.pow(u, 1.35);
}

// ---------------------------------------------------------------- rostliny

/* Chaluha: pás listů na pružném stvolu. `sway` je fázový posun, aby celý
   trs nekmital jako jeden kus — kreslí se staticky do plátna, takže je to
   jen tvarová rozmanitost, ne animace. */
function drawKelp(g, x, baseY, h, w, sway, col, edge, rand) {
  const n = 26;
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const f = i / n;
    pts.push([x + Math.sin(f * 2.1 + sway) * w * (0.35 + f * 1.15),
              baseY - h * f]);
  }
  g.strokeStyle = col;
  g.lineCap = 'round';
  g.lineWidth = Math.max(1.4, h * 0.026);
  g.beginPath();
  g.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i <= n; i++) g.lineTo(pts[i][0], pts[i][1]);
  g.stroke();

  for (let i = 2; i < n; i += 2) {
    const f = i / n;
    const side = i % 4 === 0 ? 1 : -1;
    const ll = w * 2.1 * (0.40 + Math.sin(Math.PI * f) * 0.95);
    const px = pts[i][0], py = pts[i][1];
    g.fillStyle = i % 4 === 0 ? col : edge;
    g.beginPath();
    g.moveTo(px, py);
    g.quadraticCurveTo(px + side * ll * 0.8, py - ll * 0.55,
                       px + side * ll * (1.0 + rand() * 0.4), py - ll * 1.25);
    g.quadraticCurveTo(px + side * ll * 0.45, py - ll * 0.45, px, py + ll * 0.10);
    g.closePath();
    g.fill();
  }
}

/* Trs mořské trávy — svazek úzkých listů, drží dno pohromadě. */
function drawSeagrass(g, x, baseY, h, col, rand) {
  const n = 7 + Math.floor(rand() * 5);
  g.lineCap = 'round';
  for (let i = 0; i < n; i++) {
    const lean = (i / (n - 1) - 0.5) * 1.7;
    const hh = h * (0.55 + rand() * 0.6);
    g.strokeStyle = col;
    g.lineWidth = Math.max(1, h * 0.045);
    g.beginPath();
    g.moveTo(x, baseY);
    g.quadraticCurveTo(x + lean * hh * 0.25, baseY - hh * 0.6,
                       x + lean * hh * 0.75, baseY - hh);
    g.stroke();
  }
}

/* Větvený korál: trubice, které se dvakrát rozdvojí. */
function drawBranchCoral(g, x, baseY, h, col, rand) {
  g.strokeStyle = col;
  g.lineCap = 'round';
  const grow = (px, py, ang, len, wide, depth) => {
    const ex = px + Math.cos(ang) * len, ey = py + Math.sin(ang) * len;
    g.lineWidth = Math.max(1.2, wide);
    g.beginPath();
    g.moveTo(px, py);
    g.quadraticCurveTo(px + Math.cos(ang) * len * 0.5 + (rand() - 0.5) * len * 0.2,
                       py + Math.sin(ang) * len * 0.5, ex, ey);
    g.stroke();
    if (depth <= 0) return;
    for (let s = -1; s <= 1; s += 2) {
      grow(ex, ey, ang + s * (0.35 + rand() * 0.35), len * (0.55 + rand() * 0.2),
           wide * 0.62, depth - 1);
    }
  };
  const arms = 3;
  for (let i = 0; i < arms; i++) {
    const a = -Math.PI / 2 + (i / (arms - 1) - 0.5) * 0.9;
    grow(x + (i - 1) * h * 0.06, baseY, a, h * 0.42, h * 0.10, 2);
  }
}

/* Mozkový korál: baňka s vrásami. */
function drawBrainCoral(g, x, baseY, r, col, rand) {
  g.fillStyle = col;
  g.beginPath();
  g.ellipse(x, baseY - r * 0.55, r, r * 0.72, 0, Math.PI, Math.PI * 2);
  g.ellipse(x, baseY - r * 0.55, r, r * 0.42, 0, 0, Math.PI);
  g.fill();
  g.strokeStyle = rgba(mix(col, [255, 255, 255], 0.35), 0.55);
  g.lineWidth = Math.max(1, r * 0.09);
  for (let i = 0; i < 4; i++) {
    const yy = baseY - r * (0.25 + i * 0.30);
    const ww = r * Math.sqrt(Math.max(0.05, 1 - Math.pow(i / 4, 2))) * 0.9;
    g.beginPath();
    for (let k = 0; k <= 8; k++) {
      const xx = x - ww + (2 * ww) * k / 8;
      const wob = Math.sin(k * 1.7 + i) * r * 0.05;
      if (k === 0) g.moveTo(xx, yy + wob); else g.lineTo(xx, yy + wob);
    }
    g.stroke();
  }
}

/* Sasanka: nožka s věncem chapadel. */
function drawAnemone(g, x, baseY, r, col, rand) {
  g.fillStyle = rgba(mix(col, [120, 60, 90], 0.35), 1);
  g.beginPath();
  g.ellipse(x, baseY - r * 0.25, r * 0.55, r * 0.45, 0, 0, Math.PI * 2);
  g.fill();
  g.strokeStyle = col;
  g.lineCap = 'round';
  g.lineWidth = Math.max(1, r * 0.16);
  const n = 12;
  for (let i = 0; i < n; i++) {
    const a = -Math.PI + (i + 0.5) / n * Math.PI;
    const len = r * (0.85 + rand() * 0.5);
    g.beginPath();
    g.moveTo(x, baseY - r * 0.35);
    g.quadraticCurveTo(x + Math.cos(a) * len * 0.5, baseY - r * 0.35 + Math.sin(a) * len * 0.9,
                       x + Math.cos(a) * len, baseY - r * 0.35 + Math.sin(a) * len * 0.55);
    g.stroke();
  }
}

// ---------------------------------------------------------------- továrna

export function create(variant = 'reef') {
  // dnes je jen jedna varianta; parametr drží kontrakt s křídovou krajinou
  void variant;

  /* Vodní sloupec: svislý gradient, vzdálené skalní masivy rozpuštěné v modré
     a řídký les chaluh na obzoru dna. Bez těch tvarů je z akvária jednolitá
     modrá plocha, ve které ryba nemá k čemu být blízko nebo daleko. */
  function buildWater(W, H, rand) {
    const c = makeCanvas(W, H), g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, H);
    for (const [pos, col] of P.WATER) grad.addColorStop(pos, rgba(col, 1));
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);

    // světlý sloup pod hladinou v místě zdroje světla — voda pod ním svítí
    const lg = g.createRadialGradient(W * LIGHT_X, H * SURFACE, 0,
                                      W * LIGHT_X, H * SURFACE, H * 0.95);
    lg.addColorStop(0.00, 'rgba(' + P.RAY + ',0.34)');
    lg.addColorStop(0.35, 'rgba(' + P.RAY + ',0.10)');
    lg.addColorStop(1.00, 'rgba(' + P.RAY + ',0)');
    g.fillStyle = lg;
    g.fillRect(0, H * SURFACE, W, H);

    // dva vzdálené masivy za dnem: obrys ze šumu, silně zamlžený vodou
    const mounds = [
      { x: 0.24, w: 0.42, h: 0.150, base: FLOOR_BACK + 0.010, haze: 0.74 },
      { x: 0.72, w: 0.52, h: 0.105, base: FLOOR_BACK + 0.004, haze: 0.82 },
    ];
    for (const M of mounds) {
      const wob = waveFn(rand, 4, 7.0 / W, 0.55);
      const x0 = W * (M.x - M.w / 2), x1 = W * (M.x + M.w / 2);
      g.beginPath();
      g.moveTo(x0, H * M.base);
      for (let x = x0; x <= x1; x += 4) {
        const f = (x - x0) / (x1 - x0);
        const dome = Math.sin(Math.PI * f);
        g.lineTo(x, H * M.base - H * M.h * Math.pow(dome, 0.75) * (0.72 + 0.28 * wob(x)));
      }
      g.lineTo(x1, H * M.base);
      g.closePath();
      g.fillStyle = rgba(mix(P.ROCK, waterAt(M.base - M.h * 0.4), M.haze), 1);
      g.fill();
    }

    // les chaluh na obzoru dna: tmavší jen o vlásek, dělá hloubku, nekřičí
    const far = Math.round(W / H * 26);
    for (let i = 0; i < far; i++) {
      const fx = rand() * W;
      const by = H * (FLOOR_BACK + 0.004 + rand() * 0.010);
      const fh = H * (0.070 + rand() * 0.105);
      const col = rgba(mix(P.KELP_DARK, waterAt(FLOOR_BACK - 0.06), 0.68), 1);
      drawKelp(g, fx, by, fh, fh * 0.10, rand() * 6.283, col, col, rand);
    }
    /* Tři vysoké chaluhy až do vodního sloupce: bez nich je horní dvě
       třetiny akvária jen modrá plocha a ryba v ní nemá k čemu být „vpředu".
       Kreslí se sem, do plnoplošného plátna — do podlahového by se nevešly. */
    for (let i = 0; i < 3; i++) {
      const tx = W * (0.10 + i * 0.34 + rand() * 0.14);
      const th = H * (0.30 + rand() * 0.16);
      const col = rgba(mix(P.KELP_DARK, waterAt(0.35), 0.62), 1);
      const lit = rgba(mix(P.KELP_MID, waterAt(0.35), 0.64), 1);
      drawKelp(g, tx, H * (FLOOR_BACK + 0.02), th, th * 0.075,
               rand() * 6.283, col, lit, rand);
    }
    return c;
  }

  /* Písečné dno se stíny, kameny, korály a chaluhami. Rostliny s patou
     BLÍZKO divákovi (pod drahami ryb) jdou do předního plátna `fg`, které
     drawFront vrství nad ryby; zadní zůstávají tady. */
  function buildFloor(W, H, rand, fg) {
    // Plátno začíná vysoko nad pískem: zadní chaluhy vyrůstají až do drah
    // ryb a nesmí se orámovat o horní hranu bufferu.
    const y0 = Math.round(H * 0.30);
    const c = makeCanvas(W, H - y0 + 2), g = c.getContext('2d');
    g.translate(0, -y0);
    let x;

    const edge = waveFn(rand, 4, 5.4 / W, 0.55);
    const backY = (xx) => H * FLOOR_BACK + H * 0.012 * edge(xx);

    // samotný písek: vzadu domodra (víc vody mezi), vepředu teplý a světlý
    const sg = g.createLinearGradient(0, H * FLOOR_BACK, 0, H);
    sg.addColorStop(0.00, rgba(mix(P.SAND_FAR, waterAt(FLOOR_BACK), 0.66), 1));
    sg.addColorStop(0.35, rgba(mix(P.SAND_NEAR, P.SAND_FAR, 0.45), 1));
    sg.addColorStop(1.00, rgba(P.SAND_NEAR, 1));
    g.fillStyle = sg;
    g.beginPath();
    g.moveTo(0, H + 2);
    for (x = 0; x <= W; x += 4) g.lineTo(x, backY(x));
    g.lineTo(W, H + 2);
    g.closePath();
    g.fill();

    // tmavý spoj dna se vodním sloupcem, ať hrana nevypadá jako nalepená
    const jg = g.createLinearGradient(0, H * (FLOOR_BACK - 0.012), 0, H * (FLOOR_BACK + 0.05));
    jg.addColorStop(0, 'rgba(6,34,62,0.55)');
    jg.addColorStop(1, 'rgba(6,34,62,0)');
    g.fillStyle = jg;
    g.fillRect(0, H * (FLOOR_BACK - 0.012), W, H * 0.062);

    /* Vlnky v písku: vodorovné brázdy, vpředu dál od sebe a s větší amplitudou.
       Světlý hřeben a pod ním stín — z toho dno čte jako plastické, ne jako
       hnědá plocha. */
    const ripples = 26;
    for (let i = 0; i < ripples; i++) {
      const f = i / (ripples - 1);
      const ry = H * (FLOOR_BACK + 0.010) + (H * (1.03 - FLOOR_BACK)) * Math.pow(f, 1.55);
      const amp = H * (0.002 + 0.010 * f);
      const wl = W * (0.10 + 0.30 * f);
      const rw = waveFn(rand, 2, 3.0 / W, 0.5);
      for (let pass = 0; pass < 2; pass++) {
        g.strokeStyle = pass === 0
          ? rgba(P.SAND_RIDGE, 0.16 + 0.20 * f)
          : rgba(P.SAND_SHADE, 0.10 + 0.16 * f);
        g.lineWidth = Math.max(1, H * (0.0012 + 0.0026 * f));
        g.beginPath();
        for (x = -10; x <= W + 10; x += 6) {
          const yy = ry + pass * H * (0.003 + 0.006 * f)
                   + Math.sin(x / wl * 6.283 + i * 1.7) * amp
                   + rw(x) * amp * 0.8;
          if (x <= -10) g.moveTo(x, yy); else g.lineTo(x, yy);
        }
        g.stroke();
      }
    }

    // zrno písku: vepředu větší a hustší
    for (let i = 0; i < 2400; i++) {
      const t = rand();
      const yy = H * lerp(FLOOR_BACK + 0.012, 1.0, Math.pow(t, 0.75));
      const xx = rand() * W;
      const s = H * 0.0008 * (0.5 + Math.pow(t, 1.6) * 4.2);
      g.fillStyle = rand() < 0.5 ? rgba(P.SAND_SHADE, 0.26) : rgba(P.SAND_RIDGE, 0.34);
      g.beginPath();
      g.ellipse(xx, yy, s * (1 + rand()), s * 0.7, 0, 0, Math.PI * 2);
      g.fill();
    }

    /* Kameny: každý se stínem na písku (světlo jde shora, stín tedy pod ním
       a mírně od zdroje světla) a světlejším temenem. Drží se ke krajům, ať
       zůstane prostor, kde je ryba dobře vidět. */
    const rocks = Math.round(W / H * 7);
    for (let i = 0; i < rocks; i++) {
      const side = i % 2 === 0 ? 0.02 + rand() * 0.30 : 0.68 + rand() * 0.30;
      const bx = W * side;
      const byF = FLOOR_BACK + 0.03 + rand() * 0.30;
      const by = H * byF;
      const bw = H * (0.035 + rand() * 0.075) * (1.25 - 0.25 * farness(byF));
      const bh = bw * (0.45 + rand() * 0.45);
      const wob = waveFn(rand, 3, 1.2, 0.5);
      // stín pod kamenem
      g.fillStyle = 'rgba(18,34,44,0.30)';
      g.beginPath();
      g.ellipse(bx + bw * 0.10, by + bh * 0.22, bw * 1.15, bh * 0.34, 0, 0, Math.PI * 2);
      g.fill();
      g.beginPath();
      for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.22) {
        const rr = 1 + 0.18 * wob(a * 3);
        g.lineTo(bx + Math.cos(a) * bw * rr, by + Math.sin(a) * bh * rr);
      }
      g.closePath();
      g.fillStyle = rgba(murk(mix(P.ROCK, [30, 34, 40], rand() * 0.35), byF, 0.6), 1);
      g.fill();
      g.beginPath();
      g.ellipse(bx - bw * 0.15, by - bh * 0.45, bw * 0.62, bh * 0.32, -0.25, 0, Math.PI * 2);
      g.fillStyle = rgba(murk(P.ROCK_LIT, byF, 0.5), 0.5);
      g.fill();
    }

    /* Korály a sasanky po dně. Střídají se druhy i barvy; vzdálené jsou
       vymyté vodou (murk), aby dno mělo hloubku a ne plakátové barvy. */
    const corals = Math.round(W / H * 13);
    for (let i = 0; i < corals; i++) {
      const cxF = rand();
      const cyF = FLOOR_BACK + 0.02 + Math.pow(rand(), 0.9) * 0.26;
      const cx = W * cxF, cy = H * cyF;
      const base = P.CORAL[Math.floor(rand() * P.CORAL.length)];
      const col = rgba(murk(base, cyF, 0.62), 1);
      const s = H * (0.030 + rand() * 0.045) * (0.7 + depthScale(cyF) * 0.6);
      g.fillStyle = 'rgba(18,34,44,0.22)';
      g.beginPath();
      g.ellipse(cx, cy + s * 0.06, s * 0.7, s * 0.16, 0, 0, Math.PI * 2);
      g.fill();
      const kind = i % 3;
      if (kind === 0) drawBranchCoral(g, cx, cy, s, col, rand);
      else if (kind === 1) drawBrainCoral(g, cx, cy, s * 0.45, col, rand);
      else drawAnemone(g, cx, cy, s * 0.42, rgba(murk(P.ANEMONE, cyF, 0.55), 1), rand);
    }

    /* Chaluhy a tráva. Rozhoduje pata: co vyrůstá NAD nejnižší drahou ryb
       (vzadu, do ~0.72) patří do zadního plátna, protože ryba má plavat před
       tím; co vyrůstá blíž divákovi, musí rybu naopak zakrývat, a jde tedy do
       předního plátna `fg` (stejný princip jako stromy poloostrova v křídové
       laguně). */
    const plants = Math.round(W / H * 20);
    for (let i = 0; i < plants; i++) {
      const px = rand() * W;
      const pyF = FLOOR_BACK + 0.008 + Math.pow(rand(), 0.8) * 0.32;
      const front = pyF > 0.725;
      const dst = front ? fg : g;
      // zadni chaluhy jsou vyssi, at zasahuji do drah ryb (ryba pak plave
      // pred necim, ne pred prazdnou modrou); predni jsou spis silueta
      const ph = H * (0.10 + rand() * 0.16) * (0.6 + depthScale(pyF) * 0.75)
               * (front ? 0.85 : 1.15);
      const deep = front ? [8, 34, 44] : [10, 46, 62];
      const dark = rgba(mix(murk(P.KELP_DARK, pyF, 0.45), deep, front ? 0.45 : 0.15), 1);
      const litc = rgba(mix(murk(P.KELP_MID, pyF, 0.45), deep, front ? 0.50 : 0.15), 1);
      if (rand() < 0.78) {
        drawKelp(dst, px, H * pyF, ph, ph * 0.13, rand() * 6.283, dark, litc, rand);
      } else {
        drawSeagrass(dst, px, H * pyF, ph * 0.55, litc, rand);
      }
    }
    return { canvas: c, y0: y0 };
  }

  /* Přední kulisa: velké trsy v dolních rozích a jeden kámen u spodní hrany.
     Kreslí se do plátna, které drawFront vrství NAD ryby — ryba tak zajede
     za popředí a scéna má čitelný předek. */
  function buildFront(W, H, rand, fg) {
    const clumps = Math.round(W / H * 4);
    for (let i = 0; i < clumps; i++) {
      const pos = i / Math.max(1, clumps - 1);
      // trsy do rohů, uprostřed se nechává průhled na ryby
      const fx = W * (pos < 0.5 ? pos * 0.34 - 0.03 + rand() * 0.05
                                : 0.70 + (pos - 0.5) * 0.66 + rand() * 0.05);
      const by = H * (1.03 + rand() * 0.05);
      const hh = H * (0.20 + rand() * 0.13);
      const strands = 2 + Math.floor(rand() * 2);
      for (let k = 0; k < strands; k++) {
        const off = (k - (strands - 1) / 2) * W * 0.018;
        const col = rgba(mix(P.KELP_DARK, [4, 20, 24], 0.35), 1);
        drawKelp(fg, fx + off, by, hh * (0.7 + rand() * 0.5), hh * 0.12,
                 rand() * 6.283, col, rgba(mix(P.KELP_MID, [6, 30, 30], 0.45), 1), rand);
      }
      drawSeagrass(fg, fx, by - H * 0.02, hh * 0.34,
                   rgba(mix(P.KELP_MID, [6, 28, 30], 0.55), 1), rand);
    }
    // korálový trs u samé spodní hrany — silueta, jen tvar
    for (let i = 0; i < 2; i++) {
      const cx = W * (0.16 + i * 0.62 + rand() * 0.08);
      drawBranchCoral(fg, cx, H * 1.02, H * 0.22,
                      rgba(mix(P.CORAL[0], [6, 24, 34], 0.62), 1), rand);
    }
  }

  // -------------------------------------------------------------- runtime

  let state = null;

  function build(W, H) {
    const rand = mulberry32(SEED);
    const frontY0 = Math.round(H * FRONT_TOP);
    const front = makeCanvas(W, H - frontY0 + Math.round(H * 0.10));
    const fg = front.getContext('2d');
    fg.translate(0, -frontY0);

    const water = buildWater(W, H, rand);
    const floor = buildFloor(W, H, rand, fg);
    buildFront(W, H, rand, fg);

    // hladina: dvě vlnové délky, každá s vlastní rychlostí
    const waves = [];
    for (let i = 0; i < 5; i++) {
      waves.push({ off: (i - 2) * 0.008, wl: 0.055 + rand() * 0.14,
                   amp: 0.0016 + rand() * 0.0030, sp: 0.25 + rand() * 0.45,
                   a: 0.20 + rand() * 0.45, ph: rand() * 6.283 });
    }
    // světelné kužely: šířka a náklon se pomalu vlní
    const rays = [];
    for (let i = 0; i < 8; i++) {
      rays.push({ x: rand(), w: 0.012 + rand() * 0.030, lean: (rand() - 0.5) * 0.6,
                  len: 0.55 + rand() * 0.45, a: 0.05 + rand() * 0.09,
                  sp: 0.10 + rand() * 0.22, ph: rand() * 6.283 });
    }
    // kaustika na písku: světlé mřížky, které se posouvají a mění
    const caustics = [];
    for (let i = 0; i < 26; i++) {
      caustics.push({ x: rand(), y: rand(), r: 0.03 + rand() * 0.07,
                      sp: 0.18 + rand() * 0.5, ph: rand() * 6.283 });
    }
    // bublinky: tři výdechy ze dna plus rozptýlené
    const bubbles = [];
    for (let i = 0; i < 54; i++) {
      const vent = i % 3;
      bubbles.push({
        x: vent === 0 ? 0.17 : (vent === 1 ? 0.55 : 0.86),
        jitter: (rand() - 0.5) * 0.05,
        from: FLOOR_BACK + 0.05 + rand() * 0.28,
        r: 0.0016 + rand() * 0.0050,
        sp: 0.045 + rand() * 0.075,
        wob: 0.004 + rand() * 0.012,
        ph: rand(),
      });
    }
    // prach ve vodě: skoro nehybné částice, aby voda nebyla vakuum
    const dust = [];
    for (let i = 0; i < 130; i++) {
      dust.push({ x: rand(), y: SURFACE + rand() * (1 - SURFACE), r: 0.4 + rand() * 1.5,
                  sp: 0.2 + rand() * 0.9, ph: rand() * 6.283, a: 0.06 + rand() * 0.16 });
    }
    // velké bubliny v popředí (do drawFront) — dodají scéně přední plán
    const nearBubbles = [];
    for (let i = 0; i < 9; i++) {
      nearBubbles.push({ x: rand(), r: 0.006 + rand() * 0.010, sp: 0.06 + rand() * 0.07,
                         wob: 0.010 + rand() * 0.018, ph: rand() });
    }

    const vig = makeCanvas(W, H), vg = vig.getContext('2d');
    const v = vg.createRadialGradient(W * 0.5, H * 0.46, H * 0.34, W * 0.5, H * 0.46, H * 1.0);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, P.VIGNETTE);
    vg.fillStyle = v;
    vg.fillRect(0, 0, W, H);

    return {
      W, H, water, floor, front, frontY0, vig,
      waves, rays, caustics, bubbles, dust, nearBubbles,
    };
  }

  /* Hladina zdola: prosvítající pruh, vlnky jako světlé čáry a pod nimi
     měkká zář. Kreslí se každý snímek — je to pět sinových čar. */
  function drawSurface(ctx, W, H, t, S) {
    const y = H * SURFACE;
    const glow = ctx.createLinearGradient(0, 0, 0, H * (SURFACE + 0.14));
    glow.addColorStop(0.00, 'rgba(' + P.RAY + ',0.55)');
    glow.addColorStop(0.42, 'rgba(' + P.RAY + ',0.20)');
    glow.addColorStop(1.00, 'rgba(' + P.RAY + ',0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H * (SURFACE + 0.14));

    ctx.save();
    ctx.lineCap = 'round';
    for (const Wv of S.waves) {
      ctx.globalAlpha = Wv.a * (0.6 + 0.4 * Math.sin(t * 0.5 + Wv.ph));
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.lineWidth = Math.max(1, H * 0.0022);
      ctx.beginPath();
      for (let x = 0; x <= W; x += 5) {
        const yy = y + H * Wv.off
                 + Math.sin(x / (W * Wv.wl) * 6.283 + t * Wv.sp * 2 + Wv.ph) * H * Wv.amp
                 + Math.sin(x / (W * Wv.wl * 0.41) * 6.283 - t * Wv.sp * 3.1) * H * Wv.amp * 0.5;
        if (x === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  /* Světelné kužely: úzké čtyřúhelníky od hladiny dolů, alfa slábne s hloubkou.
     Náklon a šířka se pomalu vlní, takže voda „žije" bez jediné textury. */
  function drawRays(ctx, W, H, t, S) {
    ctx.save();
    for (const R of S.rays) {
      const drift = Math.sin(t * R.sp + R.ph);
      const top = H * (SURFACE - 0.005);
      const bot = H * (SURFACE + R.len * (0.9 + 0.1 * drift));
      const x0 = W * lerp(LIGHT_X, R.x, 0.55);
      const w0 = W * R.w * (0.6 + 0.4 * drift);
      const w1 = w0 * (2.2 + 0.6 * drift);
      const lean = W * R.lean * 0.25 + (x0 - W * LIGHT_X) * 0.55;
      const g = ctx.createLinearGradient(0, top, 0, bot);
      g.addColorStop(0.00, 'rgba(' + P.RAY + ',' + (R.a * (0.7 + 0.3 * drift)).toFixed(3) + ')');
      g.addColorStop(0.45, 'rgba(' + P.RAY + ',' + (R.a * 0.42).toFixed(3) + ')');
      g.addColorStop(1.00, 'rgba(' + P.RAY + ',0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(x0 - w0, top);
      ctx.lineTo(x0 + w0, top);
      ctx.lineTo(x0 + lean + w1, bot);
      ctx.lineTo(x0 + lean - w1, bot);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  /* Kaustika: síť světlých skvrn na písku, která se přelévá. Kreslí se PO dně
     a před rybami, takže dno vypadá prosvícené vlnkami nad ním. */
  function drawCaustics(ctx, W, H, t, S) {
    ctx.save();
    for (const C of S.caustics) {
      const f = C.y;                                   // 0 vzadu, 1 vepředu
      const yy = H * lerp(FLOOR_BACK + 0.015, 1.02, Math.pow(f, 1.4));
      const xx = ((C.x + t * 0.006 * C.sp) % 1.2 - 0.1) * W
               + Math.sin(t * 0.35 + C.ph) * W * 0.01;
      const rr = W * C.r * (0.35 + f);
      const a = 0.10 + 0.09 * Math.sin(t * 0.9 * C.sp + C.ph);
      if (a <= 0) continue;
      const g = ctx.createRadialGradient(xx, yy, 0, xx, yy, rr);
      g.addColorStop(0, 'rgba(' + P.RAY + ',' + a.toFixed(3) + ')');
      g.addColorStop(1, 'rgba(' + P.RAY + ',0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(xx, yy, rr, rr * 0.42, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function bubble(ctx, x, y, r) {
    ctx.strokeStyle = 'rgba(232,250,255,0.65)';
    ctx.lineWidth = Math.max(0.8, r * 0.28);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.42)';
    ctx.beginPath();
    ctx.arc(x - r * 0.30, y - r * 0.32, Math.max(0.6, r * 0.28), 0, Math.PI * 2);
    ctx.fill();
  }

  function drawBubbles(ctx, W, H, t, S) {
    ctx.save();
    for (const B of S.bubbles) {
      const p = (B.ph + t * B.sp) % 1;
      const yF = lerp(B.from, SURFACE + 0.004, p);
      const y = H * yF;
      const x = W * (B.x + B.jitter) + Math.sin(p * 14 + B.ph * 6.283) * W * B.wob;
      const r = H * B.r * (0.55 + depthScale(yF)) * lerp(0.75, 1.15, p);
      ctx.globalAlpha = Math.min(1, Math.min(p * 8, (1 - p) * 6));
      bubble(ctx, x, y, r);
    }
    ctx.restore();
  }

  function drawDust(ctx, W, H, t, S) {
    ctx.save();
    for (const D of S.dust) {
      const x = ((D.x + t * 0.0025 * D.sp) % 1.06 - 0.03) * W;
      const y = H * (D.y + Math.sin(t * 0.13 * D.sp + D.ph) * 0.012);
      ctx.globalAlpha = D.a * (0.6 + 0.4 * Math.sin(t * 0.7 + D.ph));
      ctx.fillStyle = P.SPARK;
      ctx.beginPath();
      ctx.arc(x, y, D.r * (0.5 + depthScale(D.y)), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function draw(ctx, W, H, t) {
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;
    ctx.drawImage(S.water, 0, 0);
    drawRays(ctx, W, H, t, S);
    drawSurface(ctx, W, H, t, S);
    ctx.drawImage(S.floor.canvas, 0, S.floor.y0);
    drawCaustics(ctx, W, H, t, S);
    drawDust(ctx, W, H, t, S);
    drawBubbles(ctx, W, H, t, S);
  }

  function drawFront(ctx, W, H, t) {
    /* Nad ryby patří všechno, co je blíž divákovi než jejich dráhy: trsy
       chaluh a korálů z dolních rohů (pata pod dnem obrazu), velké bublinky
       v popředí a vinětace — jinak by ryba plavala přes obrázek, ne v něm. */
    if (!state || state.W !== W || state.H !== H) state = build(W, H);
    const S = state;
    ctx.drawImage(S.front, 0, S.frontY0);
    ctx.save();
    for (const B of S.nearBubbles) {
      const p = (B.ph + t * B.sp) % 1;
      const y = H * lerp(1.04, SURFACE - 0.02, p);
      const x = W * B.x + Math.sin(p * 9 + B.ph * 6.283) * W * B.wob;
      ctx.globalAlpha = 0.55 * Math.min(1, Math.min(p * 6, (1 - p) * 5));
      bubble(ctx, x, y, H * B.r);
    }
    ctx.restore();
    ctx.drawImage(S.vig, 0, 0);
  }

  return {
    draw,
    drawFront,
    // odkud prosvítá světlo do vody, ať ho 3D vrstva může napodobit
    sun: { x: LIGHT_X, y: 0.0 },
    depthScale,
  };
}
