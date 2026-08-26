/* Lišta dole: kolik je ve scéně kterého tvora a kdo právě přišel nebo odešel.

   Přírůstky a odchody se dějí samy — úlovek od dětí, doplněk z katalogu, tvor,
   který ustoupil úlovku — a bez výpisu se nedá poznat, co scéna zrovna udělala.
   Jméno je to z odeslané fotky; u tvorů z katalogu žádné není, tak je tam "-".

   Klávesa i lištu skryje. */

const EVENTS = 5;                        // kolik posledních záznamů nechat

let bar = null;
let tally = null;
let feed = null;
const events = [];

export function init() {
  bar = document.getElementById('roster');
  tally = document.getElementById('tally');
  feed = document.getElementById('feed');
}

export function toggle() {
  if (bar) bar.style.display = bar.style.display === 'none' ? '' : 'none';
}

/** Kolik je čeho ve scéně; přepisuje se při každé změně obsazení. */
export function cast(actors) {
  if (!tally) return;
  const count = new Map();
  for (const a of actors) count.set(a.label, (count.get(a.label) || 0) + 1);
  const parts = [...count.entries()]
    .sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0], 'cs'))
    .map(([label, n]) => `${n}× ${label}`);
  tally.textContent = `${actors.length} ${plural(actors.length)}`
                    + (parts.length ? ' · ' + parts.join(' · ') : '');
}

function plural(n) {
  if (n === 1) return 'tvor';
  return n >= 2 && n <= 4 ? 'tvorové' : 'tvorů';
}

/** Přišel (`in`) nebo odešel (`out`) tvor daného typu a jména; `note` je
    obecný záznam bez tvora (např. „stanice vyprázdněna“) — bere jen `label`. */
export function event(kind, label, who) {
  if (!feed) return;
  const time = new Date().toLocaleTimeString('cs-CZ');
  const text = kind === 'note' ? label : `${label} · ${who || '-'}`;
  events.unshift({ kind, text, time });
  events.length = Math.min(events.length, EVENTS);
  feed.replaceChildren(...events.map((e, i) => {
    const item = document.createElement('span');
    item.className = 'ev ' + e.kind;
    item.style.opacity = 1 - i * 0.17;    // starší záznamy blednou dozadu
    const prefix = e.kind === 'in' ? '+' : e.kind === 'out' ? '−' : '•';
    item.textContent = `${prefix} ${e.text}`;
    item.title = e.time;
    return item;
  }));
}
