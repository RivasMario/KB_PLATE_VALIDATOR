#!/usr/bin/env python3
import ezdxf
from pathlib import Path

def find_rects(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    segs = []
    for e in msp.query('LINE'): segs.append((e.dxf.start, e.dxf.end))
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
    dxf = Path(r"C:\Users\v-mariorivas\Downloads\new96.dxf")
    rects = find_rects(dxf)
    
    # Enter area roughly around X=280
    print("Potential holes in Enter area (X > 250, Y 60-75):")
    enter_area = [r for r in rects if r[0] > 250 and 60 < r[1] < 75]
    enter_area.sort(key=lambda r: (r[1], r[0]))
    
    for i, (cx, cy, w, h) in enumerate(enter_area):
        print(f"[{i:2d}] Center:({cx:6.1f}, {cy:6.1f}) Size:{w:5.1f}x{h:5.1f}")

if __name__ == "__main__": main()
