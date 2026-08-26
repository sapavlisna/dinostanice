"""Turning a flat drawn shape into a rounded 3D body.

The child draws a side view, so the depth is not in the drawing -- it has to be
invented. Inflation invents it the way a plush toy does: the further a point
lies from the outline, the further it bulges out of the paper. Take the local
half-thickness R of the shape at that point and the distance D to the outline,
and z = sqrt(D * (2R - D)) is exactly the circular cross-section a tube of
radius R would have. A limb drawn 14 mm wide comes out 14 mm deep, a
stegosaur's plate stays a plate, and nothing needs tuning per creature.

The mesh keeps sheet coordinates, so its texture coordinates are simply where
the point sits on the printed page: seen from the side, the model reproduces
the drawing exactly, and turning it wraps the same colours over the back.
"""

import cv2
import numpy as np
from scipy.spatial import Delaunay

from .shapes import SHEET_W_MM, SHEET_H_MM

INFLATE_PPM = 8.0        # raster resolution the depth field is computed at
SPACING_MM = 2.4         # target edge length of the triangulation
SKEL_BLUR_PX = 2.5       # same smoothing silhouette.py uses; kills pixel-noise twigs
RADIUS_SMOOTH_MM = 3.0   # blurs the Voronoi steps out of the local-radius field
DEPTH_SMOOTH_MM = 1.2    # final polish on the height field


def medial_axis(mask):
    smooth = cv2.GaussianBlur(mask, (0, 0), SKEL_BLUR_PX)
    smooth = ((smooth > 127) * 255).astype(np.uint8)
    return cv2.bitwise_and(cv2.ximgproc.thinning(smooth), mask)


def depth_field(mask, ppm=INFLATE_PPM, depth=1.0):
    """Height above the paper for every pixel, in millimetres.

    R is read off the shape's own medial axis rather than guessed, which is what
    makes a thin plate stay thin while the belly next to it goes round.
    """
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5) / ppm

    skel = medial_axis(mask)
    if not skel.any():                      # a shape too small to thin: treat it as a disc
        return depth * np.sqrt(np.maximum(dist * (2 * dist.max() - dist), 0.0))

    # Nearest medial-axis pixel for every point, so R can be looked up there.
    _, labels = cv2.distanceTransformWithLabels(
        cv2.bitwise_not(skel), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros(int(labels.max()) + 1, np.float32)
    lut[labels[skel > 0]] = dist[skel > 0]
    radius = _smooth_inside(lut[labels], mask, RADIUS_SMOOTH_MM * ppm)

    d = np.minimum(dist, radius)
    z = depth * np.sqrt(np.maximum(d * (2 * radius - d), 0.0))
    z = _smooth_inside(z, mask, DEPTH_SMOOTH_MM * ppm)
    return np.where(mask > 0, z, 0.0)


def _smooth_inside(field, mask, sigma_px):
    """Blur a field without letting the empty paper around the shape bleed in.

    Nearest-medial-axis lookup is a Voronoi partition, so R jumps from one value
    to another across every cell wall. Inflating that raw covers the animal in
    faint lumps and facets. Dividing two blurs -- of the field and of the mask --
    smooths across those walls while keeping the mask's own edge intact.
    """
    if sigma_px <= 0:
        return field
    m = (mask > 0).astype(np.float32)
    num = cv2.GaussianBlur(field.astype(np.float32) * m, (0, 0), sigma_px)
    den = cv2.GaussianBlur(m, (0, 0), sigma_px)
    return np.where(den > 1e-4, num / np.maximum(den, 1e-4), field)


def _contours_mm(mask, ppm):
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not len(cnts):
        return []
    return [c.reshape(-1, 2).astype(float) / ppm for c in cnts
            if cv2.contourArea(c) > (1.0 * ppm) ** 2]


def _resample_closed(poly, spacing):
    d = np.linalg.norm(np.diff(np.vstack([poly, poly[:1]]), axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    n = max(8, int(round(s[-1] / spacing)))
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(t, s, np.vstack([poly, poly[:1]])[:, 0]),
                     np.interp(t, s, np.vstack([poly, poly[:1]])[:, 1])], axis=1)


def sample_field(field, pts, ppm):
    """Bilinear lookup of a pixel field at millimetre positions."""
    x = np.clip(pts[:, 0] * ppm, 0, field.shape[1] - 1.001).astype(np.float32)
    y = np.clip(pts[:, 1] * ppm, 0, field.shape[0] - 1.001).astype(np.float32)
    return cv2.remap(field, x[None, :], y[None, :],
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]


def _thin_out(fixed, extra, min_dist):
    """Drop points of `extra` that crowd `fixed` or each other.

    Where the shape narrows, an inset ring collapses onto the outline and the
    triangulation degenerates into slivers that the inside test then throws
    away, leaving pinholes along the rim.
    """
    cell = min_dist
    buckets = {}
    for p in fixed:
        buckets.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    keep = []
    for p in extra:
        cx, cy = int(p[0] // cell), int(p[1] // cell)
        crowded = any(
            (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < min_dist ** 2
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            for q in buckets.get((cx + dx, cy + dy), ()))
        if not crowded:
            buckets.setdefault((cx, cy), []).append(p)
            keep.append(p)
    return np.array(keep) if keep else np.zeros((0, 2))


def _inside(mask, pts, ppm):
    x = np.clip(np.round(pts[:, 0] * ppm).astype(int), 0, mask.shape[1] - 1)
    y = np.clip(np.round(pts[:, 1] * ppm).astype(int), 0, mask.shape[0] - 1)
    return mask[y, x] > 0


def inflate(mask, ppm=INFLATE_PPM, depth=1.0, spacing=SPACING_MM):
    """Mask -> closed rounded mesh. Coordinates stay in sheet millimetres.

    Returns positions (N,3), uvs (N,2) and triangle indices (M,3).
    """
    z_img = depth_field(mask, ppm, depth)
    rings = _contours_mm(mask, ppm)
    if not rings:
        raise ValueError("prázdná maska, není co nafouknout")

    border = np.vstack([_resample_closed(r, spacing) for r in rings])

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5) / ppm

    # Two rings just inside the outline. The depth field meets the edge
    # vertically -- that is what makes the rim round rather than sharp -- so it
    # climbs several millimetres within the first one, and without extra rows
    # there the round edge is carried by a single band of triangles and shows up
    # as a hard zigzag crease down the silhouette.
    inset = []
    for frac in (0.28, 0.62):
        k = int(round(frac * spacing * ppm)) * 2 + 1
        eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        inset += [_resample_closed(r, spacing) for r in _contours_mm(eroded, ppm)]
    inset = np.vstack(inset) if inset else np.zeros((0, 2))
    lo = border.min(axis=0)
    hi = border.max(axis=0)
    step = spacing * 0.92
    rows = []
    for j, y in enumerate(np.arange(lo[1], hi[1] + step, step)):
        xs = np.arange(lo[0] + (step / 2 if j % 2 else 0), hi[0] + step, step)
        rows.append(np.stack([xs, np.full_like(xs, y)], axis=1))
    grid = np.vstack(rows)
    grid = grid[sample_field(dist.astype(np.float32), grid, ppm) > spacing * 1.15]

    # The medial axis guarantees a row of vertices down every thin feature. A
    # neck narrower than a couple of triangles would otherwise get none, and the
    # surface there collapses into a flat membrane with a pinhole at each end.
    spine_px = np.argwhere(medial_axis(mask) > 0)[:, ::-1] / ppm
    spine_px = _thin_out(np.zeros((0, 2)), spine_px, spacing * 0.8)

    extra = _thin_out(np.vstack([border, spine_px]), np.vstack([inset, grid]),
                      spacing * 0.45)
    pts = np.vstack([border, spine_px, extra])
    tri = Delaunay(pts)

    # Delaunay fills the convex hull, so anything bridging a concavity or a hole
    # has to go. Testing the edge midpoints too rejects slivers that creep across
    # a notch while keeping their centroid on the solid side.
    simp = tri.simplices
    a, b, c = pts[simp[:, 0]], pts[simp[:, 1]], pts[simp[:, 2]]
    # Pulled a little towards the centre: a triangle spanning a narrow neck has
    # its edge midpoints sitting right on the outline, and testing them raw
    # rejects perfectly good geometry wherever rounding lands a pixel outside.
    mid = (a + b + c) / 3
    probes = [mid] + [m * 0.75 + mid * 0.25 for m in ((a + b) / 2, (b + c) / 2, (a + c) / 2)]
    keep = np.ones(len(simp), bool)
    for p in probes:
        keep &= _inside(mask, p, ppm)
    simp = simp[keep]

    z = sample_field(z_img.astype(np.float32), pts, ppm)
    on_rim = np.zeros(len(pts), bool)
    on_rim[:len(border)] = True
    z[on_rim] = 0.0

    # Front and back share the rim vertices, which is what rounds the edge off:
    # the depth field meets the outline vertically, so the welded normal there
    # points sideways and the silhouette reads as a rolled edge, not a blade.
    n = len(pts)
    back_of = np.where(on_rim, np.arange(n), np.arange(n) + n)
    pos = np.concatenate([
        np.column_stack([pts, z]),
        np.column_stack([pts, -z]),
    ])
    # Where the shape is thinner than the grid spacing there are no interior
    # points, so the triangle sits flat on the paper. Mirroring it would lay a
    # second copy exactly on top, whose face normal cancels the first and leaves
    # the vertex unshaded. Such a patch is a membrane: emit it once, rendered
    # from both sides.
    flat = on_rim[simp].all(axis=1)
    faces = np.vstack([simp, back_of[simp[~flat]][:, ::-1]])

    used = np.unique(faces)
    remap = np.full(len(pos), -1, np.int64)
    remap[used] = np.arange(len(used))
    pos = pos[used]
    faces = remap[faces]

    uv = np.column_stack([pos[:, 0] / SHEET_W_MM, 1.0 - pos[:, 1] / SHEET_H_MM])
    return pos, uv, faces


def vertex_normals(pos, faces):
    """Area-weighted normals; the shared rim gets front and back averaged in."""
    v0, v1, v2 = pos[faces[:, 0]], pos[faces[:, 1]], pos[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    out = np.zeros_like(pos)
    for k in range(3):
        np.add.at(out, faces[:, k], fn)
    norm = np.linalg.norm(out, axis=1, keepdims=True)
    out = np.where(norm > 1e-9, out / np.maximum(norm, 1e-9), np.array([0.0, 0.0, 1.0]))
    return out
