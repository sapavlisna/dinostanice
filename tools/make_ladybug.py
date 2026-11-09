"""Postaví berušku v Blenderu: tvar, kostra a klipy Fly a Rest, export do GLB.

    blender -b --python tools/make_ladybug.py
    (nebo v běžícím Blenderu: exec(open("tools/make_ladybug.py", encoding="utf-8").read()))

Konvence jako u motýlka z `make_butterfly.py`: po exportu (glTF je Y nahoru) má
beruška tělo podél osy y (hlava nahoře), rozpětí podél x a hřbet k divákovi (+z).
V Blenderu je to tedy hlava k +Z a hřbet k -Y. Krovky a křidélka se otevírají
kolem podélné osy, tak jako křídla motýlka.
"""
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

DST = Path(__file__).resolve().parent.parent / "data/models_src/ladybug.glb"

FPS = 24
FLY_FRAMES = 6
REST_FRAMES = 48

COLOURS = {
    "elytra": (0.80, 0.07, 0.05),
    "elytra2": (0.80, 0.07, 0.05),  # stejná barva, jen aby předloha dostala šev mezi krovkami
    "spot": (0.02, 0.02, 0.03),
    "white": (0.95, 0.94, 0.88),
    "black": (0.04, 0.04, 0.05),
    "shield": (0.06, 0.06, 0.07),
    "head": (0.03, 0.03, 0.04),
    "wing": (0.55, 0.50, 0.48),
}


def reset():
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return
    # v živém Blenderu by factory reset vypnul addon MCP
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.actions,
                 bpy.data.materials):
        for item in list(coll):
            coll.remove(item)


def material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*COLOURS[name], 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    return m


def ellipsoid(name, centre, radii, mat, rot_z=0.0, segs=24, rings=12):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.scale = radii
    ob.rotation_euler = (0, 0, rot_z)
    ob.location = centre
    bpy.context.view_layer.update()
    me.transform(ob.matrix_basis)
    ob.matrix_basis = Matrix.Identity(4)
    return ob


def stick(name, a, b, radius, mat):
    a, b = Vector(a), Vector(b)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=radius, radius2=radius * 0.6,
                          depth=(b - a).length)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    q = Vector((0, 0, 1)).rotation_difference(b - a)
    me.transform(Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())
    return ob


def on_surface(centre, radii, x, z):
    """Y bodu (x, z) na zádech elipsoidu; hřbet míří k -Y."""
    u = ((x - centre[0]) / radii[0]) ** 2 + ((z - centre[2]) / radii[2]) ** 2
    return centre[1] - radii[1] * math.sqrt(max(0.0, 1.0 - u))


def shell(name, centre, radii, mat, side, thickness=0.02):
    """Tenká ohnutá krovka: hřbetní půlka elipsoidu ořezaná na šev (x = 0) a na rovinu
    spodku, s tloušťkou. Celá skořápka se tak jen klene přes tělo, nenafukuje se."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=14, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0] + centre[0], v.co.y * radii[1] + centre[1],
                       v.co.z * radii[2] + centre[2]))

    def cut(normal, **clear):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0) if normal[1] == 0 else centre,
                               plane_no=normal, **clear)

    cut((0, 1, 0), clear_outer=True)
    cut((1, 0, 0), **({"clear_inner": True} if side > 0 else {"clear_outer": True}))
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thickness)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def patch(name, centre, radii, x, z, size, mat):
    """Plochá skvrna přisedlá na povrch elipsoidu, vyčnívá o `size[1]`."""
    return ellipsoid(name, (x, on_surface(centre, radii, x, z), z), (size[0], size[1], size[2]), mat)


# podle fotek sedmitečné berušky: kulaté tělo delší než široké, přes něj tenké
# ohnuté krovky, užší štít, malá hlava se dvěma bílými očima a sedm teček
# (jedna společná u štítku a tři na každé straně)
BODY = ((0.0, 0.12, -0.10), (0.36, 0.20, 0.44))
ELYTRON = ((0.15, 0.06, -0.12), (0.28, 0.17, 0.44))
PRONOTUM = ((0.0, 0.06, 0.30), (0.28, 0.14, 0.12))
HEAD = ((0.0, 0.06, 0.46), (0.13, 0.10, 0.08))
SPOTS = ((0.31, 0.10, 0.070), (0.13, -0.12, 0.060), (0.31, -0.30, 0.070))
SHARED_SPOT = (0.0, 0.10, 0.050)


def build_meshes():
    elytra, elytra2 = material("elytra"), material("elytra2")
    black, wing = material("black"), material("wing")
    shield, head, spot, white = (material(n) for n in ("shield", "head", "spot", "white"))
    parts = {"Body": [], "Head": [], "ElytraL": [], "ElytraR": [], "WingL": [], "WingR": []}

    parts["Body"].append(ellipsoid("abdomen", BODY[0], BODY[1], black))
    parts["Body"].append(ellipsoid("pronotum", PRONOTUM[0], PRONOTUM[1], shield))
    parts["Head"].append(ellipsoid("head", HEAD[0], HEAD[1], head))
    for sx in (1, -1):
        side = "L" if sx > 0 else "R"
        e_centre = (sx * ELYTRON[0][0], ELYTRON[0][1], ELYTRON[0][2])
        elytron = parts["Elytra" + side]
        elytron.append(shell("elytron" + side, e_centre, ELYTRON[1],
                             elytra if sx > 0 else elytra2, sx))
        for i, (x, z, r) in enumerate(SPOTS):
            elytron.append(patch(f"spot{i}{side}", e_centre, ELYTRON[1], sx * x, z,
                                 (r, 0.03, r), spot))
        if sx > 0:
            x, z, r = SHARED_SPOT
            elytron.append(patch("spot_shared", e_centre, ELYTRON[1], x, z, (r, 0.03, r), spot))

        parts["Head"].append(patch(f"eye{side}", HEAD[0], HEAD[1], sx * 0.075, 0.49,
                                   (0.03, 0.02, 0.03), white))
        for i, (z, reach) in enumerate(((0.30, 0.46), (0.0, 0.49), (-0.26, 0.46))):
            parts["Body"].append(stick(f"leg{i}{side}", (sx * 0.18, 0.22, z),
                                       (sx * reach, 0.30, z + (0.10 - 0.10 * i)), 0.020, black))
        parts["Head"].append(stick(f"antenna{side}", (sx * 0.05, 0.0, 0.52),
                                   (sx * 0.14, 0.0, 0.68), 0.013, black))
        parts["Wing" + side].append(ellipsoid("wing" + side, (sx * 0.17, -0.03, -0.14),
                                              (0.19, 0.012, 0.20), wing))
    return parts


def build_armature():
    arm_data = bpy.data.armatures.new("LadybugRig")
    arm = bpy.data.objects.new("Ladybug", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def bone(name, head, parent=None):
        b = eb.new(name)
        b.head = head
        b.tail = (head[0], head[1], head[2] + 0.1)
        b.roll = 0.0
        if parent:
            b.parent = eb[parent]
        return b

    bone("Body", (0, 0, 0))
    bone("Head", (0, 0.0, 0.46), "Body")
    bone("ElytraL", (0.0, 0.0, 0.30), "Body")
    bone("ElytraR", (0.0, 0.0, 0.30), "Body")
    bone("WingL", (0.0, -0.03, 0.20), "Body")
    bone("WingR", (0.0, -0.03, 0.20), "Body")
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def skin(arm, parts):
    for bone_name, objs in parts.items():
        for ob in objs:
            ob.parent = arm
            vg = ob.vertex_groups.new(name=bone_name)
            vg.add([v.index for v in ob.data.vertices], 1.0, "REPLACE")
            mod = ob.modifiers.new("Armature", "ARMATURE")
            mod.object = arm


def rot(angle):
    return Quaternion((0, 1, 0), angle)


def key(arm, name, frames, tracks):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = action
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion((1, 0, 0, 0))
    for f in range(frames + 1):
        for bone_name, fn in tracks.items():
            pb = arm.pose.bones[bone_name]
            pb.rotation_quaternion = fn(f / frames)
            pb.keyframe_insert("rotation_quaternion", frame=f + 1)
    track = arm.animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, 1, action)
    strip.name = name


def build_clips(arm):
    rad = math.radians

    def fly_elytra(sign):
        return lambda t: rot(sign * rad(58 + 5 * math.sin(2 * math.pi * t)))

    def fly_wing(sign):
        return lambda t: rot(sign * rad(25 + 60 * math.sin(2 * math.pi * t + 0.4)))

    def calm(sign):
        return lambda t: rot(sign * rad(2 * math.sin(2 * math.pi * t)))

    still = lambda t: Quaternion((1, 0, 0, 0))
    key(arm, "Fly", FLY_FRAMES, {
        "ElytraL": fly_elytra(-1), "ElytraR": fly_elytra(1),
        "WingL": fly_wing(-1), "WingR": fly_wing(1),
        "Body": lambda t: Quaternion((1, 0, 0), rad(5 * math.sin(2 * math.pi * t + 1.0))),
        "Head": still,
    })
    key(arm, "Rest", REST_FRAMES, {
        "ElytraL": calm(-1), "ElytraR": calm(1),
        "WingL": still, "WingR": still,
        "Body": still,
        "Head": lambda t: Quaternion((0, 0, 1), rad(8 * math.sin(4 * math.pi * t))),
    })
    arm.animation_data.action = None


def export():
    DST.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=str(DST), export_format="GLB", export_animations=True,
                              export_animation_mode="ACTIONS", export_skins=True,
                              use_selection=False)


def main():
    reset()
    bpy.context.scene.render.fps = FPS
    arm = build_armature()
    parts = build_meshes()
    skin(arm, parts)
    build_clips(arm)
    export()
    print("ladybug:", DST, DST.stat().st_size // 1024, "kB")


main()
