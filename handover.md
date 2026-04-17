# Handover Notes

## Current Project Status (Latest — April 17, 2026, Gemini CLI)

### Just-Completed Work

- **Integrated `screw_presets.py` into `build_plate.py`**: Added CLI arguments `--screw-preset`, `--screw-custom`, and `--screw-inset`. Supports KLE-only mode (Mode B) and overriding PCB screws.
- **Plate outline follows PCB's Edge.Cuts shape**: When `--pcb` is provided, the script now extracts all `Edge.Cuts` segments (lines and arcs), transforms them, and uses them as the plate outline.
- **Corner fillets on plate outline**: Added `--fillet` flag to add small radii to the corners of the plate outline (both for rectangular and notched outlines).
- **LWPOLYLINE with bulge for arcs**: Updated `emit_dxf` to use `LWPOLYLINE` with bulges for all arcs (notches, fillets), creating more robust and compatible DXF output for SendCutSend.
- **Improved Alignment Solver**: Robustly matches multiple landmark keys to find the best alignment even when KLE and PCB key counts differ.
- **README documentation**: Updated with Mode B examples and detailed flag tables for kerf, switch/stab types, and screw presets.

**Test file (working):** `output/skyway96_plate.dxf` (generated from `skyway96_kle.json` + SKYWAY-96 KiCad).

### Recent fixes (this session):
1. **Full PCB Outline**: `find_all_edge_cuts` extracts the entire perimeter from KiCad, ensuring perfect case fit.
2. **Robust Registration**: Landmark-based NN scoring handles "extra" keys in KLE layouts without shifting the entire alignment by 0.5u.
3. **SCS-Ready DXF**: Single-loop `LWPOLYLINE` output (where possible) and bulge-based arcs prevent "open entity" errors.

### 1. Website deployment — two-mode plan

User wants to host this like http://builder.swillkb.com/. Decided on a two-mode UI:

**Mode A: "PCB Mode"** — upload a KiCad `.kicad_pcb`. Auto-extracts switches (alignment anchors), M2 screw holes, Edge.Cuts notches. Same as current `scripts/build_plate.py` invocation with `--pcb` + `--snap-screws`. Target user: people who've designed their own PCB (like user + SKYWAY-96).

**Mode B: "KLE Mode"** — paste a KLE JSON (or paste a keyboard-layout-editor.com URL). No PCB. Screw positions come from a preset generator instead of KiCad extraction. Target user: people using off-the-shelf PCBs / prototyping.

**Scaffolded foundation (completed):** `scripts/screw_presets.py` is now integrated into `build_plate.py`.
- `four_corners(plate_w, plate_h, inset=5)` — 4 screws
- `six_perimeter(plate_w, plate_h)` — 4 corners + 2 mid-edge
- `grid(plate_w, plate_h, cols, rows)` — regular grid
- `between_rows(keys, plate_w, pad, U1)` — left/right screws between each key row
- `custom_from_string("x1,y1;x2,y2;...")` — manual pixel-coord list    
- `PRESETS` dict — string → callable, for CLI `--screw-preset 4corners`

**Web stack recommendation** (not prescriptive):
- FastAPI for the Python wrapper, since all our code is Python and fast plate-gen is <1s.
- Next.js or plain vanilla HTML frontend, embedding keyboard-layout-editor.com in an iframe for KLE input OR just a textarea for JSON.
- Host the backend on Fly.io / Railway / Render; frontend on Vercel or same box.
- Endpoint shape: `POST /generate { mode: "pcb"|"kle", kle: ..., pcb_file?: base64, options: {...} }` → returns DXF bytes as `application/dxf`.
- Cache by content hash — same inputs shouldn't re-run.

**UI skeleton (user approved):**
```
[ PCB Mode | KLE Mode ]   ← tab switch at top
──────────────────────
Mode-specific inputs (PCB upload / KLE textarea + screw preset dropdown)
──────────────────────
Shared: switch type (0-3), stab type (0-2), kerf, pad, screw diameter  
──────────────────────
[Generate DXF]   [Preview]
```

**Effort estimates:**
- MVP (CLI+API, single HTML page, no preview): 1-2 days.
- Polished (KLE preview, DXF preview pane, presets): ~1 week.
- Production (rate limit, queue, accounts): 2-3 weeks.

**Biggest blockers flagged** (from live discussion):
- PCB upload users are the minority; Mode B must be fully functional for the site to be useful.
- KLE edge-cases: swillkb handles weird layouts we haven't tested. Gather test fixtures before going public.

### 2. Next Technical Steps (Future AI)

- **discretize_segments improvements**: Further refine the number of steps or use a proper geometric intersection for validation to avoid false positives on boundary screws.
- **Support for more KiCad entities**: Currently handles `gr_line` and `gr_arc`. Support for `gr_poly` or `gr_circle` on `Edge.Cuts` would improve compatibility.
- **Multi-loop support**: If the PCB has multiple `Edge.Cuts` loops (e.g., internal cutouts), the script currently combines them into one discretized list.

**Files to look at first**:
- `scripts/build_plate.py` — the one script that matters. All logic lives here: KLE parsing, kb_builder-ported polygons, KiCad extraction, auto-align, validator, DXF writer.
- `scripts/screw_presets.py` — pure-Python screw-position generators for Mode B (KLE-only, no PCB).
- `skyway96_kle.json` — the test KLE at repo root (user's layout; includes dead "LED on/off" key not on PCB).
- `output/skyway96_plate.dxf` — last known-good output.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
