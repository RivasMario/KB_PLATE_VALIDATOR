import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import the plate generator
# We assume the current directory is the project root
import sys
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)
from scripts.build_plate import generate_plate

app = FastAPI(title="KB Plate Validator Web")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("app/static/index.html")

@app.post("/api/generate")
async def api_generate_plate(
    kle_file: UploadFile = File(...),
    pcb_file: Optional[UploadFile] = File(None),
    switch_type: int = Form(1),
    stab_type: int = Form(0),
    kerf: float = Form(0.0),
    pad: float = Form(0.0),
    screw_diameter: float = Form(2.4),
    pcb_dx: float = Form(0.0),
    pcb_dy: float = Form(0.0),
    no_auto_align: bool = Form(False),
    clearance: float = Form(0.5),
    snap_screws: bool = Form(False),
    fillet: float = Form(0.0),
    screw_preset: Optional[str] = Form(None),
    screw_custom: Optional[str] = Form(None),
    screw_inset: float = Form(5.0),
):
    # Create a temporary directory for the session
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Save KLE file
        kle_path = temp_dir / f"kle_{uuid.uuid4()}.json"
        with kle_path.open("wb") as buffer:
            shutil.copyfileobj(kle_file.file, buffer)

        # Save PCB file if provided
        pcb_path = None
        if pcb_file and pcb_file.filename:
            pcb_path = temp_dir / f"pcb_{uuid.uuid4()}.kicad_pcb"
            with pcb_path.open("wb") as buffer:
                shutil.copyfileobj(pcb_file.file, buffer)

        # Output path
        out_path = temp_dir / f"plate_{uuid.uuid4()}.dxf"

        # Generate the plate
        try:
            res = generate_plate(
                str(kle_path), str(out_path), pcb_path=str(pcb_path) if pcb_path else None,
                switch_type=switch_type, stab_type=stab_type,
                kerf=kerf, pad=pad, screw_diameter=screw_diameter,
                pcb_dx=pcb_dx, pcb_dy=pcb_dy,
                no_auto_align=no_auto_align, clearance=clearance,
                snap_screws=snap_screws, fillet=fillet,
                screw_preset=screw_preset if screw_preset else None,
                screw_custom=screw_custom if screw_custom else None,
                screw_inset=screw_inset
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check if the output file was created
        if not out_path.exists():
            raise HTTPException(status_code=500, detail="DXF generation failed (output file missing)")

        # Prepare metadata headers (X-Metadata-*)
        headers = {
            "X-Keys": str(res["keys"]),
            "X-Plate-Width": str(res["plate_w"]),
            "X-Plate-Height": str(res["plate_h"]),
            "X-Screws": str(res["screws"]),
            "X-Issues": str(len(res["issues"])),
            "Access-Control-Expose-Headers": "X-Keys, X-Plate-Width, X-Plate-Height, X-Screws, X-Issues, Content-Disposition"
        }

        # Return the file
        return FileResponse(
            path=out_path,
            filename="plate.dxf",
            media_type="application/dxf",
            headers=headers
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    # Note: Temp files are not automatically cleaned here because FileResponse 
    # might still be reading them. In a real production app, we'd use BackgroundTasks.
    # But for MVP, they'll just stay in the system's temp dir.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
