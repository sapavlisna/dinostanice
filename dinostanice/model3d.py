"""Assembling a creature's 3D model from its drawn silhouette.

The whole animal is inflated as **one continuous skin**. An earlier attempt
inflated the trunk and each limb separately and pushed them apart, which meant
the trunk had to be grown back into the leg sockets so the pieces would not
part -- and that growth hung four short stumps under the belly, so the animal
read as having eight legs. One skin has no sockets and no seams.

Depth still has to separate the legs: on a side view the near and the far leg
are drawn next to each other on the paper, and left flat the model is a
cardboard cut-out. So each leg gets a weight field that is 1 deep inside it and
fades to 0 at the hip, and the leg is displaced in depth by that weight. The
skin shears smoothly across the shoulder instead of breaking.

The same weights drive the walk: a vertex rotates about its hip by weight times
the swing angle, which bends the leg at the hip without a skeleton.

Which parts of the drawing are legs is decided by the silhouette, not by the
skeleton-branch segmentation: anything sticking out past the trunk's thickness
profile is a limb. That segmentation is what loses a leg to a 7 mm stump now
and then, and a stump would splay and swing while the rest of the drawn leg
stood still.
"""

import cv2
import numpy as np

from . import inflate
from .raster import _to_px, creature_mask
from .shapes import (SHEET_H_MM, SHEET_W_MM, body_centerline, limb_polygons,
                     tube_outline)

PPM = inflate.INFLATE_PPM
LIMB_SPREAD = 0.80       # how far out of the body a limb sits, as a share of body depth
TUBE_SLACK_MM = 1.5      # how far past the thickness profile counts as a limb
MIN_LIMB_AREA_MM2 = 60.0
BLEND_MM = 4.0           # how far a limb's influence reaches up into the trunk

# A diagonal pair swings together: the simplest gait that still reads as walking.
PHASE = {(0, "front"): 0.0, (1, "front"): 0.5, (0, "hind"): 0.5, (1, "hind"): 0.0}


def _blank():
    return np.zeros((int(round(SHEET_H_MM * PPM)), int(round(SHEET_W_MM * PPM))), np.uint8)


def _grow(mask, mm):
    k = int(round(mm * PPM)) * 2 + 1
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def _limb_pivot(creature, limb):
    if limb.parts:
        return np.asarray(limb.parts[0][1], dtype=float)
    if limb.pivot is not None:
        return np.asarray(limb.pivot, dtype=float)
    return np.asarray(limb_polygons(creature, limb)[0], dtype=float).mean(axis=0)


def _limb_mask(creature, limb):
    mask = _blank()
    for poly in limb_polygons(creature, limb):
        cv2.fillPoly(mask, [_to_px(poly, PPM)], 255)
    return mask


def _phase(limb):
    group = "hind" if "hind" in limb.name else "front"
    return PHASE.get((int(limb.side), group), 0.0)


def _body_depth_at(creature, point):
    """Half-thickness of the trunk nearest a point -- how far out a limb belongs."""
    line, radii = body_centerline(creature)
    i = int(np.argmin(np.linalg.norm(np.asarray(line) - point, axis=1)))
    return float(radii[i])


def trunk_tube(creature):
    """The body as the thickness profile describes it: no limbs, no frills."""
    line, radii = body_centerline(creature)
    mask = _blank()
    cv2.fillPoly(mask, [_to_px(tube_outline(np.asarray(line), radii), PPM)], 255)
    return mask


def _nearest_owner(masks):
    """For every pixel, which of `masks` is closest. Ties go to the lower index."""
    seeds = np.zeros_like(masks[0])
    for m in masks:
        seeds = cv2.bitwise_or(seeds, m)
    _, labels = cv2.distanceTransformWithLabels(
        cv2.bitwise_not(seeds), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.full(int(labels.max()) + 1, -1, np.int32)
    for i, m in reversed(list(enumerate(masks))):     # lower index wins an overlap
        lut[labels[m > 0]] = i
    return lut[labels]


def limb_regions(creature):
    """(region mask, limb) for every limb the silhouette actually shows.

    A region is the drawing outside the trunk's thickness profile, so it is the
    whole drawn leg however badly the skeleton segmentation carved it up -- that
    segmentation is what turns a leg into a 7 mm stump now and then. The
    declared limb only says which side of the body the leg is on and where its
    hip sits.

    Two legs of a pair are drawn side by side and the strip of belly between
    them joins them into one lump, so the lump is divided between the nearest
    declared limbs. Restricting each share to the piece touching that limb's own
    polygon is what keeps a stegosaur's plates -- which also stick out past the
    profile, but never move -- from being claimed as legs.
    """
    whole = creature_mask(creature, ppm=PPM)
    beyond = cv2.bitwise_and(whole, cv2.bitwise_not(_grow(trunk_tube(creature),
                                                          TUBE_SLACK_MM)))
    declared = [(limb, _limb_mask(creature, limb)) for limb in creature.limbs]
    if not declared:
        return [], []
    owner = _nearest_owner([m for _, m in declared])

    out, missed = [], []
    for i, (limb, mask) in enumerate(declared):
        share = ((beyond > 0) & (owner == i)).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(share)
        keep = np.zeros_like(share, bool)
        for j in range(1, count):
            if stats[j, cv2.CC_STAT_AREA] < MIN_LIMB_AREA_MM2 * PPM ** 2:
                continue
            piece = labels == j
            if np.any(piece & (mask > 0)):
                keep |= piece
        if not keep.any():
            missed.append(limb.name)
            continue
        out.append((keep.astype(np.uint8) * 255, limb))
    return out, missed


def _weights(regions, pts):
    """Per-vertex influence of each limb, faded over BLEND_MM at the hip."""
    sigma = BLEND_MM * PPM / 2.0
    out = []
    for comp, _ in regions:
        field = cv2.GaussianBlur((comp > 0).astype(np.float32), (0, 0), sigma)
        # A blur never reaches 1 inside a leg only a few millimetres wide, so the
        # ramp is stretched and clipped instead of normalised.
        field = np.clip(field * 1.7, 0.0, 1.0).astype(np.float32)
        out.append(inflate.sample_field(field, pts, PPM))
    return out


def _spine_param(creature, pts):
    """Position along the spine, 0 at the nose and 1 at the tail tip, per vertex.

    Lets the renderer sway the neck and the tail without a skeleton: everything
    is already indexed by how far down the animal it sits.
    """
    line, _ = body_centerline(creature)
    line = np.asarray(line)
    d = np.linalg.norm(np.diff(line, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    s /= max(s[-1], 1e-9)
    near = np.argmin(((pts[:, None, :2] - line[None, :, :]) ** 2).sum(axis=2), axis=1)
    return s[near]


def build(creature, spacing=inflate.SPACING_MM):
    """Creature -> one skinned part plus notes about anything that looked wrong."""
    notes = []
    mask = creature_mask(creature, ppm=PPM)
    pos, uv, faces = inflate.inflate(mask, PPM, spacing=spacing)

    regions, missed = limb_regions(creature)
    if missed:
        notes.append("v siluetě se nenašla končetina: " + ", ".join(sorted(set(missed))))

    limbs = []
    for (comp, limb), w in zip(regions, _weights(regions, pos[:, :2])):
        pivot = _limb_pivot(creature, limb)
        # A creature drawn from above already has its left and right limbs apart
        # on the paper; there the depth axis is up, and splaying would lift one
        # wing off the body.
        z = 0.0 if creature.view == "top" else LIMB_SPREAD * _body_depth_at(creature, pivot)
        z = z if int(limb.side) == 0 else -z
        pos[:, 2] += w * z                      # baked: the rest pose already splays
        inside = np.argwhere(comp > 0)[:, ::-1] / PPM
        reach = float(np.linalg.norm(inside - pivot, axis=1).max()) if len(inside) else 0.0
        limbs.append({"name": limb.name, "side": int(limb.side), "phase": _phase(limb),
                      "pivot": [float(pivot[0]), float(pivot[1]), float(z)],
                      "length_mm": reach, "weight": w})

    # Normals only after the shear: taken from the flat rest pose they would
    # light the splayed legs as though they still lay in the plane of the paper.
    nrm = inflate.vertex_normals(pos, faces)

    part = {"name": "body", "kind": "body", "pos": pos, "uv": uv, "nrm": nrm,
            "faces": faces, "spine_t": _spine_param(creature, pos), "limbs": limbs}
    return part, notes


def to_json(creature, part, notes):
    def flat(a, nd):
        return [round(float(v), nd) for v in np.asarray(a).ravel()]

    line, _ = body_centerline(creature)
    line = np.asarray(line)
    d = np.linalg.norm(np.diff(line, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])

    # One id and one weight per vertex rather than a field per limb: the
    # influences barely overlap, and where they do the stronger one wins.
    stack = (np.stack([l["weight"] for l in part["limbs"]]) if part["limbs"]
             else np.zeros((1, len(part["pos"])), np.float32))
    best = stack.argmax(axis=0)
    top = stack.max(axis=0)
    limb_id = np.where(top > 0.02, best, -1)

    return {
        "key": creature.key, "label": creature.label, "motion": creature.motion,
        "view": creature.view, "sheet_mm": [SHEET_W_MM, SHEET_H_MM], "notes": notes,
        # the spine travels with the model so the renderer can pick a hinge for
        # the neck or the tail without knowing anything about the creature
        "spine": [[round(float(x), 2), round(float(y), 2)] for x, y in line],
        "spine_s": [round(float(v / max(s[-1], 1e-9)), 4) for v in s],
        "pos": flat(part["pos"], 2), "nrm": flat(part["nrm"], 3),
        "uv": flat(part["uv"], 4),
        "idx": [int(v) for v in np.asarray(part["faces"]).ravel()],
        "spine_t": flat(part["spine_t"], 3),
        "limb_id": [int(v) for v in limb_id],
        "limb_w": flat(np.where(limb_id >= 0, top, 0.0), 2),
        "limbs": [{"name": l["name"], "side": l["side"], "phase": l["phase"],
                   "pivot": [round(v, 2) for v in l["pivot"]],
                   "length_mm": round(l["length_mm"], 1)} for l in part["limbs"]],
    }
