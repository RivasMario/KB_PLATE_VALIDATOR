#!/usr/bin/env python3
"""
SWILLKB (2) Complete Analysis
1. Extract PCB requirements (edge cutouts, screw holes)
2. Find plate holes (switches, combos, stabs)
3. Generate ASCII map
4. Validate no overlaps
"""

import re
import math
from pathlib import Path
import ezdxf

def find_edge_cutouts(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    edges = []
    line_pattern = r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(line_pattern, content, re.DOTALL):
        x1, y1, x2, y2 = [float(match.group(i)) for i in range(1, 5)]
        edges.append(('line', [(x1, y1), (x2, y2)]))
    arc_pattern = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(arc_pattern, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = [float(match.group(i)) for i in range(1, 7)]
        edges.append(('arc', [(x1, y1), (x2, y2), (xm, ym)]))
    points = []
    for etype, pts in edges:
        for p in pts[:2]:
            points.append(p)
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

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return sorted(holes, key=lambda h: (h[1], h[0]))

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    h_lines = {}
    v_lines = {}
    tolerance = 0.5

    for line in [e for e in msp if e.dxftype() == 'LINE']:
        x1, y1 = line.dxf.start.x, line.dxf.start.y
        x2, y2 = line.dxf.end.x, line.dxf.end.y

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

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def check_overlaps(left_cuts, bottom_cuts, screw_holes, switches, combos, stabs):
    """Check if PCB elements overlap with plate holes"""
    issues = []

    edge_cuts = left_cuts + bottom_cuts

    # Screw holes vs switches
    for sx, sy in screw_holes:
        for swx, swy, w, h in switches:
            d = distance((sx, sy), (swx, swy))
            if d < 1.1 + min(w, h)/2 + 0.5:  # 1.1mm screw radius + switch half-width
                issues.append(('screw_switch', (sx, sy), (swx, swy), d))

    # Screw holes vs combos
    for sx, sy in screw_holes:
        for cx, cy, w, h in combos:
            d = distance((sx, sy), (cx, cy))
            if d < 1.1 + min(w, h)/2 + 0.5:
                issues.append(('screw_combo', (sx, sy), (cx, cy), d))

    # Screw holes vs stabs
    for sx, sy in screw_holes:
        for stx, sty, w, h in stabs:
            d = distance((sx, sy), (stx, sty))
            if d < 1.1 + min(w, h)/2 + 0.5:
                issues.append(('screw_stab', (sx, sy), (stx, sty), d))

    return issues

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
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")

    print("\n" + "="*80)
    print("SWILLKB (2) - COMPLETE ANALYSIS")
    print("="*80 + "\n")

    # Extract PCB
    left_cuts, bottom_cuts, bounds = find_edge_cutouts(kicad)
    screw_holes = find_kicad_screw_holes(kicad)

    print("PCB ELEMENTS:")
    print(f"  Edge cutouts: {len(left_cuts)} left, {len(bottom_cuts)} bottom")
    print(f"  Screw holes: {len(screw_holes)}\n")

    # Extract plate
    rects = find_rectangles_from_lines(plate_dxf)
    switches, combos, stabs = classify_holes(rects)

    print("PLATE ELEMENTS:")
    print(f"  Switches: {len(switches)}")
    print(f"  Combos: {len(combos)}")
    print(f"  Stabilizers: {len(stabs)}\n")

    # Generate map
    print(draw_map(left_cuts, bottom_cuts, screw_holes, switches, combos, stabs, bounds))
    print()

    # Check overlaps
    print("="*80)
    print("OVERLAP CHECK")
    print("="*80)

    issues = check_overlaps(left_cuts, bottom_cuts, screw_holes, switches, combos, stabs)

    if issues:
        print(f"ISSUES FOUND: {len(issues)}\n")
        for issue_type, hole1, hole2, dist in issues[:10]:
            print(f"  {issue_type.upper()}")
            print(f"    PCB hole: ({hole1[0]:.1f}, {hole1[1]:.1f})")
            print(f"    Plate hole: ({hole2[0]:.1f}, {hole2[1]:.1f})")
            print(f"    Distance: {dist:.1f}mm")
        if len(issues) > 10:
            print(f"  ... and {len(issues)-10} more")
    else:
        print("PASS - No overlaps detected")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"PCB screw holes: {len(screw_holes)}")
    print(f"PCB edge cutouts: {len(left_cuts)+len(bottom_cuts)}")
    print(f"Plate total holes: {len(switches)+len(combos)+len(stabs)}")
    print(f"Overlap issues: {len(issues)}")

if __name__ == "__main__":
    main()
