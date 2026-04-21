
import sys
import json
from collections import defaultdict
from pathlib import Path

sys.path.append('/home/mario/Documents/GitHub/KB_PLATE_VALIDATOR')
from scripts.build_plate import find_kicad_switches, U1

def generate_kle_from_pcb(kicad_path):
    switches = find_kicad_switches(kicad_path)
    if not switches:
        print("No switches found!")
        return

    # Sort switches by Y to group into rows
    switches.sort(key=lambda s: (round(s[1] / 5), s[0])) # Group Y within ~5mm
    
    rows = []
    current_row = []
    last_y = None
    
    for s in switches:
        x, y = s
        if last_y is None or abs(y - last_y) < 5.0:
            current_row.append((x, y))
            last_y = (last_y * len(current_row[:-1]) + y) / len(current_row) if last_y else y
        else:
            rows.append(current_row)
            current_row = [(x, y)]
            last_y = y
    if current_row:
        rows.append(current_row)

    kle_rows = []
    for r in rows:
        r.sort(key=lambda s: s[0])
        row_keys = []
        last_x = r[0][0] - U1
        
        for i, (x, y) in enumerate(r):
            # Calculate gap from last key center
            gap = (x - last_x) / U1
            
            # This is a very rough heuristic for key width/spacing
            width = 1.0
            x_offset = 0
            
            # If there's a significant gap, it's either an offset or a wide key
            # For the purpose of getting a functional KLE, we'll try to estimate width
            if i > 0:
                prev_x = r[i-1][0]
                dist = (x - prev_x) / U1
                
                # If distance > 1.25, it might be a gap or a wide key
                if dist > 1.1:
                    if dist >= 1.5:
                        x_offset = dist - 1.0
                        
            # It's hard to guess exact widths from just centers, but let's try to emit basic keys
            # We'll rely on the user to adjust the exact modifiers, but this will give the structure
            if x_offset > 0.1:
                row_keys.append({"x": round(x_offset, 2)})
                
            row_keys.append("") # Empty label
            last_x = x
            
        kle_rows.append(row_keys)

    print(json.dumps(kle_rows, separators=(',', ':')))

generate_kle_from_pcb('/home/mario/Documents/GitHub/TKL_VIDEO/TKL_Video/TKL_Video.kicad_pcb')
