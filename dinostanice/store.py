"""Persistent catches under data/catch/<id>/.

Each catch is a self-contained directory: model.json plus the texture (written
by capture3d.save_catch), the original photo so a catch can be reprocessed
after the pipeline changes, and meta.json with everything the listing needs.
"""

import json
import os
import re
import secrets
import shutil
import unicodedata
from datetime import datetime

from . import paths

DATA_ROOT = paths.data_root()
CATCH_ROOT = os.path.join(DATA_ROOT, "catch")
REJECTED_ROOT = os.path.join(DATA_ROOT, "rejected")
TRASH_ROOT = os.path.join(DATA_ROOT, "trash")
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


DEFAULT_SESSION = "tv"


def write_meta(catch_id, *, creature, label, motion, name="", coverage=0.0,
               markers=0, photo=None, session=DEFAULT_SESSION, owner=""):
    """`session` rika, ktere televizi ulovek patri, `owner` ktery mobil ho
    poslal (nahodne id z localStorage; smi pak svuj ulovek smazat)."""
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
        "session": session,
        "owner": owner,
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


def list_catches(session=None):
    """All finished catches, oldest first. Half-written directories are skipped.

    `session` filtruje ulovky jedne televize; starsi meta bez klice `session`
    patri defaultni. None = vsechno (interni pouziti, uklid)."""
    ensure_root()
    out = []
    for entry in os.scandir(CATCH_ROOT):
        if not entry.is_dir() or not ID_RE.match(entry.name):
            continue
        # bez model.json je adresar rozepsany
        if not os.path.exists(os.path.join(entry.path, "model.json")):
            continue
        try:
            meta = read_meta(entry.name)
        except (OSError, json.JSONDecodeError):
            continue
        if not meta:
            continue
        if session is not None and meta.get("session", DEFAULT_SESSION) != session:
            continue
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
                # shutil.move umí i přesun přes hranici filesystémů (bind
                # mount v Dockeru), kde by os.replace spadl na EXDEV
                shutil.move(entry.path, dest)
            except OSError:
                left += 1
    cutoff = datetime.now().timestamp() - TRASH_KEEP_DAYS * 86400
    for entry in list(os.scandir(TRASH_ROOT)):
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry.path, ignore_errors=True)
    return left


# Archiv: ulovky deti, ktere uz na zadne televizi nebezi (stanice skoncila,
# byla vyprazdnena, dite zvire z televize odebralo). Mobil je odtud muze
# poslat znovu. Lezi uvnitr CATCH_ROOT, aby je drzel stejny bind mount
# a servirovalo /catch; list_catches ho nevidi, `_archiv` neodpovida ID_RE.
def archive_root():
    return os.path.join(CATCH_ROOT, "_archiv")


def _write_meta(path, meta):
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def origin_of(meta):
    """Kopie poslana znovu nese id puvodniho ulovku — je to porad tentyz obrazek."""
    return meta.get("origin") or meta["id"]


def find_catch(catch_id):
    """(meta, archived) pro ulovek na televizi i v archivu; (None, False) kdyz neni."""
    catch_dir(catch_id)
    meta = read_meta(catch_id)
    if meta:
        return meta, False
    path = os.path.join(archive_root(), catch_id, "meta.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f), True
    return None, False


def list_archive(owner=None):
    if not os.path.isdir(archive_root()):
        return []
    out = []
    for entry in os.scandir(archive_root()):
        if not entry.is_dir() or not ID_RE.match(entry.name):
            continue
        try:
            with open(os.path.join(entry.path, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if owner is not None and meta.get("owner") != owner:
            continue
        meta["url"] = f"/catch/_archiv/{entry.name}/"
        meta["archived"] = True
        out.append(meta)
    out.sort(key=lambda m: (m.get("created", ""), m["id"]))
    return out


def _to_trash(path, name):
    os.makedirs(TRASH_ROOT, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.move(path, os.path.join(TRASH_ROOT, f"{name}-{stamp}"))


def archive_catch(catch_id):
    """Sundá úlovek z televize do archivu. Starší archivní kopie téhož obrázku
    jdou do koše, ať v knihovně mobilu nestraší dvakrát."""
    src = catch_dir(catch_id)
    meta = read_meta(catch_id)
    if not meta or not os.path.isdir(src):
        return False
    os.makedirs(archive_root(), exist_ok=True)
    origin = origin_of(meta)
    for old in list_archive(owner=meta.get("owner")):
        if origin_of(old) == origin:
            _to_trash(os.path.join(archive_root(), old["id"]), old["id"])
    shutil.move(src, os.path.join(archive_root(), catch_id))
    return True


def trash_archived(catch_id):
    path = os.path.join(archive_root(), catch_id)
    catch_dir(catch_id)
    if not os.path.isdir(path):
        return False
    _to_trash(path, catch_id)
    return True


def resend_catch(catch_id, session):
    """Pošle úlovek na televizi `session`. Z archivu se přesune zpátky,
    z jiné běžící stanice se zkopíruje pod novým id (tam má zůstat)."""
    meta, archived = find_catch(catch_id)
    if meta is None:
        return None
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if archived:
        new_id, dst = catch_id, catch_dir(catch_id)
        if os.path.exists(dst):
            return None
        shutil.move(os.path.join(archive_root(), catch_id), dst)
    else:
        new_id, dst = new_catch(meta["creature"])
        for entry in os.scandir(catch_dir(catch_id)):
            if entry.is_file() and entry.name != "meta.json":
                shutil.copy2(entry.path, os.path.join(dst, entry.name))
    meta.pop("archived", None)
    meta.update(id=new_id, url=f"/catch/{new_id}/", session=session, created=now,
                origin=origin_of(meta))
    _write_meta(dst, meta)
    return meta


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
