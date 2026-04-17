# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Containerized Web Application**: Created a standalone FastAPI-based website for generating plates.
  - **Backend**: FastAPI app (`app/main.py`) that accepts file uploads (KLE JSON, KiCad PCB) and returns the generated DXF.
  - **Frontend**: Clean, modern Vanilla HTML/CSS/JS interface (`app/static/`) with tabbed "PCB Mode" and "KLE Mode".
  - **Refactored Core**: `scripts/build_plate.py` now has a programmatic `generate_plate()` API.
  - **Dockerized**: Added `Dockerfile` for easy deployment.
- **Integrated `screw_presets.py` into `build_plate.py`**: Added CLI arguments `--screw-preset`, `--screw-custom`, and `--screw-inset`. Supports KLE-only mode (Mode B) and overriding PCB screws.
- **Plate outline follows PCB's Edge.Cuts shape**: When `--pcb` is provided, the script now extracts all `Edge.Cuts` segments (lines and arcs), transforms them, and uses them as the plate outline.
- **Corner fillets on plate outline**: Added `--fillet` flag to add small radii to the corners of the plate outline (both for rectangular and notched outlines).
- **LWPOLYLINE with bulge for arcs**: Updated `emit_dxf` to use `LWPOLYLINE` with bulges for all arcs (notches, fillets), creating more robust and compatible DXF output for SendCutSend.
- **Improved Alignment Solver**: Robustly matches multiple landmark keys to find the best alignment even when KLE and PCB key counts differ.
- **README documentation**: Updated with Web App instructions, Mode B examples, and detailed flag tables.

**Test file (working):** `output/skyway96_plate.dxf` (generated from `skyway96_kle.json` + SKYWAY-96 KiCad).

### Recent fixes (this session):
1. **Full PCB Outline**: `find_all_edge_cuts` extracts the entire perimeter from KiCad, ensuring perfect case fit.
2. **Robust Registration**: Landmark-based NN scoring handles "extra" keys in KLE layouts without shifting the entire alignment by 0.5u.
3. **SCS-Ready DXF**: Single-loop `LWPOLYLINE` output (where possible) and bulge-based arcs prevent "open entity" errors.
4. **Web API**: Programmatic entry point in `build_plate.py` allows third-party integrations and web serving.

### 1. Web stack details

The application is now deployable as a single container.

**Deployment recommendation:**
- Host the backend on Fly.io, Railway, or Render.
- Frontend is served statically by the FastAPI backend for simplicity.
- Endpoint shape: `POST /api/generate` accepts `multipart/form-data`.
- Metadata is returned in HTTP headers (`X-Keys`, `X-Plate-Width`, etc.).

### 2. Next Technical Steps (Future AI)

- **discretize_segments improvements**: Further refine the number of steps or use a proper geometric intersection for validation to avoid false positives on boundary screws.
- **Support for more KiCad entities**: Currently handles `gr_line` and `gr_arc`. Support for `gr_poly` or `gr_circle` on `Edge.Cuts` would improve compatibility.
- **Multi-loop support**: If the PCB has multiple `Edge.Cuts` loops (e.g., internal cutouts), the script currently combines them into one discretized list.
- **Web UI enhancements**: Add a canvas-based preview of the DXF before downloading.

**Files to look at first**:
- `app/main.py`: The FastAPI backend.
- `app/static/`: The frontend source.
- `scripts/build_plate.py`: The core generation logic.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
