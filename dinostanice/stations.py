"""Stanice = jedna televize se svou krajinou, svými úlovky a svým QR.

Zakládá je správce (`owner`) a vidí je jen on a hlavní správce. Každá má
dvě adresy: krátké `id` pro dětský QR (/pridat?s=…) a tajný `tv` token pro
odkaz na scénu (/tv/…) — kdo ho nemá, scénu cizí stanice neotevře. Registr je trvalý
(`data/config/stations.json`), takže krajina i nastavení každé stanice
přežijí restart. Neznámé `?s=` už stanici nezaloží — dítě s QR od skončené
stanice dostane „tahle stanice neběží", ne prázdnou novou.

Domácí stanice `tv` vznikne při prvním startu z dřívějšího `data/state.json`
(krajina + ambient) a neusíná, aby se nic doma nezměnilo.
"""

import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass

from . import paths, scenes
from .auth import MAIN_ID

HOME = "tv"
SID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
SID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
SID_LEN = 8
TV_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIR_LEN = 4
PAIR_TTL_S = 10 * 60


def default_path():
    return os.path.join(paths.data_root(), "config", "stations.json")


@dataclass
class Station:
    id: str
    scene: str
    ambient: bool = True
    stay: bool = False       # neusínat po 15 minutách bez aktivity
    created: float = 0.0
    owner: str = MAIN_ID     # id správce (auth.Admins)
    tv: str = ""             # tajný token odkazu na scénu


def new_tv_token():
    return secrets.token_urlsafe(12)


class Registry:
    def __init__(self, path=None, legacy_state=None):
        self.path = path or default_path()
        self.legacy_state = legacy_state
        self.items: dict[str, Station] = {}
        self.pairs: dict[str, float] = {}     # kód -> čas vypršení
        self.load()

    # --- trvalé uložení -----------------------------------------------------

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = None
        if raw is None:
            self.items = {}
            self._migrate()
            return
        self.items = {}
        dirty = False
        for sid, d in raw.items():
            if SID_RE.match(sid):
                tv = d.get("tv") or ""
                if not TV_RE.match(tv):
                    tv, dirty = new_tv_token(), True
                self.items[sid] = Station(id=sid, scene=scenes.clean_scene(d.get("scene")),
                                          ambient=bool(d.get("ambient", True)),
                                          stay=bool(d.get("stay", False)),
                                          created=float(d.get("created", 0.0)),
                                          owner=d.get("owner") or MAIN_ID, tv=tv)
        if dirty:
            self.save()

    def _migrate(self):
        """První start: domácí televize ze starého state.json."""
        state = {}
        if self.legacy_state:
            try:
                with open(self.legacy_state, encoding="utf-8") as f:
                    state = json.load(f)
            except (OSError, ValueError):
                state = {}
        self.items[HOME] = Station(id=HOME, scene=scenes.clean_scene(state.get("scene")),
                                   ambient=bool(state.get("ambient", True)), stay=True,
                                   created=time.time(), tv=new_tv_token())
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({sid: {k: v for k, v in asdict(st).items() if k != "id"}
                       for sid, st in self.items.items()}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # --- stanice ------------------------------------------------------------

    def get(self, sid):
        return self.items.get(sid)

    def by_tv(self, token):
        if not TV_RE.match(token or ""):
            return None
        return next((st for st in self.items.values() if st.tv == token), None)

    def create(self, scene=None, owner=MAIN_ID):
        while True:
            sid = "".join(secrets.choice(SID_ALPHABET) for _ in range(SID_LEN))
            if sid not in self.items:
                break
        st = Station(id=sid, scene=scenes.clean_scene(scene), created=time.time(),
                     owner=owner, tv=new_tv_token())
        self.items[sid] = st
        self.save()
        return st

    def update(self, sid, **fields):
        st = self.items[sid]
        for k, v in fields.items():
            setattr(st, k, v)
        self.save()
        return st

    def remove(self, sid):
        if self.items.pop(sid, None) is None:
            return False
        self.save()
        return True

    # --- párování televize --------------------------------------------------

    def new_pair_code(self, now=None):
        now = time.monotonic() if now is None else now
        self.pairs = {c: t for c, t in self.pairs.items() if t > now}
        while True:
            code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(PAIR_LEN))
            if code not in self.pairs:
                break
        self.pairs[code] = now + PAIR_TTL_S
        return code

    def pair_valid(self, code, now=None):
        now = time.monotonic() if now is None else now
        exp = self.pairs.get(code)
        return exp is not None and exp > now

    def take_pair(self, code, now=None):
        """Jednorázové: platný kód se spotřebuje."""
        if not self.pair_valid(code, now):
            return False
        del self.pairs[code]
        return True
