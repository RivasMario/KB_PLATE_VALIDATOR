#!/usr/bin/env python3
import ezdxf
from pathlib import Path

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
            if y1 >= y2 or abs(y2-y1) < 2 or abs(y2-y1) > 100: continue
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
            if abs(r[0]-c[0][0]) < 5 and abs(r[1]-c[0][1]) < 5: c.append(r); found = True; break
        if not found: clusters.append([r])
    return [max(c, key=lambda x: x[2]*x[3]) for c in clusters]

def main():
    dxf = Path(r"C:\Users\v-mariorivas\Downloads\new96.dxf")
    rects = find_rects(dxf)
    rects.sort(key=lambda r: (r[1], r[0]))
    
    print(f"Found {len(rects)} rectangles:")
    for i, (cx, cy, w, h) in enumerate(rects):
        print(f"[{i:3d}] Center:({cx:6.1f}, {cy:6.1f}) Size:{w:5.1f}x{h:5.1f}")

    # Generate SVG for visual inspection
    xs = [r[0] for r in rects]; ys = [r[1] for r in rects]
    min_x, max_x, min_y, max_y = min(xs)-20, max(xs)+20, min(ys)-20, max(ys)+20
    
    with open(r"C:\Users\v-mariorivas\Downloads\plate_debug.svg", 'w') as f:
        width = max_x - min_x
        height = max_y - min_y
        f.write(f'<svg viewBox="{min_x} {min_y} {width} {height}" xmlns="http://www.w3.org/2000/svg" transform="scale(1, -1)">\n')
        f.write('<rect x="%f" y="%f" width="%f" height="%f" fill="white"/>\n' % (min_x, min_y, width, height))
        for cx, cy, w, h in rects:
            f.write(f'  <rect x="{cx-w/2}" y="{cy-h/2}" width="{w}" height="{h}" fill="none" stroke="black" stroke-width="0.5"/>\n')
            # label
            # f.write(f'  <text x="{cx}" y="{cy}" font-size="2" fill="red">{w:.1f}x{h:.1f}</text>\n')
        f.write('</svg>')
    print(f"\nSVG debug file created: C:\\Users\\v-mariorivas\\Downloads\\plate_debug.svg")

if __name__ == "__main__": main()
