# GEMINI.md - Agent Instructions & Workflows

## Overview
This file provides specific instructions for Gemini CLI (or other AI agents) working on the **KB_PLATE_VALIDATOR** project. It supplements `CLAUDE.md` with agent-specific operation details.

## Primary Workflow: PCB Element Injection
The project's main value is the automated injection of PCB elements (mounting holes, edge cutouts) into an existing plate DXF using FreeCAD.

### Execution Steps
1.  **Extract & Inject**: Run `python scripts/add_holes_freecad.py`.
    *   This script parses the KiCad PCB file for coordinates.
    *   It generates a FreeCAD macro `add_holes_macro.py`.
    *   It executes `freecadcmd.exe` to import the DXF, add circles, and export a merged DXF.
2.  **Validate**: Run `python scripts/validate_new_plate.py <path_to_merged_dxf>`.
    *   Confirm the 15 circles (11 screw, 4 edge) are present.
    *   Check for overlap conflicts between PCB elements and switch holes.

## Tool Configurations
- **FreeCAD Path**: `C:\Users\v-mariorivas\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe`
- **KiCad PCB**: `C:\Users\v-mariorivas\OneDrive - Microsoft\Desktop\96_ Hotswap Keyboard PCB\KiCAD Source Files\rivasmario 96% Hotswap Rp2040.kicad_pcb`
- **Reference Plate**: `C:\Users\v-mariorivas\Downloads\cc1e0e052d37d91e9d1f8f9d7166eea779a44e9f_switch.dxf`

## Coding Standards for Agents
- **Path Handling**: Always use `pathlib.Path` for cross-platform compatibility, especially when dealing with Windows paths and FreeCAD's preference for forward slashes in macros.
- **DXF Parsing**: When adding or modifying validation logic, ensure support for both `LINE` and `LWPOLYLINE` entities using the `msp.query('LINE LWPOLYLINE')` pattern.
- **FreeCAD Macros**: Use the `importDXF` module directly for `insert` and `export` operations in headless mode, as standard `Import` calls may fail without a GUI context.

## Troubleshooting
- **DXF Not Exporting**: Check the macro output in `add_holes_freecad.py`. If `importDXF.export` fails, ensure the document has objects and `doc.recompute()` was called.
- **Zero Holes Detected**: Ensure the DXF isn't using a non-standard entity type. Current support includes `LINE` and `LWPOLYLINE`.
