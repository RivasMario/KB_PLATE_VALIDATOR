#!/usr/bin/env python3
"""
Full validation: map PCB elements to plate, check overlaps & bounds
"""

import re
import math
from pathlib import Path
import ezdxf

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    h_lines = {}
    v_lines = {}
    tolerance = 0.5

    # Handle both LINE and LWPOLYLINE entities
    entities = list(msp.query('LINE LWPOLYLINE'))
    
    segments = []
    for entity in entities:
        if entity.dxftype() == 'LINE':
            segments.append((entity.dxf.start, entity.dxf.end))
        elif entity.dxftype() == 'LWPOLYLINE':
            # Get points from vertices
            points = list(entity.vertices())
            if not points:
                continue
            # If closed, add first point to end
            if entity.closed:
                points.append(points[0])
            for i in range(len(points)-1):
                segments.append((points[i], points[i+1]))

    for start, end in segments:
        x1, y1 = start[0], start[1]
        x2, y2 = end[0], end[1]

        if abs(y1 - y2) < 0.1:
            y = round(y1, 1)
            if y not in h_lines:
                h_lines[y] = []
            h_lines[y].append((min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 0.1:
            x = round(x1, 1)
            if x not in v_lines:
                v_lines[x] = []
            v_lines[x].append((min(y1, y2), max(y1, y2)))

    rectangles = []
    for y1 in sorted(h_lines.keys()):
        for y2 in sorted(h_lines.keys()):
            if y1 >= y2:
                continue
            height = abs(y2 - y1)
            if height < 2 or height > 50:
                continue
            for (x1a, x1b) in h_lines[y1]:
                for (x2a, x2b) in h_lines[y2]:
                    x_left = max(x1a, x2a)
                    x_right = min(x1b, x2b)
                    width = x_right - x_left
                    if width < 2 or width > 50:
                        continue
                    v_left = any(abs(v - x_left) < tolerance for v in v_lines.keys())
                    v_right = any(abs(v - x_right) < tolerance for v in v_lines.keys())
                    if v_left and v_right:
                        cx = (x_left + x_right) / 2
                        cy = (y1 + y2) / 2
                        rectangles.append((cx, cy, width, height))

    clusters = []
    for r in rectangles:
        found_cluster = None
        for cluster in clusters:
            if abs(r[0] - cluster[0][0]) < 5 and abs(r[1] - cluster[0][1]) < 5:
                found_cluster = cluster
                break
        if found_cluster is None:
            clusters.append([r])
        else:
            found_cluster.append(r)

    unique = []
    for cluster in clusters:
        largest = max(cluster, key=lambda r: r[2] * r[3])
        unique.append(largest)

    return sorted(unique, key=lambda r: (r[1], r[0]))

def classify_holes(rects):
    switches = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2]
    combos = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43]
    stabs = [(cx, cy, w, h) for cx, cy, w, h in rects if 8 < min(w,h) < 10 and 18 < max(w,h) < 26]
    return switches, combos, stabs

def get_plate_bounds(rects):
    if not rects:
        return None
    xs = [cx - w/2 for cx, cy, w, h in rects] + [cx + w/2 for cx, cy, w, h in rects]
    ys = [cy - h/2 for cx, cy, w, h in rects] + [cy + h/2 for cx, cy, w, h in rects]
    return min(xs), max(xs), min(ys), max(ys)

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return sorted(holes, key=lambda h: (h[1], h[0]))

def find_edge_cutouts(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    edges = []
    arc_pattern = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(arc_pattern, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = [float(match.group(i)) for i in range(1, 7)]
        edges.append(('arc', [(x1, y1), (x2, y2), (xm, ym)]))

    points = []
    for etype, pts in edges:
        for p in pts[:2]:
            points.append(p)
    if not points:
        return [], [], (0, 0, 0, 0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    left_cuts, bottom_cuts = [], []
    for etype, pts in edges:
        if etype != 'arc':
            continue
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        xm, ym = pts[2]
        if abs(x1 - min_x) < 5 and abs(x2 - min_x) < 5:
            depth = xm - min_x
            if depth >= 3.0:
                y = (y1 + y2) / 2
                left_cuts.append((xm, y, depth))
        if abs(y1 - max_y) < 5 and abs(y2 - max_y) < 5:
            depth = max_y - ym
            if depth >= 3.0:
                x = (x1 + x2) / 2
                bottom_cuts.append((x, y1, depth))
    return left_cuts, bottom_cuts, (min_x, max_x, min_y, max_y)

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def draw_map(left_cuts, bottom_cuts, screw_holes, switches, combos, stabs, bounds):
    min_x, max_x, min_y, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y

    scale = 5
    map_width = int(width / scale) + 4
    map_height = int(height / scale) + 4

    grid = [[' ' for _ in range(map_width)] for _ in range(map_height)]

    for i in range(map_height):
        grid[i][0] = '|'
        grid[i][-1] = '|'
    for j in range(map_width):
        grid[0][j] = '-'
        grid[-1][j] = '-'
    grid[0][0] = '+'
    grid[0][-1] = '+'
    grid[-1][0] = '+'
    grid[-1][-1] = '+'

    for x, y, d in left_cuts + bottom_cuts:
        col = int((x - min_x) / scale) + 1
        row = int((y - min_y) / scale) + 1
        if 0 < col < map_width and 0 < row < map_height:
            grid[row][col] = 'E'

    for x, y in screw_holes:
        col = int((x - min_x) / scale) + 1
        row = int((y - min_y) / scale) + 1
        if 0 < col < map_width and 0 < row < map_height:
            grid[row][col] = 'H'

    for cx, cy, w, h in switches:
        col = int((cx - min_x) / scale) + 1
        row = int((cy - min_y) / scale) + 1
        if 0 < col < map_width and 0 < row < map_height:
            grid[row][col] = 'S'

    for cx, cy, w, h in combos:
        col = int((cx - min_x) / scale) + 1
        row = int((cy - min_y) / scale) + 1
        if 0 < col < map_width and 0 < row < map_height:
            grid[row][col] = 'C'

    for cx, cy, w, h in stabs:
        col = int((cx - min_x) / scale) + 1
        row = int((cy - min_y) / scale) + 1
        if 0 < col < map_width and 0 < row < map_height:
            grid[row][col] = 'T'

    lines = []
    lines.append("ASCII MAP (scale 5mm per character)")
    lines.append("E=edge cutout, H=screw, S=switch, C=combo, T=stabilizer")
    lines.append("")
    for row in grid:
        lines.append(''.join(row))

    return '\n'.join(lines)

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch.dxf")

    print("\n" + "="*80)
    print("FULL VALIDATION - PCB TO PLATE MAPPING")
    print("="*80 + "\n")

    # Extract plate holes
    print("Scanning plate DXF...")
    rects = find_rectangles_from_lines(plate_dxf)
    switches, combos, stabs = classify_holes(rects)
    plate_bounds = get_plate_bounds(rects)

    print(f"PLATE HOLES:")
    print(f"  Switches: {len(switches)}")
    print(f"  Combos: {len(combos)}")
    print(f"  Stabilizers: {len(stabs)}")
    print(f"  Total: {len(switches) + len(combos) + len(stabs)}\n")

    # Extract PCB elements
    print("Scanning PCB KiCad file...")
    screw_holes = find_kicad_screw_holes(kicad)
    left_cuts, bottom_cuts, pcb_bounds = find_edge_cutouts(kicad)

    print(f"PCB ELEMENTS:")
    print(f"  Screw holes: {len(screw_holes)}")
    print(f"  Left edge cutouts: {len(left_cuts)}")
    print(f"  Bottom edge cutouts: {len(bottom_cuts)}\n")

    # Use plate bounds for map
    bounds = plate_bounds if plate_bounds else (0, 400, 0, 200)

    # Generate map
    print(draw_map(left_cuts, bottom_cuts, screw_holes, switches, combos, stabs, bounds))
    print()

    # Validation checks
    print("="*80)
    print("VALIDATION CHECKS")
    print("="*80)

    all_plate_holes = switches + combos + stabs
    min_x, max_x, min_y, max_y = bounds

    # Check 1: Screw holes within plate bounds
    print("\n[1] SCREW HOLES WITHIN PLATE BOUNDS")
    print(f"    Plate bounds: X({min_x:.1f}-{max_x:.1f}) Y({min_y:.1f}-{max_y:.1f})")
    out_of_bounds = 0
    for sx, sy in screw_holes:
        if not (min_x <= sx <= max_x and min_y <= sy <= max_y):
            print(f"    WARNING: Screw at ({sx:.1f}, {sy:.1f}) outside bounds")
            out_of_bounds += 1
    if out_of_bounds == 0:
        print(f"    PASS: All {len(screw_holes)} screw holes within bounds")
    else:
        print(f"    FAIL: {out_of_bounds} screw holes out of bounds")

    # Check 2: Edge cutouts on plate edges
    print("\n[2] EDGE CUTOUTS ON PLATE EDGES")
    edge_issues = 0
    for x, y, d in left_cuts:
        if abs(x - min_x) > 3:
            print(f"    WARNING: Left cutout at ({x:.1f}, {y:.1f}) not on left edge")
            edge_issues += 1
    for x, y, d in bottom_cuts:
        if abs(y - max_y) > 3:
            print(f"    WARNING: Bottom cutout at ({x:.1f}, {y:.1f}) not on bottom edge")
            edge_issues += 1
    total_edge = len(left_cuts) + len(bottom_cuts)
    if edge_issues == 0:
        print(f"    PASS: All {total_edge} edge cutouts on plate edges")
    else:
        print(f"    WARNING: {edge_issues} edge cutouts misaligned")

    # Check 3: No overlap between screw holes and plate holes
    print("\n[3] SCREW HOLES VS PLATE HOLES OVERLAP")
    overlap_threshold = 8.55
    overlaps = []
    for sx, sy in screw_holes:
        for ph in all_plate_holes:
            if len(ph) == 4:
                cx, cy, w, h = ph
                d = distance((sx, sy), (cx, cy))
                if d < overlap_threshold:
                    overlaps.append((d, (sx, sy), (cx, cy)))

    overlaps.sort()
    if not overlaps:
        print(f"    PASS: No overlaps (threshold: {overlap_threshold}mm)")
    else:
        print(f"    ISSUES FOUND: {len(overlaps)} marginal conflicts")
        for d, (sx, sy), (cx, cy) in overlaps[:5]:
            print(f"      Screw ({sx:.1f},{sy:.1f}) -> Plate ({cx:.1f},{cy:.1f}) = {d:.2f}mm")
        if len(overlaps) > 5:
            print(f"      ... and {len(overlaps)-5} more")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Plate holes detected: {len(all_plate_holes)}")
    print(f"PCB elements to place: {len(screw_holes) + total_edge}")
    print(f"Screw holes in bounds: {len(screw_holes) - out_of_bounds}/{len(screw_holes)}")
    print(f"Edge cutouts aligned: {total_edge - edge_issues}/{total_edge}")
    print(f"Overlaps detected: {len(overlaps)}")

    status = "PASS" if (out_of_bounds == 0 and edge_issues == 0 and len(overlaps) == 0) else "WARNING"
    print(f"\nOVERALL STATUS: {status}")

if __name__ == "__main__":
    main()
