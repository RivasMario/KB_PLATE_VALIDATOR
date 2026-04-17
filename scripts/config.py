import os
from pathlib import Path

# Base paths
HOME = Path.home()
WORKSPACE = HOME / "Documents" / "GitHub" / "KB_PLATE_VALIDATOR"
KICAD_PROJECT = HOME / "Documents" / "GitHub" / "SKYWAY-96"

# KiCad PCB File (Source of truth for mounting holes & edge cutouts)
KICAD_PCB = KICAD_PROJECT / "KiCAD Source Files" / "rivasmario 96% Hotswap Rp2040.kicad_pcb"

# Plate DXF Files (Test inputs)
# Default to Downloads, but allow override via environment variable
INPUT_DXF = Path(os.getenv("PLATE_INPUT_DXF", HOME / "Downloads" / "unfucked.dxf"))
OUTPUT_DXF = Path(os.getenv("PLATE_OUTPUT_DXF", HOME / "Downloads" / "96plate_CLEAN_WITH_PCB.dxf"))
MACRO_FILE = Path(os.getenv("PLATE_MACRO_FILE", HOME / "Downloads" / "add_holes_macro.py"))

# FreeCAD Command List
if os.name == 'nt':
    FREECAD_CMD = [str(Path(r"C:\Users\v-mariorivas\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"))]
else:
    # On Linux, try to find freecadcmd or freecad
    import shutil
    if shutil.which("flatpak"):
        FREECAD_CMD = ["flatpak", "run", "--command=freecadcmd", "--filesystem=host", "org.freecad.FreeCAD"]
    else:
        fc_exe = shutil.which("freecadcmd") or shutil.which("freecad") or "/usr/bin/freecadcmd"
        FREECAD_CMD = [str(fc_exe)]
