#!/usr/bin/env python3
import ezdxf
from pathlib import Path

def main():
    dxf = Path(r"C:\Users\v-mariorivas\Downloads\unfucked.dxf")
    doc = ezdxf.readfile(str(dxf))
    msp = doc.modelspace()
    
    circles = list(msp.query('CIRCLE'))
    print(f"Found {len(circles)} CIRCLE entities.")
    for i, c in enumerate(circles[:20]):
        print(f"[{i:2d}] Center:({c.dxf.center.x:6.1f}, {c.dxf.center.y:6.1f}) Radius:{c.dxf.radius:4.1f}")
        
    lines = list(msp.query('LINE'))
    lwpolylines = list(msp.query('LWPOLYLINE'))
    print(f"\nOther entities: {len(lines)} LINEs, {len(lwpolylines)} LWPOLYLINEs")

if __name__ == "__main__": main()
