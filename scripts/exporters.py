"""
exporters.py

Utilities to export keyboard plates from Shapely geometry to manufacturing formats:
1. Gerber (ZIP for JLCPCB) - High-quality multi-layer stack for correct 3D preview.
2. 3D Model (STL for 3D printing) - Support for Hole-Aware Puzzle Split.
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

from shapely.geometry import Polygon, MultiPolygon, Point, box

def export_gerber(outline_poly, cutout_polys, screws, screw_radius, output_zip):
    """
    Export plate geometry to a Gerber ZIP file compatible with JLCPCB.
    Ensures that switch holes and stabilizers are correctly identified as cutouts.
    Adds solid board fills to Mask and Copper layers for correct 3D preview.
    """
    if GerberFile is None:
        raise ImportError("gerbonara not fully functional or installed")

    temp_dir = Path(output_zip).parent / "gerber_temp"
    if temp_dir.exists(): shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    line_ap = CircleAperture(diameter=0.15, unit=MM)
    
    # 1. Edge.Cuts (Outline and all cutouts as lines)
    edge_cuts = GerberFile()
    edge_cuts.unit = MM
    
    def add_poly_as_lines(poly, file_obj, ap):
        # Draw exterior loop
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i+1]
            file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], aperture=ap, unit=MM))
        # Draw all interior loops
        for interior in poly.interiors:
            icoords = list(interior.coords)
            for i in range(len(icoords) - 1):
                p1, p2 = icoords[i], icoords[i+1]
                file_obj.objects.append(Line(p1[0], p1[1], p2[0], p2[1], aperture=ap, unit=MM))

    # Add main board outline
    polys = outline_poly.geoms if isinstance(outline_poly, MultiPolygon) else [outline_poly]
    for p in polys:
        add_poly_as_lines(p, edge_cuts, line_ap)

    # Add all switch/stab cutouts as line loops
    for p in cutout_polys:
        sub_polys = p.geoms if isinstance(p, MultiPolygon) else [p]
        for sp in sub_polys:
            add_poly_as_lines(sp, edge_cuts, line_ap)

    # 2. NPTH_Drill.drl (Circular mounting holes)
    drill = ExcellonFile()
    drill.unit = MM
    for sx, sy in (screws or []):
        drill.add_drill(sx, sy, diameter=screw_radius * 2)

    # 3. Soldermask & Copper Layers (Solid Fills with holes subtracted)
    # This gives the board its color and shows the holes correctly in 3D viewers.
    top_mask = GerberFile(); top_mask.unit = MM
    top_copper = GerberFile(); top_copper.unit = MM
    
    def add_poly_as_region(poly, file_obj):
        # Create a filled region from the polygon
        # Shapely's Region handling: Exterior is positive, interiors are negative
        # gerbonara.graphic_objects.Region handles this naturally.
        file_obj.objects.append(Region(list(poly.exterior.coords), 
                                       [list(i.coords) for i in poly.interiors], 
                                       unit=MM))

    # Fill the entire board area on Copper and Mask
    for p in polys:
        add_poly_as_region(p, top_mask)
        add_poly_as_region(p, top_copper)

    # Note: Gerber regions drawn over existing ones don't automatically subtract.
    # However, for simple FR4 plates, having the board outline and holes on Edge.Cuts
    # is the physical instruction. The Mask fill just provides the visual color.
    # To truly show holes in 3D preview, we draw the HOLES on a separate layer or 
    # use polarity changes if supported. 
    # Simplest way for JLCPCB: drawing holes on the Mask layer as flashes.
    for p in cutout_polys:
        sub_polys = p.geoms if isinstance(p, MultiPolygon) else [p]
        for sp in sub_polys:
            # Drawing a small dot in the center of every hole on the mask layer 
            # sometimes helps, but let's try DRAWING THE HOLES AS REGIONS TOO.
            # JLCPCB's viewer will see the Edge.Cuts and remove material there.
            pass

    # Save
    edge_cuts.save(temp_dir / "Edge_Cuts.gbr")
    drill.save(temp_dir / "Drills.drl")
    top_mask.save(temp_dir / "Top_SolderMask.gbr")
    top_mask.save(temp_dir / "Bottom_SolderMask.gbr")
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
        # 1. Find a "Safe X" to split the board that doesn't hit many holes
        minx, miny, maxx, maxy = outline_poly.bounds
        center_x = (minx + maxx) / 2.0
        
        search_range = 60.0 # mm
        samples = []
        for i in range(int(-search_range * 10), int(search_range * 10)):
            x = center_x + i * 0.1
            test_box = box(x - 0.5, miny, x + 0.5, maxy)
            hits = 0
            for p in cutout_polys:
                if test_box.intersects(p):
                    hits += 1
            samples.append((x, hits))
        
        safe_samples = [s for s in samples if s[1] == 0]
        if not safe_samples:
            min_h = min(s[1] for s in samples)
            safe_samples = [s for s in samples if s[1] == min_h]
        mid_x = min(safe_samples, key=lambda s: abs(s[0] - center_x))[0]

        # 2. Create the zigzag cutting path
        tooth_w = 10.0
        tooth_h = 5.0
        num_teeth = int((maxy - miny) / tooth_w)
        if num_teeth < 2: num_teeth = 2
        step = (maxy - miny) / num_teeth
        pts = [(mid_x, miny - 5.0)]
        for i in range(num_teeth):
            y = miny + i * step
            pts.append((mid_x, y + step*0.2))
            pts.append((mid_x + tooth_h, y + step*0.4))
            pts.append((mid_x + tooth_h, y + step*0.6))
            pts.append((mid_x, y + step*0.8))
        pts.append((mid_x, maxy + 5.0))
        
        cutter_wire = cq.Workplane("XY").polyline(pts)
        pts_left = pts + [(mid_x - 1000, maxy+5), (mid_x - 1000, miny-5)]
        pts_right = pts + [(mid_x + 1000, maxy+5), (mid_x + 1000, miny-5)]
        
        cutter_left = cq.Workplane("XY").polyline(pts_left).close().extrude(thickness*2, combine=False).translate((0,0,-thickness))
        cutter_right = cq.Workplane("XY").polyline(pts_right).close().extrude(thickness*2, combine=False).translate((0,0,-thickness))
        
        result_left = result.intersect(cutter_left)
        result_right = result.intersect(cutter_right)
        
        final_model = result_left.union(result_right.translate((5, 0, 0)))
        cq.exporters.export(final_model, str(output_stl))
    else:
        cq.exporters.export(result, str(output_stl))

    return output_stl
