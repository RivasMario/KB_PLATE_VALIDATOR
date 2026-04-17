#!/usr/bin/env python3
"""
build_plate.py

Generate a keyboard plate DXF from KLE JSON plus (optionally) a KiCad PCB.
Outputs a single DXF with layered geometry and an SVG preview.
"""

import argparse
import json
import math
import re
from pathlib import Path

import ezdxf
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely import affinity
from shapely.ops import unary_union

try:
    from . import screw_presets
except ImportError:
    import screw_presets

try:
    from . import cutouts as cutout_registry
except ImportError:
    import cutouts as cutout_registry


U1 = 19.05

STAB_WIDTHS = {
    "300": 19.05, "400": 28.575, "450": 34.671, "550": 42.8625,
    "625": 50.0, "650": 52.38, "700": 57.15,
    "800": 66.675, "900": 66.675, "1000": 66.675,
}

L_OUTLINE = "PLATE_OUTLINE"
L_SWITCH = "SWITCH_CUTOUTS"
L_STAB = "STAB_CUTOUTS"
L_SCREW = "PCB_SCREW_HOLES"


def parse_kle(layout):
    """
    Robust KLE parser matching official specification.
    KLE rotation is clockwise. Trig is counter-clockwise.
    """
    keys = []
    rx, ry, r = 0.0, 0.0, 0.0
    kx, ky = 0.0, 0.0
    pending = None
    
    for row in layout:
        if isinstance(row, dict): continue
        if not isinstance(row, list): continue
            
        for item in row:
            if isinstance(item, dict):
                pending = dict(item) if pending is None else {**pending, **item}
                if 'rx' in item: rx = item['rx']
                if 'ry' in item: ry = item['ry']
                if 'rx' in item or 'ry' in item:
                    kx = rx
                    ky = ry
                if 'r' in item: r = item['r']
                if 'x' in item: kx += item['x']
                if 'y' in item: ky += item['y']
                continue
                
            w = (pending or {}).get('w', 1.0)
            h = (pending or {}).get('h', 1.0)
            x2 = (pending or {}).get('x2', 0.0)
            y2 = (pending or {}).get('y2', 0.0)
            w2 = (pending or {}).get('w2', w)
            h2 = (pending or {}).get('h2', h)
            
            keys.append({
                'cx_u_raw': kx + w / 2.0,
                'cy_u_raw': ky + h / 2.0,
                'w': w, 'h': h,
                'w2': w2, 'h2': h2, 'x2': x2, 'y2': y2,
                '_t': (pending or {}).get('_t'),
                '_s': (pending or {}).get('_s'),
                '_r': r, '_rx': rx, '_ry': ry,
                '_rs': (pending or {}).get('_rs', 0),
                '_k': (pending or {}).get('_k'),
            })
            kx += w
            pending = None
            
        ky += 1.0
        kx = rx
        
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    
    for k in keys:
        cx, cy = k['cx_u_raw'], k['cy_u_raw']
        angle, rx_c, ry_c = k['_r'], k['_rx'], k['_ry']
        
        if angle != 0:
            # KLE angle is clockwise. rotate (cx, cy) around (rx_c, ry_c) clockwise.
            # CW rotation: x' = x cos a + y sin a, y' = -x sin a + y cos a
            rad = math.radians(angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            dx, dy = cx - rx_c, cy - ry_c
            cx = rx_c + (dx * cos_a - dy * sin_a)
            cy = ry_c + (dx * sin_a + dy * cos_a)
            
        k['cx_u_down'] = cx
        k['cy_u_down'] = cy
        
        # Corners for bounding box (rotated)
        w, h = k['w'], k['h']
        raw_x, raw_y = k['cx_u_raw'], k['cy_u_raw']
        corners = [(raw_x-w/2, raw_y-h/2), (raw_x+w/2, raw_y-h/2),
                   (raw_x+w/2, raw_y+h/2), (raw_x-w/2, raw_y+h/2)]
        if k['w2'] != w or k['h2'] != h:
            w2, h2, x2, y2 = k['w2'], k['h2'], k['x2'], k['y2']
            raw_x2, raw_y2 = raw_x - w/2 + x2 + w2/2, raw_y - h/2 + y2 + h2/2
            corners += [(raw_x2-w2/2, raw_y2-h2/2), (raw_x2+w2/2, raw_y2-h2/2),
                        (raw_x2+w2/2, raw_y2+h2/2), (raw_x2-w2/2, raw_y2+h2/2)]
        
        for c_x, c_y in corners:
            if angle != 0:
                rad = math.radians(angle)
                cos_a, sin_a = math.cos(rad), math.sin(rad)
                dx, dy = c_x - rx_c, c_y - ry_c
                rx_p = rx_c + (dx * cos_a - dy * sin_a)
                ry_p = ry_c + (dx * sin_a + dy * cos_a)
            else:
                rx_p, ry_p = c_x, c_y
            min_x, max_x = min(min_x, rx_p), max(max_x, rx_p)
            min_y, max_y = min(min_y, ry_p), max(max_y, ry_p)
            
    plate_w = max_x - min_x
    plate_h = max_y - min_y
    for k in keys:
        k['cx_u'] = k['cx_u_down'] - min_x
        k['cy_u'] = max_y - k['cy_u_down']
        k['_r'] = -k['_r'] # flip CW to CCW for affinity.rotate
        
    return keys, plate_w, plate_h


# ---------- plate assembly ----------

def build_entities(keys, plate_w_u, plate_h_u, *,
                   pad=0.0, kerf=0.0, switch_type=1, stab_type=0):
    cutout_polys = []
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

        stab_shapes = []
        if (2 <= w < 3) or (rotate_stab and 2 <= h < 3):
            stab_shapes = cutout_registry.get_stab_2u(s)
        elif w >= 3 or (rotate_stab and h >= 3):
            l = h if rotate_stab else w
            s_str = str(l).replace('.', '')
            s_str = s_str.ljust(4 if l >= 10 else 3, '0')
            x_off = STAB_WIDTHS.get(s_str, 11.95)
            stab_shapes = cutout_registry.get_stab_space(s, x_off)

        needs_switch_cutout = not stab_shapes or s == 2
        
        key_polys = []
        if needs_switch_cutout:
            pts = cutout_registry.SWITCH_TYPES.get(t, cutout_registry.SWITCH_TYPES[0])
            poly = Polygon(pts)
            if r:
                poly = affinity.rotate(poly, r, origin=(0, 0))
            key_polys.append(poly)
            
        for pts in stab_shapes:
            poly = Polygon(pts)
            if rotate_stab:
                poly = affinity.rotate(poly, 90, origin=(0, 0))
            if rs:
                poly = affinity.rotate(poly, rs, origin=(0, 0))
            key_polys.append(poly)
            
        if key_polys:
            merged = unary_union(key_polys)
            if k != 0:
                merged = merged.buffer(-k, join_style=2)
            merged = affinity.translate(merged, xoff=cx, yoff=cy)
            cutout_polys.append(merged)
            
    global_cutouts = unary_union(cutout_polys)
    if isinstance(global_cutouts, Polygon):
        return [global_cutouts]
    elif isinstance(global_cutouts, MultiPolygon):
        return list(global_cutouts.geoms)
    else:
        return []


# ---------- PCB extraction ----------

def find_kicad_screw_holes(kicad_path):
    content = Path(kicad_path).read_text()
    pat = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(pat, content, re.DOTALL)]


def find_kicad_switches(kicad_path):
    content = Path(kicad_path).read_text()
    pat = (r'\(footprint\s+"[^"]*SW_[^"]*"'
           r'[^\(]*?\(layer[^\)]+\)'
           r'[^\(]*?\(uuid[^\)]+\)'
           r'\s*\(at\s+([-\d.]+)\s+([-\d.]+)')
    return [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(pat, content)]


def find_edge_cutouts(kicad_path):
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
    pts = []
    for seg in segs:
        if seg[0] == 'line':
            pts.append(seg[1])
        elif seg[0] == 'arc':
            s, m, e = seg[1], seg[2], seg[3]
            res = arc_from_3pts(s, m, e)
            if res:
                center, radius, a_start, a_end = res
                if a_end < a_start:
                    a_end += 360
                for i in range(steps):
                    ang = math.radians(a_start + (a_end - a_start) * i / steps)
                    pts.append((center[0] + radius * math.cos(ang),
                                center[1] + radius * math.sin(ang)))
            else:
                pts.append(s)
    if segs:
        last = segs[-1]
        pts.append(last[2] if last[0] == 'line' else last[3])
    return pts


def classify_arc_side(arc, W, H):
    pts = [arc['start'], arc['mid'], arc['end']]
    avg_x = sum(p[0] for p in pts) / 3.0
    avg_y = sum(p[1] for p in pts) / 3.0
    dists = {'bottom': avg_y, 'top': H - avg_y,
             'left': avg_x, 'right': W - avg_x}
    return min(dists, key=dists.get)


def arc_from_3pts(p1, p2, p3):
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
    by_side = {'bottom': [], 'right': [], 'top': [], 'left': []}
    for a in arcs:
        by_side[classify_arc_side(a, W, H)].append(a)

    r = fillet
    edge_walks = [
        ('bottom', (r, 0.0), (W - r, 0.0)),
        ('right',  (W, r),   (W, H - r)),
        ('top',    (W - r, H), (r, H)),
        ('left',   (0, H - r), (0, r)),
    ]
    
    s45 = math.sin(math.radians(45))
    c45 = math.cos(math.radians(45))
    corners = {
        'br': ('arc', (W-r, 0), (W-r+r*c45, r-r*s45), (W, r)),
        'tr': ('arc', (W, H-r), (W-r+r*c45, H-r+r*s45), (W-r, H)),
        'tl': ('arc', (r, H), (r-r*c45, H-r+r*s45), (0, H-r)),
        'bl': ('arc', (0, r), (r-r*c45, r-r*s45), (r, 0)),
    }

    segs = []
    for i, (side, p1, p2) in enumerate(edge_walks):
        arcs_here = by_side[side]
        if side == 'bottom': arcs_here.sort(key=lambda a: min(a['start'][0], a['end'][0]))
        elif side == 'right': arcs_here.sort(key=lambda a: min(a['start'][1], a['end'][1]))
        elif side == 'top': arcs_here.sort(key=lambda a: -max(a['start'][0], a['end'][0]))
        else: arcs_here.sort(key=lambda a: -max(a['start'][1], a['end'][1]))

        cursor = p1
        for a in arcs_here:
            s, m, e = a['start'], a['mid'], a['end']
            ds = math.hypot(s[0] - cursor[0], s[1] - cursor[1])
            de = math.hypot(e[0] - cursor[0], e[1] - cursor[1])
            entry, exit_ = (s, e) if ds <= de else (e, s)
            if side == 'bottom': edge_entry, edge_exit = (entry[0], 0.0), (exit_[0], 0.0)
            elif side == 'top': edge_entry, edge_exit = (entry[0], H), (exit_[0], H)
            elif side == 'left': edge_entry, edge_exit = (0.0, entry[1]), (0.0, exit_[1])
            else: edge_entry, edge_exit = (W, entry[1]), (W, exit_[1])
            segs.append(('line', cursor, edge_entry))
            segs.append(('line', edge_entry, entry))
            segs.append(('arc', entry, m, exit_))
            segs.append(('line', exit_, edge_exit))
            cursor = edge_exit
        segs.append(('line', cursor, p2))
        
        if r > 0:
            if side == 'bottom': segs.append(corners['br'])
            elif side == 'right': segs.append(corners['tr'])
            elif side == 'top': segs.append(corners['tl'])
            elif side == 'left': segs.append(corners['bl'])
            
    return segs


def snap_screws_to_grid(screws, key_centers, row_tol=4.0, max_shift=5.0):
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

def validate_screws(screws, screw_radius, outline_poly, cutouts_polys, clearance=0.5):
    issues = []
    for i, (sx, sy) in enumerate(screws):
        screw_center = Point(sx, sy)
        
        if not outline_poly.contains(screw_center):
            issues.append((i, 'outside_plate', 0.0))
            continue
            
        d_edge = outline_poly.exterior.distance(screw_center)
        if d_edge < screw_radius + clearance:
            issues.append((i, 'too_close_edge', d_edge))
            continue
            
        hit = False
        for j, cut in enumerate(cutouts_polys):
            if cut.contains(screw_center):
                issues.append((i, f'inside_cutout#{j}', 0.0))
                hit = True
                break
            d = cut.distance(screw_center)
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
        if flip_x: x = -x
        if flip_y: y = -y
        if rot_deg:
            r = math.radians(rot_deg)
            co, si = math.cos(r), math.sin(r)
            x, y = co * x - si * y, si * x + co * y
        out.append((x, y))
    return out


def solve_pcb_transform(pcb_switches, kle_switches):
    if not pcb_switches or not kle_switches:
        return None, (lambda pts: list(pts))

    best = None
    for flip_x in (False, True):
        for flip_y in (False, True):
            for rot in (0, 90, 180, 270):
                t_base = _transform_points(pcb_switches, flip_x, flip_y, rot)
                landmarks = [0, len(t_base)//2, len(t_base)-1]
                for l_idx in landmarks:
                    lp = t_base[l_idx]
                    for kp in kle_switches:
                        tx = kp[0] - lp[0]
                        ty = kp[1] - lp[1]
                        
                        score = 0.0
                        for sx, sy in t_base:
                            px, py = sx + tx, sy + ty
                            min_d2 = float('inf')
                            for kx, ky in kle_switches:
                                d2 = (px - kx)**2 + (py - ky)**2
                                if d2 < min_d2: min_d2 = d2
                            score += math.sqrt(min_d2)
                        
                        if best is None or score < best[0]:
                            best = (score, {'flip_x': flip_x, 'flip_y': flip_y,
                                            'rot': rot, 'dx': tx, 'dy': ty})
    score, params = best

    def apply(pts):
        t = _transform_points(pts, params['flip_x'], params['flip_y'], params['rot'])
        return [(x + params['dx'], y + params['dy']) for x, y in t]

    params['nn_score'] = score
    return params, apply


# ---------- DXF & SVG writer ----------

def emit_dxf(out_path, cutouts_polys, screw_holes=None, outline_segments=None, screw_radius=1.2):
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    colors = {L_OUTLINE: 7, L_SWITCH: 3, L_SCREW: 1}
    for name in colors:
        if name not in doc.layers:
            doc.layers.add(name, color=colors[name])

    if outline_segments is not None:
        for seg in outline_segments:
            if seg[0] == 'line':
                msp.add_lwpolyline([seg[1], seg[2]], dxfattribs={'layer': L_OUTLINE})
            elif seg[0] == 'arc':
                res = arc_from_3pts(seg[1], seg[2], seg[3])
                if res:
                    center, radius, a_start, a_end = res
                    sweep = a_end - a_start
                    if sweep < 0: sweep += 360
                    bulge = math.tan(math.radians(sweep) / 4.0)
                    msp.add_lwpolyline([(seg[1][0], seg[1][1], 0, 0, bulge),
                                        (seg[3][0], seg[3][1])],
                                       dxfattribs={'layer': L_OUTLINE})
                else:
                    msp.add_lwpolyline([seg[1], seg[3]], dxfattribs={'layer': L_OUTLINE})

    def add_poly(p):
        coords = list(p.exterior.coords)
        if coords[0] == coords[-1]: coords = coords[:-1]
        msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': L_SWITCH})
        for interior in p.interiors:
            coords = list(interior.coords)
            if coords[0] == coords[-1]: coords = coords[:-1]
            msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': L_SWITCH})

    for poly in cutouts_polys:
        if isinstance(poly, Polygon):
            add_poly(poly)
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms:
                add_poly(p)

    for x, y in (screw_holes or []):
        msp.add_circle((x, y), screw_radius, dxfattribs={'layer': L_SCREW})

    doc.saveas(out_path)


def generate_svg_string(plate_w, plate_h, outline_segments, cutouts_polys, screws, screw_radius):
    pad = 10
    min_x, min_y = -pad, -pad
    max_x, max_y = plate_w + pad, plate_h + pad
    width = max_x - min_x
    height = max_y - min_y
    
    lines = []
    lines.append(f'<svg viewBox="{min_x} {-max_y} {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    lines.append(f'<g transform="scale(1, -1)">')
    
    if outline_segments:
        path_data = []
        for i, seg in enumerate(outline_segments):
            if seg[0] == 'line':
                p1, p2 = seg[1], seg[2]
                if i == 0: path_data.append(f"M {p1[0]},{p1[1]}")
                path_data.append(f"L {p2[0]},{p2[1]}")
            elif seg[0] == 'arc':
                pts = discretize_segments([seg], steps=20)
                if i == 0 and pts: path_data.append(f"M {pts[0][0]},{pts[0][1]}")
                for p in pts[1:]: path_data.append(f"L {p[0]},{p[1]}")
                    
        path_str = " ".join(path_data)
        if path_str:
            lines.append(f'<path d="{path_str} Z" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
            
    for poly in cutouts_polys:
        def poly_to_path(p):
            coords = list(p.exterior.coords)
            d = f"M {coords[0][0]},{coords[0][1]} " + " ".join(f"L {x},{y}" for x, y in coords[1:]) + " Z"
            for interior in p.interiors:
                coords = list(interior.coords)
                d += f" M {coords[0][0]},{coords[0][1]} " + " ".join(f"L {x},{y}" for x, y in coords[1:]) + " Z"
            return d
            
        if isinstance(poly, Polygon):
            lines.append(f'<path d="{poly_to_path(poly)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms:
                lines.append(f'<path d="{poly_to_path(p)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
        
    for sx, sy in (screws or []):
        lines.append(f'<circle cx="{sx}" cy="{sy}" r="{screw_radius}" fill="#ffffff" stroke="#ef4444" stroke-width="0.5"/>')
        
    lines.append('</g>')
    lines.append('</svg>')
    return "\n".join(lines)


# ---------- Core API ----------

def generate_plate(kle_path=None, out_path=None, pcb_path=None,
                   switch_type=1, stab_type=0, kerf=0.0, pad=0.0,
                   screw_diameter=2.4, pcb_dx=0.0, pcb_dy=0.0,
                   no_auto_align=False, clearance=0.5, snap_screws=False,
                   fillet=0.0, screw_preset=None, screw_custom=None,
                   screw_inset=5.0, kle_text=None):
    if kle_text:
        raw_text = kle_text
    elif kle_path:
        raw_text = Path(kle_path).read_text(encoding='utf-8')
    else:
        raise ValueError("Must provide either kle_path or kle_text")
        
    # KLE's raw data tab produces JavaScript objects with unquoted keys (e.g., {w:2})
    # This regex wraps any unquoted alphanumeric keys in double quotes to make it valid JSON.
    sanitized_text = re.sub(r'([{,]\s*)([a-zA-Z_]\w*)\s*:', r'\1"\2":', raw_text)
    layout = json.loads(sanitized_text)
    
    keys, w_u, h_u = parse_kle(layout)
    
    cutouts_polys = build_entities(
        keys, w_u, h_u,
        pad=pad, kerf=kerf,
        switch_type=switch_type, stab_type=stab_type,
    )

    plate_w = w_u * U1 + 2 * pad
    plate_h = h_u * U1 + 2 * pad
    screw_radius = screw_diameter / 2.0

    screws = None
    edge_arcs = []
    params = None
    issues = []

    if screw_custom:
        screws = screw_presets.custom_from_string(screw_custom, plate_w, plate_h)
    elif screw_preset:
        fn = screw_presets.PRESETS[screw_preset]
        if screw_preset == 'between_rows':
            screws = fn(keys, plate_w, pad, screw_inset, U1)
        else:
            screws = fn(plate_w, plate_h, inset=screw_inset)
    elif pcb_path:
        screws = find_kicad_screw_holes(pcb_path)
        edge_arcs = find_edge_cutouts(pcb_path)
        pcb_switches = find_kicad_switches(pcb_path)
        kle_switches = [(k['cx_u'] * U1 + pad, k['cy_u'] * U1 + pad) for k in keys]

        if no_auto_align:
            nudge = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in pts]
            screws = nudge(screws)
            edge_arcs = [transform_arc(a, nudge) for a in edge_arcs]
        else:
            params, apply = solve_pcb_transform(pcb_switches, kle_switches)
            nudged_apply = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
            screws = nudged_apply(screws)
            edge_arcs = [transform_arc(a, nudged_apply) for a in edge_arcs]

        if snap_screws:
            screws = snap_screws_to_grid(screws, kle_switches)

    outline_segments = None
    outline_poly = None
    
    if pcb_path:
        pcb_outline = find_all_edge_cuts(pcb_path)
        if pcb_outline:
            nudged_apply = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
            outline_segments = [transform_segment(seg, nudged_apply) for seg in pcb_outline]
            pts = discretize_segments(outline_segments)
            if pts: outline_poly = Polygon(pts)
        if not outline_segments:
            outline_segments = build_outline_segments(plate_w, plate_h, edge_arcs, fillet=fillet)
            outline_poly = Polygon(discretize_segments(outline_segments))
    else:
        outline_segments = build_outline_segments(plate_w, plate_h, edge_arcs, fillet=fillet)
        outline_poly = Polygon(discretize_segments(outline_segments))

    if not outline_poly or not outline_poly.is_valid:
        # Fallback to bbox
        outline_poly = Polygon([(0,0), (plate_w,0), (plate_w,plate_h), (0,plate_h)])

    if screws:
        issues = validate_screws(screws, screw_radius, outline_poly, cutouts_polys, clearance)

    emit_dxf(
        out_path, cutouts_polys,
        screw_holes=screws,
        outline_segments=outline_segments,
        screw_radius=screw_radius,
    )
    
    svg_str = generate_svg_string(plate_w, plate_h, outline_segments, cutouts_polys, screws, screw_radius)

    return {
        "keys": len(keys),
        "plate_w": plate_w,
        "plate_h": plate_h,
        "screws": len(screws or []),
        "edge_notches": len(edge_arcs),
        "params": params,
        "issues": issues,
        "out_path": out_path,
        "svg": svg_str
    }


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument('--kle', required=True, help='KLE JSON layout file')
    ap.add_argument('--out', required=True, help='Output DXF path')
    ap.add_argument('--pcb', help='KiCad PCB file (optional)')
    ap.add_argument('--switch-type', type=int, default=1, choices=[0, 1, 2, 3])
    ap.add_argument('--stab-type', type=int, default=0, choices=[0, 1, 2])
    ap.add_argument('--kerf', type=float, default=0.0)
    ap.add_argument('--pad', type=float, default=0.0)
    ap.add_argument('--screw-diameter', type=float, default=2.4)
    ap.add_argument('--pcb-dx', type=float, default=0.0)
    ap.add_argument('--pcb-dy', type=float, default=0.0)
    ap.add_argument('--no-auto-align', action='store_true')
    ap.add_argument('--clearance', type=float, default=0.5)
    ap.add_argument('--snap-screws', action='store_true')
    ap.add_argument('--fillet', type=float, default=0.0)
    ap.add_argument('--screw-preset', choices=list(screw_presets.PRESETS.keys()))
    ap.add_argument('--screw-custom')
    ap.add_argument('--screw-inset', type=float, default=5.0)
    args = ap.parse_args()

    res = generate_plate(
        args.kle, args.out, pcb_path=args.pcb,
        switch_type=args.switch_type, stab_type=args.stab_type,
        kerf=args.kerf, pad=args.pad, screw_diameter=args.screw_diameter,
        pcb_dx=args.pcb_dx, pcb_dy=args.pcb_dy,
        no_auto_align=args.no_auto_align, clearance=args.clearance,
        snap_screws=args.snap_screws, fillet=args.fillet,
        screw_preset=args.screw_preset, screw_custom=args.screw_custom,
        screw_inset=args.screw_inset
    )

    print(f"keys={res['keys']} plate={res['plate_w']:.2f}x{res['plate_h']:.2f}mm screws={res['screws']} -> {res['out_path']}")

    if res['issues']:
        print(f"VALIDATOR: {len(res['issues'])} issue(s):")
        for i, kind, d in res['issues'][:20]: print(f"  screw#{i} {kind} dist={d:.2f}mm")
        raise SystemExit(1)
    elif args.pcb:
        print("VALIDATOR: all screws inside plate, none overlapping cutouts")

if __name__ == '__main__':
    main()
