# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Direct DXF to Gerber Conversion**: 
  - Added a new **"DXF to Gerber"** tab to the web application.
  - Users can upload an existing DXF plate file (manually tweaked) and the system will automatically parse the standard layers (`PLATE_OUTLINE`, `SWITCH_CUTOUTS`, etc.) and generate a high-quality Gerber ZIP for JLCPCB.
  - This leverages the same **geometric subtraction engine** used for the main generator, ensuring transparent holes in FR4 plates.
- **Fixed Gerber Export (JLCPCB-Ready)**: 
  - Uses explicit **geometric subtraction** for Mask/Copper layers.
  - The board is generated as a solid "Material Polygon" (Outline minus Holes), which is the most reliable way to force JLCPCB's automated viewers to render holes correctly.
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
3. **Download Reliability**: Verified and fixed all download path identifiers for the API.

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
