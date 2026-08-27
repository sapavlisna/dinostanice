/* Ladicí panel chůze (klávesa d).

   Rychlost chodce si scéna počítá z délky kroku odečtené z animace, takže se
   nedá zvolit "co vypadá dobře" — dá se jen zvolit tempo cyklu. Tady jsou
   oba šroubky na jednom místě a mění se za běhu, ať se nemusí ladit
   překompilováním scény:

     tempo     tempo animace (timeScale). Rychlost po scéně jde s ním, aby
               chodidla zůstala na zemi — jen se šlape rychleji a tvor tomu
               odpovídajícím dílem ujde víc.
     rychlost  násobek dopočítané rychlosti. Tímhle se sladění chodidel
               rozladí — je to šroubek na "měřený krok je vedle".

   Prázdné pole = automat. Nastavení drží localStorage, ať přežije reload, a
   tlačítko "kopírovat" vysype JSON, který se dá zapéct do katalogu. */

const STORE = 'dino.tune';

let store = read();
let panel = null;
let rows = new Map();
let timer = 0;
let source = null;                  // co je ve scéně, dodává scene.js
let onChange = null;
let sceneSrc = null;                // () => aktivní definice scény (pro trasy)

function read() {
  try {
    return JSON.parse(localStorage.getItem(STORE)) || {};
  } catch (e) {
    return {};                      // rozbité nastavení není důvod nespustit scénu
  }
}

function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify(store));
  } catch (e) {
    /* v privátním okně se ladí bez pamatování */
  }
}

export function init(o) {
  source = o.read;
  onChange = o.apply;
  sceneSrc = o.scene || null;
  if (Object.keys(store).length) onChange();     // uložené hodnoty platí hned
}

export function of(key) {
  return store[key] || {};
}

function set(key, field, value) {
  const t = store[key] || (store[key] = {});
  if (value > 0) t[field] = value;
  else delete t[field];
  if (!Object.keys(t).length) delete store[key];
  save();
  onChange();
}

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  Object.assign(node, attrs || {});
  if (text !== undefined) node.textContent = text;
  return node;
}

function numberCell(key, field, onto) {
  const input = el('input', { type: 'number', step: '0.05', min: '0.05',
                              placeholder: 'auto', value: of(key)[field] || '' });
  input.oninput = () => set(key, field, parseFloat(input.value));
  const cell = el('td');
  cell.append(input);
  onto.append(cell);
  return input;
}

function rowFor(spec) {
  const tr = el('tr');
  tr.append(el('td', { className: 'who' }, spec.label));
  const row = { tr, rate: numberCell(spec.key, 'rate', tr),
                speed: numberCell(spec.key, 'speed', tr) };
  row.out = el('td', { className: 'out' });
  tr.append(row.out);
  return row;
}

function stageWidth() {
  return document.getElementById('stage').clientWidth;
}

function refresh() {
  if (!panel) return;
  const specs = source();
  const seen = new Set();
  for (const spec of specs) {
    seen.add(spec.key);
    let row = rows.get(spec.key);
    if (!row) {
      rows.set(spec.key, row = rowFor(spec));
      panel.body.append(row.tr);
    }
    for (const field of ['rate', 'speed']) {
      const input = row[field];
      const saved = of(spec.key)[field];
      if (document.activeElement === input) continue;      // do rozepsaného nesahat
      input.value = saved || '';
      // v placeholderu je, co plati bez zasahu — vcetne hodnot zapecenych ve scene
      input.placeholder = (field === 'rate' ? spec.autoRate : spec.autoSpeed).toFixed(2);
    }
    const cross = spec.px > 0 ? stageWidth() / spec.px : 0;
    row.out.textContent =
      `${Math.round(spec.px)} px/s · přejezd ${cross.toFixed(0)} s`
      + (spec.cycle ? ` · cyklus ${spec.cycle.toFixed(2)} s` : '')
      + (spec.stride ? ` · krok ${spec.stride.toFixed(3)} těla` : '')
      + (spec.count > 1 ? ` · ${spec.count}×` : '');
  }
  for (const [key, row] of rows) {
    if (!seen.has(key)) { row.tr.remove(); rows.delete(key); }
  }
  if (ui) {
    curPaths();
    if (routesSig() !== uiSig) syncRoutesUI();   // např. přepnutí scény za běhu
  }
}

/* ---- Trasy (bod 9) -------------------------------------------------------

   Editor waypointů aktivní scény. Efektivní trasy = úpravy z localStorage
   (per klíč scény), jinak deep-copy pole `paths` z definice scény; scene.js
   si je bere přes pathsFor() při příchodu tvora, editor edituje tutéž
   instanci, takže tvorové na trase reagují na tažení bodů živě.

   Ovládání v editačním režimu (checkbox „editovat"):
     klik do scény      přidat waypoint na konec vybrané trasy
     klik na bod        cyklovat typ chůze → zastávka → otočka
     tažení bodu        posunout (u kraje obrazovky přeskočí za okraj)
     pravý klik na bod  smazat */

const PSTORE = 'dino.paths';
const HIT_PX = 14;                  // dosah kliku na bod
const EDGE_PX = 12;                 // klik/dotažení ke kraji = bod za okraj
const DO_CYCLE = { walk: 'stop', stop: 'turn', turn: 'walk' };
const DO_COLOR = { walk: '#7fd68a', stop: '#ffb35c', turn: '#c79bff' };
const DO_LABEL = { stop: 'stop', turn: 'otočka' };

let liveKey = '';                   // klíč scény, pro kterou platí livePaths
let livePaths = [];                 // efektivní trasy (sdílené se scene.js)
let liveDef = [];                   // trasy z definice (pro „smazat úpravy")
let edited = false;                 // localStorage přebíjí definici
let sel = 0;                        // index vybrané trasy
let editing = false;
let drag = null;                    // { pt, moved } — rozpracované tažení
let ui = null;                      // prvky sekce Trasy v panelu

function readPathStore() {
  try {
    return JSON.parse(localStorage.getItem(PSTORE)) || {};
  } catch (e) {
    return {};
  }
}

export function pathsFor(def) {
  if (!def || !def.key) return [];
  if (liveKey !== def.key) {
    liveKey = def.key;
    liveDef = def.paths || [];
    const saved = readPathStore()[def.key];
    edited = !!saved;
    livePaths = saved || JSON.parse(JSON.stringify(liveDef));
    sel = 0;
    drag = null;
  }
  return livePaths;
}

function curPaths() {
  return sceneSrc ? pathsFor(sceneSrc()) : [];
}

function savePaths() {
  edited = true;
  const all = readPathStore();
  all[liveKey] = livePaths;
  try {
    localStorage.setItem(PSTORE, JSON.stringify(all));
  } catch (e) {
    /* v privátním okně se kreslí bez pamatování */
  }
}

function revertPaths() {
  const all = readPathStore();
  delete all[liveKey];
  try {
    localStorage.setItem(PSTORE, JSON.stringify(all));
  } catch (e) { /* viz savePaths */ }
  livePaths = JSON.parse(JSON.stringify(liveDef));
  edited = false;
  sel = 0;
}

function stageSize() {
  const st = document.getElementById('stage');
  return { W: st.clientWidth, H: st.clientHeight };
}

/* Pozice kliku v podílech obrazovky; těsně u kraje se bod posílá za okraj
   (±0.12), protože tam kurzorem nejde — trasy mají začínat mimo scénu. */
function clickFrac(e) {
  const { W, H } = stageSize();
  let x = e.clientX / W, y = e.clientY / H;
  if (e.clientX < EDGE_PX) x = -0.12;
  if (e.clientX > W - EDGE_PX) x = 1.12;
  if (e.clientY < EDGE_PX) y = -0.12;
  if (e.clientY > H - EDGE_PX) y = 1.12;
  return { x: +x.toFixed(3), y: +y.toFixed(3) };
}

function hitPoint(e) {
  const path = livePaths[sel];
  if (!path) return null;
  const { W, H } = stageSize();
  for (const p of path.points) {
    if (Math.hypot(p.x * W - e.clientX, p.y * H - e.clientY) < HIT_PX) return p;
  }
  return null;
}

function onStage(e) {
  return editing && panel && e.target && e.target.tagName === 'CANVAS';
}

document.addEventListener('pointerdown', (e) => {
  if (!onStage(e) || e.button !== 0) return;
  e.preventDefault();
  curPaths();                        // sync na aktivní scénu
  drag = { pt: hitPoint(e), moved: false, x0: e.clientX, y0: e.clientY };
});

document.addEventListener('pointermove', (e) => {
  if (!drag || !drag.pt || !editing) return;
  if (!drag.moved && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 5) return;
  drag.moved = true;
  const f = clickFrac(e);
  drag.pt.x = f.x;
  drag.pt.y = f.y;
});

document.addEventListener('pointerup', (e) => {
  if (!drag) return;
  const d = drag;
  drag = null;
  if (!editing || !panel) return;
  if (d.pt && d.moved) {
    savePaths();                     // tažení skončilo — uložit poslední pozici
  } else if (d.pt) {
    // klik na bod cykluje typ; dwell má smysl jen u zastávky
    d.pt.do = DO_CYCLE[d.pt.do] || 'stop';
    if (d.pt.do === 'stop') { if (!d.pt.dwell) d.pt.dwell = [3, 8]; }
    else delete d.pt.dwell;
    savePaths();
  } else if (onStage(e)) {
    const path = livePaths[sel];
    if (!path) return;
    path.points.push({ ...clickFrac(e), do: 'walk' });
    savePaths();
  }
  syncRoutesUI();
});

document.addEventListener('contextmenu', (e) => {
  if (!onStage(e)) return;
  e.preventDefault();
  const p = hitPoint(e);
  const path = livePaths[sel];
  if (!p || !path) return;
  path.points.splice(path.points.indexOf(p), 1);
  savePaths();
  syncRoutesUI();
});

/* Kreslí se do horní fx vrstvy, volá to scene.js po drawFront; mimo editaci
   ani čárka. Vybraná trasa plně, ostatní jen slabou čárkovanou stopou. */
export function drawOverlay(ctx, W, H) {
  if (!editing || !panel) return;
  for (let i = 0; i < livePaths.length; i++) {
    const path = livePaths[i], pts = path.points;
    if (!pts.length) continue;
    const on = i === sel;
    ctx.save();
    ctx.lineWidth = on ? 2 : 1;
    ctx.strokeStyle = on ? 'rgba(255, 233, 168, .9)' : 'rgba(255,255,255,.28)';
    ctx.setLineDash(on ? [] : [6, 6]);
    ctx.beginPath();
    ctx.moveTo(pts[0].x * W, pts[0].y * H);
    for (const p of pts.slice(1)) ctx.lineTo(p.x * W, p.y * H);
    if (path.loop && pts.length > 2) ctx.closePath();
    ctx.stroke();
    if (!on) { ctx.restore(); continue; }
    ctx.setLineDash([]);
    ctx.font = '600 12px "Segoe UI", system-ui, sans-serif';
    ctx.textAlign = 'center';
    for (let j = 0; j < pts.length; j++) {
      const p = pts[j], x = p.x * W, y = p.y * H;
      ctx.beginPath();
      ctx.arc(x, y, 9, 0, Math.PI * 2);
      ctx.fillStyle = DO_COLOR[p.do] || DO_COLOR.walk;
      ctx.fill();
      ctx.strokeStyle = 'rgba(6, 18, 26, .85)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = '#06222c';
      ctx.fillText(String(j + 1), x, y + 4);
      const tag = DO_LABEL[p.do];
      if (tag) {
        ctx.fillStyle = 'rgba(255, 233, 168, .95)';
        ctx.fillText(tag + (p.dwell ? ` ${p.dwell[0]}–${p.dwell[1]} s` : ''), x, y - 14);
      }
    }
    ctx.restore();
  }
}

/* Sekce „Trasy" v panelu. */
function buildRoutes(box) {
  box.append(el('h2', null, 'trasy'));
  const pick = el('select');
  pick.onchange = () => { sel = +pick.value || 0; syncRoutesUI(); };
  const add = el('button', null, 'nová trasa');
  add.onclick = () => {
    curPaths();
    livePaths.push({ name: 'trasa ' + (livePaths.length + 1), loop: false,
                     species: null, points: [] });
    sel = livePaths.length - 1;
    savePaths();
    syncRoutesUI();
  };
  const editBox = el('input', { type: 'checkbox', id: 'tune-edit' });
  editBox.onchange = () => { editing = editBox.checked; };
  const editLbl = el('label', { htmlFor: 'tune-edit' }, ' editovat');
  editLbl.prepend(editBox);
  const loopBox = el('input', { type: 'checkbox', id: 'tune-loop' });
  loopBox.onchange = () => {
    const p = livePaths[sel];
    if (p) { p.loop = loopBox.checked; savePaths(); }
  };
  const loopLbl = el('label', { htmlFor: 'tune-loop' }, ' dokola');
  loopLbl.prepend(loopBox);

  const row = el('div', { className: 'tools' });
  row.append(pick, add, editLbl, loopLbl);
  box.append(row);

  const help = el('div', { className: 'hint' },
    'klik = bod na konec · klik na bod = typ · tažení = posun · '
    + 'pravý klik = smazat · kraj obrazovky = bod za okraj');
  box.append(help);

  const tools = el('div', { className: 'tools' });
  const copy = el('button', null, 'kopírovat JSON');
  copy.onclick = () => {
    const text = JSON.stringify(curPaths(), null, 2);
    window.__pathsJSON = text;       // pro testy; clipboard chce fokus okna
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => prompt('paths:', text));
    else prompt('paths:', text);
  };
  const wipe = el('button', null, 'smazat úpravy');
  wipe.onclick = () => { revertPaths(); syncRoutesUI(); };
  tools.append(copy, wipe);
  box.append(tools);

  ui = { pick, editBox, loopBox, wipe };
  syncRoutesUI();
}

let uiSig = '';

function routesSig() {
  return liveKey + '|' + sel + '|' + edited + '|'
       + livePaths.map(p => `${p.name}:${p.points.length}:${p.loop ? 1 : 0}`).join(',');
}

function syncRoutesUI() {
  if (!ui || !panel) return;
  curPaths();                        // přepnutí scény vymění trasy pod rukama
  sel = Math.max(0, Math.min(sel, livePaths.length - 1));
  ui.pick.replaceChildren(...livePaths.map((p, i) =>
    el('option', { value: i, selected: i === sel },
       (p.name || 'trasa ' + (i + 1)) + ` (${p.points.length})`)));
  if (!livePaths.length) ui.pick.append(el('option', null, '— žádné —'));
  ui.pick.disabled = !livePaths.length;
  const p = livePaths[sel];
  ui.loopBox.checked = !!(p && p.loop);
  ui.loopBox.disabled = !p;
  ui.editBox.checked = editing;
  ui.wipe.disabled = !edited;
  uiSig = routesSig();
}

function build() {
  const box = el('div', { id: 'tune' });
  box.append(el('h2', null, 'ladění chůze — d zavře'));

  const table = el('table');
  const head = el('tr');
  for (const name of ['druh', 'tempo', 'rychlost', '']) head.append(el('th', null, name));
  table.append(head);
  const body = el('tbody');
  table.append(body);
  box.append(table);

  const tools = el('div', { className: 'tools' });
  const reset = el('button', null, 'vše na auto');
  reset.onclick = () => {
    store = {};
    save();
    onChange();
    refresh();
  };
  const copy = el('button', null, 'kopírovat JSON');
  copy.onclick = () => {
    const text = JSON.stringify(store, null, 1);
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => prompt('', text));
    else prompt('', text);
  };
  tools.append(reset, copy);
  box.append(tools);

  buildRoutes(box);

  document.body.append(box);
  return { box, body };
}

export function toggle() {
  if (panel) {
    panel.box.remove();
    clearInterval(timer);
    panel = null;
    rows = new Map();
    ui = null;
    editing = false;                 // zavření panelu = konec editace tras
    drag = null;
    return;
  }
  panel = build();
  refresh();
  timer = setInterval(refresh, 300);
}
