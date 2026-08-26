"""Z vyfoceneho listu udela texturu pro 3D model.

Protejsek `rig.py` pro vetev, ktera stoji na hotovych modelech. Zadny rig se
nestavi — model uz kostru ma. Staci prenest barvy z papiru na kuzi, a to je
otazka jedine transformace, protoze predloha vznikla promitnutim modelu na
list: kde na papire bod lezi, tam ma na modelu svoje UV.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from . import capture
from .modelsheet import SheetShape, to_texture
from .shapes import SHEET_H_MM, SHEET_W_MM

TEXTURE_PPM = 6.0        # jemnejsi nez WARP_PPM uz nema z ceho brat detail


def sheet_mask(shape: SheetShape, ppm: float) -> np.ndarray:
    """Maska kresby na listu, v pixelech dane hustoty."""
    mask = np.zeros((int(round(SHEET_H_MM * ppm)), int(round(SHEET_W_MM * ppm))), np.uint8)
    for poly in shape.outline:
        cv2.fillPoly(mask, [np.round(poly * ppm).astype(np.int32)], 255)
    return mask


def build_texture(warped: np.ndarray, shape: SheetShape) -> np.ndarray:
    """Srovnany list -> textura pro model.

    Osvetleni se narovna jen uvnitr kresby (venku je papir a znacky, ktere by
    odhad zkreslily), pak se vymazou tistene linky a barva se rozlije kousek za
    obrys — model je o chlup jinde nez papirovy obrys a bily lem by se na nem
    projevil jako svetla obruba.
    """
    ppm = TEXTURE_PPM
    size = (int(round(SHEET_W_MM * ppm)), int(round(SHEET_H_MM * ppm)))
    sheet = cv2.resize(warped, size, interpolation=cv2.INTER_AREA)

    mask = sheet_mask(shape, ppm)
    flat = capture.flatten_lighting(sheet, mask)
    sheet = np.where(mask[..., None] > 0, flat, sheet)
    return to_texture(sheet, shape, ppm)


def save_catch(out_dir: str | Path, warped: np.ndarray, shape: SheetShape,
               spec, name: str) -> dict:
    """Ulozi texturu a popis ulovku; model uz lezi v data/models3d."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    texture = build_texture(warped, shape)
    cv2.imwrite(str(out / "texture.png"), texture)

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
