import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

const PREFERRED = 'Walk';

const el = (id) => document.getElementById(id);
const status = (msg, bad) => {
  const box = el('status');
  box.textContent = msg;
  box.className = bad ? 'bad' : '';
};

const canvas = el('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a2028);

const camera = new THREE.PerspectiveCamera(38, 1, 0.5, 500);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI * 0.52;

scene.add(new THREE.HemisphereLight(0xbfd8ff, 0x4a4030, 1.1));
const sun = new THREE.DirectionalLight(0xfff2dc, 2.0);
sun.position.set(-30, 55, 40);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 1, far: 200 });
scene.add(sun);

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(90, 64).rotateX(-Math.PI / 2),
  new THREE.MeshStandardMaterial({ color: 0x2c3a34, roughness: 1 }),
);
ground.receiveShadow = true;
scene.add(ground);

const st = { mixer: null, action: null, root: null, texture: null, playing: true,
             spin: true, textured: true, clock: new THREE.Clock() };

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);

const loader = new GLTFLoader();
const textures = new THREE.TextureLoader();

function loadTexture(url) {
  const tex = textures.load(url);
  tex.flipY = false;                         // glTF má počátek UV vlevo nahoře
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function show(entry) {
  status(`načítám ${entry.label}…`);
  if (st.root) {
    scene.remove(st.root);
    Object.assign(st, { root: null, mixer: null, action: null });
  }
  st.texture = loadTexture(entry.texture);

  loader.load(entry.glb, (gltf) => {
    const root = gltf.scene;
    st.root = root;
    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.material = new THREE.MeshStandardMaterial({
        map: st.textured ? st.texture : null, roughness: 0.85, metalness: 0,
      });
      o.frustumCulled = false;               // skinning posouvá vrcholy mimo bind bbox
    });

    resize();                                  // aby aspect sedel uz pri fitu
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const flying = entry.motion === 'fly';
    const span = Math.max(size.x, size.y, size.z);
    // chodec stoji na zemi, letec se vznasi
    root.position.y -= box.min.y - (flying ? span * 0.5 : 0);

    // kamera z boku: predloha chodce je bokorys, takze z boku sedi textura
    // presne na kresbu. Letec se kresli shora, tak na nej kamera kouka shora.
    const half = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const dist = (flying ? 1.9 : 1.3) * Math.max(span / camera.aspect, size.y) / (2 * half);
    const eyeY = flying ? span * 1.3 : size.y * 0.62;
    camera.position.set(dist * (flying ? 0.45 : 0.96), eyeY, dist * (flying ? 0.75 : 0.28));
    controls.target.set(0, flying ? span * 0.55 : size.y * 0.45, 0);
    controls.minDistance = dist * 0.25;
    controls.maxDistance = dist * 4;
    ground.scale.setScalar(Math.max(1, span / 40));
    scene.add(root);

    st.mixer = new THREE.AnimationMixer(root);
    const select = el('anim');
    select.replaceChildren(...gltf.animations.map((clip, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = clip.name.split('_').pop();   // "Armature|TRex_Walk" -> "Walk"
      return opt;
    }));
    // rezim chuze chce rovnou spravny pohyb: chodci Walk, letci Flying
    const preferredName = entry.motion === 'fly' ? 'Flying' : PREFERRED;
    const preferred = gltf.animations.findIndex((c) => c.name.endsWith(preferredName));
    select.value = String(preferred >= 0 ? preferred : 0);
    const playClip = (i) => {
      st.action?.fadeOut(0.2);
      st.action = st.mixer.clipAction(gltf.animations[i]).reset().fadeIn(0.2).play();
    };
    select.onchange = () => playClip(Number(select.value));
    playClip(Number(select.value));

    const pose = entry.pose ? ` · póza předlohy ${entry.pose.split('_').pop()}` : '';
    el('info').textContent =
      `${entry.label} · ${gltf.animations.length} animací${pose} · ${entry.source}`;
    status('hotovo');
    resize();
  }, undefined, (err) => status(`model se nenačetl: ${err.message || err}`, true));
}

status('načítám katalog…');
Promise.all([
  fetch('/api/dino3d').then((r) => r.json()),
  fetch('/api/rigs').then((r) => r.json()).catch(() => []),
]).then(([catalogue, rigs]) => {
  // ulovky jsou tentyz model, jen s texturou z vyfocene kresby
  const caught = rigs
    .filter((r) => r.kind === 'model')
    .map((r) => ({
      key: `${r.id}`,
      label: r.name ? `${r.name} — ${r.label}` : r.label,
      glb: `/models3d/${r.creature}.glb`,
      texture: `${r.url}texture.png`,
      motion: r.motion,
      pose: '',
      source: 'vybarveno a vyfoceno',
    }));
  const list = [...caught, ...catalogue.map((e) => ({ ...e, source: 'ukázková textura' }))];

  const pick = el('creature');
  let group = null;
  list.forEach((entry, i) => {
    const wanted = i < caught.length ? 'Úlovky' : 'Katalog';
    if (!group || group.label !== wanted) {
      group = document.createElement('optgroup');
      group.label = wanted;
      pick.appendChild(group);
    }
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = entry.label;
    group.appendChild(opt);
  });
  pick.addEventListener('change', () => {
    const entry = list[Number(pick.value)];
    history.replaceState(null, '', `#${entry.key}`);
    show(entry);
  });
  // na konkretniho tvora se da odkazat z prehledu sablon; hash muze nest i
  // ?mode=walk za klicem (#trex3d?mode=walk), tak se odstihne pred hledanim
  const hashKey = location.hash.slice(1).split('?')[0];
  const wanted = list.findIndex((e) => e.key === decodeURIComponent(hashKey));
  const start = wanted >= 0 ? wanted : 0;
  pick.value = String(start);
  show(list[start]);
}).catch((err) => status(`katalog se nenačetl: ${err.message || err}`, true));

el('play').addEventListener('click', () => {
  st.playing = !st.playing;
  el('play').textContent = st.playing ? 'Pauza' : 'Přehrát';
});
el('spin').addEventListener('click', () => {
  st.spin = !st.spin;
  el('spin').textContent = st.spin ? 'Zastavit otáčení' : 'Otáčet';
});
el('tex').addEventListener('click', () => {
  st.textured = !st.textured;
  st.root?.traverse((o) => {
    if (o.isMesh) {
      o.material.map = st.textured ? st.texture : null;
      o.material.color.set(st.textured ? 0xffffff : 0x9fb3a4);
      o.material.needsUpdate = true;
    }
  });
  el('tex').textContent = st.textured ? 'Bez textury' : 'S texturou';
});
el('allOptions').addEventListener('click', () => {
  document.documentElement.classList.remove('walk-mode');
});

function frame() {
  const dt = st.clock.getDelta();
  if (st.playing) st.mixer?.update(dt);
  if (st.spin && st.root) st.root.rotation.y += dt * 0.35;
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
resize();
frame();
