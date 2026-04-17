# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Fixed Gerber Export (JLCPCB-Ready)**: 
  - Switched from a single file to a **full PCB layer stack** (Edge.Cuts, NPTH Drill, Mask, Copper).
  - This fixes the "solid block" issue on JLCPCB's viewer. The holes and outline are now correctly identified as physical board features.
- **STL Puzzle Split (for 3D Printing)**: 
  - Added an optional **"Puzzle Split"** feature for STLs.
  - Large plates are automatically split down the middle with a **trapezoidal zigzag joint**.
  - The two halves are saved in a single STL file but moved slightly apart (5mm), allowing you to print them separately on smaller beds and lock them together securely.
- **Form-Fitting Split Mode**: 
  - Generates tight, professional "islands" around rotated/split clusters.
  - Unions key footprints and buffers them by the specified `Plate Padding`.
- **Enhanced Web UI**:
  - Added checkboxes for **"Split Plates"** and **"Puzzle Split STL"**.
  - Multi-format download buttons (DXF, Gerber, STL).

### Recent fixes (this session):
1. **Gerber Recognition**: providing dummy copper and solid soldermask layers ensures manufacturing automated systems treat the FR4 plate as a real PCB.
2. **Zigzag Solid Math**: used CadQuery's boolean intersection logic to cleanly slice the extruded solid with a custom tooth path.
3. **Continuity Fix**: `emit_dxf` now correctly identifies and outputs separate closed loops for split/island layouts.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`.

### 2. Next Technical Steps (Future AI)
- **Configurable Split X**: Allow users to choose the X-coordinate for the puzzle split instead of defaulting to center.
- **Drill Metadata**: Add tool sizes to the Excellon Drill file for even better compatibility.
- **Advanced Puzzle Shapes**: Add options for different joint types (e.g., bone-shaped, dovetail).

**Files to look at first**:
- `scripts/exporters.py`: Gerber stack and STL split logic.
- `scripts/build_plate.py`: Core generation and routing logic.
- `app/static/index.html`: UI controls.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
