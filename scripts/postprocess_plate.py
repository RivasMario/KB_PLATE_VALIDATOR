#!/usr/bin/env python3
"""Post-process a generated plate DXF: grow edge notches for install clearance
and normalize screw-hole diameter. Re-emits a clean layered DXF.

Usage:
  python scripts/postprocess_plate.py IN.dxf OUT.dxf [--notch-grow 1.0] [--screw-dia 2.6]
"""
import argparse, ezdxf
from shapely.geometry import Polygon, box, MultiPolygon, Point
from shapely.ops import unary_union


def loops(msp, layer):
    out = []
    for e in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
        pts = [(p[0], p[1]) for p in e.get_points()]
        if len(pts) >= 3:
            out.append(pts)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--notch-grow', type=float, default=1.0)
    ap.add_argument('--screw-dia', type=float, default=3.2)   # target (max) diameter
    ap.add_argument('--min-wall', type=float, default=0.4)    # min material to a cutout/edge
    ap.add_argument('--min-dia', type=float, default=2.4)     # never shrink below this
    a = ap.parse_args()
    target_r = a.screw_dia / 2.0

    doc = ezdxf.readfile(a.inp); msp = doc.modelspace()
    switch = [Polygon(p) for p in loops(msp, 'SWITCH_CUTOUTS') if len(p) >= 3]
    stab = [Polygon(p) for p in loops(msp, 'STAB_CUTOUTS') if len(p) >= 3]
    screws = [(c.dxf.center.x, c.dxf.center.y) for c in msp.query('CIRCLE[layer=="PCB_SCREW_HOLES"]')]
    polys = [Polygon(p) for p in loops(msp, 'PLATE_OUTLINE') if len(p) >= 3]
    polys = sorted([p for p in polys if p.is_valid and p.area > 5], key=lambda p: p.area, reverse=True)
    main_poly, internal = polys[0], polys[1:]

    # grow notches: the "bites" the perimeter takes out of its bounding box
    bites = box(*main_poly.bounds).difference(main_poly)
    geoms = [bites] if isinstance(bites, Polygon) else list(bites.geoms)
    real = [g for g in geoms if g.area > 2.0]          # ignore corner slivers
    if real:
        grown = unary_union([g.buffer(a.notch_grow, join_style=2) for g in real])
        main_poly = main_poly.difference(grown)
        if isinstance(main_poly, MultiPolygon):
            main_poly = max(main_poly.geoms, key=lambda p: p.area)
    print(f"notches grown: {len(real)} (+{a.notch_grow}mm)")

    out = ezdxf.new('R2010', setup=True); m = out.modelspace()
    for n, c in {'PLATE_OUTLINE': 7, 'SWITCH_CUTOUTS': 3, 'STAB_CUTOUTS': 5, 'PCB_SCREW_HOLES': 1}.items():
        out.layers.add(n, color=c)

    def addp(poly, layer):
        ext = list(poly.exterior.coords)
        m.add_lwpolyline(ext[:-1] if ext[0] == ext[-1] else ext, close=True, dxfattribs={'layer': layer})
        for ring in poly.interiors:
            ri = list(ring.coords)
            m.add_lwpolyline(ri[:-1] if ri[0] == ri[-1] else ri, close=True, dxfattribs={'layer': layer})

    addp(main_poly, 'PLATE_OUTLINE')
    for p in internal: addp(p, 'PLATE_OUTLINE')
    for p in switch: addp(p, 'SWITCH_CUTOUTS')
    for p in stab: addp(p, 'STAB_CUTOUTS')

    # per-hole adaptive radius: as big as target, capped to keep min-wall to the
    # nearest cutout edge or the plate perimeter; floored at min-dia.
    clear_geoms = switch + stab + internal
    floor_r = a.min_dia / 2.0
    capped = []
    for x, y in screws:
        pt = Point(x, y)
        r = target_r
        for g in clear_geoms:
            r = min(r, pt.distance(g) - a.min_wall)
        r = min(r, main_poly.exterior.distance(pt) - a.min_wall)
        r = max(r, floor_r)
        if r < target_r - 1e-6:
            capped.append(round(r * 2, 2))
        m.add_circle((x, y), r, dxfattribs={'layer': 'PCB_SCREW_HOLES'})
    out.saveas(a.out)
    print(f"wrote {a.out}  switches={len(switch)} stabs={len(stab)} screws={len(screws)} "
          f"target Ø{a.screw_dia}; capped holes: {capped if capped else 'none'}")


if __name__ == '__main__':
    main()
