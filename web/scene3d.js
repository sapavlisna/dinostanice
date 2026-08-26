/* Vrstva s 3D tvory nad malovanou krajinou.

   Krajina zustava kreslena do 2D platna — je ruzne a hezci, nez co by dalo
   postavit v three.js. Tvory z hotovych modelu se kresli do pruhledneho
   WebGL platna nad ni. Aby obe vrstvy sedely, kamera je ortografická a
   nastavena v pixelech obrazovky: svetove X je X na obrazovce, svetove Y je
   -Y. Scena tak muze rikat "tenhle tvor stoji na x=430, y=780 a ma byt 260 px
   dlouhy" a nemusi vedet nic o perspektive.
*/

import * as THREE from 'three';
import { GLTFLoader } from './vendor/GLTFLoader.js';
import { clone as cloneSkinned } from './vendor/SkeletonUtils.js';

const FORWARD_YAW = Math.PI / 2;   // modely koukaji na +Z, obrazovka doprava je +X
const TURN = { walk: 0.34, fly: 0.95 };
// Letec z ciste profilu je jen car; naklon k divakovi ukaze i kridla, ktera
// jsou na nem to jedine zajimave — a zaroven vrchni stranu, kam padla kresba.
const BANK = { walk: 0, fly: -0.42 };

// Chodidla se poznaji podle jmena kostry; podle nich se meri delka kroku.
// Koncove kosti (_end) se vynechavaji, jsou to jen spicky bez vlastniho pohybu.
const FOOT = /foot|toe|paw|hoof/i;
const STRIDE_SAMPLES = 32;

const loader = new GLTFLoader();
const textureLoader = new THREE.TextureLoader();
const glbCache = new Map();
const texCache = new Map();
const strideCache = new Map();

let renderer = null;
let scene = null;
let camera = null;
const actors = new Set();

let notify = () => {};
export function onNote(fn) { notify = fn; }

function initRenderer(canvas) {
  // Reset GPU driveru u kiosku je realny scenar; bez preventDefault() se
  // kontext uz nikdy neobnovi, tak se scena radsi cela nacte znovu.
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    notify('Grafika se restartovala, scéna se za chvíli načte znovu…');
    setTimeout(() => location.reload(), 3000);
  });
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setClearAlpha(0);
  renderer.sortObjects = true;

  scene = new THREE.Scene();
  camera = new THREE.OrthographicCamera(0, 1, 0, -1, -20000, 20000);

  scene.add(new THREE.HemisphereLight(0xcfe2ff, 0x5c5b3a, 1.05));
  // slunce je na malovane obloze vpravo nahore (backdrop.js), at stiny sedi
  const sun = new THREE.DirectionalLight(0xfff0d4, 2.1);
  sun.position.set(0.62, 1.35, 0.95);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0x9fc4e8, 0.5);
  fill.position.set(-0.8, 0.3, 0.6);
  scene.add(fill);
}

export function init(canvas) {
  if (renderer) return '';
  try {
    initRenderer(canvas);
    return '';
  } catch (e) {
    renderer = null;
    return e.message || String(e);       // scena to musi umet rict nahlas
  }
}

export function resize(W, H) {
  if (!renderer) return;
  renderer.setSize(W, H, false);
  camera.left = 0;
  camera.right = W;
  camera.top = 0;
  camera.bottom = -H;
  camera.updateProjectionMatrix();
}

function texture(url) {
  let e = texCache.get(url);
  if (!e) {
    const tex = textureLoader.load(url, undefined, undefined, () => {
      // nahradni jednobarevna textura: tvor je videt a chyba je nahlasena,
      // misto tichoucke bile siluety
      const c = document.createElement('canvas');
      c.width = c.height = 1;
      const g = c.getContext('2d');
      g.fillStyle = '#c9c9c9';
      g.fillRect(0, 0, 1, 1);
      tex.image = c;
      tex.needsUpdate = true;
      notify('textura se nenačetla: ' + url);
    });
    tex.flipY = false;                       // glTF ma pocatek UV vlevo nahore
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    // katalogove textury sdili vsichni ambientni tvori a drzi se trvale;
    // textura ulovku zije jen dokud je jeji tvor ve scene (refcount)
    e = { tex, refs: 0, keep: url.startsWith('/models3d/') };
    texCache.set(url, e);
  }
  e.refs++;
  return e.tex;
}

function dropTexture(url) {
  const e = texCache.get(url);
  if (!e) return;
  e.refs--;
  if (e.refs <= 0 && !e.keep) {
    e.tex.dispose();
    texCache.delete(url);
  }
}

function source(url) {
  let p = glbCache.get(url);
  if (!p) {
    p = new Promise((ok, bad) => loader.load(url, ok, undefined, bad));
    p.catch(() => glbCache.delete(url));     // at jeden sitovy zadrhel druh nezabije
    glbCache.set(url, p);
  }
  return p;
}

function measure(object) {
  /* Rozmer modelu v bind poze.

     Box3.setFromObject() se u skinovanych meshu pta na SkinnedMesh.boundingBox,
     ktery pocita z aktualni pozy — a protoze kosti uz nesou transformaci
     skeletu, jeste jednou se na nej vrstvi matrixWorld meshe. Vyjde z toho
     obalka o dva rady vetsi a s prohozenymi osami. Meritko tvora navic nema na
     poze zaviset, jinak by se pri kazdem kroku nafukoval. */
  const box = new THREE.Box3().makeEmpty();
  const one = new THREE.Box3();
  object.updateWorldMatrix(true, true);
  object.traverse((o) => {
    if (!o.geometry) return;
    if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
    box.union(one.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld));
  });
  return box;
}


function screenBox(box, quat) {
  /* Obalka modelu po natoceni — z ni se pocita meritko, aby zadany rozmer
     platil na obrazovce a ne v modelu. Letec natoceny k divakovi zabira po
     sirce min nez jeho rozpeti. */
  const out = new THREE.Box3().makeEmpty();
  const v = new THREE.Vector3();
  for (let i = 0; i < 8; i++) {
    v.set(i & 1 ? box.max.x : box.min.x,
          i & 2 ? box.max.y : box.min.y,
          i & 4 ? box.max.z : box.min.z).applyQuaternion(quat);
    out.expandByPoint(v);
  }
  return out;
}

function trimTail(clip) {
  /* Odřízne mrtvý konec klipu.

     Velociraptorova chůze má za odkráčeným cyklem ještě půl cyklu nehybné
     pózy. Ve smyčce z toho je tvor, který se uprostřed chůze zastaví — a scéna
     ho přesto posouvá dál. Hledá se, odkud už se žádná kost nehýbe: mezi
     klíčovými snímky nehybného konce zbývají jen setiny promile, kdežto živá
     animace jde po promilích rozsahu i víc. */
  let quiet = 0;
  for (const track of clip.tracks) {
    const v = track.values, t = track.times, n = t.length;
    if (n < 3) continue;
    const width = v.length / n;
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < v.length; i++) {
      if (v[i] < lo) lo = v[i];
      if (v[i] > hi) hi = v[i];
    }
    const eps = (hi - lo) * 1e-3;
    let f = n - 1;
    while (f > 0) {
      let step = 0;
      for (let c = 0; c < width; c++) {
        step = Math.max(step, Math.abs(v[f * width + c] - v[(f - 1) * width + c]));
      }
      if (step > eps) break;
      f--;
    }
    quiet = Math.max(quiet, t[f]);      // stopa, ktera se hybe nejdele, rozhoduje
  }
  // Zdrzeni kratsi nez ctvrtina klipu je soucast pohybu, ne mrtvy konec.
  if (quiet < clip.duration && quiet >= clip.duration * 0.25) clip.duration = quiet;
}

function strideOf(key, model, handle, clip) {
  /* Dráha, kterou tvor ujde za jeden cyklus animace, odečtená z chodidel.

     Klipy šlapou na místě — kostra se nikam neposouvá, takže scéna nemá odkud
     vzít, jak rychle tvorem posunout. Hádat se to nedá: každý model má jinak
     dlouhý krok i jinak dlouhý cyklus, a jak moc se odhad mine, tak moc tvor
     po zemi klouže, nebo naopak přešlapuje, aniž by se posouval.

     Noha, která se v modelu sune dozadu nejrychleji, je ta, co právě stojí na
     zemi; ostatní se zvedají nebo dosedají. Kolik za cyklus ujede, tolik se
     musí posunout tvor. Sčítá se přes celý cyklus, ne jen rozkyv jedné nohy —
     na jeden cyklus přijdou dva kroky, každý za jednu nohu.

     Vedle celkové dráhy se ukládá i kumulativní křivka posunu po fázi klipu
     (`cum`, normalizovaná 0..1) — stojná noha se nesune konstantně, takže
     `walked()` z ní čte, kolik tvor ujde za konkrétní úsek cyklu. */
  if (strideCache.has(key)) return strideCache.get(key);

  const feet = [];
  model.traverse((o) => {
    if (FOOT.test(o.name) && !/_end$/.test(o.name)) feet.push(o);
  });
  const N = STRIDE_SAMPLES;
  let travel = 0;
  const cum = new Float64Array(N + 1);
  if (feet.length && clip.duration > 0) {
    const z = feet.map(() => new Float64Array(N));
    const keep = handle.action.time;
    for (let k = 0; k < N; k++) {
      handle.action.time = k * clip.duration / N;
      handle.mixer.update(0);                  // pozice kostí pro tenhle okamžik
      model.updateWorldMatrix(true, true);
      for (let i = 0; i < feet.length; i++) z[i][k] = feet[i].matrixWorld.elements[14];
    }
    handle.action.time = keep;

    for (let k = 0; k < N; k++) {
      let back = 0;
      for (let i = 0; i < feet.length; i++) {
        back = Math.max(back, z[i][k] - z[i][(k + 1) % N]);
      }
      travel += back;
      cum[k + 1] = travel;
    }
  }
  if (travel > 0) for (let k = 0; k <= N; k++) cum[k] /= travel;
  const stride = { travel, cum: travel > 0 ? cum : null };
  strideCache.set(key, stride);
  return stride;
}

function find(clips, name) {
  return clips.find((c) => c.name === name)
      || (name ? clips.find((c) => c.name.endsWith(name)) : undefined);
}

export async function spawn(entry) {
  if (!renderer) throw new Error('WebGL není k dispozici');
  const gltf = await source(entry.glb);
  const model = cloneSkinned(gltf.scene);

  const tex = texture(entry.texture);
  model.traverse((o) => {
    if (!o.isMesh) return;
    o.material = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.88, metalness: 0 });
    o.frustumCulled = false;                 // skinning vytahuje vrcholy z bind bboxu
  });

  const flying = entry.motion === 'fly';
  const yaw = (FORWARD_YAW - (flying ? TURN.fly : TURN.walk));
  const bank = flying ? BANK.fly : BANK.walk;

  const box = measure(model);
  const centre = box.getCenter(new THREE.Vector3());
  // Chodec visi za nohy, letec za stred tela. Nohy jsou na y = 0: modely maji
  // pocatek na zemi. Spodek obalky by nesedel — triceratops ma bind pozu, ktera
  // sahá pet jednotek pod nej, a ve sceně by se pak vznasel nad piskem.
  const anchor = new THREE.Vector3(centre.x, flying ? centre.y : 0, centre.z);
  model.position.sub(anchor);

  const spin = new THREE.Group();
  spin.add(model);
  const root = new THREE.Group();
  root.add(spin);

  // stejne poradi jako v hierarchii nize: root naklani, spin otaci
  const q = new THREE.Quaternion()
    .setFromAxisAngle(new THREE.Vector3(0, 0, 1), bank)
    .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), yaw));
  const shifted = box.clone().translate(anchor.clone().negate());
  const onScreen = screenBox(shifted, q);

  const length = onScreen.max.x - onScreen.min.x;
  // chodec se meri od zeme nahoru, ne pres celou obalku: triceratopsu sahá bind
  // poza pod nulu a vyska by z toho vysla o polovinu vetsi
  const height = flying ? onScreen.max.y - onScreen.min.y : onScreen.max.y;

  const handle = {
    id: entry.id, motion: entry.motion, root, spin, yaw, bank,
    length, height, texUrl: entry.texture,
    // Meritko se vaze na plochu siluety, ne na delku. Kdyby vsichni meli stejnou
    // delku, apatosaurus — samy krk a ocas — by vedle tyranosaura vypadal jako
    // jesterka.
    sizePx: Math.sqrt(length * height),
    mixer: new THREE.AnimationMixer(model),
    action: null,
    breaks: {},                      // pozy, do kterych se da prolnout
    breakDur: {},
  };

  const clip = find(gltf.animations, entry.clip) || gltf.animations[0];
  if (clip) {
    trimTail(clip);
    handle.action = handle.mixer.clipAction(clip).play();
    handle.duration = clip.duration;
    // Krok v delkach tela, promitnuty do osy obrazovky stejne jako `length`,
    // aby scena mohla rychlost spocitat rovnou v podilech sirky obrazovky.
    const stride = strideOf(entry.glb + '|' + clip.name, model, handle, clip);
    handle.strideBodies = stride.travel * Math.abs(Math.sin(yaw)) / length;
    handle.phaseCum = stride.cum;
    handle.action.time = Math.random() * clip.duration;   // at neslapou v zakrytu
  }

  /* Zastavky: stani, skok, cokoli dalsiho z katalogu. Bezi porad, jen s nulovou
     vahou — scena je prolina pres chuzi, misto aby prehazovala klipy. Prechod je
     tak plynuly a nemusi se resit, ve ktere fazi kroku se tvor zastavil. */
  for (const [name, clipName] of Object.entries(entry.breaks || {})) {
    const c = handle.action && clipName && find(gltf.animations, clipName);
    if (!c) continue;
    trimTail(c);
    const action = handle.mixer.clipAction(c).play();
    action.setEffectiveWeight(0);
    action.time = Math.random() * c.duration;
    handle.breaks[name] = action;
    handle.breakDur[name] = c.duration;
  }

  root.visible = false;                      // dokud scena nerekne kam
  scene.add(root);
  actors.add(handle);
  return handle;
}

export function place(handle, at) {
  const s = at.scale;
  handle.root.position.set(at.x, -at.y, at.depth);
  handle.root.scale.setScalar(s);
  handle.root.rotation.z = handle.bank * (at.face < 0 ? -1 : 1);
  // face je -1..1: mezi tim se tvor otaci na miste a prochazi celem k divakovi
  handle.spin.rotation.y = at.face * handle.yaw;
  handle.root.visible = true;
}

export function speed(handle, timeScale) {
  if (handle.action) handle.action.timeScale = timeScale;
}

/* Kolik délek těla tvor ujde za dt při aktuálním timeScale — po kumulativní
   křivce klipu, ne průměrem. Čte action.time, ale neposouvá ho: mixer ho
   v render() posune o totéž dt. */
export function walked(handle, dt) {
  const a = handle.action;
  if (!a || !handle.phaseCum) return null;
  const cum = handle.phaseCum;
  const dur = a.getClip().duration;
  const adv = dt * a.timeScale;
  const f = (t) => {
    const p = (t / dur) * (cum.length - 1);
    const i = Math.min(cum.length - 2, Math.floor(p));
    return cum[i] + (p - i) * (cum[i + 1] - cum[i]);
  };
  const t0 = a.time % dur, t1 = t0 + adv;
  const whole = Math.floor(t1 / dur);
  return handle.strideBodies * (whole + f(t1 - whole * dur) - f(t0));
}

/* Kolik z tvora je zastavena poza `name`: 0 jde, 1 stoji (nebo skace). Mezi tim
   se obe pozy michaji, takze se tvor do zastaveni plynule uklidni. */
export function blend(handle, name, weight) {
  if (!handle.action) return;
  let on = 0;
  for (const [key, action] of Object.entries(handle.breaks)) {
    const w = key === name ? weight : 0;
    action.setEffectiveWeight(w);
    on = Math.max(on, w);
  }
  handle.action.setEffectiveWeight(1 - on);
}

/* Skok se ma prehrat od zacatku, ne odkud prave bezi. */
export function restart(handle, name) {
  if (handle.breaks[name]) handle.breaks[name].time = 0;
}

export function remove(handle) {
  if (!handle) return;
  actors.delete(handle);
  handle.mixer.stopAllAction();
  handle.mixer.uncacheRoot(handle.mixer.getRoot());
  scene.remove(handle.root);
  handle.root.traverse((o) => {
    if (o.isSkinnedMesh && o.skeleton) o.skeleton.dispose();  // bone textura
    if (o.isMesh) o.material.dispose();      // geometrie je sdilena z glbCache
  });
  dropTexture(handle.texUrl);
}

/* Diagnostika GPU pameti (pocty textur/geometrii), pro testy a kiosk. */
export function info() {
  return renderer ? { ...renderer.info.memory } : null;
}

export function render(dt) {
  if (!renderer) return;
  for (const a of actors) a.mixer.update(dt);
  renderer.render(scene, camera);
}
