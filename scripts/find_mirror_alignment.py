#!/usr/bin/env python3
import re, math
from pathlib import Path
import ezdxf

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f: content = f.read()
    return [(float(m.group(1)), float(m.group(2))) for m in re.finditer(r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)', content, re.DOTALL)]

def find_rects(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    segs = []
    for e in msp.query('LINE LWPOLYLINE'):
        if e.dxftype() == 'LINE': segs.append((e.dxf.start, e.dxf.end))
        else:
            p = list(e.vertices())
            if not p: continue
            if e.closed: p.append(p[0])
            for i in range(len(p)-1): segs.append((p[i], p[i+1]))
    h, v = {}, {}
    for s, e in segs:
        if abs(s[1]-e[1]) < 0.1:
            y = round(s[1],1)
            if y not in h: h[y] = []
            h[y].append((min(s[0], e[0]), max(s[0], e[0])))
        elif abs(s[0]-e[0]) < 0.1:
            x = round(s[0],1)
            if x not in v: v[x] = []
            v[x].append((min(s[1], e[1]), max(s[1], e[1])))
    rects = []
    for y1 in sorted(h.keys()):
        for y2 in sorted(h.keys()):
            if y1 >= y2 or abs(y2-y1) < 2 or abs(y2-y1) > 50: continue
            for x1a, x1b in h[y1]:
                for x2a, x2b in h[y2]:
                    xl, xr = max(x1a, x2a), min(x1b, x2b)
                    if xr-xl < 2 or xr-xl > 50: continue
                    if any(abs(vx-xl)<0.5 for vx in v) and any(abs(vx-xr)<0.5 for vx in v):
                        rects.append(((xl+xr)/2, (y1+y2)/2, xr-xl, y2-y1))
    clusters = []
    for r in rects:
        found = False
        for c in clusters:
            if abs(r[0]-c[0][0]) < 5 and abs(r[1]-c[0][1]) < 5: c.append(r); found = True; break
        if not found: clusters.append([r])
    return [max(c, key=lambda x: x[2]*x[3]) for c in clusters]

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    dxf = Path(r"C:\Users\v-mariorivas\Downloads\unfucked.dxf")
    screws = find_kicad_screw_holes(kicad)
    plate_holes = find_rects(dxf)
    
    xs = [p[0] for p in plate_holes]; ys = [p[1] for p in plate_holes]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    plt_cx = (min_x + max_x) / 2
    
    pcb_xs = [s[0] for s in screws]; pcb_cx = (min(pcb_xs)+max(pcb_xs))/2
    
    print(f"Plate Bounds: X({min_x:.1f}-{max_x:.1f}) Y({min_y:.1f}-{max_y:.1f})")
    
    print("Trying MIRROR-X alignment...")
    best_dx, best_dy, min_overlaps, min_out = 0, 0, 999, 999
    
    # Mirror sx around pcb_cx then shift to match plt_cx
    # mirrored_sx = pcb_cx - (sx - pcb_cx)
    # nx = mirrored_sx + dx
    
    # Search for perfect alignment
    best_dx, best_dy, min_total_issues = 0, 0, 999
    
    print("Searching for PERFECT alignment (0 overlaps, 0 out-of-bounds)...")
    
    for dy in range(-150, 150, 1):
        for dx in range(-150, 150, 1):
            overlaps = 0
            out = 0
            # Check out of bounds first (faster)
            for sx, sy in screws:
                mx = pcb_cx - (sx - pcb_cx)
                nx, ny = mx + dx, sy + dy
                if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                    out += 1
            
            # Only check overlaps if out-of-bounds is low
            if out <= 2: # Allow some tolerance if perfect is not found
                for sx, sy in screws:
                    mx = pcb_cx - (sx - pcb_cx)
                    nx, ny = mx + dx, sy + dy
                    for px, py, pw, ph in plate_holes:
                        if math.sqrt((nx-px)**2 + (ny-py)**2) < 8.55:
                            overlaps += 1
                
                total_issues = overlaps + out
                if total_issues < min_total_issues:
                    min_total_issues = total_issues
                    best_dx, best_dy = dx, dy
                    if total_issues == 0: break
        if min_total_issues == 0: break
    
    print(f"Optimal Result: dx={best_dx}, dy={best_dy}, Total Issues={min_total_issues}")
    
    print(f"Optimal Mirror-X Result: dx={best_dx}, dy={best_dy}, Out={min_out}, Overlaps={min_overlaps}")
    
    # Debug report for best result
    print("\nDebug for best result:")
    for sx, sy in screws:
        mx = pcb_cx - (sx - pcb_cx)
        nx, ny = mx + best_dx, sy + best_dy
        in_bounds = (min_x <= nx <= max_x and min_y <= ny <= max_y)
        status = "IN" if in_bounds else "OUT"
        print(f"  Screw ({sx:.1f}, {sy:.1f}) -> ({nx:.1f}, {ny:.1f}) [{status}]")

if __name__ == "__main__": main()
