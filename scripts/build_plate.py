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
from collections import defaultdict

import ezdxf
from shapely.geometry import Polygon, MultiPolygon, Point, box
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
    # Clockwise rotation in Y-down system (standard Trig formula is correct here)
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
    if (bx-ax)*(cy-ay) - (by-ay)*(cx-ax) < 0: s, e = e, s
    return (ux, uy), r, s, e


# ---------- parsers ----------

def parse_kle(layout):
    """
    Robust KLE parser matching official specification.
    KLE uses a Y-down coordinate system and clockwise angles.
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
                # rx/ry reset the cursor to the new origin. r does NOT reset the cursor.
                if 'rx' in item: rx = item['rx']
                if 'ry' in item: ry = item['ry']
                if 'rx' in item or 'ry' in item:
                    kx, ky = rx, ry
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
    cutout_polys = []
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
        stab_shapes = []
        if (2 <= w < 3) or (rotate_stab and 2 <= h < 3):
            stab_shapes = cutout_registry.get_stab_2u(s)
        elif w >= 3 or (rotate_stab and h >= 3):
            l = h if rotate_stab else w
            s_str = str(l).replace('.', '').ljust(3, '0')
            x_off = STAB_WIDTHS.get(s_str[:3], 11.95)
            stab_shapes = cutout_registry.get_stab_space(s, x_off)
        key_polys = []
        if not stab_shapes or s == 2:
            pts = cutout_registry.SWITCH_TYPES.get(t, cutout_registry.SWITCH_TYPES[0])
            p = Polygon(pts)
            if rs: p = affinity.rotate(p, rs, origin=(0, 0))
            key_polys.append(p)
        for pts in stab_shapes:
            p = Polygon(pts)
            if rotate_stab: p = affinity.rotate(p, 90, origin=(0, 0))
            key_polys.append(p)
        if key_polys:
            merged = unary_union(key_polys)
            if r: merged = affinity.rotate(merged, r, origin=(0, 0))
            if k != 0: merged = merged.buffer(-k, join_style=2)
            cutout_polys.append(affinity.translate(merged, xoff=cx, yoff=cy))
    return cutout_polys


# ---------- extraction ----------

def find_kicad_screw_holes(kicad_path):
    content = Path(kicad_path).read_text()
    pat = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2))) for m in re.finditer(pat, content, re.DOTALL)]

def find_kicad_switches(kicad_path):
    content = Path(kicad_path).read_text()
    pat = r'\(footprint\s+"[^"]*SW_[^"]*"[^\(]*?\(layer[^\)]+\)[^\(]*?\(uuid[^\)]+\)\s*\(at\s+([-\d.]+)\s+([-\d.]+)'
    return [(float(m.group(1)), float(m.group(2))) for m in re.finditer(pat, content)]

def find_all_edge_cuts(kicad_path):
    content = Path(kicad_path).read_text()
    line_re = r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    arc_re = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    segs = []
    for m in re.finditer(line_re, content, re.DOTALL):
        segs.append(('line', (float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4)))))
    for m in re.finditer(arc_re, content, re.DOTALL):
        segs.append(('arc', (float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4))), (float(m.group(5)), float(m.group(6)))))
    return segs

def transform_segment(seg, apply_fn):
    if seg[0] == 'line': return ('line', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0])
    if seg[0] == 'arc': return ('arc', apply_fn([seg[1]])[0], apply_fn([seg[2]])[0], apply_fn([seg[3]])[0])
    return seg


# ---------- emitters ----------

def build_outline_segments(W, H, fillet=0.0):
    r = fillet
    if r <= 0: return [('line', (0,0), (W,0)), ('line', (W,0), (W,H)), ('line', (W,H), (0,H)), ('line', (0,H), (0,0))]
    s45, c45 = math.sin(math.radians(45)), math.cos(math.radians(45))
    return [
        ('line', (r, 0), (W-r, 0)), ('arc', (W-r, 0), (W-r+r*c45, r-r*s45), (W, r)),
        ('line', (W, r), (W, H-r)), ('arc', (W, H-r), (W-r+r*c45, H-r+r*s45), (W-r, H)),
        ('line', (W-r, H), (r, H)), ('arc', (r, H), (r-r*c45, H-r+r*s45), (0, H-r)),
        ('line', (0, H-r), (0, r)), ('arc', (0, r), (r-r*c45, r-r*s45), (r, 0))
    ]

def discretize_segments(segs, steps=30):
    pts = []
    for seg in segs:
        if seg[0] == 'line': pts.append(seg[1])
        elif seg[0] == 'arc':
            res = arc_from_3pts(seg[1], seg[2], seg[3])
            if not res: pts.append(seg[1]); continue
            (ux, uy), r, s, e = res
            sweep = (e - s) % 360
            for i in range(steps):
                ang = math.radians(s + sweep * i / steps)
                pts.append((ux + r * math.cos(ang), uy + r * math.sin(ang)))
    if segs: pts.append(segs[-1][2] if segs[-1][0]=='line' else segs[-1][3])
    return pts

def emit_dxf(out_path, cutouts_polys, screw_holes=None, outline_segments=None, screw_radius=1.2):
    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()
    for name, color in {L_OUTLINE: 7, L_SWITCH: 3, L_SCREW: 1}.items():
        doc.layers.add(name, color=color)
    if outline_segments:
        loops = []
        current_loop = []
        for i, seg in enumerate(outline_segments):
            if seg[0] == 'line':
                p1, p2 = seg[1], seg[2]
                if current_loop and math.hypot(p1[0]-current_loop[-1][0], p1[1]-current_loop[-1][1]) > 0.01:
                    loops.append(current_loop); current_loop = [p1, p2]
                else:
                    if not current_loop: current_loop.append(p1)
                    current_loop.append(p2)
            elif seg[0] == 'arc':
                s, m, e = seg[1], seg[2], seg[3]
                res = arc_from_3pts(s, m, e)
                if current_loop and math.hypot(s[0]-current_loop[-1][0], s[1]-current_loop[-1][1]) > 0.01:
                    loops.append(current_loop); current_loop = [s]
                elif not current_loop: current_loop.append(s)
                if not res: current_loop.append(e)
                else:
                    (ux, uy), r, start_ang, end_ang = res
                    sweep = (end_ang - start_ang) % 360
                    bulge = math.tan(math.radians(sweep) / 4.0)
                    prev = list(current_loop[-1])
                    if len(prev) < 5: prev.extend([0, 0, bulge])
                    else: prev[4] = bulge
                    current_loop[-1] = tuple(prev)
                    current_loop.append(e)
        if current_loop: loops.append(current_loop)
        for loop in loops:
            if len(loop) > 1:
                is_closed = math.hypot(loop[0][0]-loop[-1][0], loop[0][1]-loop[-1][1]) < 0.01
                pts = loop[:-1] if is_closed else loop
                msp.add_lwpolyline(pts, close=is_closed, dxfattribs={'layer': L_OUTLINE})

    def add_poly(p):
        coords = list(p.exterior.coords)
        if coords[0] == coords[-1]: coords = coords[:-1]
        msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': L_SWITCH})
        for interior in p.interiors:
            coords = list(interior.coords)
            if coords[0] == coords[-1]: coords = coords[:-1]
            msp.add_lwpolyline(coords, close=True, dxfattribs={'layer': L_SWITCH})
    for poly in cutouts_polys:
        if isinstance(poly, Polygon): add_poly(poly)
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: add_poly(p)
    for x, y in (screw_holes or []): msp.add_circle((x, y), screw_radius, dxfattribs={'layer': L_SCREW})
    doc.saveas(out_path)

def generate_svg_string(plate_w, plate_h, outline_poly, cutouts_polys, screws, screw_radius):
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
    if isinstance(outline_poly, Polygon): lines.append(f'<path d="{poly_to_path(outline_poly)}" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
    elif isinstance(outline_poly, MultiPolygon):
        for p in outline_poly.geoms: lines.append(f'<path d="{poly_to_path(p)}" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>')
    for poly in cutouts_polys:
        if isinstance(poly, Polygon): lines.append(f'<path d="{poly_to_path(poly)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms: lines.append(f'<path d="{poly_to_path(p)}" fill="#ffffff" stroke="#3b82f6" stroke-width="0.5"/>')
    for sx, sy in (screws or []): lines.append(f'<circle cx="{sx}" cy="{sy}" r="{screw_radius}" fill="#ffffff" stroke="#ef4444" stroke-width="0.5"/>')
    lines.extend(['</g>', '</svg>'])
    return "\n".join(lines)


# ---------- core api ----------

def generate_plate(kle_path=None, out_path=None, pcb_path=None,
                   switch_type=1, stab_type=0, kerf=0.0, pad=0.0,
                   screw_diameter=2.4, pcb_dx=0.0, pcb_dy=0.0,
                   no_auto_align=False, clearance=0.5, snap_screws=False,
                   fillet=0.0, screw_preset=None, screw_custom=None,
                   screw_inset=5.0, kle_text=None, split=False):
    if kle_text: raw_text = kle_text
    elif kle_path: raw_text = Path(kle_path).read_text(encoding='utf-8')
    else: raise ValueError("No KLE input provided")
        
    sanitized = re.sub(r'([{,]\s*)([a-zA-Z_]\w*)\s*:', r'\1"\2":', raw_text)
    keys, plate_w, plate_h = parse_kle(json.loads(sanitized))
    cutouts = build_entities(keys, pad=pad, kerf=kerf, switch_type=switch_type, stab_type=stab_type)
    screw_radius = screw_diameter / 2.0
    screws = None
    if screw_custom: screws = screw_presets.custom_from_string(screw_custom, plate_w, plate_h)
    elif screw_preset:
        fn = screw_presets.PRESETS[screw_preset]
        screws = fn(keys, plate_w, pad, screw_inset, U1) if screw_preset == 'between_rows' else fn(plate_w, plate_h, inset=screw_inset)
    elif pcb_path:
        screws = find_kicad_screw_holes(pcb_path)
        pcb_sw, kle_sw = find_kicad_switches(pcb_path), [(k['cx_u']*U1+pad, k['cy_u']*U1+pad) for k in keys]
        params, apply = solve_pcb_transform(pcb_sw, kle_sw)
        nudge = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
        screws = nudge(screws)
        if snap_screws: screws = snap_screws_to_grid(screws, kle_sw)

    outline_segments = []
    if pcb_path:
        # Use full Edge.Cuts if available
        pcb_outline = find_all_edge_cuts(pcb_path)
        if pcb_outline:
            nudged_apply = lambda pts: [(x + pcb_dx, y + pcb_dy) for x, y in apply(pts)]
            outline_segments = [transform_segment(seg, nudged_apply) for seg in pcb_outline]
            outline_poly = Polygon(discretize_segments(outline_segments))
        else:
            outline_segments = build_outline_segments(plate_w, plate_h, fillet=fillet)
            outline_poly = Polygon(discretize_segments(outline_segments))
    elif split:
        key_boxes = []
        for k in keys:
            cx, cy = k['cx_u'] * U1 + pad, k['cy_u'] * U1 + pad
            angle = k.get('_r_ccw', 0)
            b = box(cx - U1/2, cy - U1/2, cx + U1/2, cy + U1/2)
            if angle: b = affinity.rotate(b, angle, origin=(cx, cy))
            key_boxes.append(b)
        outline_poly = unary_union(key_boxes).buffer(pad, join_style=1)
        if fillet > 0: outline_poly = outline_poly.buffer(-fillet).buffer(fillet)
        def poly_to_segs(p):
            pts = list(p.exterior.coords)
            return [('line', pts[i], pts[i+1]) for i in range(len(pts)-1)]
        if isinstance(outline_poly, Polygon): outline_segments = poly_to_segs(outline_poly)
        elif isinstance(outline_poly, MultiPolygon):
            for p in outline_poly.geoms: outline_segments.extend(poly_to_segs(p))
    else:
        outline_segments = build_outline_segments(plate_w, plate_h, fillet=fillet)
        outline_poly = Polygon(discretize_segments(outline_segments))

    issues = validate_screws(screws or [], screw_radius, outline_poly, cutouts, clearance)
    emit_dxf(out_path, cutouts, screws, outline_segments, screw_radius)
    svg = generate_svg_string(plate_w, plate_h, outline_poly, cutouts, screws, screw_radius)

    # Optional exports
    try:
        from . import exporters
    except ImportError:
        import exporters

    res = {
        "keys": len(keys),
        "plate_w": plate_w,
        "plate_h": plate_h,
        "screws": len(screws or []),
        "issues": issues,
        "out_path": out_path,
        "svg": svg
    }

    # Generate Gerber ZIP if requested
    gerber_path = str(Path(out_path).with_suffix('.zip'))
    try:
        exporters.export_gerber(outline_poly, cutouts, screws, screw_radius, gerber_path)
        res["gerber_path"] = gerber_path
    except Exception as e:
        print(f"Gerber export failed: {e}")

    # Generate STL if requested (usually always for web)
    stl_path = str(Path(out_path).with_suffix('.stl'))
    try:
        exporters.export_stl(outline_poly, cutouts, screws, screw_radius, stl_path)
        res["stl_path"] = stl_path
    except Exception as e:
        print(f"STL export failed: {e}")

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
