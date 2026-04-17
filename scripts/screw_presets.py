#!/usr/bin/env python3
"""
screw_presets.py

Screw position generators for KLE-only mode (no KiCad PCB).
Returns a list of (x, y) coordinates in plate space (same coord system as
build_plate.build_entities output: origin at BL, Y up, pad applied).
"""

from __future__ import annotations


def four_corners(plate_w, plate_h, inset=5.0):
    """Four M2 screws, one at each corner, inset from edges."""
    return [
        (inset, inset),
        (plate_w - inset, inset),
        (inset, plate_h - inset),
        (plate_w - inset, plate_h - inset),
    ]


def six_perimeter(plate_w, plate_h, inset=5.0):
    """Four corners + two mid-top/mid-bottom."""
    return four_corners(plate_w, plate_h, inset) + [
        (plate_w / 2.0, inset),
        (plate_w / 2.0, plate_h - inset),
    ]


def grid(plate_w, plate_h, cols=3, rows=2, inset=5.0):
    """Regular grid of screws, inset from edges."""
    pts = []
    for r in range(rows):
        for c in range(cols):
            x = inset + c * (plate_w - 2 * inset) / max(cols - 1, 1)
            y = inset + r * (plate_h - 2 * inset) / max(rows - 1, 1)
            pts.append((x, y))
    return pts


def between_rows(keys, plate_w, pad=0.0, inset=5.0, U1=19.05):
    """One screw between each row of keys, at the left/right inset positions.
    keys: list of dicts from parse_kle() with cy_u."""
    row_ys = sorted({round(k['cy_u'] * U1 + pad, 2) for k in keys})
    if len(row_ys) < 2:
        return []
    pts = []
    for i in range(len(row_ys) - 1):
        mid_y = (row_ys[i] + row_ys[i + 1]) / 2.0
        pts.append((inset, mid_y))
        pts.append((plate_w - inset, mid_y))
    return pts


PRESETS = {
    '4corners': four_corners,
    '6perimeter': six_perimeter,
    'grid3x2': lambda w, h, **kw: grid(w, h, 3, 2, **kw),
    'grid4x2': lambda w, h, **kw: grid(w, h, 4, 2, **kw),
    'between_rows': between_rows,
}


def custom_from_string(spec, plate_w, plate_h):
    """Parse a string like '5,5;100,50;200,60' into a list of (x,y)."""
    pts = []
    for pair in spec.split(';'):
        pair = pair.strip()
        if not pair:
            continue
        x, y = pair.split(',')
        pts.append((float(x), float(y)))
    return pts


if __name__ == '__main__':
    W, H = 361.95, 114.30
    print('4corners:', four_corners(W, H))
    print('6perimeter:', six_perimeter(W, H))
    print('grid 3x2:', grid(W, H, 3, 2))
    print('grid 4x2:', grid(W, H, 4, 2))
