# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Hole-Aware Puzzle Split (for 3D Printing)**: 
  - Upgraded the **Puzzle Split** logic to be "aware" of switch and stabilizer holes.
  - The script now automatically scans the center of your board to find a **"Safe Zone"** (a vertical gap between key columns).
  - It prioritizes splitting through empty space, ensuring that **no switch holes are cut in half**, which drastically improves the mechanical strength of 3D printed plates.
- **Fixed Gerber Export (JLCPCB-Ready)**: 
  - Switched to a **full PCB layer stack** (Edge.Cuts, NPTH Drill, Mask, Copper).
  - This ensures that JLCPCB's online viewer correctly renders the plate with all holes and slots, fixing the "solid block" issue.
- **Form-Fitting Split Mode**: 
  - Generates tight, professional "islands" around rotated/split clusters for Ergo/Alice boards.
- **Enhanced Web UI**:
  - Instant SVG Preview, one-click multi-format downloads.

### Recent fixes (this session):
1. **Intelligent Slicing**: uses high-resolution geometry sampling to find the widest possible X-gap near the board center for the puzzle joint.
2. **Gerber Recognition**: providing dummy copper and solid soldermask layers ensures manufacturing systems treat the FR4 plate as a real PCB.
3. **Continuity Fix**: `emit_dxf` now outputs separate closed loops for split/island layouts.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`.

### 2. Next Technical Steps (Future AI)
- **Manual Split Line**: Allow users to click a location in the UI to manually define the split X-coordinate.
- **Bone Joints**: Implement "Dog-bone" style joints for even higher tensile strength.
- **ISO Enter Cutout**: Add the specific "L-shaped" switch cutout to `cutouts.py`.

**Files to look at first**:
- `scripts/exporters.py`: Gerber stack and Hole-Aware STL split logic.
- `scripts/build_plate.py`: Core logic.
- `app/static/index.html`: UI controls.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
