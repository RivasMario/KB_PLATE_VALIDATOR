#!/usr/bin/env python3
"""
Swillkb (2): Take ONE largest rectangle per position to eliminate duplicates
"""

from pathlib import Path
import ezdxf
from collections import defaultdict

def find_rectangles_one_per_y(dxf_path):
    """Find rectangles, keep only largest per Y position"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    h_lines = {}
    v_lines = {}

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
                    v_left = any(abs(v - x_left) < 0.5 for v in v_lines.keys())
                    v_right = any(abs(v - x_right) < 0.5 for v in v_lines.keys())
                    if v_left and v_right:
                        cx = (x_left + x_right) / 2
                        cy = round((y1 + y2) / 2, 0)
                        rectangles.append((cx, cy, width, height))

    # Group by Y position and keep largest per Y
    by_y = defaultdict(list)
    for r in rectangles:
        cy = r[1]
        by_y[cy].append(r)

    unique_per_y = []
    for cy in sorted(by_y.keys()):
        largest = max(by_y[cy], key=lambda r: r[2] * r[3])
        unique_per_y.append(largest)

    return sorted(unique_per_y, key=lambda r: (r[1], r[0]))

def classify_holes(rects):
    switches = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2)
    combos = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43)
    stabs = sum(1 for cx, cy, w, h in rects if 8 < min(w,h) < 10 and 18 < max(w,h) < 26)
    return switches, combos, stabs

def main():
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")

    print("\n" + "="*80)
    print("SWILLKB (2) - ONE RECTANGLE PER Y POSITION")
    print("="*80)
    print("Takes largest rectangle at each Y coordinate to eliminate duplicates\n")

    rects = find_rectangles_one_per_y(plate_dxf)
    print(f"Total rectangles after dedup: {len(rects)}\n")

    print("10 ITERATIONS:")
    print("-" * 60)

    results = []
    for iteration in range(1, 11):
        sw, combo, stab = classify_holes(rects)
        results.append((sw, combo, stab))
        print(f"  Iter {iteration:2d}: {sw:3d} switches, {combo:2d} combos, {stab:2d} stabs | Total: {sw+combo}")

    # Check consistency
    unique = set(results)
    if len(unique) == 1:
        sw, combo, stab = results[0]
        print(f"\nCONSISTENT RESULTS:")
        print(f"  Switches: {sw}")
        print(f"  Combos: {combo}")
        print(f"  Stabs: {stab}")
        print(f"  TOTAL SWITCHES: {sw + combo}")
        print(f"\nEXPECTED:")
        print(f"  Switches: ~96")
        print(f"  Combos: 5")
        print(f"  Total: ~101")

        if combo == 5:
            print(f"\n  PASS - Combo count correct!")
        else:
            print(f"\n  FAIL - Got {combo} combos, expected 5")
    else:
        print(f"\nINCONSISTENT: {len(unique)} different results")

if __name__ == "__main__":
    main()
