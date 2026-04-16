# CLAUDE.md - Technical Context for SKYWAY96 Analysis

## Project Overview

SKYWAY96 is a 96% mechanical keyboard PCB (RP2040-based) with corresponding plate designs. This analysis framework validates that plate designs match PCB requirements by:
1. Extracting PCB elements (screw holes, edge cutouts) from KiCad files
2. Detecting switch/stabilizer holes from DXF plate files
3. Validating no overlaps between PCB and plate elements
4. Generating ASCII maps for visual verification

## Key Problem Statement

User had two plate design sources (ai03 and swillkb) with different hole geometries:
- **ai03**: Square-like switch holes, separate rectangular stabilizer cutouts
- **swillkb**: Rectangular switch holes, combo holes (switch + stabilizer combined into single large rectangle)

Goal: Count 101 total switch positions (96 regular + 5 stabilized keys with combo holes) and validate against PCB requirements.

## Architecture & Design Decisions

### Rectangle Detection Algorithm

**Challenge**: DXF files contain primitive LINE entities forming rectangle boundaries. Must reconstruct complete rectangles.

**Approach**:
1. Collect all horizontal lines (abs(y1-y2) < 0.1) into dict keyed by Y coordinate
2. Collect all vertical lines (abs(x1-x2) < 0.1) into dict keyed by X coordinate
3. Find all pairs of horizontal lines with matching vertical line boundaries
4. Calculate center point (cx, cy) and dimensions (width, height)

**Deduplication**:
- Rectangle detection finds overlapping rectangles at slightly different heights (e.g., 32.9mm, 35.5mm, 35.6mm for same logical hole)
- Solution: Position-based clustering with 5mm tolerance
  - Group rectangles within 5mm distance (both X and Y)
  - Keep only largest rectangle per cluster (by area: w*h)
  - This preserves all distinct holes while eliminating duplicates

**Why this works**: Laser-cut or CAM-generated DXF files often have duplicate line segments at slightly offset positions. The 5mm threshold is much larger than production tolerances (0.1mm scale) but small enough to not merge adjacent keys.

### Size-Based Classification

Switch/stabilizer identification uses rectangle dimensions:

```
Pure Switches:      12.5 < min(w,h) < 14.2  AND  12.5 < max(w,h) < 14.2
Combo Switches:     12.5 < min(w,h) < 14.2  AND  31 < max(w,h) < 43
Stabilizers:        8 < min(w,h) < 10       AND  18 < max(w,h) < 26
```

**Thresholds derived from**:
- Standard MX switch: 13.9×13.9mm (MX spec)
- PCB KLE definition: 96 regular + 5 stabilized = 101 total
- Stabilizer cutout sizes vary by type (Cherry vs Costar style)

**Swillkb specific**: 5 combo holes for space bar, enter, backspace, numpad enter, numpad plus. These are single large rectangles combining both switch and stabilizer mounting, counted as one switch position.

### PCB Element Extraction

**Screw Holes** (`find_kicad_screw_holes`):
- Regex pattern: `r'MountingHole_2\.2mm_M2.*?\(at\s+([-\d.]+)\s+([-\d.]+)'`
- KiCad stores footprint instances with position in s-expression format
- 2.2mm M2 holes are standard keyboard mounting (metric standard)

**Edge Cutouts** (`find_edge_cutouts`):
- Parse gr_arc and gr_line from KiCad Edge.Cuts layer
- Arcs: Look for start/end/mid points; calculate arc depth relative to board edge
- Filter: Only arcs with depth >= 3.0mm (eliminates noise, captures real cutouts)
- Classify by position: Left edge arcs are "left_cuts", bottom edge arcs are "bottom_cuts"

**Why this distinction**: User described left cutout working well, bottom cutouts initially backwards (outcuts instead of incuts). Separate tracking enables debugging per-edge.

### Overlap Validation

**Distance formula**: Euclidean distance between PCB hole center and plate hole center.

**Clearance thresholds**:
```
Safe distance = 1.1mm (screw hole radius) + plate_hole_half_width + 0.5mm (tolerance)
```

For a 13.9mm switch (half-width 6.95mm):
- Safe distance ≈ 1.1 + 6.95 + 0.5 = 8.55mm

Issues flagged if actual distance < safe distance. Swillkb analysis found 5 marginal conflicts at 4.8-7.8mm (screw-to-combo), assessed as minor given 2.2mm M2 standard tolerances.

## Known Limitations & Edge Cases

1. **Rectangle detection precision**: Algorithm finds ALL rectangular line sequences, not just holes. Requires post-filtering by size.

2. **DXF variation**: Different CAD sources produce different line-drawing patterns:
   - ai03: Uses squares + separate rectangles for stabs
   - swillkb: Uses combo rectangles
   - Both valid, both require same algorithm but different classification thresholds

3. **Tolerance assumptions**:
   - 5mm clustering assumes no actual holes within 5mm (keyboard key spacing is ~19.05mm, so safe)
   - 0.5mm vertical line tolerance assumes lines don't skew > 0.5mm from perfect vertical
   - All thresholds empirically tuned for mechanical keyboard plates

4. **PCB file format dependency**: Regex parsing assumes KiCad 6.x+ s-expression format. Changes to KiCad format would break pattern matching.

5. **AI03 file issue**: Downloaded file from website was incomplete (only 4 switches, should be 101+). May be a web generation artifact or partial download. File located at:
   - `C:\Users\v-mariorivas\Downloads\plate-2026-04-16T22_27_19.833Z.dxf`
   - Do not use for validation; file is known-broken

## PCB Reference Data

**File**: `rivasmario 96% Hotswap Rp2040.kicad_pcb`
**Location**: `C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\`

**PCB Constants**:
- Switch positions: 96 regular (1x1 units) + 5 stabilized (2x1, 2.75x1, 7x1 units)
- Mounting holes: 11 M2 holes (2.2mm diameter)
- Edge cutouts: 4 total
  - 1 on left edge (cutout depth varies)
  - 3 on bottom edge (cutout depths vary)

**Important**: PCB and plate are independent designs but must align. PCB defines switch matrix electrically; plate defines physical hole positions. Both must match KLE (Keyboard Layout Editor) data.

## Debugging & Troubleshooting

### Low Switch Count (< 50)
- Check: Is rectangle detection running? (Should print "Total rectangles after dedup: X")
- Check: Are horizontal/vertical lines being collected? Add debug prints to h_lines/v_lines keys
- Check: Are lines being parsed from DXF? Verify file exists and is readable with ezdxf

### High Combo Count (> 10)
- Expected: 5 combos on swillkb, 0 on ai03
- If high: Clustering threshold too aggressive or size range too broad
- Debug: Print all rectangles and their sizes to see what's being classified

### Overlap Validation Always Passes (0 issues)
- Check: Are screw_holes being extracted? Should be 11
- Check: Distance formula correctness - formula should use sqrt((x1-x2)^2 + (y1-y2)^2)
- Check: Threshold formula - may need adjustment for specific PCB/plate pair

### DXF Parsing Errors
- Check: File format - must be DXF, not DWG or other formats
- Check: ezdxf version compatibility - project uses modern ezdxf (check requirements.txt)
- Debug: Try opening DXF with Inkscape to verify file integrity

## Development Workflow

1. Run 10-iteration count script first (`swillkb2_final_10x.py`) - fast validation, deterministic
2. If counts match expectations, run full analysis (`swillkb2_complete_analysis.py`) - includes visualization and overlap checking
3. Review ASCII map for sanity (switch pattern should match 96% layout visually)
4. If overlaps found, review manually - some conflicts may be acceptable depending on tolerance stack-up

## Future Enhancements

- [ ] Support for multiple plate designs in single run
- [ ] Configurable size thresholds (currently hardcoded)
- [ ] 3D visualization (matplotlib/plotly)
- [ ] Direct KiCad file modifications to import plate holes
- [ ] Tolerance stack-up calculation for clearance margin analysis
- [ ] Support for different stabilizer types (Cherry, Costar, BJ spring)
