
import json
from scripts.build_plate import generate_plate
from pathlib import Path

# Simple KLE with one 2u stabilized key
kle_data = [
    ["", {"w": 2}, ""]
]

res = generate_plate(
    kle_text=json.dumps(kle_data),
    out_path="repro.dxf",
    gen_gerber=False,
    gen_stl=False
)

print(f"Generated {res['out_path']}")
print(f"Issues: {res['issues']}")
