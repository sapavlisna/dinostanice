"""End-to-end testy serveru pres FastAPI TestClient.

Zadny bezici server ani Docker neni potreba; fotky jsou synteticke
(tests/helpers.py vybarvi predlohu z katalogu, synth.photograph ji vyfoti).
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

import helpers as H
import server
from dinostanice import store, synth

PPM = 6.0


@pytest.fixture
def client(monkeypatch, tmp_path):
    catch_root = tmp_path / "catch"
    rejected_root = tmp_path / "rejected"
    monkeypatch.setattr(store, "CATCH_ROOT", str(catch_root))
    monkeypatch.setattr(store, "REJECTED_ROOT", str(rejected_root))
    monkeypatch.setattr(store, "TRASH_ROOT", str(tmp_path / "trash"))
    server.hub.sessions.clear()   # sessions z minulych testu nesmi prosakovat
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def fast_idle_client(monkeypatch, tmp_path):
    """Jako client, ale s milisekundovymi casy uspavani — konstanty se musi
    zkratit PRED startem TestClienta, background task cte IDLE_TICK_S az
    v behu smycky."""
    monkeypatch.setattr(store, "CATCH_ROOT", str(tmp_path / "catch"))
    monkeypatch.setattr(store, "REJECTED_ROOT", str(tmp_path / "rejected"))
    monkeypatch.setattr(store, "TRASH_ROOT", str(tmp_path / "trash"))
    monkeypatch.setattr(server, "IDLE_WARN_S", 0.15)
    monkeypatch.setattr(server, "IDLE_SLEEP_S", 0.5)
    monkeypatch.setattr(server, "IDLE_TICK_S", 0.03)
    server.hub.sessions.clear()
    with TestClient(server.app) as c:
        yield c


@lru_cache(maxsize=1)
def model_photo_jpg():
    """Vybarveny trex3d list vyfoceny simulovanym telefonem, jako JPEG bytes."""
    sheet = H.sheet("trex3d", seed=3, ppm=PPM, strokes=40)
    photo = synth.photograph(sheet.img, seed=3)
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


def upload(client, data, filename="photo.jpg", name="Test", s=None):
    form = {"name": name}
    if s is not None:
        form["s"] = s
    return client.post("/api/upload",
                       files={"photo": (filename, data, "image/jpeg")},
                       data=form)


def test_upload_model_catch(client):
    r = upload(client, model_photo_jpg(), name="Kubík")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
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
    # neodešel do nenávratna, ale do koše
    binned = [e.name for e in server.os.scandir(store.TRASH_ROOT)]
    assert any(name.startswith("trex3d-dead-") for name in binned)


def test_ws_add_and_remove(client):
    with client.websocket_connect("/ws") as ws:
        catch_id = upload(client, model_photo_jpg()).json()["id"]
        msg = ws.receive_json()
        assert msg["type"] == "add"
        assert msg["id"] == catch_id

        assert client.delete(f"/api/rigs/{catch_id}").status_code == 200
        msg = ws.receive_json()
        assert msg == {"type": "remove", "id": catch_id}


def test_scene_settings_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE_PATH", str(tmp_path / "state.json"))

    # bez souboru je vychozi ambient zapnuty (a krajina default)
    assert client.get("/api/scene/settings").json() == {
        "ambient": True, "scene": "cretaceous"}

    r = client.post("/api/scene/settings", json={"ambient": False})
    assert r.status_code == 200
    assert r.json()["ambient"] is False

    # perzistuje pres dalsi cteni i primo na disku
    assert client.get("/api/scene/settings").json()["ambient"] is False
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["ambient"] is False

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


# --- Sessions (bod 6) ----------------------------------------------------

def test_sessions_rigs_isolated(client):
    body = upload(client, model_photo_jpg(), s="aaa").json()
    assert body["ok"] is True
    assert body["session"] == "aaa"

    ids = lambda r: [m["id"] for m in r.json()]
    assert ids(client.get("/api/rigs?s=aaa")) == [body["id"]]
    assert ids(client.get("/api/rigs?s=bbb")) == []
    # default "tv" cizi ulovek nevidi — a naopak
    assert ids(client.get("/api/rigs")) == []

    tv = upload(client, model_photo_jpg()).json()
    assert tv["session"] == "tv"
    assert ids(client.get("/api/rigs")) == [tv["id"]]
    assert ids(client.get("/api/rigs?s=aaa")) == [body["id"]]


def test_old_meta_without_session_counts_as_default(client):
    catch_id = upload(client, model_photo_jpg()).json()["id"]
    path = server.os.path.join(store.catch_dir(catch_id), "meta.json")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    del meta["session"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    assert [m["id"] for m in client.get("/api/rigs").json()] == [catch_id]
    assert client.get("/api/rigs?s=aaa").json() == []


def test_sessions_ws_routing(client):
    with client.websocket_connect("/ws?s=aaa") as ws_a, \
         client.websocket_connect("/ws?s=bbb") as ws_b:
        id_a = upload(client, model_photo_jpg(), s="aaa").json()["id"]
        id_b = upload(client, model_photo_jpg(), s="bbb").json()["id"]
        # kazdy klient dostane JEN svuj prirustek: prvni zprava B je jeho
        # vlastni add, nikoli add z A (ktery vznikl driv)
        msg_a = ws_a.receive_json()
        assert (msg_a["type"], msg_a["id"]) == ("add", id_a)
        msg_b = ws_b.receive_json()
        assert (msg_b["type"], msg_b["id"]) == ("add", id_b)

        # remove jde do session ulovku, ne vsem
        assert client.delete(f"/api/rigs/{id_b}").status_code == 200
        assert ws_b.receive_json() == {"type": "remove", "id": id_b}
        assert client.delete(f"/api/rigs/{id_a}").status_code == 200
        assert ws_a.receive_json() == {"type": "remove", "id": id_a}


def test_qr_carries_session(client):
    r = client.get("/api/qr?s=abc")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "s=abc" in r.headers["X-Upload-Url"]
    # bez parametru zustava hole /pridat — QR domaci televize se nemeni
    assert "s=" not in client.get("/api/qr").headers["X-Upload-Url"]
    # neplatne id spadne do defaultu, zadna chyba
    assert "s=" not in client.get("/api/qr?s=..%2F..").headers["X-Upload-Url"]


def test_reset_scoped_to_session(client):
    id_a = upload(client, model_photo_jpg(), s="aaa").json()["id"]
    id_b = upload(client, model_photo_jpg(), s="bbb").json()["id"]

    with client.websocket_connect("/ws?s=aaa") as ws_a:
        r = client.post("/api/scene/reset?s=aaa")
        assert r.json() == {"ok": True, "deleted": 1}
        assert ws_a.receive_json() == {"type": "cleared"}

    assert client.get("/api/rigs?s=aaa").json() == []
    assert [m["id"] for m in client.get("/api/rigs?s=bbb").json()] == [id_b]
    assert server.os.path.isdir(store.catch_dir(id_b))
    assert not server.os.path.isdir(store.catch_dir(id_a))


def test_session_touch_and_state(client):
    # touch session zalozi a nastavi last_seen
    r = client.post("/api/session/touch", json={"s": "abc"})
    assert r.json() == {"ok": True, "s": "abc", "sleeping": False}
    assert "abc" in server.hub.sessions
    before = server.hub.sessions["abc"].last_seen

    state = client.get("/api/session/abc").json()
    assert state["ok"] is True and state["sleeping"] is False
    assert state["idle_s"] < 5

    server.hub.sessions["abc"].last_seen -= 100
    client.post("/api/session/touch", json={"s": "abc"})
    assert server.hub.sessions["abc"].last_seen >= before

    assert client.get("/api/session/neni").status_code == 404


def test_pridat_with_session_touches(client):
    assert "kid7" not in server.hub.sessions
    assert client.get("/pridat?s=kid7").status_code == 200
    assert "kid7" in server.hub.sessions
    # bez parametru se nic nezaklada (default nikdy nespi)
    n = len(server.hub.sessions)
    client.get("/pridat")
    assert len(server.hub.sessions) == n


def test_idle_tick_logic(monkeypatch):
    """Deterministicka cast hlidace: prah varovani/uspani, vyjimka pro default
    "tv", zahazovani opustenych sessions z pameti. Cerstvy Hub, zadny server."""
    import asyncio

    monkeypatch.setattr(server, "hub", server.Hub())
    now = 1_000_000.0
    hub = server.hub
    # hluboko za prahem uspani, ale pod TTL — uklid pameti je jina vec
    hub.session("tv").last_seen = now - (server.SESSION_TTL_S - 10)
    hub.session("kid").last_seen = now - server.IDLE_SLEEP_S - 1
    hub.session("fresh").last_seen = now - 1
    hub.session("gone").last_seen = now - server.SESSION_TTL_S - 1

    async def run():
        # jeden bh smycky: tick uspava/zahazuje, touch pak budi (v jednom
        # event loopu — asyncio.Lock hubu nesmi mezi loopy)
        await server.idle_tick(now=now)
        assert "gone" not in hub.sessions      # opustena session zmizela z pameti
        assert hub.sessions["kid"].sleeping is True
        assert hub.sessions["fresh"].sleeping is False
        # default "tv" se NEUSPAVA, at je necinna jakkoli dlouho
        assert hub.sessions["tv"].sleeping is False
        await server.touch_session("kid")      # touch spici session probudi
        assert hub.sessions["kid"].sleeping is False

    asyncio.run(run())


def test_idle_sleep_wake_over_ws(fast_idle_client):
    """Cely obeh pres bezici background task: idle odpocet -> sleep -> touch
    -> wake. Casy jsou milisekundove (fixture je zkracuje pred startem)."""
    client = fast_idle_client
    with client.websocket_connect("/ws?s=nap1") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "idle"
        assert 0 <= msg["seconds_left"] <= server.IDLE_SLEEP_S

        # idle chodi kazdy tick, nez prijde sleep
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "sleep":
                break
            assert msg["type"] == "idle"
        assert msg["type"] == "sleep"
        assert client.get("/api/session/nap1").json()["sleeping"] is True

        r = client.post("/api/session/touch", json={"s": "nap1"})
        assert r.json()["sleeping"] is False
        msg = ws.receive_json()
        assert msg == {"type": "wake"}
        assert client.get("/api/session/nap1").json()["sleeping"] is False


def test_sleeping_session_greets_new_client_with_sleep(client):
    server.hub.session("zzz").sleeping = True
    with client.websocket_connect("/ws?s=zzz") as ws:
        assert ws.receive_json() == {"type": "sleep"}


# --- Více scén (bod 8) ----------------------------------------------------

def test_api_scenes_registry(client):
    scenes = client.get("/api/scenes").json()
    keys = [s["key"] for s in scenes]
    assert "cretaceous" in keys and "cretaceous_night" in keys
    for s in scenes:
        assert s["label"] and s["subtitle"] and s["catalogue"]
    # obe varianty laguny sdili touz sadu tvoru
    by_key = {s["key"]: s for s in scenes}
    assert by_key["cretaceous_night"]["catalogue"] == "cretaceous"


def test_dino3d_scene_filter(client):
    everything = client.get("/api/dino3d").json()
    cretaceous = client.get("/api/dino3d?scene=cretaceous").json()
    aquarium = client.get("/api/dino3d?scene=aquarium").json()
    # filtr musi katalog opravdu rozdelit, ne vratit vsechno
    assert 0 < len(cretaceous) < len(everything)
    assert 0 < len(aquarium) < len(everything)
    assert len(cretaceous) + len(aquarium) == len(everything)
    assert all(m["scene"] == "cretaceous" for m in cretaceous)
    assert all(m["scene"] == "aquarium" and m["motion"] == "swim" for m in aquarium)
    assert client.get("/api/dino3d?scene=neexistuje").json() == []


def test_scene_active_per_session(client):
    # neznama session vznika s defaultni krajinou
    assert client.get("/api/scene/active?s=xyz").json() == {
        "s": "xyz", "scene": "cretaceous"}

    with client.websocket_connect("/ws?s=xyz") as ws:
        r = client.post("/api/scene/active",
                        json={"scene": "cretaceous_night", "s": "xyz"})
        assert r.json() == {"ok": True, "s": "xyz", "scene": "cretaceous_night"}
        assert ws.receive_json() == {"type": "scene", "scene": "cretaceous_night"}

    assert client.get("/api/scene/active?s=xyz").json()["scene"] == "cretaceous_night"
    assert client.get("/api/session/xyz").json()["scene"] == "cretaceous_night"
    # jina session zustava na defaultu
    assert client.get("/api/scene/active?s=jina").json()["scene"] == "cretaceous"

    r = client.post("/api/scene/active", json={"scene": "atlantida", "s": "xyz"})
    assert r.status_code == 400
    assert "krajina" in r.json()["error"]


def test_default_scene_survives_restart(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE_PATH", str(tmp_path / "state.json"))
    r = client.post("/api/scene/active", json={"scene": "cretaceous_night"})
    assert r.json()["ok"] is True
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["scene"] == "cretaceous_night"

    # "restart": sessions z pameti zmizi, default si krajinu vezme ze state.json
    server.hub.sessions.clear()
    assert client.get("/api/scene/active").json()["scene"] == "cretaceous_night"


@pytest.fixture
def aquarium(monkeypatch):
    """Docasna scena s cizi sadou tvoru — trex do ni nepatri."""
    from dinostanice import scenes as scenes_mod
    fake = scenes_mod.Scene("aquarium", "Akvárium", "test", "aquarium")
    monkeypatch.setattr(scenes_mod, "SCENES", scenes_mod.SCENES + [fake])
    monkeypatch.setattr(scenes_mod, "BY_KEY",
                        {**scenes_mod.BY_KEY, "aquarium": fake})
    return fake


def test_upload_to_foreign_scene_saves_without_broadcast(client, aquarium):
    with client.websocket_connect("/ws?s=aaa") as ws:
        r = client.post("/api/scene/active", json={"scene": "aquarium", "s": "aaa"})
        assert r.json()["ok"] is True
        assert ws.receive_json() == {"type": "scene", "scene": "aquarium"}

        body = upload(client, model_photo_jpg(), s="aaa").json()
        assert body["ok"] is True
        # ulovek se ULOZIL, mobil dostal ceskou hlasku o jine krajine
        assert "Křídová laguna" in body["note"]
        assert server.os.path.isdir(store.catch_dir(body["id"]))

        # scena zadny `add` nedostala: dalsi zprava na WS je az tohle prepnuti
        client.post("/api/scene/active", json={"scene": "cretaceous", "s": "aaa"})
        assert ws.receive_json() == {"type": "scene", "scene": "cretaceous"}

    # rigs: bez filtru je videt, s filtrem patri jen do kridy
    ids = lambda r: [m["id"] for m in r.json()]
    assert ids(client.get("/api/rigs?s=aaa")) == [body["id"]]
    assert ids(client.get("/api/rigs?s=aaa&scene=aquarium")) == []
    assert ids(client.get("/api/rigs?s=aaa&scene=cretaceous")) == [body["id"]]
    # nocni laguna sdili sadu tvoru s denni, ulovek do ni patri taky
    assert ids(client.get("/api/rigs?s=aaa&scene=cretaceous_night")) == [body["id"]]


def test_upload_to_matching_scene_has_no_note(client):
    body = upload(client, model_photo_jpg()).json()
    assert body["ok"] is True
    assert "note" not in body


# --- Krmeni z mobilu (bod 11) ----------------------------------------------

def test_feed_broadcast_rate_limit_and_isolation(client):
    with client.websocket_connect("/ws?s=aaa") as ws_a, \
         client.websocket_connect("/ws?s=bbb") as ws_b:
        r = client.post("/api/feed", json={"s": "aaa"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        msg = ws_a.receive_json()
        assert msg["type"] == "feed"
        assert 0.25 <= msg["x"] <= 0.75
        assert msg["x"] == body["x"]

        # rate-limit: druhy hod hned po prvnim vraci 429 s ceskou hlaskou
        r2 = client.post("/api/feed", json={"s": "aaa"})
        assert r2.status_code == 429
        assert r2.json()["ok"] is False
        assert "žvýkají" in r2.json()["error"]

        # cizi session feed nedostala: prvni zprava na jejim WS je az jeji
        # vlastni hod (rate-limit je per session, aaa ho neblokuje)
        r3 = client.post("/api/feed", json={"s": "bbb"})
        assert r3.status_code == 200
        msg_b = ws_b.receive_json()
        assert msg_b["type"] == "feed"
        assert msg_b["x"] == r3.json()["x"]


def test_feed_cooldown_expires(client, monkeypatch):
    monkeypatch.setattr(server, "FEED_COOLDOWN_S", 0.05)
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 200
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 429
    import time as _time
    _time.sleep(0.06)
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 200
