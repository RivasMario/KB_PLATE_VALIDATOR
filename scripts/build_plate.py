#!/usr/bin/env python3
"""
build_plate.py

Generate a keyboard plate DXF from KLE JSON plus (optionally) a KiCad PCB.
Outputs a single DXF with layered geometry and an SVG preview.
"""

import argparse
import json
import logging
import math
import re
from pathlib import Path
from collections import defaultdict

import ezdxf
from shapely.geometry import Polygon, MultiPolygon, Point, box, LineString, GeometryCollection
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


def _setup_logger():
    lg = logging.getLogger('plate')
    if getattr(lg, '_plate_configured', False):
        return lg
    lg.setLevel(logging.DEBUG)
    log_dir = Path(__file__).resolve().parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(log_dir / 'plate_generator.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    lg.addHandler(fh)
    lg.propagate = False
    lg._plate_configured = True
    return lg


log = _setup_logger()


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


# ---------- helpers ----------

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
                        tx, ty = kp[0] - lp[0], kp[1] - lp[1]
                        score = 0.0
                        for sx, sy in t_base:
                            px, py = sx + tx, sy + ty
                            min_d2 = float('inf')
                            for kx, ky in kle_switches:
                                d2 = (px - kx)**2 + (py - ky)**2
                                if d2 < min_d2: min_d2 = d2
                            score += math.sqrt(min_d2)
                        if best is None or score < best[0]:
                            best = (score, {'flip_x': flip_x, 'flip_y': flip_y, 'rot': rot, 'dx': tx, 'dy': ty})
    score, params = best
    def apply(pts):
        t = _transform_points(pts, params['flip_x'], params['flip_y'], params['rot'])
        return [(x + params['dx'], y + params['dy']) for x, y in t]
    params['nn_score'] = score
    return params, apply


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
                hit = True; break
            d = cut.distance(screw_center)
            if d < screw_radius + clearance:
                issues.append((i, f'too_close_cutout#{j}', d))
                hit = True; break
        if hit: continue
    return issues


def rotate_pt(px, py, ang, cx, cy):
    if ang == 0: return px, py
    rad = math.radians(ang)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = px - cx, py - cy
    return cx + (dx * cos_a - dy * sin_a), cy + (dx * sin_a + dy * cos_a)


def arc_from_3pts(p1, p2, p3):
    ax, ay = p1; bx, by = p2; cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9: return None
    ux = ((ax**2+ay**2)*(by-cy) + (bx**2+by**2)*(cy-ay) + (cx**2+cy**2)*(ay-by)) / d
    uy = ((ax**2+ay**2)*(cx-bx) + (bx**2+by**2)*(ax-cx) + (cx**2+cy**2)*(bx-ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    s = math.degrees(math.atan2(ay - uy, ax - ux))
    e = math.degrees(math.atan2(cy - uy, cx - ux))
    cp = (bx-ax)*(cy-by) - (by-ay)*(cx-bx)
    if cp < 0: s, e = e, s
    return (ux, uy), r, s, e, cp > 0


# ---------- parsers ----------

def parse_kle(layout):
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
                if 'rx' in item or 'ry' in item: kx, ky = rx, ry
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
        angle, rx_c, ry_c = k['_r'], k['_rx'], k['_ry']
        k['cx_u_down'], k['cy_u_down'] = rotate_pt(k['cx_u_raw'], k['cy_u_raw'], angle, rx_c, ry_c)
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
            rx_p, ry_p = rotate_pt(c_x, c_y, angle, rx_c, ry_c)
            min_x, max_x = min(min_x, rx_p), max(max_x, rx_p)
            min_y, max_y = min(min_y, ry_p), max(max_y, ry_p)
    plate_w = max_x - min_x
    plate_h = max_y - min_y
    for k in keys:
        k['cx_u'] = k['cx_u_down'] - min_x
        k['cy_u'] = max_y - k['cy_u_down']
        k['_r_ccw'] = -k['_r']
    return keys, plate_w * U1, plate_h * U1


def build_entities(keys, pad=0.0, kerf=0.0, switch_type=1, stab_type=0):
    all_cutouts = []
    k_default = kerf / 2.0
    for key in keys:
        cx, cy = key['cx_u'] * U1 + pad, key['cy_u'] * U1 + pad
        w, h = key['w'], key['h']
        k = (key['_k'] / 2.0) if key.get('_k') is not None else k_default
        t = key['_t'] if key.get('_t') is not None else switch_type
        s = key['_s'] if key.get('_s') is not None else stab_type
        r = key.get('_r_ccw', 0)
        rs = key.get('_rs', 0)
        rotate_stab = h > w
        
        # 1. Switch hole
        pts = cutout_registry.SWITCH_TYPES.get(t, cutout_registry.SWITCH_TYPES[0])
        p_sw = Polygon(pts)
        if rs: p_sw = affinity.rotate(p_sw, rs, origin=(0, 0))
        
        key_polys = [p_sw]
        
        # 2. Stab hole(s)
        stab_shapes = []
        if (2 <= w < 3) or (rotate_stab and 2 <= h < 3):
            stab_shapes = cutout_registry.get_stab_2u(s)
        elif w >= 3 or (rotate_stab and h >= 3):
            l = h if rotate_stab else w
            s_str = str(l).replace('.', '').ljust(3, '0')
            x_off = STAB_WIDTHS.get(s_str[:3], 11.95)
            stab_shapes = cutout_registry.get_stab_space(s, x_off)
        
        for pts in stab_shapes:
            p_st = Polygon(pts)
            if rotate_stab: p_st = affinity.rotate(p_st, 90, origin=(0, 0))
            key_polys.append(p_st)
            
        # 3. Union them for this key
        merged = unary_union(key_polys)
        
        # 4. Apply rotation, kerf and translation
        if r: merged = affinity.rotate(merged, r, origin=(0, 0))
        if k != 0: merged = merged.buffer(-k, join_style=2)
        
        shifted = affinity.translate(merged, xoff=cx, yoff=cy)
        if isinstance(shifted, Polygon):
            all_cutouts.append(shifted)
        elif isinstance(shifted, MultiPolygon):
            all_cutouts.extend(list(shifted.geoms))
            
    return all_cutouts


# ---------- extraction ----------

def find_kicad_screw_holes(kicad_path):
    content = Path(kicad_path).read_text()
    pat = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2))) for m in re.finditer(pat, content, re.DOTALL)]

def find_kicad_switches(kicad_path):
    content = Path(kicad_path).read_text()
    # Support "SW_" or "MX-" footprints. Using DOTALL and non-greedy match for flexibility.
    # Updated to handle 'locked' or other attributes between footprint name and 'at'
    pat = r'\(footprint\s+"[^"]*(?:SW_|MX-)[^"]*".*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2))) for m in re.finditer(pat, content, re.DOTALL)]

def find_all_edge_cuts(kicad_path):
    content = Path(kicad_path).read_text()
    
    # 1. Global (gr_*) segments
    line_re = r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    arc_re = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    circle_re = r'\(gr_circle\s+\(center\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    
    segs = []
    for m in re.finditer(line_re, content, re.DOTALL):
        segs.append(('line', (float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4)))))
    for m in re.finditer(arc_re, content, re.DOTALL):
        segs.append(('arc', (float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4))), (float(m.group(5)), float(m.group(6)))))
    for m in re.finditer(circle_re, content, re.DOTALL):
        cx, cy, ex, ey = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        r = math.hypot(ex - cx, ey - cy)
        segs.append(('arc', (cx+r, cy), (cx+r/1.414, cy+r/1.414), (cx, cy+r)))
        segs.append(('arc', (cx, cy+r), (cx-r/1.414, cy+r/1.414), (cx-r, cy)))
        segs.append(('arc', (cx-r, cy), (cx-r/1.414, cy-r/1.414), (cx, cy-r)))
        segs.append(('arc', (cx, cy-r), (cx+r/1.414, cy-r/1.414), (cx+r, cy)))
        
    # 2. Footprint-embedded (fp_*) segments
    # Pattern: find (footprint ... (at X Y R) ... followed by (fp_line ... (layer "Edge.Cuts"))
    # This is slightly more complex as coordinates are relative to footprint origin.
    footprint_re = r'\(footprint\s+"[^"]*".*?\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\).*?(\(fp_line.*?\)\s*|\(fp_arc.*?\)\s*|\(fp_circle.*?\)\s*)*\)'
    # Actually, simpler to just parse all footprints and then their internal fp_ elements
    for fp_match in re.finditer(r'\(footprint\s+"([^"]*)".*?\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\).*?\)', content, re.DOTALL):
        fp_name = fp_match.group(1)
        fx, fy = float(fp_match.group(2)), float(fp_match.group(3))
        fr = float(fp_match.group(4)) if fp_match.group(4) else 0.0
        fp_body = fp_match.group(0)
        
        def rel_to_abs(px, py):
            return rotate_pt(px + fx, py + fy, fr, fx, fy)

        # Parse fp_line
        for m in re.finditer(r'\(fp_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"', fp_body, re.DOTALL):
            p1 = rel_to_abs(float(m.group(1)), float(m.group(2)))
            p2 = rel_to_abs(float(m.group(3)), float(m.group(4)))
            segs.append(('line', p1, p2))
            
        # Parse fp_arc
        for m in re.finditer(r'\(fp_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"', fp_body, re.DOTALL):
            p1 = rel_to_abs(float(m.group(1)), float(m.group(2)))
            p2 = rel_to_abs(float(m.group(3)), float(m.group(4)))
            p3 = rel_to_abs(float(m.group(5)), float(m.group(6)))
            segs.append(('arc', p1, p2, p3))
            
    return segs

def transform_segment(seg, apply_fn):
    if seg[0] == 'line': return ('line', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0])
    if seg[0] == 'arc': return ('arc', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0], apply_fn([seg[3]])[0])
    return seg

def chain_segments_robust(segs, tol=0.1):
    if not segs: return []
    items = []
    for s in segs:
        if s[0] == 'line': items.append({'p1': s[1], 'p2': s[2], 'type': 'line'})
        elif s[0] == 'arc': items.append({'p1': s[1], 'p2': s[3], 'type': 'arc', 'mid': s[2], 'orig': s})
    loops = []
    used = [False] * len(items)
    def dist(p_a, p_b): return math.hypot(p_a[0]-p_b[0], p_a[1]-p_b[1])
    def calc_bulge(item, is_forward):
        if item['type'] == 'line': return 0.0
        if is_forward: s, m, e = item['p1'], item['mid'], item['p2']
        else: s, m, e = item['p2'], item['mid'], item['p1']
        res = arc_from_3pts(s, m, e)
        if not res: return 0.0
        _, _, start_ang, end_ang, is_ccw = res
        sweep = (end_ang - start_ang) % 360
        if not is_ccw: sweep -= 360
        return math.tan(math.radians(sweep) / 4.0)

    for start_idx in range(len(items)):
        if used[start_idx]: continue
        curr_chain = []
        curr_item = items[start_idx]
        used[start_idx] = True
        curr_chain.append({'pt': curr_item['p1'], 'bulge': calc_bulge(curr_item, is_forward=True)})
        last_pt = curr_item['p2']
        while True:
            found_next = False
            for i in range(len(items)):
                if used[i]: continue
                candidate = items[i]
                if dist(last_pt, candidate['p1']) < tol:
                    curr_chain.append({'pt': last_pt, 'bulge': calc_bulge(candidate, is_forward=True)})
                    last_pt = candidate['p2']
                    used[i] = True; found_next = True; break
                elif dist(last_pt, candidate['p2']) < tol:
                    curr_chain.append({'pt': last_pt, 'bulge': calc_bulge(candidate, is_forward=False)})
                    last_pt = candidate['p1']
                    used[i] = True; found_next = True; break
            if not found_next: break
        curr_chain.append({'pt': last_pt, 'bulge': 0.0})
        is_closed = dist(curr_chain[0]['pt'], curr_chain[-1]['pt']) < tol
        loops.append({'pts': curr_chain, 'closed': is_closed})
    return loops


# ---------- chaining helpers (module-scope so emit_dxf can use them) ----------

def seg_to_polyline(seg, steps=24):
    """Flatten a line/arc segment into a list of (x, y) points."""
    if seg[0] == 'line':
        return [seg[1], seg[2]]
    res = arc_from_3pts(seg[1], seg[2], seg[3])
    if not res:
        return [seg[1], seg[3]]
    (ux, uy), r, s, e, _ = res
    sweep = (e - s) % 360
    pts = []
    for i in range(steps + 1):
        ang = math.radians(s + sweep * (i / steps))
        pts.append((ux + r * math.cos(ang), uy + r * math.sin(ang)))
    return pts


def chain_polylines(segments, tol=0.1):
    """
    Chain raw line/arc segments into ordered polylines, growing each chain in
    BOTH directions (forward and backward). Returns (closed_loops, open_chains)
    as lists of point lists. Arcs are flattened via seg_to_polyline.
    """
    polys = [seg_to_polyline(s) for s in segments]
    used = [False] * len(polys)
    closed_loops = []
    open_chains = []
    for start in range(len(polys)):
        if used[start]:
            continue
        used[start] = True
        chain = list(polys[start])
        changed = True
        while changed:
            changed = False
            for i in range(len(polys)):
                if used[i]:
                    continue
                p = polys[i]
                if math.hypot(chain[-1][0]-p[0][0], chain[-1][1]-p[0][1]) < tol:
                    chain.extend(p[1:]); used[i] = True; changed = True
                elif math.hypot(chain[-1][0]-p[-1][0], chain[-1][1]-p[-1][1]) < tol:
                    chain.extend(list(reversed(p))[1:]); used[i] = True; changed = True
                elif math.hypot(chain[0][0]-p[-1][0], chain[0][1]-p[-1][1]) < tol:
                    chain = list(p) + chain[1:]; used[i] = True; changed = True
                elif math.hypot(chain[0][0]-p[0][0], chain[0][1]-p[0][1]) < tol:
                    chain = list(reversed(p)) + chain[1:]; used[i] = True; changed = True
        if math.hypot(chain[0][0]-chain[-1][0], chain[0][1]-chain[-1][1]) < tol * 5:
            closed_loops.append(chain)
        else:
            open_chains.append(chain)
    return closed_loops, open_chains


# ---------- emitters ----------

def emit_dxf(out_path, switch_polys, stab_polys, screw_holes=None, outline_segments=None, screw_radius=1.2, outline_poly=None):
    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()
    for name, color in {L_OUTLINE: 7, L_SWITCH: 3, L_STAB: 5, L_SCREW: 1}.items():
        doc.layers.add(name, color=color)

    def add_poly(p, layer):
        coords = list(p.exterior.coords)
        if coords[0] == coords[-1]: coords = coords[:-1]
        msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': layer})
        for interior in p.interiors:
            coords = list(interior.coords)
            if coords[0] == coords[-1]: coords = coords[:-1]
            msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': layer})

    if outline_segments:
        # SendCutSend / fab houses parse closed boundary loops, not floating LINE/ARC
        # primitives. Chain segments (extending in both directions for robustness),
        # flatten arcs into short chord polylines, and emit each closed loop as a
        # single closed LWPOLYLINE. No bulges → no sign-convention ambiguity, no
        # "open entities" complaints, no balls extending out of corners.
        closed_loops, open_chains = chain_polylines(outline_segments)
        for chain in closed_loops:
            pts = list(chain)
            if len(pts) > 1 and math.hypot(pts[0][0]-pts[-1][0], pts[0][1]-pts[-1][1]) < 1e-6:
                pts = pts[:-1]  # drop duplicated closing vertex; close=True handles it
            if len(pts) >= 2:
                msp.add_lwpolyline(pts, close=True, dxfattribs={'layer': L_OUTLINE})
        for chain in open_chains:
            if len(chain) >= 2:
                msp.add_lwpolyline(chain, close=False, dxfattribs={'layer': L_OUTLINE})
        log.info(
            "emit_dxf outline: closed_loops=%d open_chains=%d total_segments_in=%d",
            len(closed_loops), len(open_chains), len(outline_segments),
        )
        if open_chains:
            log.warning("emit_dxf produced %d open chain(s) — fab parser may reject", len(open_chains))
    else:
        if isinstance(outline_poly, Polygon): add_poly(outline_poly, L_OUTLINE)
        elif isinstance(outline_poly, MultiPolygon):
            for p in outline_poly.geoms: add_poly(p, L_OUTLINE)
            
    for poly in switch_polys:
        if isinstance(poly, Polygon): add_poly(poly, L_SWITCH)
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: add_poly(p, L_SWITCH)
            
    for poly in stab_polys:
        if isinstance(poly, Polygon): add_poly(poly, L_STAB)
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: add_poly(p, L_STAB)
            
    for x, y in (screw_holes or []): msp.add_circle((x, y), screw_radius, dxfattribs={'layer': L_SCREW})
    doc.saveas(out_path)

def generate_svg_string(plate_w, plate_h, outline_poly, switch_polys, stab_polys, screws, screw_radius, outline_segments=None):
    minx, miny, maxx, maxy = outline_poly.bounds
    pad = 10
    view_w, view_h = (maxx - minx) + 2*pad, (maxy - miny) + 2*pad
    lines = [f'<svg viewBox="{minx-pad} {-maxy-pad} {view_w} {view_h}" xmlns="http://www.w3.org/2000/svg">',
             '<g transform="scale(1, -1)">']
    def poly_to_path(p):
        coords = list(p.exterior.coords)
        d = f"M {coords[0][0]},{coords[0][1]} " + " ".join(f"L {x},{y}" for x, y in coords[1:]) + " Z"
        for interior in p.interiors:
            coords = list(interior.coords)
            d += f" M {coords[0][0]},{coords[0][1]} " + " ".join(f"L {x},{y}" for x, y in coords[1:]) + " Z"
        return d
    
    if outline_segments:
        # Use the same chain+flatten as the DXF emitter so the preview is a faithful
        # representation of what gets shipped (no separate arc math, no sign drift).
        closed_loops, open_chains = chain_polylines(outline_segments)
        for chain, is_closed in [(c, True) for c in closed_loops] + [(c, False) for c in open_chains]:
            if not chain: continue
            d_parts = [f"M {chain[0][0]},{chain[0][1]}"]
            for x, y in chain[1:]:
                d_parts.append(f"L {x},{y}")
            if is_closed: d_parts.append("Z")
            lines.append(f'<path d="{" ".join(d_parts)}" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
    else:
        if isinstance(outline_poly, Polygon): lines.append(f'<path d="{poly_to_path(outline_poly)}" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
        elif isinstance(outline_poly, MultiPolygon):
            for p in outline_poly.geoms: lines.append(f'<path d="{poly_to_path(p)}" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
            
    for poly in switch_polys:
        if isinstance(poly, Polygon): lines.append(f'<path d="{poly_to_path(poly)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: lines.append(f'<path d="{poly_to_path(p)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
            
    for poly in stab_polys:
        if isinstance(poly, Polygon): lines.append(f'<path d="{poly_to_path(poly)}" fill="#ffffff" stroke="#10b981" stroke-width="0.5"/>')
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: lines.append(f'<path d="{poly_to_path(p)}" fill="#ffffff" stroke="#10b981" stroke-width="0.5"/>')
            
    for sx, sy in (screws or []): lines.append(f'<circle cx="{sx}" cy="{sy}" r="{screw_radius}" fill="#ffffff" stroke="#ef4444" stroke-width="0.5"/>')
    lines.extend(['</g>', '</svg>'])
    return "\n".join(lines)


# ---------- core api ----------

def snap_screws_to_grid(screws, key_centers, row_tol=4.0, max_shift=5.0):
    snapped = []
    for sx, sy in screws:
        row = [kx for (kx, ky) in key_centers if abs(ky - sy) < row_tol]
        if len(row) < 2:
            snapped.append((sx, sy)); continue
        row.sort()
        left = max((x for x in row if x <= sx), default=None)
        right = min((x for x in row if x >= sx), default=None)
        if left is None or right is None:
            snapped.append((sx, sy)); continue
        target = (left + right) / 2.0
        if abs(target - sx) <= max_shift: snapped.append((target, sy))
        else: snapped.append((sx, sy))
    return snapped


def apply_poker_cutins(poly, plate_w, plate_h):
    """
    SwillKB Poker method fallback. Forcefully cuts small U-shaped notches into the edges.
    """
    # Create 4 standard poker cut-ins (1 left, 3 bottom)
    cutins = []
    # Left cut-in
    cutins.append(box(-2, plate_h/2 - 10, 2.62, plate_h/2 + 10))
    # Bottom cut-ins (approximate positions like Swillkb Poker)
    cutins.append(box(plate_w*0.2 - 10, plate_h - 2.62, plate_w*0.2 + 10, plate_h + 2))
    cutins.append(box(plate_w*0.5 - 10, plate_h - 2.62, plate_w*0.5 + 10, plate_h + 2))
    cutins.append(box(plate_w*0.8 - 10, plate_h - 2.62, plate_w*0.8 + 10, plate_h + 2))
    
    for cutin in cutins:
        poly = poly.difference(cutin)
    return poly


def apply_puzzle_split(outline_poly, all_cutouts, screws, thickness=1.5, gap=10.0, tolerance=0.1):
    """
    Split the plate geometry into two halves using a zigzag joint.
    Assigns cutouts by centroid to guarantee they are never intersected or broken.
    Includes a 'tolerance' gap for 3D printing fit.
    """
    minx, miny, maxx, maxy = outline_poly.bounds
    center_x = (minx + maxx) / 2.0
    
    # Wider corridor search
    tooth_h = 4.0 
    search_range = 80.0
    step_size = 0.5
    
    samples = []
    for i in range(int(-search_range / step_size), int(search_range / step_size)):
        x = center_x + i * step_size
        test_box = box(x - (tooth_h/2 + 1.0), miny - 5, x + (tooth_h/2 + 1.0), maxy + 5)
        hits = 0
        for p in all_cutouts:
            if test_box.intersects(p): hits += 1
        samples.append((x, hits))
    
    zero_ranges = []
    current_range = []
    for x, hits in samples:
        if hits == 0:
            current_range.append(x)
        else:
            if current_range:
                zero_ranges.append(current_range)
                current_range = []
    if current_range: zero_ranges.append(current_range)
    
    if zero_ranges:
        best_range = max(zero_ranges, key=len)
        mid_x = sum(best_range) / len(best_range)
        log.info("found clear corridor at x=%.2f (width %.1fmm)", mid_x, len(best_range) * step_size)
    else:
        min_hits = min(s[1] for s in samples)
        best_samples = [s for s in samples if s[1] == min_hits]
        mid_x = min(best_samples, key=lambda s: abs(s[0] - center_x))[0]
        log.warning("no clear corridor found; splitting with %d hits at x=%.2f", min_hits, mid_x)

    tooth_w = 15.0 
    num_teeth = int((maxy - miny) / tooth_w)
    if num_teeth < 2: num_teeth = 2
    step = (maxy - miny) / num_teeth
    
    pts = [(mid_x, miny - 10.0)]
    for i in range(num_teeth):
        y = miny + i * step
        pts.append((mid_x - tooth_h/2, y + step*0.2))
        pts.append((mid_x + tooth_h/2, y + step*0.4))
        pts.append((mid_x + tooth_h/2, y + step*0.6))
        pts.append((mid_x - tooth_h/2, y + step*0.8))
    pts.append((mid_x, maxy + 10.0))
    
    # Base split polygons
    poly_left_base = Polygon(pts + [(mid_x - 5000, maxy + 10), (mid_x - 5000, miny - 10)])
    poly_right_base = Polygon(pts + [(mid_x + 5000, maxy + 10), (mid_x + 5000, miny - 10)])
    
    # Apply tolerance to the right side by buffering the cutter
    # This creates a small gap between the teeth
    if tolerance > 0:
        # We shrink the left part and right part slightly at the joint?
        # Simpler: offset the zigzag line by tolerance/2 for each side.
        joint_line = LineString(pts)
        left_cutter = poly_left_base.difference(joint_line.buffer(tolerance/2, join_style=2))
        right_cutter = poly_right_base.difference(joint_line.buffer(tolerance/2, join_style=2))
    else:
        left_cutter = poly_left_base
        right_cutter = poly_right_base
    
    def process_half(cutter, raw_base_cutter, x_shift=0.0):
        new_outline = outline_poly.intersection(cutter)
        if x_shift != 0:
            new_outline = affinity.translate(new_outline, xoff=x_shift)
            
        new_cutouts = []
        for p in all_cutouts:
            # We use the RAW base cutter (no tolerance) for assignment to ensure 
            # we don't lose holes that fall into the tolerance gap
            if raw_base_cutter.contains(p.centroid):
                res = p
                if x_shift != 0: res = affinity.translate(res, xoff=x_shift)
                new_cutouts.append(res)
                
        new_screws = []
        if screws:
            for sx, sy in screws:
                if raw_base_cutter.contains(Point(sx, sy)):
                    new_screws.append((sx + x_shift, sy))
                    
        return new_outline, new_cutouts, new_screws

    left_out, left_cuts, left_screws = process_half(left_cutter, poly_left_base)
    right_out, right_cuts, right_screws = process_half(right_cutter, poly_right_base, x_shift=gap)
    
    return (left_out, left_cuts, left_screws), (right_out, right_cuts, right_screws)


def generate_plate(kle_path=None, out_path=None, pcb_path=None,
                   switch_type=1, stab_type=0, kerf=0.0, pad=0.0,
                   screw_diameter=2.4, pcb_dx=0.0, pcb_dy=0.0,
                   no_auto_align=False, clearance=0.5, snap_screws=False,
                   fillet=0.0, screw_preset=None, screw_custom=None,
                   screw_inset=5.0, kle_text=None, split=False, puzzle_split=False,
                   gen_dxf=True, gen_gerber=True, gen_stl=True):
    log.info(
        "generate_plate start out=%s pcb=%s switch_type=%s stab_type=%s kerf=%s pad=%s "
        "screw_diameter=%s pcb_dx=%s pcb_dy=%s no_auto_align=%s clearance=%s snap_screws=%s "
        "fillet=%s screw_preset=%s screw_custom=%s screw_inset=%s split=%s puzzle_split=%s "
        "gen_dxf=%s gen_gerber=%s gen_stl=%s",
        out_path, pcb_path, switch_type, stab_type, kerf, pad,
        screw_diameter, pcb_dx, pcb_dy, no_auto_align, clearance, snap_screws,
        fillet, screw_preset, screw_custom, screw_inset, split, puzzle_split,
        gen_dxf, gen_gerber, gen_stl,
    )
    if kle_text: raw_text = kle_text
    elif kle_path: raw_text = Path(kle_path).read_text(encoding='utf-8')
    else: raise ValueError("No KLE input provided")
    
    # Pre-process for KLE "Raw Data" quirks
    text_to_parse = raw_text.strip()
    # 1. Quote unquoted keys like {w:2}
    sanitized = re.sub(r'([{,]\s*)([a-zA-Z_]\w*)\s*:', r'\1"\2":', text_to_parse)
    
    try:
        json_data = json.loads(sanitized)
    except json.JSONDecodeError:
        # 2. Try wrapping in brackets if the user pasted rows directly without outer []
        try:
            # Handle potential trailing commas when wrapping
            potential_json = sanitized.rstrip(',')
            json_data = json.loads(f"[{potential_json}]")
        except Exception:
            raise ValueError("Invalid KLE JSON format. Ensure it is a valid list of rows.")

    keys, key_w, key_h = parse_kle(json_data)
    log.debug("parsed KLE: keys=%d key_w=%.3f key_h=%.3f", len(keys), key_w, key_h)
    
    all_cutouts = build_entities(keys, pad=0.0, kerf=kerf, switch_type=switch_type, stab_type=stab_type)
    sw_polys = all_cutouts
    st_polys = []
    
    screw_radius = screw_diameter / 2.0
    screws = None
    if screw_custom: 
        screws = screw_presets.custom_from_string(screw_custom, key_w, key_h)
    elif screw_preset:
        fn = screw_presets.PRESETS[screw_preset]
        screws = fn(keys, key_w, 0.0, screw_inset, U1) if screw_preset == 'between_rows' else fn(key_w, key_h, inset=screw_inset)
    elif pcb_path:
        screws = find_kicad_screw_holes(pcb_path)
        pcb_sw, kle_sw = find_kicad_switches(pcb_path), [(k['cx_u']*U1, k['cy_u']*U1) for k in keys]
        log.debug("pcb extract: screws=%d pcb_switches=%d kle_switches=%d", len(screws), len(pcb_sw), len(kle_sw))
        params, apply = solve_pcb_transform(pcb_sw, kle_sw)
        log.debug("solve_pcb_transform params=%s", params)
        nudge = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
        screws = nudge(screws)
        if snap_screws: screws = snap_screws_to_grid(screws, kle_sw)
        
    pcb_outline_poly = None
    pcb_raw_segments = []

    if pcb_path:
        pcb_sw = find_kicad_switches(pcb_path)
        kle_sw = [(k['cx_u']*U1, k['cy_u']*U1) for k in keys]
        _, apply = solve_pcb_transform(pcb_sw, kle_sw)
        nudge = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
        pcb_edge_segs = find_all_edge_cuts(pcb_path)
        log.debug("edge_cuts raw: segments=%d (lines+arcs)", len(pcb_edge_segs))
        if pcb_edge_segs:
            pcb_raw_segments = [transform_segment(s, nudge) for s in pcb_edge_segs]
            closed_loops, open_chains = chain_polylines(pcb_raw_segments)
            log.debug("legacy_chain: closed_loops=%d open_chains=%d", len(closed_loops), len(open_chains))
            polys = []
            for loop in closed_loops:
                try:
                    p = Polygon(loop)
                    if p.is_valid and p.area > 10.0: polys.append(p)
                except: pass
            log.debug("valid polys from loops: %d", len(polys))
            if polys:
                # Sort by area descending to pick the largest one
                polys.sort(key=lambda p: p.area, reverse=True)
                
                # We need a minimum area threshold to avoid picking tiny artifacts as the outline
                # 100mm^2 is roughly 10x10mm, very safe for a keyboard outline
                valid_outlines = [p for p in polys if p.area > 500.0]
                
                if valid_outlines:
                    pcb_outline_poly = valid_outlines[0]
                    log.info("pcb_outline_poly selected area=%.2f bounds=%s", pcb_outline_poly.area, pcb_outline_poly.bounds)
                    
                    # Treat ALL other valid polygons from the Edge.Cuts as cutouts.
                    for p in polys:
                        if p != pcb_outline_poly:
                            log.debug("adding internal loop (flex/cutout) area=%.2f", p.area)
                            all_cutouts.append(p)
                else:
                    log.warning("No polygons large enough to be an outline (largest area=%.2f)", polys[0].area)
                    # Fallback to the largest one anyway if we have nothing else
                    pcb_outline_poly = polys[0]
            else:
                log.warning("pcb edge segments found but no valid closed polygons — outline will fall back to bbox")
                    
    if split:
        key_boxes = []
        for k in keys:
            cx, cy = k['cx_u'] * U1, k['cy_u'] * U1
            angle = k.get('_r_ccw', 0)
            b = box(cx - U1/2, cy - U1/2, cx + U1/2, cy + U1/2)
            if angle: b = affinity.rotate(b, angle, origin=(cx, cy))
            key_boxes.append(b)
        outline_poly = unary_union(key_boxes).buffer(pad, join_style=1)
    else: outline_poly = box(-pad, -pad, key_w + pad, key_h + pad)
    
    if fillet > 0: outline_poly = outline_poly.buffer(-fillet).buffer(fillet)
    
    if pcb_outline_poly is not None:
        outline_poly = pcb_outline_poly
        if pad > 0: outline_poly = outline_poly.buffer(pad, join_style=1)
        if fillet > 0: outline_poly = outline_poly.buffer(-fillet).buffer(fillet)
    elif pcb_raw_segments:
        pts = []
        for s in pcb_raw_segments: pts.extend(s[1:3] if s[0]=='line' else s[1:4])
        outline_poly = box(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        
    if pcb_raw_segments:
        pts = []
        for s in pcb_raw_segments: pts.extend(s[1:3] if s[0]=='line' else s[1:4])
        minx, miny = min(p[0] for p in pts), min(p[1] for p in pts)
    else: minx, miny, _, _ = outline_poly.bounds
    
    shift_x, shift_y = -minx, -miny
    outline_poly = affinity.translate(outline_poly, xoff=shift_x, yoff=shift_y)
    sw_polys = [affinity.translate(c, xoff=shift_x, yoff=shift_y) for c in sw_polys]
    st_polys = [affinity.translate(c, xoff=shift_x, yoff=shift_y) for c in st_polys]
    all_cutouts = sw_polys + st_polys
    if screws: screws = [(x+shift_x, y+shift_y) for x,y in screws]
    
    if pcb_raw_segments:
        shifted_raw = []
        for seg in pcb_raw_segments:
            if seg[0] == 'line':
                p1, p2 = seg[1], seg[2]
                shifted_raw.append(('line', (p1[0]+shift_x, p1[1]+shift_y), (p2[0]+shift_x, p2[1]+shift_y)))
            elif seg[0] == 'arc':
                p1, p2, p3 = seg[1], seg[2], seg[3]
                shifted_raw.append(('arc', (p1[0]+shift_x, p1[1]+shift_y), (p2[0]+shift_x, p2[1]+shift_y), (p3[0]+shift_x, p3[1]+shift_y)))
        pcb_raw_segments = shifted_raw
        
    outline_segments = []
    use_raw = bool(pcb_raw_segments) and pad == 0 and fillet == 0
    log.info(
        "outline source decision: pcb_raw_segments=%d pad=%s fillet=%s -> use_raw_segments=%s",
        len(pcb_raw_segments), pad, fillet, use_raw,
    )
    if use_raw:
        outline_segments = pcb_raw_segments
    else:
        # Fallback to SwillKB Poker style injection if PCB features are skipped/missing
        if screw_preset == 'poker' or (not pcb_raw_segments):
            log.debug("applying poker cutins (screw_preset=%s, raw_segs_present=%s)", screw_preset, bool(pcb_raw_segments))
            plate_w_temp, plate_h_temp = outline_poly.bounds[2], outline_poly.bounds[3]
            outline_poly = apply_poker_cutins(outline_poly, plate_w_temp, plate_h_temp)

        def poly_to_segs(p):
            pts = list(p.exterior.coords)
            segs = [('line', pts[i], pts[i+1]) for i in range(len(pts)-1)]
            for interior in p.interiors:
                ipts = list(interior.coords)
                segs.extend([('line', ipts[j], ipts[j+1]) for j in range(len(ipts)-1)])
            return segs
            
        if isinstance(outline_poly, Polygon): outline_segments = poly_to_segs(outline_poly)
        elif isinstance(outline_poly, MultiPolygon):
            for p in outline_poly.geoms: outline_segments.extend(poly_to_segs(p))

    # --- Validation Check for Notches/Cut-ins ---
    is_simple_box = True
    if outline_segments:
        has_arcs = any(seg[0] == 'arc' for seg in outline_segments)
        if has_arcs or len(outline_segments) > 4:
            is_simple_box = False
    log.info(
        "outline classification: segments=%d arcs=%d is_simple_box=%s",
        len(outline_segments),
        sum(1 for s in outline_segments if s[0] == 'arc'),
        is_simple_box,
    )

    issues = validate_screws(screws or [], screw_radius, outline_poly, all_cutouts, clearance)

    if is_simple_box:
        log.warning("outline collapsed to simple rectangle — applying poker override (pcb_path=%s pad=%s fillet=%s)", pcb_path, pad, fillet)
        issues.append((-1, 'warning_simple_box', 0.0))
        # SWILLKB POKER OVERRIDE - if it's still a simple box, forcefully apply cut-ins and regenerate segments
        plate_w_temp, plate_h_temp = outline_poly.bounds[2], outline_poly.bounds[3]
        outline_poly = apply_poker_cutins(outline_poly, plate_w_temp, plate_h_temp)
        
        def poly_to_segs(p):
            pts = list(p.exterior.coords)
            segs = [('line', pts[i], pts[i+1]) for i in range(len(pts)-1)]
            for interior in p.interiors:
                ipts = list(interior.coords)
                segs.extend([('line', ipts[j], ipts[j+1]) for j in range(len(ipts)-1)])
            return segs
            
        outline_segments = []
        if isinstance(outline_poly, Polygon): outline_segments = poly_to_segs(outline_poly)
        elif isinstance(outline_poly, MultiPolygon):
            for p in outline_poly.geoms: outline_segments.extend(poly_to_segs(p))
            
        print("\n=======================================================")
        print("WARNING: The generated outline was a simple rectangle.")
        print("SwillKB Poker Cut-ins have been forcefully injected to the plate edge.")
        print("=======================================================\n")

    if puzzle_split:
        log.info("applying puzzle split to geometry")
        (l_out, l_cuts, l_screws), (r_out, r_cuts, r_screws) = apply_puzzle_split(outline_poly, all_cutouts, screws, gap=10.0)
        
        # Re-combine for emission
        outline_poly = MultiPolygon([l_out, r_out]) if isinstance(l_out, Polygon) and isinstance(r_out, Polygon) else unary_union([l_out, r_out])
        all_cutouts = l_cuts + r_cuts
        screws = l_screws + r_screws
        
        # Re-distribute to sw/st for the legacy emitter counts (approximate)
        sw_polys = [p for p in all_cutouts if p.area < 250] # MX is ~196mm2
        st_polys = [p for p in all_cutouts if p.area >= 250]
        
        # Update segments for DXF outline
        def poly_to_segs(p):
            pts = list(p.exterior.coords)
            segs = [('line', pts[i], pts[i+1]) for i in range(len(pts)-1)]
            for interior in p.interiors:
                ipts = list(interior.coords)
                segs.extend([('line', ipts[j], ipts[j+1]) for j in range(len(ipts)-1)])
            return segs
        
        outline_segments = []
        if isinstance(outline_poly, Polygon): outline_segments = poly_to_segs(outline_poly)
        elif hasattr(outline_poly, 'geoms'):
            for p in outline_poly.geoms: outline_segments.extend(poly_to_segs(p))

    plate_w_final, plate_h_final = outline_poly.bounds[2], outline_poly.bounds[3]
    log.info(
        "emit summary: plate=%.2fx%.2fmm outline_segments=%d switch_polys=%d stab_polys=%d screws=%d issues=%d",
        plate_w_final, plate_h_final, len(outline_segments), len(sw_polys), len(st_polys),
        len(screws or []), len(issues),
    )

    if gen_dxf:
        log.debug("writing DXF -> %s", out_path)
        emit_dxf(out_path, sw_polys, st_polys, screws, outline_segments, screw_radius, outline_poly=outline_poly)
    
    # SVG preview - we use the full MultiPolygon outline here
    svg = generate_svg_string(plate_w_final, plate_h_final, outline_poly, sw_polys, st_polys, screws, screw_radius, outline_segments=outline_segments if pcb_raw_segments and pad == 0 and fillet == 0 and not puzzle_split else None)
    
    try: from . import exporters
    except ImportError: import exporters
    res = {"keys": len(keys), "plate_w": plate_w_final, "plate_h": plate_h_final, "screws": len(screws or []), "issues": issues, "out_path": out_path if gen_dxf else None, "svg": svg, "gerber_path": None, "stl_path": None, "gerber_error": None, "stl_error": None}
    
    if gen_gerber:
        gerber_path = str(Path(out_path).with_suffix('.zip'))
        try:
            exporters.export_gerber(outline_poly, all_cutouts, screws, screw_radius, gerber_path)
            res["gerber_path"] = gerber_path
        except Exception as e:
            res["gerber_error"] = f"{type(e).__name__}: {e}"
            log.exception("export_gerber failed")

    if gen_stl:
        stl_path = str(Path(out_path).with_suffix('.stl'))
        try:
            # Pass our already split geometry to STL exporter.
            exporters.export_stl(outline_poly, all_cutouts, screws, screw_radius, stl_path, thickness=1.5)
            res["stl_path"] = stl_path
        except Exception as e:
            res["stl_error"] = f"{type(e).__name__}: {e}"
            log.exception("export_stl failed")

    log.info("generate_plate done keys=%d screws=%d issues=%d", res["keys"], res["screws"], len(res["issues"]))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kle', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--pcb'); ap.add_argument('--switch-type', type=int, default=1)
    ap.add_argument('--stab-type', type=int, default=0); ap.add_argument('--kerf', type=float, default=0.0)
    ap.add_argument('--pad', type=float, default=0.0); ap.add_argument('--screw-diameter', type=float, default=2.4)
    ap.add_argument('--pcb-dx', type=float, default=0.0); ap.add_argument('--pcb-dy', type=float, default=0.0)
    ap.add_argument('--no-auto-align', action='store_true'); ap.add_argument('--clearance', type=float, default=0.5)
    ap.add_argument('--snap-screws', action='store_true'); ap.add_argument('--fillet', type=float, default=0.0)
    ap.add_argument('--screw-preset'); ap.add_argument('--screw-custom'); ap.add_argument('--screw-inset', type=float, default=5.0)
    args = ap.parse_args()
    res = generate_plate(args.kle, args.out, pcb_path=args.pcb, switch_type=args.switch_type, stab_type=args.stab_type, kerf=args.kerf, pad=args.pad, screw_diameter=args.screw_diameter, pcb_dx=args.pcb_dx, pcb_dy=args.pcb_dy, no_auto_align=args.no_auto_align, clearance=args.clearance, snap_screws=args.snap_screws, fillet=args.fillet, screw_preset=args.screw_preset, screw_custom=args.screw_custom, screw_inset=args.screw_inset)
    print(f"keys={res['keys']} plate={res['plate_w']:.2f}x{res['plate_h']:.2f}mm screws={res['screws']} -> {res['out_path']}")
    if res['issues']:
        for i, k, d in res['issues']: print(f"  screw#{i} {k} dist={d:.2f}mm")
        raise SystemExit(1)

if __name__ == '__main__':
    main()
