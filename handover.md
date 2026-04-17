# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Gerber & 3D (STL) Export Automation**: 
  - Direct generation of **JLCPCB-ready Gerber ZIPs** using `gerbonara`. All features are mapped to the `Edge.Cuts` layer.
  - Automatic **3D Model (STL)** extrusion using `CadQuery`. Plates are extruded to 1.5mm (standard FR4/aluminum thickness).
  - Integrated into the Web UI: Users can now download DXF, Gerber, and STL with one click.
- **Refactored Geometry Engine (Shapely)**: Fully migrated to **Shapely** for mathematically perfect CAD generation.
  - **Perfect Kerfing**: Applied via `Polygon.buffer()`.
  - **Automatic Unioning**: Prevents overlapping geometry in CAD software.
- **Form-Fitting Split Mode**: 
  - Generates tight, professional "islands" around rotated/split clusters.
  - Unions key footprints and buffers them by the specified `Plate Padding`.
- **Robust KLE Parser**: 
  - Spec-compliant state machine for `rx/ry` origins and `r` angles.
  - handles ISO Enter and complex key shapes (`w2/h2`).
  - Automatic JSON sanitization for Keyboard Layout Editor pastes.
- **Enhanced Web UI with SVG Preview**:
  - Instant visual verification before downloading.
  - Default view set to "KLE Mode" + "Paste JSON".

### Recent fixes (this session):
1. **Export Stability**: Resolved `gerbonara` and `cadquery` integration issues, ensuring robust multi-format output.
2. **Standard Trig Rotation**: Verified and implemented standard rotation formulas for perfect alignment on split ergo boards.
3. **Multi-Format Downloads**: Generic download endpoint in FastAPI supports DXF, ZIP, and STL.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`. 
**Note**: `cadquery` is a heavy dependency and requires several megabytes of OCP libraries. It is included in the updated `requirements.txt`.

### 2. Next Technical Steps (Future AI)
- **Configurable Thickness**: Add a UI slider for STL thickness (e.g. 1.2mm, 1.5mm, 4.0mm).
- **ISO Enter Cutout**: Add the specific "L-shaped" switch cutout to `cutouts.py`.
- **Canvas Zoom/Pan**: Improve SVG preview for large layouts.

**Files to look at first**:
- `scripts/exporters.py`: Gerber and STL generation logic.
- `scripts/build_plate.py`: Core logic (Parser, Generator, API).
- `app/main.py`: Web Backend.
- `app/static/`: Web Frontend.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
