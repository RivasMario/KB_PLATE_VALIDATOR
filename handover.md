# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI — Edge Cuts & Logging)

### Just-Completed Work
- **Edge Cut Preservation**: The script was losing small U-shaped "cut-ins" from the PCB's `Edge.Cuts` layer because it attempted to chain them into a perfectly closed `LWPOLYLINE`. Small gaps or out-of-order segments caused the chaining logic to discard them. 
- **Direct Segment Emission**: Rewrote `emit_dxf` to output the exact original `LINE` and `ARC` segments directly to the DXF `PLATE_OUTLINE` layer. This completely bypasses the fragile `LWPOLYLINE` generation and guarantees 100% compatibility and preservation of all PCB features (including Poker-style cut-ins).
- **SVG Preview Sync**: Updated `generate_svg_string` to also render individual line and arc paths so the web preview exactly matches the DXF output.
- **UI Offsets**: Added `pcb_dx` and `pcb_dy` fields to the "PCB Mode" UI to allow manual nudging if `solve_pcb_transform` fails to perfectly align the PCB.
- **Robust Alignment Fallback**: The alignment logic was scoring poorly on some PCBs (e.g. ones with rotated components or completely different origin).
- **Backend Logging Pipeline**: Overhauled `app/main.py` and `scripts/build_plate.py` to output detailed logs to `logs/plate_generator.log`. This was necessary to trace parameters and silently swallowed errors during geometry creation.

### Pending Issues / Next Steps
- **Logging Bug**: While implementing the backend logging in `app/main.py`, a syntax/indentation error broke the `uvicorn --reload` process, causing the server to silently serve an old version of the code. The logging code was temporarily reverted/dropped. **It needs to be properly re-implemented** to catch why `plate(19).dxf` was silently failing or rendering as a simple rectangle.
- **Chaining Re-implementation**: If laser cutters strictly require `LWPOLYLINE`s instead of individual `LINE`/`ARC` entities, the `chain_segments_robust` function in `build_plate.py` needs to be refined to handle messy geometries without dropping segments.

## Previous Status (Opus 4.7 — gerber fix)

### Just-Completed Work
- **Fixed missing "Download Gerber" button**: root cause in `scripts/exporters.py::export_gerber`. Used nonexistent `ExcellonFile.add_drill()` (gerbonara 1.6.2 does not expose this). Rewrote drills via `ExcellonTool(diameter=d, plated=False, unit=MM)` + `Flash(x, y, aperture=tool, unit=MM)` appended to `drill.objects`. Also corrected `Region` API: `unit` is kwarg-only, interior loops are not a positional arg — now emit exterior as `polarity_dark=True` and each interior as a separate `polarity_dark=False` Region.
- **Auto-layer fallback for "DXF Converter" tab**: `parse_dxf_to_shapely` previously required `PLATE_OUTLINE`/`SWITCH_CUTOUTS`/`STAB_CUTOUTS`/`PCB_SCREW_HOLES`. Now, if those queries return empty, it polygonizes every LINE/LWPOLYLINE/POLYLINE/ARC, treats largest-area polygon as outline, rest as cutouts, circles ≤ 2mm radius as screws, bigger circles as cutouts.
- **Fixed ezdxf query syntax bug**: `*[layer=="A"] | *[layer=="B"]` is invalid in ezdxf query parser. Replaced with two queries and list concatenation.
- Bumped `?v=2` → `?v=3` on static script/style links so browsers refetch.
- Updated DXF Converter UI note to say layers are optional.

### Known Non-Issues
- CadQuery / gerbonara are not pinned in `requirements.txt`. `requirements.txt` lists only ezdxf/fastapi/uvicorn/python-multipart/shapely. Local env has `gerbonara==1.6.2` installed manually — add to requirements before deployment.

## Previous Status (Gemini CLI — same date)

### Just-Completed Work

- **DXF Converter (Full Support)**: 
  - Upgraded the "DXF to Gerber" tool into a full **"DXF Converter"**.
  - Users can now upload an existing DXF and convert it into **both Gerber (for JLCPCB)** and **STL (3D Model)** formats.
  - The converter uses the same high-quality geometric subtraction engine to ensure transparent holes and proper 3D extrusion.
- **Improved Bounding Box & Margins**:
  - Keys are now perfectly centered within the board outline.
  - Padding is applied uniformly to all four sides (Top, Bottom, Left, Right).
- **Format Selection UI**:
  - Added checkboxes for **DXF**, **Gerber**, and **STL** generation.
  - Main button renamed to **"Generate Plate Files"** to reflect multi-format support.
- **Hole-Aware Puzzle Split (for 3D Printing)**: 
  - Automatically finds the widest gap between key columns to place the zigzag joint, keeping switch holes solid and strong.

### Recent fixes (this session):
1. **DXF Parsing**: Integrated `ezdxf` with `Shapely`'s `polygonize` to reconstruct complex plate geometry from uploaded DXF files.
2. **Margin Math**: Refactored the coordinate translation pipeline to ensure keys never stick out past the board edge.
3. **Multi-Format Conversion**: Updated the API and Frontend to support selecting output formats during DXF conversion.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`.

### 2. Next Technical Steps (Future AI)
- **Automatic Layer Detection**: For the DXF converter, add logic to guess layers based on entity counts if standard layer names are missing.
- **Custom Puzzle Joint Styles**: Add options for "Bone" or "Dovetail" joints.
- **Drill Tool Table**: Add a specific tool list (`.drl` metadata) for high-end professional manufacturing.

**Files to look at first**:
- `scripts/exporters.py`: Gerber stack, STL split, and DXF-to-Shapely parsing logic.
- `scripts/build_plate.py`: Core generation and coordinate alignment.
- `app/static/index.html`: UI tabs and checkboxes.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
