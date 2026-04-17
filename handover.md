# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Refactored Geometry Engine (Shapely)**: Ripped out manual coordinate math and replaced it with the **Shapely** geometric engine.
  - **Perfect Kerfing**: Kerf is now applied via `Polygon.buffer()`, ensuring mathematically perfect expansion/contraction of even the most complex shapes.
  - **Automatic Unioning**: Switch and stabilizer cutouts are now cleanly merged using `unary_union()`, preventing overlapping geometry errors in CAD/CAM software.
  - **Robust Validation**: Screw hole validation now uses high-precision geometric intersection tests.
- **Robust KLE Parser (Rotation-Aware)**: Implemented a full KLE state-machine parser.
  - **Rotations**: Corrected handling of `r`, `rx`, `ry` properties. Plate outlines now correctly encompass rotated/split layouts (e.g., Alice, Ergo).
  - **Secondary Boxes**: Added support for `w2`, `h2`, `x2`, `y2`, ensuring ISO Enter and other multi-part keys are correctly bounded.
  - **JSON Sanitization**: Added automatic regex-based quoting of KLE raw data keys (e.g., `{y:0}` -> `{"y":0}`) so users can paste directly from Keyboard Layout Editor.
- **Enhanced Web UI with SVG Preview**:
  - **Instant Preview**: The web app now renders a beautiful SVG preview of the plate layout immediately upon generation. Users can verify the design before downloading the DXF.
  - **UI Optimization**: "KLE Mode" and "Paste Raw JSON" are now the default selections.
  - **New Presets**: Added `Poker (Standard 60% Tray Mount)` preset for quick mounting hole generation.
- **Containerized Web Application**: Created a standalone FastAPI-based website for generating plates.
  - **Dockerized**: Fully deployable via the included `Dockerfile`.

**Test file (working):** `output/skyway96_plate.dxf`.

### Recent fixes (this session):
1. **Rotation Origin Logic**: Fixed the "switch off the plate" bug by correctly tracking the rotation cluster origin in the KLE parser.
2. **SCS-Ready DXF**: Re-implemented `emit_dxf` to output Shapely polygons as clean `LWPOLYLINE` entities.
3. **Regex Sanitizer**: Resolved parsing errors when users paste raw JavaScript-style objects from KLE.

### 1. Web stack details

The application is now deployable as a single container.

**Deployment recommendation:**
- Host the backend on Fly.io, Railway, or Render.
- Frontend is served statically by the FastAPI backend for simplicity.

### 2. Next Technical Steps (Future AI)

- **ISO Enter Shape**: Add a specific ISO enter cutout shape to `scripts/cutouts.py` and logic in `build_entities` to detect and use it when `w2/h2` match ISO specs.
- **Support for more KiCad entities**: Support for `gr_poly` or `gr_circle` on `Edge.Cuts`.
- **Canvas Zoom/Pan**: Improve the web SVG preview with zoom and pan capabilities for large boards.

**Files to look at first**:
- `scripts/build_plate.py`: Core generation and KLE parsing logic.
- `scripts/cutouts.py`: Extensible registry for switch and stabilizer shapes.
- `app/main.py`: FastAPI routes.
- `app/static/`: Frontend source.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
