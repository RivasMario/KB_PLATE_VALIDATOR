#!/usr/bin/env python3
import re, math
from pathlib import Path
import ezdxf

def find_kicad_elements(kicad_path):
    with open(kicad_path, 'r') as f: content = f.read()
    
    # 1. Find all footprints that are NOT mounting holes (switches, stabilizers)
    switches = []
    # Pattern to match footprint start and its 'at' coordinate
    # (footprint "..." (at X Y ...))
    for m in re.finditer(r'\(footprint "(?!MountingHole)[^"]+".*?\(at\s+([-\d.]+)\s+([-\d.]+)', content, re.DOTALL):
        switches.append((float(m.group(1)), float(m.group(2))))
        
    # 2. Find mounting holes
    screws = []
    for m in re.finditer(r'\(footprint "MountingHole:MountingHole_2\.2mm_M2_Pad".*?\(at\s+([-\d.]+)\s+([-\d.]+)', content, re.DOTALL):
        screws.append((float(m.group(1)), float(m.group(2))))
        
    return switches, screws

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
            if y1 >= y2 or abs(y2-y1) < 2 or abs(y2-y1) > 20: continue
            for x1a, x1b in h[y1]:
                for x2a, x2b in h[y2]:
                    xl, xr = max(x1a, x2a), min(x1b, x2b)
                    if xr-xl < 2 or xr-xl > 150: continue
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
    
    k_switches, k_screws = find_kicad_elements(kicad)
    d_holes = find_rects(dxf)
    
    # Filter for standard switch holes in DXF (13.9x13.9)
    d_switches = [r for r in d_holes if 13.0 < r[2] < 15.0 and 13.0 < r[3] < 15.0]
    
    print(f"KiCad: {len(k_switches)} switches, {len(k_screws)} screws")
    print(f"DXF: {len(d_holes)} holes, {len(d_switches)} are 14mm switches")
    
    pcb_xs = [s[0] for s in k_switches + k_screws]; pcb_cx = (min(pcb_xs)+max(pcb_xs))/2
    
    best_dx, best_dy, min_err = 0, 0, 999999
    
    # Brute force search for best alignment of KiCad switches to DXF switch holes
    # Mirror-X orientation
    for dy in range(-200, 200, 1):
        for dx in range(-200, 200, 1):
            matched = 0
            err = 0
            for kx, ky in k_switches:
                mx = pcb_cx - (kx - pcb_cx)
                nx, ny = mx + dx, ky + dy
                # Check if this transformed switch is near ANY DXF hole
                dist = min([math.sqrt((nx-dh[0])**2 + (ny-dh[1])**2) for dh in d_holes] + [99])
                if dist < 3.0:
                    matched += 1
                    err += dist
            
            if matched > 50: # Must match at least 50 switches
                score = (len(k_switches) - matched) * 1000 + err
                if score < min_err:
                    min_err = score
                    best_dx, best_dy = dx, dy
                    if matched == len(k_switches) and err < 1: break
        if matched == len(k_switches) and err < 1: break
                    
    print(f"\nFinal Alignment FOUND:")
    print(f"  Mirror-X with dx={best_dx}, dy={best_dy}")
    print(f"  Matched {matched}/{len(k_switches)} switches")
    
    # Apply to screws and check bounds
    xs = [p[0] for p in d_holes]; ys = [p[1] for p in d_holes]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    
    print(f"\nScrew Placements:")
    out = 0; overlaps = 0
    for sx, sy in k_screws:
        mx = pcb_cx - (sx - pcb_cx)
        nx, ny = mx + best_dx, sy + best_dy
        in_bounds = (min_x-5 <= nx <= max_x+5 and min_y-5 <= ny <= max_y+5)
        status = "IN" if in_bounds else "OUT"
        if not in_bounds: out += 1
        
        # Check overlaps
        dist = min([math.sqrt((nx-dh[0])**2 + (ny-dh[1])**2) for dh in d_holes] + [99])
        if dist < 8.55: overlaps += 1
        
        print(f"  ({sx:.1f}, {sy:.1f}) -> ({nx:.1f}, {ny:.1f}) [{status}] dist_to_hole={dist:.2f}mm")
        
    print(f"\nSUMMARY:")
    print(f"  Out of bounds: {out}")
    print(f"  Overlaps: {overlaps}")

if __name__ == "__main__": main()
