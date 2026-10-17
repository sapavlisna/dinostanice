"""Vyfotí živou scénu, aby se dala posoudit bez televize.

    python tools/shot_scene.py --url "http://127.0.0.1:8123/tv?scene=cretaceous" --demo

`--demo` doplní tvory z katalogu (s ukázkovou texturou), aby bylo co soudit
i když ještě nikdo nic nevybarvil.
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")

DEMO = ["trex3d", "triceratops3d", "stegosaurus3d", "apatosaurus3d",
        "pteranodon3d", "drak3d"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8123/tv?scene=cretaceous")
    ap.add_argument("--demo", action="store_true", help="doplnit tvory z katalogu")
    ap.add_argument("--prefix", default="scena")
    ap.add_argument("--shots", type=int, default=3)
    ap.add_argument("--every", type=int, default=2500, help="ms mezi snímky")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-gl=angle", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("window.__ready === true", timeout=30000)

        if args.demo:
            page.evaluate("""async (keys) => {
                for (const key of keys) {
                    await window.DinoScene.add({
                        id: 'demo-' + key, creature: key,
                        texture: `/models3d/${key}_texture.png`,
                    }, { silent: true });
                }
            }""", DEMO)
        page.wait_for_timeout(2500)

        for i in range(args.shots):
            if i:
                page.wait_for_timeout(args.every)
            path = os.path.join(OUT, f"{args.prefix}_{i + 1}.png")
            page.screenshot(path=path)
            print(path)

        where = page.evaluate("window.DinoScene.where()")
        browser.close()

    for w in where:
        print(w)
    if errors:
        print("CHYBY V PROHLÍŽEČI:", *errors, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
