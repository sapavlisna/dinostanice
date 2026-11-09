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
from dinostanice import auth, scenes, stations, store, synth

PPM = 6.0


ADMIN_CODE = "TEST42"
# stanice, se kterymi testy pracuji (krome domaci "tv", ta vznika migraci)
STATIONS = ("aaa", "bbb", "ccc", "abc", "xyz", "kid7", "nap1", "zzz")


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "CATCH_ROOT", str(tmp_path / "catch"))
    monkeypatch.setattr(store, "REJECTED_ROOT", str(tmp_path / "rejected"))
    monkeypatch.setattr(store, "TRASH_ROOT", str(tmp_path / "trash"))
    # registr stanic i stary state.json (zdroj migrace) jdou z tmp_path — se
    # zivymi daty by testy prepinaly krajinu skutecne televizi
    monkeypatch.setattr(server, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(server, "STATIONS_PATH", str(tmp_path / "config" / "stations.json"))
    monkeypatch.setattr(server, "registry", None)
    monkeypatch.setattr(server, "admins", auth.Admins(
        ADMIN_CODE, path=str(tmp_path / "config" / "admins.json"), secret="s" * 64))
    server.hub.sessions.clear()   # sessions z minulych testu nesmi prosakovat
    server.hub.pairing.clear()
    reg = server.get_registry()
    for sid in STATIONS:
        reg.items[sid] = stations.Station(id=sid, scene="cretaceous")
    reg.save()


@pytest.fixture
def client(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def admin(client):
    """Tentyz klient, prihlaseny kodem spravce (cookie si TestClient drzi)."""
    assert client.post("/api/login", json={"code": ADMIN_CODE}).status_code == 200
    return client


@pytest.fixture
def fast_idle_client(monkeypatch, tmp_path):
    """Jako client, ale s milisekundovymi casy uspavani — konstanty se musi
    zkratit PRED startem TestClienta, background task cte IDLE_TICK_S az
    v behu smycky."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "IDLE_WARN_S", 0.15)
    monkeypatch.setattr(server, "IDLE_SLEEP_S", 0.5)
    monkeypatch.setattr(server, "IDLE_TICK_S", 0.03)
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


def upload(client, data, filename="photo.jpg", name="Test", s=None, device=None):
    form = {"name": name}
    if s is not None:
        form["s"] = s
    if device is not None:
        form["device"] = device
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


def test_delete_catch(admin):
    client = admin
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


def test_ws_add_and_remove(admin):
    client = admin
    with client.websocket_connect("/ws") as ws:
        catch_id = upload(client, model_photo_jpg()).json()["id"]
        msg = ws.receive_json()
        assert msg["type"] == "add"
        assert msg["id"] == catch_id

        assert client.delete(f"/api/rigs/{catch_id}").status_code == 200
        msg = ws.receive_json()
        assert msg == {"type": "remove", "id": catch_id}


# --- Spravce: prihlaseni kodem ----------------------------------------------

def test_login_sets_cookie_and_me(client):
    assert client.get("/api/me").json() == {"admin": False}
    r = client.post("/api/login", json={"code": "spatny"})
    assert r.status_code == 403
    assert client.get("/api/me").json() == {"admin": False}

    # kod se opisuje rucne: velikost pismen a mezery nevadi
    r = client.post("/api/login", json={"code": " test 42 "})
    assert r.status_code == 200
    assert auth.COOKIE in r.cookies
    me = client.get("/api/me").json()
    assert me["admin"] is True and me["main"] is True and me["id"] == auth.MAIN_ID

    client.post("/api/logout")
    client.cookies.clear()
    assert client.get("/api/me").json() == {"admin": False}


def test_login_is_throttled(client):
    for _ in range(auth.LOGIN_TRIES):
        assert client.post("/api/login", json={"code": "x"}).status_code == 403
    # i spravny kod je po vycerpani pokusu chvili blokovany
    r = client.post("/api/login", json={"code": ADMIN_CODE})
    assert r.status_code == 429


def test_forged_cookie_is_not_admin(client):
    other = auth.Admins(ADMIN_CODE, path=server.admins.path + ".jiny", secret="j" * 64)
    client.cookies.set(auth.COOKIE, other.token(other.items[auth.MAIN_ID]))
    assert client.get("/api/me").json() == {"admin": False}
    client.cookies.set(auth.COOKIE, "hlavni.nesmysl")
    assert client.get("/api/me").json() == {"admin": False}


@pytest.mark.parametrize("method,url,body", [
    ("get", "/api/stations", None),
    ("post", "/api/stations", {}),
    ("delete", "/api/stations/aaa", None),
    ("post", "/api/scene/active", {"s": "aaa", "scene": "cretaceous_night"}),
    ("post", "/api/scene/settings", {"s": "aaa", "ambient": False}),
    ("post", "/api/scene/reset?s=aaa", None),
    ("post", "/api/pair/ABCD", {}),
])
def test_admin_actions_need_login(client, method, url, body):
    kw = {"json": body} if body is not None else {}
    r = getattr(client, method)(url, **kw)
    assert r.status_code == 403, url
    assert "správce" in r.json()["error"]


def test_generated_admin_code_is_persisted(monkeypatch, tmp_path):
    monkeypatch.delenv("DINO_ADMIN_CODE", raising=False)
    monkeypatch.setattr(auth, "CONFIG_DIR", str(tmp_path))
    code = auth.load_code()
    assert len(code) == auth.CODE_LEN and set(code) <= set(auth.ALPHABET)
    assert auth.load_code() == code          # druhy start: stejny kod
    monkeypatch.setenv("DINO_ADMIN_CODE", "abc-123")
    assert auth.load_code() == "ABC123"      # .env ma prednost


# --- Stanice ---------------------------------------------------------------

def test_station_create_list_and_end(admin):
    client = admin
    r = client.post("/api/stations", json={"scene": "aquarium"})
    assert r.status_code == 200
    sid = r.json()["s"]
    assert r.json()["scene"] == "aquarium"
    assert any(st["s"] == sid for st in client.get("/api/stations").json())
    # domaci stanice je v seznamu prvni
    assert client.get("/api/stations").json()[0]["s"] == "tv"

    catch_id = upload(client, model_photo_jpg(), s="aaa").json()["id"]
    with client.websocket_connect("/ws?s=aaa") as ws:
        r = client.delete("/api/stations/aaa")
        assert r.json() == {"ok": True, "deleted": 1}
        assert ws.receive_json() == {"type": "ended"}
    assert not server.os.path.isdir(store.catch_dir(catch_id))
    # po ukonceni je stanice pro vsechny pryc
    assert client.get("/api/scene/active?s=aaa").status_code == 404
    assert client.post("/api/feed", json={"s": "aaa"}).status_code == 404
    # domaci stanici ukoncit nejde
    assert client.delete("/api/stations/tv").status_code == 400


def test_station_registry_survives_restart(admin):
    client = admin
    sid = client.post("/api/stations", json={"scene": "cretaceous_night"}).json()["s"]
    client.post("/api/scene/settings", json={"s": sid, "ambient": False, "stay": True})
    server.registry = None          # "restart": registr se nacte znovu z disku
    server.hub.sessions.clear()
    assert client.get(f"/api/scene/active?s={sid}").json()["scene"] == "cretaceous_night"
    assert client.get(f"/api/scene/settings?s={sid}").json() == {
        "ambient": False, "stay": True, "scene": "cretaceous_night"}


def test_home_station_migrates_from_state_json(monkeypatch, tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"ambient": False, "scene": "aquarium"}),
                                         encoding="utf-8")
    reg = stations.Registry(str(tmp_path / "config" / "stations.json"),
                            legacy_state=str(tmp_path / "state.json"))
    home = reg.get("tv")
    assert (home.scene, home.ambient, home.stay) == ("aquarium", False, True)
    assert (tmp_path / "config" / "stations.json").exists()


def test_unknown_station_is_not_created(client):
    assert client.get("/api/scene/active?s=nikdo").status_code == 404
    assert client.post("/api/feed", json={"s": "nikdo"}).status_code == 404
    assert client.get("/api/qr?s=nikdo").status_code == 404
    r = upload(client, model_photo_jpg(), s="nikdo")
    assert r.status_code == 404 and "neběží" in r.json()["error"]
    assert "nikdo" not in server.get_registry().items
    with client.websocket_connect("/ws?s=nikdo") as ws:
        assert ws.receive_json() == {"type": "ended"}


def test_tv_pairing(admin):
    client = admin
    code = client.post("/api/pair").json()["code"]
    assert len(code) == stations.PAIR_LEN
    with client.websocket_connect(f"/ws?pair={code}") as tv:
        r = client.post(f"/api/pair/{code.lower()}", json={"scene": "aquarium"})
        assert r.status_code == 200
        sid = r.json()["s"]
        msg = tv.receive_json()
        assert msg["type"] == "paired" and msg["s"] == sid
        assert "/tv/" + msg["tv"] == r.json()["tv"]
    assert client.get(f"/api/scene/active?s={sid}").json()["scene"] == "aquarium"
    # kod je jednorazovy
    assert client.post(f"/api/pair/{code}", json={}).status_code == 404


def test_tv_pairing_to_existing_station(admin):
    client = admin
    code = client.post("/api/pair").json()["code"]
    with client.websocket_connect(f"/ws?pair={code}") as tv:
        r = client.post(f"/api/pair/{code}", json={"s": "tv"})
        assert r.json()["s"] == "tv"
        msg = tv.receive_json()
        assert (msg["type"], msg["s"]) == ("paired", "tv") and msg["tv"]


def test_expired_pair_code(client, monkeypatch):
    code = client.post("/api/pair").json()["code"]
    server.get_registry().pairs[code] = 0.0
    with client.websocket_connect(f"/ws?pair={code}") as tv:
        assert tv.receive_json() == {"type": "pair_expired"}


# --- Nastaveni a vyprazdneni stanice ---------------------------------------

def test_scene_settings_roundtrip(admin):
    client = admin
    assert client.get("/api/scene/settings?s=aaa").json() == {
        "ambient": True, "stay": False, "scene": "cretaceous"}

    r = client.post("/api/scene/settings", json={"s": "aaa", "ambient": False})
    assert r.status_code == 200
    assert r.json()["ambient"] is False
    assert client.get("/api/scene/settings?s=aaa").json()["ambient"] is False
    saved = json.loads(open(server.STATIONS_PATH, encoding="utf-8").read())
    assert saved["aaa"]["ambient"] is False
    # nastaveni je per stanice
    assert client.get("/api/scene/settings?s=bbb").json()["ambient"] is True


def test_scene_settings_broadcast_only_to_own_station(admin):
    client = admin
    with client.websocket_connect("/ws?s=aaa") as a, \
            client.websocket_connect("/ws?s=bbb") as b:
        client.post("/api/scene/settings", json={"s": "aaa", "ambient": False})
        assert a.receive_json() == {"type": "settings", "ambient": False}
        client.post("/api/scene/settings", json={"s": "bbb", "ambient": True})
        # prvni zprava B je jeho vlastni nastaveni, ne to od A
        assert b.receive_json() == {"type": "settings", "ambient": True}


def test_scene_reset_clears_catches_and_broadcasts(admin):
    client = admin
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


def test_scene_reset_with_nothing_to_delete(admin):
    r = admin.post("/api/scene/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deleted": 0}


def test_main_page_is_admin_and_old_links_redirect(client):
    r = client.get("/")
    assert r.status_code == 200 and "Správa" in r.text
    for old in ("/admin", "/rezim?s=aaa"):
        r = client.get(old, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/"
    assert client.get("/tv").status_code == 200
    assert client.get("/tv/cokoli").status_code == 200


# --- Detske mobily: vlastni ulovky ------------------------------------------

DEV_A = "mobil-aaaaaaaa"
DEV_B = "mobil-bbbbbbbb"


def test_kid_sees_and_deletes_only_own_catches(client):
    mine = upload(client, model_photo_jpg(), device=DEV_A).json()["id"]
    other = upload(client, model_photo_jpg(), device=DEV_B).json()["id"]
    ids = lambda r: [m["id"] for m in r.json()]
    assert ids(client.get(f"/api/rigs?mine={DEV_A}")) == [mine]
    assert ids(client.get(f"/api/rigs?mine={DEV_B}")) == [other]

    # cizi zvire smazat nejde, ani bez device
    r = client.delete(f"/api/rigs/{other}?device={DEV_A}")
    assert r.status_code == 403
    assert client.delete(f"/api/rigs/{other}").status_code == 403
    assert server.os.path.isdir(store.catch_dir(other))

    assert client.delete(f"/api/rigs/{mine}?device={DEV_A}").status_code == 200
    assert ids(client.get("/api/rigs")) == [other]


def test_kid_resends_old_catch_to_new_station(admin):
    """Dite prijde za dva dny k jine stanici a posle tam, co nakreslilo minule.
    Ukonceni stanice zvirata deti archivuje; poslat jde jen do spravne krajiny."""
    client = admin
    old = upload(client, model_photo_jpg(), s="aaa", device=DEV_A).json()["id"]
    fish_id, fish_dir = store.new_catch("clownfish")
    server.os.makedirs(fish_dir, exist_ok=True)
    open(server.os.path.join(fish_dir, "model.json"), "w").write("{}")
    store.write_meta(fish_id, creature="clownfish", label="Klaun", motion="swim",
                     session="aaa", owner=DEV_A)

    assert client.delete("/api/stations/aaa").status_code == 200
    mine = lambda s: {m["creature"]: m for m in
                      client.get(f"/api/mine?s={s}&device={DEV_A}").json()}
    lib = mine("bbb")
    assert set(lib) == {"trex3d", "clownfish"}
    assert lib["trex3d"]["fits"] and not lib["trex3d"]["here"]
    assert not lib["clownfish"]["fits"]
    assert client.get(f"/api/mine?s=bbb&device={DEV_B}").json() == []

    r = client.post("/api/mine/send", json={"s": "bbb", "device": DEV_A, "id": fish_id})
    assert r.status_code == 409
    r = client.post("/api/mine/send", json={"s": "bbb", "device": DEV_B, "id": old})
    assert r.status_code == 404
    with client.websocket_connect("/ws?s=bbb") as ws:
        r = client.post("/api/mine/send", json={"s": "bbb", "device": DEV_A, "id": old})
        assert r.status_code == 200, r.text
        assert ws.receive_json()["type"] == "add"
    assert [m["id"] for m in client.get("/api/rigs?s=bbb").json()] == [old]
    assert mine("bbb")["trex3d"]["here"]
    r = client.post("/api/mine/send", json={"s": "bbb", "device": DEV_A, "id": old})
    assert r.status_code == 409

    # ze ziveho zvirete na jine televizi vznikne kopie, original tam zustane
    r = client.post("/api/mine/send", json={"s": "ccc", "device": DEV_A, "id": old})
    assert r.status_code == 200 and r.json()["id"] != old
    assert [m["id"] for m in client.get("/api/rigs?s=bbb").json()] == [old]
    assert len(mine("ccc")) == 2

    # odebrani z televize = zpatky do archivu, pak teprve nadobro
    assert client.delete(f"/api/rigs/{old}?device={DEV_A}").status_code == 200
    assert not mine("bbb")["trex3d"]["here"]
    assert client.delete(f"/api/rigs/{old}?device={DEV_A}").status_code == 200
    assert store.find_catch(old) == (None, False)


def test_catch_without_owner_is_nobodys(client):
    """Stare ulovky (bez `owner`) ani nevalidni device nesmi nikomu dat pravo."""
    cid = upload(client, model_photo_jpg(), device="kratke").json()["id"]
    assert store.read_meta(cid)["owner"] == ""
    assert client.get("/api/rigs?mine=").json() != []        # prazdny filtr = vse
    assert client.delete(f"/api/rigs/{cid}?device=").status_code == 403


# --- Stanice izolovane ----------------------------------------------------

def test_sessions_rigs_isolated(client):
    body = upload(client, model_photo_jpg(), s="aaa").json()
    assert body["ok"] is True
    assert body["session"] == "aaa"

    ids = lambda r: [m["id"] for m in r.json()]
    assert ids(client.get("/api/rigs?s=aaa")) == [body["id"]]
    assert ids(client.get("/api/rigs?s=bbb")) == []
    # domaci "tv" cizi ulovek nevidi — a naopak
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


def test_sessions_ws_routing(admin):
    client = admin
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

        # remove jde do stanice ulovku, ne vsem
        assert client.delete(f"/api/rigs/{id_b}").status_code == 200
        assert ws_b.receive_json() == {"type": "remove", "id": id_b}
        assert client.delete(f"/api/rigs/{id_a}").status_code == 200
        assert ws_a.receive_json() == {"type": "remove", "id": id_a}


def test_qr_leads_only_to_pridat(client):
    r = client.get("/api/qr?s=abc")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    url = r.headers["X-Upload-Url"]
    assert url.endswith("/pridat?s=abc")
    # i domaci televize ma v QR vyslovne svou stanici
    assert client.get("/api/qr").headers["X-Upload-Url"].endswith("/pridat?s=tv")
    assert client.get("/api/qr?s=..%2F..").status_code == 404


def test_reset_scoped_to_session(admin):
    client = admin
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
    assert client.post("/api/session/touch", json={"s": "neni"}).status_code == 404


def test_pridat_with_session_touches(client):
    assert "kid7" not in server.hub.sessions
    assert client.get("/pridat?s=kid7").status_code == 200
    assert "kid7" in server.hub.sessions
    # neznama stanice: stranka se ukaze (rekne „nebezi"), ale nic nevznikne
    assert client.get("/pridat?s=nikdo").status_code == 200
    assert "nikdo" not in server.hub.sessions


def test_idle_tick_logic(client, monkeypatch):
    """Deterministicka cast hlidace: prah varovani/uspani, vyjimka pro
    stanice se `stay` (domaci "tv"), zahazovani opustenych sessions z pameti."""
    import asyncio

    monkeypatch.setattr(server, "hub", server.Hub())
    reg = server.get_registry()
    for sid in ("kid", "fresh", "gone"):
        reg.items[sid] = stations.Station(id=sid, scene="cretaceous")
    now = 1_000_000.0
    hub = server.hub
    # hluboko za prahem uspani, ale pod TTL — uklid pameti je jina vec
    hub.session("tv").last_seen = now - (server.SESSION_TTL_S - 10)
    hub.session("kid").last_seen = now - server.IDLE_SLEEP_S - 1
    hub.session("fresh").last_seen = now - 1
    hub.session("gone").last_seen = now - server.SESSION_TTL_S - 1

    async def run():
        await server.idle_tick(now=now)
        assert "gone" not in hub.sessions      # opustena session zmizela z pameti
        assert "gone" in reg.items             # ...ale stanice zustava
        assert hub.sessions["kid"].sleeping is True
        assert hub.sessions["fresh"].sleeping is False
        # domaci "tv" (stay) se NEUSPAVA, at je necinna jakkoli dlouho
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
        assert len(s["nouns"]) == 3 and s["invite"]["title"] and s["feedBusy"]
    by_key = {s["key"]: s for s in scenes}
    assert by_key["cretaceous_night"]["catalogue"] == "cretaceous"
    assert [s["order"] for s in scenes] == sorted(s["order"] for s in scenes)


def test_scene_render_served_only_for_registered_scenes(client):
    r = client.get("/scenes/aquarium/render.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert client.get("/scenes/neni/render.js").status_code == 404
    assert client.get("/scenes/aquarium/scene.json").status_code == 404


def test_templates_carry_scene_and_filter(client):
    everything = client.get("/api/templates").json()
    owners = {s.catalogue for s in scenes.SCENES}
    assert {"cretaceous", "aquarium"} <= owners
    assert {t["scene"] for t in everything} == owners
    fish = client.get("/api/templates?scene=aquarium").json()
    assert fish and all(t["scene"] == "aquarium" for t in fish)
    night = client.get("/api/templates?scene=cretaceous_night").json()
    assert night and all(t["scene"] == "cretaceous" for t in night)


def test_dino3d_scene_filter(client):
    everything = client.get("/api/dino3d").json()
    cretaceous = client.get("/api/dino3d?scene=cretaceous").json()
    aquarium = client.get("/api/dino3d?scene=aquarium").json()
    assert 0 < len(cretaceous) < len(everything)
    assert 0 < len(aquarium) < len(everything)
    assert sum(len(client.get(f"/api/dino3d?scene={k}").json())
               for k in {s.catalogue for s in scenes.SCENES}) == len(everything)
    assert all(m["scene"] == "cretaceous" for m in cretaceous)
    assert all(m["scene"] == "aquarium" and m["motion"] == "swim" for m in aquarium)
    assert client.get("/api/dino3d?scene=neexistuje").json() == []


def test_scene_active_per_session(admin):
    client = admin
    assert client.get("/api/scene/active?s=xyz").json() == {
        "s": "xyz", "scene": "cretaceous"}

    with client.websocket_connect("/ws?s=xyz") as ws:
        r = client.post("/api/scene/active",
                        json={"scene": "cretaceous_night", "s": "xyz"})
        assert r.json() == {"ok": True, "s": "xyz", "scene": "cretaceous_night"}
        assert ws.receive_json() == {"type": "scene", "scene": "cretaceous_night"}

    assert client.get("/api/scene/active?s=xyz").json()["scene"] == "cretaceous_night"
    assert client.get("/api/session/xyz").json()["scene"] == "cretaceous_night"
    assert client.get("/api/scene/active?s=aaa").json()["scene"] == "cretaceous"

    r = client.post("/api/scene/active", json={"scene": "atlantida", "s": "xyz"})
    assert r.status_code == 400
    assert "krajina" in r.json()["error"]


def test_foreign_creature_is_rejected_and_not_saved(admin):
    client = admin
    with client.websocket_connect("/ws?s=aaa") as ws:
        client.post("/api/scene/active", json={"scene": "aquarium", "s": "aaa"})
        assert ws.receive_json() == {"type": "scene", "scene": "aquarium"}

        r = upload(client, model_photo_jpg(), s="aaa")
        assert r.status_code == 409
        body = r.json()
        assert body["foreign"] is True
        assert "Akvárium" in body["error"] and "Tyrannosaurus" in body["error"]
        assert "Žralok" in body["allowed"]

        # scena zadny `add` nedostala: dalsi zprava na WS je az tohle prepnuti
        client.post("/api/scene/active", json={"scene": "cretaceous", "s": "aaa"})
        assert ws.receive_json() == {"type": "scene", "scene": "cretaceous"}

    # nic se neulozilo — ani mezi ulovky, ani mezi odmitnute fotky
    assert client.get("/api/rigs?s=aaa").json() == []
    assert not server.os.path.isdir(store.REJECTED_ROOT) or \
        not list(server.os.scandir(store.REJECTED_ROOT))


def test_shared_catalogue_accepts_creature(admin):
    """Nocni laguna sdili dinosaury s denni — trex do ni patri."""
    client = admin
    client.post("/api/scene/active", json={"scene": "cretaceous_night", "s": "aaa"})
    body = upload(client, model_photo_jpg(), s="aaa").json()
    assert body["ok"] is True
    ids = lambda r: [m["id"] for m in r.json()]
    assert ids(client.get("/api/rigs?s=aaa&scene=cretaceous")) == [body["id"]]
    assert ids(client.get("/api/rigs?s=aaa&scene=aquarium")) == []


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

        # rate-limit: druhy hod hned po prvnim vraci 429 s hlaskou krajiny
        r2 = client.post("/api/feed", json={"s": "aaa"})
        assert r2.status_code == 429
        assert r2.json()["ok"] is False
        assert "žvýkají" in r2.json()["error"]

        r3 = client.post("/api/feed", json={"s": "bbb"})
        assert r3.status_code == 200
        msg_b = ws_b.receive_json()
        assert msg_b["type"] == "feed"
        assert msg_b["x"] == r3.json()["x"]


def test_feed_busy_text_follows_scene(admin):
    client = admin
    client.post("/api/scene/active", json={"scene": "aquarium", "s": "ccc"})
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 200
    r = client.post("/api/feed", json={"s": "ccc"})
    assert r.status_code == 429 and "Ryby" in r.json()["error"]


def test_feed_cooldown_expires(client, monkeypatch):
    monkeypatch.setattr(server, "FEED_COOLDOWN_S", 0.05)
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 200
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 429
    import time as _time
    _time.sleep(0.06)
    assert client.post("/api/feed", json={"s": "ccc"}).status_code == 200


# --- Vic spravcu -------------------------------------------------------------

def _login(client, code):
    client.cookies.clear()
    r = client.post("/api/login", json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()


def test_main_admin_issues_codes_and_admins_see_only_own(client):
    _login(client, ADMIN_CODE)
    r = client.post("/api/admins", json={"name": "Učitelka Jana"})
    assert r.status_code == 200
    jana_code, jana_id = r.json()["code"], r.json()["id"]
    assert len(jana_code) == auth.CODE_LEN
    # kod se uklada jen jako otisk
    assert jana_code not in open(server.admins.path, encoding="utf-8").read()

    me = _login(client, jana_code)
    assert me["name"] == "Učitelka Jana" and me["main"] is False
    sid = client.post("/api/stations", json={"scene": "aquarium"}).json()["s"]
    mine = [st["s"] for st in client.get("/api/stations").json()]
    assert mine == [sid]                         # cizi stanice (tv, aaa…) nevidi
    # cizi stanici neovlada ani primo
    assert client.post("/api/scene/active", json={"s": "aaa", "scene": "aquarium"}
                       ).status_code == 404
    assert client.post("/api/scene/reset?s=tv").status_code == 404
    assert client.delete("/api/stations/aaa").status_code == 404
    assert client.get("/api/admins").status_code == 403   # spravu spravcu ma jen hlavni

    _login(client, ADMIN_CODE)
    every = {st["s"]: st for st in client.get("/api/stations").json()}
    assert sid in every and "tv" in every        # hlavni vidi vsechno
    assert every[sid]["ownerName"] == "Učitelka Jana"

    # novy kod zneplatni stary i Janino prihlaseni
    jana_cookie = _login(client, jana_code) and client.cookies.get(auth.COOKIE)
    _login(client, ADMIN_CODE)
    new_code = client.post(f"/api/admins/{jana_id}/code").json()["code"]
    client.cookies.clear()
    assert client.post("/api/login", json={"code": jana_code}).status_code == 403
    client.cookies.set(auth.COOKIE, jana_cookie)
    assert client.get("/api/me").json() == {"admin": False}
    _login(client, new_code)

    # zruseni spravce: stanice prevezme hlavni
    _login(client, ADMIN_CODE)
    assert client.delete(f"/api/admins/{jana_id}").json() == {"ok": True, "moved": 1}
    assert server.get_registry().get(sid).owner == auth.MAIN_ID
    assert client.delete(f"/api/admins/{auth.MAIN_ID}").status_code == 400


def test_tv_link_resolves_station(admin):
    st = admin.post("/api/stations", json={"scene": "cretaceous_night"}).json()
    token = st["tv"].rsplit("/", 1)[1]
    assert len(token) >= 16
    assert admin.get(f"/api/tv/{token}").json() == {"s": st["s"], "scene": "cretaceous_night"}
    admin.cookies.clear()                        # odkaz plati i bez prihlaseni
    assert admin.get(f"/api/tv/{token}").status_code == 200
    assert admin.get("/api/tv/uhodnuty-token-xyz").status_code == 404


def test_old_stations_get_tv_token_on_load(tmp_path):
    path = tmp_path / "stations.json"
    path.write_text(json.dumps({"tv": {"scene": "aquarium", "stay": True}}), encoding="utf-8")
    reg = stations.Registry(str(path))
    tv = reg.get("tv")
    assert tv.owner == auth.MAIN_ID and len(tv.tv) >= 16
    assert reg.by_tv(tv.tv) is tv
    assert json.loads(path.read_text(encoding="utf-8"))["tv"]["tv"] == tv.tv


def test_page_scripts_are_revalidated(client):
    """Po nasazeni nesmi televize bezet se starym modulem vedle nove stranky."""
    r = client.get("/web/roster.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    r2 = client.get("/web/roster.js", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304
