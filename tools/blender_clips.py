"""Blender headless: dopíše do riggovaného GLB klipy, které autor modelu nemá.

    blender -b --factory-startup --python tools/blender_clips.py -- VSTUP.glb MAPA.json VYSTUP.glb

Přidá akce Sit (sedne si a drží), LieDown (lehne si a drží), Sleep (leží
a pomalu dýchá, smyčka) a LookAround (rozhlédne se vlevo/vpravo, smyčka nad
Idle). Jména dostanou předponu klipu Idle („Armature|TRex_Idle“ →
„Armature|TRex_Sit“), takže je `Model.clip("Sit")` i katalog najdou.

Mapa kostí (tools/clipmaps/<model>.json) říká, co je páteř, krk, hlava, ocas
a nohy; `plan` („biped“/„quadruped“) vybere sadu póz. Všechny pózy se zadávají
ve světových osách zvířete (dopředu = od kyčlí k hlavě, nahoru = Z), ne v osách
jednotlivých kostí — proto stačí vyměnit mapu a skript jde na jiný model.
Nohy jsou v `legs` pod klíči začínajícími `front`/`back` (horní a dolní kost
a chodidlo); `"ik": false` je pro ruce dvounožce, které se jen pokrčí.
`tweaks` v mapě přepíše parametry jednotlivých póz („sit“, „lie“…).

Pózování:
- základ je první snímek Idle (u LookAround celý Idle pod ním), takže klip
  navazuje na stávající animace bez skoku,
- tělo se nakloní a spustí, páteř/krk/hlava/ocas se ohnou o úhly rozložené
  po řetězu kostí,
- nohy řeší dvoukloubové IK: chodidlo zůstane na zemi (nebo se posune), koleno
  se ohne na stranu, kam je ohnuté v Idle,
- celé zvíře se nakonec posadí na zem (nejnižší vrchol = zem v Idle).

Původní klipy se nemění ani o bajt: Blender je při exportu přepočítá ke své
klidové póze, která se u modelů z FBX2glTF od uzlů v GLB liší (kosti, které
Idle neanimuje, by se posunuly). Nové akce se proto vyexportují zvlášť a do
kopie původního GLB se jen připíšou. Ze stejného důvodu se klidová póza bere
z uzlů GLB (import bez animací), ne z Blenderu.
"""

import json
import math
import struct
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, MAP, DST = Path(argv[0]), Path(argv[1]), Path(argv[2])
BMAP = json.loads(MAP.read_text(encoding="utf-8"))
FPS = 24
STEP = 2
KNEE_CLEARANCE = 0.12


# --- GLB jako data -------------------------------------------------------------

def read_glb(path):
    data = Path(path).read_bytes()
    chunks, off = {}, 12
    while off < len(data):
        clen, ctype = struct.unpack("<I4s", data[off:off + 8])
        chunks[ctype.rstrip(b"\x00")] = data[off + 8: off + 8 + clen]
        off += 8 + clen + (-clen % 4)
    return json.loads(chunks[b"JSON"]), bytearray(chunks.get(b"BIN", b""))


def write_glb(path, g, blob):
    blob = bytearray(blob)
    blob.extend(b"\x00" * (-len(blob) % 4))
    g["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = bytearray(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob)))
    out += struct.pack("<I4s", len(js), b"JSON") + js
    out += struct.pack("<I4s", len(blob), b"BIN\x00") + blob
    Path(path).write_bytes(out)


def merge_animations(orig_path, new_path, names, dst):
    """Připíše animace `names` z new_path do kopie orig_path (uzly podle jména)."""
    g, blob = read_glb(orig_path)
    ng, nblob = read_glb(new_path)
    node_by_name = {n.get("name"): i for i, n in enumerate(g["nodes"])}
    copied = {}

    def copy_accessor(idx):
        if idx in copied:
            return copied[idx]
        acc = dict(ng["accessors"][idx])
        bv = ng["bufferViews"][acc["bufferView"]]
        start = bv.get("byteOffset", 0)
        blob.extend(b"\x00" * (-len(blob) % 4))
        g["bufferViews"].append({"buffer": 0, "byteOffset": len(blob),
                                 "byteLength": bv["byteLength"]})
        blob.extend(nblob[start:start + bv["byteLength"]])
        acc["bufferView"] = len(g["bufferViews"]) - 1
        g["accessors"].append(acc)
        copied[idx] = len(g["accessors"]) - 1
        return copied[idx]

    g.setdefault("animations", [])
    have = {a.get("name") for a in g["animations"]}
    for anim in ng.get("animations", []):
        if anim.get("name") not in names:
            continue
        if anim["name"] in have:
            sys.exit(f"animace {anim['name']} už v modelu je")
        samplers = [{"input": copy_accessor(s["input"]), "output": copy_accessor(s["output"]),
                     "interpolation": s.get("interpolation", "LINEAR")} for s in anim["samplers"]]
        channels = []
        for ch in anim["channels"]:
            name = ng["nodes"][ch["target"]["node"]].get("name")
            if name not in node_by_name:
                sys.exit(f"uzel {name} v původním modelu chybí")
            channels.append({"sampler": ch["sampler"],
                             "target": {"node": node_by_name[name], "path": ch["target"]["path"]}})
        g["animations"].append({"name": anim["name"], "channels": channels, "samplers": samplers})
    write_glb(dst, g, blob)


# --- import --------------------------------------------------------------------

def import_glb(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    shapes = {pb.custom_shape for o in bpy.data.objects if o.type == "ARMATURE"
              for pb in o.pose.bones if pb.custom_shape}
    for s in shapes:
        bpy.data.objects.remove(s)
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    return arm


def node_pose(path, tmpdir):
    """Póza kostí z uzlů GLB — tu vidí three.js u kostí, které klip neanimuje."""
    g, blob = read_glb(path)
    g.pop("animations", None)
    bare = Path(tmpdir) / "bez_animaci.glb"
    write_glb(bare, g, blob)
    arm = import_glb(bare)
    return {pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(), pb.scale.copy())
            for pb in arm.pose.bones}


# --- pózování ------------------------------------------------------------------

PARAMS = ("drop", "pitch", "spine", "spine_yaw", "neck_p", "neck_y", "neck_r",
          "head_p", "head_y", "head_r", "tail_base", "tail_tip", "tail_yaw",
          "back_dx", "back_dz", "back_tuck", "front_dx", "front_dz", "front_tuck",
          "arm_up", "arm_low", "back_foot_p", "front_foot_p")


class Poser:
    def __init__(self, arm, rest_basis):
        self.arm = arm
        self.pb = arm.pose.bones
        self.rest_basis = rest_basis
        self.scale = arm.matrix_world.to_scale()[0]
        anims = {a.name: a for a in bpy.data.actions}
        idle = [n for n in anims if n.split("|")[-1].split("_")[-1] == BMAP.get("idle", "Idle")]
        if not idle:
            sys.exit("model nemá klip Idle")
        self.idle = anims[idle[0]]
        self.prefix = idle[0][: -len(BMAP.get("idle", "Idle"))]
        self.idle_frames = int(round(self.idle.frame_range[1]))
        bag = self.idle.layers[0].strips[0].channelbag(self.idle.slots[0])
        self.idle_curves = []
        for fc in bag.fcurves:
            bone, prop = fc.data_path.split('"]', 1)
            pb = self.pb[bone.split('["', 1)[1]]
            self.idle_curves.append((pb, prop.lstrip("."), fc.array_index, fc))
        self.mesh = [o for o in bpy.context.scene.objects
                     if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]

        self.set_idle(0)
        inv = arm.matrix_world.to_3x3().normalized().inverted()
        self.up = (inv @ Vector((0, 0, 1))).normalized()
        spine0 = self.pb[BMAP["spine"][0]].head
        fwd = self.pb[BMAP["head"]].head - spine0
        fwd -= self.up * fwd.dot(self.up)
        self.fwd = fwd.normalized()
        self.right = self.fwd.cross(self.up).normalized()
        self.ground_z = self.min_z()
        self.legs = {}
        for key, leg in BMAP["legs"].items():
            up, low = self.pb[leg["upper"]], self.pb[leg["lower"]]
            foot = self.pb[leg["foot"]]
            free = foot.parent.name != leg["lower"]
            self.legs[key] = dict(
                leg, free=free,
                group="front" if key.startswith("front") else "back",
                a=(low.head - up.head).length,
                b=(foot.head - low.head).length,
                ankle_local=low.matrix.inverted() @ foot.head,
                target=foot.head.copy(),
                pole=low.head - up.head,
                foot_matrix=foot.matrix.copy())
        backs = [self.pb[l["upper"]].head for k, l in BMAP["legs"].items() if k.startswith("back")]
        self.hip_h = (self.world(sum(backs, Vector()) / len(backs)).z - self.ground_z) / self.scale

    def world(self, v):
        return self.arm.matrix_world @ v

    def update(self):
        bpy.context.view_layer.update()

    def min_z(self):
        self.update()
        dg = bpy.context.evaluated_depsgraph_get()
        low = math.inf
        for o in self.mesh:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            mw = ev.matrix_world
            low = min(low, min((mw @ v.co).z for v in me.vertices))
            ev.to_mesh_clear()
        return low

    def set_idle(self, frame):
        """Póza Idle ve snímku `frame`: uzly GLB + to, co Idle animuje.

        Křivky se vyhodnocují přímo, takže nezáleží na tom, jakou akci
        a snímek má scéna zrovna nastavené."""
        for pb in self.pb:
            loc, rot, sc = self.rest_basis[pb.name]
            pb.location, pb.rotation_quaternion, pb.scale = loc, rot, sc
        for pb, prop, index, fc in self.idle_curves:
            getattr(pb, prop)[index] = fc.evaluate(frame)
        self.update()

    def snapshot(self):
        return {pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(), pb.scale.copy())
                for pb in self.pb}

    # pohyby v prostoru armatury; po každém se přepočítají potomci
    def rotate(self, name, axis, deg, pivot=None):
        if not deg:
            return
        pb = self.pb[name]
        m = pb.matrix.copy()
        p = m.translation.copy() if pivot is None else pivot
        r = Matrix.Rotation(math.radians(deg), 4, axis)
        pb.matrix = Matrix.Translation(p) @ r @ Matrix.Translation(-p) @ m
        self.update()

    def turn(self, name, q, pivot):
        pb = self.pb[name]
        r = q.to_matrix().to_4x4()
        pb.matrix = Matrix.Translation(pivot) @ r @ Matrix.Translation(-pivot) @ pb.matrix
        self.update()

    def move(self, name, v):
        pb = self.pb[name]
        pb.matrix = Matrix.Translation(v) @ pb.matrix
        self.update()

    def chain(self, names, axis, total):
        for name in names:
            self.rotate(name, axis, total / len(names))

    def taper(self, names, axis, first, last):
        """Každá kost řetězu zvlášť, úhel plynule od první k poslední."""
        n = len(names)
        for i, name in enumerate(names):
            self.rotate(name, axis, first + (last - first) * (i / (n - 1) if n > 1 else 0.0))

    def pivot(self, kind):
        if kind == "front":
            heads = [self.pb[l["upper"]].head for k, l in BMAP["legs"].items() if k.startswith("front")]
        elif kind == "back":
            heads = [self.pb[l["upper"]].head for k, l in BMAP["legs"].items() if k.startswith("back")]
        else:
            return None
        return sum(heads, Vector()) / len(heads)

    def ik(self, leg, target):
        up, low = self.pb[leg["upper"]], self.pb[leg["lower"]]
        h = up.head.copy()
        a, b = leg["a"], leg["b"]
        to = target - h
        eps = 1e-5 * (a + b)
        d = min(max(to.length, abs(a - b) + eps), a + b - eps)
        axis = to.normalized()
        knee_now = low.head.copy()
        # ohyb jako v Idle ve světě, ne s tělem: při posazení by se jinak
        # loket přetočil dopředu
        pole = leg["pole"] - axis * leg["pole"].dot(axis)
        if pole.length < 1e-3 * a:
            pole = self.fwd * (1 if leg.get("bend", "forward") == "forward" else -1)
            pole -= axis * pole.dot(axis)
        pole.normalize()
        along = (a * a - b * b + d * d) / (2 * d)
        knee = self.knee(h + axis * along, math.sqrt(max(a * a - along * along, 0.0)), pole, axis)
        self.turn(leg["upper"], (knee_now - h).rotation_difference(knee - h), h)
        ankle_now = low.matrix @ leg["ankle_local"]
        reach = h + axis * d
        self.turn(leg["lower"], (ankle_now - knee).rotation_difference(reach - knee), knee)
        return low.matrix @ leg["ankle_local"]

    def knee(self, centre, radius, pole, axis):
        """Koleno na kružnici kolem osy kyčel–kotník: co nejblíž směru z Idle,
        ale nad zemí. Při lehnutí by ho jinak IK zarazilo do podlahy a celé
        zvíře by se pak zvedlo na kolenou."""
        floor = self.ground_z + KNEE_CLEARANCE * self.hip_h * self.scale
        side = axis.cross(pole)
        if self.world(centre + pole * radius).z >= floor:
            return centre + pole * radius
        best, best_score, highest = None, -math.inf, None
        for step in range(180):
            th = math.radians(2 * step)
            d = pole * math.cos(th) + side * math.sin(th)
            k = centre + d * radius
            if highest is None or self.world(k).z > self.world(highest).z:
                highest = k
            # do strany (od těla) se koleno vytáčet nemá, raději nahoru
            score = d.dot(pole) - abs(d.dot(self.right))
            if self.world(k).z >= floor and score > best_score:
                best, best_score = k, score
        return best if best is not None else highest

    def pose(self, p, pivot, legs, ground):
        P = {k: p.get(k, 0.0) for k in PARAMS}
        hh = self.hip_h
        body = BMAP["body"]
        self.rotate(body, self.right, P["pitch"], self.pivot(pivot))
        if P["drop"]:
            self.move(body, -self.up * P["drop"] * hh)
        self.chain(BMAP["spine"], self.right, P["spine"])
        self.chain(BMAP["spine"], self.up, P["spine_yaw"])
        for axis, key in ((self.right, "neck_p"), (self.up, "neck_y"), (self.fwd, "neck_r")):
            self.chain(BMAP["neck"], axis, P[key])
        for axis, key in ((self.right, "head_p"), (self.up, "head_y"), (self.fwd, "head_r")):
            self.rotate(BMAP["head"], axis, P[key])
        if BMAP.get("tail"):
            self.taper(BMAP["tail"], self.right, P["tail_base"], P["tail_tip"])
            self.chain(BMAP["tail"], self.up, P["tail_yaw"])
        if not legs:
            return
        for key, leg in self.legs.items():
            g = leg["group"]
            if leg.get("ik", True):
                t = leg["target"]
                if P[g + "_tuck"]:
                    hip = self.pb[leg["upper"]].head
                    under = hip - self.up * (hip - t).dot(self.up)
                    t = t.lerp(under, P[g + "_tuck"])
                t = t + (self.fwd * P[g + "_dx"] + self.up * P[g + "_dz"]) * hh
                ankle = self.ik(leg, t)
            else:
                self.rotate(leg["upper"], self.right, P["arm_up"])
                self.rotate(leg["lower"], self.right, P["arm_low"])
                ankle = None
            if leg["free"] and ankle is not None:
                m = leg["foot_matrix"].copy()
                m.translation = ankle
                self.pb[leg["foot"]].matrix = m
                self.update()
                self.rotate(leg["foot"], self.right, P[g + "_foot_p"])
        if ground:
            dz = self.ground_z - self.min_z()
            self.move(BMAP["root"], self.up * dz / self.scale)


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def params_at(keys, t):
    if t <= keys[0][0]:
        return dict(keys[0][1])
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t <= t1:
            u = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            return {k: p0.get(k, 0.0) * (1 - u) + p1.get(k, 0.0) * u for k in set(p0) | set(p1)}
    return dict(keys[-1][1])


def add(*ps):
    out = {}
    for p in ps:
        for k, v in p.items():
            out[k] = out.get(k, 0.0) + v
    return out


# --- pózy ----------------------------------------------------------------------
# Úhly ve stupních ve světových osách zvířete: pitch kladný = přední konec nahoru
# (u ocasu, který míří dozadu, tedy kladný = dolů),
# yaw kladný = doleva, drop = podíl výšky kyčlí, *_dx/*_dz = posun chodidla
# dopředu/nahoru v podílech výšky kyčlí; *_tuck 0..1 přesune chodidlo z místa,
# kde stálo v Idle, pod kyčel (pak *_dx měří od kyčle a nohy jsou souměrné).

POSES = {
    "biped": {
        "sit": dict(pitch=24, drop=0.42, neck_p=-12, head_p=-8, tail_base=-14, tail_tip=22,
                    back_dx=0.12, arm_up=10, arm_low=-10),
        "crouch": dict(drop=0.35, pitch=-4, neck_p=-8, head_p=-4, tail_base=-4, tail_tip=6),
        "lie": dict(drop=0.85, pitch=-6, spine=-12, neck_p=-28, head_p=14, tail_base=10, tail_tip=-2,
                    back_tuck=1, back_dx=-0.3, arm_up=35, arm_low=-25),
        "sleep": dict(neck_p=-12, neck_y=6, head_p=-4, head_y=6, tail_yaw=30, spine_yaw=4),
        "breath": dict(spine=2.5, neck_p=1.5, head_p=1.5),
    },
    "quadruped": {
        "sit": dict(pitch=32, drop=0.05, neck_p=-8, head_p=-16, tail_base=-28, tail_tip=4,
                    back_dx=0.35, front_dx=-0.05),
        "crouch": dict(drop=0.3, neck_p=-6, back_dx=0.05, front_dx=-0.05),
        "lie": dict(drop=0.62, pitch=-2, neck_p=-14, head_p=6, tail_base=-6, tail_tip=8,
                    back_dx=0.35, front_dx=0.25),
        "sleep": dict(neck_p=-10, neck_y=12, head_p=2, head_y=10, head_r=-12,
                      tail_yaw=40, spine_yaw=5),
        "breath": dict(spine=2.0, neck_p=1.5, head_p=1.0),
    },
}

LOOK = dict(neck_y=22, head_y=26, head_r=8, head_p=4)


def poses():
    base = {k: dict(v) for k, v in POSES[BMAP["plan"]].items()}
    for name, over in BMAP.get("tweaks", {}).items():
        base.setdefault(name, {}).update(over)
    return base


def clip_specs(idle_seconds):
    P = poses()
    lie, sleep = P["lie"], add(P["lie"], P["sleep"])
    zero = {}
    look_left = dict(LOOK)
    look_right = {k: (-v if k in ("neck_y", "head_y", "head_r") else v) for k, v in LOOK.items()}
    L = 2 * idle_seconds
    return [
        dict(name="Sit", base="hold", pivot="back" if BMAP["plan"] == "biped" else "front",
             keys=[(0, zero), (0.9, P["sit"]), (1.25, P["sit"])]),
        dict(name="LieDown", base="hold", pivot="back",
             keys=[(0, zero), (0.6, P["crouch"]), (1.5, lie), (1.75, lie)]),
        dict(name="Sleep", base="hold", pivot="back",
             keys=[(0, sleep), (1.6, add(sleep, P["breath"])), (3.2, sleep)]),
        dict(name="LookAround", base="idle", pivot=None, legs=False, ground=False,
             keys=[(0, zero), (0.16 * L, look_left), (0.36 * L, look_left),
                   (0.56 * L, look_right), (0.76 * L, look_right), (0.92 * L, zero), (L, zero)]),
    ]


def build(poser, spec):
    keys = [(t * FPS, p) for t, p in spec["keys"]]
    end = int(round(keys[-1][0]))
    frames = list(range(0, end, STEP)) + [end]
    samples = []
    for f in frames:
        poser.set_idle(f % poser.idle_frames if spec["base"] == "idle" else 0)
        poser.pose(params_at(keys, f), spec["pivot"], spec.get("legs", True), spec.get("ground", True))
        samples.append((f, poser.snapshot()))

    act = bpy.data.actions.new(poser.prefix + spec["name"])
    act.use_fake_user = True
    poser.arm.animation_data.action = act
    prev = {}
    for f, snap in samples:
        for pb in poser.pb:
            loc, rot, sc = snap[pb.name]
            rot = rot.copy()
            if pb.name in prev:
                rot.make_compatible(prev[pb.name])
            prev[pb.name] = rot
            pb.location, pb.rotation_quaternion, pb.scale = loc, rot, sc
            for path in ("location", "rotation_quaternion", "scale"):
                pb.keyframe_insert(path, frame=f, group=pb.name)
    poser.arm.animation_data.action = None
    print(f"CLIP {act.name}: {len(samples)} vzorků, {end / FPS:.2f} s")
    return act.name


def main():
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    with tempfile.TemporaryDirectory(dir=DST.parent) as tmp:
        rest = node_pose(SRC, tmp)
        arm = import_glb(SRC)
        poser = Poser(arm, rest)
        bpy.context.scene.render.fps = FPS
        names = [build(poser, s) for s in clip_specs(poser.idle_frames / FPS)]

        for a in list(bpy.data.actions):
            if a.name not in names:
                bpy.data.actions.remove(a)
        for o in bpy.context.scene.objects:
            if o.animation_data:
                for tr in list(o.animation_data.nla_tracks):
                    o.animation_data.nla_tracks.remove(tr)
        tmp_glb = Path(tmp) / "nove_klipy.glb"
        bpy.ops.export_scene.gltf(filepath=str(tmp_glb), export_format="GLB", export_yup=True,
                                  export_apply=False, export_animations=True,
                                  export_animation_mode="ACTIONS", export_skins=True)
        DST.parent.mkdir(parents=True, exist_ok=True)
        merge_animations(SRC, tmp_glb, set(names), DST)
    print(f"CLIPS {DST}: {', '.join(names)}")


main()
