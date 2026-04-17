#!/usr/bin/env python3
"""
Debug: Show all rectangles found in DXF
"""

import sys
from pathlib import Path
import ezdxf

# Add current directory to path so config can be imported
sys.path.append(str(Path(__file__).parent))
HOME = Path.home()
try:
    import config
except ImportError:
    # Fallback if config is missing or not in path
    class ConfigMock:
        INPUT_DXF = Path("/home/mario/Downloads/unfucked.dxf")
    config = ConfigMock()

def find_all_rectangles(dxf_path):
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

def main():
    plate_dxf = config.INPUT_DXF

    print("\n" + "="*80)
    print("DEBUG: RECTANGLE DETECTION")
    print("="*80 + "\n")

    rects = find_all_rectangles(plate_dxf)

    print(f"Total rectangles found: {len(rects)}\n")

    if not rects:
        print("NO RECTANGLES DETECTED")
        return

    print("ALL RECTANGLES:")
    print("  #    X Center    Y Center    Width   Height   Type")
    print("---  ----------  ----------  --------  --------  ---------")

    for i, (cx, cy, w, h) in enumerate(rects, 1):
        if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2:
            rtype = "SWITCH"
        elif 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43:
            rtype = "COMBO"
        elif 8 < min(w,h) < 10 and 18 < max(w,h) < 26:
            rtype = "STAB"
        else:
            rtype = "OTHER"

        print(f" {i:3d}  {cx:10.1f}  {cy:10.1f}  {w:8.2f}  {h:8.2f}  {rtype}")

    # Summary by type
    switches = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2)
    combos = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43)
    stabs = sum(1 for cx, cy, w, h in rects if 8 < min(w,h) < 10 and 18 < max(w,h) < 26)
    other = len(rects) - switches - combos - stabs

    print("\nSUMMARY:")
    print(f"  Switches: {switches}")
    print(f"  Combos: {combos}")
    print(f"  Stabs: {stabs}")
    print(f"  Other: {other}")

    print("\nTHRESHOLDS:")
    print(f"  Switch: 12.5 < min(w,h) < 14.2  AND  12.5 < max(w,h) < 14.2")
    print(f"  Combo:  12.5 < min(w,h) < 14.2  AND  31 < max(w,h) < 43")
    print(f"  Stab:   8 < min(w,h) < 10  AND  18 < max(w,h) < 26")

if __name__ == "__main__":
    main()
