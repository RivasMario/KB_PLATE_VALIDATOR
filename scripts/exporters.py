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
    from gerbonara.apertures import CircleAperture, ExcellonTool
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
    if screws:
        drill_tool = ExcellonTool(diameter=screw_radius * 2, plated=False, unit=MM)
        for sx, sy in screws:
            drill.objects.append(Flash(x=sx, y=sy, aperture=drill_tool, unit=MM))

    # 3. Copper + Mask: shapely precomputes material = outline - holes.
    # Emit the same filled-with-holes shape on copper AND mask so JLCPCB
    # doesn't auto-fill mask over the cutouts.
    top_copper = GerberFile(); top_copper.unit = MM
    top_mask = GerberFile(); top_mask.unit = MM

    hole_geoms = list(cutout_polys)
    for sx, sy in (screws or []):
        hole_geoms.append(Point(sx, sy).buffer(screw_radius, quad_segs=32))
    all_holes = unary_union(hole_geoms) if hole_geoms else None
    material_poly = outline_poly.difference(all_holes) if all_holes else outline_poly

    sub = material_poly.geoms if isinstance(material_poly, MultiPolygon) else [material_poly]
    for sp in sub:
        for target in (top_copper, top_mask):
            target.objects.append(Region(outline=list(sp.exterior.coords),
                                         unit=MM, polarity_dark=True))
            for interior in sp.interiors:
                target.objects.append(Region(outline=list(interior.coords),
                                             unit=MM, polarity_dark=False))

    edge_cuts.save(temp_dir / "Edge_Cuts.gbr")
    drill.save(temp_dir / "Drills.drl")
    top_copper.save(temp_dir / "Top_Copper.gbr")
    top_copper.save(temp_dir / "Bottom_Copper.gbr")
    top_mask.save(temp_dir / "Top_SolderMask.gbr")
    top_mask.save(temp_dir / "Bottom_SolderMask.gbr")

    # Create ZIP
    with zipfile.ZipFile(output_zip, 'w') as zipf:
        for f in temp_dir.glob("*"):
            zipf.write(f, arcname=f.name)
    
    shutil.rmtree(temp_dir)
    return output_zip

def export_stl(outline_poly, cutout_polys, screws, screw_radius, output_stl, thickness=1.5):
    """
    Export plate geometry to an STL file using CadQuery.
    Extrudes the 2D layout into a 3D solid.
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

    if result:
        cq.exporters.export(result, str(output_stl))
    return output_stl

def parse_dxf_to_shapely(dxf_path):
    """
    Parse an existing DXF file and reconstruct Shapely geometry.
    Prefers named layers (PLATE_OUTLINE, SWITCH_CUTOUTS, STAB_CUTOUTS, PCB_SCREW_HOLES).
    Falls back to auto-detection: all lines polygonized, largest polygon = outline,
    rest = cutouts; all CIRCLEs = screws.
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
            elif e.dxftype() == 'POLYLINE':
                verts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                if e.is_closed and verts: verts.append(verts[0])
                for i in range(len(verts)-1):
                    lines.append([verts[i], verts[i+1]])
            elif e.dxftype() == 'ARC':
                cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
                a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
                if a1 < a0: a1 += 2 * math.pi
                steps = max(8, int((a1 - a0) / (math.pi / 32)))
                pts = [(cx + r*math.cos(a0 + (a1-a0)*i/steps),
                        cy + r*math.sin(a0 + (a1-a0)*i/steps)) for i in range(steps+1)]
                for i in range(len(pts)-1):
                    lines.append([pts[i], pts[i+1]])
            elif e.dxftype() == 'CIRCLE':
                cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
                steps = 48
                pts = [(cx + r*math.cos(2*math.pi*i/steps),
                        cy + r*math.sin(2*math.pi*i/steps)) for i in range(steps+1)]
                for i in range(len(pts)-1):
                    lines.append([pts[i], pts[i+1]])
        return lines

    def safe_query(q):
        try:
            return list(msp.query(q))
        except Exception:
            return []

    outline_entities = safe_query('*[layer=="PLATE_OUTLINE"]')
    outline_lines = entities_to_lines(outline_entities)
    outline_polys = list(polygonize(outline_lines))
    outline_poly = unary_union(outline_polys) if outline_polys else None

    cutout_entities = safe_query('*[layer=="SWITCH_CUTOUTS"]') + \
                      safe_query('*[layer=="STAB_CUTOUTS"]')
    cutout_lines = entities_to_lines(cutout_entities)
    cutout_polys = list(polygonize(cutout_lines))

    screw_entities = safe_query('*[layer=="PCB_SCREW_HOLES"]')
    screws = []
    screw_radius = 1.2
    for e in screw_entities:
        if e.dxftype() == 'CIRCLE':
            screws.append((e.dxf.center.x, e.dxf.center.y))
            screw_radius = e.dxf.radius

    # Fallback: outline missing. Auto-detect from any layer.
    if outline_poly is None:
        all_entities = list(msp.query('LINE LWPOLYLINE POLYLINE ARC'))
        all_lines = entities_to_lines(all_entities)
        all_polys = list(polygonize(all_lines))

        if not screws:
            for c in msp.query('CIRCLE'):
                if c.dxf.radius <= 2.0:
                    screws.append((c.dxf.center.x, c.dxf.center.y))
                    screw_radius = c.dxf.radius

        for c in msp.query('CIRCLE'):
            if c.dxf.radius > 2.0:
                cx, cy, r = c.dxf.center.x, c.dxf.center.y, c.dxf.radius
                steps = 48
                pts = [(cx + r*math.cos(2*math.pi*i/steps),
                        cy + r*math.sin(2*math.pi*i/steps)) for i in range(steps+1)]
                circle_polys = list(polygonize([[pts[i], pts[i+1]] for i in range(len(pts)-1)]))
                all_polys.extend(circle_polys)

        if all_polys:
            all_polys.sort(key=lambda p: p.area, reverse=True)
            outline_poly = all_polys[0]
            if not cutout_polys:
                cutout_polys = all_polys[1:]

    return {
        "outline": outline_poly,
        "cutouts": cutout_polys,
        "screws": screws,
        "screw_radius": screw_radius
    }
