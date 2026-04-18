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

import ezdxf
from ezdxf.math import Vec2

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
from shapely.ops import unary_union

def export_gerber(outline_poly, cutout_polys, screws, screw_radius, output_zip):
    """
    Export plate geometry to a Gerber ZIP file compatible with JLCPCB.
    Uses high-precision line paths for Edge.Cuts and explicit subtraction for Mask/Copper.
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

    # 3. Soldermask & Copper Layers
    # We want a solid board WITH HOLES REMOVED.
    top_mask = GerberFile(); top_mask.unit = MM
    top_copper = GerberFile(); top_copper.unit = MM
    
    # Union all cutouts and screws into a single "Holes" geometry
    hole_geoms = []
    for p in cutout_polys:
        hole_geoms.append(p)
    for sx, sy in (screws or []):
        hole_geoms.append(Point(sx, sy).buffer(screw_radius))
    
    all_holes = unary_union(hole_geoms)
    
    # Create the final "Material" geometry by subtracting holes from the outline
    material_poly = outline_poly.difference(all_holes)
    
    def add_poly_as_region(poly, file_obj):
        if isinstance(poly, Polygon):
            file_obj.objects.append(Region(list(poly.exterior.coords), 
                                           [list(i.coords) for i in poly.interiors], 
                                           unit=MM))
        elif isinstance(poly, MultiPolygon):
            for p in poly.geoms:
                file_obj.objects.append(Region(list(p.exterior.coords), 
                                               [list(i.coords) for i in p.interiors], 
                                               unit=MM))

    # Draw the physical material on Mask and Copper
    add_poly_as_region(material_poly, top_mask)
    add_poly_as_region(material_poly, top_copper)

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
        minx, miny, maxx, maxy = outline_poly.bounds
        center_x = (minx + maxx) / 2.0
        search_range = 60.0 # mm
        samples = []
        for i in range(int(-search_range * 10), int(search_range * 10)):
            x = center_x + i * 0.1
            test_box = box(x - 0.5, miny, x + 0.5, maxy)
            hits = 0
            for p in cutout_polys:
                if test_box.intersects(p): hits += 1
            samples.append((x, hits))
        safe_samples = [s for s in samples if s[1] == 0]
        if not safe_samples:
            min_h = min(s[1] for s in samples)
            safe_samples = [s for s in samples if s[1] == min_h]
        mid_x = min(safe_samples, key=lambda s: abs(s[0] - center_x))[0]

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
        result = result_left.union(result_right.translate((5, 0, 0)))

    if result:
        cq.exporters.export(result, str(output_stl))
    return output_stl

def parse_dxf_to_shapely(dxf_path):
    """
    Parse an existing DXF file and reconstruct Shapely geometry.
    Looks for layers: PLATE_OUTLINE, SWITCH_CUTOUTS, STAB_CUTOUTS, PCB_SCREW_HOLES.
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    from shapely.ops import polygonize
    
    def entities_to_lines(entities):
        lines = []
        for e in entities:
            if e.dxftype() == 'LINE':
                lines.append([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
            elif e.dxftype() == 'LWPOLYLINE':
                pts = list(e.get_points('xy'))
                if e.closed: pts.append(pts[0])
                for i in range(len(pts)-1):
                    lines.append([pts[i], pts[i+1]])
        return lines

    # 1. Reconstruct Outline
    outline_entities = msp.query('*[layer=="PLATE_OUTLINE"]')
    outline_lines = entities_to_lines(outline_entities)
    outline_polys = list(polygonize(outline_lines))
    outline_poly = unary_union(outline_polys) if outline_polys else None

    # 2. Reconstruct Cutouts
    cutout_entities = msp.query('*[layer=="SWITCH_CUTOUTS"] | *[layer=="STAB_CUTOUTS"]')
    cutout_lines = entities_to_lines(cutout_entities)
    cutout_polys = list(polygonize(cutout_lines))

    # 3. Reconstruct Screws
    screw_entities = msp.query('*[layer=="PCB_SCREW_HOLES"]')
    screws = []
    screw_radius = 1.2 # default
    for e in screw_entities:
        if e.dxftype() == 'CIRCLE':
            screws.append((e.dxf.center.x, e.dxf.center.y))
            screw_radius = e.dxf.radius

    return {
        "outline": outline_poly,
        "cutouts": cutout_polys,
        "screws": screws,
        "screw_radius": screw_radius
    }
