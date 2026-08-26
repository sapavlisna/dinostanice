"""DinoStanice server: photo in, animated creature out.

Runs the capture -> rig pipeline for an uploaded photo and tells every connected
scene about the new arrival over a WebSocket.
"""

import asyncio
import io
import json
import logging
import os
import socket
import time

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import (FastAPI, File, Form, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from dinostanice import capture, capture3d, modelsheet, quality, rig, store
from dinostanice.capture import CaptureError
from dinostanice.creatures import CATALOGUE
from dinostanice.creatures3d import CATALOGUE as CATALOGUE3D

BY_MARKER3D = {m.marker_index: m for m in CATALOGUE3D}

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
MODELS3D_DIR = os.path.join(ROOT, "data", "models3d")
TEMPLATES_DIR = os.path.join(ROOT, "data", "templates")
SHAPES3D_DIR = os.path.join(ROOT, "data", "shapes3d")

MAX_UPLOAD = 25 * 1024 * 1024
MAX_BODY = MAX_UPLOAD + 1024 * 1024   # rezerva na multipart obálku okolo fotky
MAX_PIXELS = 40_000_000  # rozumny strop; nad tim uz jde o dekompresni bombu, ne fotku
MAX_ASPECT = 4.0         # bezny telefon foti 4:3 az 16:9; extremni pomer neni list
MAX_CONCURRENT = 2       # exponat obsluhuje jedno dite po druhem, fronta je spravne
MAX_SIDE = 4000          # detection gains nothing above this, but the warp costs a lot
MIN_SIDE = 400
TRIM_MM = 0.6            # pull the cut inside the printed outline so the black line is gone

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

app = FastAPI(title="DinoStanice")
app.mount("/catch", StaticFiles(directory=store.CATCH_ROOT), name="catch")
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
app.mount("/models3d", StaticFiles(directory=MODELS3D_DIR), name="models3d")
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")


class Hub:
    def __init__(self):
        self.clients = set()
        self.lock = asyncio.Lock()

    async def add(self, ws):
        async with self.lock:
            self.clients.add(ws)

    async def drop(self, ws):
        async with self.lock:
            self.clients.discard(ws)

    async def broadcast(self, message):
        # Paralelne a s timeoutem: televize v suspendu drzi half-open TCP a
        # seriove `await send_json` by povesilo odpoved na upload.
        async with self.lock:
            targets = list(self.clients)
        if not targets:
            return
        results = await asyncio.gather(
            *[asyncio.wait_for(ws.send_json(message), timeout=2.0) for ws in targets],
            return_exceptions=True)
        for ws, res in zip(targets, results):
            if isinstance(res, BaseException):
                log.warning("broadcast klientovi selhal (%s), odpojuji ho",
                            type(res).__name__)
                await self.drop(ws)


hub = Hub()


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


def _process_model_sheet(spec, warped, markers, data, name):
    """List tvora postaveneho z 3D modelu: staci prenest barvy, rig uz existuje."""
    shape = modelsheet.load(os.path.join(SHAPES3D_DIR, f"{spec.key}.json"))
    coverage = capture3d.ink_coverage(warped, shape)

    catch_id, out_dir = store.new_catch(spec.key)
    try:
        capture3d.save_catch(out_dir, warped, shape, spec, name or spec.label)
        photo = store.save_photo(catch_id, data)
        return store.write_meta(catch_id, creature=spec.key, label=spec.label,
                                motion=spec.motion, name=name, coverage=coverage,
                                markers=markers, photo=photo, kind="model")
    except Exception:
        store.delete_catch(catch_id)
        raise


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


def process(data, name):
    """The whole pipeline. Blocking — never call this straight from the event loop."""
    started = time.perf_counter()
    bgr = decode_photo(data)

    try:
        creature_index, warped, markers = capture.detect_sheet(bgr)
    except CaptureError as e:
        raise CaptureError(_capture_advice(bgr, e)) from e

    spec = BY_MARKER3D.get(creature_index)
    if spec is not None:
        meta = _process_model_sheet(spec, warped, markers, data, name)
        meta["took_ms"] = int((time.perf_counter() - started) * 1000)
        return meta

    creature = CATALOGUE[creature_index]
    sheet = capture.sheet_texture(warped, creature, trim_mm=TRIM_MM)
    coverage = capture.ink_coverage(sheet)

    catch_id, out_dir = store.new_catch(creature.key)
    try:
        rig.build_rig(sheet, creature, out_dir, name or creature.label)
        photo = store.save_photo(catch_id, data)
        meta = store.write_meta(catch_id, creature=creature.key, label=creature.label,
                                motion=creature.motion, name=name, coverage=coverage,
                                markers=markers, photo=photo, kind="rig")
    except Exception:
        store.delete_catch(catch_id)
        raise

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
def scene_page():
    return _page("scene.html", "Scéna zatím není nasazená.")


@app.get("/pridat")
def upload_page():
    return _page("upload.html", "Stránka pro přidání zatím není nasazená.")


@app.get("/dino3d")
def dino3d_page():
    return _page("dino3d.html", "Model z předlohy zatím není nasazený.")


@app.get("/sablony")
def sheets_page():
    return _page("sablony.html", "Přehled šablon zatím není nasazený.")


@app.get("/api/templates")
def api_templates():
    """Předlohy vygenerované z 3D modelů.

    Jde se výhradně přes katalog, ne přes obsah adresáře: kdyby se stará větev
    někdy přegenerovala, do přehledu se stejně nedostane.
    """
    out = []
    for spec in CATALOGUE3D:
        name = f"{spec.key}.svg"
        if os.path.exists(os.path.join(TEMPLATES_DIR, name)):
            out.append({"key": spec.key, "label": spec.label,
                        "motion": spec.motion, "template": f"/templates/{name}"})
    return JSONResponse(sorted(out, key=lambda e: e["label"]))


@app.get("/api/dino3d")
def api_dino3d():
    """Katalog tvorů postavených z hotových 3D modelů."""
    path = os.path.join(MODELS3D_DIR, "catalogue3d.json")
    if not os.path.exists(path):
        return JSONResponse([], status_code=200)
    with open(path, encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


def _keep_rejected(data, reason):
    try:
        store.save_rejected(data, reason)
    except OSError:
        log.exception("odmítnutou fotku se nepodařilo uložit")


@app.post("/api/upload")
async def api_upload(photo: UploadFile = File(...), name: str = Form("")):
    data = await photo.read(MAX_UPLOAD + 1)
    if not data:
        return JSONResponse({"ok": False, "error": "fotka nedorazila, zkus to znovu"},
                            status_code=400)
    if len(data) > MAX_UPLOAD:
        return JSONResponse({"ok": False, "error": "fotka je moc velká (max 25 MB)"},
                            status_code=413)

    try:
        async with PROCESS_SEM:
            meta = await run_in_threadpool(process, data, clean_name(name))
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

    log.info("úlovek %s: %s kind=%s markers=%s coverage=%.3f took_ms=%s",
             meta["id"], meta["creature"], meta.get("kind"), meta.get("markers"),
             meta.get("coverage", 0.0), meta.get("took_ms"))
    await hub.broadcast({"type": "add", "url": meta["url"], "id": meta["id"],
                         "label": meta["label"], "name": meta["name"],
                         "creature": meta["creature"],
                         "kind": meta.get("kind", "rig")})
    return {"ok": True, **meta}


@app.get("/api/rigs")
def api_rigs():
    return store.list_catches()


@app.delete("/api/rigs/{catch_id}")
async def api_delete(catch_id: str):
    try:
        removed = store.delete_catch(catch_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except OSError:
        log.exception("odstavení úlovku %s selhalo", catch_id)
        return JSONResponse({"ok": False, "error": "úlovek se nepodařilo smazat, "
                                                   "zkus to za chvíli"},
                            status_code=500)
    if not removed:
        return JSONResponse({"ok": False, "error": "takový úlovek tu není"},
                            status_code=404)
    log.info("úlovek %s smazán", catch_id)
    await hub.broadcast({"type": "remove", "id": catch_id})
    leftover = await run_in_threadpool(store.purge_deleted)
    if leftover:
        log.warning("%d odstavených úlovků drží otevřené soubory, dočistí se po startu",
                    leftover)
    return {"ok": True, "id": catch_id}


@app.get("/api/qr")
def api_qr(request: Request):
    port = request.url.port or int(os.environ.get("DINO_PORT", 0)) or 80
    # Point the phone at whatever address the scene itself is being viewed on:
    # over Tailscale or any other tunnel, our LAN address is unreachable.
    host = request.url.hostname or ""
    if host in ("", "localhost", "127.0.0.1", "::1"):
        # v kontejneru je lan_ip() adresa dockerove site (172.x), ktera mobilu
        # nerekne nic — tam musi adresu hostitele dodat DINO_HOST
        host = PUBLIC_HOST or ("" if IN_CONTAINER else lan_ip()) or host
    target = f"http://{host}:{port}/pridat"
    img = qrcode.make(target, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"X-Upload-Url": target, "Cache-Control": "no-store"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await hub.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.drop(ws)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DINO_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
