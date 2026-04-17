#!/usr/bin/env python3
import re
import math
from pathlib import Path
import ezdxf

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f: content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        holes.append((float(match.group(1)), float(match.group(2))))
    return holes

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    h_lines, v_lines = {}, {}
    entities = list(msp.query('LINE LWPOLYLINE'))
    segments = []
    for entity in entities:
        if entity.dxftype() == 'LINE': segments.append((entity.dxf.start, entity.dxf.end))
        elif entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.vertices())
            if not points: continue
            if entity.closed: points.append(points[0])
            for i in range(len(points)-1): segments.append((points[i], points[i+1]))
    for start, end in segments:
        x1, y1, x2, y2 = start[0], start[1], end[0], end[1]
        if abs(y1 - y2) < 0.1:
            y = round(y1, 1)
            if y not in h_lines: h_lines[y] = []
            h_lines[y].append((min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 0.1:
            x = round(x1, 1)
            if x not in v_lines: v_lines[x] = []
            v_lines[x].append((min(y1, y2), max(y1, y2)))
    rectangles = []
    for y1 in sorted(h_lines.keys()):
        for y2 in sorted(h_lines.keys()):
            if y1 >= y2: continue
            height = abs(y2 - y1)
            if height < 2 or height > 50: continue
            for (x1a, x1b) in h_lines[y1]:
                for (x2a, x2b) in h_lines[y2]:
                    x_left, x_right = max(x1a, x2a), min(x1b, x2b)
                    width = x_right - x_left
                    if width < 2 or width > 50: continue
                    if any(abs(v - x_left) < 0.5 for v in v_lines.keys()) and any(abs(v - x_right) < 0.5 for v in v_lines.keys()):
                        rectangles.append(((x_left + x_right) / 2, (y1 + y2) / 2, width, height))
    clusters = []
    for r in rectangles:
        found = False
        for c in clusters:
            if abs(r[0]-c[0][0]) < 5 and abs(r[1]-c[0][1]) < 5:
                c.append(r); found = True; break
        if not found: clusters.append([r])
    return [max(c, key=lambda x: x[2]*x[3]) for c in clusters]

def distance(p1, p2): return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\new96.dxf")
    screw_holes = find_kicad_screw_holes(kicad)
    plate_holes = find_rectangles_from_lines(plate_dxf)
    xs = [p[0] for p in plate_holes]; ys = [p[1] for p in plate_holes]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    
    print("Searching for MIRROR alignment...")
    best_offset, min_overlaps, min_out = (0,0), 999, 999
    
    # Try mirror X around the center of the PCB screws
    pcb_xs = [h[0] for h in screw_holes]
    pcb_center_x = (min(pcb_xs) + max(pcb_xs)) / 2
    
    for dy in range(-150, 50, 5):
        for dx in range(-100, 100, 5):
            out, overlaps = 0, 0
            for sx, sy in screw_holes:
                # Mirror sx around pcb_center_x
                mx = pcb_center_x - (sx - pcb_center_x)
                nx, ny = mx + dx, sy + dy
                if not (min_x-20 <= nx <= max_x+20 and min_y-20 <= ny <= max_y+20): out += 1
                for px, py, pw, ph in plate_holes:
                    if distance((nx, ny), (px, py)) < 8.55: overlaps += 1
            if out < min_out or (out == min_out and overlaps < min_overlaps):
                min_out, min_overlaps, best_offset = out, overlaps, (dx, dy)
    
    print(f"Best MIRROR Offset: dx={best_offset[0]}, dy={best_offset[1]}, Out={min_out}, Overlaps={min_overlaps}")

if __name__ == "__main__": main()
