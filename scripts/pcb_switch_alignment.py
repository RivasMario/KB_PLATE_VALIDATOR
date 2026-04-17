#!/usr/bin/env python3
import re, math
from pathlib import Path
import ezdxf

def find_kicad_elements(kicad_path):
    with open(kicad_path, 'r') as f: content = f.read()
    
    switches = []
    # Find all Kailh hotswap footprint centers
    for m in re.finditer(r'\(footprint ".*?SW_Hotswap_Kailh.*?".*?\(at\s+([-\d.]+)\s+([-\d.]+)', content, re.DOTALL):
        switches.append((float(m.group(1)), float(m.group(2))))
        
    screws = []
    for m in re.finditer(r'\(footprint "MountingHole:MountingHole_2\.2mm_M2_Pad".*?\(at\s+([-\d.]+)\s+([-\d.]+)', content, re.DOTALL):
        screws.append((float(m.group(1)), float(m.group(2))))
        
    return list(set(switches)), list(set(screws))

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
    
    # Filter for standard switch holes in DXF (around 14x14)
    d_switches = [r for r in d_holes if 13.5 < r[2] < 14.5 and 13.5 < r[3] < 14.5]
    
    print(f"KiCad: {len(k_switches)} switches, {len(k_screws)} screws")
    print(f"DXF: {len(d_holes)} total holes, {len(d_switches)} are 14x14 switch cutouts")
    
    if not k_switches or not d_switches:
        print("Failed to find switches to align.")
        return

    # To find alignment, let's look at the bounding boxes of the switch centers
    k_xs = [s[0] for s in k_switches]; k_ys = [s[1] for s in k_switches]
    k_minx, k_maxx, k_miny, k_maxy = min(k_xs), max(k_xs), min(k_ys), max(k_ys)
    
    d_xs = [s[0] for s in d_switches]; d_ys = [s[1] for s in d_switches]
    d_minx, d_maxx, d_miny, d_maxy = min(d_xs), max(d_xs), min(d_ys), max(d_ys)
    
    print(f"\nKiCad Switch Bounds: X({k_minx:.1f} to {k_maxx:.1f}), Y({k_miny:.1f} to {k_maxy:.1f}) | Span: {k_maxx-k_minx:.1f} x {k_maxy-k_miny:.1f}")
    print(f"DXF Switch Bounds:   X({d_minx:.1f} to {d_maxx:.1f}), Y({d_miny:.1f} to {d_maxy:.1f}) | Span: {d_maxx-d_minx:.1f} x {d_maxy-d_miny:.1f}")

    # The DXF coordinates might be offset, mirrored, or flipped.
    # Check 4 orientations: Normal, MirrorX, MirrorY, MirrorXY
    
    k_cx = (k_minx + k_maxx) / 2
    k_cy = (k_miny + k_maxy) / 2
    d_cx = (d_minx + d_maxx) / 2
    d_cy = (d_miny + d_maxy) / 2

    orientations = [
        ("Normal", lambda x,y: (x, y)),
        ("Mirror-X", lambda x,y: (k_cx - (x - k_cx), y)),
        ("Mirror-Y", lambda x,y: (x, k_cy - (y - k_cy))),
        ("Mirror-XY", lambda x,y: (k_cx - (x - k_cx), k_cy - (y - k_cy)))
    ]
    
    best_match = 0
    best_setup = None
    
    for name, transform in orientations:
        # Transform KiCad switches to test orientation
        t_switches = [transform(sx, sy) for sx, sy in k_switches]
        t_minx, t_maxx, t_miny, t_maxy = min([s[0] for s in t_switches]), max([s[0] for s in t_switches]), min([s[1] for s in t_switches]), max([s[1] for s in t_switches])
        
        # Calculate dx, dy to align the bounding box centers
        dx = d_cx - ((t_minx + t_maxx) / 2)
        dy = d_cy - ((t_miny + t_maxy) / 2)
        
        # Fine-tune the offset locally (since bounding boxes might not be perfectly identical due to missing/extra keys)
        for fine_dy in range(int(dy)-10, int(dy)+10):
            for fine_dx in range(int(dx)-10, int(dx)+10):
                matched = 0
                for tx, ty in t_switches:
                    nx, ny = tx + fine_dx, ty + fine_dy
                    # Find nearest DXF switch
                    dist = min([math.sqrt((nx-dx_[0])**2 + (ny-dx_[1])**2) for dx_ in d_switches] + [99])
                    if dist < 2.0:
                        matched += 1
                if matched > best_match:
                    best_match = matched
                    best_setup = (name, transform, fine_dx, fine_dy)

    if not best_setup:
        print("No valid alignment found.")
        return
        
    name, transform, final_dx, final_dy = best_setup
    print(f"\nWINNING ALIGNMENT: {name}")
    print(f"  dx = {final_dx}, dy = {final_dy}")
    print(f"  Matched {best_match} out of {len(k_switches)} PCB switches to DXF switch holes")
    
    # Now check the screws with this exact transformation
    print("\nValidating 11 PCB Mounting Holes:")
    
    plate_xs = [p[0] for p in d_holes]; plate_ys = [p[1] for p in d_holes]
    p_min_x, p_max_x, p_min_y, p_max_y = min(plate_xs), max(plate_xs), min(plate_ys), max(plate_ys)
    
    out_of_bounds = 0
    overlaps = 0
    
    for sx, sy in k_screws:
        tx, ty = transform(sx, sy)
        nx, ny = tx + final_dx, ty + final_dy
        
        in_bounds = (p_min_x <= nx <= p_max_x and p_min_y <= ny <= p_max_y)
        dist_to_hole = min([math.sqrt((nx-ph[0])**2 + (ny-ph[1])**2) for ph in d_holes] + [99])
        
        status = "OK"
        if not in_bounds: 
            status = "OUT OF BOUNDS"
            out_of_bounds += 1
        elif dist_to_hole < 8.55:
            status = f"OVERLAP ({dist_to_hole:.1f}mm)"
            overlaps += 1
            
        print(f"  Screw @ PCB({sx:.1f}, {sy:.1f}) -> DXF({nx:.1f}, {ny:.1f}) | {status}")
        
    print(f"\nFinal Check: {out_of_bounds} Out of bounds, {overlaps} Overlaps")
    
    if out_of_bounds == 0 and overlaps == 0:
        print("SUCCESS! This alignment perfectly maps the PCB to the DXF plate.")

if __name__ == "__main__": main()
