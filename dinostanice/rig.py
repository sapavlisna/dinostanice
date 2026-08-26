"""Turning a captured texture into animatable parts.

The body is unwrapped along its spine into a straight strip: x runs along the
spine, y is the perpendicular offset. Bending the creature then means drawing
that straight strip along any curve, which a renderer can do with plain 2D
transforms. Limbs are cut into rigid segments that rotate about their joints.
"""

import json
import math
import os

import cv2
import numpy as np

from .shapes import (SHEET_W_MM, SHEET_H_MM, body_centerline,
                     limb_joints, resample_profile, tube_outline)
from .capture import WARP_PPM
from .raster import body_mask
from .store import write_image
from .template import LINE_MM

STRIP_MIN_SAMPLES = 256
STRIP_MAX_SAMPLES = 1600


def strip_samples(length_mm, ppm):
    """Sample along the spine at the same density as across it, so the strip
    does not squash the drawing lengthwise."""
    return int(np.clip(round(length_mm * ppm), STRIP_MIN_SAMPLES, STRIP_MAX_SAMPLES))


def _arclen(points):
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def resample_by_length(points, n):
    s = _arclen(points)
    target = np.linspace(0, s[-1], n)
    x = np.interp(target, s, points[:, 0])
    y = np.interp(target, s, points[:, 1])
    return np.stack([x, y], axis=1), float(s[-1])


def extend_past_caps(line, radii, ppm):
    """Carry the spine past both ends so the tube's round caps land in the strip.

    Without this the nose and the tail tip -- which are cap arcs, not tube --
    are simply absent from body.png, and no renderer can put them back. A
    radius profile of sqrt(r^2 - d^2) over the extension reproduces the cap
    exactly as a half circle.
    """
    pieces_line, pieces_r = [line], [radii]
    for end in (0, -1):
        r = float(radii[end])
        if r <= 0.1:
            continue
        direction = line[0] - line[1] if end == 0 else line[-1] - line[-2]
        direction = direction / max(np.linalg.norm(direction), 1e-9)
        steps = max(2, int(round(r * ppm)))
        d = np.linspace(r / steps, r, steps)
        pts = line[end] + direction[None, :] * d[:, None]
        rr = np.sqrt(np.maximum(r ** 2 - d ** 2, 0.0))
        if end == 0:
            pieces_line.insert(0, pts[::-1])
            pieces_r.insert(0, rr[::-1])
        else:
            pieces_line.append(pts)
            pieces_r.append(rr)
    return np.vstack(pieces_line), np.concatenate(pieces_r)


SPINE_GAP_MM = 24.0


def spine_connected(keep, gap_px):
    """Trim the strip to the part of the mask that hangs together with the spine.

    A normal taken near the snout can fly clear across a triceratops frill, so
    that column of the strip would otherwise carry a slice of head under the
    belly. Gaps up to gap_px are tolerated -- those are real holes in the
    drawing, like an open jaw or the space between legs.
    """
    h = keep.shape[0]
    closed = cv2.morphologyEx(keep, cv2.MORPH_CLOSE,
                              np.ones((2 * gap_px + 1, 1), np.uint8))
    n, labels = cv2.connectedComponents((closed > 0).astype(np.uint8))
    if n <= 1:
        return keep
    wanted = labels[h // 2, :]
    same = (labels == wanted[None, :]) & (wanted[None, :] > 0)
    return np.where(same, keep, 0).astype(keep.dtype)


def unwrap_body(rgba_sheet, creature, ppm=WARP_PPM):
    """Straighten the body along its spine. Returns (strip_rgba, meta)."""
    raw, raw_radii = body_centerline(creature)
    raw = np.asarray(raw)
    samples = strip_samples(float(_arclen(raw)[-1]), ppm)
    line, _ = resample_by_length(raw, samples)
    # radii must follow arc length too, or they drift against the strip columns
    s_raw = _arclen(raw)
    radii = np.interp(np.linspace(0, 1, samples), s_raw / s_raw[-1], raw_radii)

    line, radii = extend_past_caps(line, radii, ppm)
    samples = len(line)
    length_mm = float(_arclen(line)[-1])

    # The strip must be tall enough for what the silhouette actually reaches --
    # a stegosaur's plates stick out well past the inscribed radius the profile
    # knows about -- so measure it against the real body mask.
    body = body_mask(creature, ppm=ppm, grow_mm=LINE_MM * 0.75)
    spine_img = np.full(body.shape, 255, np.uint8)
    cv2.polylines(spine_img, [np.round(line * ppm).astype(np.int32)], False, 0, 1)
    reach = cv2.distanceTransform(spine_img, cv2.DIST_L2, 5)
    half_mm = float(reach[body > 0].max()) / ppm + 1.0 if (body > 0).any() else         float(radii.max()) + 1.0

    tang = np.gradient(line, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    normal = np.stack([-tang[:, 1], tang[:, 0]], axis=1)

    strip_h = int(round(half_mm * 2 * ppm))
    offsets = np.linspace(-half_mm, half_mm, strip_h)

    # sample position for every (row, column) of the strip
    src = line[None, :, :] + normal[None, :, :] * offsets[:, None, None]
    map_x = (src[:, :, 0] * ppm).astype(np.float32)
    map_y = (src[:, :, 1] * ppm).astype(np.float32)

    strip = cv2.remap(rgba_sheet, map_x, map_y, cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

    # Limbs were unwrapped along with the body; keep only the trunk. Unwrapping
    # the body mask by the very same mapping works for any shape, whereas a
    # radius test only ever describes a tube.
    keep = cv2.remap(body, map_x, map_y, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    keep = spine_connected(keep, int(round(SPINE_GAP_MM * ppm)))
    strip[:, :, 3] = np.minimum(strip[:, :, 3], keep)

    meta = {
        "length_mm": length_mm,
        "half_mm": half_mm,
        "samples": samples,
        # 3 decimals, not 1: samples sit 1/ppm mm apart, so coarse rounding makes
        # the numerical tangent between neighbours badly noisy
        "radius_mm": [round(float(r), 3) for r in radii],
        "spine_mm": [[round(float(x), 3), round(float(y), 3)] for x, y in line],
    }
    return strip, meta


def effective_anchor(creature, limb):
    """Where a limb hangs off the spine. Explicit-outline limbs don't declare it,
    so take the spine sample nearest their pivot."""
    if limb.anchor is not None:
        return float(limb.anchor)
    line, _ = body_centerline(creature)
    line = np.asarray(line)
    if limb.pivot is not None:
        pivot = np.asarray(limb.pivot, dtype=float)
    elif limb.outline is not None:
        pivot = np.asarray(limb.outline, dtype=float).mean(axis=0)
    else:
        return 0.5
    return float(np.argmin(np.linalg.norm(line - pivot, axis=1))) / (len(line) - 1)


def cut_limb(rgba_sheet, creature, limb, ppm=WARP_PPM):
    """Cut a limb into rigid pieces. Explicit-outline limbs stay in one piece."""
    pieces = []
    if limb.parts:
        pieces = [(np.asarray(poly, float), np.asarray(pivot, float), np.asarray(tip, float))
                  for poly, pivot, tip in limb.parts]
    elif limb.outline is not None:
        poly = np.asarray(limb.outline, dtype=float)
        pivot = np.asarray(limb.pivot if limb.pivot else poly.mean(axis=0), dtype=float)
        pieces.append((poly, pivot, pivot))
    else:
        joints = limb_joints(creature, limb)
        widths = np.asarray(limb.widths, dtype=float)
        for i in range(len(joints) - 1):
            a, b = joints[i], joints[i + 1]
            seg = np.stack([a, b])
            dense, _ = resample_by_length(seg, 24)
            r = np.linspace(widths[i] / 2, widths[i + 1] / 2, len(dense))
            pieces.append((tube_outline(dense, r), a, b))

    out = []
    for poly, pivot, tip in pieces:
        mask = np.zeros(rgba_sheet.shape[:2], np.uint8)
        cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
        x, y, w, h = cv2.boundingRect(mask)
        pad = int(round(1.5 * ppm))
        x, y = max(0, x - pad), max(0, y - pad)
        w = min(mask.shape[1] - x, w + 2 * pad)
        h = min(mask.shape[0] - y, h + 2 * pad)
        crop = rgba_sheet[y:y + h, x:x + w].copy()
        alpha = cv2.GaussianBlur(mask[y:y + h, x:x + w], (0, 0), 0.7)
        crop[:, :, 3] = np.minimum(crop[:, :, 3], alpha)
        out.append({
            "image": crop,
            "origin_mm": [x / ppm, y / ppm],
            "pivot_mm": [float(pivot[0]), float(pivot[1])],
            "tip_mm": [float(tip[0]), float(tip[1])],
            "length_mm": float(np.linalg.norm(np.asarray(tip) - np.asarray(pivot))),
        })
    return out


def rigid_body(rgba_sheet, creature, ppm=WARP_PPM):
    """A body given as an explicit outline cannot bend; cut it as one rigid piece."""
    poly = np.asarray(creature.outline[0], dtype=float)
    mask = np.zeros(rgba_sheet.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
    x, y, w, h = cv2.boundingRect(mask)
    pad = int(round(1.5 * ppm))
    x, y = max(0, x - pad), max(0, y - pad)
    w, h = min(mask.shape[1] - x, w + 2 * pad), min(mask.shape[0] - y, h + 2 * pad)
    crop = rgba_sheet[y:y + h, x:x + w].copy()
    crop[:, :, 3] = np.minimum(crop[:, :, 3],
                               cv2.GaussianBlur(mask[y:y + h, x:x + w], (0, 0), 0.7))
    meta = {"rigid": True,
            "origin_mm": [round(x / ppm, 2), round(y / ppm, 2)],
            "size_mm": [round(w / ppm, 2), round(h / ppm, 2)]}
    return crop, meta


SHEET_BLEED_MM = 2.5


def sheet_for_texture(rgba_sheet, ppm=WARP_PPM):
    """The whole drawing as one opaque image, for texturing a 3D model.

    The cut-out is trimmed a little inside the printed line, so a mesh built on
    the full outline samples past its edge and would come out transparent
    there. Bleeding the colours outwards is the usual cure and costs nothing.
    """
    rgb = rgba_sheet[:, :, :3].copy()
    alpha = rgba_sheet[:, :, 3]
    solid = (alpha > 8).astype(np.uint8)
    k = int(round(SHEET_BLEED_MM * ppm)) * 2 + 1
    kernel = np.ones((k, k), np.uint8)
    grown = cv2.dilate(rgb, kernel)
    reach = cv2.dilate(solid, kernel) > 0
    out = np.where((solid > 0)[:, :, None], rgb,
                   np.where(reach[:, :, None], grown, 255)).astype(np.uint8)
    return out


def build_rig(rgba_sheet, creature, out_dir, name, ppm=WARP_PPM):
    """Write strip + limb images and a rig.json describing how they fit together."""
    os.makedirs(out_dir, exist_ok=True)
    if creature.rigid:
        strip, meta = rigid_body(rgba_sheet, creature, ppm)
    else:
        strip, meta = unwrap_body(rgba_sheet, creature, ppm)
    write_image(os.path.join(out_dir, "body.png"), strip)
    write_image(os.path.join(out_dir, "sheet.png"), sheet_for_texture(rgba_sheet, ppm))

    limbs = []
    for idx, limb in enumerate(creature.limbs):
        segs = cut_limb(rgba_sheet, creature, limb, ppm)
        entry = {"name": limb.name, "anchor": round(effective_anchor(creature, limb), 4),
                 "side": int(limb.side), "phase": limb.phase, "segments": []}
        for i, s in enumerate(segs):
            # the index belongs in the name: both legs of a pair share a
            # name, and without it the second one overwrites the first
            fname = f"limb_{idx}_{limb.name}_{i}.png"
            write_image(os.path.join(out_dir, fname), s["image"])
            entry["segments"].append({
                "image": fname,
                "origin_mm": [round(v, 2) for v in s["origin_mm"]],
                "pivot_mm": [round(v, 2) for v in s["pivot_mm"]],
                "tip_mm": [round(v, 2) for v in s["tip_mm"]],
                "length_mm": round(s["length_mm"], 2),
            })
        limbs.append(entry)

    rig = {
        "name": name,
        "creature": creature.key,
        "label": creature.label,
        "motion": creature.motion,
        "view": creature.view,
        "ppm": ppm,
        "sheet_mm": [SHEET_W_MM, SHEET_H_MM],
        "body": {"image": "body.png", **meta},
        "sheet": "sheet.png",
        "limbs": limbs,
    }
    with open(os.path.join(out_dir, "rig.json"), "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=1)
    return rig
