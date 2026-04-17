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
            y = round(s[1],1); h.setdefault(y, []).append((min(s[0], e[0]), max(s[0], e[0])))
        elif abs(s[0]-e[0]) < 0.1:
            x = round(s[0],1); v.setdefault(x, []).append((min(s[1], e[1]), max(s[1], e[1])))
    rects = []
    for y1 in sorted(h.keys()):
        for y2 in sorted(h.keys()):
            if y1 >= y2 or abs(y2-y1) < 2: continue
            for x1a, x1b in h[y1]:
                for x2a, x2b in h[y2]:
                    xl, xr = max(x1a, x2a), min(x1b, x2b)
                    if xr-xl < 2: continue
                    if any(abs(vx-xl)<0.5 for vx in v) and any(abs(vx-xr)<0.5 for vx in v):
                        rects.append(((xl+xr)/2, (y1+y2)/2, xr-xl, y2-y1))
    clusters = []
    for r in rects:
        found = False
        for c in clusters:
            if abs(r[0]-c[0][0]) < 1 and abs(r[1]-c[0][1]) < 1: c.append(r); found = True; break
        if not found: clusters.append([r])
    return [max(c, key=lambda x: x[2]*x[3]) for c in clusters]

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    dxf = Path(r"C:\Users\v-mariorivas\Downloads\unfucked.dxf")
    screws = find_kicad_screw_holes(kicad)
    plate_holes = find_rects(dxf)
    
    xs = [p[0] for p in plate_holes]; ys = [p[1] for p in plate_holes]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    pcb_xs = [s[0] for s in screws]; pcb_cx = (min(pcb_xs)+max(pcb_xs))/2
    pcb_ys = [s[1] for s in screws]; pcb_cy = (min(pcb_ys)+max(pcb_ys))/2
    
    orientations = [
        ("Normal", lambda x,y: (x, y)),
        ("Mirror-X", lambda x,y: (pcb_cx - (x - pcb_cx), y)),
        ("Mirror-Y", lambda x,y: (x, pcb_cy - (y - pcb_cy))),
        ("Mirror-XY", lambda x,y: (pcb_cx - (x - pcb_cx), pcb_cy - (y - pcb_cy)))
    ]
    
    best_overall = None
    min_score = 999
    
    for name, transform in orientations:
        print(f"Testing {name}...")
        best_dx, best_dy, min_issues = 0, 0, 999
        for dy in range(-200, 100, 2):
            for dx in range(-200, 100, 2):
                overlaps = 0
                out = 0
                for sx, sy in screws:
                    nx, ny = transform(sx, sy)
                    nx += dx; ny += dy
                    if not (min_x <= nx <= max_x and min_y <= ny <= max_y): out += 1
                    for px, py, pw, ph in plate_holes:
                        if math.sqrt((nx-px)**2 + (ny-py)**2) < 8.55: overlaps += 1
                
                score = overlaps + out
                if score < min_issues:
                    min_issues = score
                    best_dx, best_dy = dx, dy
                    if score == 0: break
            if min_issues == 0: break
        
        print(f"  Best {name}: dx={best_dx}, dy={best_dy}, Issues={min_issues}")
        if min_issues < min_score:
            min_score = min_issues
            best_overall = (name, best_dx, best_dy)
            
    print(f"\nWINNER: {best_overall[0]} with dx={best_overall[1]}, dy={best_overall[2]} (Issues={min_score})")

if __name__ == "__main__": main()
