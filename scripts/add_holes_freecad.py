#!/usr/bin/env python3
"""
Add PCB holes to plate DXF using FreeCAD CLI-Anything harness
Includes overlap validation against plate holes.
"""

import re
import json
import subprocess
import math
from pathlib import Path
import ezdxf

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return sorted(holes, key=lambda h: (h[1], h[0]))

def find_edge_cutouts(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    edges = []
    
    # Improved regex for KiCad 6+ gr_arc and gr_line
    arc_pattern = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(arc_pattern, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = [float(match.group(i)) for i in range(1, 7)]
        edges.append(('arc', [(x1, y1), (x2, y2), (xm, ym)]))
        
    line_pattern = r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(line_pattern, content, re.DOTALL):
        x1, y1, x2, y2 = [float(match.group(i)) for i in range(1, 5)]
        edges.append(('line', [(x1, y1), (x2, y2)]))

    points = []
    for etype, pts in edges:
        for p in pts:
            points.append(p)
            
    if not points:
        return []

    xs, ys = [p[0] for p in points], [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    
    # We want to return the center of arcs that are "cutouts"
    cutouts = []
    for etype, pts in edges:
        if etype == 'arc':
            x1, y1, x2, y2, xm, ym = pts[0][0], pts[0][1], pts[1][0], pts[1][1], pts[2][0], pts[2][1]
            # Left edge cutout check
            if abs(x1 - min_x) < 5 and abs(x2 - min_x) < 5 and xm - min_x >= 2.0:
                cutouts.append((xm, (y1+y2)/2))
            # Bottom edge cutout check
            elif abs(y1 - max_y) < 5 and abs(y2 - max_y) < 5 and max_y - ym >= 2.0:
                cutouts.append(((x1+x2)/2, ym))
                
    return cutouts

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    h_lines = {}
    v_lines = {}
    tolerance = 0.5

    # Handle both LINE and LWPOLYLINE entities
    entities = list(msp.query('LINE LWPOLYLINE'))
    
    segments = []
    for entity in entities:
        if entity.dxftype() == 'LINE':
            segments.append((entity.dxf.start, entity.dxf.end))
        elif entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.vertices())
            if not points: continue
            if entity.closed:
                points.append(points[0])
            for i in range(len(points)-1):
                segments.append((points[i], points[i+1]))

    for start, end in segments:
        x1, y1 = start[0], start[1]
        x2, y2 = end[0], end[1]

        if abs(y1 - y2) < 0.1:
            y = round(y1, 1)
            if y not in h_lines: h_lines[y] = []
            h_lines[y].append((min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 0.1:
            x = round(x1, 1)
            if x not in v_lines: v_lines[x] = []
            v_lines[x].append((min(y1, y2), max(y1, y2)))

    rectangles = []
    for y1 in sorted(h_lines.keys()):
        for y2 in sorted(h_lines.keys()):
            if y1 >= y2: continue
            height = abs(y2 - y1)
            if height < 2 or height > 50: continue
            for (x1a, x1b) in h_lines[y1]:
                for (x2a, x2b) in h_lines[y2]:
                    x_left = max(x1a, x2a)
                    x_right = min(x1b, x2b)
                    width = x_right - x_left
                    if width < 2 or width > 50: continue
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
    switches = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 12.5 < max(w,h) < 14.2]
    combos = [(cx, cy, w, h) for cx, cy, w, h in rects if 12.5 < min(w,h) < 14.2 and 31 < max(w,h) < 43]
    stabs = [(cx, cy, w, h) for cx, cy, w, h in rects if 8 < min(w,h) < 10 and 18 < max(w,h) < 26]
    return switches, combos, stabs

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def create_freecad_macro(screw_holes, edge_cutouts, input_dxf, output_dxf):
    """Generate FreeCAD Python macro to add holes"""
    input_dxf_str = str(input_dxf).replace('\\', '/')
    output_dxf_str = str(output_dxf).replace('\\', '/')
    fcstd_output_str = output_dxf_str.replace('.dxf', '.FCStd')

    macro = f"""
import FreeCAD
import Import
import Part
import Draft
import os
import importDXF

print("Starting FreeCAD macro execution...")
doc = FreeCAD.newDocument("PlateWithHoles")

print(f"Importing plate DXF: {{r'{input_dxf_str}'}}")
try:
    if os.path.exists(r'{input_dxf_str}'):
        importDXF.insert(r'{input_dxf_str}', doc.Name)
        print("Plate DXF imported successfully using importDXF.")
    else:
        print("Warning: Input DXF file not found.")
except Exception as e:
    print(f"Error importing plate DXF: {{e}}")

print(f"Adding {{len({screw_holes})}} screw holes...")
screw_coords = {screw_holes}
for i, (x, y) in enumerate(screw_coords):
    circle = Draft.makeCircle(radius=1.5, placement=FreeCAD.Placement(FreeCAD.Vector(x, y, 0), FreeCAD.Rotation()))
    circle.Label = f"Screw_{{i+1}}"
    try:
        circle.ViewObject.LineColor = (1.0, 0.0, 0.0, 1.0)  # RED
    except:
        pass

print(f"Adding {{len({edge_cutouts})}} edge cutouts...")
edge_coords = {edge_cutouts}
for i, (x, y) in enumerate(edge_coords):
    circle = Draft.makeCircle(radius=1.0, placement=FreeCAD.Placement(FreeCAD.Vector(x, y, 0), FreeCAD.Rotation()))
    circle.Label = f"EdgeCutout_{{i+1}}"
    try:
        circle.ViewObject.LineColor = (0.0, 0.0, 1.0, 1.0)  # BLUE
    except:
        pass

doc.recompute()

print(f"Exporting to DXF: {{r'{output_dxf_str}'}}")
try:
    objs = doc.Objects
    importDXF.export(objs, r'{output_dxf_str}')
    if os.path.exists(r'{output_dxf_str}'):
        print(f"Verified: DXF file exists and is {{os.path.getsize(r'{output_dxf_str}')}} bytes.")
except Exception as e:
    print(f"Error exporting to DXF: {{e}}")

print(f"Saving FreeCAD document: {{r'{fcstd_output_str}'}}")
try:
    doc.saveAs(r'{fcstd_output_str}')
    print("FreeCAD document saved successfully.")
except Exception as e:
    print(f"Error saving FreeCAD document: {{e}}")

FreeCAD.closeDocument(doc.Name)
print("Macro execution finished.")
"""
    return macro

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    input_dxf = Path(r"C:\Users\v-mariorivas\Downloads\unfucked.dxf")
    output_dxf = Path(r"C:\Users\v-mariorivas\Downloads\96plate_CLEAN_WITH_PCB.dxf")
    macro_file = Path(r"C:\Users\v-mariorivas\Downloads\add_holes_macro.py")
    freecad_exe = Path(r"C:\Users\v-mariorivas\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe")

    print("\n" + "="*80)
    print("ADD PCB ELEMENTS TO PLATE USING FREECAD (WITH VALIDATION)")
    print("="*80 + "\n")

    # 1. Extract PCB coordinates
    print("Scanning PCB from KiCad...")
    screw_holes = find_kicad_screw_holes(kicad)
    edge_cutouts = find_edge_cutouts(kicad)

    print(f"  Found {len(screw_holes)} screw holes and {len(edge_cutouts)} edge cutouts.")

    # 2. Extract Plate Holes for Validation
    print(f"Scanning plate DXF: {input_dxf.name}...")
    if not input_dxf.exists():
        print(f"ERROR: Input file {input_dxf} not found!")
        return

    rects = find_rectangles_from_lines(input_dxf)
    switches, combos, stabs = classify_holes(rects)
    all_plate_holes = switches + combos + stabs
    print(f"  Detected {len(all_plate_holes)} plate holes (Switches: {len(switches)}, Combos: {len(combos)}, Stabs: {len(stabs)})")

    # 3. Overlap Validation with Mirror-Y
    print("\nValidating overlaps with MIRROR-Y transformation...")
    
    # Calculate PCB screw center for mirroring based on all PCB elements
    pcb_ys = [s[1] for s in screw_holes]
    pcb_cy = 127.1 # Based on min(79.5) and max(174.7) from switch bounds
    
    # Optimal offset found: dx=-52, dy=-71 (relative to Mirror-Y)
    dx, dy = -52, -71
    
    transformed_screws = []
    for sx, sy in screw_holes:
        my = pcb_cy - (sy - pcb_cy) # Mirror Y
        transformed_screws.append((sx + dx, my + dy))
        
    transformed_edges = []
    for ex, ey in edge_cutouts:
        my = pcb_cy - (ey - pcb_cy) # Mirror Y
        transformed_edges.append((ex + dx, my + dy))

    overlap_threshold = 8.55
    overlaps = []
    for sx, sy in transformed_screws:
        for ph in all_plate_holes:
            cx, cy, w, h = ph
            d = distance((sx, sy), (cx, cy))
            if d < overlap_threshold:
                overlaps.append((d, (sx, sy), (cx, cy)))

    if overlaps:
        print(f"  WARNING: Found {len(overlaps)} potential overlaps!")
        overlaps.sort()
        for d, (sx, sy), (cx, cy) in overlaps[:5]:
            print(f"    - Distance {d:.2f}mm: Screw at ({sx:.1f}, {sy:.1f}) vs Plate hole at ({cx:.1f}, {cy:.1f})")
    else:
        print("  SUCCESS: No overlaps detected with transformation.")

    # 4. Create & Run FreeCAD macro with transformed coordinates
    macro = create_freecad_macro(transformed_screws, transformed_edges, input_dxf, output_dxf)
    with open(macro_file, 'w') as f:
        f.write(macro)

    print(f"\nRunning FreeCAD macro...")
    try:
        result = subprocess.run(
            [str(freecad_exe), str(macro_file)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"SUCCESS: FreeCAD macro executed")
            print(f"STDOUT Summary:\n" + "\n".join(result.stdout.splitlines()[-5:]))
            
            if output_dxf.exists():
                print(f"\nFINAL OUTPUTS:")
                print(f"  DXF File: {output_dxf} ({output_dxf.stat().st_size} bytes)")
                fcstd_output = Path(str(output_dxf).replace('.dxf', '.FCStd'))
                if fcstd_output.exists():
                    print(f"  FreeCAD File: {fcstd_output} ({fcstd_output.stat().st_size} bytes)")
        else:
            print(f"ERROR: FreeCAD returned code {result.returncode}")
            print(f"STDERR:\n{result.stderr}")
    except Exception as e:
        print(f"ERROR: Failed to execute FreeCAD macro: {e}")

if __name__ == "__main__":
    main()
