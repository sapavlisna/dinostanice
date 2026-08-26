"""Creature definitions.

A creature is a spine curve with a thickness profile plus limbs attached at
parameter positions along that spine. The printed outline, the fill mask and
the animation rig are all derived from this one definition, so a coloured-in
drawing always registers exactly onto the skeleton that moves it.

All coordinates are millimetres on a landscape A4 sheet (297 x 210).
"""

from dataclasses import dataclass, field
import numpy as np

SHEET_W_MM = 297.0
SHEET_H_MM = 210.0


@dataclass
class Limb:
    name: str
    anchor: float = None    # position along body spine (0 = nose); derived if None
    segments: list = None   # [(length_mm, angle_deg_from_vertical), ...] root -> tip
    widths: list = None     # thickness at each joint, len == len(segments) + 1
    foot: float = 0.0       # extra forward extension of the last segment (hoof/claw)
    side: int = 0           # 0 = near side, 1 = far side (drawn behind body)
    phase: float = 0.0      # gait phase offset, 0..1
    outline: list = None    # explicit polygon in sheet mm; overrides segments/widths
    pivot: tuple = None     # rotation centre for an explicit-outline limb
    parts: list = None      # [(polygon_mm, pivot_mm, tip_mm), ...] root -> tip


@dataclass
class Creature:
    key: str
    label: str
    spine: list             # [(x_mm, y_mm), ...] nose -> tail tip
    profile: list           # radius in mm at each spine point
    outline: list = None    # [outer_polygon, hole, ...] in sheet mm; overrides spine/profile
    rigid: bool = False     # a rigid body is drawn as one piece instead of bending
    limbs: list = field(default_factory=list)
    eye: tuple = None       # (x_mm, y_mm, r_mm) drawn on the template, not part of the mask
    motion: str = "walk"    # walk | swim | fly | sail
    view: str = "side"      # side | top
    ground_bias: float = 0.0
    details: list = field(default_factory=list)   # extra polylines drawn on the template only


def catmull_rom(points, samples_per_segment=14):
    """Smooth an open polyline; endpoints are duplicated so the curve reaches them."""
    p = np.asarray(points, dtype=float)
    if len(p) < 3:
        return p
    ext = np.vstack([p[0] + (p[0] - p[1]), p, p[-1] + (p[-1] - p[-2])])
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t = np.linspace(0.0, 1.0, samples_per_segment, endpoint=False)[:, None]
        out.append(
            0.5 * ((2 * p1)
                   + (-p0 + p2) * t
                   + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
        )
    out.append(ext[-2][None, :])
    return np.vstack(out)


def smooth_closed(points, samples_per_segment=10):
    """Catmull-Rom through a closed loop of control points.

    Hand-placed polygons read as crude next to a traced silhouette; running the
    same few points through a spline is what makes a hull look like a hull.
    """
    p = np.asarray(points, dtype=float)
    n = len(p)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = p[(i - 1) % n], p[i], p[(i + 1) % n], p[(i + 2) % n]
        t = np.linspace(0.0, 1.0, samples_per_segment, endpoint=False)[:, None]
        out.append(
            0.5 * ((2 * p1)
                   + (-p0 + p2) * t
                   + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
        )
    return np.vstack(out)


def resample_profile(profile, n):
    src = np.linspace(0.0, 1.0, len(profile))
    dst = np.linspace(0.0, 1.0, n)
    return np.interp(dst, src, np.asarray(profile, dtype=float))


def tube_outline(centerline, radii, cap_samples=10):
    """Offset a centerline by +/- radius and close it with round caps."""
    c = np.asarray(centerline, dtype=float)
    tangents = np.gradient(c, axis=0)
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1e-9
    tangents = tangents / norms
    normals = np.stack([-tangents[:, 1], tangents[:, 0]], axis=1)
    r = np.asarray(radii, dtype=float)[:, None]

    left = c + normals * r
    right = c - normals * r

    # A cap is always exactly a half turn, from -n to +n going the long way
    # round past the tube's end. Deriving the direction from the angle
    # difference cannot work: that difference is precisely pi, so its sign
    # falls out of atan2 at random and the arc gets traced back into the tube,
    # self-intersecting the polygon and punching a crescent hole in the fill.
    def cap(center, radius, from_vec):
        a0 = np.arctan2(from_vec[1], from_vec[0])
        angles = np.linspace(a0, a0 - np.pi, cap_samples)
        return center + radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)

    start_cap = cap(c[0], float(r[0, 0]), -normals[0])
    end_cap = cap(c[-1], float(r[-1, 0]), normals[-1])
    return np.vstack([left, end_cap, right[::-1], start_cap])


def body_centerline(creature, samples_per_segment=14):
    line = catmull_rom(creature.spine, samples_per_segment)
    radii = resample_profile(creature.profile, len(line))
    return line, radii


def limb_joints(creature, limb, pose_angles=None):
    """World-space joint positions of a limb, root first."""
    line, _ = body_centerline(creature)
    idx = int(round(limb.anchor * (len(line) - 1)))
    root = line[idx].copy()
    angles = pose_angles if pose_angles is not None else [a for _, a in limb.segments]
    pts = [root]
    cur = root.copy()
    absolute = 0.0
    for (length, _), ang in zip(limb.segments, angles):
        absolute += ang
        rad = np.radians(absolute)
        # angle 0 points straight down the sheet (+y)
        cur = cur + np.array([np.sin(rad), np.cos(rad)]) * length
        pts.append(cur.copy())
    return np.array(pts)


def limb_polygons(creature, limb, pose_angles=None):
    """Every filled polygon belonging to a limb (a chain contributes several)."""
    if limb.parts:
        return [np.asarray(p, dtype=float) for p, _, _ in limb.parts]
    return [limb_outline(creature, limb, pose_angles)]


def limb_outline(creature, limb, pose_angles=None):
    if limb.parts:
        return np.asarray(limb.parts[0][0], dtype=float)
    if limb.outline is not None:
        return np.asarray(limb.outline, dtype=float)
    joints = limb_joints(creature, limb, pose_angles)
    line = catmull_rom(joints, 10) if len(joints) > 2 else joints
    dense = []
    for i in range(len(line) - 1):
        for t in np.linspace(0, 1, 6, endpoint=False):
            dense.append(line[i] * (1 - t) + line[i + 1] * t)
    dense.append(line[-1])
    dense = np.array(dense)
    radii = resample_profile([w / 2.0 for w in limb.widths], len(dense))
    return tube_outline(dense, radii)


def split_limb_polygon(polygon, joints, ppm=8.0):
    """Cut a limb's outline into one rigid piece per bone.

    A limb traced out of a silhouette arrives as a single blob; to bend at the
    knee it has to become a chain. Slicing it with the half-planes bisecting
    each joint keeps the drawn shape instead of replacing it with a tube.
    """
    import cv2

    poly = np.asarray(polygon, dtype=float)
    joints = np.asarray(joints, dtype=float)
    if len(joints) < 3:
        return [(poly, joints[0], joints[-1])]

    lo = poly.min(axis=0) - 2.0
    hi = poly.max(axis=0) + 2.0
    size = (int(np.ceil((hi[0] - lo[0]) * ppm)), int(np.ceil((hi[1] - lo[1]) * ppm)))
    mask = np.zeros((size[1], size[0]), np.uint8)
    cv2.fillPoly(mask, [np.round((poly - lo) * ppm).astype(np.int32)], 255)

    yy, xx = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    px = xx / ppm + lo[0]
    py = yy / ppm + lo[1]

    out = []
    for i in range(len(joints) - 1):
        keep = mask > 0
        for j, sign in ((i, -1.0), (i + 1, 1.0)):
            if j == 0 or j == len(joints) - 1:
                continue          # the ends are open, only interior joints cut
            d = joints[j + 1] - joints[j - 1]
            n = d / max(np.linalg.norm(d), 1e-9)
            side = (px - joints[j][0]) * n[0] + (py - joints[j][1]) * n[1]
            keep &= (side * sign) >= 0
        piece = (keep.astype(np.uint8)) * 255
        contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            continue
        c = max(contours, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 0.3 * ppm, True).reshape(-1, 2).astype(float) / ppm + lo
        out.append((c, joints[i], joints[i + 1]))
    return out or [(poly, joints[0], joints[-1])]


def creature_holes(creature):
    """Enclosed gaps in the silhouette, e.g. between a raised neck and the body."""
    if creature.outline is None or len(creature.outline) < 2:
        return []
    return [np.asarray(h, dtype=float) for h in creature.outline[1:]]


def creature_polygons(creature, poses=None):
    """All filled polygons of a creature in draw order (far limbs, body, near limbs)."""
    if creature.outline is not None:
        body = np.asarray(creature.outline[0], dtype=float)
    else:
        line, radii = body_centerline(creature)
        body = tube_outline(line, radii)
    far, near = [], []
    for limb in creature.limbs:
        pose = poses.get(limb.name) if poses else None
        bucket = far if limb.side else near
        for poly in limb_polygons(creature, limb, pose):
            bucket.append((limb.name, poly))
    return [("body", body)], far, near
