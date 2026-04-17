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
    
    # Try the "Normal" winning offset
    dx, dy = -52, 20
    
    overlaps = []
    out = []
    for sx, sy in screws:
        nx, ny = sx + dx, sy + dy
        if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
            out.append((nx, ny))
        for px, py, pw, ph in plate_holes:
            d = math.sqrt((nx-px)**2 + (ny-py)**2)
            if d < 8.55:
                overlaps.append((d, nx, ny, px, py))
    
    print(f"Testing Normal with dx={dx}, dy={dy}:")
    print(f"  Overlaps: {len(overlaps)}")
    for d, nx, ny, px, py in overlaps:
        print(f"    - {d:.2f}mm conflict at ({nx:.1f}, {ny:.1f})")
    print(f"  Out of bounds: {len(out)}")
    for ox, oy in out:
        print(f"    - ({ox:.1f}, {oy:.1f})")

if __name__ == "__main__": main()
