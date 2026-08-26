"""Persistent catches under data/catch/<id>/.

Each catch is a self-contained directory: rig.json plus its images (written by
rig.build_rig), the original photo so a catch can be reprocessed after the
pipeline changes, and meta.json with everything the listing needs.
"""

import json
import os
import re
import secrets
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATCH_ROOT = os.path.join(ROOT, "data", "catch")

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}-[0-9a-f]{4}$")


def ensure_root():
    os.makedirs(CATCH_ROOT, exist_ok=True)
    return CATCH_ROOT


def catch_dir(catch_id):
    if not ID_RE.match(catch_id or ""):
        raise ValueError(f"neplatné id úlovku: {catch_id!r}")
    return os.path.join(CATCH_ROOT, catch_id)


def new_catch(creature_key):
    """Reserve a fresh, human-readable directory. Returns (id, path)."""
    ensure_root()
    key = re.sub(r"[^a-z0-9_]", "", creature_key.lower()) or "tvor"
    for _ in range(64):
        catch_id = f"{key}-{secrets.token_hex(2)}"
        path = os.path.join(CATCH_ROOT, catch_id)
        try:
            os.mkdir(path)
        except FileExistsError:
            continue
        return catch_id, path
    raise RuntimeError("nepodařilo se vytvořit složku pro úlovek")


def save_photo(catch_id, data):
    """Keep the untouched upload for later reprocessing."""
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    path = os.path.join(catch_dir(catch_id), "photo" + ext)
    with open(path, "wb") as f:
        f.write(data)
    return os.path.basename(path)


def find_photo(catch_id):
    d = catch_dir(catch_id)
    for ext in (".jpg", ".png"):
        p = os.path.join(d, "photo" + ext)
        if os.path.exists(p):
            return p
    return None


def write_meta(catch_id, *, creature, label, motion, name="", coverage=0.0,
               markers=0, photo=None, kind="rig"):
    """`kind` rozlisuje, co v adresari lezi: ohybany 2D rig, nebo textura
    k hotovemu 3D modelu."""
    meta = {
        "id": catch_id,
        "url": f"/catch/{catch_id}/",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "creature": creature,
        "label": label,
        "motion": motion,
        "name": name,
        "coverage": round(float(coverage), 4),
        "markers": int(markers),
        "photo": photo,
        "kind": kind,
    }
    with open(os.path.join(catch_dir(catch_id), "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return meta


def read_meta(catch_id):
    path = os.path.join(catch_dir(catch_id), "meta.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_catches():
    """All finished catches, oldest first. Half-written directories are skipped."""
    ensure_root()
    out = []
    for entry in os.scandir(CATCH_ROOT):
        if not entry.is_dir() or not ID_RE.match(entry.name):
            continue
        # rig.json ma ohybany 2D tvor, model.json ten z hotoveho 3D modelu;
        # bez jednoho z nich je adresar rozepsany
        if not any(os.path.exists(os.path.join(entry.path, f))
                   for f in ("rig.json", "model.json")):
            continue
        try:
            meta = read_meta(entry.name)
        except (OSError, json.JSONDecodeError):
            continue
        if meta:
            out.append(meta)
    out.sort(key=lambda m: (m.get("created", ""), m["id"]))
    return out


def delete_catch(catch_id):
    path = catch_dir(catch_id)
    if not os.path.isdir(path):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.isdir(path)
