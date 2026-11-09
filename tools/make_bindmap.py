"""Mapa navlečení (tools/bindmaps/<zvíře>.json) z kostry předlohy a ručních bodů.

    python tools/make_bindmap.py data/models_src/alpaca.glb tmp/sheep_over.json tools/bindmaps/sheep.json

`blender_bind.py` potřebuje pro každý řetěz kloubů předlohy bod na tvaru
(`landmarks`, v jednotkovém rámci z `--prep`). Většina řetězů je u všech zvířat
Quaterniova packu stejná (Back, Torso…, Neck…, Head, Tail…, uši, nohy), takže
se mapa složí ze vzoru (`tools/bindmaps/zajic.json`: řetězy, části, barvy) a z
přepisů, které popisují jen to, co je u daného zvířete jinak:

    {"source": "data/models_src/sheep_tvar.glb", "name": "Ovce", "faces": 2400,
     "chains": [...],                       volitelně jiné řetězy (zvíře bez uší…)
     "fit": [...], "aim": [...],            volitelně
     "landmarks": {"Back": [x, y, z], …},   body na tvaru (x do strany, y nahoru, z k hlavě)
     "colors": {"Telo": [r, g, b], …}}

Do mapy jdou jen ručně zadané landmarks; klouby mezi nimi na řetězu si
`blender_bind.py` dopočítá na úsečce v poměru délek kostí předlohy. Řetězy
se zkrátí na klouby, které předloha opravdu má (alpaka a jelen nemají `Head_end`).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dinostanice.gltf import Model  # noqa: E402

BASE = ROOT / "tools/bindmaps/zajic.json"
KEEP = ("source", "name", "faces", "rotate_y", "dissolve", "keep_parts", "cut", "fill_holes",
        "fit", "aim", "leg_scale", "scale_by", "smooth_parts", "thickness", "thick",
        "colors", "parts", "chains")


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    template, over_path, out = (Path(a) for a in sys.argv[1:])
    template = template if template.is_absolute() else ROOT / template
    over = json.loads(over_path.read_text(encoding="utf-8"))
    cfg = json.loads(BASE.read_text(encoding="utf-8"))
    for k in KEEP:
        if k in over:
            cfg[k] = over[k]
    names = set(Model(template).node_names)
    cfg["chains"] = [[j for j in ch if j in names] for ch in cfg["chains"]]
    cfg["template"] = str(template.relative_to(ROOT)).replace("\\", "/") \
        if template.is_relative_to(ROOT) else str(template)
    cfg["landmarks"] = {k: {"at": v} for k, v in over.get("landmarks", {}).items()}
    out.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out}: {len(cfg['landmarks'])} landmarks, {len(cfg['chains'])} řetězů")


if __name__ == "__main__":
    main()
