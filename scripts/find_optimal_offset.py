#!/usr/bin/env python3
"""
Find optimal (dx, dy) offset to align PCB screw holes with plate holes.
"""

import re
import math
from pathlib import Path
import ezdxf

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return holes

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    h_lines = {}
    v_lines = {}
    entities = list(msp.query('LINE LWPOLYLINE'))
    segments = []
    for entity in entities:
        if entity.dxftype() == 'LINE':
            segments.append((entity.dxf.start, entity.dxf.end))
        elif entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.vertices())
            if not points: continue
            if entity.closed: points.append(points[0])
            for i in range(len(points)-1):
                segments.append((points[i], points[i+1]))
    for start, end in segments:
        x1, y1 = start[0], start[1]
        x2, y2 = end[0], end[1]
        if abs(y1 - y2) < 0.1:
            y = round(y1, 1)
            if y not in h_lines: h_lines[y] = []
            h_lines[y].append((min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 0.1:
            x = round(x1, 1)
            if x not in v_lines: v_lines[x] = []
            v_lines[x].append((min(y1, y2), max(y1, y2)))
    rectangles = []
    tolerance = 0.5
    for y1 in sorted(h_lines.keys()):
        for y2 in sorted(h_lines.keys()):
            if y1 >= y2: continue
            height = abs(y2 - y1)
            if height < 2 or height > 50: continue
            for (x1a, x1b) in h_lines[y1]:
                for (x2a, x2b) in h_lines[y2]:
                    x_left = max(x1a, x2a)
                    x_right = min(x1b, x2b)
                    width = x_right - x_left
                    if width < 2 or width > 50: continue
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
        if found_cluster is None: clusters.append([r])
        else: found_cluster.append(r)
    unique = []
    for cluster in clusters:
        largest = max(cluster, key=lambda r: r[2] * r[3])
        unique.append(largest)
    return unique

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\new96.dxf")

    screw_holes = find_kicad_screw_holes(kicad)
    plate_holes = find_rectangles_from_lines(plate_dxf)
    
    xs = [p[0] - p[2]/2 for p in plate_holes] + [p[0] + p[2]/2 for p in plate_holes]
    ys = [p[1] - p[3]/2 for p in plate_holes] + [p[1] + p[3]/2 for p in plate_holes]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    
    print(f"Plate bounds: X({min_x:.1f}, {max_x:.1f}), Y({min_y:.1f}, {max_y:.1f})")
    
    best_offset = (0, 0)
    min_overlaps = 999
    min_out_of_bounds = 999
    
    # Brute force search for best offset
    # Range of dx: -100 to 100, dy: -200 to 200 (based on initial findings)
    overlap_threshold = 8.55
    
    print("Searching for optimal offset...")
    
    for dy in range(-150, 50, 2):
        for dx in range(-100, 50, 2):
            out_of_bounds = 0
            overlaps = 0
            
            for sx, sy in screw_holes:
                nx, ny = sx + dx, sy + dy
                if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                    out_of_bounds += 1
                
                for px, py, pw, ph in plate_holes:
                    if distance((nx, ny), (px, py)) < overlap_threshold:
                        overlaps += 1
            
            if out_of_bounds < min_out_of_bounds or (out_of_bounds == min_out_of_bounds and overlaps < min_overlaps):
                min_out_of_bounds = out_of_bounds
                min_overlaps = overlaps
                best_offset = (dx, dy)
                if min_out_of_bounds == 0 and min_overlaps == 0:
                    break
        if min_out_of_bounds == 0 and min_overlaps == 0:
            break

    print(f"Best Offset Found: dx={best_offset[0]}, dy={best_offset[1]}")
    print(f"Out of bounds: {min_out_of_bounds}")
    print(f"Overlaps: {min_overlaps}")

if __name__ == "__main__":
    main()
