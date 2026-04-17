# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Refactored Geometry Engine (Shapely)**: Fully migrated to **Shapely** for mathematically perfect CAD generation.
  - **Perfect Kerfing**: Applied via `Polygon.buffer()`.
  - **Automatic Unioning**: Prevents overlapping geometry in CAD software.
- **Form-Fitting Split Mode**: 
  - Generates tight, professional "islands" around rotated/split clusters.
  - Unions key footprints and buffers them by the specified `Plate Padding`.
  - Supports separate physical plates in a single DXF file.
- **Robust KLE Parser**: 
  - Spec-compliant state machine for `rx/ry` origins and `r` angles.
  - Handles **ISO Enter** and other complex key shapes (`w2/h2`).
  - Automatic JSON sanitization for raw Keyboard Layout Editor pastes.
- **Enhanced Web UI with SVG Preview**:
  - Instant visual verification before downloading.
  - Default view set to "KLE Mode" + "Paste JSON" for the most common workflow.
  - **GH60/Poker** and **Sandwich Case** mounting presets.

### Recent fixes (this session):
1. **Multi-Island DXF**: Fixed `emit_dxf` to output disconnected islands as separate, closed `LWPOLYLINE` entities.
2. **Helper Function Scope**: Re-ordered the codebase to ensure all helper functions (`validate_screws`, etc.) are always in scope.
3. **Spec-Compliant Cursor**: Fixed cursor reset logic to strictly follow the KLE serialization spec.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`.

### 2. Next Technical Steps (Future AI)
- **ISO Enter Cutout**: Add the specific "L-shaped" switch cutout to `cutouts.py`.
- **Canvas Zoom/Pan**: Improve SVG preview for large layouts.
- **Manual Notch Tool**: Allow users to click on the outline in the web UI to drop in manual notches.

**Files to look at first**:
- `scripts/build_plate.py`: Core logic (Parser, Generator, API).
- `scripts/cutouts.py`: Shape registry.
- `app/main.py`: Web Backend.
- `app/static/`: Web Frontend.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
