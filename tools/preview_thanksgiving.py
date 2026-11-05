#!/usr/bin/env python3
"""Preview the Thanksgiving runtime scene and turkey shader without a Pi."""
import argparse
from pathlib import Path
import types

import numpy as np
from PIL import Image

from preview_christmas import ROOT, load_scene, draw_scene, rasterize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--animate",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/thanksgiving/preview.png")
    args=parser.parse_args()
    scene=load_scene("thanksgiving",1600,800,170)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    rasterize(draw_scene(scene),1600,800).save(args.output)
    print("Still preview:",args.output,flush=True)
    if not args.animate:
        return
    scene=load_scene("thanksgiving",800,400,85)
    clock=[1000.0]
    scene["time"]=types.SimpleNamespace(time=lambda:clock[0])
    scene["lastFrameTime"]=clock[0]-.125
    scene["startTime"]=clock[0]
    frames=[]
    for i in range(48):
        seconds=i/8
        clock[0]=1000+seconds
        scene["curX"]=16*np.sin(seconds*np.pi/3)
        scene["curY"]=3*np.sin(seconds*np.pi/3)
        if i == 21:
            scene["blinkStateLeft"]=scene["blinkStateRight"]=1
            scene["blinkStartTimeLeft"]=scene["blinkStartTimeRight"]=clock[0]
            scene["blinkDurationLeft"]=scene["blinkDurationRight"]=.126
        frames.append(rasterize(draw_scene(scene,.5+.18*np.sin(seconds*np.pi/3)),800,400))
        if i%16 == 15:
            print("Frames:",i+1,"/48",flush=True)
    palette_source=Image.new("RGB",(800,1600))
    for j,index in enumerate((0,12,22,36)):
        palette_source.paste(frames[index],(0,j*400))
    palette=palette_source.quantize(colors=256)
    frames=[f.quantize(palette=palette,dither=Image.Dither.FLOYDSTEINBERG) for f in frames]
    path=args.output.with_suffix(".gif")
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=125,
                   loop=0,disposal=2,optimize=False)
    print("Animation preview:",path,flush=True)


if __name__ == "__main__":
    main()
