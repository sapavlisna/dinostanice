"""Printable colouring templates.

A template is built once as a list of drawing primitives, then emitted either
as SVG (for printing) or rasterised with OpenCV (for previews and for the
synthetic test sheets used to develop the capture pipeline without a printer).
"""

import numpy as np

from .shapes import SHEET_W_MM, SHEET_H_MM
from .raster import outline_contours
from .markers import marker_ids, marker_bits, CORNER_ORIGINS, MARKER_MM

LINE_MM = 0.9


def build(creature, creature_index):
    """Drawing primitives in sheet millimetres."""
    items = []
    for contour in outline_contours(creature):
        items.append(("path", contour, LINE_MM))
    if creature.eye and creature.eye[2] > 0:
        items.append(("circle", creature.eye, LINE_MM))
    for line in creature.details:
        # interior lines: not silhouette edges, but the child needs them to tell
        # a sail from a hull. They are drawn, never part of the mask.
        items.append(("line", np.asarray(line, dtype=float), LINE_MM * 0.8))
    for corner, mid in enumerate(marker_ids(creature_index)):
        ox, oy = CORNER_ORIGINS[corner]
        bits = marker_bits(mid)
        cell = MARKER_MM / bits.shape[0]
        for r in range(bits.shape[0]):
            for c in range(bits.shape[1]):
                if bits[r, c]:
                    items.append(("rect", (ox + c * cell, oy + r * cell, cell, cell)))
    items.append(("label", creature.label))
    return items


def to_svg(creature, creature_index):
    items = build(creature, creature_index)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W_MM}mm" '
        f'height="{SHEET_H_MM}mm" viewBox="0 0 {SHEET_W_MM} {SHEET_H_MM}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    for item in items:
        kind = item[0]
        if kind == "path":
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in item[1])
            out.append(f'<polygon points="{pts}" fill="none" stroke="#111" '
                       f'stroke-width="{item[2]}" stroke-linejoin="round"/>')
        elif kind == "line":
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in item[1])
            out.append(f'<polyline points="{pts}" fill="none" stroke="#111" '
                       f'stroke-width="{item[2]}" stroke-linecap="round"/>')
        elif kind == "circle":
            x, y, r = item[1]
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" '
                       f'stroke="#111" stroke-width="{item[2]}"/>')
        elif kind == "rect":
            x, y, w, h = item[1]
            out.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" '
                       f'height="{h:.3f}" fill="#000"/>')
        elif kind == "label":
            out.append(f'<text x="{SHEET_W_MM/2:.1f}" y="{SHEET_H_MM - 6:.1f}" '
                       f'font-family="Verdana,sans-serif" font-size="6" fill="#999" '
                       f'text-anchor="middle">{item[1]} &#183; vybarvi mě a vyfoť</text>')
    out.append("</svg>")
    return "\n".join(out)


def _draw_label(img, text, ppm):
    """cv2.putText has no Czech diacritics, so the caption goes through PIL."""
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(img[:, :, ::-1])
    draw = ImageDraw.Draw(pil)
    size = max(10, int(round(4.5 * ppm)))
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    w = draw.textlength(text, font=font)
    draw.text(((pil.width - w) / 2, pil.height - int(11 * ppm)), text,
              fill=(150, 150, 150), font=font)
    img[:] = np.asarray(pil)[:, :, ::-1]


def rasterise(creature, creature_index, ppm=6.0, with_markers=True, with_label=True):
    import cv2
    W, H = int(round(SHEET_W_MM * ppm)), int(round(SHEET_H_MM * ppm))
    img = np.full((H, W, 3), 255, np.uint8)
    for item in build(creature, creature_index):
        kind = item[0]
        if kind == "path":
            cv2.polylines(img, [np.round(item[1] * ppm).astype(np.int32)], True,
                          (17, 17, 17), max(1, int(round(item[2] * ppm))), cv2.LINE_AA)
        elif kind == "line":
            cv2.polylines(img, [np.round(item[1] * ppm).astype(np.int32)], False,
                          (17, 17, 17), max(1, int(round(item[2] * ppm))), cv2.LINE_AA)
        elif kind == "circle":
            x, y, r = item[1]
            cv2.circle(img, (int(x * ppm), int(y * ppm)), int(r * ppm), (17, 17, 17),
                       max(1, int(round(item[2] * ppm))), cv2.LINE_AA)
        elif kind == "rect" and with_markers:
            x, y, w, h = item[1]
            cv2.rectangle(img, (int(round(x * ppm)), int(round(y * ppm))),
                          (int(round((x + w) * ppm)) - 1, int(round((y + h) * ppm)) - 1),
                          (0, 0, 0), -1)
        elif kind == "label" and with_label:
            _draw_label(img, f"{item[1]} · vybarvi mě a vyfoť", ppm)
    return img
