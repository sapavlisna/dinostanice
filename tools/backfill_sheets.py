"""Write sheet.png into catches taken before the 3D view existed.

Everything is recovered from the photo the catch already keeps, so this needs
no reprint and no re-upload.
"""

import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dinostanice import capture, rig, store            # noqa: E402
from dinostanice.creatures import CATALOGUE            # noqa: E402

TRIM_MM = 0.6


def main():
    force = "--force" in sys.argv
    done = skipped = failed = 0
    for meta in store.list_catches():
        out = os.path.join(store.catch_dir(meta["id"]), "sheet.png")
        if os.path.exists(out) and not force:
            skipped += 1
            continue
        photo = store.find_photo(meta["id"])
        if not photo:
            print(f"{meta['id']}: chybí fotka, přeskakuji")
            failed += 1
            continue
        bgr = cv2.imread(photo, cv2.IMREAD_COLOR)
        try:
            index, warped, _ = capture.detect_sheet(bgr)
            sheet = capture.sheet_texture(warped, CATALOGUE[index], trim_mm=TRIM_MM)
        except Exception as e:
            print(f"{meta['id']}: {type(e).__name__}: {e}")
            failed += 1
            continue
        cv2.imwrite(out, rig.sheet_for_texture(sheet))
        done += 1
        print(f"{meta['id']}: sheet.png hotovo")
    print(f"\nhotovo {done}, přeskočeno {skipped}, selhalo {failed}")


if __name__ == "__main__":
    main()
