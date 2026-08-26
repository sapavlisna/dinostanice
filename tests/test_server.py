"""End-to-end testy serveru pres FastAPI TestClient.

Zadny bezici server ani Docker neni potreba; fotky jsou synteticke
(dinostanice.synth.photograph nad rucne vybarvenym listem z 3D katalogu).
Ulozene ulovky jdou do tmp_path — store se parametrizuje monkeypatchem
CATCH_ROOT/REJECTED_ROOT, vsechny funkce store je ctou az za behu.
"""

import json
import struct
import zlib
from functools import lru_cache

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import server
from dinostanice import modelsheet, store, synth
from dinostanice.markers import CORNER_ORIGINS, MARKER_MM, marker_bits, marker_ids
from dinostanice.shapes import SHEET_H_MM, SHEET_W_MM

PPM = 6.0
TREX_INDEX = 8  # trex3d v creatures3d.CATALOGUE


@pytest.fixture
def client(monkeypatch, tmp_path):
    catch_root = tmp_path / "catch"
    rejected_root = tmp_path / "rejected"
    monkeypatch.setattr(store, "CATCH_ROOT", str(catch_root))
    monkeypatch.setattr(store, "REJECTED_ROOT", str(rejected_root))
    with TestClient(server.app) as c:
        yield c


def _draw_markers(img, creature_index, ppm):
    for corner, mid in enumerate(marker_ids(creature_index)):
        ox, oy = CORNER_ORIGINS[corner]
        bits = marker_bits(mid)
        cell = MARKER_MM / bits.shape[0]
        for r in range(bits.shape[0]):
            for c in range(bits.shape[1]):
                if bits[r, c]:
                    x0 = int(round((ox + c * cell) * ppm))
                    y0 = int(round((oy + r * cell) * ppm))
                    x1 = int(round((ox + (c + 1) * cell) * ppm)) - 1
                    y1 = int(round((oy + (r + 1) * cell) * ppm)) - 1
                    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 0), -1)


@lru_cache(maxsize=1)
def model_photo_jpg():
    """Vybarveny trex3d list vyfoceny simulovanym telefonem, jako JPEG bytes."""
    shape = modelsheet.load(server.os.path.join(server.SHAPES3D_DIR, "trex3d.json"))
    W, H = int(SHEET_W_MM * PPM), int(SHEET_H_MM * PPM)
    sheet = np.full((H, W, 3), 255, np.uint8)
    body = np.zeros((H, W), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * PPM).astype(np.int32)], 1)
    sheet[body > 0] = (70, 170, 90)
    for poly in shape.outline:
        cv2.polylines(sheet, [np.round(poly * PPM).astype(np.int32)], True,
                      (20, 20, 20), 3, cv2.LINE_AA)
    _draw_markers(sheet, TREX_INDEX, PPM)
    photo = synth.photograph(sheet, seed=3)
    ok, enc = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert ok
    return enc.tobytes()


def blank_photo_jpg():
    """Fotka bez listu: sedy papirovy sum, zadne znacky."""
    rng = np.random.default_rng(11)
    img = np.clip(rng.normal(185, 8, (1512, 2016, 3)), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", img)
    assert ok
    return enc.tobytes()


def png_with_header(w, h):
    """Minimalni PNG, ktere v hlavicce tvrdi w x h — telo je prazdne.

    Staci na Image.open().size; kdyby server zkusil plne dekodovani,
    alokoval by w*h*3 bajtu, cemuz ma pixel budget zabranit.
    """
    def chunk(typ, payload):
        return (struct.pack(">I", len(payload)) + typ + payload
                + struct.pack(">I", zlib.crc32(typ + payload)))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", b"") + chunk(b"IEND", b""))


def upload(client, data, filename="photo.jpg", name="Test"):
    return client.post("/api/upload",
                       files={"photo": (filename, data, "image/jpeg")},
                       data={"name": name})


def test_upload_model_catch(client):
    r = upload(client, model_photo_jpg(), name="Kubík")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["kind"] == "model"
    assert body["creature"] == "trex3d"
    assert body["id"].startswith("trex3d-")

    catch = store.catch_dir(body["id"])
    for fname in ("texture.png", "model.json", "meta.json"):
        assert server.os.path.exists(server.os.path.join(catch, fname)), fname

    rigs = client.get("/api/rigs").json()
    assert [m["id"] for m in rigs] == [body["id"]]
    assert rigs[0]["name"] == "Kubík"


def test_upload_blank_photo_rejected(client):
    r = upload(client, blank_photo_jpg())
    assert r.status_code == 400
    err = r.json()["error"]
    assert err and any(ch in err for ch in "áéěíóřšůž"), err
    # odmitnuta fotka se schovava do data/rejected (tady tmp)
    rejected = list(server.os.scandir(store.REJECTED_ROOT))
    assert len(rejected) == 1
    # a nic se nezapsalo mezi ulovky
    assert client.get("/api/rigs").json() == []


def test_upload_blurry_photo_gets_concrete_advice(client):
    """Odmítnutí neříká jen „nejsou vidět značky" — quality poradí, co s fotkou."""
    bgr = cv2.imdecode(np.frombuffer(model_photo_jpg(), np.uint8), cv2.IMREAD_COLOR)
    ok, enc = cv2.imencode(".jpg", cv2.GaussianBlur(bgr, (0, 0), 15))
    assert ok
    r = upload(client, enc.tobytes(), filename="blur.jpg")
    assert r.status_code == 400
    assert "rozmazan" in r.json()["error"], r.json()["error"]


def test_upload_too_far_photo_advises_moving_closer(client):
    bgr = cv2.imdecode(np.frombuffer(model_photo_jpg(), np.uint8), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, (w // 6, h // 6), interpolation=cv2.INTER_AREA)
    canvas = np.full((h, w, 3), 175, np.uint8)
    y0, x0 = (h - small.shape[0]) // 2, (w - small.shape[1]) // 2
    canvas[y0:y0 + small.shape[0], x0:x0 + small.shape[1]] = small
    ok, enc = cv2.imencode(".jpg", canvas)
    assert ok
    r = upload(client, enc.tobytes(), filename="far.jpg")
    assert r.status_code == 400
    assert "přibliž telefon" in r.json()["error"], r.json()["error"]


def test_upload_unreadable_file(client):
    r = upload(client, b"tohle rozhodne neni obrazek", filename="x.jpg")
    assert r.status_code == 400
    assert "obrázek" in r.json()["error"]


def test_upload_missing_content_length(client):
    r = client.post("/api/upload", content=iter([b"x"]),
                    headers={"Content-Type": "multipart/form-data; boundary=q"})
    assert r.status_code == 413
    assert "velikost" in r.json()["error"]


def test_upload_huge_content_length(client):
    r = client.post("/api/upload", content=b"",
                    headers={"Content-Length": str(200 * 1024 * 1024),
                             "Content-Type": "multipart/form-data; boundary=q"})
    assert r.status_code == 413
    assert "moc velká" in r.json()["error"]


def test_upload_pixel_bomb_header(client):
    # 9000x9000 = 81 Mpx: pod limitem PIL, nad nasim budgetem
    r = upload(client, png_with_header(9000, 9000), filename="bomb.png")
    assert r.status_code == 400
    assert "rozlišení" in r.json()["error"]


def test_upload_decompression_bomb(client):
    # 30000x30000 = 900 Mpx: tohle uz zabiji primo PIL bomb-limit;
    # nesmi propadnout do cv2 fallbacku bez limitu
    r = upload(client, png_with_header(30000, 30000), filename="bomb.png")
    assert r.status_code == 400
    assert "rozlišení" in r.json()["error"]


def test_upload_extreme_aspect(client):
    img = np.full((100, 2000, 3), 190, np.uint8)
    ok, enc = cv2.imencode(".png", img)
    assert ok
    r = upload(client, enc.tobytes(), filename="pano.png")
    assert r.status_code == 400
    assert "celý list" in r.json()["error"]


def test_delete_catch(client):
    catch_id = upload(client, model_photo_jpg()).json()["id"]

    r = client.delete(f"/api/rigs/{catch_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": catch_id}
    assert client.get("/api/rigs").json() == []
    # adresar je pryc, nebo aspon odstaveny mimo ID_RE
    assert not server.os.path.isdir(store.catch_dir(catch_id))

    assert client.delete(f"/api/rigs/{catch_id}").status_code == 404
    assert client.delete("/api/rigs/trex3d-ffff").status_code == 404
    assert client.delete("/api/rigs/Spatne.Id").status_code == 400


def test_purge_deleted_cleans_leftovers(client):
    store.ensure_root()
    leftover = server.os.path.join(store.CATCH_ROOT, "trex3d-dead.deleted")
    server.os.makedirs(leftover)
    assert store.purge_deleted() == 0
    assert not server.os.path.isdir(leftover)


def test_ws_add_and_remove(client):
    with client.websocket_connect("/ws") as ws:
        catch_id = upload(client, model_photo_jpg()).json()["id"]
        msg = ws.receive_json()
        assert msg["type"] == "add"
        assert msg["id"] == catch_id
        assert msg["kind"] == "model"

        assert client.delete(f"/api/rigs/{catch_id}").status_code == 200
        msg = ws.receive_json()
        assert msg == {"type": "remove", "id": catch_id}


def test_scene_settings_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE_PATH", str(tmp_path / "state.json"))

    # bez souboru je vychozi ambient zapnuty
    assert client.get("/api/scene/settings").json() == {"ambient": True}

    r = client.post("/api/scene/settings", json={"ambient": False})
    assert r.status_code == 200
    assert r.json()["ambient"] is False

    # perzistuje pres dalsi cteni i primo na disku
    assert client.get("/api/scene/settings").json()["ambient"] is False
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved == {"ambient": False}

    r = client.post("/api/scene/settings", json={"ambient": True})
    assert r.json()["ambient"] is True
    assert client.get("/api/scene/settings").json()["ambient"] is True


def test_scene_settings_broadcasts(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE_PATH", str(tmp_path / "state.json"))
    with client.websocket_connect("/ws") as ws:
        client.post("/api/scene/settings", json={"ambient": False})
        msg = ws.receive_json()
        assert msg == {"type": "settings", "ambient": False}


def test_scene_reset_clears_catches_and_broadcasts(client):
    catch_id = upload(client, model_photo_jpg()).json()["id"]
    assert len(client.get("/api/rigs").json()) == 1

    with client.websocket_connect("/ws") as ws:
        r = client.post("/api/scene/reset")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "deleted": 1}
        msg = ws.receive_json()
        assert msg == {"type": "cleared"}

    assert client.get("/api/rigs").json() == []
    assert not server.os.path.isdir(store.catch_dir(catch_id))


def test_scene_reset_with_nothing_to_delete(client):
    r = client.post("/api/scene/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deleted": 0}


def test_rezim_page(client):
    r = client.get("/rezim")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
