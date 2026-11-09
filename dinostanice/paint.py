"""Výchozí zbarvení tvorů: ukázková textura, než dítě vybarví vlastní list.

Každý druh má ve `scene.json` blok `paint` — základní barva, břicho, nohy,
čumák, špička ocasu a pár vzorů (tečky, pruhy, pásy, skvrny). Souřadnice jsou
relativní k obrysu na listu: `u` 0 u ocasu až 1 u hlavy (strana se pozná podle
oka), `v` 0 na hřbetě až 1 u země. Díky tomu stejný popis sedí na zvíře
zleva i zprava a nezávisí na velikosti listu.

Barvy jsou RGB. Výsledek je barevná plocha uvnitř obrysu; obrys a oko dokreslí
volající (tools/model_paint_demo.py).
"""
from __future__ import annotations

import zlib

import cv2
import numpy as np

SIDE_ONLY = ("belly", "legs", "muzzle", "antler")


def _rgb(c):
    return np.array(c, np.float32)


def _smooth(x, lo, hi):
    t = np.clip((x - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _blend(img, colour, weight):
    img += (colour[None, None, :] - img) * weight[..., None]


def _box(u, v, region, feather=0.04):
    """Měkký obdélník v souřadnicích u/v; region = [u0, u1, v0, v1]."""
    u0, u1, v0, v1 = region
    wu = _smooth(u, u0 - feather, u0 + feather) * (1 - _smooth(u, u1 - feather, u1 + feather))
    wv = _smooth(v, v0 - feather, v0 + feather) * (1 - _smooth(v, v1 - feather, v1 + feather))
    return wu * wv


def _noise(shape, sigma, rng):
    n = rng.standard_normal(shape).astype(np.float32)
    n = cv2.GaussianBlur(n, (0, 0), sigma)
    return n / (n.std() + 1e-6)


def _geometry(shape, ppm: float, size: tuple):
    """Maska těla a souřadnice listu: u, v relativní k obrysu (u 0 u ocasu, 1 u hlavy)."""
    H, W = size
    body = np.zeros((H, W), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * ppm).astype(np.int32)], 1)
    ys, xs = np.nonzero(body)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    head_right = True
    eye_y = None
    if shape.eye:
        head_right = shape.eye[0] * ppm >= (x0 + x1) / 2
        eye_y = shape.eye[1] * ppm
    u = (gx - x0) / max(x1 - x0, 1)
    if not head_right:
        u = 1.0 - u
    v = (gy - y0) / max(y1 - y0, 1)
    return body, (x0, x1, y0, y1), gx, gy, head_right, eye_y, u, v


def _mask(m: dict, u, v):
    """Váha značky: `region` [u0, u1, v0, v1] s měkkým okrajem `feather`, `invert` ji obrátí."""
    if "region" not in m:
        return 1.0
    w = _box(u, v, m["region"], m.get("feather", 0.04))
    return 1.0 - w if m.get("invert") else w


def _cells(H: int, W: int, cell_px: float, rng):
    """Rozložení na buňky (jitterovaný Voronoi): vzdálenost k nejbližšímu a druhému
    nejbližšímu středu a náhodné číslo buňky. d2 - d1 je malé na hranách buněk."""
    gh, gw = int(H / cell_px) + 4, int(W / cell_px) + 4
    pts = rng.uniform(0.15, 0.85, (gh, gw, 2)).astype(np.float32)
    tone = rng.random((gh, gw)).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cy = (yy / cell_px).astype(np.int32)
    cx = (xx / cell_px).astype(np.int32)
    d1 = np.full((H, W), 1e9, np.float32)
    d2 = np.full((H, W), 1e9, np.float32)
    best = np.zeros((H, W), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = cy + dy + 1, cx + dx + 1
            px = (cx + dx + pts[ny, nx, 0]) * cell_px
            py = (cy + dy + pts[ny, nx, 1]) * cell_px
            d = np.hypot(xx - px, yy - py)
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            best = np.where(closer, tone[ny, nx], best)
            d1 = np.where(closer, d, d1)
    return d1, d2, best


def _streaks(shape, along_v: bool, length: float, rng):
    """Šum protažený podél osy (srst): ostré napříč, hladké podél."""
    n = rng.standard_normal(shape).astype(np.float32)
    sx, sy = (0.7, length) if along_v else (length, 0.7)
    n = cv2.GaussianBlur(n, (0, 0), sigmaX=sx, sigmaY=sy)
    return n / (n.std() + 1e-6)


def _spiral(m: dict, gx, gy, x0, x1, y0, y1, ppm):
    """Archimédova spirála (ulita): váha 1 na proužku, 0 jinde, a poloměr 0–1 k okraji."""
    cu, cv_ = m["centre"]
    cx, cy = x0 + cu * (x1 - x0), y0 + cv_ * (y1 - y0)
    rmax = m["radius_mm"] * ppm
    dx, dy = gx - cx, (gy - cy) / m.get("squash", 1.0)
    r = np.hypot(dx, dy)
    turn = np.arctan2(dy, dx) / (2 * np.pi)
    phase = (r / (m["period_mm"] * ppm) - turn) % 1.0
    width = m.get("width", 0.35)
    line = _smooth(phase, 0.0, 0.08) * (1 - _smooth(phase, width, width + 0.08))
    return line, np.clip(r / rmax, 0.0, 1.0), r <= rmax


def paint_body(shape, paint: dict, ppm: float, size: tuple, side_view: bool = True,
               key: str = "") -> np.ndarray:
    """Barevný list (BGR uint8) pro tvora; mimo tělo bílý."""
    H, W = size
    rng = np.random.default_rng(zlib.crc32(key.encode()) if key else 7)
    body, (x0, x1, y0, y1), gx, gy, head_right, eye_y, u, v = _geometry(shape, ppm, size)

    p = paint or {}
    img = np.empty((H, W, 3), np.float32)
    img[:] = _rgb(p.get("base", (200, 200, 200)))

    if p.get("back"):
        _blend(img, _rgb(p["back"]), 1 - _smooth(v, p.get("back_to", 0.35) - 0.1,
                                                 p.get("back_to", 0.35) + 0.1))
    if side_view:
        if p.get("belly"):
            at = p.get("belly_at", 0.5)
            _blend(img, _rgb(p["belly"]), _smooth(v, at, at + 0.18))
        if p.get("legs"):
            at = p.get("legs_at", 0.72)
            _blend(img, _rgb(p["legs"]), _smooth(v, at, at + 0.12))
        if p.get("muzzle") and eye_y is not None:
            ln = p.get("muzzle_len", 0.1)
            below = _smooth(gy, eye_y + 1.0 * ppm, eye_y + 4.0 * ppm)
            _blend(img, _rgb(p["muzzle"]), _smooth(u, 1 - ln - 0.02, 1 - ln + 0.02) * below)
        if p.get("antler") and eye_y is not None:
            start = p.get("antler_from", 0.62)
            above = 1 - _smooth(gy, eye_y - 9.0 * ppm, eye_y - 6.0 * ppm)
            _blend(img, _rgb(p["antler"]), _smooth(u, start - 0.02, start + 0.02) * above)
    if p.get("tail_tip"):
        ln = p.get("tail_len", 0.1)
        _blend(img, _rgb(p["tail_tip"]), 1 - _smooth(u, ln - 0.015, ln + 0.015))

    for m in p.get("marks", []):
        kind = m["type"]
        col = _rgb(m.get("color", (0, 0, 0)))
        region = m.get("region", [0, 1, 0, 1])
        if kind == "spots":
            layer = np.zeros((H, W), np.float32)
            r0, r1 = m.get("r", [2.0, 4.0])
            for _ in range(m.get("n", 30)):
                cu = rng.uniform(region[0], region[1])
                cv_ = rng.uniform(region[2], region[3])
                cx = (x0 + cu * (x1 - x0)) if head_right else (x1 - cu * (x1 - x0))
                cy = y0 + cv_ * (y1 - y0)
                r = rng.uniform(r0, r1) * ppm
                cv2.ellipse(layer, (int(cx), int(cy)), (int(r), int(r * m.get("squash", 1.0))),
                            m.get("angle", 0), 0, 360, 1.0, -1, cv2.LINE_AA)
            _blend(img, col, layer * m.get("alpha", 1.0))
        elif kind == "stripes":
            period = m.get("period_mm", 12) * ppm
            width = m.get("width_mm", 4) * ppm / period
            tilt = m.get("tilt", 0.0)
            phase = ((gx + tilt * gy) / period) % 1.0
            band = (phase < width).astype(np.float32)
            band = cv2.GaussianBlur(band, (0, 0), 1.5)
            _blend(img, col, band * _box(u, v, region) * m.get("alpha", 1.0))
        elif kind == "bands":
            layer = np.zeros((H, W), np.float32)
            for cu, wd in m["at"]:
                layer = np.maximum(layer, _smooth(u, cu - wd / 2 - 0.01, cu - wd / 2 + 0.01) *
                                   (1 - _smooth(u, cu + wd / 2 - 0.01, cu + wd / 2 + 0.01)))
            if m.get("edge"):
                edge = cv2.dilate(layer, np.ones((int(0.9 * ppm) | 1,) * 2, np.uint8))
                _blend(img, _rgb(m["edge"]), np.clip(edge - layer, 0, 1))
            _blend(img, col, layer)
        elif kind == "patches":
            n = _noise((H, W), m.get("size_mm", 10) * ppm / 2, rng)
            layer = _smooth(n, m.get("threshold", 0.5), m.get("threshold", 0.5) + 0.25)
            _blend(img, col, layer * _box(u, v, region) * m.get("alpha", 1.0))
        elif kind == "box":
            _blend(img, col, _mask(m, u, v) * m.get("alpha", 1.0))
        elif kind == "dots":
            layer = np.zeros((H, W), np.float32)
            for cu, cv_, r_mm in m["at"]:
                cx = (x0 + cu * (x1 - x0)) if head_right else (x1 - cu * (x1 - x0))
                cy = y0 + cv_ * (y1 - y0)
                cv2.ellipse(layer, (int(cx), int(cy)),
                            (int(r_mm * ppm), int(r_mm * ppm * m.get("squash", 1.0))),
                            m.get("angle", 0), 0, 360, 1.0, -1, cv2.LINE_AA)
            layer = cv2.GaussianBlur(layer, (0, 0), m.get("soft_mm", 0.25) * ppm)
            _blend(img, col, layer * m.get("alpha", 1.0))
        elif kind == "fur":
            n = _streaks((H, W), m.get("axis", "v") == "v", m.get("length_mm", 1.2) * ppm, rng)
            w = _mask(m, u, v)
            img *= 1.0 + (n * m.get("amp", 0.12) * w)[..., None]
            if m.get("tip"):
                _blend(img, col, _smooth(n, 1.0, 2.2) * w * m["tip"])
        elif kind == "cells":
            d1, d2, tone = _cells(H, W, m.get("cell_mm", 3.0) * ppm, rng)
            w = _mask(m, u, v)
            img *= 1.0 + ((tone - 0.5) * 2 * m.get("tone", 0.08) * w)[..., None]
            edge = 1.0 - _smooth(d2 - d1, 0.0, m.get("edge_mm", 0.35) * ppm)
            _blend(img, col, edge * w * m.get("alpha", 0.3))
        elif kind == "spiral":
            m2 = dict(m)
            if not head_right:
                m2["centre"] = [1 - m["centre"][0], m["centre"][1]]
            line, _, inside = _spiral(m2, gx, gy, x0, x1, y0, y1, ppm)
            _blend(img, col, line * inside * _mask(m, u, v) * m.get("alpha", 0.8))

    if p.get("rim"):
        # tělo se k okraji siluety zatáčí od diváka, a tam je tmavší
        dist = cv2.distanceTransform(body, cv2.DIST_L2, 3)
        k = 1.0 - _smooth(dist, 0.0, p["rim"].get("mm", 2.5) * ppm)
        img *= (1.0 - p["rim"].get("amount", 0.2) * k)[..., None]

    grain = _noise((H, W), 2.0, rng) * 1.0 + _noise((H, W), 9 * ppm / 2, rng) * 3.0
    img *= (1.0 + grain[..., None] / 100.0 * p.get("grain", 2.0))
    img = np.clip(img, 0, 255).astype(np.uint8)
    out = np.full((H, W, 3), 255, np.uint8)
    out[body > 0] = img[..., ::-1][body > 0]
    return out


def paint_relief(shape, paint: dict, ppm: float, size: tuple, key: str = "") -> np.ndarray:
    """Výšková mapa (BGR uint8, šedá) ve stejných souřadnicích jako barevný list.

    128 je rovina, světlejší vystupuje, tmavší je důlek. Bere `paint["relief"]`:
    `cells` (šupiny a destičky), `fur` (srst), `stripes` (články), `spiral` (ulita),
    `noise` (hrbolky). Díky tomu, že UV jsou vázané na list, sedí mapa na každém
    zvířeti daného druhu — i na tom, které vybarvilo dítě."""
    H, W = size
    rng = np.random.default_rng(zlib.crc32((key + "-relief").encode()))
    body, (x0, x1, y0, y1), gx, gy, head_right, _, u, v = _geometry(shape, ppm, size)
    h = np.zeros((H, W), np.float32)
    for m in (paint or {}).get("relief", []):
        kind, depth, w = m["type"], m.get("depth", 0.3), None
        w = _mask(m, u, v)
        if kind == "cells":
            cell = m.get("cell_mm", 3.0) * ppm
            d1, d2, tone = _cells(H, W, cell, rng)
            dome = 1.0 - _smooth(d1, 0.0, cell * 0.6)
            groove = 1.0 - _smooth(d2 - d1, 0.0, m.get("edge_mm", 0.4) * ppm)
            h += w * depth * (0.45 * (dome - 0.5) - 0.9 * groove + (tone - 0.5) * m.get("tone", 0.0))
        elif kind == "fur":
            n = _streaks((H, W), m.get("axis", "v") == "v", m.get("length_mm", 1.2) * ppm, rng)
            h += w * depth * 0.5 * n
        elif kind == "stripes":
            period = m.get("period_mm", 10) * ppm
            width = m.get("width", 0.2)
            phase = ((gx + m.get("tilt", 0.0) * gy) / period) % 1.0
            band = _smooth(phase, 0.0, width * 0.5) * (1 - _smooth(phase, width * 0.5, width))
            h -= w * depth * band
        elif kind == "spiral":
            m2 = dict(m)
            if not head_right:
                m2["centre"] = [1 - m["centre"][0], m["centre"][1]]
            line, _, inside = _spiral(m2, gx, gy, x0, x1, y0, y1, ppm)
            h -= w * depth * line * inside
        elif kind == "noise":
            h += w * depth * 0.5 * _noise((H, W), m.get("size_mm", 2.0) * ppm / 2, rng)
    h = np.clip(0.5 + h * 0.5, 0.0, 1.0)
    h[body == 0] = 0.5
    return np.repeat(np.round(h * 255).astype(np.uint8)[..., None], 3, axis=2)
