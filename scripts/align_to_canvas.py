#!/usr/bin/env python3
"""
Align DXF elements to canvas (white paper bounds)
Finds canvas rectangle and translates all holes to align with it
"""

from pathlib import Path
import ezdxf

def find_canvas_bounds(dxf_path):
    """Find the white paper (canvas) bounds - largest rectangle"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    # Collect all line segments
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

    # Find largest rectangle (canvas bounds)
    largest_rect = None
    largest_area = 0

    for y1 in sorted(h_lines.keys()):
        for y2 in sorted(h_lines.keys()):
            if y1 >= y2:
                continue
            height = abs(y2 - y1)
            if height < 50:
                continue

            for (x1a, x1b) in h_lines[y1]:
                for (x2a, x2b) in h_lines[y2]:
                    x_left = max(x1a, x2a)
                    x_right = min(x1b, x2b)
                    width = x_right - x_left
                    if width < 50:
                        continue

                    area = width * height
                    if area > largest_area:
                        largest_area = area
                        largest_rect = (x_left, x_right, y1, y2, width, height)

    return largest_rect

def get_elements_bounds(dxf_path):
    """Get bounds of all hole elements (excluding canvas)"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    xs, ys = [], []
    for line in [e for e in msp if e.dxftype() == 'LINE']:
        xs.append(line.dxf.start.x)
        xs.append(line.dxf.end.x)
        ys.append(line.dxf.start.y)
        ys.append(line.dxf.end.y)

    if not xs:
        return None

    return min(xs), max(xs), min(ys), max(ys)

def align_dxf(dxf_path, output_path):
    """Align all DXF elements to canvas bounds"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    print("\n" + "="*80)
    print("ALIGN DXF TO CANVAS")
    print("="*80 + "\n")

    # Find canvas
    canvas = find_canvas_bounds(dxf_path)
    if not canvas:
        print("ERROR: Could not find canvas bounds")
        return

    canvas_x_left, canvas_x_right, canvas_y_top, canvas_y_bottom, canvas_w, canvas_h = canvas
    print(f"CANVAS FOUND:")
    print(f"  Position: ({canvas_x_left:.1f}, {canvas_y_top:.1f})")
    print(f"  Size: {canvas_w:.1f} x {canvas_h:.1f}")
    print(f"  Bounds: X({canvas_x_left:.1f}-{canvas_x_right:.1f}) Y({canvas_y_bottom:.1f}-{canvas_y_top:.1f})\n")

    # Get elements bounds
    elements = get_elements_bounds(dxf_path)
    if not elements:
        print("ERROR: No elements found")
        return

    elem_x_min, elem_x_max, elem_y_min, elem_y_max = elements
    print(f"ELEMENTS BEFORE ALIGNMENT:")
    print(f"  Bounds: X({elem_x_min:.1f}-{elem_x_max:.1f}) Y({elem_y_min:.1f}-{elem_y_max:.1f})\n")

    # Calculate offset
    offset_x = canvas_x_left - elem_x_min
    offset_y = canvas_y_bottom - elem_y_min

    print(f"TRANSLATION OFFSET:")
    print(f"  X: {offset_x:+.1f}mm")
    print(f"  Y: {offset_y:+.1f}mm\n")

    # Apply offset to all elements (except canvas itself)
    translated = 0
    for entity in msp:
        if entity.dxftype() == 'LINE':
            # Check if this is a canvas line (very long)
            x1, y1 = entity.dxf.start.x, entity.dxf.start.y
            x2, y2 = entity.dxf.end.x, entity.dxf.end.y
            length = ((x2-x1)**2 + (y2-y1)**2)**0.5

            # Skip canvas lines (they're very long, > 300mm)
            if length > 300:
                continue

            # Translate
            entity.dxf.start = (x1 + offset_x, y1 + offset_y)
            entity.dxf.end = (x2 + offset_x, y2 + offset_y)
            translated += 1

    print(f"ALIGNMENT COMPLETE:")
    print(f"  Translated {translated} line segments\n")

    # Verify
    elements_after = get_elements_bounds(dxf_path)
    if elements_after:
        elem_x_min, elem_x_max, elem_y_min, elem_y_max = elements_after
        print(f"ELEMENTS AFTER ALIGNMENT:")
        print(f"  Bounds: X({elem_x_min:.1f}-{elem_x_max:.1f}) Y({elem_y_min:.1f}-{elem_y_max:.1f})")

        # But we need to recalculate after our changes
        doc.saveas(str(output_path))

    # Recalculate after save
    doc2 = ezdxf.readfile(str(output_path))
    msp2 = doc2.modelspace()
    xs, ys = [], []
    for line in [e for e in msp2 if e.dxftype() == 'LINE']:
        xs.append(line.dxf.start.x)
        xs.append(line.dxf.end.x)
        ys.append(line.dxf.start.y)
        ys.append(line.dxf.end.y)

    if xs and ys:
        print(f"\nVERIFICATION (from saved file):")
        print(f"  X range: {min(xs):.1f} to {max(xs):.1f}")
        print(f"  Y range: {min(ys):.1f} to {max(ys):.1f}")
        print(f"\nAligned DXF saved to:")
        print(f"  {output_path}")

def main():
    plate_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch.dxf")
    output_dxf = Path(r"C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch_ALIGNED.dxf")

    align_dxf(plate_dxf, output_dxf)

if __name__ == "__main__":
    main()
