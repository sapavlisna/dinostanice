"""Deriving creature geometry from a filled silhouette bitmap.

A PhyloPic silhouette is one opaque blob with no structure in it. Thinning gives
a skeleton whose longest *thick* path is the spine, the distance transform of the
same blob gives the thickness profile at every point of it, and the skeleton
branches hanging off that path are limb candidates. Assigning every mask pixel to
its nearest skeleton point then cuts the blob into a body plus one region per
limb, along the natural haunch/shoulder boundary rather than a guessed line.

All output coordinates are millimetres on a landscape A4 sheet (297 x 210).
"""

import heapq
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import KDTree

from .markers import CORNER_ORIGINS, MARKER_MM
from .shapes import SHEET_W_MM, SHEET_H_MM

SHEET_MARGIN_MM = 7.0
LABEL_BAND_MM = 12.0
MARKER_CLEAR_MM = 7.0   # crayons overshoot the outline; keep the markers well clear

SKEL_BLUR_PX = 2.5          # boundary smoothing before thinning; kills pixel-noise twigs
PRUNE_RADIUS_FACTOR = 0.6   # a twig shorter than this times the local flesh radius is noise
PRUNE_MIN_PX = 6.0
SPINE_SAMPLES = 200
SPINE_SMOOTH = 3.0          # gaussian sigma in resampled spine steps
PROFILE_SMOOTH = 3.0
CONTOUR_SMOOTH_PX = 2.0     # gaussian sigma along the traced contour, in source pixels
CONTOUR_EPS_MM = 0.15
HOLE_MIN_MM2 = 2.0

THICKNESS_BIAS = 6.0        # how strongly the main path prefers thick flesh over length
BLUNT_FRACTION = 0.05       # arc fraction at each end used to tell a snout from a tail tip
BLUNT_MARGIN = 1.3          # below this ratio the bluntness test is called inconclusive
TAPER_LEVEL = 0.15          # fallback cue: fraction of max radius the ends are timed against

LIMB_MIN_AREA = 0.012       # region area / silhouette area
LIMB_MIN_REACH = 0.05       # branch skeleton length / spine length
LIMB_HEAD_ZONE = 0.18       # no limb may be anchored this close to the nose
LIMB_DOWN_COS = 0.35        # side view: limb must point at least ~20 deg below horizontal
LIMB_MIN_RELATIVE = 0.22    # a limb far smaller than the biggest one is a stray body part
TRUNK_INSIDE = 0.8          # branch closer to the spine than this share of the flesh radius is torso


@dataclass
class DerivedLimb:
    name: str
    anchor: float
    side: int
    joints: np.ndarray
    polygon: np.ndarray
    area_mm2: float = 0.0


@dataclass
class DerivedShape:
    outline: list
    spine: np.ndarray
    profile: np.ndarray
    limbs: list = field(default_factory=list)
    view: str = "side"
    motion: str = "walk"
    scale: float = 1.0          # mm per source pixel
    offset: tuple = (0.0, 0.0)
    notes: dict = field(default_factory=dict)


# ---------------------------------------------------------------- mask & sheet

def load_mask(png_path):
    im = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(png_path)
    if im.ndim == 3 and im.shape[2] == 4:
        alpha = im[:, :, 3]
    elif im.ndim == 3:
        alpha = 255 - cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    else:
        alpha = 255 - im
    mask = (alpha > 127).astype(np.uint8) * 255
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    dropped = 0
    if n > 2:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        dropped = int(n - 2)
        mask = (lab == keep).astype(np.uint8) * 255
    return mask, dropped


def _forbidden_rects():
    c = MARKER_CLEAR_MM
    return [(ox - c, oy - c, ox + MARKER_MM + c, oy + MARKER_MM + c)
            for ox, oy in CORNER_ORIGINS]


def drawing_area():
    """Rectangle the creature is fitted into, before the corner cut-outs."""
    x0 = SHEET_MARGIN_MM
    x1 = SHEET_W_MM - SHEET_MARGIN_MM
    y0 = SHEET_MARGIN_MM
    # the bottom markers stick down into the label band, so anything below their
    # top edge is unusable at the corners; keeping the whole strip clear is
    # simpler than carving two more notches and costs nothing in practice
    y1 = min(SHEET_H_MM - LABEL_BAND_MM,
             CORNER_ORIGINS[3][1] - MARKER_CLEAR_MM)
    return x0, y0, x1, y1


def _place(mask):
    """Largest uniform scale + offset that keeps the blob inside the drawing area."""
    ys, xs = np.nonzero(mask[::3, ::3])
    pts = np.stack([xs * 3.0, ys * 3.0], 1)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    edge = np.vstack([c.reshape(-1, 2) for c in cnts]).astype(float)
    pts = np.vstack([pts, edge])
    lo = pts.min(0)
    span = pts.max(0) - lo + 1.0
    pts = pts - lo

    x0, y0, x1, y1 = drawing_area()
    bad = _forbidden_rects()

    grid = np.linspace(0, 1, 9)
    offsets = sorted(((abs(fx - 0.5) + abs(fy - 0.5), fx, fy) for fx in grid for fy in grid))

    def legal(scale):
        w, h = span * scale
        free = np.array([x1 - x0 - w, y1 - y0 - h])
        if free.min() < -1e-6:
            return None
        p = pts * scale
        for _, fx, fy in offsets:
            tx, ty = x0 + free[0] * fx, y0 + free[1] * fy
            qx, qy = p[:, 0] + tx, p[:, 1] + ty
            if not any(np.any((qx > bx0) & (qx < bx1) & (qy > by0) & (qy < by1))
                       for bx0, by0, bx1, by1 in bad):
                return tx, ty
        return None

    hi = min((x1 - x0) / span[0], (y1 - y0) / span[1])
    found = legal(hi)
    if found is not None:
        return hi, (found[0] - lo[0] * hi, found[1] - lo[1] * hi)
    plo, phi = 0.2 * hi, hi
    best = None
    for _ in range(24):
        mid = 0.5 * (plo + phi)
        got = legal(mid)
        if got is None:
            phi = mid
        else:
            plo = mid
            best = (mid, got)
    scale, (tx, ty) = best
    return scale, (tx - lo[0] * scale, ty - lo[1] * scale)


# ---------------------------------------------------------------- skeleton graph

def _skeleton(mask):
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), SKEL_BLUR_PX)
    smooth = (blurred > 127).astype(np.uint8) * 255
    n, lab, stats, _ = cv2.connectedComponentsWithStats(smooth, 8)
    if n > 2:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        smooth = (lab == keep).astype(np.uint8) * 255
    skel = cv2.ximgproc.thinning(smooth)
    dist = cv2.distanceTransform(smooth, cv2.DIST_L2, 5)
    return _prune(skel, dist), dist, smooth


def _prune(skel, dist, rounds=6):
    """Drop terminal twigs shorter than the flesh radius at the junction they hang on.

    Thinning turns every bump on the outline into a spur. A branch that does not
    reach further out than the inscribed circle it sprouts from cannot be a limb;
    it is boundary noise, and leaving it in floods the limb search with hundreds
    of one-pixel candidates.
    """
    skel = skel.copy()
    for _ in range(rounds):
        pts, nbr = _graph(skel)
        if len(pts) == 0:
            break
        deg = np.array([len(n) for n in nbr])
        doomed = []
        for e in np.nonzero(deg == 1)[0]:
            cur, prev, chain, length, junction = int(e), -1, [int(e)], 0.0, None
            while True:
                nxt = [(v, w) for v, w in nbr[cur] if v != prev]
                if len(nxt) != 1:
                    break
                v, w = nxt[0]
                length += w
                if deg[v] > 2:
                    junction = v
                    break
                prev, cur = cur, v
                chain.append(v)
            if junction is None:
                continue
            r = dist[int(pts[junction][1]), int(pts[junction][0])]
            if length < PRUNE_RADIUS_FACTOR * r + PRUNE_MIN_PX:
                doomed.extend(chain)
        if not doomed:
            break
        for i in doomed:
            skel[int(pts[i][1]), int(pts[i][0])] = 0
    return skel


def _graph(skel):
    ys, xs = np.nonzero(skel)
    idx = -np.ones(skel.shape, np.int32)
    idx[ys, xs] = np.arange(len(ys))
    nbr = [[] for _ in range(len(ys))]
    h, w = skel.shape
    for dy, dx in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
        weight = 1.0 if dy == 0 or dx == 0 else 1.4142135624
        yy, xx = ys + dy, xs + dx
        ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
        j = np.where(ok, idx[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)], -1)
        for i in np.nonzero(j >= 0)[0]:
            nbr[i].append((int(j[i]), weight))

    # A thinned line often keeps an L of three mutually adjacent pixels, which
    # makes an ordinary point look like a three-way junction and would let the
    # twig pruner mistake half the spine for a branch. Dropping the diagonal
    # short-cut of every such triangle leaves degree meaning what it should.
    sets = [set(v for v, _ in n) for n in nbr]
    for i, n in enumerate(nbr):
        drop = {v for v, w in n if w > 1.1 and (sets[i] & sets[v])}
        if drop:
            nbr[i] = [(v, w) for v, w in n if v not in drop]
    return np.stack([xs, ys], 1).astype(float), nbr


def _dijkstra(nbr, src, weights=None):
    d = np.full(len(nbr), np.inf)
    prev = np.full(len(nbr), -1, np.int32)
    d[src] = 0.0
    q = [(0.0, src)]
    while q:
        du, u = heapq.heappop(q)
        if du > d[u] + 1e-9:
            continue
        for v, w in nbr[u]:
            if weights is not None:
                w = w * weights[v]
            nd = du + w
            if nd < d[v] - 1e-9:
                d[v] = nd
                prev[v] = u
                heapq.heappush(q, (nd, v))
    return d, prev


def _trace(prev, end):
    p = [int(end)]
    while prev[p[-1]] >= 0:
        p.append(int(prev[p[-1]]))
    return p[::-1]


def _main_path(pts, nbr, radius, mask, view):
    deg = np.array([len(n) for n in nbr])
    ends = list(np.nonzero(deg <= 1)[0])
    if len(ends) < 2:
        d0, _ = _dijkstra(nbr, 0)
        d0 = np.where(np.isinf(d0), -1, d0)
        a = int(np.argmax(d0))
        da, pa = _dijkstra(nbr, a)
        da = np.where(np.isinf(da), -1, da)
        return _trace(pa, int(np.argmax(da)))

    rmax = float(radius.max()) or 1.0
    axis = None
    if view == "top":
        ys, xs = np.nonzero(mask)
        cloud = np.stack([xs, ys], 1).astype(float)
        cloud -= cloud.mean(0)
        _, vecs = np.linalg.eigh(np.cov(cloud.T))
        axis = vecs[:, 0]          # minor axis = the body, not the wingspan

    sweeps = {e: _dijkstra(nbr, e) for e in ends}
    best, best_score = None, -np.inf
    for i, a in enumerate(ends):
        da, pa = sweeps[a]
        for b in ends[i + 1:]:
            if np.isinf(da[b]):
                continue
            if axis is not None:
                score = abs(float((pts[a] - pts[b]) @ axis))
            else:
                path = _trace(pa, b)
                r = radius[pts[path][:, 1].astype(int), pts[path][:, 0].astype(int)]
                step = np.linalg.norm(np.diff(pts[path], axis=0), axis=1)
                w = 1.0 + THICKNESS_BIAS * 0.5 * (r[:-1] + r[1:]) / rmax
                score = float((step * w).sum())
            if score > best_score:
                best_score, best = score, (a, b)
    a, b = best
    return _trace(sweeps[a][1], b)


# ---------------------------------------------------------------- spine & profile

def _resample(poly, n):
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))])
    if d[-1] <= 0:
        return np.repeat(poly[:1], n, axis=0)
    t = np.linspace(0.0, d[-1], n)
    return np.stack([np.interp(t, d, poly[:, 0]), np.interp(t, d, poly[:, 1])], 1)


def _smooth_open(poly, sigma):
    if sigma <= 0 or len(poly) < 5:
        return poly
    out = np.stack([gaussian_filter1d(poly[:, 0], sigma, mode="nearest"),
                    gaussian_filter1d(poly[:, 1], sigma, mode="nearest")], 1)
    out[0], out[-1] = poly[0], poly[-1]
    return out


def _sample_bilinear(img, xy):
    x = np.clip(xy[:, 0], 0, img.shape[1] - 1.001)
    y = np.clip(xy[:, 1], 0, img.shape[0] - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    v = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
         + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
    return v


def _taper_length(radius, arc, level):
    """Arc length from the tip to where the profile first reaches `level`."""
    hit = np.nonzero(radius >= level)[0]
    if len(hit) == 0:
        return arc[-1]
    return float(arc[hit[0]])


def _head_first(spine, profile, limb_anchor_arc, view):
    """Return (spine, profile, flipped, why) with the nose at index 0.

    A tail ends in a wedge that keeps thinning for a long way; a head ends in a
    snout, which is a blunt cap sitting on a neck. So the mean radius over the
    outermost few percent of the spine is markedly larger at the head. When the
    two ends come out close, fall back on how much arc length each needs to grow
    to a fixed fraction of the body's thickness -- a wedge needs much more.
    Top view: the wings hang off the shoulders, which sit well behind the skull
    and only just in front of the hips, so the head is the end further from them.
    """
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(spine, axis=0), axis=1))])
    total = arc[-1]
    if view == "top" and limb_anchor_arc is not None:
        flip = (total - limb_anchor_arc) > limb_anchor_arc
        why = "top view: limbs anchored at %.0f%% of spine, head is the far end" % (
            100 * limb_anchor_arc / total)
    else:
        head_blunt = float(profile[arc <= BLUNT_FRACTION * total].mean())
        tail_blunt = float(profile[arc >= (1 - BLUNT_FRACTION) * total].mean())
        ratio = max(head_blunt, tail_blunt) / max(min(head_blunt, tail_blunt), 1e-6)
        flip = tail_blunt > head_blunt
        why = "blunt ends %.2f / %.2f mm-px (ratio %.2f)" % (head_blunt, tail_blunt, ratio)
        if ratio < BLUNT_MARGIN:
            level = TAPER_LEVEL * float(profile.max())
            head_taper = _taper_length(profile, arc, level)
            tail_taper = _taper_length(profile[::-1], arc, level)
            flip = tail_taper < head_taper
            why += ", inconclusive -> taper %.0f%% / %.0f%%" % (
                100 * head_taper / total, 100 * tail_taper / total)
    if flip:
        return spine[::-1].copy(), profile[::-1].copy(), True, why
    return spine, profile, False, why


# ---------------------------------------------------------------- limbs

def _branch_components(nbr, main):
    on_main = np.zeros(len(nbr), bool)
    on_main[main] = True
    comp = np.full(len(nbr), -1, np.int32)
    groups = []
    for start in range(len(nbr)):
        if on_main[start] or comp[start] >= 0:
            continue
        stack, members = [start], []
        comp[start] = len(groups)
        while stack:
            u = stack.pop()
            members.append(u)
            for v, _ in nbr[u]:
                if not on_main[v] and comp[v] < 0:
                    comp[v] = len(groups)
                    stack.append(v)
        groups.append(members)
    return groups


def _branch_root(nbr, members, main_index):
    for u in members:
        for v, _ in nbr[u]:
            if v in main_index:
                return u, main_index[v]
    return members[0], None


def _sub_dijkstra(nbr, members, src):
    keep = set(members)
    d = {src: 0.0}
    prev = {src: -1}
    q = [(0.0, src)]
    while q:
        du, u = heapq.heappop(q)
        if du > d.get(u, np.inf) + 1e-9:
            continue
        for v, w in nbr[u]:
            if v not in keep:
                continue
            nd = du + w
            if nd < d.get(v, np.inf) - 1e-9:
                d[v] = nd
                prev[v] = u
                heapq.heappush(q, (nd, v))
    return d, prev


def _split_branch(nbr, members, root, min_own):
    """One skeleton branch can carry a whole pair of legs, so cut it at the fork.

    Walking inwards from the longest tip first and stopping at already-claimed
    skeleton makes each further tip contribute only what it owns alone. A toe
    owns a few pixels and joins its foot; the far leg of a pair owns almost its
    whole length and becomes a limb of its own.
    """
    d, prev = _sub_dijkstra(nbr, members, root)
    tips = sorted((u for u in members if len(nbr[u]) == 1 and u != root and u in d),
                  key=lambda u: -d[u])
    if not tips:
        tips = [max(d, key=d.get)]
    owner, limbs = {}, []
    for t in tips:
        own, u = [], t
        while u != -1 and u not in owner:
            own.append(u)
            u = prev.get(u, -1)
        if not own:
            continue
        own_len = d[t] - (d[u] if u != -1 else 0.0)
        if limbs and own_len < max(min_own, 0.4 * d[t]):
            k = owner[u]
            limbs[k]["nodes"].extend(own)
        else:
            k = len(limbs)
            limbs.append({"tip": t, "root": own[-1], "nodes": own, "reach": own_len})
        for n in own:
            owner[n] = k
    stack = [n for n in owner]
    while stack:
        u = stack.pop()
        for v, _ in nbr[u]:
            if v in d and v not in owner:
                owner[v] = owner[u]
                limbs[owner[u]]["nodes"].append(v)
                stack.append(v)
    for limb in limbs:
        limb["chain"] = _trace_dict(prev, limb["tip"], limb["root"])
    return limbs


def _trace_dict(prev, end, stop):
    p = [end]
    while p[-1] != stop and prev.get(p[-1], -1) != -1:
        p.append(prev[p[-1]])
    return p[::-1]


def _voronoi_labels(mask, groups_pixels):
    """Label every mask pixel by the nearest skeleton group."""
    dists = []
    for px in groups_pixels:
        src = np.full(mask.shape, 255, np.uint8)
        src[px[:, 1].astype(int), px[:, 0].astype(int)] = 0
        dists.append(cv2.distanceTransform(src, cv2.DIST_L2, 3))
    stack = np.stack(dists, 0)
    lab = np.argmin(stack, 0).astype(np.int32)
    lab[mask == 0] = -1
    return lab


def _pull_inside(spine, poly):
    """Nudge the two spine tips back inside the outline.

    The skeleton is thinned from a slightly blurred mask, so its tips can end a
    fraction of a millimetre outside the contour traced from the sharp one.
    """
    p = np.asarray(poly, np.float32)
    for i, j in ((0, 1), (-1, -2)):
        if cv2.pointPolygonTest(p, (float(spine[i][0]), float(spine[i][1])), False) >= 0:
            continue
        for t in np.linspace(0.05, 1.0, 20):
            q = spine[i] * (1 - t) + spine[j] * t
            if cv2.pointPolygonTest(p, (float(q[0]), float(q[1])), False) >= 0:
                spine[i] = q
                break
    return spine


def _seam_anchor(lab, value, spine_px, fallback):
    """Where the limb region is welded to the rest of the body, as spine position.

    The skeleton of a whole pair of legs can hang off a single spine pixel, so
    the attachment node says nothing about which leg is the front one. The seam
    the region shares with its neighbours does: it is the shoulder or hip.
    """
    reg = (lab == value).astype(np.uint8)
    ring = cv2.dilate(reg, np.ones((3, 3), np.uint8)) - reg
    ys, xs = np.nonzero(ring & (lab >= 0))
    if len(xs) < 4:
        return fallback
    seam = np.array([xs.mean(), ys.mean()])
    return float(np.argmin(np.linalg.norm(spine_px - seam, axis=1))) / (len(spine_px) - 1)


def _joints(path_pts):
    if len(path_pts) < 3:
        return path_pts
    a, b = path_pts[0], path_pts[-1]
    chord = b - a
    span = np.linalg.norm(chord)
    if span < 1e-6:
        return np.stack([a, b])
    n = np.array([-chord[1], chord[0]]) / span
    off = np.abs((path_pts - a) @ n)
    k = int(np.argmax(off))
    if off[k] < 0.05 * span or k < 2 or k > len(path_pts) - 3:
        return np.stack([a, b])
    return np.stack([a, path_pts[k], b])


def _region_polygon(lab, value, scale, offset):
    reg = (lab == value).astype(np.uint8) * 255
    n, cc, stats, _ = cv2.connectedComponentsWithStats(reg, 8)
    if n > 2:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        reg = (cc == keep).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, 0.0
    c = max(cnts, key=cv2.contourArea)
    poly = _to_mm(_smooth_closed(c.reshape(-1, 2).astype(float), CONTOUR_SMOOTH_PX),
                  scale, offset)
    poly = cv2.approxPolyDP(poly.astype(np.float32), CONTOUR_EPS_MM, True).reshape(-1, 2)
    return poly.astype(float), float(reg.sum() / 255) * scale * scale


# ---------------------------------------------------------------- contours

def _smooth_closed(poly, sigma):
    if sigma <= 0 or len(poly) < 12:
        return poly
    return np.stack([gaussian_filter1d(poly[:, 0], sigma, mode="wrap"),
                     gaussian_filter1d(poly[:, 1], sigma, mode="wrap")], 1)


def _to_mm(pts, scale, offset):
    return np.asarray(pts, float) * scale + np.asarray(offset, float)


def _outline(mask, scale, offset):
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    hier = hier[0]
    outer = max((i for i in range(len(cnts)) if hier[i][3] < 0),
                key=lambda i: cv2.contourArea(cnts[i]))
    order = [outer] + [i for i in range(len(cnts)) if hier[i][3] == outer
                       and cv2.contourArea(cnts[i]) * scale * scale >= HOLE_MIN_MM2]
    out = []
    for i in order:
        p = _to_mm(_smooth_closed(cnts[i].reshape(-1, 2).astype(float), CONTOUR_SMOOTH_PX),
                   scale, offset)
        p = cv2.approxPolyDP(p.astype(np.float32), CONTOUR_EPS_MM, True).reshape(-1, 2)
        out.append(p.astype(float))
    return out


# ---------------------------------------------------------------- naming

def _pair_up(cands):
    """Group limbs into near/far pairs of the same girdle, ordered head to tail.

    The two legs of a pair sit close together along the spine and are within a
    factor of two in area; a T. rex arm is neither, so it stays a unit of one.
    Only neighbours in spine order may pair, which for an even count leaves a
    single arrangement and for an odd one only as many as there are limbs.
    """
    order = sorted(range(len(cands)), key=lambda i: cands[i]["anchor"])

    def cost(i, j):
        a, b = cands[i], cands[j]
        ratio = max(a["area"], b["area"]) / max(min(a["area"], b["area"]), 1e-9)
        return abs(a["anchor"] - b["anchor"]) + 0.1 * np.log(ratio)

    best = None
    for solo in ([None] if len(order) % 2 == 0 else range(len(order))):
        rest = [k for k in order if k != (order[solo] if solo is not None else None)]
        if len(rest) % 2:
            continue
        units, total = [], 0.0
        if solo is not None:
            units.append([order[solo]])
        for k in range(0, len(rest), 2):
            units.append([rest[k], rest[k + 1]])
            total += cost(rest[k], rest[k + 1])
        if best is None or total < best[0]:
            best = (total, units)
    units = best[1]
    units.sort(key=lambda u: min(cands[i]["anchor"] for i in u))
    return units


def _name_and_side(cands, view, motion):
    if view == "top":
        base = "wing" if motion == "fly" else "fin"
        for c in cands:
            c["name"] = base + ("_l" if c["cross"] > 0 else "_r")
            c["side"] = 0
        return
    base = {"swim": "fin", "fly": "wing"}.get(motion, "leg")
    units = _pair_up(cands)
    if len(units) == 1:
        labels = [base]
    else:
        front = np.mean([cands[i]["area"] for i in units[0]])
        hind = np.mean([cands[i]["area"] for i in units[-1]])
        # a biped's arms are a fraction of the size of its legs; a quadruped's
        # front and hind legs are within a factor of two of each other
        arms = motion == "walk" and len(units[0]) < len(units[-1]) and front < 0.7 * hind
        labels = [(base + "_%d" % k) for k in range(len(units))]
        labels[0] = "arm" if arms else base + "_front"
        labels[-1] = base + "_hind"
    for label, unit in zip(labels, units):
        for c in (cands[i] for i in unit):
            c["name"] = label
        if len(unit) == 2:
            a, b = cands[unit[0]], cands[unit[1]]
            if max(a["area"], b["area"]) > 1.15 * min(a["area"], b["area"]):
                near = a if a["area"] > b["area"] else b
            else:
                near = a if a["joints"][-1][1] > b["joints"][-1][1] else b
            a["side"], b["side"] = (0, 1) if near is a else (1, 0)
        else:
            cands[unit[0]]["side"] = 0


# ---------------------------------------------------------------- main entry

def derive(png_path, view="side", motion="walk"):
    mask, dropped = load_mask(png_path)
    scale, offset = _place(mask)
    skel, dist, smooth = _skeleton(mask)
    pts, nbr = _graph(skel)
    main = _main_path(pts, nbr, dist, smooth, view)

    raw = pts[main]
    spine_px = _smooth_open(_resample(raw, SPINE_SAMPLES), SPINE_SMOOTH)
    spine_px = _resample(spine_px, SPINE_SAMPLES)
    prof_px = gaussian_filter1d(_sample_bilinear(dist, spine_px), PROFILE_SMOOTH,
                                mode="nearest")

    main_index = {n: i for i, n in enumerate(main)}
    main_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))])
    spine_len_px = main_arc[-1]
    groups = _branch_components(nbr, main)
    total_area = float((mask > 0).sum())

    trunk = KDTree(raw)
    body_nodes = list(main)
    metas = []
    for members in groups:
        root, anchor_node = _branch_root(nbr, members, main_index)
        if anchor_node is None:
            continue
        for limb in _split_branch(nbr, members, root, LIMB_MIN_REACH * spine_len_px):
            # the stretch of a branch that still runs inside the torso is body,
            # not limb: without cutting it, whichever leg of a pair happens to
            # own the shared stub also swallows the whole belly around it
            xy = pts[limb["nodes"]]
            gap, near = trunk.query(xy)
            outside = gap > TRUNK_INSIDE * dist[raw[near][:, 1].astype(int),
                                                raw[near][:, 0].astype(int)]
            body_nodes.extend(np.asarray(limb["nodes"])[~outside].tolist())
            if outside.sum() < 5:
                continue
            metas.append({"anchor_node": anchor_node,
                          "reach": limb["reach"] / max(spine_len_px, 1.0),
                          "chain": pts[limb["chain"]], "nodes": xy[outside]})

    labels = [pts[body_nodes]] + [m["nodes"] for m in metas]
    vor = _voronoi_labels(mask, labels)

    cands = []
    for k, meta in enumerate(metas, start=1):
        poly, area_mm2 = _region_polygon(vor, k, scale, offset)
        if poly is None or len(poly) < 3:
            continue
        attach = main_arc[meta["anchor_node"]] / spine_len_px
        # in top view a wing pair really does share one shoulder point, so the
        # attachment node is right; in side view it is not, see _seam_anchor
        anchor = attach if view == "top" else _seam_anchor(vor, k, spine_px, attach)
        i0 = min(int(round(anchor * (SPINE_SAMPLES - 1))), SPINE_SAMPLES - 1)
        anchor_mm = _to_mm(spine_px[i0][None], scale, offset)[0]
        chain_mm = np.vstack([anchor_mm, _to_mm(meta["chain"], scale, offset)])
        joints = _joints(_smooth_open(_resample(chain_mm, 40), 3.0))
        d = joints[-1] - joints[0]
        length = np.linalg.norm(d)
        tangent = spine_px[min(SPINE_SAMPLES - 1, i0 + 3)] - spine_px[max(0, i0 - 3)]
        tangent = tangent / max(np.linalg.norm(tangent), 1e-9)
        cands.append({
            "anchor": anchor, "area": float((vor == k).sum()) / total_area,
            "area_mm2": area_mm2, "reach": meta["reach"], "joints": joints,
            "polygon": poly, "down": float(d[1] / max(length, 1e-9)),
            "cross": float(np.cross(tangent, d)), "rejected": None,
        })

    # orientation is decided from the profile, so anchors must be flipped with it
    wing_arc = None
    if view == "top" and cands:
        wing = max(cands, key=lambda c: c["area"])
        wing_arc = wing["anchor"] * spine_len_px
    spine_px2, prof_px2, flipped, why = _head_first(spine_px, prof_px, wing_arc, view)
    if flipped:
        for c in cands:
            c["anchor"] = 1.0 - c["anchor"]
            c["cross"] = -c["cross"]

    for c in cands:
        if c["area"] < LIMB_MIN_AREA:
            c["rejected"] = "area %.1f%%" % (100 * c["area"])
        elif c["reach"] < LIMB_MIN_REACH:
            c["rejected"] = "reach %.1f%%" % (100 * c["reach"])
        elif c["anchor"] < LIMB_HEAD_ZONE:
            c["rejected"] = "head zone %.2f" % c["anchor"]
        elif view != "top" and c["down"] < LIMB_DOWN_COS:
            c["rejected"] = "points up/along %.2f" % c["down"]

    kept = [c for c in cands if c["rejected"] is None]
    if kept:
        biggest = max(c["area"] for c in kept)
        for c in kept:
            if c["area"] < LIMB_MIN_RELATIVE * biggest:
                c["rejected"] = "only %.0f%% of the largest limb" % (100 * c["area"] / biggest)
        kept = [c for c in kept if c["rejected"] is None]
    _name_and_side(kept, view, motion)
    kept.sort(key=lambda c: (c["anchor"], c["side"]))

    outline = _outline(mask, scale, offset)
    spine = _pull_inside(_to_mm(spine_px2, scale, offset), outline[0])
    profile = prof_px2 * scale
    limbs = [DerivedLimb(name=c["name"], anchor=float(c["anchor"]), side=int(c["side"]),
                         joints=np.asarray(c["joints"], float),
                         polygon=np.asarray(c["polygon"], float),
                         area_mm2=float(c["area_mm2"]))
             for c in kept]
    notes = {
        "flipped": flipped,
        "head_rule": why,
        "dropped_blobs": dropped,
        "spine_len_mm": float(np.linalg.norm(np.diff(spine, axis=0), axis=1).sum()),
        "candidates": [{k: c[k] for k in ("anchor", "area", "reach", "down", "rejected")}
                       for c in sorted(cands, key=lambda c: c["anchor"])],
    }
    return DerivedShape(outline=outline, spine=spine, profile=profile,
                        limbs=limbs, view=view, motion=motion, scale=scale,
                        offset=tuple(offset), notes=notes)
