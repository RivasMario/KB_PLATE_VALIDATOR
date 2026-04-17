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
- **ezdxf 1.0+** (for DXF parsing and plate generation)
- **FreeCAD 1.1** *(legacy, only for `add_holes_freecad.py`)*
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

### ⭐ Main: Generate Plate DXF from KLE + KiCad (`build_plate.py`)

Single-script plate generator — no FreeCAD, no manual DXF merging.

```bash
python3 scripts/build_plate.py \
  --kle "path/to/KLE.json" \
  --pcb "path/to/board.kicad_pcb" \
  --out plate.dxf \
  --pad 5
```

What it does:
1. Parses KLE JSON into switch positions.
2. Ports switch/stab cutout geometry from [swill/kb_builder](https://github.com/swill/kb_builder) (Cherry MX spec, 4 switch types, 3 stab types).
3. Extracts 99 switch footprints + mounting holes + Edge.Cuts arcs from KiCad.
4. Auto-registers PCB → plate by matching switch positions across 8 symmetries (nearest-neighbor score). No manual `--dx`/`--dy`/`--mirror-y` needed.
5. Renders edge cutouts as **true U-shaped arcs cut into the plate perimeter**, not overlaid circles.
6. Emits a single DXF with layered geometry:
   - `PLATE_OUTLINE` (white) — perimeter with arc notches
   - `SWITCH_CUTOUTS` (green)
   - `STAB_CUTOUTS` (cyan)
   - `PCB_SCREW_HOLES` (red)
7. Runs a built-in validator: every screw must be inside the plate and not overlap any switch/stab cutout. Non-zero exit on violations.

**Typical output:**
```
keys=99 plate=371.95x124.30mm screws=11 edge_notches=4 -> plate.dxf
align: flip_x=False flip_y=True rot=0 dx=-46.51 dy=189.25 nn_score=0.02mm
VALIDATOR: all screws inside plate, none overlapping cutouts
```

**Key flags:**

| Flag | Default | Purpose |
|------|---------|---------|
| `--switch-type` | 1 | 0=square, 1=mx+alps, 2=mx-openable, 3=rotatable |
| `--stab-type` | 0 | 0=cherry+costar, 1=cherry, 2=costar |
| `--screw-diameter` | 2.4 | mm. 2.2=close-fit, 2.4=M2 free-fit, 2.6=loose |
| `--kerf` | 0.0 | Laser kerf compensation (mm) |
| `--pad` | 0.0 | Plate padding around keys (mm) |
| `--clearance` | 0.5 | Min screw-to-cutout clearance (mm) |
| `--no-auto-align` | off | Skip brute-force; use raw KiCad coords + manual nudge |
| `--pcb-dx` / `--pcb-dy` | 0 | Manual nudge after auto-align |

### Legacy: Add PCB Elements to Existing Plate DXF (FreeCAD)

```bash
python scripts/add_holes_freecad.py
```

Older pipeline that imports an existing plate DXF into FreeCAD and overlays PCB holes as Draft circles. Requires FreeCAD 1.1 and a manual DXF export step. Superseded by `build_plate.py` for new plate designs.

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
| **build_plate.py** | ⭐ Main: Generate plate DXF from KLE + KiCad (no FreeCAD) | < 1 sec |
| add_holes_freecad.py | Legacy: Overlay PCB circles onto existing plate DXF (needs FreeCAD) | 2-3 sec |
| validate_new_plate.py | Analyze plate, show ASCII map, check overlaps | < 1 sec |
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
- ✅ `build_plate.py` — one-shot plate DXF generator, no FreeCAD required
- ✅ KLE → DXF: plate outline, switch cutouts (4 types), stab cutouts (3 types)
- ✅ PCB-to-plate registration via switch-footprint nearest-neighbor matching (sub-0.1mm accuracy on SKYWAY-96)
- ✅ Edge cutouts rendered as true U-arcs cut into the plate outline
- ✅ Built-in validator: screw clearance + cutout-overlap check
- ⏳ Next: fillet corners, LWPOLYLINE+bulge for arcs (single-path outline), support for non-standard stab positions

**Previous: FreeCAD-based pipeline (superseded):**
- ✅ FreeCAD PCB element injection pipeline working
- ✅ Successfully creates .FCStd files with 11 screw holes + 4 edge cutouts
- ⚠️ Required manual DXF export step — replaced by `build_plate.py`

**Swillkb2 Plate Validation (Previous):**
- Switches detected: 102 (34 pure + 68 combos)
- Expected: 101 (96 pure + 5 combos)
- Overlap conflicts: 5 marginal (acceptable clearance)

## License

Open source for keyboard design and validation.

## Support

Detailed technical documentation in CLAUDE.md. For analysis methodology and results, see handover.md.
