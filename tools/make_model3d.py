"""Bake a creature's 3D model into data/models3d/<key>.json.

    python tools/make_model3d.py sauropod
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dinostanice import model3d                                  # noqa: E402
from dinostanice.creatures import BY_KEY, CATALOGUE              # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "models3d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=[], help="klíče tvorů; prázdné = všichni")
    ap.add_argument("--spacing", type=float, default=None,
                    help="hrana trojúhelníku v mm (menší = jemnější a větší soubor)")
    args = ap.parse_args()

    keys = args.keys or [c.key for c in CATALOGUE]
    os.makedirs(OUT_DIR, exist_ok=True)
    for key in keys:
        if key not in BY_KEY:
            raise SystemExit(f"neznámý tvor: {key}")
        creature = BY_KEY[key]
        t = time.perf_counter()
        kwargs = {"spacing": args.spacing} if args.spacing else {}
        part, notes = model3d.build(creature, **kwargs)
        doc = model3d.to_json(creature, part, notes)
        path = os.path.join(OUT_DIR, f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{key:12s} {len(part['pos']):6d} vrcholů, {len(part['faces']):6d} "
              f"trojúhelníků, {len(part['limbs'])} končetin, "
              f"{os.path.getsize(path)/1024:6.0f} kB, {time.perf_counter()-t:.1f}s")
        for n in notes:
            print(f"             ! {n}")


if __name__ == "__main__":
    main()
