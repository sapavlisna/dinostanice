"""Správci stanice: kdo zná svůj kód, je správce svých stanic.

Hlavní správce má kód v `DINO_ADMIN_CODE` (.env); když tam není, vygeneruje
se při prvním startu do `data/config/admin.json` a vypíše do logu. Hlavní
správce vydává kódy dalším správcům (`data/config/admins.json`). Každý vidí
a ovládá jen svoje stanice, hlavní všechny.

Kódy se ukládají jen jako otisk; ukázat jde jen při vytvoření nebo
přegenerování. Cookie nese id správce a HMAC z tajného klíče serveru a otisku
kódu — nový kód (nebo smazání správce) jeho přihlášení zneplatní.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass

from . import paths

COOKIE = "dino_admin"
COOKIE_MAX_AGE = 30 * 24 * 3600
# bez 0/O, 1/I/L — kód se opisuje z papíru nebo z hlavy
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 6
LOGIN_TRIES = 5          # pokusů za LOGIN_WINDOW_S z jedné adresy
LOGIN_WINDOW_S = 60
MAIN_ID = "hlavni"

CONFIG_DIR = os.path.join(paths.data_root(), "config")


def config_path(name):
    return os.path.join(CONFIG_DIR, name)


def new_code(n=CODE_LEN):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def normalize(code):
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def code_hash(code):
    return hashlib.sha256(("dinostanice:" + normalize(code)).encode()).hexdigest()


def load_code(log=None):
    """Kód hlavního správce: z prostředí, jinak z admin.json, jinak nový."""
    env = normalize(os.environ.get("DINO_ADMIN_CODE"))
    if env:
        return env
    path = config_path("admin.json")
    try:
        with open(path, encoding="utf-8") as f:
            code = normalize(json.load(f).get("code"))
        if code:
            return code
    except (OSError, ValueError):
        pass
    code = new_code()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"code": code}, f)
    if log:
        log.warning("vygenerován kód hlavního správce: %s (změníš ho v .env přes "
                    "DINO_ADMIN_CODE nebo v %s)", code, path)
    return code


def _load_secret():
    path = config_path("secret")
    try:
        with open(path, encoding="utf-8") as f:
            s = f.read().strip()
        if len(s) >= 32:
            return s
    except OSError:
        pass
    s = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    return s


@dataclass
class Admin:
    id: str
    name: str
    hash: str
    main: bool = False
    created: float = 0.0

    def public(self):
        return {"id": self.id, "name": self.name, "main": self.main,
                "created": self.created}


class Admins:
    def __init__(self, main_code, path=None, secret=None):
        self.path = path or config_path("admins.json")
        self.secret = secret or _load_secret()
        self.tries: dict[str, list] = {}
        self.items: dict[str, Admin] = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                for aid, d in json.load(f).items():
                    self.items[aid] = Admin(id=aid, name=d["name"], hash=d["hash"],
                                            main=bool(d.get("main")),
                                            created=float(d.get("created", 0)))
        except (OSError, ValueError, KeyError):
            pass
        # hlavní správce vždy existuje a jeho kód určuje .env / admin.json
        main = self.items.get(MAIN_ID)
        h = code_hash(main_code)
        if main is None or main.hash != h or not main.main:
            self.items[MAIN_ID] = Admin(id=MAIN_ID, name=main.name if main else "Hlavní správce",
                                        hash=h, main=True,
                                        created=main.created if main else time.time())
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({a.id: {k: v for k, v in asdict(a).items() if k != "id"}
                       for a in self.items.values()}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # --- přihlášení ---------------------------------------------------------

    def token(self, admin):
        sig = hmac.new(self.secret.encode(), f"{admin.id}:{admin.hash}".encode(),
                       hashlib.sha256).hexdigest()
        return f"{admin.id}.{sig}"

    def from_cookie(self, value):
        aid, _, _sig = (value or "").partition(".")
        admin = self.items.get(aid)
        if admin and hmac.compare_digest(value, self.token(admin)):
            return admin
        return None

    def throttled(self, ip, now=None):
        now = time.monotonic() if now is None else now
        recent = [t for t in self.tries.get(ip, []) if now - t < LOGIN_WINDOW_S]
        self.tries[ip] = recent
        return len(recent) >= LOGIN_TRIES

    def login(self, ip, code, now=None):
        """Správce s tímhle kódem, nebo None (pokus se počítá do limitu)."""
        now = time.monotonic() if now is None else now
        h = code_hash(code)
        for admin in self.items.values():
            if hmac.compare_digest(admin.hash, h):
                self.tries.pop(ip, None)
                return admin
        self.tries.setdefault(ip, []).append(now)
        return None

    # --- správa správců (jen hlavní) ----------------------------------------

    def _fresh_code(self):
        used = {a.hash for a in self.items.values()}
        while True:
            code = new_code()
            if code_hash(code) not in used:
                return code

    def create(self, name):
        name = " ".join((name or "").split())[:40] or "Správce"
        while True:
            aid = "a" + secrets.token_hex(4)
            if aid not in self.items:
                break
        code = self._fresh_code()
        admin = Admin(id=aid, name=name, hash=code_hash(code), created=time.time())
        self.items[aid] = admin
        self.save()
        return admin, code

    def reset_code(self, aid):
        admin = self.items[aid]
        code = self._fresh_code()
        admin.hash = code_hash(code)
        self.save()
        return code

    def remove(self, aid):
        if aid == MAIN_ID or self.items.pop(aid, None) is None:
            return False
        self.save()
        return True
