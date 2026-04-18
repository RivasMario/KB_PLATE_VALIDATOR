# Handover Notes

## Current Project Status (Latest — April 17, 2026, Opus 4.7 — Flat Closed LWPOLYLINE outline + matched SVG)

### Just-Completed Work (this turn)
- **Replaced bulge-LWPOLYLINE outline with flat closed LWPOLYLINE** (`scripts/build_plate.py::emit_dxf`):
  - Prior bulge-based emission caused two regressions: SendCutSend still rejected with *"close all open entities"*, and tiny "balls at corners" appeared (bulge sign convention ambiguity at near-zero-sweep arcs).
  - Now: chain raw segments → flatten each arc into 24 line segments via `seg_to_polyline` → emit one closed `LWPOLYLINE` per loop with `close=True` and no bulges. Open chains (chaining failure) emit as a single open `LWPOLYLINE` and log a WARNING.
  - Logs: `emit_dxf outline: closed_loops=N open_chains=N total_segments_in=M`.
- **Rewrote `generate_svg_string` outline path to match DXF exactly** — same `chain_polylines` + flatten approach, emits `<path d="M ... L ... Z">` for each closed loop. SVG preview can no longer disagree with DXF (was previously rendering inverted-U via buggy `sweep_flag` arc commands using `abs(bulge)`).
- **Lifted `seg_to_polyline` and `chain_polylines` (formerly nested `legacy_chain`) to module scope** so both `emit_dxf` and `generate_svg_string` use one canonical chainer. `chain_polylines` extends in BOTH directions (head and tail) so reversed segments don't get orphaned.
- **Mandatory kill-and-rebuild on every code change** (per user): no longer relying on `uvicorn --reload` to pick up `scripts/build_plate.py` edits. Stop the bg uvicorn task, restart with `.venv312/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.

### Previous Work (still relevant)
- **Re-implemented backend logging** (`scripts/build_plate.py`, `app/main.py`):
  - Idempotent `_setup_logger()` returning the `'plate'` logger, writing to `logs/plate_generator.log` with `DEBUG` level. Idempotent guard (`_plate_configured` attribute) so `uvicorn --reload` re-imports don't stack handlers — this was what broke the previous attempt.
  - `generate_plate` now logs every decision point: input params, KLE key count, PCB screw/switch/edge-segment counts, `solve_pcb_transform` params, `legacy_chain` results (closed loops + valid polys), the `pcb_raw_segments / pad / fillet → use_raw_segments` gating decision, `is_simple_box` classification, emit summary, and Gerber/STL export errors with traceback.
  - `app/main.py` logs incoming `/api/generate` params and result IDs, and uses `log.exception` on failures so tracebacks land in `logs/plate_generator.log` instead of being swallowed.
- **Confirmed plate(19) "simple rectangle" bug was the stale-code-served scenario** caused by the prior session's broken `--reload`. With the new logging in place, edge-cut chaining works correctly: 24 raw segments → 1 closed loop → `pcb_outline_poly` selected → `is_simple_box=False`. No code path bug.
- **Fixed inverted-arc bug in `emit_dxf`** (`scripts/build_plate.py`):
  - `arc_from_3pts` already pre-swaps `(s, e)` for clockwise-original arcs so that ezdxf's CCW-only `add_arc` traces through the correct mid-point. The old code did `if not is_ccw: s, e = e, s` *after that*, double-swapping and emitting the **complementary** arc on the wrong side of the chord.
  - Symptom: U-shaped Edge.Cuts notches were drawn as inverted-U bumps (cup facing inward, opening outward), which is physically impossible to mill with a circular cutter. Fix removes the second swap; notches now bulge correctly into the plate (cup deep, opening at edge), corner chamfers also correct.
- **Closed-loop outline emission for SendCutSend / fab houses** (`scripts/build_plate.py::emit_dxf`):
  - Previous output was 24 individual `LINE`/`ARC` entities — SendCutSend rejected with *"close all open entities and reupload"*.
  - Now runs `chain_segments_robust` on the raw segments and emits each closed loop as a single `LWPOLYLINE` with bulges (preserves arcs as true curves, not flattened polylines). Vertices use `format='xyb'` and `close=True`.
  - Open chains (if chaining ever fails) fall back to individual entities via a chord-and-bulge → arc reconstruction so no segment is silently dropped. Closed/open counts logged at INFO.

### Local Dev Environment Notes (NEW, important)
- `requirements.txt` lists only `ezdxf / fastapi / uvicorn / python-multipart / shapely`. **`gerbonara==1.6.2` and `cadquery` must be installed manually** for the Gerber and STL download buttons to light up. If they're missing, `exporters.py` catches the `ImportError`, sets `GerberFile = None` / `cq = None`, and `generate_plate` logs `export_gerber failed` / `export_stl failed`. The UI silently omits the corresponding download buttons (no error toast).
- **Python version conflict**: `gerbonara==1.6.2` requires `>=3.12`; `cadquery-ocp` has no wheels for Python 3.14 (Fedora 43's default). Use Python **3.12** locally:
  ```
  uv python install 3.12
  uv venv --python 3.12 .venv312
  uv pip install --python .venv312/bin/python -r requirements.txt gerbonara==1.6.2 cadquery
  .venv312/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ```
- The `Dockerfile` is currently pinned to `python:3.11-slim` — **this will break the next container rebuild** because gerbonara 1.6.2 needs ≥3.12. Bump the base image to `python:3.12-slim` before next ghcr.io publish.

### Pending Issues / Next Steps
- ~~**Bump Dockerfile base image to `python:3.12-slim`**~~ — **DONE** (was already 3.12-slim; gerbonara + cadquery already in requirements.txt).
- **GitHub Actions CI/CD** — **DONE** (April 18, 2026): `.github/workflows/docker-publish.yml` builds on every PR, publishes `ghcr.io/rivasmario/kb_plate_validator:latest` on every merge to main. PR template added. `.gitignore` updated to exclude `.venv*/`.
- **Make ghcr.io package public** after first workflow run: GitHub → Packages → `kb_plate_validator` → Package settings → Change visibility → Public. (Repo is already public; packages still default to private.)
- **STL viewer** installed locally as `f3d` (lightweight, dnf package).
- **Verify SendCutSend acceptance** of the new closed-LWPOLYLINE DXF output (should resolve their "open entities" error).
- **Generate-route still single-threaded** — large plates take ~7s for legacy_chain alignment. Not blocking but a future optimization opportunity.

## Previous Status (Gemini CLI — April 17, 2026, Edge Cuts & Logging — superseded)

### Just-Completed Work
- **Edge Cut Preservation**: Switched `emit_dxf` from fragile `LWPOLYLINE` chaining to direct `LINE`/`ARC` segment emission to preserve PCB cut-ins. *(Note: this session re-introduced LWPOLYLINE chaining via the robust chainer to satisfy SendCutSend, which rejects open entities. Both issues now solved together.)*
- **SVG Preview Sync**: Updated `generate_svg_string` to also render individual line and arc paths so the web preview matches the DXF output.
- **UI Offsets**: Added `pcb_dx` / `pcb_dy` fields in "PCB Mode" UI for manual nudging when `solve_pcb_transform` misaligns.
- **Robust Alignment Fallback**: Added scoring fallback for PCBs with rotated components / different origins.
- **Backend Logging Pipeline**: Started but reverted in-session due to indentation error breaking `uvicorn --reload`. *Re-implemented this session — see top.*

### Pending Issues that were carried over
- ~~Logging bug~~ — **DONE this session**.
- ~~Chaining re-implementation for laser cutters~~ — **DONE this session** via `chain_segments_robust` in `emit_dxf`.

## Previous Status (Opus 4.7 — gerber fix, April 17 earlier)

### Just-Completed Work
- **Fixed missing "Download Gerber" button**: `scripts/exporters.py::export_gerber` rewrote drills via `ExcellonTool(diameter=d, plated=False, unit=MM)` + `Flash(...)` (gerbonara 1.6.2 doesn't expose `add_drill`). Region API: `unit` is kwarg-only; emit exterior as `polarity_dark=True` and each interior as a separate `polarity_dark=False` Region.
- **Auto-layer fallback for "DXF Converter" tab**: `parse_dxf_to_shapely` now polygonizes every `LINE`/`LWPOLYLINE`/`POLYLINE`/`ARC`, treats largest-area polygon as outline, rest as cutouts, circles ≤2mm radius as screws.
- **Fixed ezdxf query syntax bug**: replaced invalid `*[layer=="A"] | *[layer=="B"]` with two queries + list concatenation.
- Bumped `?v=2` → `?v=3` on static script/style links to bust browser cache.

### Known Non-Issues (resolved this session)
- ~~CadQuery / gerbonara are not pinned in `requirements.txt`~~ → see Local Dev Environment Notes above. Container/`requirements.txt` update is in Pending Issues.

## Previous Status (Gemini CLI — same date, DXF Converter)

### Just-Completed Work
- **DXF Converter (Full Support)**: Upload existing DXF → convert to both Gerber (JLCPCB) and STL.
- **Improved Bounding Box & Margins**: Keys now perfectly centered; uniform padding.
- **Format Selection UI**: Checkboxes for DXF / Gerber / STL; main button renamed to "Generate Plate Files".
- **Hole-Aware Puzzle Split (3D Printing)**: Finds widest gap between key columns to place zigzag joint.

### Recent fixes (that session)
1. **DXF Parsing**: Integrated `ezdxf` with Shapely's `polygonize` for complex plate geometry.
2. **Margin Math**: Refactored coord pipeline so keys never overshoot board edge.
3. **Multi-Format Conversion**: API + frontend now support per-format selection during DXF conversion.

### 1. Web stack details
Deployable as a single container via the root `Dockerfile`. **Bump base image to python:3.12-slim** (see Pending Issues).

### 2. Next Technical Steps (Future AI)
- **Automatic Layer Detection**: For DXF converter, guess layers based on entity counts when standard names missing.
- **Custom Puzzle Joint Styles**: "Bone" or "Dovetail" joints.
- **Drill Tool Table**: `.drl` metadata for high-end professional manufacturing.

**Files to look at first**:
- `scripts/build_plate.py`: Core generation, alignment, edge-cut chaining, `emit_dxf`, logging.
- `scripts/exporters.py`: Gerber stack, STL split, DXF-to-Shapely parsing.
- `app/main.py`: FastAPI routes, request logging.
- `app/static/index.html`: UI tabs and checkboxes.
- `logs/plate_generator.log`: Debug log written by every `/api/generate` call.

**Do NOT regenerate `add_holes_freecad.py` work** — user has moved past it.
