#!/usr/bin/env python3
"""
Organize and rename DXF files from Downloads into human-readable names
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
import ezdxf

def analyze_dxf(dxf_path):
    """Determine what a DXF file contains"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        line_count = len([e for e in msp if e.dxftype() == 'LINE'])
        circle_count = len([e for e in msp if e.dxftype() == 'CIRCLE'])
        arc_count = len([e for e in msp if e.dxftype() == 'ARC'])

        # Plate files have many lines (forming rectangles)
        # PCB files have circles (vias) and arcs
        if line_count > 100:
            return 'PLATE'
        elif circle_count > 50 or arc_count > 20:
            return 'PCB'
        else:
            return 'UNKNOWN'
    except:
        return 'ERROR'

def detect_source(filename):
    """Detect plate source from filename or content"""
    fname_lower = filename.lower()

    if 'cc1e0e' in fname_lower or 'swillkb' in fname_lower:
        return 'SWILLKB'
    elif 'ai03' in fname_lower or 'plate-2026' in fname_lower:
        return 'AI03'
    elif '96_plate' in fname_lower:
        return 'CUSTOM'
    else:
        return 'UNKNOWN'

def has_pcb_elements(dxf_path):
    """Check if DXF has PCB elements (circles for screw holes, cutout markers)"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        # Check for SCREW_HOLES or EDGE_CUTOUTS layer
        layers = [layer.dxf.name for layer in doc.layers]
        if 'SCREW_HOLES' in layers or 'EDGE_CUTOUTS' in layers:
            return True

        # Check for small circles (screw hole markers ~1.1mm)
        for circle in [e for e in msp if e.dxftype() == 'CIRCLE']:
            if 0.8 < circle.dxf.radius < 1.5:
                return True

        return False
    except:
        return False

def rename_dxf(old_path, new_name):
    """Rename DXF file"""
    new_path = old_path.parent / f"{new_name}.dxf"

    if new_path.exists():
        counter = 1
        base = f"{new_name}_v{counter}"
        new_path = old_path.parent / f"{base}.dxf"
        while new_path.exists():
            counter += 1
            base = f"{new_name}_v{counter}"
            new_path = old_path.parent / f"{base}.dxf"

    shutil.move(str(old_path), str(new_path))
    return new_path

def main():
    downloads = Path(r"C:\Users\v-mariorivas\Downloads")

    print("\n" + "="*80)
    print("ORGANIZE DXF FILES")
    print("="*80 + "\n")

    # Find hash-named DXF files
    hash_pattern = re.compile(r'^[a-f0-9]{40}')
    plate_version_pattern = re.compile(r'^plate-\d{4}-\d{2}-\d{2}')

    dxf_files = []
    for dxf in downloads.glob("*.dxf"):
        fname = dxf.name.replace('.dxf', '')

        # Skip already-named files
        if fname.startswith('KB_') or fname.startswith('96_PLATE'):
            continue

        # Target hash-named or auto-generated files
        if hash_pattern.match(fname) or plate_version_pattern.match(fname):
            dxf_files.append(dxf)

    if not dxf_files:
        print("No hash-named DXF files found in Downloads")
        return

    print(f"Found {len(dxf_files)} DXF files to organize:\n")

    date_str = datetime.now().strftime("%Y%m%d")

    for dxf_path in sorted(dxf_files):
        print(f"Processing: {dxf_path.name}")

        # Analyze file
        file_type = analyze_dxf(dxf_path)
        source = detect_source(dxf_path.name)
        has_pcb = has_pcb_elements(dxf_path)

        print(f"  Type: {file_type} | Source: {source} | Has PCB: {has_pcb}")

        # Generate new name
        if file_type == 'PLATE':
            if has_pcb:
                new_name = f"KB_96_PLATE_{source}_WITH_PCB_{date_str}"
            else:
                new_name = f"KB_96_PLATE_{source}_{date_str}"
        elif file_type == 'PCB':
            new_name = f"KB_96_PCB_{source}_{date_str}"
        else:
            new_name = f"KB_UNKNOWN_{source}_{date_str}"

        # Rename file
        try:
            new_path = rename_dxf(dxf_path, new_name)
            print(f"  Renamed to: {new_path.name}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print()

    print("="*80)
    print("COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
