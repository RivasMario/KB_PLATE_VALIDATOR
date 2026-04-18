import logging
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
from scripts.build_plate import generate_plate  # noqa: E402 — also wires up 'plate' logger

log = logging.getLogger('plate')

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
    split: bool = Form(False),
    puzzle_split: bool = Form(False),
    gen_dxf: bool = Form(True),
    gen_gerber: bool = Form(True),
    gen_stl: bool = Form(True),
):
    log.info(
        "/api/generate kle_file=%s kle_text_len=%s pcb_file=%s switch_type=%s stab_type=%s "
        "kerf=%s pad=%s screw_diameter=%s pcb_dx=%s pcb_dy=%s no_auto_align=%s clearance=%s "
        "snap_screws=%s fillet=%s screw_preset=%s screw_custom=%s screw_inset=%s split=%s "
        "puzzle_split=%s gen_dxf=%s gen_gerber=%s gen_stl=%s",
        (kle_file.filename if kle_file else None),
        (len(kle_text) if kle_text else 0),
        (pcb_file.filename if pcb_file else None),
        switch_type, stab_type, kerf, pad, screw_diameter, pcb_dx, pcb_dy,
        no_auto_align, clearance, snap_screws, fillet, screw_preset, screw_custom,
        screw_inset, split, puzzle_split, gen_dxf, gen_gerber, gen_stl,
    )

    if not kle_file and not kle_text:
        raise HTTPException(status_code=400, detail="Must provide either KLE file or KLE JSON text.")

    if not any([gen_dxf, gen_gerber, gen_stl]):
        raise HTTPException(status_code=400, detail="At least one generation format must be selected.")

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
                screw_inset=screw_inset,
                split=split,
                puzzle_split=puzzle_split,
                gen_dxf=gen_dxf,
                gen_gerber=gen_gerber,
                gen_stl=gen_stl
            )
        except Exception as e:
            log.exception("generate_plate raised")
            raise HTTPException(status_code=400, detail=str(e))

        dxf_id = out_path.name if gen_dxf and out_path.exists() else None
        gerber_id = Path(res["gerber_path"]).name if res.get("gerber_path") else None
        stl_id = Path(res["stl_path"]).name if res.get("stl_path") else None
        log.info(
            "/api/generate result dxf=%s gerber=%s stl=%s gerber_error=%s stl_error=%s issues=%d",
            dxf_id, gerber_id, stl_id, res.get("gerber_error"), res.get("stl_error"), len(res["issues"]),
        )

        # Return JSON with SVG and download link
        return JSONResponse({
            "svg": res["svg"],
            "dxf_id": dxf_id,
            "gerber_id": gerber_id,
            "stl_id": stl_id,
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
        log.exception("/api/generate server error")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/api/convert-dxf")
async def api_convert_dxf(
    dxf_file: UploadFile = File(...),
    gen_gerber: bool = Form(True),
    gen_stl: bool = Form(True),
    thickness: float = Form(1.5),
):
    from scripts.exporters import parse_dxf_to_shapely, export_gerber, export_stl
    
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Save DXF
        dxf_path = temp_dir / f"input_{uuid.uuid4()}.dxf"
        with dxf_path.open("wb") as buffer:
            shutil.copyfileobj(dxf_file.file, buffer)
            
        # Parse
        geo = parse_dxf_to_shapely(str(dxf_path))
        if not geo["outline"]:
            raise HTTPException(status_code=400, detail="Could not find valid outline in PLATE_OUTLINE layer")
            
        response_data = {}

        # Generate Gerber
        if gen_gerber:
            out_zip = temp_dir / f"gerber_{uuid.uuid4()}.zip"
            export_gerber(geo["outline"], geo["cutouts"], geo["screws"], geo["screw_radius"], str(out_zip))
            response_data["gerber_id"] = out_zip.name

        # Generate STL
        if gen_stl:
            out_stl = temp_dir / f"model_{uuid.uuid4()}.stl"
            export_stl(geo["outline"], geo["cutouts"], geo["screws"], geo["screw_radius"], str(out_stl), thickness=thickness)
            response_data["stl_id"] = out_stl.name
        
        return JSONResponse(response_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Conversion failed: {str(e)}")

@app.get("/api/download/{file_id}")
async def api_download_file(file_id: str):
    temp_parent = Path(tempfile.gettempdir())
    for p in temp_parent.glob(f"*/{file_id}"):
        if p.is_file():
            # Set media type based on extension
            media_type = "application/octet-stream"
            if p.suffix == ".dxf": media_type = "application/dxf"
            elif p.suffix == ".zip": media_type = "application/zip"
            elif p.suffix == ".stl": media_type = "application/vnd.ms-pki.stl"
            
            return FileResponse(
                path=p,
                filename=f"plate{p.suffix}",
                media_type=media_type
            )
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
