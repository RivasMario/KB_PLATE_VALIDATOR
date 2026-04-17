#!/usr/bin/env python3
"""
build_plate.py

Generate a keyboard plate DXF from KLE JSON plus (optionally) a KiCad PCB.
Outputs a single DXF with layered geometry:
  - PLATE_OUTLINE: plate perimeter
  - SWITCH_CUTOUTS: per-key switch openings
  - STAB_CUTOUTS: 2u/spacebar stabilizer openings
  - PCB_SCREW_HOLES: mounting holes extracted from KiCad
  - PCB_EDGE_CUTOUTS: edge arc centers extracted from KiCad

Switch/stab cutout polygons are ported from swill/kb_builder (AGPLv3).
"""

import argparse
import json
import math
import re
from pathlib import Path

import ezdxf

try:
    from . import screw_presets
except ImportError:
    import screw_presets


U1 = 19.05  # 1u spacing in mm

STAB_WIDTHS = {
    "300": 19.05, "400": 28.575, "450": 34.671, "550": 42.8625,
    "625": 50.0, "650": 52.38, "700": 57.15,
    "800": 66.675, "900": 66.675, "1000": 66.675,
}

L_OUTLINE = "PLATE_OUTLINE"
L_SWITCH = "SWITCH_CUTOUTS"
L_STAB = "STAB_CUTOUTS"
L_SCREW = "PCB_SCREW_HOLES"
L_EDGE = "PCB_EDGE_CUTOUTS"


# ---------- geometry helpers ----------

def rotate(points, deg, origin=(0.0, 0.0)):
    if not deg:
        return list(points)
    r = math.radians(deg)
    co, si = math.cos(r), math.sin(r)
    ox, oy = origin
    return [
        (co * (x - ox) - si * (y - oy) + ox,
         si * (x - ox) + co * (y - oy) + oy)
        for x, y in points
    ]


def translate(points, dx, dy):
    return [(x + dx, y + dy) for x, y in points]


# ---------- switch cutout polygons (ported from kb_builder) ----------

def switch_points(t, k, grow_x=0.0, grow_y=0.0):
    """Return closed polygon for switch cutout type t at origin."""
    if t == 0:  # plain square
        return [
            (7 - k + grow_x, -7 + k - grow_y),
            (7 - k + grow_x,  7 - k + grow_y),
            (-7 + k - grow_x, 7 - k + grow_y),
            (-7 + k - grow_x, -7 + k - grow_y),
            (7 - k + grow_x, -7 + k - grow_y),
        ]
    if t == 1:  # mx + alps (short side wings)
        return [
            (7 - k, -7 + k), (7 - k, -6.4 + k), (7.8 - k, -6.4 + k),
            (7.8 - k, 6.4 - k), (7 - k, 6.4 - k), (7 - k, 7 - k),
            (-7 + k, 7 - k), (-7 + k, 6.4 - k), (-7.8 + k, 6.4 - k),
            (-7.8 + k, -6.4 + k), (-7 + k, -6.4 + k), (-7 + k, -7 + k),
            (7 - k, -7 + k),
        ]
    if t == 2:  # mx openable (side wings)
        return [
            (7 - k, -7 + k), (7 - k, -6 + k), (7.8 - k, -6 + k),
            (7.8 - k, -2.9 - k), (7 - k, -2.9 - k), (7 - k, 2.9 + k),
            (7.8 - k, 2.9 + k), (7.8 - k, 6 - k), (7 - k, 6 - k),
            (7 - k, 7 - k), (-7 + k, 7 - k), (-7 + k, 6 - k),
            (-7.8 + k, 6 - k), (-7.8 + k, 2.9 + k), (-7 + k, 2.9 + k),
            (-7 + k, -2.9 - k), (-7.8 + k, -2.9 - k), (-7.8 + k, -6 + k),
            (-7 + k, -6 + k), (-7 + k, -7 + k), (7 - k, -7 + k),
        ]
    if t == 3:  # mx rotatable (side + top/bottom wings)
        return [
            (7 - k, -7 + k), (7 - k, -6 + k), (7.8 - k, -6 + k),
            (7.8 - k, -2.9 - k), (7 - k, -2.9 - k), (7 - k, 2.9 + k),
            (7.8 - k, 2.9 + k), (7.8 - k, 6 - k), (7 - k, 6 - k),
            (7 - k, 7 - k), (6 - k, 7 - k), (6 - k, 7.8 - k),
            (2.9 + k, 7.8 - k), (2.9 + k, 7 - k), (-2.9 - k, 7 - k),
            (-2.9 - k, 7.8 - k), (-6 + k, 7.8 - k), (-6 + k, 7 - k),
            (-7 + k, 7 - k), (-7 + k, 6 - k), (-7.8 + k, 6 - k),
            (-7.8 + k, 2.9 + k), (-7 + k, 2.9 + k), (-7 + k, -2.9 - k),
            (-7.8 + k, -2.9 - k), (-7.8 + k, -6 + k), (-7 + k, -6 + k),
            (-7 + k, -7 + k), (-6 + k, -7 + k), (-6 + k, -7.8 + k),
            (-2.9 - k, -7.8 + k), (-2.9 - k, -7 + k), (2.9 + k, -7 + k),
            (2.9 + k, -7.8 + k), (6 - k, -7.8 + k), (6 - k, -7 + k),
            (7 - k, -7 + k),
        ]
    return switch_points(0, k, grow_x, grow_y)


# ---------- stabilizer cutout polygons (ported from kb_builder) ----------

def stab_2u(s, k):
    """2u stab cutouts. Returns list of polygons (1 for cherry, 2 for costar)."""
    if s == 0:  # cherry modded for costar
        return [[
            (7 - k, -7 + k), (7 - k, -4.73 + k), (8.575 + k, -4.73 + k),
            (8.575 + k, -5.53 + k), (10.3 + k, -5.53 + k), (10.3 + k, -6.45 + k),
            (13.6 - k, -6.45 + k), (13.6 - k, -5.53 + k), (15.225 - k, -5.53 + k),
            (15.225 - k, -2.3 + k), (16.1 - k, -2.3 + k), (16.1 - k, 0.5 - k),
            (15.225 - k, 0.5 - k), (15.225 - k, 6.77 - k), (13.6 - k, 6.77 - k),
            (13.6 - k, 7.75 - k), (10.3 + k, 7.75 - k), (10.3 + k, 6.77 - k),
            (8.575 + k, 6.77 - k), (8.575 + k, 5.97 - k), (7 - k, 5.97 - k),
            (7 - k, 7 - k), (-7 + k, 7 - k), (-7 + k, 5.97 - k),
            (-8.575 - k, 5.97 - k), (-8.575 - k, 6.77 - k), (-10.3 - k, 6.77 - k),
            (-10.3 - k, 7.75 - k), (-13.6 + k, 7.75 - k), (-13.6 + k, 6.77 - k),
            (-15.225 + k, 6.77 - k), (-15.225 + k, 0.5 - k), (-16.1 + k, 0.5 - k),
            (-16.1 + k, -2.3 + k), (-15.225 + k, -2.3 + k),
            (-15.225 + k, -5.53 + k), (-13.6 + k, -5.53 + k),
            (-13.6 + k, -6.45 + k), (-10.3 - k, -6.45 + k), (-10.3 - k, -5.53 + k),
            (-8.575 - k, -5.53 + k), (-8.575 - k, -4.73 + k), (-7 + k, -4.73 + k),
            (-7 + k, -7 + k), (7 - k, -7 + k),
        ]]
    if s == 1:  # cherry spec only
        return [[
            (7 - k, -7 + k), (7 - k, -4.73 + k), (8.575 + k, -4.73 + k),
            (8.575 + k, -5.53 + k), (15.225 - k, -5.53 + k),
            (15.225 - k, -2.3 + k), (16.1 - k, -2.3 + k), (16.1 - k, 0.5 - k),
            (15.225 - k, 0.5 - k), (15.225 - k, 6.77 - k), (13.6 - k, 6.77 - k),
            (13.6 - k, 7.97 - k), (10.3 + k, 7.97 - k), (10.3 + k, 6.77 - k),
            (8.575 + k, 6.77 - k), (8.575 + k, 5.97 - k), (7 - k, 5.97 - k),
            (7 - k, 7 - k), (-7 + k, 7 - k), (-7 + k, 5.97 - k),
            (-8.575 - k, 5.97 - k), (-8.575 - k, 6.77 - k), (-10.3 - k, 6.77 - k),
            (-10.3 - k, 7.97 - k), (-13.6 + k, 7.97 - k), (-13.6 + k, 6.77 - k),
            (-15.225 + k, 6.77 - k), (-15.225 + k, 0.5 - k), (-16.1 + k, 0.5 - k),
            (-16.1 + k, -2.3 + k), (-15.225 + k, -2.3 + k),
            (-15.225 + k, -5.53 + k), (-8.575 - k, -5.53 + k),
            (-8.575 - k, -4.73 + k), (-7 + k, -4.73 + k), (-7 + k, -7 + k),
            (7 - k, -7 + k),
        ]]
    if s == 2:  # costar only
        return [
            [(-10.3 - k, -6.45 + k), (-13.6 + k, -6.45 + k),
             (-13.6 + k, 7.75 - k), (-10.3 - k, 7.75 - k),
             (-10.3 - k, -6.45 + k)],
            [(10.3 + k, -6.45 + k), (13.6 - k, -6.45 + k),
             (13.6 - k, 7.75 - k), (10.3 + k, 7.75 - k),
             (10.3 + k, -6.45 + k)],
        ]
    return []


def stab_space(s, k, x):
    """Spacebar/3u+ stab cutouts. x = stabilizer offset from key center (mm)."""
    if s == 0:  # cherry modded for costar
        return [[
            (7 - k, -7 + k), (7 - k, -2.3 + k), (x - 3.325 + k, -2.3 + k),
            (x - 3.325 + k, -5.53 + k), (x - 1.65 + k, -5.53 + k),
            (x - 1.65 + k, -6.45 + k), (x + 1.65 - k, -6.45 + k),
            (x + 1.65 - k, -5.53 + k), (x + 3.325 - k, -5.53 + k),
            (x + 3.325 - k, -2.3 + k), (x + 4.2 - k, -2.3 + k), (x + 4.2 - k, 0.5 - k),
            (x + 3.325 - k, 0.5 - k), (x + 3.325 - k, 6.77 - k),
            (x + 1.65 - k, 6.77 - k), (x + 1.65 - k, 7.75 - k), (x - 1.65 + k, 7.75 - k),
            (x - 1.65 + k, 6.77 - k), (x - 3.325 + k, 6.77 - k),
            (x - 3.325 + k, 2.3 - k), (7 - k, 2.3 - k), (7 - k, 7 - k), (-7 + k, 7 - k),
            (-7 + k, 2.3 - k), (-x + 3.325 - k, 2.3 - k), (-x + 3.325 - k, 6.77 - k),
            (-x + 1.65 - k, 6.77 - k), (-x + 1.65 - k, 7.75 - k),
            (-x - 1.65 + k, 7.75 - k), (-x - 1.65 + k, 6.77 - k),
            (-x - 3.325 + k, 6.77 - k), (-x - 3.325 + k, 0.5 - k),
            (-x - 4.2 + k, 0.5 - k), (-x - 4.2 + k, -2.3 + k),
            (-x - 3.325 + k, -2.3 + k), (-x - 3.325 + k, -5.53 + k),
            (-x - 1.65 + k, -5.53 + k), (-x - 1.65 + k, -6.45 + k),
            (-x + 1.65 - k, -6.45 + k), (-x + 1.65 - k, -5.53 + k),
            (-x + 3.325 - k, -5.53 + k), (-x + 3.325 - k, -2.3 + k),
            (-7 + k, -2.3 + k), (-7 + k, -7 + k), (7 - k, -7 + k),
        ]]
    if s == 1:  # cherry spec
        return [[
            (7 - k, -7 + k), (7 - k, -2.3 + k), (x - 3.325 + k, -2.3 + k),
            (x - 3.325 + k, -5.53 + k), (x + 3.325 - k, -5.53 + k),
            (x + 3.325 - k, -2.3 + k), (x + 4.2 - k, -2.3 + k), (x + 4.2 - k, 0.5 - k),
            (x + 3.325 - k, 0.5 - k), (x + 3.325 - k, 6.77 - k),
            (x + 1.65 - k, 6.77 - k), (x + 1.65 - k, 7.97 - k), (x - 1.65 + k, 7.97 - k),
            (x - 1.65 + k, 6.77 - k), (x - 3.325 + k, 6.77 - k),
            (x - 3.325 + k, 2.3 - k), (7 - k, 2.3 - k), (7 - k, 7 - k), (-7 + k, 7 - k),
            (-7 + k, 2.3 - k), (-x + 3.325 - k, 2.3 - k), (-x + 3.325 - k, 6.77 - k),
            (-x + 1.65 - k, 6.77 - k), (-x + 1.65 - k, 7.97 - k),
            (-x - 1.65 + k, 7.97 - k), (-x - 1.65 + k, 6.77 - k),
            (-x - 3.325 + k, 6.77 - k), (-x - 3.325 + k, 0.5 - k),
            (-x - 4.2 + k, 0.5 - k), (-x - 4.2 + k, -2.3 + k),
            (-x - 3.325 + k, -2.3 + k), (-x - 3.325 + k, -5.53 + k),
            (-x + 3.325 - k, -5.53 + k), (-x + 3.325 - k, -2.3 + k),
            (-7 + k, -2.3 + k), (-7 + k, -7 + k), (7 - k, -7 + k),
        ]]
    if s == 2:  # costar only
        return [
            [(-x + 1.65 - k, -6.45 + k), (-x - 1.65 + k, -6.45 + k),
             (-x - 1.65 + k, 7.75 - k), (-x + 1.65 - k, 7.75 - k),
             (-x + 1.65 - k, -6.45 + k)],
            [(x - 1.65 + k, -6.45 + k), (x + 1.65 - k, -6.45 + k),
             (x + 1.65 - k, 7.75 - k), (x - 1.65 + k, 7.75 - k),
             (x - 1.65 + k, -6.45 + k)],
        ]
    return []


# ---------- KLE parser ----------

def parse_kle(layout):
    """Walk KLE JSON; return (keys, plate_w_u, plate_h_u) in 1u units.

    Output convention: Y grows UP (DXF standard). Row 0 of KLE ends up at
    the top of the plate (high Y); last row at the bottom (low Y).
    """
    keys = []
    cur_y = 0.0
    plate_w = 0.0
    pending = None
    for row in layout:
        if isinstance(row, dict):
            continue
        if not isinstance(row, list):
            continue
        cur_x = 0.0
        row_h = 1.0
        for item in row:
            if isinstance(item, dict):
                pending = dict(item) if pending is None else {**pending, **item}
                if 'x' in item:
                    cur_x += item['x']
                if 'y' in item:
                    cur_y += item['y']
                continue
            w = (pending or {}).get('w', 1)
            h = (pending or {}).get('h', 1)
            keys.append({
                'cx_u': cur_x + w / 2.0,
                'cy_u_down': cur_y + h / 2.0,
                'w': w,
                'h': h,
                '_t': (pending or {}).get('_t'),
                '_s': (pending or {}).get('_s'),
                '_r': (pending or {}).get('_r', 0),
                '_rs': (pending or {}).get('_rs', 0),
                '_k': (pending or {}).get('_k'),
            })
            cur_x += w
            if h > row_h:
                row_h = h
            pending = None
        if cur_x > plate_w:
            plate_w = cur_x
        cur_y += 1.0
    plate_h = cur_y
    for k in keys:
        k['cy_u'] = plate_h - k.pop('cy_u_down')
    return keys, plate_w, plate_h


# ---------- plate assembly ----------

def build_entities(keys, plate_w_u, plate_h_u, *,
                   pad=0.0, kerf=0.0, switch_type=1, stab_type=0):
    ents = {L_OUTLINE: [], L_SWITCH: [], L_STAB: []}
    W = plate_w_u * U1 + 2 * pad
    H = plate_h_u * U1 + 2 * pad
    ents[L_OUTLINE].append([(0, 0), (W, 0), (W, H), (0, H), (0, 0)])

    k_default = kerf / 2.0

    for key in keys:
        cx = key['cx_u'] * U1 + pad
        cy = key['cy_u'] * U1 + pad
        w, h = key['w'], key['h']
        k = (key['_k'] / 2.0) if key.get('_k') is not None else k_default
        t = key['_t'] if key.get('_t') is not None else switch_type
        s = key['_s'] if key.get('_s') is not None else stab_type
        r = key.get('_r', 0)
        rs = key.get('_rs', 0)
        rotate_stab = h > w

        stab_polys = []
        if (2 <= w < 3) or (rotate_stab and 2 <= h < 3):
            stab_polys = stab_2u(s, k)
        elif w >= 3 or (rotate_stab and h >= 3):
            l = h if rotate_stab else w
            s_str = str(l).replace('.', '')
            s_str = s_str.ljust(4 if l >= 10 else 3, '0')
            x_off = STAB_WIDTHS.get(s_str, 11.95)
            stab_polys = stab_space(s, k, x_off)

        # Cherry-mode stab polygons (s=0 cherry+costar, s=1 cherry) already
        # include the switch cutout as part of their combined outline.
        # Drawing a separate switch square inside creates overlapping closed
        # polygons; SCS applies even-odd fill and the overlap region becomes
        # "material remains" while the single-coverage stab wings become
        # "hole" — exactly reversed from intent. Only emit switch_points
        # when no combined stab or for Costar (s=2, two separate stab rects).
        needs_switch_cutout = not stab_polys or s == 2
        if needs_switch_cutout:
            pts = switch_points(t, k)
            if r:
                pts = rotate(pts, r)
            ents[L_SWITCH].append(translate(pts, cx, cy))

        for poly in stab_polys:
            if rotate_stab:
                poly = rotate(poly, 90)
            if rs:
                poly = rotate(poly, rs)
            ents[L_STAB].append(translate(poly, cx, cy))

    return ents


# ---------- PCB extraction (shared with validator) ----------

def find_kicad_screw_holes(kicad_path):
    content = Path(kicad_path).read_text()
    pat = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(pat, content, re.DOTALL)]


def find_kicad_switches(kicad_path):
    """Return list of (x, y) for every hotswap / plain switch footprint."""
    content = Path(kicad_path).read_text()
    pat = (r'\(footprint\s+"[^"]*SW_[^"]*"'
           r'[^\(]*?\(layer[^\)]+\)'
           r'[^\(]*?\(uuid[^\)]+\)'
           r'\s*\(at\s+([-\d.]+)\s+([-\d.]+)')
    return [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(pat, content)]


def find_edge_cutouts(kicad_path):
    """Return list of {'start', 'mid', 'end'} dicts for inward-bowing arcs
    on the KiCad Edge.Cuts layer."""
    content = Path(kicad_path).read_text()
    arc_re = (
        r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)'
        r'\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)'
        r'\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)'
        r'.*?\(layer "Edge\.Cuts"'
    )
    arcs = []
    for m in re.finditer(arc_re, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = (float(m.group(i)) for i in range(1, 7))
        arcs.append({'start': (x1, y1), 'mid': (xm, ym), 'end': (x2, y2)})
    if not arcs:
        return []

    all_pts = [p for a in arcs for p in (a['start'], a['mid'], a['end'])]
    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)

    cutouts = []
    for a in arcs:
        (x1, y1), (xm, ym), (x2, y2) = a['start'], a['mid'], a['end']
        near_left = abs(x1 - min_x) < 5 and abs(x2 - min_x) < 5
        near_right = abs(x1 - max_x) < 5 and abs(x2 - max_x) < 5
        near_bot = abs(y1 - min_y) < 5 and abs(y2 - min_y) < 5
        near_top = abs(y1 - max_y) < 5 and abs(y2 - max_y) < 5
        bows_in = (
            (near_left and xm - min_x >= 2) or
            (near_right and max_x - xm >= 2) or
            (near_bot and ym - min_y >= 2) or
            (near_top and max_y - ym >= 2)
        )
        if bows_in:
            cutouts.append(a)
    return cutouts


def find_all_edge_cuts(kicad_path):
    """Return all segments on Edge.Cuts as list of ('line', p1, p2) or
    ('arc', s, m, e)."""
    content = Path(kicad_path).read_text()
    line_re = (
        r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)'
        r'\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)'
        r'.*?\(layer "Edge\.Cuts"'
    )
    arc_re = (
        r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)'
        r'\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)'
        r'\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)'
        r'.*?\(layer "Edge\.Cuts"'
    )
    segs = []
    for m in re.finditer(line_re, content, re.DOTALL):
        p1 = (float(m.group(1)), float(m.group(2)))
        p2 = (float(m.group(3)), float(m.group(4)))
        segs.append(('line', p1, p2))
    for m in re.finditer(arc_re, content, re.DOTALL):
        s = (float(m.group(1)), float(m.group(2)))
        m_ = (float(m.group(3)), float(m.group(4)))
        e = (float(m.group(5)), float(m.group(6)))
        segs.append(('arc', s, m_, e))
    return segs


def transform_arc(arc, apply_fn):
    return {k: apply_fn([arc[k]])[0] for k in ('start', 'mid', 'end')}


def transform_segment(seg, apply_fn):
    if seg[0] == 'line':
        return ('line', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0])
    if seg[0] == 'arc':
        return ('arc', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0],
                apply_fn([seg[3]])[0])
    return seg


def discretize_segments(segs, steps=50):
    """Convert list of segments to a list of points (approximate polygon)."""
    pts = []
    for seg in segs:
        if seg[0] == 'line':
            pts.append(seg[1])
        elif seg[0] == 'arc':
            s, m, e = seg[1], seg[2], seg[3]
            res = arc_from_3pts(s, m, e)
            if res:
                center, radius, a_start, a_end = res
                # handle wrap around? ezdxf arc is CCW.
                # we need to ensure we go from a_start to a_end through m
                if a_end < a_start:
                    a_end += 360
                for i in range(steps):
                    ang = math.radians(a_start + (a_end - a_start) * i / steps)
                    pts.append((center[0] + radius * math.cos(ang),
                                center[1] + radius * math.sin(ang)))
            else:
                pts.append(s)
    if segs:
        # add the very last point
        last = segs[-1]
        pts.append(last[2] if last[0] == 'line' else last[3])
    return pts


def classify_arc_side(arc, W, H):
    """Return 'bottom'|'right'|'top'|'left' based on arc average position."""
    pts = [arc['start'], arc['mid'], arc['end']]
    avg_x = sum(p[0] for p in pts) / 3.0
    avg_y = sum(p[1] for p in pts) / 3.0
    dists = {'bottom': avg_y, 'top': H - avg_y,
             'left': avg_x, 'right': W - avg_x}
    return min(dists, key=dists.get)


def arc_from_3pts(p1, p2, p3):
    """Circle through 3 points. Returns (center, radius, start_deg, end_deg)
    for ezdxf CCW arc from start_deg to end_deg passing through p2."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) +
          (bx * bx + by * by) * (cy - ay) +
          (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) +
          (bx * bx + by * by) * (ax - cx) +
          (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a_start = math.degrees(math.atan2(ay - uy, ax - ux))
    a_end = math.degrees(math.atan2(cy - uy, cx - ux))
    cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if cross < 0:
        a_start, a_end = a_end, a_start
    return (ux, uy), r, a_start, a_end


def build_outline_segments(W, H, arcs, fillet=0.0):
    """Walk CCW around the plate. Insert arcs (as U-cuts) on the edge they
    belong to. Returns list of ('line', p1, p2) and ('arc', s, m, e) segments."""
    by_side = {'bottom': [], 'right': [], 'top': [], 'left': []}
    for a in arcs:
        by_side[classify_arc_side(a, W, H)].append(a)

    r = fillet
    # Perimeter walk CCW: Bottom -> Right -> Top -> Left
    edge_walks = [
        ('bottom', (r, 0.0), (W - r, 0.0)),
        ('right',  (W, r),   (W, H - r)),
        ('top',    (W - r, H), (r, H)),
        ('left',   (0, H - r), (0, r)),
    ]
    
    s45 = math.sin(math.radians(45))
    c45 = math.cos(math.radians(45))
    # Corner arcs to be inserted BETWEEN edge walks
    # BR: after bottom, before right. Center (W-r, r)
    # TR: after right, before top. Center (W-r, H-r)
    # TL: after top, before left. Center (r, H-r)
    # BL: after left, before bottom. Center (r, r)
    corners = {
        'br': ('arc', (W-r, 0), (W-r+r*c45, r-r*s45), (W, r)),
        'tr': ('arc', (W, H-r), (W-r+r*c45, H-r+r*s45), (W-r, H)),
        'tl': ('arc', (r, H), (r-r*c45, H-r+r*s45), (0, H-r)),
        'bl': ('arc', (0, r), (r-r*c45, r-r*s45), (r, 0)),
    }

    segs = []
    for i, (side, p1, p2) in enumerate(edge_walks):
        arcs_here = by_side[side]
        # Sort arcs along travel direction
        if side == 'bottom':
            arcs_here.sort(key=lambda a: min(a['start'][0], a['end'][0]))
        elif side == 'right':
            arcs_here.sort(key=lambda a: min(a['start'][1], a['end'][1]))
        elif side == 'top':
            arcs_here.sort(key=lambda a: -max(a['start'][0], a['end'][0]))
        else:  # left
            arcs_here.sort(key=lambda a: -max(a['start'][1], a['end'][1]))

        cursor = p1
        for a in arcs_here:
            s, m, e = a['start'], a['mid'], a['end']
            ds = math.hypot(s[0] - cursor[0], s[1] - cursor[1])
            de = math.hypot(e[0] - cursor[0], e[1] - cursor[1])
            entry, exit_ = (s, e) if ds <= de else (e, s)
            # Project entry/exit onto plate edge for U-shaped notch
            if side == 'bottom':
                edge_entry = (entry[0], 0.0)
                edge_exit = (exit_[0], 0.0)
            elif side == 'top':
                edge_entry = (entry[0], H)
                edge_exit = (exit_[0], H)
            elif side == 'left':
                edge_entry = (0.0, entry[1])
                edge_exit = (0.0, exit_[1])
            else:  # right
                edge_entry = (W, entry[1])
                edge_exit = (W, exit_[1])
            segs.append(('line', cursor, edge_entry))
            segs.append(('line', edge_entry, entry))
            segs.append(('arc', entry, m, exit_))
            segs.append(('line', exit_, edge_exit))
            cursor = edge_exit
        segs.append(('line', cursor, p2))
        
        # Add corner arc
        if r > 0:
            if side == 'bottom': segs.append(corners['br'])
            elif side == 'right': segs.append(corners['tr'])
            elif side == 'top': segs.append(corners['tl'])
            elif side == 'left': segs.append(corners['bl'])
            
    return segs


def snap_screws_to_grid(screws, key_centers, row_tol=4.0, max_shift=5.0):
    """For each screw, snap X to midpoint between the two nearest key columns
    on the same row (same Y within row_tol). Skip if target is > max_shift
    away (screw is near a wide key like spacebar, handled differently)."""
    snapped = []
    for sx, sy in screws:
        row = [kx for (kx, ky) in key_centers if abs(ky - sy) < row_tol]
        if len(row) < 2:
            snapped.append((sx, sy))
            continue
        row.sort()
        left = max((x for x in row if x <= sx), default=None)
        right = min((x for x in row if x >= sx), default=None)
        if left is None or right is None:
            snapped.append((sx, sy))
            continue
        target = (left + right) / 2.0
        if abs(target - sx) <= max_shift:
            snapped.append((target, sy))
        else:
            snapped.append((sx, sy))
    return snapped


def apply_pcb_transform(points, mirror_y=None, dx=0.0, dy=0.0):
    out = []
    for x, y in points:
        if mirror_y is not None:
            y = mirror_y - (y - mirror_y)
        out.append((x + dx, y + dy))
    return out


# ---------- validator ----------

def point_in_polygon(x, y, poly):
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def min_dist_to_polygon(x, y, poly):
    best = float('inf')
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        dx, dy = x2 - x1, y2 - y1
        denom = dx * dx + dy * dy
        if denom < 1e-12:
            d = math.hypot(x - x1, y - y1)
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / denom))
            nx, ny = x1 + t * dx, y1 + t * dy
            d = math.hypot(x - nx, y - ny)
        if d < best:
            best = d
    return best


def validate_screws(screws, screw_radius, outline, cutouts, clearance=0.5):
    """Return list of issues (idx, kind, distance)."""
    issues = []
    for i, (sx, sy) in enumerate(screws):
        if not point_in_polygon(sx, sy, outline):
            issues.append((i, 'outside_plate', 0.0))
            continue
        # edge clearance to plate outline
        d_edge = min_dist_to_polygon(sx, sy, outline)
        if d_edge < screw_radius + clearance:
            issues.append((i, 'too_close_edge', d_edge))
            continue
        hit = False
        for j, cut in enumerate(cutouts):
            if point_in_polygon(sx, sy, cut):
                issues.append((i, f'inside_cutout#{j}', 0.0))
                hit = True
                break
            d = min_dist_to_polygon(sx, sy, cut)
            if d < screw_radius + clearance:
                issues.append((i, f'too_close_cutout#{j}', d))
                hit = True
                break
        if hit:
            continue
    return issues


# ---------- alignment solver ----------

def _transform_points(points, flip_x, flip_y, rot_deg):
    out = []
    for x, y in points:
        if flip_x:
            x = -x
        if flip_y:
            y = -y
        if rot_deg:
            r = math.radians(rot_deg)
            co, si = math.cos(r), math.sin(r)
            x, y = co * x - si * y, si * x + co * y
        out.append((x, y))
    return out


def _bbox_center(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def _nearest_neighbor_score(src, tgt):
    """Sum of distance from each src point to nearest tgt point."""
    total = 0.0
    for x, y in src:
        best = float('inf')
        for tx, ty in tgt:
            d = (x - tx) ** 2 + (y - ty) ** 2
            if d < best:
                best = d
        total += math.sqrt(best)
    return total


def solve_pcb_transform(pcb_switches, kle_switches):
    """Find best rigid transform (flip + rotate + translate) mapping PCB
    switch centers onto KLE switch centers. Returns (params, apply_fn)."""
    if not pcb_switches or not kle_switches:
        return None, (lambda pts: list(pts))

    best = None
    # Try all 8 symmetries
    for flip_x in (False, True):
        for flip_y in (False, True):
            for rot in (0, 90, 180, 270):
                t_base = _transform_points(pcb_switches, flip_x, flip_y, rot)
                
                # Candidate translations: match a few landmark PCB switches
                # to every possible KLE switch center.
                landmarks = [0, len(t_base)//2, len(t_base)-1]
                for l_idx in landmarks:
                    lp = t_base[l_idx]
                    for kp in kle_switches:
                        tx = kp[0] - lp[0]
                        ty = kp[1] - lp[1]
                        
                        # Score: nearest neighbor sum
                        score = 0.0
                        for sx, sy in t_base:
                            px, py = sx + tx, sy + ty
                            min_d2 = float('inf')
                            for kx, ky in kle_switches:
                                d2 = (px - kx)**2 + (py - ky)**2
                                if d2 < min_d2:
                                    min_d2 = d2
                            score += math.sqrt(min_d2)
                        
                        if best is None or score < best[0]:
                            best = (score, {'flip_x': flip_x, 'flip_y': flip_y,
                                            'rot': rot, 'dx': tx, 'dy': ty})
    score, params = best

    def apply(pts):
        t = _transform_points(pts, params['flip_x'], params['flip_y'],
                              params['rot'])
        return [(x + params['dx'], y + params['dy']) for x, y in t]

    params['nn_score'] = score
    return params, apply


# ---------- DXF writer ----------

def emit_dxf(out_path, ents, screw_holes=None, outline_segments=None,
             screw_radius=1.2):
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    colors = {L_OUTLINE: 7, L_SWITCH: 3, L_STAB: 4, L_SCREW: 1}
    for name in [L_OUTLINE, L_SWITCH, L_STAB, L_SCREW]:
        if name not in doc.layers:
            doc.layers.add(name, color=colors[name])

    # Plate outline: use LWPOLYLINE with bulge for arcs
    if outline_segments is not None:
        # try to build a single closed loop if segments are connected
        # for now, add them one by one but using bulges for arcs
        for seg in outline_segments:
            if seg[0] == 'line':
                msp.add_lwpolyline([seg[1], seg[2]], dxfattribs={'layer': L_OUTLINE})
            elif seg[0] == 'arc':
                res = arc_from_3pts(seg[1], seg[2], seg[3])
                if res:
                    center, radius, a_start, a_end = res
                    sweep = a_end - a_start
                    if sweep < 0: sweep += 360
                    # bulge = tan(sweep_angle / 4)
                    bulge = math.tan(math.radians(sweep) / 4.0)
                    msp.add_lwpolyline([(seg[1][0], seg[1][1], 0, 0, bulge),
                                        (seg[3][0], seg[3][1])],
                                       dxfattribs={'layer': L_OUTLINE})
                else:
                    msp.add_lwpolyline([seg[1], seg[3]], dxfattribs={'layer': L_OUTLINE})
    else:
        for pts in ents.get(L_OUTLINE, []):
            if len(pts) >= 2 and pts[0] == pts[-1]:
                pts = pts[:-1]
            msp.add_lwpolyline(pts, close=True,
                               dxfattribs={'layer': L_OUTLINE})

    # Switch + stab cutouts. Strip duplicate closing point: kb_builder polys
    # start and end on the same vertex, but add_lwpolyline(close=True) will
    # emit its own closing segment — leaving the dup creates a zero-length
    # edge that SendCutSend flags as an "open entity".
    for layer in (L_SWITCH, L_STAB):
        for pts in ents.get(layer, []):
            if len(pts) >= 2 and pts[0] == pts[-1]:
                pts = pts[:-1]
            msp.add_lwpolyline(pts, close=True, dxfattribs={'layer': layer})

    for x, y in (screw_holes or []):
        msp.add_circle((x, y), screw_radius, dxfattribs={'layer': L_SCREW})

    doc.saveas(out_path)


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument('--kle', required=True, help='KLE JSON layout file')
    ap.add_argument('--out', required=True, help='Output DXF path')
    ap.add_argument('--pcb', help='KiCad PCB file (optional)')
    ap.add_argument('--switch-type', type=int, default=1, choices=[0, 1, 2, 3])
    ap.add_argument('--stab-type', type=int, default=0, choices=[0, 1, 2])
    ap.add_argument('--kerf', type=float, default=0.0,
                    help='Laser kerf compensation (mm)')
    ap.add_argument('--pad', type=float, default=0.0,
                    help='Plate padding around keys (mm). Typical 96%% cases '
                         'want 0-1mm. Use 0 for edge-aligned plates, 1 for '
                         'slight clearance. Larger values (3-5) only needed '
                         'if case has oversized pocket.')
    ap.add_argument('--screw-diameter', type=float, default=2.4,
                    help='Plate mounting hole diameter (mm). '
                         '2.4 = M2 free-fit (install slop). '
                         '2.2 = close-fit (matches PCB exactly). '
                         '2.6 = coarse/loose.')
    ap.add_argument('--pcb-dx', type=float, default=0.0,
                    help='Manual X nudge after auto-align (mm)')
    ap.add_argument('--pcb-dy', type=float, default=0.0,
                    help='Manual Y nudge after auto-align (mm)')
    ap.add_argument('--no-auto-align', action='store_true',
                    help='Skip brute-force alignment; use raw KiCad coords')
    ap.add_argument('--clearance', type=float, default=0.5,
                    help='Min clearance from screw edge to cutout edge (mm)')
    ap.add_argument('--snap-screws', action='store_true',
                    help='Snap each screw X to midpoint between nearest two '
                         'key columns on same row (fixes local PCB-vs-KLE drift)')
    ap.add_argument('--fillet', type=float, default=0.0,
                    help='Corner fillet radius for plate outline (mm)')
    ap.add_argument('--screw-preset', choices=list(screw_presets.PRESETS.keys()),
                    help='Use a predefined screw position template (KLE-only mode)')
    ap.add_argument('--screw-custom',
                    help='Semicolon-separated list of x,y coordinates '
                         '(e.g. "5,5;350,5;175,110")')
    ap.add_argument('--screw-inset', type=float, default=5.0,
                    help='Inset distance from plate edge for presets (mm)')
    args = ap.parse_args()

    layout = json.loads(Path(args.kle).read_text(encoding='utf-8'))
    keys, w_u, h_u = parse_kle(layout)
    ents = build_entities(
        keys, w_u, h_u,
        pad=args.pad, kerf=args.kerf,
        switch_type=args.switch_type, stab_type=args.stab_type,
    )

    plate_w = w_u * U1 + 2 * args.pad
    plate_h = h_u * U1 + 2 * args.pad
    outline = ents[L_OUTLINE][0]
    cutouts = ents[L_SWITCH] + ents[L_STAB]
    screw_radius = args.screw_diameter / 2.0

    screws = None
    edge_arcs = []
    params = None
    issues = []

    # 1. Source screws (Custom > Preset > PCB)
    if args.screw_custom:
        screws = screw_presets.custom_from_string(args.screw_custom, plate_w, plate_h)
    elif args.screw_preset:
        fn = screw_presets.PRESETS[args.screw_preset]
        if args.screw_preset == 'between_rows':
            screws = fn(keys, plate_w, args.pad, args.screw_inset, U1)
        else:
            screws = fn(plate_w, plate_h, inset=args.screw_inset)
    elif args.pcb:
        screws = find_kicad_screw_holes(args.pcb)
        edge_arcs = find_edge_cutouts(args.pcb)
        pcb_switches = find_kicad_switches(args.pcb)
        kle_switches = [(k['cx_u'] * U1 + args.pad, k['cy_u'] * U1 + args.pad)
                        for k in keys]

        if args.no_auto_align:
            nudge = lambda pts: [(x + args.pcb_dx, y + args.pcb_dy)
                                 for x, y in pts]
            screws = nudge(screws)
            edge_arcs = [transform_arc(a, nudge) for a in edge_arcs]
        else:
            params, apply = solve_pcb_transform(pcb_switches, kle_switches)
            nudged_apply = lambda pts: [(x + args.pcb_dx, y + args.pcb_dy)
                                        for x, y in apply(pts)]
            screws = nudged_apply(screws)
            edge_arcs = [transform_arc(a, nudged_apply) for a in edge_arcs]

        if args.snap_screws:
            screws = snap_screws_to_grid(screws, kle_switches)

    # 2. Validate (if any screws exist)
    if screws:
        issues = validate_screws(screws, screw_radius, outline, cutouts,
                                 args.clearance)

    # 3. Build outline segments (PCB Edge.Cuts > Rect + Notches)
    outline_segments = None
    if args.pcb:
        pcb_outline = find_all_edge_cuts(args.pcb)
        if pcb_outline:
            nudged_apply = lambda pts: [(x + args.pcb_dx, y + args.pcb_dy)
                                        for x, y in apply(pts)]
            outline_segments = [transform_segment(seg, nudged_apply)
                                for seg in pcb_outline]
            # Re-validate with the real PCB outline if possible
            real_outline = discretize_segments(outline_segments)
            if real_outline:
                outline = real_outline
                if screws:
                    issues = validate_screws(screws, screw_radius, outline,
                                             cutouts, args.clearance)
        else:
            outline_segments = build_outline_segments(plate_w, plate_h, edge_arcs,
                                                      fillet=args.fillet)
    else:
        # KLE-only mode: use rectangle (with optional fillets and custom notches)
        outline_segments = build_outline_segments(plate_w, plate_h, edge_arcs,
                                                  fillet=args.fillet)

    emit_dxf(
        args.out, ents,
        screw_holes=screws,
        outline_segments=outline_segments,
        screw_radius=screw_radius,
    )

    print(f"keys={len(keys)} "
          f"plate={plate_w:.2f}x{plate_h:.2f}mm "
          f"screws={len(screws or [])} edge_notches={len(edge_arcs)} "
          f"-> {args.out}")
    if params is not None:
        print(f"align: flip_x={params['flip_x']} flip_y={params['flip_y']} "
              f"rot={params['rot']} dx={params['dx']:.2f} dy={params['dy']:.2f} "
              f"nn_score={params.get('nn_score', 0):.2f}mm")
    if issues:
        print(f"VALIDATOR: {len(issues)} issue(s):")
        for i, kind, d in issues[:20]:
            print(f"  screw#{i} {kind} dist={d:.2f}mm")
        raise SystemExit(1)
    elif args.pcb:
        print("VALIDATOR: all screws inside plate, none overlapping cutouts")


if __name__ == '__main__':
    main()
