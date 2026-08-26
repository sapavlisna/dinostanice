"""Fiducial markers.

Four ArUco markers sit in the corners of every sheet. Their IDs encode which
creature the sheet is, so one photo tells us both where the paper is and what
was coloured in. IDs are allocated 4 per creature: 4*index + corner.
"""

import cv2
import numpy as np

from .shapes import SHEET_W_MM, SHEET_H_MM

# 4X4_100 je nadmnozina 4X4_50 (prvnich 50 kodu je shodnych), takze uz
# vytistene listy plati dal a pribylo misto pro dalsi tvory
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
MARKER_MM = 16.0
MARGIN_MM = 9.0

# top-left, top-right, bottom-right, bottom-left
CORNER_ORIGINS = [
    (MARGIN_MM, MARGIN_MM),
    (SHEET_W_MM - MARGIN_MM - MARKER_MM, MARGIN_MM),
    (SHEET_W_MM - MARGIN_MM - MARKER_MM, SHEET_H_MM - MARGIN_MM - MARKER_MM),
    (MARGIN_MM, SHEET_H_MM - MARGIN_MM - MARKER_MM),
]


def marker_ids(creature_index):
    return [4 * creature_index + i for i in range(4)]


def creature_index_of(marker_id):
    return marker_id // 4, marker_id % 4


def marker_bits(marker_id, border=1):
    """Marker as a small binary matrix, 1 = black."""
    side = 4 + 2 * border
    img = cv2.aruco.generateImageMarker(DICT, marker_id, side, borderBits=border)
    return (img == 0).astype(np.uint8)


def marker_corner_points_mm(creature_index):
    """Expected sheet-space corners of every marker, in ArUco's own order."""
    out = {}
    for corner, mid in enumerate(marker_ids(creature_index)):
        ox, oy = CORNER_ORIGINS[corner]
        m = MARKER_MM
        out[mid] = np.array([[ox, oy], [ox + m, oy], [ox + m, oy + m], [ox, oy + m]],
                            dtype=np.float32)
    return out
