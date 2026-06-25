#!/usr/bin/env python3
"""
screw_presets.py

Screw position generators for KLE-only mode (no KiCad PCB).
Returns a list of (x, y) coordinates in plate space (same coord system as
build_plate.build_entities output: origin at BL, Y up, pad applied).
"""

from __future__ import annotations
import math

GRID = 19.05

CONVENTIONS = {
    "gh60": [(0.84, 3.02), (6.25, 2.02), (13.17, 3.02)],
    "skyway96": [(0.75, 0.0), (1.5, 4.5), (6.5, 4.5), (9.25, 2.5), (9.41, 0.0),
                 (11.5, 4.5), (12.38, 0.0), (14.5, 4.5), (17.5, 1.5), (17.5, 4.5)],
    "kbic65": [(-0.27, 4.5), (5.06, 4.5), (10.47, 4.5), (15.80, 4.5),
               (-0.27, -0.8), (5.06, -0.8), (10.47, -0.8), (15.80, -0.8)],
    "tkl": [(-0.4, 4.5), (5.5, 4.5), (11.0, 4.5), (17.5, 4.5),
            (-0.4, -0.5), (5.5, -0.5), (11.0, -0.5), (17.5, -0.5)],
}

EDGE_NOTCHES = {
    "gh60": [(-0.40, 1.52), (14.40, 1.52), (9.52, 0.01)],
    "skyway96": [(0.73, -0.30), (7.61, -0.30), (14.50, -0.30), (-0.30, 1.51)],
    "kbic65": [],
    "tkl": [],
}

def four_corners(plate_w, plate_h, inset=5.0):
    return [
        (inset, inset),
        (plate_w - inset, inset),
        (inset, plate_h - inset),
        (plate_w - inset, plate_h - inset),
    ]

def six_perimeter(plate_w, plate_h, inset=5.0):
    return four_corners(plate_w, plate_h, inset) + [
        (plate_w / 2.0, inset),
        (plate_w / 2.0, plate_h - inset),
    ]

def grid(plate_w, plate_h, cols=3, rows=2, inset=5.0):
    pts = []
    for r in range(rows):
        for c in range(cols):
            x = inset + c * (plate_w - 2 * inset) / max(cols - 1, 1)
            y = inset + r * (plate_h - 2 * inset) / max(rows - 1, 1)
            pts.append((x, y))
    return pts

def between_rows(keys, plate_w, pad=0.0, inset=5.0, U1=19.05):
    row_ys = sorted({round(k['cy_u'] * U1 + pad, 2) for k in keys})
    if len(row_ys) < 2:
        return []
    pts = []
    for i in range(len(row_ys) - 1):
        mid_y = (row_ys[i] + row_ys[i + 1]) / 2.0
        pts.append((inset, mid_y))
        pts.append((plate_w - inset, mid_y))
    return pts

def poker(plate_w, plate_h, inset=5.0):
    return [
        (19, plate_h - 40),
        (plate_w - 19, plate_h - 40),
        (plate_w / 2 - 20, 19),
        (plate_w / 2 + 20, 19),
        (plate_w / 2, plate_h / 2),
        (plate_w / 2 - 30, plate_h - 19),
    ]

def _anchor(centers):
    return min(c[0] for c in centers), min(c[1] for c in centers)

def convention_place(name, centers, grid=GRID):
    bx, by = _anchor(centers)
    return [(bx + ux * grid, by + uy * grid) for ux, uy in CONVENTIONS.get(name, [])]

def snap(plate_w, plate_h, centers, margin=8.0, clear=11.0, spread=58.0):
    cands = []
    for x in range(int(margin) + 8, int(plate_w - margin), 3):
        for y in range(int(margin) + 8, int(plate_h - margin), 3):
            if all(math.hypot(x - sx, y - sy) > clear for sx, sy in centers):
                cands.append((x, y))
    picked = []
    for p in cands:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > spread for q in picked):
            picked.append(p)
    return picked


def snap_to_brace(x, y, centers, max_dist=25.0, clear=11.0):
    if all(math.hypot(x - sx, y - sy) > clear for sx, sy in centers):
        return (x, y)
    
    best_p = None
    best_d = float('inf')
    for dx in range(-int(max_dist), int(max_dist) + 1):
        for dy in range(-int(max_dist), int(max_dist) + 1):
            nx, ny = x + dx, y + dy
            if all(math.hypot(nx - sx, ny - sy) > clear for sx, sy in centers):
                d = math.hypot(dx, dy)
                if d < best_d:
                    best_d = d
                    best_p = (nx, ny)
    return best_p

PRESETS = {
    '4corners': four_corners,
    '6perimeter': six_perimeter,
    'grid3x2': lambda w, h, **kw: grid(w, h, 3, 2, **kw),
    'grid4x2': lambda w, h, **kw: grid(w, h, 4, 2, **kw),
    'between_rows': between_rows,
    'poker': poker,
    'snap': snap,
    'gh60': lambda w, h, centers, **kw: convention_place("gh60", centers) + [(bx+ux*GRID, by+uy*GRID) for bx, by in [_anchor(centers)] for ux, uy in EDGE_NOTCHES.get("gh60", [])],
    'skyway96': lambda w, h, centers, **kw: convention_place("skyway96", centers) + [(bx+ux*GRID, by+uy*GRID) for bx, by in [_anchor(centers)] for ux, uy in EDGE_NOTCHES.get("skyway96", [])],
    'kbic65': lambda w, h, centers, **kw: convention_place("kbic65", centers),
    'tkl': lambda w, h, centers, **kw: convention_place("tkl", centers),
}

def custom_from_string(spec, plate_w, plate_h):
    pts = []
    for pair in spec.split(';'):
        pair = pair.strip()
        if not pair:
            continue
        x, y = pair.split(',')
        pts.append((float(x), float(y)))
    return pts
