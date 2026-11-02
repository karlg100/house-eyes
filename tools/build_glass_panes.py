#!/usr/bin/env python3
"""Build a shader DATA map from black leading in the generated tree artwork.

This does not change the artwork. R = deterministic random phase per pane;
G = pane centre Y; B = 255 for detected panes, zero for leading/background.
Run only at authoring time. The compact PNG is included for the Pi.
"""
from collections import deque
from pathlib import Path
import json

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "eyes/graphics/stained-glass"


def build():
    source = Image.open(ASSETS / "tree.png").convert("RGBA")
    source.thumbnail((512, 768), Image.Resampling.LANCZOS)
    rgba = np.asarray(source)
    height, width = rgba.shape[:2]
    inside = (rgba[:, :, :3].max(axis=2) > 56) & (rgba[:, :, 3] > 200)
    seen = np.zeros((height, width), dtype=bool)
    data = np.zeros((height, width, 3), dtype=np.uint8)
    rng = np.random.default_rng(12252026)
    panes = []
    for y in range(height):
        for x in range(width):
            if not inside[y, x] or seen[y, x]:
                continue
            queue, pixels = deque([(x, y)]), []
            seen[y, x] = True
            while queue:
                cx, cy = queue.popleft()
                pixels.append((cx, cy))
                for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                    if 0 <= nx < width and 0 <= ny < height and inside[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx] = True
                        queue.append((nx, ny))
            if len(pixels) < 20:
                continue
            points = np.asarray(pixels)
            cy = float(points[:,1].mean()) / (height-1)
            phase = int(rng.integers(1, 255))
            data[points[:,1],points[:,0]] = (phase, round(cy*255), 255)
            panes.append({"pixels":len(pixels), "center_y":round(cy,4), "phase":phase})
    Image.fromarray(data).save(ASSETS / "tree-panes.png")
    (ASSETS / "tree-panes.json").write_text(json.dumps({
        "width":width, "height":height, "panes":panes}, indent=2)+"\n")
    print("Detected",len(panes),"glass panes; wrote data map",data.shape)


if __name__ == "__main__":
    build()
