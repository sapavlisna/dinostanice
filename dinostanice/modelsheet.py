"""Z 3D modelu udela predlohu k vybarveni.

Obraceny postup proti `silhouette.py`: misto aby se z ploche siluety hadala
hloubka, vychazi se z hotoveho 3D modelu. Ortogonalni bokorys da soucasne
obrys, vnitrni linky (hranice materialu a hloubkove skoky) a — hlavne —
prevodni vztah mezi milimetry na listu a souradnicemi modelu. Diky nemu
vybarvena kresba sedne zpatky na model jako textura.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

from .gltf import Model
from . import orthoview as ov
from .shapes import SHEET_W_MM, SHEET_H_MM
from .template import LINE_MM

DRAW_MARGIN_X_MM = 32.0   # znacky v rozich zabiraji 9 + 16 mm
DRAW_MARGIN_Y_MM = 30.0
MIN_REGION_MM2 = 3.0
SIMPLIFY_MM = 0.35
# Tisteny obrys je o chlup vetsi nez projekce modelu: dite pri vybarvovani
# nedojede presne k lince a model by mel bily lem. Vnitrni oblasti i UV
# zustavaji na presne projekci, takze hrana modelu vzorkuje ~1,5 mm uvnitr
# vybarvene plochy.
OUTLINE_GROW_MM = 1.5


@dataclass
class Placement:
    """Prevod mezi souradnicemi modelu a milimetry na listu."""

    axes: tuple           # (vodorovna, svisla, hloubkova) osa modelu
    flip: tuple           # znamenka tech os
    mm_per_unit: float
    origin_u: float       # modelova souradnice leveho okraje kresby
    origin_v: float       # modelova souradnice horniho okraje kresby
    offset_x_mm: float
    offset_y_mm: float

    def to_mm(self, verts: np.ndarray) -> np.ndarray:
        u = verts[:, self.axes[0]] * self.flip[0]
        v = verts[:, self.axes[1]] * self.flip[1]
        return np.stack([
            (u - self.origin_u) * self.mm_per_unit + self.offset_x_mm,
            (v - self.origin_v) * self.mm_per_unit + self.offset_y_mm,
        ], axis=1)

    def uv(self, verts: np.ndarray) -> np.ndarray:
        """Pozice na listu jako UV (0..1), stejna konvence jako model3d.py."""
        mm = self.to_mm(verts)
        return np.stack([mm[:, 0] / SHEET_W_MM, 1.0 - mm[:, 1] / SHEET_H_MM], axis=1)


@dataclass
class SheetShape:
    """Obrys a vnitrni linky jednoho tvora v milimetrech na listu."""

    key: str
    label: str
    outline: list          # [vnejsi polygon, ...] — prvni je silueta
    regions: list          # vnitrni oblasti k vybarveni (uzavrene polygony)
    eye: tuple | None
    placement: Placement
    anim: str
    time: float


def _fit(lo: np.ndarray, hi: np.ndarray) -> tuple[float, float, float]:
    """Meritko a posun tak, aby kresba vyplnila list a zustala vystredena."""
    box_w = SHEET_W_MM - 2 * DRAW_MARGIN_X_MM
    box_h = SHEET_H_MM - 2 * DRAW_MARGIN_Y_MM
    span = hi - lo
    mm_per_unit = min(box_w / span[0], box_h / span[1])
    off_x = DRAW_MARGIN_X_MM + (box_w - span[0] * mm_per_unit) / 2
    off_y = DRAW_MARGIN_Y_MM + (box_h - span[1] * mm_per_unit) / 2
    return mm_per_unit, off_x, off_y


def _chaikin(pts: np.ndarray, iterations: int = 2) -> np.ndarray:
    """Zaobli rohy uzavreneho polygonu orezavanim. Na rozdil od Catmull-Rom
    nikdy neprestreli, takze pila zubu zustane pilou a nerozvlni se."""
    for _ in range(iterations):
        a = pts
        b = np.roll(pts, -1, axis=0)
        pts = np.empty((len(pts) * 2, 2))
        pts[0::2] = 0.75 * a + 0.25 * b
        pts[1::2] = 0.25 * a + 0.75 * b
    return pts


def _trace(mask: np.ndarray, ppm: float, origin_px: np.ndarray, offset_mm: np.ndarray,
           min_area_mm2: float) -> list[np.ndarray]:
    """Kontury binarni masky prevedene do mm, zjednodusene a zaoblene."""
    out = []
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        c = cv2.approxPolyDP(c, SIMPLIFY_MM * ppm, True).reshape(-1, 2).astype(float)
        if len(c) < 3:
            continue
        # plocha az po zjednoduseni: uzka trhlina ma pred approxPolyDP plochu
        # nafouknutou o pilovity okraj a proklouzne filtrem jako artefakt
        if cv2.contourArea(c.astype(np.float32)) / (ppm ** 2) < min_area_mm2:
            continue
        pts = (c - origin_px) / ppm + offset_mm
        # zaoblovat jen mekke tvary; pila zubu ma kratke segmenty a Chaikin by
        # z ni udelal vlnovku
        step = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1).mean()
        out.append(_chaikin(pts) if len(pts) >= 4 and step > 2.0 else pts)
    return out


def fill_ratio(model: Model, anim: str, time: float,
               axes: tuple[int, int, int] = (2, 1, 0),
               flip: tuple[int, int, int] = (1, -1, 1), width: int = 240) -> float:
    """Jakou cast kreslici plochy tvor po vystredeni zabere.

    Merit se musi az po fitu na list, ne v pixelech: natazeny sauropod ma velkou
    siluetu, ale na papire z nej zbyde tenky pruh.
    """
    verts, _ = model.posed(anim, time)
    view = ov.render(verts, model.indices, axes=axes, flip=flip, width=width)
    h, w = view.mask.shape
    return float(view.mask.sum()) / (h * w) * min(1.0, (h / w) * _BOX_RATIO,
                                                  (w / h) / _BOX_RATIO)


_BOX_RATIO = (SHEET_W_MM - 2 * DRAW_MARGIN_X_MM) / (SHEET_H_MM - 2 * DRAW_MARGIN_Y_MM)


def best_pose(model: Model, clips: list[str], samples: int = 20,
              axes: tuple[int, int, int] = (2, 1, 0),
              flip: tuple[int, int, int] = (1, -1, 1)) -> tuple[str, float]:
    """Z nabidnutych animaci vybere okamzik, ktery list vyplni nejlip.

    Rozkrocene nohy a zvednuta hlava jsou pro dite citelnejsi a pro texturu
    vydatnejsi: co je v poze schovane za jinou casti tela, dostane pri obarveni
    barvu souseda.
    """
    best, score = (clips[0], 0.0), -1.0
    for clip in clips:
        if clip not in model.animations:
            continue
        duration = model.animations[clip].duration
        for i in range(samples):
            t = duration * i / samples
            s = fill_ratio(model, clip, t, axes=axes, flip=flip)
            if s > score:
                best, score = (clip, t), s
    return best


def _head_vertices(model: Model, joint: str) -> np.ndarray:
    """Indexy vrcholu, ktere na dany joint visi vetsinovou vahou."""
    slot = int(np.where(model.skin_joints == model.node_names.index(joint))[0][0])
    w = sum(np.where(model.joints[:, k] == slot, model.weights[:, k], 0) for k in range(4))
    return np.where(w > 0.5)[0]


def auto_eye(model: Model, place: Placement, verts: np.ndarray, mask: np.ndarray,
             joint: str = "Head", forward: float = 0.68, down: float = 0.34,
             r_mm: float = 2.4, centre_x: bool = False) -> tuple | None:
    """Oko odvozene z obalky hlavy na listu.

    Modely oko nemaji — nese ho materialova barva, ne geometrie. Pozice se
    proto bere z obdelnika, do ktereho se hlava na listu vejde, a bod se
    posouva k teziti hlavy, dokud se krouzek oka nevejde dovnitr obrysu.
    `centre_x` klade oko na osu soumernosti listu — letci kresleni shora ji
    maji po fitu vzdy uprostred, zatimco bbox hlavy muze byt nesoumerny.
    """
    idx = _head_vertices(model, joint)
    if len(idx) == 0:
        return None
    head_mm = place.to_mm(verts[idx])
    body_mm = place.to_mm(verts)
    lo, hi = head_mm.min(0), head_mm.max(0)

    facing_right = head_mm[:, 0].mean() > body_mm[:, 0].mean()
    fx = forward if facing_right else 1.0 - forward
    x = SHEET_W_MM / 2 if centre_x else lo[0] + fx * (hi[0] - lo[0])
    y = lo[1] + down * (hi[1] - lo[1])

    # oko i obrys se tisknou linkou LINE_MM: aby se krouzek oka obrysu ani
    # nedotkl, musi byt jeho stred r + pul linky oka + pul linky obrysu hluboko
    clear_mm = r_mm + LINE_MM
    ppm_x = mask.shape[1] / SHEET_W_MM
    ppm_y = mask.shape[0] / SHEET_H_MM
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)

    centre = head_mm.mean(0)
    if centre_x:
        centre = np.array([x, centre[1]])
    best = None
    for step in np.linspace(0.0, 1.0, 24):
        px = x + (centre[0] - x) * step
        py = y + (centre[1] - y) * step
        col = int(round(px * ppm_x))
        row = int(round(py * ppm_y))
        if not (0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]):
            continue
        d = dist[row, col] / ppm_x
        if d >= clear_mm:
            return (float(px), float(py), r_mm)
        if best is None or d > best[2]:
            best = (px, py, d)
    if best is not None and best[2] > 0:
        return (float(best[0]), float(best[1]), r_mm)
    return None


def build(
    model: Model,
    *,
    key: str,
    label: str,
    anim: str | None = None,
    time: float = 0.0,
    axes: tuple[int, int, int] = (2, 1, 0),
    flip: tuple[int, int, int] = (1, -1, 1),
    ppm: float = 8.0,
    eye_joint: str | None = "Head",
    eye_bias: dict | None = None,
    eye_r_mm: float = 2.4,
) -> SheetShape:
    """Vyrobi predlohu z modelu v dane poze."""
    eye_bias = eye_bias or {}
    verts, normals = model.posed(anim, time)

    u = verts[:, axes[0]] * flip[0]
    v = verts[:, axes[1]] * flip[1]
    lo = np.array([u.min(), v.min()])
    hi = np.array([u.max(), v.max()])
    mm_per_unit, off_x, off_y = _fit(lo, hi)
    place = Placement(tuple(axes), tuple(flip), mm_per_unit, float(lo[0]), float(lo[1]),
                      off_x, off_y)

    width = int(round((hi[0] - lo[0]) * mm_per_unit * ppm)) + 1
    view = ov.render(verts, model.indices, normals, axes=axes, flip=flip,
                     width=width, bounds=(lo, hi))
    layers = ov.outline_edges(view, model.tri_material)

    px_per_mm = view.scale / mm_per_unit
    origin_px = np.zeros(2)
    offset_mm = np.array([off_x, off_y])

    # vnejsi obrys se trasuje ze zvetsene masky (OUTLINE_GROW_MM); vnitrni
    # oblasti i Placement/UV zustavaji na presne projekci modelu. Rastr masky
    # konci presne na bboxu, takze pred dilataci je treba pridat okraj, jinak
    # by se zvetseny obrys na krajich seriznul.
    pad = int(round(OUTLINE_GROW_MM * px_per_mm))
    k = 2 * pad + 1
    grown = cv2.dilate(
        cv2.copyMakeBorder(view.mask.astype(np.uint8), pad, pad, pad, pad,
                           cv2.BORDER_CONSTANT, value=0),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    outline = _trace(grown, px_per_mm, origin_px + pad, offset_mm, MIN_REGION_MM2 * 4)

    # oblasti k vybarveni: co nerozdeluje hranice materialu ani skok v hloubce
    border = layers["material"] | layers["depth"]
    interior = view.mask & ~border
    n, comp = cv2.connectedComponents(interior.astype(np.uint8), connectivity=4)
    regions = []
    for i in range(1, n):
        regions.extend(_trace(comp == i, px_per_mm, origin_px, offset_mm, MIN_REGION_MM2))

    eye = None
    if eye_joint is not None:
        sheet_mask = np.zeros((int(SHEET_H_MM * 4), int(SHEET_W_MM * 4)), np.uint8)
        for poly in outline:
            cv2.fillPoly(sheet_mask, [np.round(poly * 4).astype(np.int32)], 1)
        eye = auto_eye(model, place, verts, sheet_mask.astype(bool), eye_joint,
                       r_mm=eye_r_mm, **eye_bias)

    return SheetShape(key, label, outline, regions, eye, place, anim or "", time)


def save(shape: SheetShape, path: str | Path) -> None:
    d = asdict(shape)
    d["outline"] = [np.round(p, 3).tolist() for p in shape.outline]
    d["regions"] = [np.round(p, 3).tolist() for p in shape.regions]
    Path(path).write_text(json.dumps(d), encoding="utf-8")


def load(path: str | Path) -> SheetShape:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    d["placement"] = Placement(**d["placement"])
    d["outline"] = [np.asarray(p, float) for p in d["outline"]]
    d["regions"] = [np.asarray(p, float) for p in d["regions"]]
    d["eye"] = tuple(d["eye"]) if d["eye"] else None
    return SheetShape(**d)


def to_texture(sheet: np.ndarray, shape: SheetShape, ppm: float) -> np.ndarray:
    """Z vybarveneho listu udela texturu: linky zamaluje okolni barvou a barvu
    rozlije kousek za obrys. Bez toho se cerny obrys pri otoceni modelu
    protahne pres hrbet — obrys patri na papir, ne na kuzi."""
    body = np.zeros(sheet.shape[:2], np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * ppm).astype(np.int32)], 255)

    dark = (sheet.max(axis=2) < 110).astype(np.uint8)
    ink = cv2.dilate(dark, np.ones((3, 3), np.uint8)) & (body > 0)
    tex = cv2.inpaint(sheet, ink, 4, cv2.INPAINT_TELEA)

    grown = cv2.dilate(body, np.ones((int(2 * ppm) | 1, int(2 * ppm) | 1), np.uint8))
    fill = cv2.inpaint(tex, ((grown > 0) & (body == 0)).astype(np.uint8), 6, cv2.INPAINT_TELEA)
    return np.where((grown > 0)[..., None], fill, tex)
