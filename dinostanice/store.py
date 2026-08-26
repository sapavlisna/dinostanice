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
import unicodedata
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATCH_ROOT = os.path.join(ROOT, "data", "catch")
REJECTED_ROOT = os.path.join(ROOT, "data", "rejected")
TRASH_ROOT = os.path.join(ROOT, "data", "trash")
TRASH_KEEP_DAYS = 30
REJECTED_KEEP = 50

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}-[0-9a-f]{4}$")


def write_image(path, img):
    """cv2.imwrite tise vraci False (plny disk, spatna cesta) — tady je z toho vyjimka."""
    import cv2
    if not cv2.imwrite(str(path), img):
        raise OSError(f"zápis obrázku selhal: {path}")


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
    """Atomicky odstaví úlovek na <id>.deleted (ID_RE ho pak nevidí); skutečné
    smazání dělá purge_deleted() — na Windows může StaticFiles držet otevřený
    soubor a rmtree by nechal adresář v půlrozpadlém stavu."""
    path = catch_dir(catch_id)
    if not os.path.isdir(path):
        return False
    trash = path + ".deleted"
    if os.path.exists(trash):
        shutil.rmtree(trash, ignore_errors=True)
    os.replace(path, trash)
    return True


def purge_deleted():
    """Best-effort úklid odstavených úlovků: přesouvá je do data/trash/, ne na
    věčnost pryč — jsou to dětské výtvory a omylem spuštěný reset je nesmí
    zničit. Koš se čistí až po TRASH_KEEP_DAYS. Vrací počet těch, co nešly
    odklidit (drží je otevřený soubor)."""
    ensure_root()
    os.makedirs(TRASH_ROOT, exist_ok=True)
    left = 0
    for entry in list(os.scandir(CATCH_ROOT)):
        if entry.is_dir() and entry.name.endswith(".deleted"):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = os.path.join(TRASH_ROOT, entry.name[: -len(".deleted")] + "-" + stamp)
            try:
                os.replace(entry.path, dest)
            except OSError:
                left += 1
    cutoff = datetime.now().timestamp() - TRASH_KEEP_DAYS * 86400
    for entry in list(os.scandir(TRASH_ROOT)):
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry.path, ignore_errors=True)
    return left


def save_rejected(data, reason):
    """Odmítnuté fotky jsou nejcennější testovací materiál — pár posledních se schová."""
    os.makedirs(REJECTED_ROOT, exist_ok=True)
    ascii_reason = unicodedata.normalize("NFKD", reason or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_reason.lower()).strip("-")[:60] or "chyba"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    path = os.path.join(REJECTED_ROOT, f"{stamp}_{slug}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    files = sorted(e.name for e in os.scandir(REJECTED_ROOT) if e.is_file())
    for name in files[:-REJECTED_KEEP]:
        try:
            os.remove(os.path.join(REJECTED_ROOT, name))
        except OSError:
            pass
    return path
