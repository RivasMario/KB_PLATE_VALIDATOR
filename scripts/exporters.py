"""
exporters.py

Utilities to export keyboard plates from Shapely geometry to manufacturing formats:
1. Gerber (ZIP for JLCPCB) - Full PCB stack to fix "solid block" issue.
2. 3D Model (STL for 3D printing) - Support for Puzzle Split (Zigzag).
"""

import os
import zipfile
import shutil
from pathlib import Path
import math

# Gerber generation
try:
    from gerbonara import GerberFile, ExcellonFile, MM
    from gerbonara.graphic_objects import Line, Arc, Flash, Region
    from gerbonara.apertures import CircleAperture
except Exception as e:
    print(f"Gerber import failed: {e}")
    GerberFile = None

# STL generation
try:
    import cadquery as cq
except ImportError:
    cq = None

from shapely.geometry import Polygon, MultiPolygon, Point

def export_gerber(outline_poly, cutout_polys, screws, screw_radius, output_zip):
    """
    Export plate geometry to a Gerber ZIP file compatible with JLCPCB.
    Creates a full PCB stack (Empty Copper, Solid Mask) to ensure correct preview.
    """
    if GerberFile is None:
        raise ImportError("gerbonara not fully functional or installed")

    temp_dir = Path(output_zip).parent / "gerber_temp"
    if temp_dir.exists(): shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    # 1. Edge.Cuts (The physical board and holes)
    edge_cuts = GerberFile()
    edge_cuts.unit = MM
    line_ap = CircleAperture(diameter=0.15, unit=MM)
    
    def add_poly_to_file(poly, file_obj, ap=None):
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i+1]
            if ap: file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], aperture=ap, unit=MM))
            else: file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], unit=MM))
        for interior in poly.interiors:
            coords = list(interior.coords)
            for i in range(len(coords) - 1):
                p1, p2 = coords[i], coords[i+1]
                if ap: file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], aperture=ap, unit=MM))
                else: file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], unit=MM))

    # Add all geometry to Edge_Cuts
    polys = outline_poly.geoms if isinstance(outline_poly, MultiPolygon) else [outline_poly]
    for p in polys: add_poly_to_file(p, edge_cuts, line_ap)
    for p in cutout_polys:
        sub_polys = p.geoms if isinstance(p, MultiPolygon) else [p]
        for sp in sub_polys: add_poly_to_file(sp, edge_cuts, line_ap)

    # 2. NPTH_Drill.drl (Circular mounting holes)
    drill = ExcellonFile()
    drill.unit = MM
    for sx, sy in (screws or []):
        drill.add_drill(sx, sy, diameter=screw_radius * 2)

    # 3. Soldermask (Top and Bottom - make them solid for plate color)
    # We use a Region covering the bounding box
    minx, miny, maxx, maxy = outline_poly.bounds
    mask_poly = Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])
    
    top_mask = GerberFile()
    top_mask.unit = MM
    # Add a solid region for the board color
    r = Region([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)], unit=MM)
    top_mask.objects.append(r)
    
    # Save files with JLCPCB-friendly names
    edge_cuts.save(temp_dir / "Edge_Cuts.gbr")
    drill.save(temp_dir / "Drills.drl")
    top_mask.save(temp_dir / "Top_SolderMask.gbr")
    top_mask.save(temp_dir / "Bottom_SolderMask.gbr") # Same as top
    
    # Empty copper layers
    top_copper = GerberFile(); top_copper.unit = MM
    top_copper.save(temp_dir / "Top_Copper.gbr")
    top_copper.save(temp_dir / "Bottom_Copper.gbr")

    # Create ZIP
    with zipfile.ZipFile(output_zip, 'w') as zipf:
        for f in temp_dir.glob("*"):
            zipf.write(f, arcname=f.name)
    
    shutil.rmtree(temp_dir)
    return output_zip

def export_stl(outline_poly, cutout_polys, screws, screw_radius, output_stl, thickness=1.5, puzzle_split=False):
    """
    Export plate geometry to an STL file using CadQuery.
    Extrudes the 2D layout into a 3D solid.
    Supports 'puzzle_split' which cuts the plate in half with a zigzag joint.
    """
    if cq is None:
        raise ImportError("cadquery not installed")

    # CadQuery works by building a face and then extruding.
    if isinstance(outline_poly, MultiPolygon):
        polys = list(outline_poly.geoms)
    else:
        polys = [outline_poly]

    result = None
    for poly in polys:
        coords = list(poly.exterior.coords)
        island = cq.Workplane("XY").polyline(coords).close().extrude(thickness)
        
        # Cut interiors of the outline island
        for interior in poly.interiors:
            island = island.faces(">Z").workplane().polyline(list(interior.coords)).close().cutThruAll()
            
        # Cut all switch/stab holes
        for p in cutout_polys:
            if p.intersects(poly):
                sub_polys = p.geoms if isinstance(p, MultiPolygon) else [p]
                for sp in sub_polys:
                    island = island.faces(">Z").workplane().polyline(list(sp.exterior.coords)).close().cutThruAll()
                    for sp_int in sp.interiors:
                        island = island.faces(">Z").workplane().polyline(list(sp_int.coords)).close().extrude(thickness)

        # Cut screw holes
        for sx, sy in (screws or []):
            if Point(sx, sy).intersects(poly.buffer(screw_radius)):
                island = island.faces(">Z").workplane().moveTo(sx, sy).circle(screw_radius).cutThruAll()
        
        if result is None: result = island
        else: result = result.union(island)

    if not result: return None

    if puzzle_split:
        # 1. Find the split X (center of board)
        minx, miny, maxx, maxy = outline_poly.bounds
        mid_x = (minx + maxx) / 2.0
        
        # 2. Create the zigzag cutting path
        # We'll make a vertical path with trapezoidal teeth
        tooth_w = 10.0
        tooth_h = 5.0
        num_teeth = int((maxy - miny) / tooth_w)
        if num_teeth < 2: num_teeth = 2
        
        step = (maxy - miny) / num_teeth
        pts = [(mid_x, miny - 5.0)]
        for i in range(num_teeth):
            y = miny + i * step
            # Trapezoid shape
            pts.append((mid_x, y + step*0.2))
            pts.append((mid_x + tooth_h, y + step*0.4))
            pts.append((mid_x + tooth_h, y + step*0.6))
            pts.append((mid_x, y + step*0.8))
        pts.append((mid_x, maxy + 5.0))
        
        # We create a giant surface to cut with
        # Actually in CadQuery, splitting with a non-planar surface is best done by:
        # Creating a wire, extruding it to a surface, then split.
        cutter_wire = cq.Workplane("XY").polyline(pts)
        # We need to make this into a "wall" that passes through the plate
        cutter = cutter_wire.extrude(thickness * 2, combine=False).translate((0,0,-thickness))
        
        # Split!
        # CadQuery split logic:
        # Actually, let's just make two solids by intersecting with two giant boxes.
        left_box = cq.Workplane("XY").moveTo(mid_x - 1000, (miny+maxy)/2).box(2000, (maxy-miny)+100, thickness*2)
        # Subtract the "right" half of the zigzag
        pts_left = pts + [(mid_x - 1000, maxy+5), (mid_x - 1000, miny-5)]
        pts_right = pts + [(mid_x + 1000, maxy+5), (mid_x + 1000, miny-5)]
        
        cutter_left = cq.Workplane("XY").polyline(pts_left).close().extrude(thickness*2, combine=False).translate((0,0,-thickness))
        cutter_right = cq.Workplane("XY").polyline(pts_right).close().extrude(thickness*2, combine=False).translate((0,0,-thickness))
        
        result_left = result.intersect(cutter_left)
        result_right = result.intersect(cutter_right)
        
        # We'll save them slightly apart or as two separate meshes if needed.
        # For now, let's just union them with a tiny gap or just return the unioned result? 
        # User said "split in two with zig zags". 
        # I'll save them as two separate objects in the same file but moved apart 5mm.
        final_model = result_left.union(result_right.translate((5, 0, 0)))
        cq.exporters.export(final_model, str(output_stl))
    else:
        cq.exporters.export(result, str(output_stl))

    return output_stl
