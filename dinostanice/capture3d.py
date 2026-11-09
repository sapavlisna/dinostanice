"""Z vyfoceneho listu udela texturu pro 3D model.

Protejsek `rig.py` pro vetev, ktera stoji na hotovych modelech. Zadny rig se
nestavi — model uz kostru ma. Staci prenest barvy z papiru na kuzi, a to je
otazka jedine transformace, protoze predloha vznikla promitnutim modelu na
list: kde na papire bod lezi, tam ma na modelu svoje UV.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import capture
from . import modelsheet
from . import paths
from .modelsheet import SheetShape, to_texture
from .store import write_image
from .shapes import SHEET_H_MM, SHEET_W_MM

TEXTURE_PPM = 6.0        # jemnejsi nez WARP_PPM uz nema z ceho brat detail
# Doplnek (ptacek, motylek) se ulozi, jen kdyz je jeho okenko opravdu vybarvene:
# podil barevnych bodu uvnitr miniatury (bez tistenych linek).
EXTRA_MIN_COVERAGE = 0.12
EXTRA_ERODE_MM = 1.5

SHAPES3D_DIR = Path(paths.resource_root()) / "data" / "shapes3d"


@lru_cache(maxsize=None)
def load_shape(key: str) -> SheetShape:
    """Predloha tvora z data/shapes3d/<key>.json.

    Cachovane: cte se pri kazdem uploadu a je to zacommitovany, za behu
    nemenny soubor (prepisuje ho jen tools/model_sheet.py).
    """
    return modelsheet.load(SHAPES3D_DIR / f"{key}.json")


def sheet_mask(shape: SheetShape, ppm: float) -> np.ndarray:
    """Maska kresby na listu, v pixelech dane hustoty."""
    mask = np.zeros((int(round(SHEET_H_MM * ppm)), int(round(SHEET_W_MM * ppm))), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
    return mask


def build_texture(warped: np.ndarray, shape: SheetShape, flatten: bool = True,
                  ink_grow: int = 3, inpaint_r: int = 4, grow_mm: float = 2.0,
                  ink_max: int = 110, ink_lines_mm: float = 0.0,
                  erode_mm: float = 0.0) -> np.ndarray:
    """Srovnany list -> textura pro model.

    Osvetleni se narovna jen uvnitr kresby (venku je papir a znacky, ktere by
    odhad zkreslily), pak se vymazou tistene linky a barva se rozlije kousek za
    obrys — model je o chlup jinde nez papirovy obrys a bily lem by se na nem
    projevil jako svetla obruba.
    """
    ppm = TEXTURE_PPM
    size = (int(round(SHEET_W_MM * ppm)), int(round(SHEET_H_MM * ppm)))
    sheet = cv2.resize(warped, size, interpolation=cv2.INTER_AREA)

    if flatten:
        mask = sheet_mask(shape, ppm)
        flat = capture.flatten_lighting(sheet, mask)
        sheet = np.where(mask[..., None] > 0, flat, sheet)
    return to_texture(sheet, shape, ppm, ink_grow=ink_grow, inpaint_r=inpaint_r,
                      grow_mm=grow_mm, ink_max=ink_max, ink_lines_mm=ink_lines_mm,
                      erode_mm=erode_mm)


def save_catch(out_dir: str | Path, warped: np.ndarray, shape: SheetShape,
               spec, name: str) -> dict:
    """Ulozi texturu a popis ulovku; model uz lezi v data/models3d."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    texture = build_texture(warped, shape)
    write_image(out / "texture.png", texture)

    doc = {
        "key": spec.key,
        "label": spec.label,
        "motion": spec.motion,
        "name": name,
        "glb": f"/models3d/{spec.key}.glb",
        "texture": "texture.png",
    }
    (out / "model.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def extra_sheets(warped: np.ndarray, shape: SheetShape) -> list:
    """Okenka doplnku z jednoho listu: pro kazde jeho vlastni "virtualni list".

    Miniatura v rohu je zmensena kopie predlohy doplnku, takze se okenko
    zvetsi zpatky (afinne, podle `scale` a `offset` z tvaru listu) na list
    doplnku, a dal uz to je obycejna textura. Svetlo se narovnava na cele
    fotce najednou, mimo zvire i okenka (barevna okenka by odhad zkreslila).
    Vraci [{key, shape, coverage, sheet}]."""
    if not shape.extras:
        return []
    ppm = capture.WARP_PPM
    host = sheet_mask(shape, ppm)
    boxes = np.zeros_like(host)
    for slot in shape.extras:
        x, y, w, h = slot["rect"]
        cv2.rectangle(boxes, (int(x * ppm) - 6, int(y * ppm) - 6),
                      (int((x + w) * ppm) + 6, int((y + h) * ppm) + 6), 255, -1)
    flat = capture.flatten_lighting(warped, np.maximum(host, boxes))

    out = []
    for slot in shape.extras:
        ex = load_shape(slot["key"])
        f, (ox, oy) = slot["scale"], slot["offset"]
        outline, _ = modelsheet.extra_polys(ex, slot)
        mask = np.zeros(host.shape, np.uint8)
        for poly in outline:
            cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
        k = int(2 * EXTRA_ERODE_MM * ppm) | 1
        inner = cv2.erode(mask, np.ones((k, k), np.uint8)) > 0
        if not inner.any():
            continue
        hsv = cv2.cvtColor(flat, cv2.COLOR_BGR2HSV)
        coloured = (hsv[..., 1] > 60) | (hsv[..., 2] < 110)
        coverage = float((coloured & inner).sum()) / float(inner.sum())
        m = np.array([[1 / f, 0, -ox * ppm / f], [0, 1 / f, -oy * ppm / f]], np.float32)
        sheet = cv2.warpAffine(flat, m, (flat.shape[1], flat.shape[0]),
                               flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        out.append({"key": slot["key"], "shape": ex, "coverage": coverage, "sheet": sheet})
    return out


def save_extra_catch(out_dir: str | Path, sheet: np.ndarray, shape: SheetShape,
                     spec, name: str) -> dict:
    """Jako save_catch, jen svetlo uz je narovnane z celeho listu."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # miniatura se zvetsuje, takze i tistene linky jsou siroke a rozmazane
    write_image(out / "texture.png", build_texture(sheet, shape, flatten=False,
                                                  ink_grow=13, inpaint_r=7, grow_mm=4.5,
                                                  ink_max=150, ink_lines_mm=4.5,
                                                  erode_mm=3.0))
    doc = {"key": spec.key, "label": spec.label, "motion": spec.motion, "name": name,
           "glb": f"/models3d/{spec.key}.glb", "texture": "texture.png"}
    (out / "model.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def ink_coverage(warped: np.ndarray, shape: SheetShape) -> float:
    """Jak velkou cast kresby dite skutecne vybarvilo."""
    ppm = TEXTURE_PPM
    size = (int(round(SHEET_W_MM * ppm)), int(round(SHEET_H_MM * ppm)))
    sheet = cv2.resize(warped, size, interpolation=cv2.INTER_AREA)
    mask = sheet_mask(shape, ppm) > 0
    if not mask.any():
        return 0.0
    hsv = cv2.cvtColor(sheet, cv2.COLOR_BGR2HSV)
    coloured = (hsv[..., 1] > 60) | (hsv[..., 2] < 110)
    return float((coloured & mask).sum()) / float(mask.sum())
