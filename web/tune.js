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
   tlačítko "kopírovat" vysype JSON, který se dá zapéct do katalogu.

   Trasy chodců jsou čistě data v definici scény (web/scenes/*.js) — bývalý
   editor tras byl zrušen a jeho localStorage (dino.paths) se ignoruje. */

const STORE = 'dino.tune';

let store = read();
let panel = null;
let rows = new Map();
let timer = 0;
let source = null;                  // co je ve scéně, dodává scene.js
let onChange = null;

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

  document.body.append(box);
  return { box, body };
}

export function toggle() {
  if (panel) {
    panel.box.remove();
    clearInterval(timer);
    panel = null;
    rows = new Map();
    return;
  }
  panel = build();
  refresh();
  timer = setInterval(refresh, 300);
}
