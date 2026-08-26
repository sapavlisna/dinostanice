"""Ortogonalni pohled na model: z-buffer, materialy, obrysove linky.

Slouzi k tomu, aby z 3D modelu vypadla predloha k vybarveni. Rasterizace je
vlastni (numpy), protoze offscreen OpenGL na Windows je vic starosti nez
z-buffer nad dvema tisici trojuhelniku.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class View:
    """Vysledek rasterizace do ortogonalniho pohledu."""

    depth: np.ndarray      # (H,W) float, vetsi = dal od kamery, inf = pozadi
    tri: np.ndarray        # (H,W) int32, index trojuhelniku, -1 = pozadi
    normal: np.ndarray     # (H,W,3) float, interpolovana normala
    bary: np.ndarray       # (H,W,3) float, barycentricke vahy vrcholu trojuhelniku
    mask: np.ndarray       # (H,W) bool
    scale: float           # pixelu na jednotku modelu
    origin: np.ndarray     # (2,) posun: pixel = (world_uv - origin) * scale

    def sample(self, tris: np.ndarray, attr: np.ndarray) -> np.ndarray:
        """Interpoluje atribut z vrcholu do obrazu; mimo masku nuly."""
        out = np.zeros((*self.tri.shape, attr.shape[1]))
        if self.mask.any():
            idx = tris[self.tri[self.mask]]
            b = self.bary[self.mask]
            out[self.mask] = (attr[idx[:, 0]] * b[:, 0:1] + attr[idx[:, 1]] * b[:, 1:2]
                              + attr[idx[:, 2]] * b[:, 2:3])
        return out

    def material(self, tri_material: np.ndarray) -> np.ndarray:
        """(H,W) int32 index materialu, -1 na pozadi."""
        out = np.full(self.tri.shape, -1, np.int32)
        out[self.mask] = tri_material[self.tri[self.mask]]
        return out


def render(
    verts: np.ndarray,
    tris: np.ndarray,
    normals: np.ndarray | None = None,
    *,
    axes: tuple[int, int, int] = (2, 1, 0),
    flip: tuple[int, int, int] = (1, -1, 1),
    width: int = 1200,
    margin: float = 0.03,
    bounds: tuple[np.ndarray, np.ndarray] | None = None,
) -> View:
    """Vyrenderuje ortogonalni pohled.

    `axes` vybira, ktera osa modelu je vodorovna / svisla / hloubkova,
    `flip` jim da znamenka. Vychozi (2,1,0)/(1,-1,1) je bokorys: vodorovne Z,
    svisle Y nahoru, hloubka X. `bounds` prebije automaticke vystredeni,
    aby slo vic snimku vyrenderovat do stejneho ramce.
    """
    ax_u, ax_v, ax_d = axes
    u = verts[:, ax_u] * flip[0]
    v = verts[:, ax_v] * flip[1]
    d = verts[:, ax_d] * flip[2]

    if bounds is None:
        lo = np.array([u.min(), v.min()])
        hi = np.array([u.max(), v.max()])
        pad = margin * max(hi - lo)
        lo, hi = lo - pad, hi + pad
    else:
        lo, hi = bounds
    scale = (width - 1) / (hi[0] - lo[0])
    height = int(round((hi[1] - lo[1]) * scale)) + 1

    px = (u - lo[0]) * scale
    py = (v - lo[1]) * scale

    depth = np.full((height, width), np.inf)
    tri_id = np.full((height, width), -1, np.int32)
    bary = np.zeros((height, width, 3))

    for i, (ia, ib, ic) in enumerate(tris):
        x0, y0 = px[[ia, ib, ic]], py[[ia, ib, ic]]
        xmin = max(int(np.floor(x0.min())), 0)
        xmax = min(int(np.ceil(x0.max())), width - 1)
        ymin = max(int(np.floor(y0.min())), 0)
        ymax = min(int(np.ceil(y0.max())), height - 1)
        if xmin > xmax or ymin > ymax:
            continue
        area = (x0[1] - x0[0]) * (y0[2] - y0[0]) - (x0[2] - x0[0]) * (y0[1] - y0[0])
        if abs(area) < 1e-12:
            continue
        xs = np.arange(xmin, xmax + 1)[None, :]
        ys = np.arange(ymin, ymax + 1)[:, None]
        w0 = ((x0[1] - xs) * (y0[2] - ys) - (x0[2] - xs) * (y0[1] - ys)) / area
        w1 = ((x0[2] - xs) * (y0[0] - ys) - (x0[0] - xs) * (y0[2] - ys)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * d[ia] + w1 * d[ib] + w2 * d[ic]
        sub = depth[ymin:ymax + 1, xmin:xmax + 1]
        win = inside & (z < sub)
        if not win.any():
            continue
        sub[win] = z[win]
        tri_id[ymin:ymax + 1, xmin:xmax + 1][win] = i
        blk = bary[ymin:ymax + 1, xmin:xmax + 1]
        blk[win] = np.stack([w0 + 0 * w2, w1 + 0 * w2, w2], -1)[win]

    mask = tri_id >= 0
    nrm = np.zeros((height, width, 3))
    if normals is not None and mask.any():
        idx = tris[tri_id[mask]]
        n = (normals[idx[:, 0]] * bary[mask][:, 0:1]
             + normals[idx[:, 1]] * bary[mask][:, 1:2]
             + normals[idx[:, 2]] * bary[mask][:, 2:3])
        nrm[mask] = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)

    return View(depth, tri_id, nrm, bary, mask, scale, lo)


def outline_edges(view: View, tri_material: np.ndarray, *, depth_jump: float = 0.06,
                  crease_cos: float = 0.5) -> dict[str, np.ndarray]:
    """Rozlozi kresbu na vrstvy linek: obrys, hloubkove skoky, hranice materialu.

    Hloubkovy skok se meri v jednotkach modelu vuci `depth_jump` nasobku
    hloubkoveho rozsahu — proto neni treba ladit prahy na kazdy model zvlast.
    """
    m = view.mask
    d = np.where(m, view.depth, np.nan)
    span = float(np.nanmax(d) - np.nanmin(d)) if m.any() else 1.0
    thr = depth_jump * max(span, 1e-9)

    def shifts(a):
        return [np.roll(a, s, ax) for ax, s in ((0, 1), (0, -1), (1, 1), (1, -1))]

    # obrys: uvnitr masky, ale soused uz je pozadi
    bg = ~m
    silhouette = m & np.any(np.stack(shifts(bg)), 0)

    # skok v hloubce: soused je vyrazne dal (kresli se blizsi strana)
    dj = np.zeros_like(m)
    for s in shifts(np.where(m, view.depth, np.inf)):
        dj |= m & np.isfinite(s) & ((s - np.where(m, view.depth, 0)) > thr)

    mat = view.material(tri_material)
    mb = np.zeros_like(m)
    for s in shifts(mat):
        mb |= m & (s >= 0) & (s != mat)

    n = view.normal
    cr = np.zeros_like(m)
    for s in shifts(n):
        cr |= m & (np.sum(n * s, -1) < crease_cos)
    cr &= ~silhouette

    return {"silhouette": silhouette, "depth": dj & ~silhouette,
            "material": mb & ~silhouette, "crease": cr}
