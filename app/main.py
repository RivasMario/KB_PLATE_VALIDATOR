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
    kle_file: Optional[UploadFile] = File(None),
    kle_text: Optional[str] = Form(None),
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
    if not kle_file and not kle_text:
        raise HTTPException(status_code=400, detail="Must provide either KLE file or KLE JSON text.")

    # Create a temporary directory for the session
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Handle KLE input
        kle_path = None
        if kle_file and kle_file.filename:
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
                kle_path=str(kle_path) if kle_path else None,
                kle_text=kle_text,
                out_path=str(out_path), 
                pcb_path=str(pcb_path) if pcb_path else None,
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

        # Return JSON with SVG and download link
        # Instead of cleaning up immediately, we store the temp_dir path in a global dict
        # or just rely on OS temp cleanup. For this MVP, we just leave it in temp_dir.
        
        return JSONResponse({
            "svg": res["svg"],
            "dxf_id": out_path.name,
            "metadata": {
                "keys": res["keys"],
                "plate_w": res["plate_w"],
                "plate_h": res["plate_h"],
                "screws": res["screws"],
                "issues": len(res["issues"])
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/api/download/{dxf_id}")
async def api_download_dxf(dxf_id: str):
    # In a real app we'd map this ID to the secure temp directory.
    # For this MVP, we find the file in the tempdir's parent.
    temp_parent = Path(tempfile.gettempdir())
    # find the file
    for p in temp_parent.glob(f"*/{dxf_id}"):
        if p.is_file():
            return FileResponse(
                path=p,
                filename="plate.dxf",
                media_type="application/dxf"
            )
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
