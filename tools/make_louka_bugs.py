"""Broučci scény `louka`: stažené modely se vyhladí, nabodují na kostru a dostanou klipy.

    blender -b --python tools/make_louka_bugs.py -- bumblebee ant
    (nebo v běžícím Blenderu: BUGS = ["ant"]; exec(open("tools/make_louka_bugs.py", encoding="utf-8").read()))

Zdroje jsou v `scenes/louka/zdroje/` (autoři v ZDROJE.md). Poly by Google se skládá
z množství překrývajících se kousků bez kostry, proto se kousky slijí, vyhladí
(subdivision) a váhy kostí se počítají z polohy vrcholů: housenka a slimák mají
řetěz článků podél těla, mravenec a kobylka nohy po šesti (tripodová chůze),
čmelák křídla a hlavu. Had od Quaterniuse kostru už má, jen se zbaví pomocné koule.
Výstup: `data/models_src/<tvor>.glb`.

Pevná konvence (jako u chodců ostatních scén): chodec stojí na ose Z a kouká k -Y
(po exportu +Z). Čmelák je letec jako motýl a beruška: pohled shora, hlava +Z,
hřbet -Y, rozpětí podél X.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path(r"E:\ClaudeProjects\DinoStanice")
SRC = ROOT / "scenes/louka/zdroje"
DST = ROOT / "data/models_src"
FPS = 24

# (zdroj, úroveň vyhlazení)
MODELS = {
    "bumblebee": ("bumblebee.glb", 2),
    "ant": ("ant.glb", 1),
    "grasshopper": ("grasshopper.glb", 1),
    "caterpillar": ("caterpillar.glb", 1),
    "snail": ("snail.glb", 2),
}


# --- příprava modelu -----------------------------------------------------------

def reset():
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.actions,
                 bpy.data.materials, bpy.data.images):
        for item in list(coll):
            coll.remove(item)


def load_model(key):
    """Jeden vyhlazený mesh: kousky slité, vrcholy sloučené, subdivision aplikovaná;
    Y je délka tvora (-Y hlava), Z nahoru, stojí na zemi uprostřed."""
    file, level = MODELS[key]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(SRC / file))
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in meshes:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0004 * max(ob.dimensions))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(ob.data)
        bm.free()
        ob.parent = None
        ob.matrix_world = Matrix.Identity(4)
        for p in ob.data.polygons:
            p.use_smooth = True
        mod = ob.modifiers.new("Vyhlazeni", "SUBSURF")
        mod.levels = level
        mod.render_levels = level
    bpy.context.view_layer.update()
    for ob in meshes:
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        new = bpy.data.meshes.new_from_object(ev)
        ob.modifiers.clear()
        ob.data = new
    for o in list(bpy.data.objects):
        if o not in meshes:
            bpy.data.objects.remove(o)
    main = meshes[0]
    with bpy.context.temp_override(active_object=main, selected_editable_objects=meshes,
                                   selected_objects=meshes):
        bpy.ops.object.join()
    main.name = key
    me = main.data
    xs = [v.co for v in me.vertices]
    lo = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
    hi = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
    scale = 1.0 / (hi.y - lo.y)
    me.transform(Matrix.Scale(scale, 4) @ Matrix.Translation(
        (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    main.matrix_world = Matrix.Identity(4)
    main.data.update()
    drop_floaters(main)
    return main


def drop_floaters(ob, gap=0.02):
    """Pryč s kousky, které s tělem nesousedí (zbytky po slučování kousků zdroje)."""
    from mathutils.kdtree import KDTree
    me = ob.data
    comps = sorted(components(me), key=len, reverse=True)
    tree = KDTree(len(comps[0]))
    for n, i in enumerate(comps[0]):
        tree.insert(me.vertices[i].co, n)
    tree.balance()
    doomed = [i for comp in comps[1:] for i in comp
              if min(tree.find(me.vertices[j].co)[2] for j in comp) > gap]
    if doomed:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context="VERTS")
        bm.to_mesh(me)
        bm.free()


def components(me):
    """Souvislé kusy sítě jako seznamy indexů vrcholů."""
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    groups = {}
    for i in range(len(parent)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def kmeans_1d(values, k, rounds=12):
    vals = sorted(values)
    centres = [vals[int((i + 0.5) * len(vals) / k)] for i in range(k)]
    for _ in range(rounds):
        buckets = [[] for _ in range(k)]
        for v in vals:
            buckets[min(range(k), key=lambda i: abs(v - centres[i]))].append(v)
        centres = [sum(b) / len(b) if b else c for b, c in zip(buckets, centres)]
    return sorted(centres)


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


# --- kostra a váhy -------------------------------------------------------------

class Rig:
    """Kostry mají klidovou pózu zarovnanou se světovými osami (kost podél +Y, bez rollu),
    takže rotace v Eulerech odpovídá rotaci kolem světové osy."""

    def __init__(self, name):
        self.data = bpy.data.armatures.new(name + "Rig")
        self.ob = bpy.data.objects.new(name, self.data)
        bpy.context.scene.collection.objects.link(self.ob)
        self.defs = []
        self.weights = {}

    def bone(self, name, head, parent=None, tail=None):
        self.defs.append((name, Vector(head), parent, None if tail is None else Vector(tail)))

    def build(self, mesh_ob):
        bpy.context.view_layer.objects.active = self.ob
        bpy.ops.object.mode_set(mode="EDIT")
        eb = self.data.edit_bones
        for name, head, parent, tail in self.defs:
            b = eb.new(name)
            b.head = head
            b.tail = tail if tail is not None else head + Vector((0, 0.04, 0))
            b.roll = 0.0
            if parent:
                b.parent = eb[parent]
        bpy.ops.object.mode_set(mode="OBJECT")
        mesh_ob.parent = self.ob
        groups = {n: mesh_ob.vertex_groups.new(name=n) for n, *_ in self.defs}
        for vi, ws in self.weights.items():
            total = sum(ws.values())
            for bone, w in ws.items():
                if w > 1e-4:
                    groups[bone].add([vi], w / total, "REPLACE")
        mod = mesh_ob.modifiers.new("Armature", "ARMATURE")
        mod.object = self.ob


def key_action(arm, name, frames, pose_fn):
    """pose_fn(t 0..1) -> {kost: (rot_xyz_rad, loc_xyz)}; chybějící kost = klidová póza."""
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = action
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    for f in range(frames + 1):
        pose = pose_fn(f / frames)
        for pb in arm.pose.bones:
            rot, loc = pose.get(pb.name, ((0, 0, 0), (0, 0, 0)))
            pb.rotation_euler = rot
            pb.location = loc
            pb.keyframe_insert("rotation_euler", frame=f + 1)
            pb.keyframe_insert("location", frame=f + 1)
    track = arm.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 1, action).name = name


def export(key):
    DST.mkdir(parents=True, exist_ok=True)
    out = DST / f"{key}.glb"
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", export_animations=True,
                              export_animation_mode="ACTIONS", export_skins=True,
                              use_selection=False)
    print(key, out, out.stat().st_size // 1024, "kB")


def fix_armature_scale(path):
    """Quaternius kostra má měřítko 100 a síť 0,01 (jelen to tak má v uzlu sítě).
    Exportér Blenderu 0,01 zahodí, síť pak vyjde 100× větší než kostra a po skinningu
    se ve scéně zhroutí do bodu: had je nevidět. Vrací se měřítko na uzel sítě."""
    import json
    import struct
    d = path.read_bytes()
    n = struct.unpack("<I", d[12:16])[0]
    j = json.loads(d[20:20 + n])
    nodes = j["nodes"]
    for i, node in enumerate(nodes):
        parent = next((p for p, x in enumerate(nodes) if i in x.get("children", [])), None)
        if ("skin" in node and "scale" not in node and "matrix" not in node
                and parent is not None and nodes[parent].get("scale", [1])[0] > 50):
            node["scale"] = [0.01] * 3
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = d[:12] + struct.pack("<I", len(js)) + d[16:20] + js + d[20 + n:]
    path.write_bytes(out[:8] + struct.pack("<I", len(out)) + out[12:])


def tau(t):
    return 2 * math.pi * t


# --- housenka a slimák: řetěz článků podél těla -------------------------------

def chain_weights(rig, me, ys, names):
    """Váha vrcholu mezi dvěma sousedními kostmi řetězu podle polohy podél Y."""
    for v in me.vertices:
        y = v.co.y
        ws = {}
        if y <= ys[0]:
            ws[names[0]] = 1.0
        elif y >= ys[-1]:
            ws[names[-1]] = 1.0
        else:
            for i in range(len(ys) - 1):
                if ys[i] <= y <= ys[i + 1]:
                    k = (y - ys[i]) / (ys[i + 1] - ys[i])
                    ws[names[i]] = 1 - k
                    ws[names[i + 1]] = k
                    break
        rig.weights[v.index] = ws


def build_crawler(key, n_seg, wave_deg, period, lift=0.0, head_bone=True):
    ob = load_model(key)
    me = ob.data
    zs = [v.co.z for v in me.vertices]
    zc = (min(zs) + max(zs)) * 0.35
    rig = Rig(key.capitalize())
    ys = [-0.5 + (i + 0.5) * (1.0 / n_seg) for i in range(n_seg)]
    names = [f"Seg{i}" for i in range(n_seg)]
    rig.bone("Body", (0, 0.0, zc), None, (0, 0.04, zc))
    prev = "Body"
    for n, y in zip(names, ys):
        rig.bone(n, (0, y, zc), prev, (0, y + 0.04, zc))
        prev = n
    rig.bone("Head", (0, ys[0], zc), "Seg0", (0, ys[0] - 0.04, zc))
    chain_weights(rig, me, ys, names)
    for v in me.vertices:
        if v.co.y < ys[0] + 0.5 / n_seg * 0.6:
            rig.weights[v.index] = {"Head": 0.8, "Seg0": 0.2}
    rig.build(ob)
    arm = rig.ob
    rad = math.radians

    def walk(t):
        pose = {}
        for i, n in enumerate(names):
            ph = tau(t - i / n_seg * 1.0)
            pose[n] = ((rad(wave_deg) * math.sin(ph), 0, 0),
                       (0, 0, lift * max(0.0, math.sin(ph))))
        pose["Head"] = ((rad(wave_deg * 0.5) * math.sin(tau(t) + 1.0), 0, 0), (0, 0, 0))
        return pose

    def idle(t):
        pose = {n: ((rad(wave_deg * 0.25) * math.sin(tau(t) + i * 0.6), 0, 0), (0, 0, 0))
                for i, n in enumerate(names)}
        pose["Head"] = ((rad(wave_deg * 0.4) * math.sin(tau(t * 2)), rad(6) * math.sin(tau(t)), 0), (0, 0, 0))
        return pose

    key_action(arm, "Walk", int(period * FPS), walk)
    key_action(arm, "Idle", 3 * FPS, idle)
    arm.animation_data.action = None
    export(key)


# --- mravenec a kobylka: šest nohou, tripodová chůze --------------------------

def build_legged(key, lateral, period, swing_deg, head_len, hop=False):
    ob = load_model(key)
    me = ob.data
    zs = [v.co.z for v in me.vertices]
    ztop = max(zs)
    zb = ztop * 0.55
    fore = min(v.co.y for v in me.vertices)
    lateral_y = [v.co.y for v in me.vertices if abs(v.co.x) > lateral and v.co.y > fore + head_len]
    centres = kmeans_1d(lateral_y, 3)
    gap = min(centres[1] - centres[0], centres[2] - centres[1])
    rig = Rig(key.capitalize())
    rig.bone("Body", (0, 0, zb), None, (0, 0.04, zb))
    rig.bone("Head", (0, fore + 0.12, zb), "Body", (0, fore + 0.08, zb))
    legs = {}
    for side, sx in (("L", 1), ("R", -1)):
        for i, yc in enumerate(centres):
            legs[(side, i)] = (f"Leg{side}{i}", sx, yc)
    for v in me.vertices:
        x, y, z = v.co
        lat = smoothstep(lateral * 0.7, lateral * 1.4, abs(x))
        ws = {"Body": 1.0 - lat}
        if y < fore + head_len:
            ws = {"Head": 0.9, "Body": 0.1}
            rig.weights[v.index] = ws
            continue
        if lat > 0:
            side = "L" if x > 0 else "R"
            near = [math.exp(-((y - yc) / (gap * 0.55)) ** 2) for yc in centres]
            s = sum(near) or 1.0
            for i, n in enumerate(near):
                ws[f"Leg{side}{i}"] = lat * n / s
        rig.weights[v.index] = ws
    for (side, i), (name, sx, yc) in legs.items():
        pts = [v.co for v in me.vertices
               if rig.weights[v.index].get(name, 0) > 0.5 and (v.co.x > 0) == (sx > 0)]
        attach = Vector((sx * lateral * 0.5, yc, zb))
        tip = max(pts, key=lambda p: (p - attach).length) if pts else Vector((sx * 0.3, yc, 0))
        rig.bone(name, attach, "Body", tip.copy())
        rig.bone(name + "_end", tip, name, tip + Vector((0, 0.02, 0)))
    rig.build(ob)
    arm = rig.ob
    rad = math.radians
    group = {("L", 0): 0.0, ("R", 1): 0.0, ("L", 2): 0.0,
             ("R", 0): 0.5, ("L", 1): 0.5, ("R", 2): 0.5}

    def walk(t):
        pose = {"Body": ((0, 0, 0), (0, 0, 0.012 * abs(math.sin(tau(t * 2)))))}
        for (side, i), ph in group.items():
            a = tau(t + ph)
            scale = 1.4 if (hop and i == 2) else 1.0
            pose[f"Leg{side}{i}"] = ((rad(swing_deg) * scale * math.sin(a), 0, 0), (0, 0, 0))
        return pose

    def idle(t):
        pose = {"Head": ((rad(5) * math.sin(tau(t)), rad(8) * math.sin(tau(t * 2)), 0), (0, 0, 0)),
                "Body": ((0, 0, 0), (0, 0, 0.004 * math.sin(tau(t))))}
        return pose

    key_action(arm, "Walk", int(period * FPS), walk)
    key_action(arm, "Idle", 3 * FPS, idle)
    arm.animation_data.action = None
    export(key)


# --- čmelák: letec shora (křídla a hlava), jako motýl a beruška -----------------

def build_bumblebee():
    key = "bumblebee"
    ob = load_model(key)
    me = ob.data
    wings = {"L": [], "R": []}
    for comp in components(me):
        pts = [me.vertices[i].co for i in comp]
        zlo, zhi = min(p.z for p in pts), max(p.z for p in pts)
        cx = sum(p.x for p in pts) / len(pts)
        if zhi - zlo < 0.012 and abs(cx) > 0.05:
            wings["L" if cx > 0 else "R"].extend(comp)
    # z původních os (Z nahoru, hlava -Y) do konvence letce: hlava +Z, hřbet -Y, rozpětí X
    M = Matrix.Rotation(math.pi, 4, "Z") @ Matrix.Rotation(-math.pi / 2, 4, "X")
    me.transform(M)
    rig = Rig("Bumblebee")
    zs = [v.co.z for v in me.vertices]
    zhead = min(zs) + (max(zs) - min(zs)) * 0.72
    ycore = sum(v.co.y for v in me.vertices) / len(me.vertices)
    rig.bone("Body", (0, ycore, 0), None, (0, ycore + 0.04, 0))
    rig.bone("Head", (0, ycore, zhead), "Body", (0, ycore + 0.04, zhead))
    roots = {}
    for side in "LR":
        pts = [me.vertices[i].co.copy() for i in wings[side]]
        pts.sort(key=lambda p: abs(p.x))
        near = pts[:max(1, len(pts) // 8)]
        root = sum(near, Vector()) / len(near)
        roots[side] = root
        rig.bone("Wing" + side, root, "Body", root + Vector((0, 0.04, 0)))
    wing_set = {i: s for s, ids in wings.items() for i in ids}
    for v in me.vertices:
        if v.index in wing_set:
            rig.weights[v.index] = {"Wing" + wing_set[v.index]: 1.0}
        elif v.co.z > zhead:
            rig.weights[v.index] = {"Head": 1.0}
        else:
            rig.weights[v.index] = {"Body": 1.0}
    rig.build(ob)
    arm = rig.ob
    rad = math.radians

    def fly(t):
        a = rad(14 + 38 * math.sin(tau(t)))
        return {"WingL": ((0, 0, -a), (0, 0, 0)), "WingR": ((0, 0, a), (0, 0, 0)),
                "Body": ((rad(3) * math.sin(tau(t) + 1.0), 0, 0), (0, 0, 0))}

    def rest(t):
        a = rad(6 + 2 * math.sin(tau(t)))
        return {"WingL": ((0, 0, -a), (0, 0, 0)), "WingR": ((0, 0, a), (0, 0, 0)),
                "Head": ((0, 0, rad(7) * math.sin(tau(t * 2))), (0, 0, 0))}

    key_action(arm, "Fly", 5, fly)
    key_action(arm, "Rest", 2 * FPS, rest)
    arm.animation_data.action = None
    export(key)


# --- had: kostru i klipy má od Quaterniuse, jen se slijí plochy a postaví na zem --

def build_snake():
    key = "snake"
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(SRC / "snake_quaternius.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]
    helpers = [o for o in new if o.type == "MESH" and o.name.startswith("Icosphere")]
    new = [o for o in new if o not in helpers]
    for o in helpers:
        bpy.data.objects.remove(o)
    for ob in meshes:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        size = max(max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3))
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0008 * size)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.shade_smooth()
    arm = next(o for o in new if o.type == "ARMATURE")
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ v.co for ob in meshes for v in ob.data.vertices]
    root = arm
    while root.parent:
        root = root.parent
    root.location -= Vector(((min(p.x for p in pts) + max(p.x for p in pts)) / 2,
                             (min(p.y for p in pts) + max(p.y for p in pts)) / 2,
                             min(p.z for p in pts)))
    export(key)
    fix_armature_scale(DST / f"{key}.glb")


# --- hlavní --------------------------------------------------------------------

BUILDERS = {
    "bumblebee": build_bumblebee,
    "caterpillar": lambda: build_crawler("caterpillar", 6, 16, 1.0, lift=0.01),
    "snail": lambda: build_crawler("snail", 4, 7, 1.6),
    "snake": build_snake,
    "ant": lambda: build_legged("ant", 0.07, 0.6, 22, 0.15),
    "grasshopper": lambda: build_legged("grasshopper", 0.05, 0.9, 13, 0.11),
}


def main(names):
    for key in names:
        reset()
        bpy.context.scene.render.fps = FPS
        BUILDERS[key]()


if "--" in sys.argv:
    BUGS = sys.argv[sys.argv.index("--") + 1:] or list(BUILDERS)
elif "BUGS" not in globals():
    BUGS = list(BUILDERS)
main(BUGS)
