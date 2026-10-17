"""Scény a jejich tvorové: založení, import modelů, kontrola.

    python tools/scena.py nova les --z cretaceous          nová scéna podle vzoru
    python tools/scena.py import les                       modely ze scenes/les/modely/
    python tools/scena.py import les --bez-blenderu        jen hotová GLB, bez převodu
    python tools/scena.py kontrola les                     co by importu vadilo

Import vezme každý soubor ve `scenes/<key>/modely/` (glb, gltf, fbx, obj,
blend), Blenderem ho srovná do GLB (`tools/blender_normalize.py`) a uloží
do `data/models_src/<tvor>.glb`. Tvora, který ve scene.json ještě není,
zapíše s odhadnutým pohybem a rolemi klipů, přidělí mu index značky
(`scenes/markers.json`, jen přibývá) a vygeneruje předlohu i model pro scénu.
Pak stačí restartovat server.

Výjimky (natočení, oko, pohled shora…) se ladí ve scene.json u tvora;
`"import": {"rotate_y": 90}` otočí model při převodu. Po změně stačí import
pustit znovu.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.path.insert(0, str(ROOT))

from dinostanice import scenes  # noqa: E402
from dinostanice.creatures3d import CLIP_FOR_DEFAULT, FIRST_MARKER  # noqa: E402
from dinostanice.gltf import Model  # noqa: E402
from dinostanice.markers import MAX_CREATURE_INDEX  # noqa: E402

SCENES = ROOT / "scenes"
SRC = ROOT / "data/models_src"
FORMATS = (".glb", ".gltf", ".fbx", ".obj", ".blend")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
DEFAULT_BLENDER = r"E:\FS25-edit\blender-5.1.2-windows-x64\blender.exe"

# synonyma rolí: když model nemá přesně jméno z CLIP_FOR_DEFAULT
ROLE_GUESS = {
    "move": ["Walk", "Walking", "Run", "Swim", "Swimming", "Normal", "Flying", "Fly", "Sail"],
    "stand": ["Idle", "Stand"],
    "jump": ["Jump"],
    "lie": ["Death", "Die", "Sleep", "Lie"],
    "fast": ["Fast", "Run", "Sprint"],
}


def read_env(name):
    val = os.environ.get(name)
    if val:
        return val
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"')
    return None


def scene_path(key):
    return SCENES / key / "scene.json"


def load_scene(key):
    p = scene_path(key)
    if not p.exists():
        sys.exit(f"scéna {key} neexistuje ({p})")
    return json.loads(p.read_text(encoding="utf-8"))


def save_scene(key, data):
    scene_path(key).write_text(scenes.dumps(data), encoding="utf-8")


# --- nova -------------------------------------------------------------------

def cmd_nova(args):
    key = args.key
    if not KEY_RE.match(key):
        sys.exit("klíč scény: malá písmena, číslice a _, začíná písmenem")
    if (SCENES / key).exists():
        sys.exit(f"scéna {key} už existuje")
    vzor = load_scene(args.z)
    owner = load_scene(vzor.get("catalogue", args.z))
    data = {"label": args.label or key.replace("_", " ").capitalize(),
            "subtitle": "Popis scény pro kartu v adminu.",
            "order": max((s.order for s in scenes.SCENES), default=0) + 1}
    for k in scenes.INHERITED:
        data[k] = vzor.get(k, owner.get(k))
    data["creatures"] = []
    (SCENES / key / "modely").mkdir(parents=True)
    shutil.copy(SCENES / args.z / "render.js", SCENES / key / "render.js")
    save_scene(key, data)
    print(f"""Scéna {key} založená podle {args.z}:
  scenes/{key}/scene.json   jméno, popis, texty pro děti (přepiš je)
  scenes/{key}/render.js    krajina a pohyb (zatím kopie {args.z})
  scenes/{key}/modely/      sem dej modely tvorů (glb/fbx/obj/blend)
Pak: python tools/scena.py import {key}""")


# --- kontrola modelu --------------------------------------------------------

def short(name):
    """Krátké jméno klipu stejně jako tools/model_export3d.py."""
    return name.split("|")[-1].split("_")[-1]


def guess_motion(clips):
    low = " ".join(clips).lower()
    for motion, words in (("swim", ("swim",)), ("fly", ("fly", "flying")),
                          ("walk", ("walk", "run"))):
        if any(w in low for w in words):
            return motion
    return "walk"


def guess_roles(motion, model):
    shorts = {short(n): n for n in model.animations}
    roles = {}
    for role, default in CLIP_FOR_DEFAULT.get(motion, {}).items():
        if model.clip(default) and short(model.clip(default)) == default:
            continue
        for cand in [default] + ROLE_GUESS.get(role, []):
            hit = next((s for s in shorts if s.lower() == cand.lower()), None)
            if hit:
                if hit != default:
                    roles[role] = hit
                break
        else:
            if role != "move":
                # role, kterou model nemá, spadne na pohyb (jako manta)
                roles[role] = roles.get("move", CLIP_FOR_DEFAULT[motion]["move"])
    return roles


def check_model(path, entry):
    """Seznam problémů (prázdný = v pořádku) a model."""
    problems = []
    try:
        model = Model(path)
    except Exception as e:  # noqa: BLE001 — chceme čitelnou hlášku, ne traceback
        return [f"GLB nejde přečíst: {e}"], None
    motion = entry.get("motion", "walk")
    if model.skin_joints is None:
        problems.append("model nemá kostru (skin) — tvor by se nehýbal. Statický model "
                        "potřebuje kostru dopsat jako tools/make_axolotl.py.")
    if not model.animations:
        problems.append("model nemá žádnou animaci")
    roles = {**CLIP_FOR_DEFAULT.get(motion, {}), **entry.get("clip_for", {})}
    shorts = {short(n) for n in model.animations}
    for role, name in roles.items():
        if name not in shorts:
            problems.append(f"role {role!r} míří na klip {name!r}, model má {sorted(shorts)} "
                            f"— oprav clip_for ve scene.json")
    names = [n.get("name", "") for n in model.g.get("nodes", [])]
    # stejné pravidlo jako feetOf() ve web/scene3d.js: chodidla, jinak špičky nohou
    if motion == "walk" and not any(re.search(r"foot|toe|paw|hoof", n, re.I)
                                    or re.search(r"leg.*_end$", n, re.I) for n in names):
        problems.append("chodec nemá kosti nohou (foot/toe/paw/hoof ani špičku *Leg*_end) "
                        "— scéna nezměří krok a nohy budou klouzat; zvaž motion swim/fly "
                        "nebo stride_rate")
    eye = entry.get("eye_joint", "Head")
    if eye not in names:
        problems.append(f"kost oka {eye!r} chybí (kosti: {', '.join(names[:12])}…) "
                        f"— nastav eye_joint ve scene.json")
    poses = entry.get("poses", ["Walk"])
    if not any(model.clip(p) for p in poses):
        problems.append(f"žádná z póz předlohy {poses} není mezi klipy — nastav poses")
    return problems, model


# --- import -----------------------------------------------------------------

def normalize(src, dst, opts, use_blender):
    if not use_blender:
        if src.suffix.lower() != ".glb":
            sys.exit(f"{src.name}: bez Blenderu jde importovat jen .glb")
        shutil.copy(src, dst)
        return
    blender = read_env("BLENDER") or DEFAULT_BLENDER
    if not Path(blender).exists():
        sys.exit(f"Blender nenalezen ({blender}). Nastav BLENDER v .env, nebo "
                 f"použij --bez-blenderu pro hotová GLB.")
    r = subprocess.run([blender, "-b", "--factory-startup", "--python",
                        str(ROOT / "tools/blender_normalize.py"), "--",
                        str(src), str(dst), json.dumps(opts)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not dst.exists():
        sys.exit(f"Blender selhal u {src.name}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    for line in r.stdout.splitlines():
        if line.startswith(("DECIMATE", "RIGID")):
            print("  " + line)


def ground(path):
    """Postaví model na zem (y=0) a doprostřed — počítáno v klidové póze tak,
    jak ji pózuje stanice. Posouvá jen kořen StationRoot z Blenderu."""
    model = Model(path)
    roots = [i for i, n in enumerate(model.g.get("nodes", [])) if n.get("name") == "StationRoot"]
    if not roots:
        return
    verts, _ = model.posed(None, 0.0)
    lo, hi = verts.min(0), verts.max(0)
    shift = [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2]
    node = model.g["nodes"][roots[0]]
    tr = node.get("translation", [0.0, 0.0, 0.0])
    node["translation"] = [float(a + b) for a, b in zip(tr, shift)]
    bind_mesh_nodes(model)
    raw = Path(path).read_bytes()
    jlen = struct.unpack_from("<I", raw, 12)[0]
    rest = raw[20 + jlen:]
    js = json.dumps(model.g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + len(rest))
    out += struct.pack("<I4s", len(js), b"JSON") + js + rest
    Path(path).write_bytes(out)


def bind_mesh_nodes(model):
    """Uzel skinovaného meshe postaví tam, kam ho kreslí kostra.

    Vykreslení uzel skinovaného meshe ignoruje (glTF i three.js berou jen
    klouby × inverse bind), scéna z něj ale měří velikost a natočení tvora
    (web/scene3d.js measure()). Blender ho věší pod armaturu, takže u modelu
    s armaturou ve 100× (Quaternius) by tvor vyšel stokrát menší a s
    prohozenými osami. Uzel dostane přesně tu transformaci, kterou mají
    vrcholy v klidové póze — kresba se tím nemění."""
    world = model.global_matrices(None, 0.0)
    if model.skin_joints is None:
        return
    bind = world[model.skin_joints[0]] @ model.inverse_bind[0]
    animated = {c["target"].get("node") for a in model.g.get("animations", [])
                for c in a["channels"]}
    for i, n in enumerate(model.g["nodes"]):
        if "skin" not in n or i in animated:
            continue
        if np.allclose(world[i], bind, atol=1e-6):
            continue
        p = model.parent[i]
        local = bind if p < 0 else np.linalg.inv(world[p]) @ bind
        for k in ("translation", "rotation", "scale"):
            n.pop(k, None)
        n["matrix"] = [float(v) for v in local.T.reshape(-1)]


def assign_markers(keys):
    path = Path(scenes.MARKERS_PATH)
    reg = scenes.load_markers()
    used = set(reg.values())
    nxt = max(used | {FIRST_MARKER - 1}) + 1
    for k in keys:
        if k in reg:
            continue
        while nxt in used:
            nxt += 1
        if nxt > MAX_CREATURE_INDEX:
            sys.exit("došly indexy značek (slovník 4X4_1000)")
        reg[k] = nxt
        used.add(nxt)
        print(f"  {k}: index značky {nxt}")
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_import(args, check_only=False):
    key = args.key
    data = load_scene(key)
    if data.get("catalogue", key) != key:
        sys.exit(f"scéna {key} sdílí tvory se scénou {data['catalogue']} — importuj tam")
    creatures = data.setdefault("creatures", [])
    by_key = {c["key"]: c for c in creatures}
    folder = SCENES / key / "modely"
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in FORMATS) \
        if folder.exists() else []
    if not files:
        sys.exit(f"ve scenes/{key}/modely/ nejsou žádné modely ({', '.join(FORMATS)})")

    all_keys = {m for sc in scenes.SCENES for m in (c["key"] for c in sc.creatures)}
    todo, failed = [], False
    for f in files:
        ck = re.sub(r"[^a-z0-9_]", "_", f.stem.lower()).strip("_")
        if not KEY_RE.match(ck):
            print(f"✗ {f.name}: z názvu nejde udělat klíč tvora — přejmenuj soubor")
            failed = True
            continue
        if ck in all_keys and ck not in by_key:
            print(f"✗ {f.name}: tvor {ck} už patří jiné scéně — přejmenuj soubor")
            failed = True
            continue
        entry = by_key.get(ck) or {"key": ck, "label": f.stem.replace("_", " ").capitalize(),
                                   "glb": f"{ck}.glb"}
        dst = SRC / entry["glb"]
        if check_only:
            tmp = ROOT / "tmp" / "scena_kontrola"
            tmp.mkdir(parents=True, exist_ok=True)
            dst = tmp / entry["glb"]
        print(f"• {f.name} -> {entry['key']}")
        normalize(f, dst, entry.get("import", {}), not args.bez_blenderu)
        ground(dst)
        if ck not in by_key:
            model = Model(dst)
            entry["motion"] = guess_motion(list(model.animations))
            roles = guess_roles(entry["motion"], model)
            if roles:
                entry["clip_for"] = roles
            if entry["motion"] != "walk" or not model.clip("Walk"):
                move = entry.get("clip_for", {}).get("move") \
                    or CLIP_FOR_DEFAULT[entry["motion"]]["move"]
                full = model.clip(move)
                if full:
                    entry["poses"] = [full.split("|")[-1]]
        problems, _ = check_model(dst, entry)
        for p in problems:
            print(f"  ✗ {p}")
        if problems:
            failed = True
            continue
        print(f"  ✓ {entry['motion']}, klipy {sorted({short(n) for n in Model(dst).animations})}")
        if ck not in by_key:
            creatures.append(entry)
            by_key[ck] = entry
        todo.append(ck)

    if check_only:
        return
    save_scene(key, data)
    if failed:
        print("\nNěco neprošlo — oprav scene.json / modely a pusť import znovu. "
              "Co prošlo, je zapsané ve scene.json.")
    if not todo:
        sys.exit(1)
    assign_markers(todo)
    for tool in ("model_sheet.py", "model_export3d.py"):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / tool), *todo])
        if r.returncode:
            sys.exit(f"{tool} selhal")
    print(f"\nHotovo: {len(todo)} tvorů. Náhledy předloh v out/<tvor>_sheet.png, "
          f"předlohy k tisku v data/templates/. Restartuj server.")
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nova", help="založit scénu podle vzoru")
    n.add_argument("key")
    n.add_argument("--z", required=True, help="vzorová scéna (krajina a texty)")
    n.add_argument("--label")
    for name in ("import", "kontrola"):
        p = sub.add_parser(name)
        p.add_argument("key")
        p.add_argument("--bez-blenderu", action="store_true")
    args = ap.parse_args()
    if args.cmd == "nova":
        cmd_nova(args)
    else:
        cmd_import(args, check_only=args.cmd == "kontrola")


if __name__ == "__main__":
    main()
