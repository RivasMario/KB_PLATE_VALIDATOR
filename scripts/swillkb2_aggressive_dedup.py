#!/usr/bin/env python3
"""
Swillkb (2) with aggressive deduplication (10mm clustering)
"""

from pathlib import Path
import ezdxf

def find_rectangles_aggressive_dedup(dxf_path, cluster_distance=10):
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
                        cy = (y1 + y2) / 2
                        rectangles.append((cx, cy, width, height))

    # AGGRESSIVE clustering: cluster_distance mm tolerance
    clusters = []
    for r in rectangles:
        found_cluster = None
        for cluster in clusters:
            if abs(r[0] - cluster[0][0]) < cluster_distance and abs(r[1] - cluster[0][1]) < cluster_distance:
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
    switches = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2]
    combos = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43]
    stabs = [(cx, cy, w, h) for cx, cy, w, h in rects if 8 < min(w,h) < 10 and 18 < max(w,h) < 26]
    return len(switches), len(combos), len(stabs), switches, combos, stabs

def main():
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")

    print("\n" + "="*80)
    print("SWILLKB (2) - AGGRESSIVE DEDUPLICATION TEST")
    print("="*80)
    print("Testing different clustering distances\n")

    distances = [5, 10, 15, 20]

    for dist in distances:
        print(f"\nCLUSTER DISTANCE: {dist}mm")
        print("-" * 60)

        results = []
        for iteration in range(1, 11):
            rects = find_rectangles_aggressive_dedup(plate_dxf, dist)
            sw, combo, stab, sw_list, combo_list, stab_list = classify_holes(rects)
            results.append((sw, combo, stab))
            print(f"  Iter {iteration:2d}: {sw:3d} switches, {combo:2d} combos, {stab:2d} stabs | Total: {sw+combo}")

        # Check consistency
        unique = set(results)
        if len(unique) == 1:
            sw, combo, stab = results[0]
            match = "PASS" if combo == 5 else f"FAIL (got {combo})"
            print(f"\n  CONSISTENT: {sw} switches, {combo} combos, {stab} stabs")
            print(f"  Expected 5 combos: {match}")
        else:
            print(f"\n  INCONSISTENT: {len(unique)} different results")

if __name__ == "__main__":
    main()
