"""Blender headless: libovolný model -> GLB, jak ho čeká stanice.

    blender -b --python tools/blender_normalize.py -- VSTUP VYSTUP.glb [JSON]

JSON (volitelný) = {"rotate_y": stupně, "max_tris": počet}. Co se děje:

- import podle přípony (glb/gltf, fbx, obj, blend — .blend se otevře celý),
- všechno se zavěsí pod jeden kořen `StationRoot`, ten se otočí kolem svislé
  osy o `rotate_y` (model má koukat k +Z = doprava na listu); na zem ho
  postaví až tools/scena.py — stejnou matematikou, jakou model pózuje stanice
  (dinostanice.gltf), protože Blenderova klidová póza se od vazební liší;
  měřítko se neřeší, scéna si velikost normalizuje,
- meshe nad `max_tris` trojúhelníků se zdecimují (předloha z 50 tisíc
  trojúhelníků je jen šum čar a scéna by se na TV zadýchala),
- export GLB i se skinem a všemi akcemi.

Transformace se neaplikují do vrcholů: u rigovaného modelu by aplikace
měřítka/rotace rozbila klíčové snímky kostry. Kořenový uzel s transformací
glTF nese a dinostanice.gltf ho do pozice započítá.
"""

import json
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = Path(argv[0]), Path(argv[1])
opts = json.loads(argv[2]) if len(argv) > 2 else {}

ext = src.suffix.lower()
if ext == ".blend":
    bpy.ops.wm.open_mainfile(filepath=str(src))
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(src))
    else:
        sys.exit(f"neznámý formát {ext}")

scene = bpy.context.scene
objs = [o for o in scene.objects if o.type in ("MESH", "ARMATURE", "EMPTY")]
tops = [o for o in objs if o.parent is None]

max_tris = int(opts.get("max_tris", 20000))
for o in objs:
    if o.type != "MESH":
        continue
    tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if tris > max_tris:
        mod = o.modifiers.new("decimate", "DECIMATE")
        mod.ratio = max_tris / tris
        print(f"DECIMATE {o.name}: {tris} -> ~{max_tris}")

root = bpy.data.objects.new("StationRoot", None)
scene.collection.objects.link(root)
for o in tops:
    mw = o.matrix_world.copy()
    o.parent = root
    o.matrix_world = mw

root.rotation_mode = "XYZ"
# Blender je Z-up; glTF export ho převrací na Y-up, svislá osa je tu tedy Z
root.rotation_euler = (0.0, 0.0, math.radians(float(opts.get("rotate_y", 0.0))))
bpy.context.view_layer.update()

dst.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(dst), export_format="GLB", export_yup=True,
                          export_apply=True, export_animations=True,
                          export_animation_mode="ACTIONS", export_skins=True)
print(f"NORMALIZED {dst}")
