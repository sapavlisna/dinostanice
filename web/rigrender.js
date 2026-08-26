/* Kreslení rigu: narovnaný pás těla se ohýbá podél animované páteře,
   končetiny jsou řetězy tuhých segmentů zavěšené na páteři. */

(function (global) {
  'use strict';

  const SLICE_STEPS = [48, 64, 96, 128, 192, 256];
  const SLICE_TOL_MM = 2.0;
  const DEFAULT_BLOCKS = 6;
  const BLEED_PX = 0.7;
  /* Mezera v pruhu alfy, kterou ještě bereme jako díru v kresbě (otevřená
     tlama, prostor mezi nohama). Cokoli dál od páteře už je kus těla, přes
     který kolmice jen prolétla, a do tohohle sloupce pásu nepatří. */
  const GAP_MM = 24;

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = () => reject(new Error('nelze načíst ' + url));
      im.src = url;
    });
  }

  function darkenCopy(img, amount) {
    const c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    g.globalCompositeOperation = 'source-atop';
    g.fillStyle = 'rgba(14, 26, 40, ' + amount + ')';
    g.fillRect(0, 0, c.width, c.height);
    return c;
  }

  function tangentAngles(spine) {
    const n = spine.length;
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const a = spine[i > 0 ? i - 1 : 0];
      const b = spine[i < n - 1 ? i + 1 : n - 1];
      out[i] = Math.atan2(b[1] - a[1], b[0] - a[0]);
    }
    return out;
  }

  /* Úhly musí být spojité, ne zabalené do (-pi, pi] — jinak páteř mířící po
     listu doleva skáče mezi +180° a -180° a interpolace ji roztrhne. */
  function unwrap(a) {
    for (let i = 1; i < a.length; i++) {
      let d = a[i] - a[i - 1];
      while (d > Math.PI) { a[i] -= 2 * Math.PI; d -= 2 * Math.PI; }
      while (d < -Math.PI) { a[i] += 2 * Math.PI; d += 2 * Math.PI; }
    }
    return a;
  }

  function near(a, ref) {
    while (a - ref > Math.PI) a -= 2 * Math.PI;
    while (a - ref < -Math.PI) a += 2 * Math.PI;
    return a;
  }

  /* Dvojice končetin sdílejí jméno (obě přední nohy jsou "leg_front"), takže
     jméno nemůže být klíčem pózy — jinak by si blízká a vzdálená noha přepsaly
     úhly a tvor by šel po dvou. */
  function keyLimbs(rig) {
    rig.limbs.forEach((l, i) => { l.key = l.name + '#' + i; });
  }

  /* Ručně kreslená šablona má z dvojice nohou jen tu blízkou; té se dogeneruje
     vzdálený protějšek. Traceovaná silueta má obě strany v datech, tam se nic
     nepřidává — jinak by čtyřnožec dostal osm nohou. */
  function addFarTwins(rig) {
    if ((rig.view || 'side') !== 'side') return;
    const motion = rig.motion || 'walk';
    if (motion !== 'walk' && motion !== 'swim') return;
    const count = Object.create(null);
    for (const l of rig.limbs) count[l.name] = (count[l.name] || 0) + 1;
    const twins = rig.limbs
      .filter((l) => count[l.name] === 1 && l.side !== 1)
      .map((l) => Object.assign({}, l, { side: 1 }));
    rig.limbs.push(...twins);
  }

  class RigInstance {
    constructor(rig, images, opts) {
      this.rig = rig;
      this.id = rig.name || rig.creature;
      this.label = rig.label || rig.creature;
      this.motion = rig.motion || 'walk';
      this.view = rig.view || 'side';
      this.creature = rig.creature;
      this.ppm = rig.ppm || 5;
      this.blocks = (opts && opts.blocks) || DEFAULT_BLOCKS;
      this.bodyMode = (opts && opts.bodyMode) || 'warp';
      this.clipSlices = !(opts && opts.clip === false);
      this.minSlicePx = (opts && opts.minSlicePx) || 9;
      this.spineGain = 1;   // pro srovnávací stránku: zesílení ohybu páteře

      addFarTwins(rig);
      keyLimbs(rig);

      const b = rig.body;
      this.rigid = !!b.rigid;
      this.bodyImg = images[b.image];

      if (this.rigid) {
        this.bodyOrigin = b.origin_mm;
        this.bodySize = b.size_mm;
      } else {
        this.L = b.length_mm;
        this.half = b.half_mm;
        this.samples = b.samples;
        this.spine = b.spine_mm;
        this.theta0 = unwrap(tangentAngles(this.spine));
        this.stripH = this.bodyImg.height;
        this.mmPerPx = this.L / (this.samples - 1);
        // střed pixelu j+0.5 odpovídá řádku j pásu, proto ten přesah o půl řádku
        this.rowMm = 2 * this.half / (this.stripH - 1);
        this.destY0 = -this.half - this.rowMm / 2;
        this.destH = 2 * this.half + this.rowMm;
        this.ext = this._stripExtent();
      }
      this.slices = (opts && opts.slices) || (this.rigid ? SLICE_STEPS[0] : this._autoSlices());

      this.setBlocks(this.blocks);

      this.pose = {
        spine: null,
        rootDx: 0, rootDy: 0, rootRot: 0, rootPivotX: 0, rootPivotY: 0,
        limbs: Object.create(null),
      };
      this.setSlices(this.slices);

      this._scale = 1;
      this.limbs = rig.limbs.map((l) => this._prepLimb(l, images));
      this._anchorLimbs();
      this._measure();

      const m = Object.create(null);
      for (const l of this.limbs) {
        m[l.key] = { angles: new Float64Array(l.segments.length), sx: 1, sy: 1 };
      }
      this.pose.limbs = m;
    }

    /* Proužek se v každém úseku kreslí jako tuhý obdélník, takže bod ve
       vzdálenosti h od páteře uteče zhruba o h*Δθ/2. Kolik úseků je potřeba,
       tedy neurčuje délka, ale zakřivení krát tloušťka: límec triceratopse
       při 48 úsecích ustřelí o půl centimetru, štíhlému trexovi stačí 48. */
    _autoSlices() {
      const ext = this.ext;
      const N = this.samples, th = this.theta0, K = SLICE_STEPS[0];
      let err = 0;
      for (let i = 0; i < K; i++) {
        const a = Math.round((i * (N - 1)) / K), b = Math.round(((i + 1) * (N - 1)) / K);
        let h = 0;
        for (let j = a; j <= b; j++) {
          if (ext.has[j] && ext.above[j] > h) h = ext.above[j];
          if (ext.has[j] && ext.below[j] > h) h = ext.below[j];
        }
        const e = (h * Math.abs(th[b] - th[a])) / 2;
        if (e > err) err = e;
      }
      const want = (K * err) / SLICE_TOL_MM;
      return SLICE_STEPS.find((s) => s >= want) || SLICE_STEPS[SLICE_STEPS.length - 1];
    }

    setBlocks(n) {
      this.blocks = n;
      this.blockX = new Float64Array(n + 1);
      this.blockY = new Float64Array(n + 1);
      this.blockA = new Float64Array(n);
    }

    /* Klidová póza se skládá z tětiv mezi vzorky původní páteře, ne z rovných
       úseků délky L/K — jen tak vyjde přesně nakreslená křivka na listu. */
    setSlices(n) {
      this.slices = n;
      this.ribX = new Float64Array(n + 1);
      this.ribY = new Float64Array(n + 1);
      this.ribA = new Float64Array(n + 1);
      this.pose.spine = new Float64Array(n + 1);
      if (this.rigid) return;
      this.restX = new Float64Array(n + 1);
      this.restY = new Float64Array(n + 1);
      this.restA = new Float64Array(n + 1);
      this.restArc = new Float64Array(n + 1);
      this.segA = new Float64Array(n);
      this.segLen = new Float64Array(n);
      const N = this.samples;
      for (let i = 0; i <= n; i++) {
        const j = Math.round((i * (N - 1)) / n);
        this.restX[i] = this.spine[j][0];
        this.restY[i] = this.spine[j][1];
        this.restA[i] = this.theta0[j];
        this.restArc[i] = j * this.mmPerPx;
      }
      this.sliceAbove = new Float64Array(n);
      this.sliceBelow = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const dx = this.restX[i + 1] - this.restX[i];
        const dy = this.restY[i + 1] - this.restY[i];
        this.segA[i] = near(Math.atan2(dy, dx), this.restA[i]);
        this.segLen[i] = Math.hypot(dx, dy);
        const c0 = Math.max(0, Math.floor(this.restArc[i] / this.mmPerPx));
        const c1 = Math.min(this.samples - 1, Math.ceil(this.restArc[i + 1] / this.mmPerPx));
        let a = 0, b = 0;
        for (let x = c0; x <= c1; x++) {
          if (!this.ext.has[x]) continue;
          if (this.ext.above[x] > a) a = this.ext.above[x];
          if (this.ext.below[x] > b) b = this.ext.below[x];
        }
        this.sliceAbove[i] = a + this.rowMm;
        this.sliceBelow[i] = b + this.rowMm;
      }
      if (this.limbs) this._anchorLimbs();
    }

    _restFrameAt(u, out) {
      if (this.rigid) { out.x = 0; out.y = 0; out.a = 0; return out; }
      const K = this.slices;
      const f = Math.max(0, Math.min(K - 1e-6, u * K));
      const i = Math.floor(f);
      const fr = f - i;
      out.x = this.restX[i] * (1 - fr) + this.restX[i + 1] * fr;
      out.y = this.restY[i] * (1 - fr) + this.restY[i + 1] * fr;
      out.a = this.restA[i] * (1 - fr) + this.restA[i + 1] * fr;
      return out;
    }

    /* Kotva končetiny se bere z klidového žebroví, ne přímo z páteře na listu:
       pak sedí na tělo i tam, kde žebroví křivku nahrazuje tětivou. */
    _anchorLimbs() {
      const fr = { x: 0, y: 0, a: 0 };
      for (const l of this.limbs) {
        this._restFrameAt(l.anchor, fr);
        l.ax = fr.x;
        l.ay = fr.y;
        l.th0 = fr.a;
        const ca = Math.cos(-fr.a), sa = Math.sin(-fr.a);
        l.toLocal = (p) => {
          const dx = p[0] - l.ax, dy = p[1] - l.ay;
          return [dx * ca - dy * sa, dx * sa + dy * ca];
        };
        const pl = l.toLocal(l.segments[0].pivot);
        l.pivotLocalX = pl[0];
        l.pivotLocalY = pl[1];
        l.rigLimb._side = pl[1] >= 0 ? 1 : -1;
      }
    }

    _prepLimb(l, images) {
      const segments = l.segments.map((s) => {
        const img = images[s.image];
        return {
          img,
          dark: null,
          origin: s.origin_mm,
          pivot: s.pivot_mm,
          wmm: img.width / this.ppm,
          hmm: img.height / this.ppm,
        };
      });
      return {
        name: l.name,
        key: l.key,
        anchor: l.anchor,
        phase: l.phase || 0,
        segments,
        behind: l.side === 1,
        rigLimb: l,
        ax: 0, ay: 0, th0: 0,
        pivotLocalX: 0, pivotLocalY: 0,
        toLocal: (p) => [p[0], p[1]],
      };
    }

    /* Lokální souřadnice = milimetry na listu, takže tvor drží nakreslenou
       pózu. Pohled shora se NEsrovnává do vodorovné osy: postavilo by to
       rozpětí křídel na hranu a z letce by byl svislý proužek. Silueta shora
       se ve scéně čte jako pták nad hlavou právě s křídly do stran. */
    _baseRot() {
      return 0;
    }

    _measure() {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      this.baseRot = this._baseRot();
      const rc = Math.cos(this.baseRot), rs = Math.sin(this.baseRot);
      const add = (px, py) => {
        const x = px * rc - py * rs, y = px * rs + py * rc;
        if (x < x0) x0 = x;
        if (y < y0) y0 = y;
        if (x > x1) x1 = x;
        if (y > y1) y1 = y;
      };
      const fr = { x: 0, y: 0, a: 0 };
      const mode = this.bodyMode;
      this.bodyMode = 'warp';   // klidový rozměr se měří vždy z hladké křivky
      if (this.rigid) {
        const o = this.bodyOrigin, s = this.bodySize;
        add(o[0], o[1]);
        add(o[0] + s[0], o[1] + s[1]);
      } else {
        this._integrate(new Float64Array(this.slices + 1));
        const ext = this.ext;
        const W = this.samples;
        for (let x = 0; x < W; x++) {
          if (!ext.has[x]) continue;
          this._frameAt(x / (W - 1), fr);
          const nx = -Math.sin(fr.a), ny = Math.cos(fr.a);
          add(fr.x + nx * ext.below[x], fr.y + ny * ext.below[x]);
          add(fr.x - nx * ext.above[x], fr.y - ny * ext.above[x]);
        }
      }
      for (const l of this.limbs) {
        this._frameAt(l.anchor, fr);
        const ca = Math.cos(fr.a), sa = Math.sin(fr.a);
        for (const s of l.segments) {
          const o = s.origin;
          for (const c of [[o[0], o[1]], [o[0] + s.wmm, o[1]],
                           [o[0], o[1] + s.hmm], [o[0] + s.wmm, o[1] + s.hmm]]) {
            const p = l.toLocal(c);
            add(fr.x + p[0] * ca - p[1] * sa, fr.y + p[0] * sa + p[1] * ca);
          }
        }
      }
      this.bodyMode = mode;
      this.boundsMm = { x0, y0, x1, y1 };
      this.sizeMm = { w: x1 - x0, h: y1 - y0 };

      // šablony s hlavou vlevo se zrcadlí, ať všichni ve výchozím stavu koukají
      // doprava; po _baseRot má pohled shora hlavu vždy vlevo
      this.faceX = !this.rigid && (this.view === 'top'
                 || this.spine[0][0] < this.spine[this.samples - 1][0]) ? -1 : 1;

      this.originX = (x0 + x1) / 2;
      if (this.motion === 'walk') this.originY = y1;                 // nohy na zemi
      else if (this.rigid) this.originY = this.bodyOrigin[1] + this.bodySize[1] * 0.62;
      else this.originY = (y0 + y1) / 2;
    }

    /* Kam až pás v každém sloupci sahá, měřeno souvislým pruhem alfy kolem
       páteře. Dvě věci najednou: pás je vysoký jako nejtlustší místo tvora,
       takže podle jeho okraje by se sauropod vznášel čtyři centimetry nad zemí;
       a kolmice u čenichu prolétne přes límec, takže narovnaný pás v těch
       sloupcích nese i kus hlavy, který tam nepatří — ten se pruhem odřízne. */
    _stripExtent() {
      const W = this.samples, H = this.stripH;
      const c = document.createElement('canvas');
      c.width = W;
      c.height = H;
      const g = c.getContext('2d');
      g.drawImage(this.bodyImg, 0, 0, W, H);
      const d = g.getImageData(0, 0, W, H).data;
      const above = new Float64Array(W), below = new Float64Array(W);
      const has = new Uint8Array(W);
      const mid = Math.round((0 - this.destY0) / this.rowMm - 0.5);
      const on = (x, y) => y >= 0 && y < H && d[(y * W + x) * 4 + 3] > 8;
      const GAP = Math.max(3, Math.round(GAP_MM / this.rowMm));
      for (let x = 0; x < W; x++) {
        if (!on(x, mid)) continue;
        has[x] = 1;
        let top = mid, bot = mid;
        for (let y = mid - 1, miss = 0; y >= 0 && miss <= GAP; y--) {
          if (on(x, y)) { top = y; miss = 0; } else miss++;
        }
        for (let y = mid + 1, miss = 0; y < H && miss <= GAP; y++) {
          if (on(x, y)) { bot = y; miss = 0; } else miss++;
        }
        above[x] = -(this.destY0 + top * this.rowMm);
        below[x] = this.destY0 + (bot + 1) * this.rowMm;
      }
      return { above, below, has };
    }

    _darkOf(seg) {
      if (!seg.dark) seg.dark = darkenCopy(seg.img, 0.42);
      return seg.dark;
    }

    /* Páteř: klidové tětivy pootočené o animační odchylku, skládané od středu
       ven, aby vlna na krku neotáčela celým zvířetem. Při nulové odchylce
       vyjde přesně původní křivka z rig.json. */
    _integrate(angles) {
      const K = this.slices;
      const m = K >> 1;
      const px = this.ribX, py = this.ribY, pa = this.ribA;
      const g = this.spineGain;
      for (let i = 0; i <= K; i++) pa[i] = this.restA[i] + angles[i] * g;
      px[m] = this.restX[m];
      py[m] = this.restY[m];
      for (let i = m; i < K; i++) {
        const a = this.segA[i] + (angles[i] + angles[i + 1]) * 0.5 * g;
        px[i + 1] = px[i] + this.segLen[i] * Math.cos(a);
        py[i + 1] = py[i] + this.segLen[i] * Math.sin(a);
      }
      for (let i = m; i > 0; i--) {
        const a = this.segA[i - 1] + (angles[i - 1] + angles[i]) * 0.5 * g;
        px[i - 1] = px[i] - this.segLen[i - 1] * Math.cos(a);
        py[i - 1] = py[i] - this.segLen[i - 1] * Math.sin(a);
      }
    }

    _integrateBlocks() {
      const B = this.blocks, K = this.slices;
      const bl = this.L / B;
      for (let b = 0; b < B; b++) {
        const f = (b + 0.5) * K / B;
        const i = Math.min(K - 1, Math.floor(f));
        const fr = f - i;
        this.blockA[b] = this.ribA[i] * (1 - fr) + this.ribA[i + 1] * fr;
      }
      const m = B >> 1;
      const f = m * K / B;
      const i = Math.min(K - 1, Math.floor(f));
      const fr = f - i;
      this.blockX[m] = this.ribX[i] * (1 - fr) + this.ribX[i + 1] * fr;
      this.blockY[m] = this.ribY[i] * (1 - fr) + this.ribY[i + 1] * fr;
      for (let b = m; b < B; b++) {
        this.blockX[b + 1] = this.blockX[b] + bl * Math.cos(this.blockA[b]);
        this.blockY[b + 1] = this.blockY[b] + bl * Math.sin(this.blockA[b]);
      }
      for (let b = m; b > 0; b--) {
        this.blockX[b - 1] = this.blockX[b] - bl * Math.cos(this.blockA[b - 1]);
        this.blockY[b - 1] = this.blockY[b] - bl * Math.sin(this.blockA[b - 1]);
      }
    }

    _frameAt(u, out) {
      if (this.rigid) { out.x = 0; out.y = 0; out.a = 0; return out; }
      if (this.bodyMode === 'blocks') {
        const B = this.blocks;
        let b = Math.floor(u * B);
        if (b < 0) b = 0;
        if (b > B - 1) b = B - 1;
        const d = (u - b / B) * this.L;
        out.a = this.blockA[b];
        out.x = this.blockX[b] + d * Math.cos(out.a);
        out.y = this.blockY[b] + d * Math.sin(out.a);
        return out;
      }
      const K = this.slices;
      const f = Math.max(0, Math.min(K - 1e-6, u * K));
      const i = Math.floor(f);
      const fr = f - i;
      out.x = this.ribX[i] * (1 - fr) + this.ribX[i + 1] * fr;
      out.y = this.ribY[i] * (1 - fr) + this.ribY[i + 1] * fr;
      out.a = this.ribA[i] * (1 - fr) + this.ribA[i + 1] * fr;
      return out;
    }

    _drawBodyWarp(ctx) {
      const K = this.slices, img = this.bodyImg;
      const px = this.ribX, py = this.ribY, pa = this.ribA;
      const mmPerPx = this.mmPerPx, N = this.samples;
      const clipExt = 0.9 * mmPerPx;
      const clip = this.clipSlices !== false;
      // malý tvor na obrazovce nepotřebuje plný počet proužků
      const want = Math.max(8, Math.round(this.L * this._scale / this.minSlicePx));
      let q = Math.max(1, Math.round(K / Math.min(K, want)));
      while (q > 1 && K % q !== 0) q--;
      for (let i = 0; i < K; i += q) {
        const j = i + q;
        const s0 = this.restArc[i], s1 = this.restArc[j];
        const a0 = pa[i], a1 = pa[j];
        // napříč se řeže jen tam, kam pás v tomto úseku opravdu sahá; okraj
        // pásu je u siluet daleko za tělem a pustil by sem cizí obsah
        let hb = 0, ha = 0;
        for (let k = i; k < j; k++) {
          if (this.sliceAbove[k] > ha) ha = this.sliceAbove[k];
          if (this.sliceBelow[k] > hb) hb = this.sliceBelow[k];
        }
        // v ohybu vybíhá klínový výřez za obdélník proužku; dokresli tolik,
        // aby ani na vnější straně oblouku nezůstala spára
        const bleedMm = clipExt + BLEED_PX * mmPerPx
                      + Math.max(ha, hb) * Math.tan(Math.min(0.7, Math.abs(a1 - a0)) / 2);
        const bleedPx = bleedMm / mmPerPx;
        const u0 = Math.max(0, s0 / mmPerPx + 0.5 - bleedPx);
        const u1 = Math.min(N, s1 / mmPerPx + 0.5 + bleedPx);
        const sw = u1 - u0;
        if (sw <= 0) continue;
        const am = (a0 + a1) * 0.5;
        const mx = (px[i] + px[j]) * 0.5, my = (py[i] + py[j]) * 0.5;
        const sc = (s0 + s1) * 0.5;

        ctx.save();
        if (clip) {
          const c0 = Math.cos(a0), n0x = -Math.sin(a0), n0y = c0;
          const t0x = c0, t0y = Math.sin(a0);
          const c1 = Math.cos(a1), n1x = -Math.sin(a1), n1y = c1;
          const t1x = c1, t1y = Math.sin(a1);
          const ax = px[i] - t0x * clipExt, ay = py[i] - t0y * clipExt;
          const bx = px[j] + t1x * clipExt, by = py[j] + t1y * clipExt;
          /* V ohybu se boční hrany výřezu protnou dřív, než dojdou k okraji
             pásu, a čtyřúhelník se překlopí do přesýpacích hodin — ořez pak
             pustí obsah z úplně jiného místa těla (límec triceratopse skončí
             pod břichem). Na protnuté straně se proto oba rohy slijí do
             průsečíku a z výřezu je trojúhelník. */
          const sn = Math.sin(a1 - a0);
          const s = Math.abs(sn) > 1e-9
            ? ((ax - bx) * n1y - n1x * (ay - by)) / -sn : Infinity;
          ctx.beginPath();
          if (s > 0 && s < hb) {
            ctx.moveTo(ax + n0x * s, ay + n0y * s);
            ctx.lineTo(ax - n0x * ha, ay - n0y * ha);
            ctx.lineTo(bx - n1x * ha, by - n1y * ha);
          } else if (s < 0 && s > -ha) {
            ctx.moveTo(ax + n0x * hb, ay + n0y * hb);
            ctx.lineTo(ax + n0x * s, ay + n0y * s);
            ctx.lineTo(bx + n1x * hb, by + n1y * hb);
          } else {
            ctx.moveTo(ax + n0x * hb, ay + n0y * hb);
            ctx.lineTo(ax - n0x * ha, ay - n0y * ha);
            ctx.lineTo(bx - n1x * ha, by - n1y * ha);
            ctx.lineTo(bx + n1x * hb, by + n1y * hb);
          }
          ctx.closePath();
          ctx.clip();
        }
        ctx.translate(mx, my);
        ctx.rotate(am);
        const dx = (u0 - 0.5) * mmPerPx - sc;
        ctx.drawImage(img, u0, 0, sw, this.stripH, dx, this.destY0,
                      sw * mmPerPx, this.destH);
        ctx.restore();
      }
    }

    _drawBodyBlocks(ctx) {
      const B = this.blocks, img = this.bodyImg;
      const mmPerPx = this.mmPerPx, N = this.samples;
      const bl = this.L / B;
      for (let b = 0; b < B; b++) {
        const s0 = b * bl, s1 = (b + 1) * bl;
        const u0 = Math.max(0, s0 / mmPerPx + 0.5);
        const u1 = Math.min(N, s1 / mmPerPx + 0.5);
        const sw = u1 - u0;
        if (sw <= 0) continue;
        ctx.save();
        ctx.translate(this.blockX[b], this.blockY[b]);
        ctx.rotate(this.blockA[b]);
        ctx.drawImage(img, u0, 0, sw, this.stripH,
                      (u0 - 0.5) * mmPerPx - s0, this.destY0, sw * mmPerPx, this.destH);
        ctx.restore();
      }
    }

    _drawRigidBody(ctx) {
      const o = this.bodyOrigin, s = this.bodySize;
      ctx.drawImage(this.bodyImg, o[0], o[1], s[0], s[1]);
    }

    _drawLimb(ctx, limb, st, dark) {
      if (!st) return;
      const fr = this._frameAt(limb.anchor, this._tmpFrame);
      ctx.save();
      ctx.translate(fr.x, fr.y);
      ctx.rotate(fr.a);
      if (st.sx !== 1 || st.sy !== 1) {
        ctx.translate(limb.pivotLocalX, limb.pivotLocalY);
        ctx.scale(st.sx, st.sy);
        ctx.translate(-limb.pivotLocalX, -limb.pivotLocalY);
      }
      ctx.rotate(-limb.th0);
      ctx.translate(-limb.ax, -limb.ay);   // odteď se pracuje v mm listu
      const segs = limb.segments;
      for (let j = 0; j < segs.length; j++) {
        const s = segs[j];
        const a = st.angles[j] || 0;
        if (a !== 0) {
          ctx.translate(s.pivot[0], s.pivot[1]);
          ctx.rotate(a);
          ctx.translate(-s.pivot[0], -s.pivot[1]);
        }
        ctx.drawImage(dark ? this._darkOf(s) : s.img,
                      s.origin[0], s.origin[1], s.wmm, s.hmm);
      }
      ctx.restore();
    }

    /* Ujetá dráha v milimetrech tvora, odečtená z jeho pohybu po plátně. Scéna
       hýbe tvorem sama a rytmus kroku se pak veze na ní, takže noha v opoře
       stojí, ať scéna zvolí jakoukoli rychlost. */
    _travelMm(o, scale) {
      if (this.motion !== 'walk') return undefined;
      const t = o.t || 0, x = o.x || 0;
      const dt = t - this._lastT;
      if (this._travel === undefined) this._travel = 0;
      else if (dt > 0 && dt < 0.5) this._travel += Math.abs(x - this._lastX) / scale;
      this._lastT = t;
      this._lastX = x;
      return this._travel;
    }

    draw(ctx, o) {
      const pose = this.pose;
      const anim = global.Anim;
      if (!anim) throw new Error('anim.js není načtený');
      const ao = this._animOpts || (this._animOpts = { motion: this.motion, view: this.view });
      const scale = o.scale || 1;
      this._scale = scale;
      ao.t = o.t || 0;
      ao.phase = o.phase || 0;
      ao.speed = o.speed || 1;
      ao.rest = !!o.rest;
      ao.distance = this._travelMm(o, scale);
      anim.pose(this.rig, ao, pose);

      if (!this.rigid) {
        this._integrate(pose.spine);
        if (this.bodyMode === 'blocks') this._integrateBlocks();
      }
      if (!this._tmpFrame) this._tmpFrame = { x: 0, y: 0, a: 0 };

      ctx.save();
      ctx.translate(o.x || 0, o.y || 0);
      ctx.scale((o.flip ? -1 : 1) * this.faceX * scale, scale);
      ctx.translate(pose.rootDx, pose.rootDy);
      if (pose.rootRot) {
        ctx.translate(pose.rootPivotX, pose.rootPivotY);
        ctx.rotate(pose.rootRot);
        ctx.translate(-pose.rootPivotX, -pose.rootPivotY);
      }
      ctx.translate(-this.originX, -this.originY);
      if (this.baseRot) ctx.rotate(this.baseRot);

      for (const l of this.limbs) {
        if (l.behind) this._drawLimb(ctx, l, pose.limbs[l.key], true);
      }
      if (this.rigid) this._drawRigidBody(ctx);
      else if (this.bodyMode === 'blocks') this._drawBodyBlocks(ctx);
      else this._drawBodyWarp(ctx);
      for (const l of this.limbs) {
        if (!l.behind) this._drawLimb(ctx, l, pose.limbs[l.key], false);
      }
      ctx.restore();
    }
  }

  async function load(baseUrl, opts) {
    const base = baseUrl.endsWith('/') ? baseUrl : baseUrl + '/';
    const res = await fetch(base + 'rig.json');
    if (!res.ok) throw new Error('rig.json: HTTP ' + res.status);
    const rig = await res.json();
    rig.limbs = (rig.limbs || []).filter((l) => l.segments && l.segments.length);
    const names = new Set([rig.body.image]);
    for (const l of rig.limbs) for (const s of l.segments) names.add(s.image);
    const list = [...names];
    const loaded = await Promise.all(list.map((n) => loadImage(base + n)));
    const images = Object.create(null);
    list.forEach((n, i) => { images[n] = loaded[i]; });
    return new RigInstance(rig, images, opts);
  }

  global.Rig = { load, RigInstance };
})(window);
