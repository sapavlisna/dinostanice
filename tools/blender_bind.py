"""Blender headless: navlékne nový tvar zvířete na kostru hotového modelu.

    blender -b --factory-startup --python tools/blender_bind.py -- MAPA.json VYSTUP.glb
    blender -b --factory-startup --python tools/blender_bind.py -- MAPA.json VYSTUP.glb --prep

Nové zvíře (vygenerovaný nebo vymodelovaný mesh bez kostry) dostane kostru
i všechny klipy předlohy (např. lišky z Quaternia). Kostra se přitom
**přizpůsobí tvaru**: nohy se zkrátí, aby tlapky dosáhly na zem pod
kyčlemi tvaru, a krk, hlava, uši a ocas dostanou délky podle tvaru.
Natočení kloubů v klipech zůstávají bajtově stejná, mění se jen posuny
(délky kostí) a z nich dopočítané polohy IK tlapek.

Mapa (tools/bindmaps/<zvíře>.json):

    {"template": "data/models_src/fox.glb",   předloha s kostrou a klipy
     "source": "cesta/k/meshi.glb",            glb/gltf/obj/fbx, jen tvar
     "name": "Zajic",                          jméno uzlu meshe
     "rotate_y": 90,                           natočení zdroje: hlava k +Z, nahoru +Y
     "faces": 1800,                            low-poly: decimace na tolik trojúhelníků
     "dissolve": 4,                            sloučí skoro rovinné plochy (úhel °) — větší fazety
     "keep_parts": 0.02,                       zahodí volné kusy menší než podíl vrcholů
     "cut": [[[x0, y0, z0], [x1, y1, z1]]],    smaže trojúhelníky v boxech (vousy)
     "fill_holes": true,                       díry po cut zalepí
     "chains": [["Back", "Torso", ...], ...],  řetězy kloubů předlohy (rodič -> potomek)
     "landmarks": {"Back": {"at": [x, y, z]}}, kde ty klouby leží na tvaru
     "scale_by": ["Back", "Torso3"],           měřítko tvaru = délka trupu předlohy
     "fit": ["Neck2", "Head", "Ear", "Tail"],  kosti (prefix uzlu), jejichž délka jde podle tvaru
     "aim": ["Ear1"],                          kosti, které se natočí ke konci řetězu na tvaru
     "legs": [{"root": "BackLeg.L", "end": "BackLowerLeg.L_end", "ik": "IKBackLeg.L"}],
     "leg_scale": 0.8,                         ruční délka nohou místo dopočtené
     "thickness": 1.0, "thick": {"Torso": 1.2}, tloušťka napříč kostí
     "parts": [["Usi", ["Ear"]], ...],         materiál podle převažující kosti
     "colors": {"Usi": [r, g, b], ...}}

`--prep` zapíše jen vyčištěný, zdecimovaný a natočený tvar v jednotkovém
rámci (délka 1, stojí na y=0, střed v x/z) — v něm se odečítají landmarks
(`python tools/bind_views.py PREP.glb out.png` nakreslí mřížku).

Landmarks: bod `at` v jednotkovém rámci pro kloub předlohy. Klíč s `.L`
(i `Ear4.L_end`) se zrcadlí na `.R` (x → −x), pokud nemá `"mirror": false`
(nohy v kroku). Chybějící kloub uvnitř řetězu se dopočítá na úsečce mezi
sousedy v poměru délek kostí předlohy.

Postup:
1. Tvar se zvětší tak, aby úsek `scale_by` měl délku jako v předloze, a
   postaví se na zem předlohy pod její kloub `scale_by[0]`.
2. Tělo (`Body`) předlohy se posune na výšku hřbetu tvaru — v klidu i ve
   všech klipech; pohupování se zmenší v poměru délky nohou.
3. Nohy (`legs`, .L se zrcadlí) se zkrátí/prodlouží poměrem k tak, aby
   tlapka dosáhla na zem: k = výška kyčle nová / původní, průměr přes nohy
   (stejné k vpředu i vzadu, jinak by stojící tlapky klouzaly). Uzly od `root`
   po `end` a pod `ik` mají posuny × k. IK tlapka je kořenová kost
   (v Quaterniovi sourozenec těla), v každém snímku každého klipu se proto
   přepočítá: IK = kyčel_nová + k·(IK − kyčel_původní). Natočení kloubů jsou
   stejná, takže je to přesně konec zkrácené nohy a krok je k× kratší —
   scéna měří krok z koncových kostí nohou, prokluz se tím nemění.
4. Kosti z `fit` dostanou délku podle landmarks tvaru (posun × poměr).
   Kosti z `aim` se natočí ke konci svého řetězu na tvaru: ke všem klíčům
   natočení se zprava přinásobí stálá oprava (jediná výjimka z „natočení
   beze změny“; pohyb kosti zůstává, mění se jen směr, kam míří).
5. Tvar se ohne do nové klidové kostry (segment po segmentu, váhy z bone
   heat Blenderu) a inverse bind matice se přepočítají.

Výstup je kopie GLB předlohy, ve které je vyměněný mesh, materiály, klidové
posuny a posunové křivky. Blender GLB s klipy neimportuje ani neexportuje
(export by klipy přepočítal, viz tools/blender_clips.py), takže tu není
potřeba ani oprava zavěšení na kost z tools/blender_normalize.py.
"""

import json
import re
import struct
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dinostanice.gltf import Model  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
MAP, DST = Path(argv[0]), Path(argv[1])
PREP = "--prep" in argv
CFG = json.loads(MAP.read_text(encoding="utf-8"))


def rel(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


# --- GLB jako data -------------------------------------------------------------

def read_glb(path):
    data = Path(path).read_bytes()
    chunks, off = {}, 12
    while off < len(data):
        clen, ctype = struct.unpack("<I4s", data[off:off + 8])
        chunks[ctype.rstrip(b"\x00")] = data[off + 8: off + 8 + clen]
        off += 8 + clen + (-clen % 4)
    return json.loads(chunks[b"JSON"]), bytes(chunks.get(b"BIN", b""))


def write_glb(path, g, blob):
    blob = bytearray(blob)
    blob.extend(b"\x00" * (-len(blob) % 4))
    g["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = bytearray(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob)))
    out += struct.pack("<I4s", len(js), b"JSON") + js
    out += struct.pack("<I4s", len(blob), b"BIN\x00") + blob
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)


class Packer:
    """Skládá nový BIN: kopie potřebných accessorů předlohy + nová data."""

    def __init__(self, g, blob):
        self.src_g, self.src_blob = g, blob
        self.views, self.accessors, self.blob = [], [], bytearray()
        self.copied = {}

    def _view(self, data, target=None):
        self.blob.extend(b"\x00" * (-len(self.blob) % 4))
        v = {"buffer": 0, "byteOffset": len(self.blob), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.blob.extend(data)
        self.views.append(v)
        return len(self.views) - 1

    def copy(self, idx):
        if idx not in self.copied:
            acc = dict(self.src_g["accessors"][idx])
            bv = self.src_g["bufferViews"][acc["bufferView"]]
            start = bv.get("byteOffset", 0)
            acc["bufferView"] = self._view(self.src_blob[start:start + bv["byteLength"]])
            self.accessors.append(acc)
            self.copied[idx] = len(self.accessors) - 1
        return self.copied[idx]

    def add(self, arr, kind, target=None):
        comp = {np.dtype(np.float32): 5126, np.dtype(np.uint16): 5123,
                np.dtype(np.uint32): 5125}[arr.dtype]
        acc = {"bufferView": self._view(np.ascontiguousarray(arr).tobytes(), target),
               "componentType": comp, "count": int(len(arr)), "type": kind}
        if kind == "VEC3" and comp == 5126:
            acc["min"] = [float(x) for x in arr.min(0)]
            acc["max"] = [float(x) for x in arr.max(0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def pack(g, blob, overrides, mesh=None):
    """Kopie GLB `g` s přepsanými výstupy samplerů ({(anim, sampler): pole})
    a volitelně novým meshem (primitivy, materiály, inverse bind)."""
    g = json.loads(json.dumps(g))
    pk = Packer(g, blob)
    for si, s in enumerate(g.get("skins", [])):
        if mesh is not None and si == 0:
            s["inverseBindMatrices"] = pk.add(mesh["ibm"], "MAT4")
        else:
            s["inverseBindMatrices"] = pk.copy(s["inverseBindMatrices"])
    for ai, a in enumerate(g.get("animations", [])):
        for si, smp in enumerate(a["samplers"]):
            smp["input"] = pk.copy(smp["input"])
            if (ai, si) in overrides:
                arr = overrides[ai, si].astype(np.float32)
                smp["output"] = pk.add(arr, "VEC4" if arr.shape[1] == 4 else "VEC3")
            else:
                smp["output"] = pk.copy(smp["output"])
    if mesh is None:
        for m in g.get("meshes", []):
            for p in m["primitives"]:
                p["attributes"] = {k: pk.copy(v) for k, v in p["attributes"].items()}
                if "indices" in p:
                    p["indices"] = pk.copy(p["indices"])
                p.pop("targets", None)
        for k in ("textures", "images", "samplers"):
            g.pop(k, None)
        for m in g.get("materials", []):
            for key in list(m):
                if key.endswith("Texture"):
                    m.pop(key)
            m.get("pbrMetallicRoughness", {}).pop("baseColorTexture", None)
            m.get("pbrMetallicRoughness", {}).pop("metallicRoughnessTexture", None)
    else:
        primitives = []
        for p in mesh["prims"]:
            primitives.append({"attributes": {
                "POSITION": pk.add(p["pos"], "VEC3", 34962),
                "NORMAL": pk.add(p["nrm"], "VEC3", 34962),
                "JOINTS_0": pk.add(p["j"], "VEC4", 34962),
                "WEIGHTS_0": pk.add(p["w"], "VEC4", 34962)},
                "indices": pk.add(np.arange(len(p["pos"]), dtype=np.uint32), "SCALAR", 34963),
                "material": p["material"]})
        mesh_nodes = [n for n in g["nodes"] if "skin" in n and "mesh" in n]
        if len(mesh_nodes) != 1:
            sys.exit(f"předloha má {len(mesh_nodes)} skinovaných meshů, čekám jeden")
        g["meshes"] = [{"name": mesh["name"], "primitives": primitives}]
        for n in g["nodes"]:
            n.pop("mesh", None)
        mesh_nodes[0]["mesh"] = 0
        mesh_nodes[0]["name"] = mesh["name"]
        for k in ("textures", "images", "samplers"):
            g.pop(k, None)
        g["materials"] = mesh["materials"]
        g["asset"] = dict(g.get("asset", {}), generator="DinoStanice blender_bind")
    g["accessors"], g["bufferViews"] = pk.accessors, pk.views
    return g, bytes(pk.blob)


# --- zdrojový tvar -------------------------------------------------------------

def load_source(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        sys.exit(f"neznámý formát {ext}")
    verts, tris, base = [], [], 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        me.transform(o.matrix_world)
        me.calc_loop_triangles()
        v = np.array([x.co[:] for x in me.vertices], float)
        t = np.array([x.vertices[:] for x in me.loop_triangles], np.int64)
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    v, t = np.concatenate(verts), np.concatenate(tris)
    # švy UV ze zdroje = zdvojené vrcholy; bez svaření by se tvar rozpadl na
    # tisíce „volných kusů“ a decimace by na švech trhala povrch
    q = np.round(v / (np.ptp(v, 0).max() * 1e-6)).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    v, t = v[first], inv.reshape(-1)[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    # Blender Z-up -> glTF Y-up
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1), t


def keep_big_parts(v, t, frac):
    par = np.arange(len(v))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for a, b, c in t:
        for p, q in ((a, b), (a, c)):
            rp, rq = find(p), find(q)
            if rp != rq:
                par[rp] = rq
    roots = np.array([find(i) for i in range(len(v))])
    ids, counts = np.unique(roots, return_counts=True)
    keep = set(ids[counts >= frac * len(v)])
    dropped = int(sum(c for i, c in zip(ids, counts) if i not in keep))
    t = t[np.isin(roots[t[:, 0]], list(keep))]
    print(f"PARTS {len(ids)} kusů, zahozeno {len(ids) - len(keep)} ({dropped} vrcholů)")
    return t


def decimate(v, t, faces, dissolve, fill):
    used, t = np.unique(t, return_inverse=True)
    t = t.reshape(-1, 3)
    v = v[used]
    me = bpy.data.meshes.new("src")
    # zpátky do Blenderu (Z-up), ať decimace vidí to, co importér
    me.from_pydata([(x, -z, y) for x, y, z in v], [], t.tolist())
    ob = bpy.data.objects.new("src", me)
    bpy.context.scene.collection.objects.link(ob)
    if fill:
        # díry po `cut` (vousy prorostlé hlavou) se zalepí plochou
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.quads_convert_to_tris()
        bpy.ops.object.mode_set(mode="OBJECT")
    if len(me.polygons) > faces:
        mod = ob.modifiers.new("dec", "DECIMATE")
        mod.ratio = faces / len(me.polygons)
    if dissolve:
        mod = ob.modifiers.new("planar", "DECIMATE")
        mod.decimate_type = "DISSOLVE"
        mod.angle_limit = np.radians(dissolve)
        ob.modifiers.new("tri", "TRIANGULATE")
    dg = bpy.context.evaluated_depsgraph_get()
    em = ob.evaluated_get(dg).to_mesh()
    em.calc_loop_triangles()
    vv = np.array([x.co[:] for x in em.vertices], float)
    tt = np.array([x.vertices[:] for x in em.loop_triangles], np.int64)
    print(f"DECIMATE {len(t)} -> {len(tt)} trojúhelníků ({len(used)} -> {len(vv)} vrcholů)")
    return np.stack([vv[:, 0], vv[:, 2], -vv[:, 1]], 1), tt


def unit_frame(v, rotate_y):
    a = np.radians(rotate_y)
    c, s = np.cos(a), np.sin(a)
    v = v @ np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]).T
    lo, hi = v.min(0), v.max(0)
    off = np.array([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    return (v + off) / (hi[2] - lo[2])


# --- landmarks -----------------------------------------------------------------

def is_left(name):
    return re.search(r"\.L(?=$|_)", name) is not None


def mirror(x):
    if isinstance(x, str):
        return re.sub(r"\.L(?=$|_)", ".R", x)
    if isinstance(x, list):
        return [mirror(i) for i in x] if x and isinstance(x[0], str) else [-x[0], x[1], x[2]]
    return {k: (mirror(i) if k in ("at", "root", "end", "ik") else i) for k, i in x.items()}


def with_mirrors(items):
    out = []
    for it in items:
        out.append(it)
        if any(is_left(n) for n in (it if isinstance(it, list) else [it["root"]])):
            out.append(mirror(it))
    return out


def shape_skeleton(cfg, joints):
    """Klouby tvaru (`at`) a segmenty řetězů. Chybějící kloub uvnitř řetězu
    se dopočítá na úsečce mezi sousedy v poměru délek kostí předlohy."""
    chains = with_mirrors(cfg["chains"])
    lms = {}
    for key, lm in cfg["landmarks"].items():
        lms[key] = lm
        if is_left(key) and lm.get("mirror", True):
            if mirror(key) in cfg["landmarks"]:
                sys.exit(f"{mirror(key)} je zadaný ručně, u {key} dej \"mirror\": false")
            lms[mirror(key)] = mirror(lm)
    at = {k: np.array(lm["at"], float) for k, lm in lms.items()}
    for ch in chains:
        known = [i for i, n in enumerate(ch) if n in at]
        if not known or known[0] != 0 or known[-1] != len(ch) - 1:
            sys.exit(f"řetěz {ch}: první a poslední kloub potřebují landmark")
        for p, q in zip(known, known[1:]):
            seg = [np.linalg.norm(joints[ch[i + 1]] - joints[ch[i]]) for i in range(p, q)]
            cum = np.cumsum(seg) / max(sum(seg), 1e-9)
            for i in range(p + 1, q):
                at[ch[i]] = at[ch[p]] + cum[i - p - 1] * (at[ch[q]] - at[ch[p]])
    segs = []
    for ch in chains:
        for a, b in zip(ch, ch[1:]):
            if (a, b) not in segs:
                segs.append((a, b))
    return at, segs


# --- přizpůsobení kostry tvaru ---------------------------------------------------

def descendants(tm, i):
    out, stack = [], [i]
    while stack:
        n = stack.pop()
        for c in np.where(tm.parent == n)[0]:
            out.append(int(c))
            stack.append(int(c))
    return out


def path_down(tm, top, bottom):
    """Uzly od `bottom` nahoru po `top` (bez něj)."""
    out, n = [], bottom
    while n != top:
        if n < 0:
            sys.exit(f"{tm.node_names[bottom]} není pod {tm.node_names[top]}")
        out.append(n)
        n = int(tm.parent[n])
    return out


def node_translation(n):
    return np.array(n.get("translation", [0.0, 0.0, 0.0]), float)


def translation_samplers(g, node):
    for ai, a in enumerate(g.get("animations", [])):
        for c in a["channels"]:
            if c["target"].get("node") == node and c["target"]["path"] == "translation":
                yield ai, c["sampler"]


def sampler_output(tm, ai, si):
    return tm.accessor(tm.g["animations"][ai]["samplers"][si]["output"]).astype(np.float64)


def fit_skeleton(cfg, tm, g, at):
    """Nová klidová kostra a posunové křivky podle tvaru (kroky 2–4 v hlavičce).
    Vrací (g s novými klidovými posuny, přepsané výstupy samplerů, nohy)."""
    g = json.loads(json.dumps(g))
    idx = {n: i for i, n in enumerate(tm.node_names)}
    W = tm.global_matrices(None, 0.0)
    J = {n: W[i][:3, 3] for i, n in enumerate(tm.node_names)}
    factor = {}

    # posun uzlu = kost rodiče v glTF (u lišky visí uši na krku, ne na hlavě)
    fit = cfg.get("fit", [])
    for b in at:
        p = tm.node_names[int(tm.parent[idx[b]])]
        if any(b.startswith(f) for f in fit) and p in at:
            factor[idx[b]] = np.linalg.norm(at[b] - at[p]) / np.linalg.norm(J[b] - J[p])
    fitted = sorted({tm.node_names[n].replace(".R", ".L"): round(f, 2)
                     for n, f in factor.items()}.items())

    body = idx[cfg.get("body", "Body")]
    back = cfg["scale_by"][0]
    dy = at[back][1] - J[back][1]
    pw = W[int(tm.parent[body])]
    d_local = np.linalg.inv(pw[:3, :3]) @ np.array([0.0, dy, 0.0])

    # jedno k pro všechny nohy: stojící tlapky se v klipu posouvají k× rychlostí
    # těla, s různým k vpředu a vzadu by jedny z nich klouzaly po zemi
    legs = [{"root": idx[lg["root"]], "end": idx[lg["end"]], "ik": idx[lg["ik"]],
             "name": lg["root"]} for lg in with_mirrors(cfg["legs"])]
    auto = [(J[lg["name"]][1] + dy) / J[lg["name"]][1] for lg in legs]
    k = float(cfg.get("leg_scale") or (np.mean(auto) if auto else 1.0))
    for lg in legs:
        lg["k"] = k
        for n in path_down(tm, lg["root"], lg["end"]) + descendants(tm, lg["ik"]):
            factor[n] = k
        foot = J[lg["name"]][1] + dy - k * J[lg["name"]][1]
        print(f"LEG {lg['name']}: tlapka {foot:+.3f} nad zemí")
    print(f"LEGS délka × {k:.3f} (podle kyčlí {', '.join(f'{a:.3f}' for a in auto[::2])})")
    overrides = {}

    for n, f in factor.items():
        node = g["nodes"][n]
        node["translation"] = list(node_translation(node) * f)
        for ai, si in translation_samplers(g, n):
            overrides[ai, si] = sampler_output(tm, ai, si) * f
    aim_bones(cfg, tm, g, at, J, idx, W, overrides)
    rest = node_translation(g["nodes"][body])
    g["nodes"][body]["translation"] = list(rest + d_local)
    for ai, si in translation_samplers(g, body):
        overrides[ai, si] = rest + d_local + k * (sampler_output(tm, ai, si) - rest)
    print(f"BODY posun {dy:+.3f}, pohupování × {k:.3f}")
    print("FIT " + ", ".join(f"{k} ×{v}" for k, v in fitted))
    return g, overrides, legs


def quat_mul(a, b):
    """glTF (x, y, z, w); a·b, po řádcích a."""
    x1, y1, z1, w1 = np.moveaxis(np.atleast_2d(a), -1, 0)
    x2, y2, z2, w2 = b
    return np.stack([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                     w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2], -1)


def matrix_quat(R):
    w = np.sqrt(max(1e-12, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    return np.array([(R[2, 1] - R[1, 2]) / (4 * w), (R[0, 2] - R[2, 0]) / (4 * w),
                     (R[1, 0] - R[0, 1]) / (4 * w), w])


def aim_bones(cfg, tm, g, at, J, idx, W, overrides):
    """`aim`: kost (prefix) se natočí ke konci svého řetězu na tvaru — liščí
    uši míří šikmo do stran, zaječí nahoru. Ke klíčům natočení se zprava
    přinásobí stálá oprava, takže pohyb (vrtění uší) zůstává stejný."""
    chains = with_mirrors(cfg["chains"])
    for name in list(at):
        if not any(name.startswith(p) for p in cfg.get("aim", [])):
            continue
        end = next(ch[-1] for ch in chains if name in ch)
        R = W[idx[name]][:3, :3]
        R = R / np.linalg.norm(R, axis=0)
        d_old = np.linalg.inv(R) @ (J[end] - J[name])
        d_new = np.linalg.inv(R) @ (at[end] - at[name])
        delta = matrix_quat(rotation_between(d_old / np.linalg.norm(d_old),
                                             d_new / np.linalg.norm(d_new)))
        node = g["nodes"][idx[name]]
        node["rotation"] = list(quat_mul(node.get("rotation", [0, 0, 0, 1]), delta)[0])
        for ai, a in enumerate(g.get("animations", [])):
            for c in a["channels"]:
                if c["target"].get("node") == idx[name] and c["target"]["path"] == "rotation":
                    q = sampler_output(tm, ai, c["sampler"])
                    overrides[ai, c["sampler"]] = quat_mul(q, delta)
        ang = np.degrees(2 * np.arccos(min(1.0, abs(delta[3]))))
        print(f"AIM {name} -> {end}: {ang:.0f}°")



def place_ik(tm_old, tm_new, g, overrides, legs):
    """IK tlapka = konec zkrácené nohy, v klidu i v každém snímku každého klipu."""
    names = list(tm_old.animations)
    W0, W1 = tm_old.global_matrices(None, 0.0), tm_new.global_matrices(None, 0.0)
    cache = {}

    def worlds(ai, t):
        if (ai, t) not in cache:
            cache[ai, t] = (tm_old.global_matrices(names[ai], t),
                            tm_new.global_matrices(names[ai], t))
        return cache[ai, t]

    for lg in legs:
        r, ik, k = lg["root"], lg["ik"], lg["k"]
        par = int(tm_old.parent[ik])

        def local(A, B):
            p = B[r][:3, 3] + k * (A[ik][:3, 3] - A[r][:3, 3])
            P = B[par] if par >= 0 else np.eye(4)
            return (np.linalg.inv(P) @ np.append(p, 1.0))[:3]

        g["nodes"][ik]["translation"] = list(local(W0, W1))
        for ai, si in translation_samplers(g, ik):
            times = tm_old.accessor(tm_old.g["animations"][ai]["samplers"][si]["input"])
            overrides[ai, si] = np.array([local(*worlds(ai, float(t))) for t in times.reshape(-1)])


# --- tvar do kostry --------------------------------------------------------------

def rotation_between(d, e):
    v, c = np.cross(d, e), float(d @ e)
    if c < -0.999999:
        axis = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def segment_transforms(at, to, segs, thickness, thick):
    """Afinní zobrazení segmentu tvaru na kost: podél kosti natáhne přesně
    na její délku, napříč nechá tloušťku tvaru (× thickness/thick)."""
    out = []
    for a, b in segs:
        L, l = np.linalg.norm(to[b] - to[a]), np.linalg.norm(at[b] - at[a])
        k = next((f for p, f in thick.items() if a.startswith(p)), 1.0)
        d = (at[b] - at[a]) / l
        e = (to[b] - to[a]) / L
        R = rotation_between(d, e)
        M = (L / l) * np.outer(e, d) + thickness * k * R @ (np.eye(3) - np.outer(d, d))
        out.append((M, at[a], to[a]))
    return out


def heat_weights(verts, tris, at, segs):
    """Bone heat Blenderu (Parent with Automatic Weights) na kostru tvaru."""
    bl = lambda p: (p[0], -p[2], p[1])  # noqa: E731 — glTF Y-up -> Blender Z-up
    me = bpy.data.meshes.new("tvar")
    me.from_pydata([bl(p) for p in verts], [], tris.tolist())
    ob = bpy.data.objects.new("tvar", me)
    arm_data = bpy.data.armatures.new("kostra")
    arm = bpy.data.objects.new("kostra", arm_data)
    for o in (ob, arm):
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    names = []
    for a, b in segs:
        eb = arm_data.edit_bones.new(f"{a}>{b}")
        eb.head, eb.tail = bl(at[a]), bl(at[b])
        names.append(eb.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    w = np.zeros((len(verts), len(segs)))
    col = {ob.vertex_groups[n].index: i for i, n in enumerate(names) if n in ob.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            if g.group in col:
                w[v.index, col[g.group]] = g.weight
    # vrchol, kam teplo nedošlo, dostane nejbližší segment
    lost = np.where(w.sum(1) < 1e-6)[0]
    for i in lost:
        dist = []
        for a, b in segs:
            d = at[b] - at[a]
            t = np.clip((verts[i] - at[a]) @ d / (d @ d), 0, 1)
            dist.append(np.linalg.norm(verts[i] - at[a] - t * d))
        w[i, int(np.argmin(dist))] = 1.0
    print(f"HEAT {len(segs)} kostí, bez tepla {len(lost)} vrcholů")
    return w / w.sum(1, keepdims=True)


def top4(w):
    idx = np.argsort(-w, axis=1)[:, :4]
    val = np.take_along_axis(w, idx, 1)
    val /= val.sum(1, keepdims=True)
    return idx.astype(np.uint16), val.astype(np.float32)


def face_parts(cfg, tm, w, tris):
    names = [tm.node_names[j] for j in tm.skin_joints]
    parts = cfg.get("parts", [["Main", []]])
    face_w = w[tris].sum(1)
    out = np.full(len(tris), len(parts) - 1)
    for fi, fw in enumerate(face_w):
        bone = names[int(fw.argmax())]
        for pi, (_, prefixes) in enumerate(parts):
            if any(bone.startswith(p) for p in prefixes):
                out[fi] = pi
                break
    # hranice materiálu jsou na předloze vnitřní linky: zubaté hrany podle
    # převažující kosti se vyhladí většinou sousedních trojúhelníků
    edges = {}
    for fi, tri in enumerate(tris):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges.setdefault((min(a, b), max(a, b)), []).append(fi)
    nbr = [[] for _ in tris]
    for fs in edges.values():
        for f in fs:
            nbr[f].extend(x for x in fs if x != f)
    for _ in range(int(cfg.get("smooth_parts", 3))):
        new = out.copy()
        for fi, ns in enumerate(nbr):
            if not ns:
                continue
            vals, counts = np.unique(out[ns], return_counts=True)
            if counts.max() >= 2 and vals[counts.argmax()] != out[fi]:
                new[fi] = vals[counts.argmax()]
        out = new
    return [p[0] for p in parts], out


def flat_mesh(cfg, verts, tris, part_of_face, part_names, w, inv):
    """Low-poly: každý trojúhelník vlastní vrcholy s normálou plochy."""
    colors = cfg.get("colors", {})
    prims, materials = [], []
    for pi, name in enumerate(part_names):
        ft = tris[part_of_face == pi]
        if not len(ft):
            continue
        p = verts[ft].reshape(-1, 3)
        n = np.cross(verts[ft[:, 1]] - verts[ft[:, 0]], verts[ft[:, 2]] - verts[ft[:, 0]])
        n = np.repeat(n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12), 3, 0)
        j, wt = top4(w[ft.reshape(-1)])
        pm = (np.hstack([p, np.ones((len(p), 1))]) @ inv.T)[:, :3]
        nm = n @ inv[:3, :3].T
        nm /= np.linalg.norm(nm, axis=1, keepdims=True) + 1e-12
        rgb = colors.get(name, [0.6, 0.6, 0.6])
        materials.append({"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": [*rgb, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.8}})
        prims.append({"pos": pm.astype(np.float32), "nrm": nm.astype(np.float32),
                      "j": j, "w": wt, "material": len(materials) - 1})
    return prims, materials


def write_static(verts, tris, dst):
    g = {"asset": {"version": "2.0", "generator": "DinoStanice blender_bind --prep"},
         "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "prep"}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}]}
    pk = Packer({}, b"")
    pk.add(verts.astype(np.float32), "VEC3", 34962)
    pk.add(tris.reshape(-1).astype(np.uint32), "SCALAR", 34963)
    g["accessors"], g["bufferViews"] = pk.accessors, pk.views
    write_glb(dst, g, pk.blob)


def main():
    v, t = load_source(rel(CFG["source"]))
    print(f"SOURCE {len(v)} vrcholů, {len(t)} trojúhelníků")
    v = unit_frame(v, float(CFG.get("rotate_y", 0)))
    for lo, hi in CFG.get("cut", []):
        inside = np.all((v >= lo) & (v <= hi), axis=1)
        before = len(t)
        t = t[~inside[t].any(1)]
        print(f"CUT {before - len(t)} trojúhelníků v {lo}..{hi}")
    t = keep_big_parts(v, t, float(CFG.get("keep_parts", 0.02)))
    v, t = decimate(v, t, int(CFG.get("faces", 1800)), float(CFG.get("dissolve", 0)),
                    bool(CFG.get("fill_holes")))
    v = unit_frame(v, 0.0)
    if PREP:
        write_static(v, t, DST)
        print(f"PREP {DST}")
        return

    tmpl_path = rel(CFG["template"])
    tm = Model(tmpl_path)
    g0, blob0 = read_glb(tmpl_path)
    W = tm.global_matrices(None, 0.0)
    joints = {n: W[i][:3, 3] for i, n in enumerate(tm.node_names)}
    at, segs = shape_skeleton(CFG, joints)

    # 1. tvar do měřítka a polohy předlohy
    a, b = CFG["scale_by"]
    s = np.linalg.norm(joints[b] - joints[a]) / np.linalg.norm(at[b] - at[a])
    off = np.array([joints[a][0], 0.0, joints[a][2]]) - s * np.array([at[a][0], 0.0, at[a][2]])
    v = s * v + off
    at = {k: s * p + off for k, p in at.items()}
    print(f"SCALE tvar × {s:.3f}")

    # 2.–4. kostra podle tvaru
    g1, overrides, legs = fit_skeleton(CFG, tm, g0, at)
    tmp = DST.with_suffix(".kostra.glb")
    write_glb(tmp, *pack(g1, blob0, overrides))
    place_ik(tm, Model(tmp), g1, overrides, legs)
    write_glb(tmp, *pack(g1, blob0, overrides))
    tm1 = Model(tmp)
    tmp.unlink()

    # 5. tvar do nové kostry
    W1 = tm1.global_matrices(None, 0.0)
    to = {n: W1[i][:3, 3] for i, n in enumerate(tm1.node_names)}
    ws = heat_weights(v, t, at, segs)
    tf = segment_transforms(at, to, segs, float(CFG.get("thickness", 1.0)), CFG.get("thick", {}))
    v = sum(ws[:, k:k + 1] * ((v - p) @ M.T + q) for k, (M, p, q) in enumerate(tf))
    skin = {tm.node_names[j]: i for i, j in enumerate(tm.skin_joints)}
    w = np.zeros((len(v), len(skin)))
    for k, (a, _) in enumerate(segs):
        if a not in skin:
            sys.exit(f"kloub {a} není v kostře předlohy (skin)")
        w[:, skin[a]] += ws[:, k]
    part_names, part_of_face = face_parts(CFG, tm, w, t)
    for pi, name in enumerate(part_names):
        print(f"PART {name}: {int((part_of_face == pi).sum())} trojúhelníků")

    bind = W[tm.skin_joints[0]] @ tm.inverse_bind[0]
    ibm = np.stack([np.linalg.inv(W1[j]) @ bind for j in tm.skin_joints])
    prims, materials = flat_mesh(CFG, v, t, part_of_face, part_names, w, np.linalg.inv(bind))
    mesh = {"name": CFG.get("name", "Bound"), "prims": prims, "materials": materials,
            "ibm": ibm.transpose(0, 2, 1).reshape(-1, 16).astype(np.float32)}
    write_glb(DST, *pack(g1, blob0, overrides, mesh))
    print(f"BOUND {DST} ({len(t)} trojúhelníků)")


main()
