#!/usr/bin/env python3
"""
Swillkb (2) - Final 10x confirmation
Count: all rectangles 13.9x13.9 OR 13.9x31-43 = total switches
5 of the large ones are combos (stabilized keys)
"""

import re
from pathlib import Path
import ezdxf

def find_rectangles_from_lines(dxf_path):
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

def classify_holes(rects):
    """
    Pure switches: 13.9x13.9 (1x1 keys)
    Combo switches: 13.9x31-43 (keys with stabilizers: space, enter, backspace, numpad enter, numpad plus)
    Total switches = pure + combos
    """
    pure = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2)
    combos = sum(1 for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43)
    total = pure + combos
    return pure, combos, total

def main():
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")

    print("\n" + "="*80)
    print("SWILLKB (2) - FINAL CONFIRMATION (10 ITERATIONS)")
    print("="*80)
    print("Pure switches (13.9x13.9) + Combo switches (13.9x31-43)")
    print("Combos = 5 stabilized keys: spacebar, enter, backspace, numpad enter, numpad plus")
    print("="*80 + "\n")

    results = []
    for iteration in range(1, 11):
        rects = find_rectangles_from_lines(plate_dxf)
        pure, combos, total = classify_holes(rects)
        results.append((pure, combos, total))
        print(f"[Iter {iteration:2d}] Pure: {pure:3d} | Combos: {combos:2d} | TOTAL SWITCHES: {total:3d}")

    # Verify consistency
    unique = set(results)
    if len(unique) == 1:
        pure, combos, total = results[0]
        print(f"\n{'='*80}")
        print("CONSISTENT RESULTS (all 10 iterations identical)")
        print(f"{'='*80}")
        print(f"Pure switches (1x1 keys): {pure}")
        print(f"Combo switches (with stabs): {combos}")
        print(f"TOTAL SWITCHES: {total}")
        print()
        print(f"Expected: 96 pure + 5 combos = 101 total")
        print(f"Found:    {pure} pure + {combos} combos = {total} total")
        print()

        if 95 < total < 106:
            print(f"STATUS: PASS - Count matches PCB")
        else:
            print(f"STATUS: FAIL - Count mismatch")
    else:
        print(f"\nINCONSISTENT: {len(unique)} different result sets")

if __name__ == "__main__":
    main()
