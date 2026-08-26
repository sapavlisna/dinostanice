"""Draw the two non-organic templates and bake them into data/shapes/.

PhyloPic only has organisms, so the boat and the plane are drawn here. They are
composed from primitives into a bitmap and then traced, exactly like the
downloaded silhouettes -- an ellipse gives a hull line that hand-placed polygon
points never will.
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PPM = 8.0
W, H = int(297 * PPM), int(210 * PPM)
OUT_DIR = "data/shapes"
SIL_DIR = "data/silhouettes"


def blank():
    return np.zeros((H, W), np.uint8)


def _p(x, y):
    return (int(round(x * PPM)), int(round(y * PPM)))


def ell(m, cx, cy, ax, ay):
    cv2.ellipse(m, _p(cx, cy), (int(ax * PPM), int(ay * PPM)), 0, 0, 360, 255, -1)


def poly(m, pts, val=255):
    cv2.fillPoly(m, [np.array([_p(*q) for q in pts], np.int32)], val)


def ship_mask():
    m = blank()
    ell(m, 150, 142, 112, 32)
    poly(m, [(10, 40), (290, 40), (290, 142), (10, 142)], 0)      # flat deck
    poly(m, [(246, 142), (272, 116), (278, 138), (262, 152)])     # bow rises
    poly(m, [(146, 30), (156, 30), (156, 144), (146, 144)])       # mast
    # the sails reach the deck: hanging them off the mast alone leaves slots
    # that the traced outline has to squeeze through, and it reads as a mess
    poly(m, [(148, 38), (148, 145), (68, 143)])                   # mainsail
    poly(m, [(155, 50), (244, 142), (155, 145)])                  # jib
    return m


def plane_body_mask():
    m = blank()
    ell(m, 165, 95, 108, 19)
    ell(m, 203, 84, 33, 13)
    poly(m, [(72, 88), (56, 95), (72, 103)])
    poly(m, [(88, 88), (62, 40), (84, 38), (112, 86)])
    ell(m, 78, 98, 26, 7)
    poly(m, [(152, 90), (210, 90), (196, 128), (126, 126)])
    return m


def prop_mask():
    m = blank()
    poly(m, [(268, 46), (277, 46), (277, 144), (268, 144)])
    ell(m, 272.5, 95, 6, 13)
    return m


def contours_mm(mask, eps_mm=0.22, min_mm=3.0):
    """Outer contour first, then holes.

    The hierarchy matters: a detached piece is another OUTER contour, not a
    hole, and treating it as one would punch the shape out of the mask.
    """
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not len(cnts):
        return []
    hier = hier[0]
    keep = [(i, c) for i, c in enumerate(cnts)
            if cv2.contourArea(c) >= (min_mm * PPM) ** 2]
    outer = [(i, c) for i, c in keep if hier[i][3] < 0]
    holes = [(i, c) for i, c in keep if hier[i][3] >= 0]
    if len(outer) > 1:
        biggest = max(outer, key=lambda ic: cv2.contourArea(ic[1]))
        raise ValueError(
            f"tvar se rozpadl na {len(outer)} oddělených částí — musí držet pohromadě "
            f"(největší {cv2.contourArea(biggest[1]) / PPM**2:.0f} mm2)")

    def mm(c):
        a = cv2.approxPolyDP(c, eps_mm * PPM, True).reshape(-1, 2).astype(float) / PPM
        return [[round(float(x), 2), round(float(y), 2)] for x, y in a]

    return [mm(c) for _, c in outer] + [mm(c) for _, c in holes]


def save_alpha(mask, path):
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[:, :, 3] = mask
    cv2.imwrite(path, rgba)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(SIL_DIR, exist_ok=True)

    ship = ship_mask()
    save_alpha(ship, os.path.join(SIL_DIR, "ship.png"))
    doc = {
        "key": "ship", "label": "Plachetnice", "motion": "sail", "view": "side",
        "rigid": True, "author": "vlastní kresba", "licence": "vlastní", "source": "",
        "spine": [[60, 142], [150, 138], [250, 134]],
        "profile": [10.0, 10.0, 10.0],
        "outline": contours_mm(ship),
        "details": [[[147, 40], [147, 142]], [[157, 42], [157, 142]],
                    [[50, 142], [266, 142]]],
        "limbs": [],
    }
    json.dump(doc, open(os.path.join(OUT_DIR, "ship.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"ship   {len(doc['outline'])} obrysů (vnější + díry mezi plachtami)")

    body = plane_body_mask()
    prop = prop_mask()
    save_alpha(cv2.bitwise_or(body, prop), os.path.join(SIL_DIR, "plane.png"))
    prop_c = contours_mm(prop)
    doc = {
        "key": "plane", "label": "Letadlo", "motion": "fly", "view": "side",
        "rigid": True, "author": "vlastní kresba", "licence": "vlastní", "source": "",
        "spine": [[250, 95], [200, 92], [150, 93], [100, 96], [60, 96]],
        "profile": [6.0, 16.0, 18.0, 14.0, 7.0],
        "outline": contours_mm(body),
        "details": [[[186, 79], [222, 79], [226, 90], [182, 90], [186, 79]]],
        "limbs": [{"name": "prop", "anchor": 0.02, "side": 0,
                   "outline": prop_c[0], "pivot": [272.5, 95.0]}],
    }
    json.dump(doc, open(os.path.join(OUT_DIR, "plane.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"plane  {len(doc['outline'])} obrysů + vrtule jako samostatný díl")


if __name__ == "__main__":
    main()
