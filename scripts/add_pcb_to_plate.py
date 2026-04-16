#!/usr/bin/env python3
"""
Add PCB elements (screw holes, edge cutouts) to plate DXF file
"""

import re
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
    line_pattern = r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(line_pattern, content, re.DOTALL):
        x1, y1, x2, y2 = [float(match.group(i)) for i in range(1, 5)]
        edges.append(('line', [(x1, y1), (x2, y2)]))
    arc_pattern = r'\(gr_arc\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(mid\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer "Edge\.Cuts"'
    for match in re.finditer(arc_pattern, content, re.DOTALL):
        x1, y1, xm, ym, x2, y2 = [float(match.group(i)) for i in range(1, 7)]
        edges.append(('arc', [(x1, y1), (x2, y2), (xm, ym)]))

    points = []
    for etype, pts in edges:
        for p in pts[:2]:
            points.append(p)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    left_cuts, bottom_cuts = [], []
    for etype, pts in edges:
        if etype != 'arc':
            continue
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        xm, ym = pts[2]
        if abs(x1 - min_x) < 5 and abs(x2 - min_x) < 5:
            depth = xm - min_x
            if depth >= 3.0:
                y = (y1 + y2) / 2
                left_cuts.append(((xm, y), (x1, y1), (x2, y2)))
        if abs(y1 - max_y) < 5 and abs(y2 - max_y) < 5:
            depth = max_y - ym
            if depth >= 3.0:
                x = (x1 + x2) / 2
                bottom_cuts.append(((x, y1), (x1, y1), (x2, y2)))

    return left_cuts, bottom_cuts

def add_elements_to_dxf(plate_dxf_path, output_path, screw_holes, left_cuts, bottom_cuts):
    """Add screw holes (circles) and edge cutouts (arcs) to DXF"""
    doc = ezdxf.readfile(str(plate_dxf_path))
    msp = doc.modelspace()

    # Add screw holes as circles (red color for visibility)
    screw_layer = doc.layers.new(name='SCREW_HOLES')
    screw_layer.color = 1  # Red

    for x, y in screw_holes:
        circle = msp.add_circle(center=(x, y), radius=1.1, dxfattribs={'layer': 'SCREW_HOLES'})

    print(f"Added {len(screw_holes)} screw holes as circles (radius 1.1mm)")

    # Add edge cutouts as arcs (blue color)
    edge_layer = doc.layers.new(name='EDGE_CUTOUTS')
    edge_layer.color = 5  # Blue

    cutout_count = 0
    for center, start, end in left_cuts + bottom_cuts:
        # Calculate arc from start to end through center
        # For simplicity, use lines to represent cutout location
        cx, cy = center

        # Add center point marker
        circle = msp.add_circle(center=(cx, cy), radius=0.5, dxfattribs={'layer': 'EDGE_CUTOUTS'})
        cutout_count += 1

    print(f"Added {cutout_count} edge cutout markers")

    # Save modified DXF
    doc.saveas(str(output_path))
    print(f"Saved to: {output_path}")

def main():
    kicad = Path(r"C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb")
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2).dxf")
    output_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch(2)_WITH_PCB.dxf")

    print("\n" + "="*80)
    print("ADD PCB ELEMENTS TO PLATE DXF")
    print("="*80 + "\n")

    # Extract PCB elements
    screw_holes = find_kicad_screw_holes(kicad)
    left_cuts, bottom_cuts = find_edge_cutouts(kicad)

    print(f"PCB ELEMENTS FOUND:")
    print(f"  Screw holes: {len(screw_holes)}")
    print(f"  Left edge cutouts: {len(left_cuts)}")
    print(f"  Bottom edge cutouts: {len(bottom_cuts)}\n")

    # Add to DXF
    add_elements_to_dxf(plate_dxf, output_dxf, screw_holes, left_cuts, bottom_cuts)

    print("\n" + "="*80)
    print("COMPLETE")
    print("="*80)
    print(f"\nNew DXF created with PCB elements added:")
    print(f"  Screw holes: Red circles (1.1mm radius)")
    print(f"  Edge cutouts: Blue circle markers")
    print(f"\nFile: {output_dxf}")

if __name__ == "__main__":
    main()
