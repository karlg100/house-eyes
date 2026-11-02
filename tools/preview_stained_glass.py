#!/usr/bin/env python3
"""Render CPU equivalents of the full-window and tree shaders without a Pi.

The reference footage and generated artwork are never edited. This renders
the program's projection output. GPU filtering and projector colour may vary.
"""
import argparse
from pathlib import Path
import sys
import types

import numpy as np
from PIL import Image

from preview_christmas import ROOT, load_scene, draw_scene, rasterize


def animated_scene(width, height, radius):
    scene = load_scene("stained-glass", width, height, radius)
    time = [1000.0]
    fake_time = types.SimpleNamespace(time=lambda:time[0])
    # frame() reads the module through its globals; this does not patch the
    # process-wide time module or the real tracker. It makes the preview repeatable.
    scene["time"] = fake_time
    scene["lastFrameTime"] = time[0]-0.1
    scene["startTime"] = time[0]
    scene["startX"] = scene["destX"] = scene["curX"] = 0
    scene["startY"] = scene["destY"] = scene["curY"] = 0
    scene["treeGlow"].clock = lambda:time[0]
    scene["treeGlow"].command("tree off")
    scene["glassDecor"].epoch = time[0]
    return scene,time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--animate", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/stained-glass/preview.png")
    args = parser.parse_args()
    scene = load_scene("stained-glass",1600,800,170,extra=["--tree-mode","on"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Warm the meshes once so the still image doesn't show the lid's
    # first-frame interpolation strip.
    draw_scene(scene)
    rasterize(draw_scene(scene),1600,800).save(args.output)
    print("Still preview:",args.output,flush=True)
    if not args.animate:
        return
    width,height,radius = 960,480,102
    scene,clock = animated_scene(width,height,radius)
    frames = []
    start = clock[0]
    for i in range(64):
        seconds = i/8
        clock[0] = start+seconds
        if i == 6:
            scene["treeGlow"].command("tree pulse 6")
        # A slow glance and return, with a smooth blink midway through it.
        scene["curX"] = 12*np.sin(seconds*np.pi/4)
        scene["curY"] = 2*np.sin(seconds*np.pi/4)
        if i in (24,25):
            scene["blinkStateLeft"] = scene["blinkStateRight"] = 1
            scene["blinkStartTimeLeft"] = scene["blinkStartTimeRight"] = clock[0]-0.1
            scene["blinkDurationLeft"] = scene["blinkDurationRight"] = 0.101
        elif i == 26:
            scene["blinkStateLeft"] = scene["blinkStateRight"] = 2
            scene["blinkStartTimeLeft"] = scene["blinkStartTimeRight"] = clock[0]
            scene["blinkDurationLeft"] = scene["blinkDurationRight"] = 0.26
        frames.append(rasterize(draw_scene(scene,0.5+0.15*np.sin(seconds*np.pi/4)),width,height))
        if i % 16 == 15:
            print("Animated frames:",i+1,"/64",flush=True)
    # Use a shared palette with dithering to retain the marbled-glass texture.
    palette_source = Image.new("RGB", (width,height*4))
    for n,index in enumerate((0,18,36,50)):
        palette_source.paste(frames[index],(0,n*height))
    palette = palette_source.quantize(colors=256)
    frames = [frame.quantize(palette=palette,dither=Image.Dither.FLOYDSTEINBERG) for frame in frames]
    path = args.output.with_suffix(".gif")
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=125,loop=0,disposal=2,optimize=False)
    print("Animation preview:",path,flush=True)


if __name__ == "__main__":
    main()
