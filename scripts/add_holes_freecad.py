#!/usr/bin/env python3
"""
Add PCB holes to plate DXF using FreeCAD CLI-Anything harness
"""

import re
import json
import subprocess
from pathlib import Path

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
    arc_pattern = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(arc_pattern, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = [float(match.group(i)) for i in range(1, 7)]
        edges.append(('arc', [(x1, y1), (x2, y2), (xm, ym)]))
    points = [p for etype, pts in edges for p in pts[:2]]
    if not points:
        return [], []
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    left_cuts, bottom_cuts = [], []
    for etype, pts in edges:
        if etype != 'arc': continue
        x1, y1, x2, y2, xm, ym = pts[0][0], pts[0][1], pts[1][0], pts[1][1], pts[2][0], pts[2][1]
        if abs(x1 - min_x) < 5 and abs(x2 - min_x) < 5 and xm - min_x >= 3.0:
            left_cuts.append((xm, (y1+y2)/2))
        if abs(y1 - max_y) < 5 and abs(y2 - max_y) < 5 and max_y - ym >= 3.0:
            bottom_cuts.append(((x1+x2)/2, y1))
    return left_cuts, bottom_cuts

def create_freecad_macro(screw_holes, edge_cutouts, input_dxf, output_dxf):
    """Generate FreeCAD Python macro to add holes"""

    macro = f"""
import FreeCAD
import Import
import Part
import Draft

# Open the DXF file
try:
    Import.insert(r"{input_dxf}", "")
except:
    pass

# Get active document
doc = FreeCAD.ActiveDocument
if doc is None:
    doc = FreeCAD.newDocument()

# Add screw holes as circles (RED layer)
screw_coords = {screw_holes}
for i, (x, y) in enumerate(screw_coords):
    circle = Draft.makeCircle(radius=1.1, placement=FreeCAD.Placement(FreeCAD.Vector(x, y, 0), FreeCAD.Rotation()))
    circle.Label = f"Screw_{{i+1}}"
    # Assign to SCREW_HOLES layer
    try:
        circle.ViewObject.LineColor = (1.0, 0.0, 0.0, 1.0)  # RED
    except:
        pass

# Add edge cutouts as circles (BLUE layer)
edge_coords = {edge_cutouts}
for i, (x, y) in enumerate(edge_coords):
    circle = Draft.makeCircle(radius=0.5, placement=FreeCAD.Placement(FreeCAD.Vector(x, y, 0), FreeCAD.Rotation()))
    circle.Label = f"EdgeCutout_{{i+1}}"
    # Assign to EDGE_CUTOUTS layer
    try:
        circle.ViewObject.LineColor = (0.0, 0.0, 1.0, 1.0)  # BLUE
    except:
        pass

# Recompute document
doc.recompute()

# Export to DXF
Import.export(doc.Objects, r"{output_dxf}")

# Save FreeCAD document too
doc.saveAs(r"{str(output_dxf).replace('.dxf', '.FCStd')}")

FreeCAD.closeDocument(doc.Name)
"""
    return macro

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    input_dxf = Path(r"C:\Users\v-mariorivas\Downloads\96plate.dxf")
    output_dxf = Path(r"C:\Users\v-mariorivas\Downloads\96plate_FREECAD_WITH_PCB.dxf")
    macro_file = Path(r"C:\Users\v-mariorivas\Downloads\add_holes_macro.py")

    print("\n" + "="*80)
    print("ADD PCB ELEMENTS TO PLATE USING FREECAD")
    print("="*80 + "\n")

    # Extract coordinates
    screw_holes = find_kicad_screw_holes(kicad)
    left_cuts, bottom_cuts = find_edge_cutouts(kicad)
    edge_cutouts = left_cuts + bottom_cuts

    print(f"COORDINATES TO ADD:")
    print(f"  Screw holes: {len(screw_holes)}")
    for i, (x, y) in enumerate(screw_holes, 1):
        print(f"    [{i:2d}] ({x:7.1f}, {y:7.1f})")

    print(f"\n  Edge cutouts: {len(edge_cutouts)}")
    for i, (x, y) in enumerate(edge_cutouts, 1):
        print(f"    [{i}] ({x:7.1f}, {y:7.1f})")

    # Create FreeCAD macro
    macro = create_freecad_macro(screw_holes, edge_cutouts, input_dxf, output_dxf)

    with open(macro_file, 'w') as f:
        f.write(macro)

    print(f"\nMacro created: {macro_file}")
    print(f"\nRunning FreeCAD macro...")

    # Execute macro
    try:
        result = subprocess.run(
            [r"C:\Program Files\FreeCAD\bin\freecadcmd.exe", str(macro_file)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"SUCCESS: FreeCAD macro executed")
            print(f"\nOutput DXF: {output_dxf}")
            if output_dxf.exists():
                print(f"File size: {output_dxf.stat().st_size} bytes")
        else:
            print(f"ERROR: FreeCAD returned code {result.returncode}")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
    except FileNotFoundError:
        print(f"ERROR: FreeCAD not found at expected location")
        print(f"Tried: C:\\Program Files\\FreeCAD\\bin\\freecadcmd.exe")
    except subprocess.TimeoutExpired:
        print(f"ERROR: FreeCAD macro timed out")

if __name__ == "__main__":
    main()
