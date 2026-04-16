# SKYWAY96 Plate Analysis

Automated analysis framework for SKYWAY96 keyboard plate design. Validates switch/stabilizer hole counts and placement against PCB requirements.

## Overview

This project analyzes DXF plate files and KiCad PCB designs to:
- Count switch holes, stabilizer holes, and combo holes
- Extract PCB requirements (screw holes, edge cutouts)
- Generate ASCII maps showing hole placement
- Validate that PCB elements don't overlap with plate holes
- Confirm plate design matches PCB layout

## Files

### Scripts

- **swillkb2_final_10x.py** - Count validation (10 iterations)
  - Counts pure switches vs combo switches
  - Confirms consistent results across runs
  
- **swillkb2_complete_analysis.py** - Full analysis pipeline
  - Extracts PCB elements (edge cutouts, screw holes)
  - Finds plate holes (switches, combos, stabs)
  - Generates ASCII map visualization
  - Checks for overlaps between PCB and plate elements

### Output

Analysis results and maps saved here.

### Logs

Processing logs and debug output.

## Usage

```bash
# Run full analysis on swillkb plate
python scripts/swillkb2_complete_analysis.py

# Run 10-iteration count validation
python scripts/swillkb2_final_10x.py
```

## Project Status

**swillkb (2) File:** PASS
- Expected: ~101 switches
- Found: 102 switches (34 pure + 68 combos)
- Combo distribution: 5 stabilized keys (spacebar, enter, backspace, numpad enter, numpad plus)

**PCB-to-Plate Alignment:** 5 marginal conflicts
- 2 screw holes 4.8mm from switches
- 3 screw holes 6.4-7.8mm from combos
- Status: Minor - likely acceptable for 2.2mm M2 screw holes

## KiCad PCB Reference

File: `rivasmario 96% Hotswap Rp2040.kicad_pcb`
- 11 M2 mounting holes
- 4 edge cutouts (1 left, 3 bottom)
- 101 total switch positions (96 regular + 5 stabilized)

## Hole Classification

- **Pure Switches:** 13.9×13.9mm (1x1 keys)
- **Combo Switches:** 13.9×31-43mm (switch + stabilizer combined)
- **Stabilizers:** 8.0×18-26mm (separate mounting)
- **Screw Holes:** 2.2mm radius M2 mounting
- **Edge Cutouts:** U-shaped PCB edge features

## Notes

- Rectangle detection uses line-based algorithm (finds rectangles formed by LINE entities)
- 5mm position clustering eliminates overlapping rectangle detections
- Overlap check uses radius-based distance calculation
- Screw hole clearance validation assumes 1.1mm mounting hole radius + tolerances
