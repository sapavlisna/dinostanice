"""Rasterising creatures: fill mask and a clean unioned outline.

The body and every limb are separate overlapping polygons. Filling them into
one bitmap and tracing the result with findContours is what turns them into a
single silhouette without needing a polygon-boolean library.
"""

import cv2
import numpy as np

from .shapes import (SHEET_W_MM, SHEET_H_MM, body_centerline, creature_holes,
                     creature_polygons, tube_outline)

MASK_PX_PER_MM = 8.0


def _to_px(poly, ppm):
    return np.round(np.asarray(poly, dtype=float) * ppm).astype(np.int32)


def creature_mask(creature, ppm=MASK_PX_PER_MM, poses=None, sheet=True):
    w = int(round(SHEET_W_MM * ppm)) if sheet else None
    h = int(round(SHEET_H_MM * ppm)) if sheet else None
    mask = np.zeros((h, w), np.uint8)
    body, far, near = creature_polygons(creature, poses)
    for _, poly in far + body + near:
        cv2.fillPoly(mask, [_to_px(poly, ppm)], 255)
    for hole in creature_holes(creature):
        cv2.fillPoly(mask, [_to_px(hole, ppm)], 0)
    return mask


def body_mask(creature, ppm=MASK_PX_PER_MM, grow_mm=0.0):
    """The trunk without its limbs -- what the unwrapped strip is allowed to keep.

    Derived from the actual silhouette rather than from the thickness profile, so
    that features the profile knows nothing about -- a stegosaur's plates, a
    triceratops frill -- survive the unwrap.
    """
    w = int(round(SHEET_W_MM * ppm))
    h = int(round(SHEET_H_MM * ppm))
    mask = np.zeros((h, w), np.uint8)
    if creature.outline is not None:
        cv2.fillPoly(mask, [_to_px(creature.outline[0], ppm)], 255)
        for hole in creature_holes(creature):
            cv2.fillPoly(mask, [_to_px(hole, ppm)], 0)
        from .shapes import limb_polygons
        for limb in creature.limbs:
            if limb.parts or limb.outline is not None:
                for poly in limb_polygons(creature, limb):
                    cv2.fillPoly(mask, [_to_px(poly, ppm)], 0)
    else:
        line, radii = body_centerline(creature)
        cv2.fillPoly(mask, [_to_px(tube_outline(line, radii), ppm)], 255)
    if grow_mm > 0:
        k = int(round(grow_mm * ppm)) * 2 + 1
        mask = cv2.dilate(mask, np.ones((k, k), np.uint8))
    return mask


def outline_contours(creature, ppm=MASK_PX_PER_MM, epsilon_mm=0.25, min_mm=3.0):
    """Unioned silhouette as a list of contours, in millimetres.

    Includes inner contours: a gap enclosed by the shape is a line the child
    should see on the printed sheet, not something to silently fill in.
    """
    mask = creature_mask(creature, ppm)
    contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < (min_mm * ppm) ** 2:
            continue
        approx = cv2.approxPolyDP(c, epsilon_mm * ppm, True)
        out.append(approx.reshape(-1, 2).astype(float) / ppm)
    return out
