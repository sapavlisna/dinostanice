"""DinoStanice server: photo in, animated creature out.

Runs the capture -> rig pipeline for an uploaded photo and tells every connected
scene about the new arrival over a WebSocket.
"""

import asyncio
import io
import json
import os
import socket
import time

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps
from fastapi import (FastAPI, File, Form, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from dinostanice import capture, capture3d, modelsheet, rig, store
from dinostanice.capture import CaptureError
from dinostanice.creatures import BY_KEY, CATALOGUE
from dinostanice.creatures3d import CATALOGUE as CATALOGUE3D

BY_MARKER3D = {m.marker_index: m for m in CATALOGUE3D}
from dinostanice.raster import outline_contours
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
MODELS3D_DIR = os.path.join(ROOT, "data", "models3d")
TEMPLATES_DIR = os.path.join(ROOT, "data", "templates")
SHAPES3D_DIR = os.path.join(ROOT, "data", "shapes3d")

MAX_UPLOAD = 25 * 1024 * 1024
MAX_SIDE = 4000          # detection gains nothing above this, but the warp costs a lot
MIN_SIDE = 400
TRIM_MM = 0.6            # pull the cut inside the printed outline so the black line is gone

os.makedirs(WEB_DIR, exist_ok=True)
os.makedirs(MODELS3D_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
store.ensure_root()

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
        async with self.lock:
            targets = list(self.clients)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.drop(ws)


hub = Hub()


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
    bgr = None
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception:
        raw = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if raw is not None:
            bgr = raw
    if bgr is None or bgr.size == 0:
        raise CaptureError("soubor se nepodařilo přečíst jako obrázek — pošli běžnou "
                           "fotku ve formátu JPEG nebo PNG")

    h, w = bgr.shape[:2]
    if max(h, w) < MIN_SIDE:
        raise CaptureError("fotka je moc malá, značky v rozích nejdou rozpoznat")
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
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


def process(data, name):
    """The whole pipeline. Blocking — never call this straight from the event loop."""
    started = time.perf_counter()
    bgr = decode_photo(data)

    creature_index, warped, markers = capture.detect_sheet(bgr)

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


@app.get("/3d")
def model3d_page():
    return _page("model3d.html", "3D náhled zatím není nasazený.")


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


@app.get("/api/models3d")
def api_models3d():
    """Creature keys that already have a baked 3D model.

    catalogue3d.json is the index of the model-built creatures, not a model —
    listing it here would offer the old viewer a key it cannot load.
    """
    return sorted(f[:-5] for f in os.listdir(MODELS3D_DIR)
                  if f.endswith(".json") and f != "catalogue3d.json")


@app.get("/api/template-texture/{key}.png")
def api_template_texture(key: str):
    """A blank sheet, so a model can be looked at before anyone colours one in."""
    creature = BY_KEY.get(key)
    if creature is None:
        return JSONResponse({"ok": False, "error": "neznámý tvor"}, status_code=404)
    ppm = 5.0
    img = np.full((int(SHEET_H_MM * ppm), int(SHEET_W_MM * ppm), 3), 246, np.uint8)
    for c in outline_contours(creature, ppm=ppm):
        cv2.polylines(img, [np.round(c * ppm).astype(np.int32)], True, (60, 60, 60),
                      max(1, int(round(0.9 * ppm))), cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    return Response(buf.tobytes(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


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
        meta = await run_in_threadpool(process, data, clean_name(name))
    except CaptureError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"zpracování fotky selhalo ({type(e).__name__})"},
            status_code=500)

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
    if not removed:
        return JSONResponse({"ok": False, "error": "takový úlovek tu není"},
                            status_code=404)
    await hub.broadcast({"type": "remove", "id": catch_id})
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
