import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const SWING_DEG = 13;            // how far a leg swings fore and aft
const BOB_MM = 3.0;              // vertical body bounce
const NECK_DEG = 7;              // idle sway of the neck
const TAIL_DEG = 9;
const STEP_HZ = 0.55;
const NECK_END = 0.35;           // spine fraction the neck hinge covers
const TAIL_START = 0.72;

const st = {
  playing: true, spin: true, clock: new THREE.Clock(), t: 0,
  model: null, mesh: null, doc: null, texture: null,
};

const el = (id) => document.getElementById(id);
const status = (msg, bad) => {
  const box = el('status');
  box.textContent = msg;
  box.className = bad ? 'bad' : '';
};

// ---------------------------------------------------------------- scene setup

const canvas = el('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a2028);

const camera = new THREE.PerspectiveCamera(38, 1, 5, 5000);
camera.position.set(230, 170, 430);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 90;
controls.maxDistance = 1600;
controls.maxPolarAngle = Math.PI * 0.52;

scene.add(new THREE.HemisphereLight(0xbfd8ff, 0x4a4030, 1.15));

const sun = new THREE.DirectionalLight(0xfff2dc, 2.0);
sun.position.set(-260, 420, 320);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
const sc = sun.shadow.camera;
sc.left = -320; sc.right = 320; sc.top = 320; sc.bottom = -320; sc.near = 50; sc.far = 1200;
sun.shadow.bias = -0.0012;
scene.add(sun);

const rim = new THREE.DirectionalLight(0x9ec8ff, 0.65);
rim.position.set(340, 150, -300);
scene.add(rim);

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(900, 64).rotateX(-Math.PI / 2),
  new THREE.MeshStandardMaterial({ color: 0x6f7f66, roughness: 1 })
);
ground.receiveShadow = true;
scene.add(ground);

const grid = new THREE.GridHelper(1200, 24, 0x8fa38a, 0x6a7a66);
grid.material.transparent = true;
grid.material.opacity = 0.22;
grid.position.y = 0.4;
scene.add(grid);

// ------------------------------------------------------------- model building

function disposeModel() {
  if (!st.model) return;
  st.mesh.geometry.dispose();
  st.mesh.material.dispose();
  scene.remove(st.model);
  st.model = st.mesh = null;
}

/** One skin for the whole animal, turned over once because sheet coordinates
 *  run y-down. A rotation keeps the triangle winding; mirroring the axis would
 *  turn the mesh inside out. */
function buildModel(doc, texture) {
  disposeModel();

  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(doc.pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(doc.nrm, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(doc.uv, 2));
  g.setIndex(doc.idx);

  const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    map: texture, roughness: 0.92, metalness: 0.0, side: THREE.DoubleSide,
  }));
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  const inner = new THREE.Group();
  inner.add(mesh);
  const model = new THREE.Group();
  model.rotation.x = Math.PI;
  model.add(inner);
  scene.add(model);

  st.model = model;
  st.inner = inner;
  st.mesh = mesh;
  st.doc = doc;
  st.restPos = new Float32Array(g.attributes.position.array);
  st.restNrm = new Float32Array(g.attributes.normal.array);
  st.spineT = doc.spine_t;
  st.limbId = doc.limb_id;
  st.limbW = doc.limb_w;
  st.hinges = {
    neck: hingeAt(doc, NECK_END),
    tail: hingeAt(doc, TAIL_START),
  };

  const box = new THREE.Box3().setFromObject(model);
  const mid = box.getCenter(new THREE.Vector3());
  model.position.set(-mid.x, -box.min.y, -mid.z);

  const size = box.getSize(new THREE.Vector3());
  controls.target.set(0, size.y * 0.45, 0);
  const reach = Math.max(size.x, size.y);
  camera.position.set(reach * 0.75, size.y * 0.85, reach * 1.35);
  controls.update();

  el('info').textContent =
    `${doc.label} · ${doc.pos.length / 3} vrcholů · ${doc.limbs.length} končetin · ` +
    `${size.x.toFixed(0)}×${size.y.toFixed(0)}×${size.z.toFixed(0)} mm`;
  el('notes').textContent = (doc.notes || []).join(' · ');
}

function hingeAt(doc, frac) {
  let i = 0;
  while (i < doc.spine_s.length - 1 && doc.spine_s[i + 1] < frac) i++;
  return doc.spine[i];
}

// ------------------------------------------------------------------ animation

/** Every vertex carries which limb owns it and how strongly, so a leg bends at
 *  the hip by rotating its own vertices -- no skeleton, no seam to split open.
 *  The neck and the tail bend the same way, hinged on the spine and graded by
 *  how far along it a vertex sits, so they arc rather than snap at one joint. */
function deform(t) {
  const pos = st.mesh.geometry.attributes.position.array;
  const nrm = st.mesh.geometry.attributes.normal.array;
  const rp = st.restPos, rn = st.restNrm;
  const id = st.limbId, w = st.limbW, sp = st.spineT;
  const walk = st.doc.motion === 'walk';

  const swing = st.doc.limbs.map((l) => (walk
    ? THREE.MathUtils.degToRad(SWING_DEG) * Math.sin(2 * Math.PI * (STEP_HZ * t + l.phase))
    : 0));
  const neckAng = THREE.MathUtils.degToRad(NECK_DEG) * Math.sin(2 * Math.PI * 0.21 * t);
  const tailAng = THREE.MathUtils.degToRad(TAIL_DEG) * Math.sin(2 * Math.PI * 0.29 * t + 1.1);
  const [nhx, nhy] = st.hinges.neck;
  const [thx, thy] = st.hinges.tail;

  for (let v = 0, n = sp.length; v < n; v++) {
    const k = v * 3;
    let x = rp[k], y = rp[k + 1];
    let turn = 0;

    const li = id[v];
    if (li >= 0) {
      const a = swing[li] * w[v];
      if (a) {
        const p = st.doc.limbs[li].pivot;
        const c = Math.cos(a), s = Math.sin(a);
        const dx = x - p[0], dy = y - p[1];
        x = p[0] + dx * c - dy * s;
        y = p[1] + dx * s + dy * c;
        turn += a;
      }
    }

    const f = sp[v];
    let a2 = 0, hx = 0, hy = 0;
    if (f < NECK_END) {
      a2 = neckAng * Math.pow(1 - f / NECK_END, 1.5); hx = nhx; hy = nhy;
    } else if (f > TAIL_START) {
      a2 = tailAng * Math.pow((f - TAIL_START) / (1 - TAIL_START), 1.5); hx = thx; hy = thy;
    }
    if (a2) {
      const c = Math.cos(a2), s = Math.sin(a2);
      const dx = x - hx, dy = y - hy;
      x = hx + dx * c - dy * s;
      y = hy + dx * s + dy * c;
      turn += a2;
    }

    pos[k] = x; pos[k + 1] = y;
    if (turn) {
      const c = Math.cos(turn), s = Math.sin(turn);
      nrm[k] = rn[k] * c - rn[k + 1] * s;
      nrm[k + 1] = rn[k] * s + rn[k + 1] * c;
    } else {
      nrm[k] = rn[k]; nrm[k + 1] = rn[k + 1];
    }
  }
  st.mesh.geometry.attributes.position.needsUpdate = true;
  st.mesh.geometry.attributes.normal.needsUpdate = true;
}

function animate(dt) {
  if (!st.model) return;
  if (st.playing) st.t += dt;
  deform(st.t);
  const walk = st.doc.motion === 'walk';
  st.inner.position.y = walk
    ? -Math.abs(Math.sin(2 * Math.PI * STEP_HZ * st.t)) * BOB_MM   // y-down: up is negative
    : 0;
  if (st.spin) st.model.rotation.y += dt * 0.35;
}

function frame() {
  const dt = Math.min(st.clock.getDelta(), 0.05);
  animate(dt);
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);

// ------------------------------------------------------------------- loading

function loadTexture(url) {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(url, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
      resolve(tex);
    }, undefined, reject);
  });
}

async function show(catchId, creatureKey) {
  status('načítám…');
  try {
    const doc = await (await fetch(`/models3d/${creatureKey}.json`)).json();
    const tex = await loadTexture(catchId
      ? `/catch/${catchId}/sheet.png`
      : `/api/template-texture/${creatureKey}.png`);
    if (st.texture) st.texture.dispose();
    st.texture = tex;
    buildModel(doc, tex);
    status(catchId ? '' : 'nevybarvená šablona — vyber úlovek');
  } catch (e) {
    status(`nepovedlo se: ${e.message || e}`, true);
    throw e;
  }
}

async function boot() {
  const picker = el('catch');
  const rigs = await (await fetch('/api/rigs')).json();
  const models = await (await fetch('/api/models3d')).json();
  const have = new Set(models);

  for (const r of rigs.filter((r) => have.has(r.creature))) {
    const o = document.createElement('option');
    o.value = `${r.id}|${r.creature}`;
    o.textContent = `${r.label}${r.name ? ' — ' + r.name : ''}`;
    picker.append(o);
  }
  for (const key of models) {
    const o = document.createElement('option');
    o.value = `|${key}`;
    o.textContent = `${key} (prázdná šablona)`;
    picker.append(o);
  }
  if (!picker.options.length) { status('žádný model není hotový', true); return; }

  picker.onchange = () => {
    const [id, key] = picker.value.split('|');
    show(id, key);
  };
  picker.selectedIndex = 0;
  picker.onchange();
}

el('play').onclick = (e) => {
  st.playing = !st.playing;
  e.target.textContent = st.playing ? 'Pauza' : 'Přehrát';
};
el('spin').onclick = (e) => {
  st.spin = !st.spin;
  e.target.textContent = st.spin ? 'Zastavit otáčení' : 'Otáčet';
};
el('wire').onclick = () => {
  st.mesh.material.wireframe = !st.mesh.material.wireframe;
};
el('flat').onclick = () => {
  const m = st.mesh.material;
  m.map = m.map ? null : st.texture;
  m.color.set(m.map ? 0xffffff : 0xc8b89a);
  m.needsUpdate = true;
};

// Hooks for tools/shot3d.py, which judges the model from fixed angles.
window.__setView = (yaw, pitch) => {
  if (!st.model) return;
  st.model.rotation.y = 0;
  const box = new THREE.Box3().setFromObject(st.model);
  const size = box.getSize(new THREE.Vector3());
  const r = Math.max(size.x, size.y) * 1.35;
  controls.target.set(0, size.y * 0.45, 0);
  camera.position.set(
    controls.target.x + r * Math.cos(pitch) * Math.sin(yaw),
    controls.target.y + r * Math.sin(pitch),
    controls.target.z + r * Math.cos(pitch) * Math.cos(yaw));
  camera.lookAt(controls.target);
  controls.update();
};

resize();
frame();
boot().then(() => { window.__ready = true; });
