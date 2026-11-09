"""Z 3D modelu udela predlohu k vybarveni.

Klicovy krok cele stanice: ortogonalni bokorys hotoveho modelu da soucasne
obrys, vnitrni linky (hranice materialu a hloubkove skoky) a — hlavne —
prevodni vztah mezi milimetry na listu a souradnicemi modelu. Diky nemu
vybarvena kresba sedne zpatky na model jako textura: kde na papire bod lezi,
tam ma na modelu svoje UV. Zadna hloubka se z kresby nehada.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import cv2
import numpy as np

from .gltf import Model
from . import orthoview as ov
from .markers import CORNER_ORIGINS, MARKER_MM, marker_bits, marker_ids
from .shapes import SHEET_W_MM, SHEET_H_MM, LINE_MM

DETAIL_MM = 0.6           # vnitrni linky jsou tencí než obrys, dítě je jen obtahuje
DRAW_MARGIN_X_MM = 32.0   # znacky v rozich zabiraji 9 + 16 mm
DRAW_MARGIN_Y_MM = 30.0
# Kresba ma byt pro dite prehledna: silny obrys a par velkych ploch. Drobne
# a uzke oblasti (bodce, prsty, hloubkove skoky podel ocasu) se proto slucuji
# se sousedem, misto aby z nich byly milimetrove prouzky.
MIN_OUTLINE_MM2 = 12.0        # samostatny kus obrysu, ktery jeste ma smysl tisknout
MIN_REGION_MM2 = 40.0         # plocha, kterou dite pastelkou vybarvi
MIN_REGION_WIDTH_MM = 5.0     # vepsany kruh oblasti; uzsi pruh se nevybarvuje
MIN_LINE_MM = 15.0            # kratke ohryzky hranic do kresby nepatri
SIMPLIFY_MM = 0.35            # obrys musi zustat verny projekci modelu (UV)
LINE_SIMPLIFY_MM = 1.2        # vnitrni linky smi byt plynulejsi, dite je obtahuje
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
        """Pozice na listu jako UV (0..1): x doprava, y nahoru od spodni hrany."""
        mm = self.to_mm(verts)
        return np.stack([mm[:, 0] / SHEET_W_MM, 1.0 - mm[:, 1] / SHEET_H_MM], axis=1)


@dataclass
class SheetShape:
    """Obrys a vnitrni linky jednoho tvora v milimetrech na listu."""

    key: str
    label: str
    outline: list          # [vnejsi polygon, ...] — prvni je silueta
    regions: list          # vnitrni linky (hranice mezi oblastmi), obtazene tam a zpet
    eye: tuple | None
    placement: Placement
    anim: str
    time: float
    # Okenka doplnku (ptacek, motylek) v rohu listu, viz place_extras:
    # [{"key", "rect": [x, y, w, h], "scale", "offset": [ox, oy]}, ...]
    extras: list = field(default_factory=list)


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


def _trace_lines(line_mask: np.ndarray, ppm: float, origin_px: np.ndarray,
                 offset_mm: np.ndarray) -> list[np.ndarray]:
    """Tenkou masku linek prevede na polygony, ktere linku obkresli tam a zpet.

    Vnitrni kresba nejsou obrysy oblasti, ale samotne hranice mezi nimi: kdyby
    se trasovaly oblasti, obtahla by se s nimi i silueta a vedle tisteneho
    (zvetseneho) obrysu by vznikla druha, paralelni linka.
    """
    out = []
    cnts, _ = cv2.findContours(line_mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                              cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        # kontura tenke linky obejde tam a zpet, delka je tedy pulka obvodu
        if cv2.arcLength(c, True) / 2 / ppm < MIN_LINE_MM:
            continue
        c = cv2.approxPolyDP(c, LINE_SIMPLIFY_MM * ppm, True).reshape(-1, 2).astype(float)
        if len(c) < 3:
            continue
        pts = (c - origin_px) / ppm + offset_mm
        out.append(_chaikin(pts) if len(pts) >= 4 else pts)
    return out


def _inscribed_mm(region: np.ndarray, ppm: float) -> float:
    """Prumer nejvetsiho kruhu, ktery se do oblasti vejde — jeji sirka.

    Plocha sama nestaci: ocas rozsekany hloubkovym skokem da dlouhou oblast
    o velke plose a sirce pod milimetr.
    """
    ys, xs = np.nonzero(region)
    sub = region[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
    sub = cv2.copyMakeBorder(sub, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    return 2 * float(cv2.distanceTransform(sub, cv2.DIST_L2, 5).max()) / ppm


def _regions(mask: np.ndarray, border: np.ndarray, extent: np.ndarray,
             ppm: float) -> np.ndarray:
    """Siluetu rozdeli na nekolik velkych oblasti.

    Drobne a uzke ostruvky se nezahazuji, ale propadnou nejblizsi velke
    oblasti — kdyby se jen smazaly, zustala by po nich v kresbe dira.
    `extent` (zvetsena maska) rika, kam se oblasti rozlejou: linky pak dojedou
    az k tistenemu obrysu a nekonci pred nim ve vzduchu.
    """
    n, comp = cv2.connectedComponents((mask & ~border).astype(np.uint8), connectivity=4)
    keep = [i for i in range(1, n)
            if (comp == i).sum() / ppm ** 2 >= MIN_REGION_MM2
            and _inscribed_mm(comp == i, ppm) >= MIN_REGION_WIDTH_MM]
    if not keep:
        return np.zeros_like(comp)
    seed = np.isin(comp, keep)
    _, lbl = cv2.distanceTransformWithLabels((~seed).astype(np.uint8), cv2.DIST_L2, 5,
                                             labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros(int(lbl.max()) + 1, np.int32)
    lut[lbl[seed]] = comp[seed]
    out = lut[lbl]
    out[~extent] = 0
    return out


def _region_edges(labels: np.ndarray) -> np.ndarray:
    """Pixely, kde se stykaji dve rozdilne oblasti."""
    edge = np.zeros(labels.shape, bool)
    for ax, s in ((0, 1), (0, -1), (1, 1), (1, -1)):
        sh = np.roll(labels, s, ax)
        edge |= (labels > 0) & (sh > 0) & (sh != labels)
    return edge


def fill_ratio(model: Model, anim: str, time: float,
               axes: tuple[int, int, int] = (2, 1, 0),
               flip: tuple[int, int, int] = (1, -1, 1), width: int = 240) -> float:
    """Jakou cast kreslici plochy tvor po vystredeni zabere.

    Merit se musi az po fitu na list, ne v pixelech: natazeny apatosaurus ma velkou
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

    # vnejsi obrys se trasuje ze zvetsene masky (OUTLINE_GROW_MM); Placement/UV
    # zustavaji na presne projekci modelu. Rastr masky konci presne na bboxu,
    # takze pred dilataci je treba pridat okraj, jinak by se zvetseny obrys na
    # krajich seriznul. V tomto orameckovanem rastru se pak pocita vsechno.
    pad = int(round(OUTLINE_GROW_MM * px_per_mm))
    origin_px = origin_px + pad

    def framed(a):
        return cv2.copyMakeBorder(a.astype(np.uint8), pad, pad, pad, pad,
                                  cv2.BORDER_CONSTANT, value=0).astype(bool)

    k = 2 * pad + 1
    mask = framed(view.mask)
    grown = cv2.dilate(mask.astype(np.uint8),
                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
    outline = _trace(grown, px_per_mm, origin_px, offset_mm, MIN_OUTLINE_MM2)

    # vnitrni kresba: hranice mezi velkymi oblastmi (hlava, telo, nohy,
    # plotenky). Hranice materialu a hloubkove skoky oblasti jen vymezuji.
    border = framed(layers["material"] | layers["depth"])
    labels = _regions(mask, border, grown, px_per_mm)
    regions = _trace_lines(_region_edges(labels), px_per_mm, origin_px, offset_mm)

    eye = None
    if eye_joint is not None:
        # oko drzi odstup nejen od obrysu, ale i od vnitrnich linek — krouzek
        # prekryty linkou hlavy je stejne necitelny jako krouzek na obrysu
        sheet_mask = np.zeros((int(SHEET_H_MM * 4), int(SHEET_W_MM * 4)), np.uint8)
        for poly in outline:
            cv2.fillPoly(sheet_mask, [np.round(poly * 4).astype(np.int32)], 1)
        for poly in regions:
            cv2.polylines(sheet_mask, [np.round(poly * 4).astype(np.int32)], True, 0,
                          max(1, int(round(LINE_MM * 4))))
        eye = auto_eye(model, place, verts, sheet_mask.astype(bool), eye_joint,
                       r_mm=eye_r_mm, **eye_bias)

    return SheetShape(key, label, outline, regions, eye, place, anim or "", time)


# --- doplnky v rohu listu ----------------------------------------------------

EXTRA_PAD_MM = 3.0           # okraj okenka kolem miniatury
EXTRA_CAPTION_MM = 4.5       # popisek nad miniaturou
EXTRA_LONG_MM = 50.0         # pozadovana delsi strana miniatury
EXTRA_MIN_LONG_MM = 30.0     # mensi uz se vybarvovat nedá
EXTRA_KEEP_OUT_MM = 5.0      # odstup od obrysu zvirete
EXTRA_TEXT_MM = 12.0         # pas dole, kde je popisek listu


def shape_bbox(shape: SheetShape) -> tuple[np.ndarray, np.ndarray]:
    pts = np.vstack([p for p in shape.outline])
    return pts.min(axis=0), pts.max(axis=0)


def extra_polys(shape: SheetShape, slot: dict) -> list:
    """Obrys a vnitrni linky doplnku, prepocitane do souradnic hostitelskeho listu."""
    f, off = slot["scale"], np.asarray(slot["offset"], float)
    return [p * f + off for p in shape.outline], [p * f + off for p in shape.regions]


def place_extras(host: SheetShape, extras: list) -> list:
    """Najde na listu volna okenka pro doplnky, aniz by se dotkla zvirete.

    Okenka jdou do spodnich rohu (prvni vlevo, druhy vpravo); kdyz se nevejde
    pozadovana velikost, miniatura se zmensuje az k EXTRA_MIN_LONG_MM, a kdyz
    ani tak, doplnek se na tomhle listu vynecha."""
    res = 1.0                                   # 1 px = 1 mm
    w_px, h_px = int(round(SHEET_W_MM)), int(round(SHEET_H_MM))
    blocked = np.zeros((h_px, w_px), np.uint8)
    for poly in host.outline:
        cv2.fillPoly(blocked, [np.round(poly * res).astype(np.int32)], 1)
    k = int(2 * EXTRA_KEEP_OUT_MM) | 1
    blocked = cv2.dilate(blocked, np.ones((k, k), np.uint8))
    for ox, oy in CORNER_ORIGINS:
        m = int(MARKER_MM + 8)
        blocked[max(0, int(oy) - 4):int(oy) + m, max(0, int(ox) - 4):int(ox) + m] = 1
    blocked[:6, :] = 1
    blocked[:, :6] = 1
    blocked[:, w_px - 6:] = 1
    blocked[h_px - int(EXTRA_TEXT_MM):, :] = 1

    slots = []
    for idx, ex in enumerate(extras):
        lo, hi = shape_bbox(ex)
        span = hi - lo
        long_mm = EXTRA_LONG_MM
        placed = None
        while long_mm >= EXTRA_MIN_LONG_MM and placed is None:
            f = long_mm / float(span.max())
            bw = float(span[0]) * f + 2 * EXTRA_PAD_MM
            bh = float(span[1]) * f + 2 * EXTRA_PAD_MM + EXTRA_CAPTION_MM
            bw_i, bh_i = int(np.ceil(bw)), int(np.ceil(bh))
            integral = cv2.integral(blocked)
            best, best_score = None, None
            for y in range(6, h_px - bh_i, 2):
                for x in range(6, w_px - bw_i, 2):
                    tot = (integral[y + bh_i, x + bw_i] - integral[y, x + bw_i]
                           - integral[y + bh_i, x] + integral[y, x])
                    if tot:
                        continue
                    # dole a do rohu: prvni doplnek vlevo, druhy vpravo
                    side = (w_px - (x + bw_i)) if idx % 2 == 0 else x
                    score = (y + bh_i) * 3.0 - side
                    if best_score is None or score > best_score:
                        best, best_score = (x, y), score
            if best is None:
                long_mm *= 0.92
                continue
            x, y = best
            ax = x + (bw - float(span[0]) * f) / 2
            ay = y + EXTRA_CAPTION_MM + EXTRA_PAD_MM
            placed = {"key": ex.key, "rect": [x, y, round(bw, 2), round(bh, 2)],
                      "scale": round(f, 5),
                      "offset": [round(ax - float(lo[0]) * f, 3), round(ay - float(lo[1]) * f, 3)]}
        if placed is None:
            continue
        x, y, bw, bh = placed["rect"]
        blocked[y:y + int(np.ceil(bh)) + 2, x:x + int(np.ceil(bw)) + 2] = 1
        slots.append(placed)
    return slots


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
    d.setdefault("extras", [])
    return SheetShape(**d)


def to_texture(sheet: np.ndarray, shape: SheetShape, ppm: float,
               remove_ink: bool = True, ink_grow: int = 3, inpaint_r: int = 4,
               grow_mm: float = 2.0, ink_max: int = 110,
               ink_lines_mm: float = 0.0, erode_mm: float = 0.0) -> np.ndarray:
    """Z vybarveneho listu udela texturu: linky zamaluje okolni barvou a barvu
    rozlije kousek za obrys. Bez toho se cerny obrys pri otoceni modelu
    protahne pres hrbet — obrys patri na papir, ne na kuzi."""
    body = np.zeros(sheet.shape[:2], np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(body, [np.round(poly * ppm).astype(np.int32)], 255)

    if remove_ink:
        dark = (sheet.max(axis=2) < ink_max).astype(np.uint8)
        ink = cv2.dilate(dark, np.ones((ink_grow, ink_grow), np.uint8)) & (body > 0)
        if ink_lines_mm:
            # kde jsou tistene linky, vime presne: zvetsena miniatura je rozmaze
            # tak, ze je barevny prah nezachyti cele
            lines = np.zeros_like(body)
            for poly in list(shape.regions) + list(shape.outline):
                cv2.polylines(lines, [np.round(poly * ppm).astype(np.int32)], True, 1,
                              max(1, int(ink_lines_mm * ppm)))
            ink = ink | (lines & (body > 0))
        tex = cv2.inpaint(sheet, ink, inpaint_r, cv2.INPAINT_TELEA)
    else:
        tex = sheet

    g = int(grow_mm * ppm) | 1
    grown = cv2.dilate(body, np.ones((g, g), np.uint8))
    core = body
    if erode_mm:
        # okraj je zasazeny do rozmazane linky: jako zname se bere az to, co je od ni dal
        e = int(2 * erode_mm * ppm) | 1
        core = cv2.erode(body, np.ones((e, e), np.uint8))
    fill = cv2.inpaint(tex, ((grown > 0) & (core == 0)).astype(np.uint8), max(6, inpaint_r),
                       cv2.INPAINT_TELEA)
    return np.where((grown > 0)[..., None], fill, tex)


EXTRA_LINE_MM = 0.7          # miniatura ma tencí linky nez zvire
EXTRA_DETAIL_MM = 0.4


def rasterise(shape: SheetShape, marker_index: int | None = None,
              ppm: float = 6.0, extras_shapes: dict | None = None) -> np.ndarray:
    """Vytištěná předloha jako bitmapa: obrys, vnitřní linky, oko a značky.

    Tiskne se z SVG (tools/model_sheet.py), tohle je tentýž list pro náhledy
    a pro syntetické fotky v testech — aby se dala celá cesta „papír → tvor"
    projít bez tiskárny.
    """
    img = np.full((int(round(SHEET_H_MM * ppm)), int(round(SHEET_W_MM * ppm)), 3),
                  255, np.uint8)
    for polys, width in ((shape.regions, DETAIL_MM), (shape.outline, LINE_MM)):
        for poly in polys:
            cv2.polylines(img, [np.round(poly * ppm).astype(np.int32)], True,
                          (17, 17, 17), max(1, int(round(width * ppm))), cv2.LINE_AA)
    if shape.eye:
        x, y, r = shape.eye
        cv2.circle(img, (int(x * ppm), int(y * ppm)), int(r * ppm), (17, 17, 17),
                   max(1, int(round(LINE_MM * ppm))), cv2.LINE_AA)
    for slot in shape.extras:
        ex = extras_shapes.get(slot["key"]) if extras_shapes else None
        x, y, bw, bh = slot["rect"]
        cv2.rectangle(img, (int(x * ppm), int(y * ppm)), (int((x + bw) * ppm), int((y + bh) * ppm)),
                      (150, 150, 150), 1, cv2.LINE_AA)
        if ex is not None:
            outline, regions = extra_polys(ex, slot)
            for polys, width in ((regions, EXTRA_DETAIL_MM), (outline, EXTRA_LINE_MM)):
                for poly in polys:
                    cv2.polylines(img, [np.round(poly * ppm).astype(np.int32)], True,
                                  (17, 17, 17), max(1, int(round(width * ppm))), cv2.LINE_AA)
    if marker_index is not None:
        for corner, mid in enumerate(marker_ids(marker_index)):
            ox, oy = CORNER_ORIGINS[corner]
            bits = marker_bits(mid)
            cell = MARKER_MM / bits.shape[0]
            for r in range(bits.shape[0]):
                for c in range(bits.shape[1]):
                    if bits[r, c]:
                        cv2.rectangle(img,
                                      (int(round((ox + c * cell) * ppm)),
                                       int(round((oy + r * cell) * ppm))),
                                      (int(round((ox + (c + 1) * cell) * ppm)) - 1,
                                       int(round((oy + (r + 1) * cell) * ppm)) - 1),
                                      (0, 0, 0), -1)
    return img
