"""Screenshot the 3D model from dino3d viewer, for judging it without a TV.

    python tools/shot3d.py --creature trex3d
    python tools/shot3d.py --creature stegosaurus3d
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100/dino3d")
    ap.add_argument("--creature", default="trex3d", help="klíč tvora z katalogu")
    ap.add_argument("--prefix", default="model3d")
    ap.add_argument("--shots", type=int, default=1, help="počet snímků (s automatickým otáčením)")
    ap.add_argument("--every", type=int, default=800, help="ms mezi snímky")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-gl=angle", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 820})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # Navigate to dino3d with creature hash
        page.goto(f"{args.url}#{args.creature}", wait_until="networkidle")

        # Wait for model to finish loading (status changes to "hotovo")
        page.wait_for_function(
            "document.getElementById('status').textContent === 'hotovo'",
            timeout=30000
        )
        page.wait_for_timeout(300)  # brief pause for render

        # Stop automatic rotation if active
        spin_btn = page.query_selector("#spin")
        if spin_btn and page.evaluate("() => window.st?.spin") is True:
            page.click("#spin")
            page.wait_for_timeout(200)

        # Take screenshots
        for i in range(args.shots):
            if i:
                page.wait_for_timeout(args.every)
            path = os.path.join(OUT, f"{args.prefix}_{i + 1}.png")
            page.screenshot(path=path)
            print(path)

        info = page.inner_text("#info")
        status = page.inner_text("#status")
        browser.close()

    print("info:", info)
    if status:
        print("status:", status)
    if errors:
        print("CHYBY V PROHLÍŽEČI:", *errors, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
