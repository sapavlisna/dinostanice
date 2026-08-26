"""Screenshot the 3D preview from a few angles, for judging it without a TV.

    python tools/shot3d.py --catch sauropod-5dae
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")

VIEWS = [
    ("bok", 0.0, 0.12),
    ("tricvrte", 0.75, 0.22),
    ("zepredu", 1.57, 0.15),
    ("shora", 0.6, 0.85),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/3d")
    ap.add_argument("--catch", default=None, help="id úlovku; jinak první v nabídce")
    ap.add_argument("--prefix", default="model3d")
    ap.add_argument("--wire", action="store_true")
    ap.add_argument("--flat", action="store_true", help="bez textury, jen tvar")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-gl=angle", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 820})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("window.__ready === true", timeout=20000)

        if args.catch:
            page.evaluate("""(want) => {
                const sel = document.getElementById('catch');
                const opt = [...sel.options].find(o => o.value.split('|')[0] === want
                                                    || o.value.split('|')[1] === want);
                if (!opt) throw new Error('v nabídce není: ' + want);
                sel.value = opt.value; sel.onchange();
            }""", args.catch)
        page.wait_for_timeout(1600)
        if args.wire:
            page.click("#wire")
        if args.flat:
            page.click("#flat")
        page.click("#play")          # freeze the pose so the shots are comparable
        page.click("#spin")

        for name, yaw, pitch in VIEWS:
            page.evaluate("([y, p]) => window.__setView(y, p)", [yaw, pitch])
            page.wait_for_timeout(350)
            path = os.path.join(OUT, f"{args.prefix}_{name}.png")
            page.screenshot(path=path)
            print(path)

        info = page.inner_text("#info")
        notes = page.inner_text("#notes")
        status = page.inner_text("#status")
        browser.close()

    print("info:", info)
    if notes:
        print("notes:", notes)
    if status:
        print("status:", status)
    if errors:
        print("CHYBY V PROHLÍŽEČI:", *errors, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
