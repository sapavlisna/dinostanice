/* Společné pomocníky mobilních stránek. Klasický skript (ne modul), aby šel
   načíst jednoduše před inline skriptem stránky. */
"use strict";

const $ = (id) => document.getElementById(id);

// Stanice z `?s=`; prázdné = domácí "tv" (starý QR bez parametru)
const SID = (new URLSearchParams(location.search).get("s") || "").toLowerCase();
const withS = (path, sid = SID) =>
  sid ? path + (path.includes("?") ? "&" : "?") + "s=" + encodeURIComponent(sid) : path;

/* fetch + JSON v jednom; vrací {ok, status, data}. Síťová chyba = status 0. */
async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body !== undefined ? "POST" : "GET") };
  if (opts.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  try {
    const res = await fetch(path, init);
    const data = await res.json().catch(() => null);
    return { ok: res.ok && !(data && data.ok === false), status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: null };
  }
}

function errorText(r, fallback) {
  if (r.status === 0) return "Nepodařilo se spojit se stanicí.";
  return (r.data && r.data.error) || fallback;
}

// tvary slova pro 1 / 2–4 / 5+
function plural(n, forms) {
  return forms[n === 1 ? 0 : (n >= 2 && n <= 4 ? 1 : 2)];
}

function setStatus(el, text, kind) {
  el.textContent = text || "";
  el.classList.toggle("ok", kind === "ok");
  el.classList.toggle("bad", kind === "bad");
}

let _scenes = null;
async function loadScenes() {
  if (!_scenes) {
    const r = await api("/api/scenes");
    _scenes = r.ok ? r.data : [];
  }
  return _scenes;
}

/* Náhodné id tohoto mobilu — podle něj smí dítě smazat svoje zvíře.
   Bez localStorage (anonymní okno) vydrží aspoň do zavření stránky. */
function deviceId() {
  const KEY = "dino.device";
  let id = null;
  try { id = localStorage.getItem(KEY); } catch (e) { /* bez úložiště */ }
  if (!id) {
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    id = "m" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    try { localStorage.setItem(KEY, id); } catch (e) { /* bez úložiště */ }
  }
  return id;
}

/* WebSocket s opakovaným připojením. `on(msg)` dostává zprávy, `state(live)`
   změny spojení. Vrací funkci, která spojení ukončí. */
function liveSocket(path, on, state) {
  let retry = 1000, stopped = false, ws = null;
  function connect() {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") +
                       location.host + path);
    ws.onopen = () => { retry = 1000; if (state) state(true); };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      on(msg);
    };
    ws.onclose = () => {
      if (state) state(false);
      if (stopped) return;
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 15000);
    };
  }
  connect();
  return () => { stopped = true; if (ws) ws.close(); };
}
