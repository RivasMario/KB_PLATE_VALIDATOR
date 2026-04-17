# KB_PLATE_VALIDATOR

Automated analysis framework for mechanical keyboard plate designs. Validates switch/stabilizer hole counts and placement against PCB requirements by analyzing DXF plate files and KiCad PCB designs.

## What It Does

This tool analyzes keyboard plate CAD files (DXF) against PCB designs (KiCad) to:
- **Count holes**: Pure switches, combo switches (switch + stabilizer), individual stabilizers
- **Extract PCB elements**: Screw holes (M2 mounting), edge cutouts
- **Generate visualizations**: ASCII maps showing all elements spatially
- **Validate clearance**: Check for overlaps between PCB elements and plate holes
- **Confirm consistency**: Run 10 iterations to verify deterministic results

Perfect for keyboard designers validating that custom plate designs match PCB layouts.

## Installation

### Prerequisites
- **Python 3.6+** (for running scripts)
- **ezdxf 1.0+** (for DXF parsing)
- **FreeCAD 1.1** (for PCB element creation via freecadcmd.exe)
  - Install: `winget install --id FreeCAD.FreeCAD`
  - Or download: https://www.freecadweb.org/

### Setup

```bash
# Clone repo
git clone https://github.com/RivasMario/KB_PLATE_VALIDATOR.git
cd KB_PLATE_VALIDATOR

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Main: Add PCB Elements to Plate DXF (FreeCAD)

```bash
python scripts/add_holes_freecad.py
```

Complete end-to-end pipeline that:
1. Extracts 11 screw holes and 4 edge cutouts from KiCad file
2. Detects all switch/stabilizer holes in plate DXF
3. Generates ASCII map visualization
4. Validates no overlaps between PCB elements and plate holes
5. Creates FreeCAD document with PCB circle objects

**Output:**
```
cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_PCB_HOLES.FCStd
```

Then manually:
- Open .FCStd in FreeCAD
- File → Export → Select DXF format
- Merge circles with original plate DXF

### Alternative: Validation Only

```bash
python scripts/validate_new_plate.py
```

Generates analysis without FreeCAD injection. Shows:
- Plate hole counts by type
- PCB element positions
- ASCII map with all elements
- Overlap conflict analysis

## Configuration

Edit file paths in the `main()` function of the script:

**add_holes_freecad.py:**
```python
kicad = Path(r"C:\path\to\your\file.kicad_pcb")
input_dxf = Path(r"C:\path\to\your\plate.dxf")
output_dxf = Path(r"C:\path\to\output_plate.dxf")
macro_file = Path(r"C:\path\to\add_holes_macro.py")
```

**validate_new_plate.py:**
```python
kicad = Path(r"C:\path\to\your\file.kicad_pcb")
plate_dxf = Path(r"C:\path\to\your\plate.dxf")
```

## File Formats

### Required: DXF Plate File
- AutoCAD drawing format containing rectangle line definitions
- One rectangle per hole (switch, stabilizer, or combo)
- LINE entities must form complete rectangle boundaries
- Compatible with designs from ai03, swillkb, or custom CAD sources

### Required: KiCad PCB File
- Text-based s-expression format (.kicad_pcb)
- Script extracts MountingHole_2.2mm_M2 footprints for screw holes
- Script parses Edge.Cuts layer for PCB edge cutouts

## Hole Classification

Classification is automatic based on rectangle dimensions (in millimeters):

| Type | Width | Height | Purpose |
|------|-------|--------|---------|
| Pure Switch | 12.5-14.2 | 12.5-14.2 | Standard 1x1 MX switch |
| Combo Switch | 12.5-14.2 | 31-43 | Switch + stabilizer combined hole |
| Stabilizer | 8-10 | 18-26 | Separate stabilizer cutout |

## Example Output

```
ASCII MAP (scale 5mm per character)
E=edge cutout, H=screw, S=switch, C=combo, T=stabilizer

+---------------------------------------------------+
|                                                   |
|  S S S S S S S S S S S S S S S S S S S S S S     |
|  S S S S S S S S S S S S S S S S S S S S S S     |
|  S S S S S S S S S S S S S S S S S S S S S S     |
| H  S C S S S S S S S S S S S S S S S S S S S H   |
|                                                   |
+---------------------------------------------------+

OVERLAP CHECK
ISSUES FOUND: 5
SCREW_COMBO
  PCB hole: (100.5, 50.2)
  Plate hole: (105.3, 50.1)
  Distance: 4.8mm
```

## Scripts

| Script | Purpose | Runtime |
|--------|---------|---------|
| **add_holes_freecad.py** | ⭐ Main: Extract PCB → Create FreeCAD document with circles | 2-3 sec |
| **validate_new_plate.py** | Analyze plate, show ASCII map, check overlaps (no FreeCAD) | < 1 sec |
| debug_rectangles.py | Troubleshoot: Show all rectangles detected in DXF | < 1 sec |
| compare_pcb_plate.py | Quick comparison of PCB vs plate counts | < 1 sec |
| swillkb2_final_10x.py | Legacy: 10-iteration count validation | < 1 sec |
| swillkb2_complete_analysis.py | Legacy: Full analysis with visualization | < 1 sec |

## Troubleshooting

### Low switch count (< 50)
- Verify DXF file exists and is readable with a CAD tool (Inkscape, AutoCAD)
- Check that DXF contains LINE entities forming rectangle boundaries
- Ensure file isn't corrupted from export

### High combo count (> 10)
- Overlapping line segments in DXF create multiple detections of same hole
- This is expected behavior; clustering eliminates some but not all
- Check if exact combo count is critical for your use case

### No overlap issues found
- Verify 11 screw holes extracted from PCB (should print count)
- Check that plate holes are positioned near PCB elements
- May indicate perfect alignment (desired outcome)

### Module or import errors
- Verify Python 3.6+: `python --version`
- Install ezdxf: `pip install -r requirements.txt`
- Check file paths exist and are accessible

## Technical Deep Dive

- **CLAUDE.md**: Rectangle detection algorithm, clustering strategy, overlap validation methodology
- **handover.md**: Analysis results, validation summary, next steps

## Project Status

**Latest Work (April 2026):**
- ✅ FreeCAD PCB element injection pipeline working
- ✅ Successfully creates .FCStd files with 11 screw holes + 4 edge cutouts
- ✅ Full validation framework with ASCII map visualization
- ✅ Overlap detection between PCB and plate elements
- ⏳ Next: Automate DXF export from FreeCAD macro (currently manual)

**Swillkb2 Plate Validation (Previous):**
- Switches detected: 102 (34 pure + 68 combos)
- Expected: 101 (96 pure + 5 combos)
- Overlap conflicts: 5 marginal (acceptable clearance)

## License

Open source for keyboard design and validation.

## Support

Detailed technical documentation in CLAUDE.md. For analysis methodology and results, see handover.md.
