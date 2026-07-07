import ezdxf
from ezdxf.addons.drawing import matplotlib
import os

brain_dir = "/home/diddy/.gemini/antigravity-cli/brain/c5047865-f0f4-48ad-86d3-12f2e29bec7b"

def render_dxf_to_png(dxf_path, png_name):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    fig = matplotlib.qsave(msp, os.path.join(brain_dir, png_name), bg="#1e1e1e")
    print(f"Rendered {png_name}")

files = [
    ("test_Skyway96.dxf", "skyway96.png"),
    ("test_DeltaSplit75_RevA.dxf", "deltasplit_reva.png"),
    ("test_DeltaSplit75_RevB.dxf", "deltasplit_revb.png"),
    ("test_Lelepad_Left.dxf", "lelepad_left.png"),
    ("test_Lelepad_Right.dxf", "lelepad_right.png")
]

for dxf, png in files:
    try:
        render_dxf_to_png(dxf, png)
    except Exception as e:
        print(f"Failed {dxf}: {e}")
