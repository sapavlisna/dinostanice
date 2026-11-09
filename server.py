"""DinoStanice server: photo in, animated creature out.

Runs the capture pipeline for an uploaded photo -- find the sheet, turn the
colours into a texture for the creature's 3D model -- and tells every connected
scene about the new arrival over a WebSocket.
"""

import asyncio
import io
import json
import logging
import os
import random
import re
import socket
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import (FastAPI, File, Form, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from dinostanice import (auth, capture, capture3d, paths, quality, scenes,
                         stations, store)
from dinostanice.capture import CaptureError
from dinostanice.creatures3d import BY_KEY as BY_KEY3D
from dinostanice.creatures3d import BY_MARKER as BY_MARKER3D
from dinostanice.creatures3d import CATALOGUE as CATALOGUE3D
from dinostanice.scenes import DEFAULT_SCENE

RES_ROOT = paths.resource_root()
WEB_DIR = os.path.join(RES_ROOT, "web")
MODELS3D_DIR = os.path.join(RES_ROOT, "data", "models3d")
TEMPLATES_DIR = os.path.join(RES_ROOT, "data", "templates")
# state.json je jen zdroj pro migraci domaci stanice (dinostanice.stations)
STATE_PATH = os.path.join(paths.data_root(), "state.json")
STATIONS_PATH = stations.default_path()

MAX_UPLOAD = 25 * 1024 * 1024
MAX_BODY = MAX_UPLOAD + 1024 * 1024   # rezerva na multipart obálku okolo fotky
MAX_PIXELS = 40_000_000  # rozumny strop; nad tim uz jde o dekompresni bombu, ne fotku
MAX_ASPECT = 4.0         # bezny telefon foti 4:3 az 16:9; extremni pomer neni list
MAX_CONCURRENT = 2       # exponat obsluhuje jedno dite po druhem, fronta je spravne
MAX_SIDE = 4000          # detection gains nothing above this, but the warp costs a lot
MIN_SIDE = 400

# --- Stanice a sessions ---------------------------------------------------
# Stanice (dinostanice.stations) = trvaly zaznam: krajina, ambient, `stay`.
# Session = jeji zivy stav v pameti: pripojene televize a mobily, posledni
# aktivita, spanek, posledni krmeni. Session vznika jen ke stanici, ktera
# v registru je.
DEFAULT_SESSION = stations.HOME
IDLE_SLEEP_S = 15 * 60   # bez skenu QR / uploadu takhle dlouho scena usne
IDLE_WARN_S = 13 * 60    # 2 minuty pred usnutim bezi na TV odpocet
IDLE_TICK_S = 10         # jak casto background task sessions kontroluje
SESSION_TTL_S = 2 * 3600  # session bez klientu a aktivity se zahodi z pameti
FEED_COOLDOWN_S = 10   # krmeni z mobilu: max 1x za tolik sekund per stanice
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dinostanice")

cv2.setNumThreads(2)     # kazdy bezici pipeline krok si jinak bere vsechna jadra

os.makedirs(WEB_DIR, exist_ok=True)
os.makedirs(MODELS3D_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
store.ensure_root()
_leftover = store.purge_deleted()
if _leftover:
    log.warning("po startu zbylo %d nedomazaných úlovků (*.deleted)", _leftover)

PROCESS_SEM = asyncio.Semaphore(MAX_CONCURRENT)

class RevalidatedFiles(StaticFiles):
    """Skripty, styly a modely: prohlizec si je smi drzet, ale pred pouzitim
    se zepta (ETag -> 304). Bez toho televize po nasazeni klidne hodiny bezi
    se starym modulem vedle nove stranky."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app = FastAPI(title="DinoStanice")
app.mount("/catch", StaticFiles(directory=store.CATCH_ROOT), name="catch")
app.mount("/web", RevalidatedFiles(directory=WEB_DIR), name="web")
app.mount("/models3d", RevalidatedFiles(directory=MODELS3D_DIR), name="models3d")
app.mount("/templates", RevalidatedFiles(directory=TEMPLATES_DIR), name="templates")

# Registr stanic a strazce kodu se zakladaji az pri prvnim pouziti, ne pri
# importu: testy si cesty presmeruji do tmp_path a import nesmi sahat na
# skutecna data.
registry = None
admins = None


def get_registry():
    global registry
    if registry is None:
        registry = stations.Registry(STATIONS_PATH, legacy_state=STATE_PATH)
    return registry


def get_admins():
    global admins
    if admins is None:
        admins = auth.Admins(auth.load_code(log))
    return admins


def current_admin(request):
    """Prihlaseny spravce z cookie, nebo None."""
    return get_admins().from_cookie(request.cookies.get(auth.COOKIE))


def may_manage(admin, st):
    return admin is not None and (admin.main or st.owner == admin.id)


def managed_station(request, raw_sid):
    """(stanice, None) kdyz ji prihlaseny spravce smi ovladat, jinak
    (None, chybova odpoved). Cizi stanice vypada jako neexistujici."""
    admin = current_admin(request)
    if admin is None:
        return None, forbidden()
    st = station_or_none(raw_sid)
    if st is None or not may_manage(admin, st):
        return None, gone()
    return st, None


def forbidden():
    return JSONResponse({"ok": False, "error": "tohle smí jen správce stanice — "
                                               "přihlas se kódem v adminu"},
                        status_code=403)


def gone():
    return JSONResponse({"ok": False, "error": "tahle stanice neběží — požádej "
                                               "dospělého o nový QR kód"},
                        status_code=404)


def clean_session(raw):
    """Prazdne id = domaci stanice (stary QR bez `?s=`)."""
    raw = (raw or "").strip().lower()
    return raw or DEFAULT_SESSION


def station_or_none(raw):
    sid = clean_session(raw)
    if not stations.SID_RE.match(sid):
        return None
    return get_registry().get(sid)


@dataclass
class Session:
    id: str
    clients: set = field(default_factory=set)
    last_seen: float = field(default_factory=time.monotonic)
    sleeping: bool = False
    last_feed: float = 0.0   # rate-limit krmeni (bod 11)


class Hub:
    """Klienti a broadcast per stanice, plus televize cekajici na sparovani."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.pairing: dict[str, set] = {}     # parovaci kod -> WS televizi
        self.lock = asyncio.Lock()

    def session(self, sid):
        s = self.sessions.get(sid)
        if s is None:
            s = self.sessions[sid] = Session(sid)
        return s

    async def add(self, sid, ws):
        async with self.lock:
            self.session(sid).clients.add(ws)

    async def drop(self, sid, ws):
        async with self.lock:
            s = self.sessions.get(sid)
            if s:
                s.clients.discard(ws)

    async def broadcast(self, sid, message):
        # Paralelne a s timeoutem: televize v suspendu drzi half-open TCP a
        # seriove `await send_json` by povesilo odpoved na upload.
        async with self.lock:
            s = self.sessions.get(sid)
            targets = list(s.clients) if s else []
        await self._send(targets, message, lambda ws: self.drop(sid, ws))

    async def notify_pair(self, code, message):
        async with self.lock:
            targets = list(self.pairing.pop(code, ()))
        await self._send(targets, message, None)

    async def _send(self, targets, message, on_fail):
        if not targets:
            return
        results = await asyncio.gather(
            *[asyncio.wait_for(ws.send_json(message), timeout=2.0) for ws in targets],
            return_exceptions=True)
        for ws, res in zip(targets, results):
            if isinstance(res, BaseException):
                log.warning("zprava klientovi selhala (%s), odpojuji ho",
                            type(res).__name__)
                if on_fail:
                    await on_fail(ws)


hub = Hub()


async def touch_session(sid):
    """Aktivita ve stanici: sken QR (otevreni /pridat), uspesny upload, krmeni,
    nebo explicitni touch z mobilu. Spici scenu probudi."""
    s = hub.session(sid)
    s.last_seen = time.monotonic()
    if s.sleeping:
        s.sleeping = False
        await hub.broadcast(sid, {"type": "wake"})
        log.info("stanice %s probuzena", sid)
    return s


async def idle_tick(now=None):
    """Jeden pruchod hlidace necinnosti; vyclenene z idle_loop() kvuli testum.

    Uspani NENI mazani: ulovky na disku zustavaji netknute, scena jen ztmavne
    a ceka na sken QR. Sessions bez klientu a bez aktivity > SESSION_TTL_S se
    zahodi jen z pameti; stanice v registru zustava."""
    now = time.monotonic() if now is None else now
    for sid, s in list(hub.sessions.items()):
        idle = now - s.last_seen
        if not s.clients and idle > SESSION_TTL_S:
            del hub.sessions[sid]
            log.info("session %s zahozena z pameti (bez klientu %d min)",
                     sid, int(idle / 60))
            continue
        st = get_registry().get(sid)
        if st is None or st.stay or s.sleeping:
            continue
        if idle >= IDLE_SLEEP_S:
            s.sleeping = True
            await hub.broadcast(sid, {"type": "sleep"})
            log.info("stanice %s usnula (bez aktivity %d min)", sid, int(idle / 60))
        elif idle >= IDLE_WARN_S:
            # posila se kazdy tick — odpocet na TV se prubezne srovnava se serverem
            await hub.broadcast(
                sid, {"type": "idle", "seconds_left": int(IDLE_SLEEP_S - idle)})


async def idle_loop():
    while True:
        await asyncio.sleep(IDLE_TICK_S)
        try:
            await idle_tick()
        except Exception:
            log.exception("hlidac necinnosti selhal, jede dal")


@app.on_event("startup")
async def _start_idle_watch():
    get_registry()
    get_admins()
    app.state.idle_task = asyncio.create_task(idle_loop())


@app.on_event("shutdown")
async def _stop_idle_watch():
    task = getattr(app.state, "idle_task", None)
    if task:
        task.cancel()


async def _json_body(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Odmítne obří upload podle Content-Length dřív, než Starlette začne
    multipart sypat do temp souboru — parser sám žádný limit na soubor nemá."""
    if request.method == "POST" and request.url.path == "/api/upload":
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(
                {"ok": False, "error": "nahrávání bez udané velikosti nebereme — "
                                       "zkus fotku poslat znovu"},
                status_code=413)
        try:
            too_big = int(length) > MAX_BODY
        except ValueError:
            too_big = True
        if too_big:
            return JSONResponse(
                {"ok": False, "error": "fotka je moc velká (max 25 MB)"},
                status_code=413)
    return await call_next(request)


IN_CONTAINER = os.path.exists("/.dockerenv")
PUBLIC_HOST = os.environ.get("DINO_HOST", "").strip()


def lan_ip():
    """Address other devices on the LAN can reach us on. No packet is actually sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def decode_photo(data):
    """Bytes -> BGR array, with the phone's EXIF rotation already applied."""
    too_many_px = ("fotka má příliš vysoké rozlišení — vyfoť list znovu, nebo pošli "
                   "fotku v menší velikosti")
    bgr = None
    try:
        img = Image.open(io.BytesIO(data))
        # rozmery zna uz hlavicka; kontrola PRED convert(), aby dekompresni
        # bomba nikdy nedosla k plne alokaci
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise CaptureError(too_many_px)
        img = ImageOps.exif_transpose(img)
        bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    except CaptureError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        # nesmi propadnout do cv2 fallbacku — imdecode zadny limit nema
        raise CaptureError(too_many_px)
    except UnidentifiedImageError:
        # format, ktery PIL nezna; cv2 jich umi vic
        raw = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if raw is not None:
            bgr = raw
    except Exception:
        bgr = None
    if bgr is None or bgr.size == 0:
        raise CaptureError("soubor se nepodařilo přečíst jako obrázek — pošli běžnou "
                           "fotku ve formátu JPEG nebo PNG")

    h, w = bgr.shape[:2]
    if max(h, w) < MIN_SIDE:
        raise CaptureError("fotka je moc malá, značky v rozích nejdou rozpoznat")
    if max(h, w) > MAX_ASPECT * min(h, w):
        raise CaptureError("fotka má nezvyklý poměr stran — na fotce nejspíš není "
                           "celý list, vyfoť ho znovu")
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        bgr = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                         interpolation=cv2.INTER_AREA)
    return bgr


def clean_name(name):
    name = "".join(ch for ch in (name or "") if ch.isprintable()).strip()
    return name[:40]


class ForeignCreature(Exception):
    """Vyfoceny tvor patri do jine krajiny, nez jaka na stanici bezi."""

    def __init__(self, spec):
        super().__init__(spec.key)
        self.spec = spec


def _process_model_sheet(spec, warped, markers, data, name, session, owner=""):
    """Vyfoceny list: staci prenest barvy na kuzi, kostru uz model ma."""
    shape = capture3d.load_shape(spec.key)
    coverage = capture3d.ink_coverage(warped, shape)

    catch_id, out_dir = store.new_catch(spec.key)
    try:
        capture3d.save_catch(out_dir, warped, shape, spec, name or spec.label)
        photo = store.save_photo(catch_id, data)
        meta = store.write_meta(catch_id, creature=spec.key, label=spec.label,
                                motion=spec.motion, name=name, coverage=coverage,
                                markers=markers, photo=photo, session=session,
                                owner=owner)
    except Exception:
        store.delete_catch(catch_id)
        raise
    meta["extras"] = _process_extras(shape, warped, markers, name, session, owner)
    return meta


def _process_extras(shape, warped, markers, name, session, owner):
    """Vybarvena okenka doplnku (ptacek, motylek) v rohu listu jsou samostatne
    ulovky. Nevybarvene se neukladaji; kdyz nektery selze, hlavni zvire
    zustane — doplnek je navic."""
    out = []
    try:
        found = capture3d.extra_sheets(warped, shape)
    except Exception:
        log.exception("okenka doplňků se nepodařilo přečíst")
        return out
    for item in found:
        if item["coverage"] < capture3d.EXTRA_MIN_COVERAGE:
            continue
        espec = BY_KEY3D[item["key"]]
        eid, edir = store.new_catch(espec.key)
        try:
            capture3d.save_extra_catch(edir, item["sheet"], item["shape"], espec,
                                       name or espec.label)
            out.append(store.write_meta(eid, creature=espec.key, label=espec.label,
                                        motion=espec.motion, name=name,
                                        coverage=item["coverage"], markers=markers,
                                        session=session, owner=owner))
        except Exception:
            log.exception("doplněk %s se nepodařilo uložit", espec.key)
            store.delete_catch(eid)
    return out


def _capture_advice(bgr, err):
    """Když se list nenajde, řekni dítěti, co s fotkou udělat jinak.

    quality.assess nikdy nevyhazuje; capture_failed je jen obecné „nepovedlo
    se" bez rady navíc, takže když nic konkrétnějšího nenajde, zůstane
    původní hláška z capture.
    """
    report = quality.assess(bgr)
    advice = [a for i, a in zip(report.issues, report.advice) if i != "capture_failed"]
    if not advice:
        return str(err)
    log.info("rada z quality: issues=%s", report.issues)
    return "; ".join(advice)


def process(data, name, session=DEFAULT_SESSION, accept=None, owner=""):
    """The whole pipeline. Blocking — never call this straight from the event loop.

    `accept` = sada tvoru, kterou stanice prijima; tvor odjinud vyhodi
    ForeignCreature jeste pred ulozenim."""
    started = time.perf_counter()
    bgr = decode_photo(data)

    try:
        creature_index, warped, markers = capture.detect_sheet(bgr)
    except CaptureError as e:
        raise CaptureError(_capture_advice(bgr, e)) from e

    spec = BY_MARKER3D[creature_index]
    if accept is not None and spec.scene != accept:
        raise ForeignCreature(spec)
    meta = _process_model_sheet(spec, warped, markers, data, name, session, owner)
    meta["took_ms"] = int((time.perf_counter() - started) * 1000)
    return meta


def _page(filename, missing_message):
    path = os.path.join(WEB_DIR, filename)
    if not os.path.exists(path):
        return HTMLResponse(f"<!doctype html><meta charset='utf-8'>"
                            f"<body style='background:#14181d;color:#e6edf3;"
                            f"font:16px sans-serif;padding:2rem'>{missing_message}</body>",
                            status_code=503)
    # Bez toho si prohlizec drzi starou stranku: HTML nema zadny validator a po
    # prestavbe pak nacita skripty, ktere uz jinam patri (a scena zustane prazdna).
    return FileResponse(path, media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/")
def admin_page():
    """Hlavni stranka = sprava: prihlaseni, moje stanice, odkazy pro televize."""
    return _page("admin.html", "Správa stanice zatím není nasazená.")


@app.get("/tv")
def tv_pair_page():
    """Televize bez odkazu: ukaze parovaci kod (nebo posledni stanici)."""
    return _page("scene.html", "Scéna zatím není nasazená.")


@app.get("/tv/{token}")
def tv_page(token: str):
    return _page("scene.html", "Scéna zatím není nasazená.")


@app.post("/api/clientlog")
async def api_clientlog(request: Request):
    """Diagnostika prohlizecu televizi: chyby a fps, ktere jinak nikdo nevidi."""
    body = (await request.body())[:4000].decode("utf-8", "replace")
    log.info("clientlog %s | %s", request.headers.get("user-agent", "?"), body)
    return {"ok": True}


@app.get("/api/tv/{token}")
def api_tv(token: str):
    """Tajny odkaz televize -> stanice. Jen tudy se scena ke stanici dostane."""
    st = get_registry().by_tv(token)
    if st is None:
        return gone()
    return {"s": st.id, "scene": st.scene}


@app.get("/pridat")
async def upload_page(s: str = ""):
    # sken QR = aktivita ve stanici (a budicek pro spici scenu)
    st = station_or_none(s)
    if st is not None:
        await touch_session(st.id)
    return _page("upload.html", "Stránka pro přidání zatím není nasazená.")


@app.get("/malovat")
async def paint_page(s: str = ""):
    st = station_or_none(s)
    if st is not None:
        await touch_session(st.id)
    return _page("malovat.html", "Malování zatím není nasazené.")


@app.get("/dino3d")
def dino3d_page():
    return _page("dino3d.html", "Model z předlohy zatím není nasazený.")


@app.get("/sablony")
def sheets_page():
    return _page("sablony.html", "Přehled šablon zatím není nasazený.")


@app.get("/admin")
@app.get("/rezim")
def old_admin_page():
    # stare zalozky a odkazy vedou sem
    return RedirectResponse("/", status_code=307)


# --- Spravci: prihlaseni ---------------------------------------------------

@app.post("/api/login")
async def api_login(request: Request):
    body = await _json_body(request)
    ip = request.client.host if request.client else "?"
    reg = get_admins()
    if reg.throttled(ip):
        return JSONResponse({"ok": False, "error": "moc pokusů — zkus to za minutu"},
                            status_code=429)
    admin = reg.login(ip, body.get("code"))
    if admin is None:
        log.warning("špatný kód správce z %s", ip)
        return JSONResponse({"ok": False, "error": "tenhle kód neplatí"}, status_code=403)
    log.info("přihlášen správce %s (%s) z %s", admin.id, admin.name, ip)
    resp = JSONResponse({"ok": True, **admin.public()})
    resp.set_cookie(auth.COOKIE, reg.token(admin), max_age=auth.COOKIE_MAX_AGE,
                    httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/me")
def api_me(request: Request):
    admin = current_admin(request)
    if admin is None:
        return {"admin": False}
    return {"admin": True, **admin.public()}


# --- Spravci: sprava (jen hlavni) -------------------------------------------

def _main_only(request):
    admin = current_admin(request)
    if admin is None or not admin.main:
        return forbidden()
    return None


def _admin_info(a):
    owned = [st for st in get_registry().items.values() if st.owner == a.id]
    return {**a.public(), "stations": len(owned)}


@app.get("/api/admins")
def api_admins(request: Request):
    if (err := _main_only(request)):
        return err
    items = sorted(get_admins().items.values(), key=lambda a: (not a.main, a.created))
    return [_admin_info(a) for a in items]


@app.post("/api/admins")
async def api_admin_create(request: Request):
    if (err := _main_only(request)):
        return err
    body = await _json_body(request)
    admin, code = get_admins().create(body.get("name"))
    log.info("nový správce %s (%s)", admin.id, admin.name)
    return {"ok": True, **_admin_info(admin), "code": code}


@app.post("/api/admins/{aid}/code")
def api_admin_new_code(request: Request, aid: str):
    if (err := _main_only(request)):
        return err
    reg = get_admins()
    if aid not in reg.items:
        return JSONResponse({"ok": False, "error": "takový správce není"}, status_code=404)
    if aid == auth.MAIN_ID:
        return JSONResponse({"ok": False, "error": "kód hlavního správce se mění "
                                                   "v .env (DINO_ADMIN_CODE)"},
                            status_code=400)
    code = reg.reset_code(aid)
    log.info("správce %s dostal nový kód", aid)
    return {"ok": True, "code": code}


@app.delete("/api/admins/{aid}")
def api_admin_delete(request: Request, aid: str):
    """Zrusi spravce; jeho stanice nezmizi, prevezme je hlavni spravce."""
    if (err := _main_only(request)):
        return err
    reg = get_admins()
    if not reg.remove(aid):
        return JSONResponse({"ok": False, "error": "tohoto správce zrušit nejde"},
                            status_code=400)
    moved = 0
    for st in list(get_registry().items.values()):
        if st.owner == aid:
            get_registry().update(st.id, owner=auth.MAIN_ID)
            moved += 1
    log.info("správce %s zrušen, %d stanic převzal hlavní", aid, moved)
    return {"ok": True, "moved": moved}


# --- Stanice -----------------------------------------------------------------

def _station_info(st, with_owner=False):
    sess = hub.sessions.get(st.id)
    info = {"s": st.id, "scene": st.scene, "ambient": st.ambient, "stay": st.stay,
            "created": st.created, "home": st.id == DEFAULT_SESSION,
            "tv": f"/tv/{st.tv}",
            "screens": len(sess.clients) if sess else 0,
            "sleeping": bool(sess and sess.sleeping),
            "catches": len(store.list_catches(session=st.id))}
    if with_owner:
        owner = get_admins().items.get(st.owner)
        info["owner"] = st.owner
        info["ownerName"] = owner.name if owner else "?"
    return info


@app.get("/api/stations")
def api_stations(request: Request):
    admin = current_admin(request)
    if admin is None:
        return forbidden()
    items = sorted((st for st in get_registry().items.values() if may_manage(admin, st)),
                   key=lambda st: (st.owner != admin.id, st.id != DEFAULT_SESSION,
                                   -st.created))
    return [_station_info(st, with_owner=admin.main) for st in items]


@app.post("/api/stations")
async def api_station_create(request: Request):
    admin = current_admin(request)
    if admin is None:
        return forbidden()
    body = await _json_body(request)
    st = get_registry().create(body.get("scene"), owner=admin.id)
    log.info("založena stanice %s (%s) správcem %s", st.id, st.scene, admin.id)
    return {"ok": True, **_station_info(st)}


@app.delete("/api/stations/{sid}")
async def api_station_delete(request: Request, sid: str):
    """Ukonci stanici: jeji ulovky jdou do kose, televize se vrati na parovani,
    mobily s jejim QR dostanou „stanice nebezi"."""
    st, err = managed_station(request, sid)
    if err:
        return err
    if st.id == DEFAULT_SESSION:
        return JSONResponse({"ok": False, "error": "domácí stanici ukončit nejde, "
                                                   "jen vyprázdnit"}, status_code=400)
    deleted = await _clear_catches(st.id)
    get_registry().remove(st.id)
    await hub.broadcast(st.id, {"type": "ended"})
    hub.sessions.pop(st.id, None)
    log.info("stanice %s ukončena (%d úlovků do koše)", st.id, deleted)
    return {"ok": True, "deleted": deleted}


@app.post("/api/pair")
def api_pair_new():
    """Televize bez odkazu si vyzada kratky kod; spravce ho opise."""
    code = get_registry().new_pair_code()
    return {"code": code, "ttl": stations.PAIR_TTL_S}


@app.post("/api/pair/{code}")
async def api_pair(request: Request, code: str):
    """Spravce sparuje televizi ukazujici `code` se svou stanici (`s`), nebo
    s novou. Televize dostane tajny odkaz a dal uz kod nepotrebuje."""
    admin = current_admin(request)
    if admin is None:
        return forbidden()
    code = auth.normalize(code)
    reg = get_registry()
    body = await _json_body(request)
    st = None
    if body.get("s"):
        st, err = managed_station(request, body["s"])
        if err:
            return err
    if not reg.take_pair(code):
        return JSONResponse({"ok": False, "error": "tenhle kód televize neukazuje "
                                                   "(nebo už vypršel)"}, status_code=404)
    if st is None:
        st = reg.create(body.get("scene"), owner=admin.id)
        log.info("založena stanice %s (%s) pro televizi s kódem %s", st.id, st.scene, code)
    await hub.notify_pair(code, {"type": "paired", "s": st.id, "tv": st.tv})
    return {"ok": True, **_station_info(st)}


# --- Sablony, katalog, sceny ---------------------------------------------

@app.get("/api/templates")
def api_templates(scene: str = ""):
    """Předlohy vygenerované z 3D modelů.

    Jde se výhradně přes katalog, ne přes obsah adresáře: tvor bez záznamu
    v katalogu nemá index značky, takže by ho vyfocený list neidentifikoval
    a nabízet takovou předlohu k tisku by byla past. `scene` (klíč scény nebo
    sady) zúží výběr na tvory, které ta scéna přijme; `scene` v odpovědi je
    sada tvorů, podle které se předlohy třídí.
    """
    accept = None
    if scene:
        sc = scenes.BY_KEY.get(scene)
        accept = sc.catalogue if sc else scene
    out = []
    for spec in CATALOGUE3D:
        if spec.extra or (accept is not None and spec.scene != accept):
            continue
        name = f"{spec.key}.svg"
        if os.path.exists(os.path.join(TEMPLATES_DIR, name)):
            out.append({"key": spec.key, "label": spec.label, "motion": spec.motion,
                        "scene": spec.scene, "template": f"/templates/{name}"})
    return JSONResponse(sorted(out, key=lambda e: e["label"]))


@app.get("/api/dino3d")
def api_dino3d(scene: str = ""):
    """Katalog tvorů postavených z hotových 3D modelů.

    `scene` filtruje na sadu tvorů (klíč katalogu, Model3D.scene); bez
    parametru jde všechno — prohlížečka /dino3d ukazuje celý katalog."""
    path = os.path.join(MODELS3D_DIR, "catalogue3d.json")
    if not os.path.exists(path):
        return JSONResponse([], status_code=200)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if scene:
        data = [e for e in data if e.get("scene", DEFAULT_SCENE) == scene]
    return JSONResponse(data)


def _catch_scene(meta):
    """Do ktere sady tvoru (Scene.catalogue) ulovek patri."""
    spec = BY_KEY3D.get(meta.get("creature"))
    return spec.scene if spec is not None else DEFAULT_SCENE


def _accepts(st):
    return scenes.BY_KEY[scenes.clean_scene(st.scene)].catalogue


@app.get("/api/scenes")
def api_scenes():
    """Registr scén: jméno, popis, `catalogue` (kterou sadu tvorů scéna
    přijímá) a texty pro děti. Pořadí = pořadí karet v adminu."""
    return [sc.public() for sc in scenes.SCENES]


@app.get("/scenes/{key}/render.js")
def scene_render(key: str):
    """Vykreslení scény. Jen přes registr — ze složek scén se jinak nic
    nevydává (leží v nich i zdrojové modely a poznámky)."""
    if key not in scenes.BY_KEY:
        return Response(status_code=404)
    return FileResponse(os.path.join(scenes.SCENES_DIR, key, "render.js"),
                        media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/scene/active")
def api_scene_active(s: str = ""):
    st = station_or_none(s)
    if st is None:
        return gone()
    return {"s": st.id, "scene": st.scene}


@app.post("/api/scene/active")
async def api_scene_active_set(request: Request):
    body = await _json_body(request)
    st, err = managed_station(request, body.get("s"))
    if err:
        return err
    key = body.get("scene")
    if key not in scenes.BY_KEY:
        return JSONResponse({"ok": False, "error": "taková krajina tu není"},
                            status_code=400)
    get_registry().update(st.id, scene=key)
    log.info("stanice %s přepnuta na krajinu %s", st.id, key)
    await hub.broadcast(st.id, {"type": "scene", "scene": key})
    return {"ok": True, "s": st.id, "scene": key}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


def _keep_rejected(data, reason):
    try:
        store.save_rejected(data, reason)
    except OSError:
        log.exception("odmítnutou fotku se nepodařilo uložit")


@app.post("/api/upload")
async def api_upload(photo: UploadFile = File(...), name: str = Form(""),
                     s: str = Form(""), device: str = Form("")):
    st = station_or_none(s)
    if st is None:
        return gone()
    sid = st.id
    owner = device if DEVICE_RE.match(device or "") else ""
    data = await photo.read(MAX_UPLOAD + 1)
    if not data:
        return JSONResponse({"ok": False, "error": "fotka nedorazila, zkus to znovu"},
                            status_code=400)
    if len(data) > MAX_UPLOAD:
        return JSONResponse({"ok": False, "error": "fotka je moc velká (max 25 MB)"},
                            status_code=413)

    accept = _accepts(st)
    try:
        async with PROCESS_SEM:
            meta = await run_in_threadpool(process, data, clean_name(name), sid,
                                           accept, owner)
    except ForeignCreature as e:
        # Zvire z jine krajiny se neuklada: dite by ho na televizi nevidelo
        # a nevedelo proc. Fotka neni vadna, do rejected nepatri.
        sc = scenes.BY_KEY[scenes.clean_scene(st.scene)]
        log.info("stanice %s: %s nepatří do krajiny %s — odmítnuto",
                 sid, e.spec.key, st.scene)
        allowed = [m.label for m in CATALOGUE3D if m.scene == accept]
        return JSONResponse(
            {"ok": False, "foreign": True, "allowed": allowed,
             "error": f"{e.spec.label} sem nepatří — na televizi teď běží "
                      f"{sc.label}. Vybarvi si někoho odsud!"},
            status_code=409)
    except CaptureError as e:
        log.warning("upload odmítnut: %s", e)
        _keep_rejected(data, str(e))
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        log.exception("zpracování fotky selhalo")
        _keep_rejected(data, type(e).__name__)
        return JSONResponse(
            {"ok": False, "error": f"zpracování fotky selhalo ({type(e).__name__})"},
            status_code=500)

    log.info("úlovek %s: %s stanice=%s markers=%s coverage=%.3f took_ms=%s",
             meta["id"], meta["creature"], sid,
             meta.get("markers"), meta.get("coverage", 0.0), meta.get("took_ms"))
    await touch_session(sid)     # uspesny upload = aktivita (a budicek)
    for m in [meta, *meta.get("extras", [])]:
        await hub.broadcast(sid, {"type": "add", "url": m["url"], "id": m["id"],
                                  "label": m["label"], "name": m["name"],
                                  "creature": m["creature"]})
    return {"ok": True, **meta}


@app.get("/api/rigs")
def api_rigs(s: str = "", scene: str = "", mine: str = ""):
    """Ulovky stanice. `scene` zuzi na ulovky patrici te krajine (scena po
    prepnuti nenacita cizi), `mine` na ulovky jednoho mobilu."""
    st = station_or_none(s)
    if st is None:
        return gone()
    out = store.list_catches(session=st.id)
    if scene:
        sc = scenes.BY_KEY.get(scene)
        accept = sc.catalogue if sc else scene
        out = [m for m in out if _catch_scene(m) == accept]
    if mine:
        out = [m for m in out if m.get("owner") and m.get("owner") == mine]
    return out


@app.get("/api/mine")
def api_mine(s: str = "", device: str = ""):
    """Vsechna zvirata jednoho mobilu napric stanicemi i archivem — kazdy
    obrazek jednou. `here` = uz bezi na teto televizi, `fits` = patri do
    jeji krajiny (jen takove jde poslat znovu)."""
    st = station_or_none(s)
    if st is None:
        return gone()
    if not DEVICE_RE.match(device or ""):
        return []
    accept = _accepts(st)
    live = [m for m in store.list_catches() if m.get("owner") == device]
    by_origin = {}
    # prednost ma kopie na teto televizi, jinak ta nejnovejsi
    on_tv = lambda m: not m.get("archived") and m.get("session") == st.id
    rank = lambda m: (on_tv(m), m.get("created", ""))
    for m in store.list_archive(owner=device) + live:
        o = store.origin_of(m)
        if o not in by_origin or rank(m) >= rank(by_origin[o]):
            by_origin[o] = m
    out = [{**m, "here": on_tv(m), "fits": _catch_scene(m) == accept}
           for m in by_origin.values()]
    out.sort(key=lambda m: m.get("created", ""), reverse=True)
    return out


@app.post("/api/mine/send")
async def api_mine_send(request: Request):
    """Poslat svoje starsi zvire znovu na televizi."""
    body = await _json_body(request)
    st = station_or_none(body.get("s"))
    if st is None:
        return gone()
    device = body.get("device") or ""
    try:
        meta, _ = store.find_catch(body.get("id") or "")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if not meta or not DEVICE_RE.match(device) or meta.get("owner") != device:
        return JSONResponse({"ok": False, "error": "tohle zvíře tu není"},
                            status_code=404)
    if _catch_scene(meta) != _accepts(st):
        sc = scenes.BY_KEY[scenes.clean_scene(st.scene)]
        return JSONResponse({"ok": False, "error": f"{meta['label']} sem nepatří — "
                                                   f"na televizi teď běží {sc.label}."},
                            status_code=409)
    origin = store.origin_of(meta)
    if any(store.origin_of(m) == origin for m in store.list_catches(session=st.id)):
        return JSONResponse({"ok": False, "error": "tohle zvíře už na televizi je"},
                            status_code=409)
    new = await run_in_threadpool(store.resend_catch, meta["id"], st.id)
    if new is None:
        return JSONResponse({"ok": False, "error": "zvíře se nepodařilo poslat, "
                                                   "zkus to znovu"}, status_code=500)
    log.info("úlovek %s poslán znovu jako %s do stanice %s", meta["id"], new["id"], st.id)
    await touch_session(st.id)
    await hub.broadcast(st.id, {"type": "add", "url": new["url"], "id": new["id"],
                                "label": new["label"], "name": new["name"],
                                "creature": new["creature"]})
    return {"ok": True, **new}


@app.delete("/api/rigs/{catch_id}")
async def api_delete(request: Request, catch_id: str, device: str = ""):
    """Smazat smi admin, nebo mobil, ktery ulovek poslal. Mobil zvire z televize
    jen odebere do archivu (pujde poslat znovu); z archivu ho smaze nadobro."""
    try:
        meta, archived = store.find_catch(catch_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if not meta:
        return JSONResponse({"ok": False, "error": "takový úlovek tu není"},
                            status_code=404)
    own = bool(device) and meta.get("owner") == device
    st = station_or_none(meta.get("session"))
    if archived:
        if not own:
            return JSONResponse({"ok": False, "error": "smazat můžeš jen svoje zvíře"},
                                status_code=403)
        store.trash_archived(catch_id)
        log.info("úlovek %s smazán z archivu vlastníkem", catch_id)
        return {"ok": True, "id": catch_id}
    if not (own or (st is not None and may_manage(current_admin(request), st))):
        return JSONResponse({"ok": False, "error": "smazat můžeš jen svoje zvíře"},
                            status_code=403)
    try:
        removed = (store.archive_catch(catch_id) if own
                   else store.delete_catch(catch_id))
    except OSError:
        log.exception("odstavení úlovku %s selhalo", catch_id)
        return JSONResponse({"ok": False, "error": "úlovek se nepodařilo smazat, "
                                                   "zkus to za chvíli"},
                            status_code=500)
    if not removed:
        return JSONResponse({"ok": False, "error": "takový úlovek tu není"},
                            status_code=404)
    sid = clean_session(meta.get("session"))
    log.info("úlovek %s smazán (stanice %s, %s)", catch_id, sid,
             "vlastníkem" if own else "správcem")
    await hub.broadcast(sid, {"type": "remove", "id": catch_id})
    leftover = await run_in_threadpool(store.purge_deleted)
    if leftover:
        log.warning("%d odstavených úlovků drží otevřené soubory, dočistí se po startu",
                    leftover)
    return {"ok": True, "id": catch_id}


@app.get("/api/scene/settings")
def api_scene_settings(s: str = ""):
    st = station_or_none(s)
    if st is None:
        return gone()
    return {"ambient": st.ambient, "stay": st.stay, "scene": st.scene}


@app.post("/api/scene/settings")
async def api_scene_settings_set(request: Request):
    """Nastaveni jedne stanice: `ambient` (ukazkovi tvorove z katalogu)
    a `stay` (neusinat)."""
    body = await _json_body(request)
    st, err = managed_station(request, body.get("s"))
    if err:
        return err
    fields = {k: bool(body[k]) for k in ("ambient", "stay") if k in body}
    st = get_registry().update(st.id, **fields)
    log.info("stanice %s: nastavení %s", st.id, fields)
    await hub.broadcast(st.id, {"type": "settings", "ambient": st.ambient})
    return {"ambient": st.ambient, "stay": st.stay, "scene": st.scene}


async def _clear_catches(sid):
    deleted = 0
    for meta in store.list_catches(session=sid):
        # zvire ditete z televize mizi, ale mobil ho muze poslat znovu
        done = (store.archive_catch(meta["id"]) if meta.get("owner")
                else store.delete_catch(meta["id"]))
        if done:
            deleted += 1
    leftover = await run_in_threadpool(store.purge_deleted)
    if leftover:
        log.warning("%d odstavených úlovků drží otevřené soubory, dočistí se po startu",
                    leftover)
    return deleted


@app.post("/api/scene/reset")
async def api_scene_reset(request: Request, s: str = ""):
    """Vyprázdní stanici: smaže úlovky JEN dané stanice (ambientní doplňky
    z katalogu v `data/catch` nejsou, tak se jich to netýká) a pošle jedinou
    zprávu scéně, ať si nespustí topUp() N-krát za sebou."""
    st, err = managed_station(request, s)
    if err:
        return err
    deleted = await _clear_catches(st.id)
    log.info("stanice %s vyprázdněna: smazáno %d úlovků", st.id, deleted)
    await hub.broadcast(st.id, {"type": "cleared"})
    return {"ok": True, "deleted": deleted}


@app.post("/api/feed")
async def api_feed(request: Request):
    """Krmeni z mobilu (bod 11): shodi do sceny kus zelene, chodci v okoli
    k nemu zamiri. Rate-limit per stanice, at deti scenu nezasypou."""
    body = await _json_body(request)
    st = station_or_none(body.get("s"))
    if st is None:
        return gone()
    sess = hub.session(st.id)
    now = time.monotonic()
    if now - sess.last_feed < FEED_COOLDOWN_S:
        sc = scenes.BY_KEY[scenes.clean_scene(st.scene)]
        return JSONResponse({"ok": False, "error": sc.feedBusy}, status_code=429)
    sess.last_feed = now
    await touch_session(st.id)   # krmeni je aktivita (a budicek pro spici scenu)
    x = round(random.uniform(0.25, 0.75), 3)
    await hub.broadcast(st.id, {"type": "feed", "x": x})
    log.info("stanice %s: hozeno žrádlo na x=%.3f", st.id, x)
    return {"ok": True, "x": x}


@app.post("/api/session/touch")
async def api_session_touch(request: Request):
    """Explicitni „ještě chvíli" z mobilu (a budicek pro spici scenu)."""
    body = await _json_body(request)
    st = station_or_none(body.get("s"))
    if st is None:
        return gone()
    sess = await touch_session(st.id)
    return {"ok": True, "s": sess.id, "sleeping": sess.sleeping}


@app.get("/api/session/{sid}")
def api_session_state(sid: str):
    """Stav session pro ladeni a testy; nic nevytvari ani neprodluzuje."""
    sess = hub.sessions.get(clean_session(sid))
    st = station_or_none(sid)
    if sess is None or st is None:
        return JSONResponse({"ok": False, "error": "session neexistuje"},
                            status_code=404)
    return {"ok": True, "id": sess.id, "sleeping": sess.sleeping,
            "scene": st.scene, "clients": len(sess.clients),
            "idle_s": round(time.monotonic() - sess.last_seen, 3)}


def public_base(request):
    port = request.url.port or int(os.environ.get("DINO_PORT", 0)) or 80
    # Point the phone at whatever address the scene itself is being viewed on:
    # over Tailscale or any other tunnel, our LAN address is unreachable.
    host = request.url.hostname or ""
    if host in ("", "localhost", "127.0.0.1", "::1"):
        # v kontejneru je lan_ip() adresa dockerove site (172.x), ktera mobilu
        # nerekne nic — tam musi adresu hostitele dodat DINO_HOST
        host = PUBLIC_HOST or ("" if IN_CONTAINER else lan_ip()) or host
    return f"http://{host}:{port}"


@app.get("/api/qr")
def api_qr(request: Request, s: str = ""):
    """QR pro deti: vede jen na /pridat dane stanice (foceni, zradlo)."""
    st = station_or_none(s)
    if st is None:
        return gone()
    target = f"{public_base(request)}/pridat?s={st.id}"
    img = qrcode.make(target, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"X-Upload-Url": target, "Cache-Control": "no-store"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    pair = auth.normalize(ws.query_params.get("pair"))
    if pair:
        await _ws_pairing(ws, pair)
        return
    st = station_or_none(ws.query_params.get("s"))
    if st is None:
        try:
            await ws.send_json({"type": "ended"})
            await ws.close(code=4404)
        except Exception:
            pass
        return
    sid = st.id
    await hub.add(sid, ws)
    # reconnect do spici session nesmi scenu probudit do plneho svetla —
    # klient se hned dozvi, ze se spi (budi jen sken QR / touch)
    if hub.session(sid).sleeping:
        try:
            await ws.send_json({"type": "sleep"})
        except Exception:
            pass
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.drop(sid, ws)


async def _ws_pairing(ws, code):
    """Televize ceka na sparovani: az admin kod potvrdi, dostane `paired`."""
    if not get_registry().pair_valid(code):
        try:
            await ws.send_json({"type": "pair_expired"})
            await ws.close()
        except Exception:
            pass
        return
    async with hub.lock:
        hub.pairing.setdefault(code, set()).add(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        async with hub.lock:
            waiting = hub.pairing.get(code)
            if waiting:
                waiting.discard(ws)
                if not waiting:
                    hub.pairing.pop(code, None)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DINO_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
