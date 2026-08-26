"""Derive geometry from every silhouette in data/silhouettes and draw a check sheet."""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dinostanice.markers import CORNER_ORIGINS, MARKER_MM
from dinostanice.shapes import SHEET_W_MM, SHEET_H_MM
from dinostanice.silhouette import LABEL_BAND_MM, derive, drawing_area, load_mask

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPM = 4.0
LIMB_COLOURS = [(60, 220, 60), (220, 120, 40), (60, 160, 250), (200, 60, 220),
                (40, 210, 210), (120, 120, 255), (0, 160, 90), (170, 90, 30)]


def _px(p):
    return np.round(np.asarray(p, float) * PPM).astype(np.int32)


def render(shape, label, path):
    w = int(SHEET_W_MM * PPM)
    h = int(SHEET_H_MM * PPM)
    img = np.full((h, w, 3), 250, np.uint8)

    for ox, oy in CORNER_ORIGINS:
        cv2.rectangle(img, tuple(_px((ox, oy))), tuple(_px((ox + MARKER_MM, oy + MARKER_MM))),
                      (30, 30, 30), -1)
    cv2.rectangle(img, tuple(_px((0, SHEET_H_MM - LABEL_BAND_MM))),
                  tuple(_px((SHEET_W_MM, SHEET_H_MM))), (225, 235, 245), -1)
    x0, y0, x1, y1 = drawing_area()
    cv2.rectangle(img, tuple(_px((x0, y0))), tuple(_px((x1, y1))), (200, 200, 200), 1)

    body = img.copy()
    cv2.fillPoly(body, [_px(shape.outline[0])], (232, 232, 232))
    for hole in shape.outline[1:]:
        cv2.fillPoly(body, [_px(hole)], (250, 250, 250))
    img = cv2.addWeighted(img, 0.0, body, 1.0, 0)

    for i, c in enumerate(shape.outline):
        cv2.polylines(img, [_px(c)], True, (0, 0, 0) if i == 0 else (0, 0, 200), 1, cv2.LINE_AA)

    step = max(1, len(shape.spine) // 26)
    for i in range(0, len(shape.spine), step):
        cv2.circle(img, tuple(_px(shape.spine[i])), int(shape.profile[i] * PPM),
                   (150, 190, 255), 1, cv2.LINE_AA)

    fill = img.copy()
    for limb, colour in zip(shape.limbs, LIMB_COLOURS * 3):
        cv2.fillPoly(fill, [_px(limb.polygon)], colour)
    img = cv2.addWeighted(img, 0.72, fill, 0.28, 0)

    for limb, colour in zip(shape.limbs, LIMB_COLOURS * 3):
        cv2.polylines(img, [_px(limb.polygon)], True, colour, 2, cv2.LINE_AA)
        j = _px(limb.joints)
        cv2.polylines(img, [j], False, colour, 3, cv2.LINE_AA)
        for k, p in enumerate(j):
            cv2.circle(img, tuple(p), 6 if k else 8, (255, 255, 255), -1)
            cv2.circle(img, tuple(p), 6 if k else 8, colour, 2)
        idx = int(round(limb.anchor * (len(shape.spine) - 1)))
        cv2.drawMarker(img, tuple(_px(shape.spine[idx])), colour, cv2.MARKER_STAR, 16, 2)
        cv2.putText(img, "%s s%d @%.2f" % (limb.name, limb.side, limb.anchor),
                    tuple(j[-1] + (6, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)

    cv2.polylines(img, [_px(shape.spine)], False, (0, 0, 255), 2, cv2.LINE_AA)
    for i in range(0, len(shape.spine), step):
        p = _px(shape.spine[i])
        cv2.circle(img, tuple(p), 3, (0, 0, 255), -1)
        cv2.putText(img, str(i), tuple(p + (3, -5)), cv2.FONT_HERSHEY_SIMPLEX, 0.32,
                    (120, 0, 0), 1, cv2.LINE_AA)
    cv2.circle(img, tuple(_px(shape.spine[0])), 11, (255, 0, 255), 3)
    cv2.putText(img, "HEAD", tuple(_px(shape.spine[0]) + (14, 4)), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 0, 255), 2, cv2.LINE_AA)
    cv2.putText(img, "TAIL", tuple(_px(shape.spine[-1]) + (8, 4)), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (140, 90, 0), 1, cv2.LINE_AA)

    cv2.putText(img, "%s  |  %s" % (label, shape.notes["head_rule"]),
                (12, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
    cv2.imwrite(path, img)


def outline_check(shape, png, path, ppm=8.0):
    """Overlay the simplified outline on the source silhouette to see what was lost."""
    mask, _ = load_mask(png)
    m = np.float32([[shape.scale * ppm, 0, shape.offset[0] * ppm],
                    [0, shape.scale * ppm, shape.offset[1] * ppm]])
    size = (int(SHEET_W_MM * ppm), int(SHEET_H_MM * ppm))
    src = cv2.warpAffine(mask, m, size, flags=cv2.INTER_NEAREST)

    poly = np.zeros(src.shape, np.uint8)
    cv2.fillPoly(poly, [np.round(shape.outline[0] * ppm).astype(np.int32)], 255)
    for hole in shape.outline[1:]:
        cv2.fillPoly(poly, [np.round(hole * ppm).astype(np.int32)], 0)

    xor = cv2.bitwise_xor(src, poly)
    lost = float(xor.sum() / 255) / max(float(src.sum() / 255), 1.0)
    n, lab, stats, _ = cv2.connectedComponentsWithStats((xor > 0).astype(np.uint8), 8)
    worst = 0.0 if n < 2 else float(stats[1:, cv2.CC_STAT_AREA].max()) / (ppm * ppm)

    vis = np.full(src.shape + (3,), 255, np.uint8)
    vis[src > 0] = (222, 222, 222)
    vis[xor > 0] = (120, 120, 255)
    cv2.polylines(vis, [np.round(shape.outline[0] * ppm).astype(np.int32)], True,
                  (0, 0, 0), 1, cv2.LINE_AA)
    for hole in shape.outline[1:]:
        cv2.polylines(vis, [np.round(hole * ppm).astype(np.int32)], True, (200, 0, 0), 1,
                      cv2.LINE_AA)
    ys, xs = np.nonzero(src)
    pad = int(4 * ppm)
    vis = vis[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]
    cv2.imwrite(path, vis)
    return lost, worst


def main():
    creds = json.load(open(os.path.join(ROOT, "data/silhouettes/credits.json"), encoding="utf-8"))
    for c in creds:
        png = os.path.join(ROOT, "data/silhouettes/%s.png" % c["key"])
        shape = derive(png, view=c.get("view", "side"), motion=c.get("motion", "walk"))
        out = os.path.join(ROOT, "out/derived_%s.png" % c["key"])
        render(shape, "%s (%s)" % (c["label"], c["key"]), out)
        lost, worst = outline_check(shape, png, os.path.join(ROOT, "out/outline_%s.png" % c["key"]))

        p = np.vstack(shape.outline[:1])
        bb = p.min(0), p.max(0)
        print("=== %-12s %-14s view=%s motion=%s" % (c["key"], c["label"], shape.view, shape.motion))
        print("    sheet box %.0f x %.0f mm at (%.0f, %.0f)   scale %.4f mm/px  flipped=%s"
              % (bb[1][0] - bb[0][0], bb[1][1] - bb[0][1], bb[0][0], bb[0][1],
                 shape.scale, shape.notes["flipped"]))
        print("    head rule: %s" % shape.notes["head_rule"])
        print("    spine %d pts, %.1f mm, r %.1f..%.1f mm   outline %d pts + %d holes"
              % (len(shape.spine), shape.notes["spine_len_mm"], shape.profile.min(),
                 shape.profile.max(), len(shape.outline[0]), len(shape.outline) - 1))
        print("    outline vs source: %.2f%% of area differs, biggest patch %.1f mm2"
              % (100 * lost, worst))
        print("    limbs: %d" % len(shape.limbs))
        for l in shape.limbs:
            print("      %-10s side=%d anchor=%.3f joints=%d area=%.0f mm2 tip=(%.0f,%.0f)"
                  % (l.name, l.side, l.anchor, len(l.joints), l.area_mm2,
                     l.joints[-1][0], l.joints[-1][1]))
        for cand in shape.notes["candidates"]:
            if cand["rejected"] and cand["area"] > 0.004:
                print("      - rejected @%.3f area=%.1f%% reach=%.1f%% down=%+.2f  (%s)"
                      % (cand["anchor"], 100 * cand["area"], 100 * cand["reach"],
                         cand["down"], cand["rejected"]))


if __name__ == "__main__":
    main()
