#!/usr/bin/env python3
"""
Compare PCB and plate elements with detailed overlap analysis
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

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return sorted(holes, key=lambda h: (h[1], h[0]))

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")

    print("\n" + "="*80)
    print("PCB vs PLATE DETAILED COMPARISON")
    print("="*80 + "\n")

    # Extract PCB screw holes
    screw_holes = find_kicad_screw_holes(kicad)

    # Extract plate holes
    rects = find_rectangles_from_lines(plate_dxf)
    switches, combos, stabs = classify_holes(rects)

    print(f"PLATE HOLES:")
    print(f"  Switches: {len(switches)}")
    print(f"  Combos: {len(combos)}")
    print(f"  Stabilizers: {len(stabs)}")
    print(f"  Total: {len(switches) + len(combos) + len(stabs)}\n")

    print(f"PCB ELEMENTS:")
    print(f"  Screw holes: {len(screw_holes)}\n")

    # Analyze each screw hole
    print("="*80)
    print("SCREW HOLE PLACEMENT ANALYSIS")
    print("="*80 + "\n")

    all_plate_holes = switches + combos + stabs

    for i, (sx, sy) in enumerate(screw_holes, 1):
        nearest = None
        nearest_dist = float('inf')
        for ph_type, hole_list in [('Switch', switches), ('Combo', combos), ('Stab', stabs)]:
            for cx, cy, w, h in hole_list:
                d = distance((sx, sy), (cx, cy))
                if d < nearest_dist:
                    nearest_dist = d
                    nearest = (ph_type, (cx, cy), d)

        status = "OK" if nearest_dist > 8.55 else "WARN"
        print(f"[{i:2d}] Screw at ({sx:7.1f}, {sy:7.1f})")
        if nearest:
            nearest_type, (nearest_cx, nearest_cy), dist = nearest
            print(f"     {status} Nearest: {nearest_type:6s} at ({nearest_cx:7.1f}, {nearest_cy:7.1f}) = {dist:5.2f}mm")
        print()

    # Summary
    print("="*80)
    print("CLEARANCE SUMMARY")
    print("="*80 + "\n")

    conflicts = 0
    for sx, sy in screw_holes:
        for cx, cy, w, h in all_plate_holes:
            d = distance((sx, sy), (cx, cy))
            if d < 8.55:
                conflicts += 1

    print(f"Safe clearance threshold: 8.55mm")
    print(f"  (1.1mm screw radius + 6.95mm switch half-width + 0.5mm tolerance)\n")
    print(f"Conflicts (< 8.55mm): {conflicts}")
    if conflicts == 0:
        print("Status: PASS - All screw holes clear")
    else:
        print(f"Status: WARNING - {conflicts} marginal conflicts found")

if __name__ == "__main__":
    main()
