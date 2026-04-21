
import json
import re
import math
from pathlib import Path
import sys

# Setup paths to use the project's internal parser
PROJECT_ROOT = Path('/home/mario/Documents/GitHub/KB_PLATE_VALIDATOR')
sys.path.append(str(PROJECT_ROOT))
from scripts.build_plate import parse_kle, U1

# The KLE layout provided by the user
kle_text = [
    ["~\n`","!\n1","@\n2","#\n3","$\n4","%\n5","^\n6","&\n7","*\n8","(\n9",")\n0","_\n-","+\n=",{"w":2},"Backspace"],
    [{"w":1.5},"Tab","Q","W","E","R","T","Y","U","I","O","P","{\n[","}\n]",{"w":1.5},"|\n\\"],
    [{"w":1.75},"Caps Lock","A","S","D","F","G","H","J","K","L",":\n;","\"\n'",{"w":2.25},"Enter"],
    [{"w":2},"Shift","Z","X","C","V","B","N","M","<\n,",">\n.","?\n/","Del","Up","Home"],
    [{"w":1.25},"Ctrl",{"w":1.25},"Win",{"w":1.25},"Alt",{"a":7,"w":6.25},"","Alt","Ctrl","Left","Down","Right"]
]

keys, w_mm, h_mm = parse_kle(kle_text)

# KiCad v6+ S-expression template
pcb_content = [
    '(kicad_pcb (version 20211014) (generator pcbnew)',
    '  (general (thickness 1.6))',
    '  (setup (stackup (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "F.Paste" (type "solderpaste"))))',
    '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))',
    ''
]

# Add footprints
for i, k in enumerate(keys):
    # KLE parser returns coordinates relative to top-left of the board
    # In KiCad, we'll place them exactly there.
    x, y = k['cx_u'] * U1, k['cy_u'] * U1
    
    # We use the naming pattern 'SW_MX' which the validator regex looks for
    fp = f'  (footprint "Button_Switch_Keyboard:SW_MX_1.00u" (layer "F.Cu") (at {x:.4f} {y:.4f})\n'
    fp += f'    (tstamp {i:08x}-0000-0000-0000-000000000000)\n'
    fp += '  )'
    pcb_content.append(fp)

# Add a simple rectangle outline on Edge.Cuts
pad = 2.0
outline = [
    f'  (gr_line (start {-pad} {-pad}) (end {w_mm+pad} {-pad}) (layer "Edge.Cuts") (width 0.1))',
    f'  (gr_line (start {w_mm+pad} {-pad}) (end {w_mm+pad} {h_mm+pad}) (layer "Edge.Cuts") (width 0.1))',
    f'  (gr_line (start {w_mm+pad} {h_mm+pad}) (end {-pad} {h_mm+pad}) (layer "Edge.Cuts") (width 0.1))',
    f'  (gr_line (start {-pad} {h_mm+pad}) (end {-pad} {-pad}) (layer "Edge.Cuts") (width 0.1))'
]
pcb_content.extend(outline)
pcb_content.append(')')

output_path = PROJECT_ROOT / 'custom_65.kicad_pcb'
output_path.write_text('\n'.join(pcb_content))
print(f"PCB generated at: {output_path}")
print(f"Stats: {len(keys)} keys, Dimensions: {w_mm:.2f} x {h_mm:.2f} mm")
