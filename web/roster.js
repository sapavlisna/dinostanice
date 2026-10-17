/* Lišta dole: kolik zvířat je ve scéně a která to jsou.

   Vlevo celkový počet, za ním každé zvíře zvlášť — druh a jméno z odeslané
   fotky, u zvířat z katalogu "-". Nejnovější je vpředu, takže právě přidané
   zvíře dítě najde hned na začátku; víc zvířat = delší seznam (zalomí se).

   Klávesa i lištu skryje. */

let bar = null;
let tally = null;
let list = null;

export function init() {
  bar = document.getElementById('roster');
  tally = document.getElementById('tally');
  list = document.getElementById('feed');
}

export function toggle() {
  if (bar) bar.style.display = bar.style.display === 'none' ? '' : 'none';
}

/** Kdo je ve scéně; přepisuje se při každé změně obsazení. */
export function cast(actors) {
  if (!tally) return;
  tally.textContent = `${actors.length} ${plural(actors.length)}`;
  list.replaceChildren(...actors.slice().reverse().map((a) => {
    const item = document.createElement('span');
    item.className = a.ambient ? 'ev demo' : 'ev';
    item.textContent = `${a.label} · ${a.who || '-'}`;
    return item;
  }));
}

function plural(n) {
  if (n === 1) return 'zvíře';
  return n >= 2 && n <= 4 ? 'zvířata' : 'zvířat';
}
