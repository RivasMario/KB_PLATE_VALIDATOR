import sys
import math
from pathlib import Path
import ezdxf
import re

# Add current directory to path so config can be imported
sys.path.append(str(Path(__file__).parent))
try:
    import config
except ImportError:
    class ConfigMock:
        KICAD_PCB = Path("/home/mario/Documents/GitHub/SKYWAY-96/KiCAD Source Files/rivasmario 96% Hotswap Rp2040.kicad_pcb")
        INPUT_DXF = Path("/home/mario/Downloads/generated_plate.dxf")
    config = ConfigMock()

def find_kicad_screw_holes(kicad_path):
    with open(kicad_path, 'r') as f:
        content = f.read()
    holes = []
    pattern = r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'
    for match in re.finditer(pattern, content, re.DOTALL):
        x, y = float(match.group(1)), float(match.group(2))
        holes.append((x, y))
    return sorted(holes, key=lambda h: (h[1], h[0]))

def find_rectangles_from_lines(dxf_path):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    h_lines, v_lines = {}, {}
    entities = list(msp.query('LINE LWPOLYLINE'))
    segments = []
    for entity in entities:
        if entity.dxftype() == 'LINE':
            segments.append((entity.dxf.start, entity.dxf.end))
        elif entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.vertices())
            if not points: continue
            if entity.closed: points.append(points[0])
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
                    v_left = any(abs(v - x_left) < 0.5 for v in v_lines.keys())
                    v_right = any(abs(v - x_right) < 0.5 for v in v_lines.keys())
                    if v_left and v_right:
                        rectangles.append(((x_left + x_right) / 2, (y1 + y2) / 2, width, height))
    clusters = []
    for r in rectangles:
        found_cluster = None
        for cluster in clusters:
            if abs(r[0] - cluster[0][0]) < 5 and abs(r[1] - cluster[0][1]) < 5:
                found_cluster = cluster
                break
        if found_cluster is None: clusters.append([r])
        else: found_cluster.append(r)
    unique = []
    for cluster in clusters:
        unique.append(max(cluster, key=lambda r: r[2] * r[3]))
    return unique

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def get_plate_bounds(rects):
    if not rects: return 0, 0, 0, 0
    xs = [cx - w/2 for cx, cy, w, h in rects] + [cx + w/2 for cx, cy, w, h in rects]
    ys = [cy - h/2 for cx, cy, w, h in rects] + [cy + h/2 for cx, cy, w, h in rects]
    return min(xs), max(xs), min(ys), max(ys)

def test_config(dx, dy, raw_screws, plate_holes, bounds, mirror, pcb_cy):
    min_x, max_x, min_y, max_y = bounds
    overlaps = 0
    current_min_dist = 999
    out_of_bounds = 0
    
    for sx, sy in raw_screws:
        ty_base = pcb_cy - (sy - pcb_cy) if mirror else sy
        tx, ty = sx + dx, ty_base + dy
        
        # Check bounds
        if not (min_x <= tx <= max_x and min_y <= ty <= max_y):
            out_of_bounds += 1
            
        # Check overlaps
        for ph in plate_holes:
            d = distance((tx, ty), (ph[0], ph[1]))
            if d < current_min_dist:
                current_min_dist = d
            if d < 8.55:
                overlaps += 1
                
    return overlaps, out_of_bounds, current_min_dist

def main():
    kicad = config.KICAD_PCB
    input_dxf = config.INPUT_DXF
    
    raw_screws = find_kicad_screw_holes(kicad)
    plate_holes = find_rectangles_from_lines(input_dxf)
    bounds = get_plate_bounds(plate_holes)
    
    print(f"Plate Bounds: X({bounds[0]:.1f}-{bounds[1]:.1f}) Y({bounds[2]:.1f}-{bounds[3]:.1f})")
    
    for pcb_cy in [127.1, 137.1, 147.1, 117.1]:
        print(f"\n--- TESTING pcb_cy = {pcb_cy} ---")
        for mirror in [True, False]:
            print(f"Testing {'Mirror-Y' if mirror else 'Normal-Y'}...")
            best_cfg = None
            min_score = 999
            
            for dx_int in range(-500, 500, 4): # 4mm steps
                dx = float(dx_int)
                for dy_int in range(-500, 500, 4):
                    dy = float(dy_int)
                    
                    overlaps, oob, min_dist = test_config(dx, dy, raw_screws, plate_holes, bounds, mirror, pcb_cy)
                    
                    if oob == 0 and overlaps == 0:
                        print(f"SUCCESS! pcb_cy={pcb_cy}, mirror={mirror}, dx={dx}, dy={dy}, min_dist={min_dist:.2f}mm")
                        return dx, dy, mirror, pcb_cy
                    
                    score = oob * 10 + overlaps
                    if not best_cfg or score < min_score:
                        min_score = score
                        best_cfg = (dx, dy, overlaps, oob, min_dist)
            
            print(f"Best: dx={best_cfg[0]}, dy={best_cfg[1]}, overlaps={best_cfg[2]}, oob={best_cfg[3]}, min_dist={best_cfg[4]:.2f}mm")

if __name__ == "__main__":
    main()
