#!/usr/bin/env python3
"""Reproducible UV maps and sprites for the Pi renderer (Pillow + NumPy).

The iris is an unwrapped annulus: U = angle, V = pupil to limbus.
Do not replace it with a photograph of an eye. Lid row zero must be black:
the extra outer geometry samples that row to mask the spherical eyeball.
All artwork is generated here; no downloaded assets or runtime generation.
"""
from pathlib import Path
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageOps

OUT = Path(__file__).resolve().parents[1] / "eyes/graphics/christmas"


def save_array(name, values):
    Image.fromarray(np.uint8(np.clip(values, 0, 255))).save(OUT / (name + ".png"))


def maps():
    rng = np.random.default_rng(1225)
    h, w = 256, 1024
    u, v = np.meshgrid(np.linspace(0, 2 * math.pi, w), np.linspace(0, 1, h))
    # Periodic angular harmonics make a seamless iris with fine radial fibres.
    fibres = np.zeros_like(u)
    for frequency in range(40, 280, 7):
        fibres += np.sin(u * frequency + rng.uniform(0, 6.28) + 0.25 * np.sin(v * 9)) / 7
    rays = np.clip(0.76 + 0.23 * fibres, 0.25, 1.3)
    radial = np.sin(np.pi * v) ** 0.45
    iris = np.stack([(70 + 127 * radial) * rays,
                     (31 + 82 * radial) * rays,
                     (12 + 35 * radial) * rays], axis=-1)
    iris *= (0.28 + 0.72 * np.sin(np.pi * v) ** 0.25)[..., None]
    save_array("iris", iris * 0.84)

    # Dark chocolate sclera: no monster veins or bright human eye whites.
    u, v = np.meshgrid(np.linspace(0, 2 * math.pi, 512), np.linspace(0, 1, 256))
    grain = rng.normal(0, 0.6, u.shape)
    shade = 0.65 + 0.35 * np.sin(v * np.pi)
    sclera = np.stack([38 * shade + grain, 23 * shade + grain,
                       17 * shade + grain, np.full_like(u, 255)], axis=-1)
    save_array("sclera", sclera)

    # Fine chestnut fur at the lid margin, fading to black on the outer mask.
    u, v = np.meshgrid(np.linspace(0, 1, 1024), np.linspace(0, 1, 128))
    fur = (0.78 + 0.15 * np.sin(u * 2400 + v * 11)
           + 0.07 * np.sin(u * 4100 - v * 23))
    rim = np.exp(-((v - 0.22) / 0.20) ** 2)
    lid = np.stack([99 * fur * rim, 66 * fur * rim, 38 * fur * rim,
                    np.full_like(u, 255)], axis=-1)
    lid[0, :, :3] = 0
    lid[-1, :, :3] = 0
    save_array("lid", lid)


def nose():
    n = 512
    x, y = np.meshgrid(np.linspace(-1, 1, n), np.linspace(-1, 1, n))
    # Broad, slightly flattened muzzle shape, rounded lower corners.
    q = (x / 0.90) ** 2 + ((y + 0.015) / 0.74) ** 2
    z = np.sqrt(np.maximum(0, 1 - q))
    edge = np.clip((1 - q) * 100, 0, 1)
    light = np.clip(0.2 + 0.62 * z - 0.23 * x - 0.32 * y, 0, 1)
    sheen = np.exp(-(((x + 0.29) / 0.25) ** 2 + ((y + 0.29) / 0.12) ** 2) * 2)
    pin = np.exp(-(((x + 0.43) / 0.07) ** 2 + ((y + 0.30) / 0.055) ** 2) * 2)
    pores = np.random.default_rng(24).normal(0, 0.8, q.shape)
    # Subtle curved nostrils distinguish a nose from a Christmas ornament.
    nostril = np.zeros_like(x)
    for side in (-1, 1):
        nostril += np.exp(-(((x - side * 0.46) / 0.15) ** 2
                            + ((y - 0.26 + 0.15 * abs(x)) / 0.052) ** 2) * 2)
    for name, glow in (("nose", 0), ("nose-lit", 1)):
        red = 39 + 116 * light + 88 * glow * z
        green = 3 + 8 * light + 31 * glow * z ** 3
        blue = 7 + 14 * light + 18 * glow * z ** 3
        rgb = np.stack([red, green, blue], axis=-1)
        rgb *= (1 - nostril * (0.68 - glow * 0.15))[..., None]
        rgb += sheen[..., None] * np.array([72, 60, 55])
        rgb += pin[..., None] * np.array([90, 110, 106])
        rgb += pores[..., None]
        save_array(name, np.dstack([rgb, edge * 255]))
    q = x*x + y*y
    alpha = np.exp(-q * 7.5) * np.clip((1 - q) * 5, 0, 1) * 155
    save_array("nose-halo", np.stack([np.full_like(x, 255), np.full_like(x, 19),
                                      np.full_like(x, 5), alpha], axis=-1))


def bezier(points, count=70):
    a, b, c, d = points
    return [tuple((1-t)**3*a[k] + 3*(1-t)**2*t*b[k] + 3*(1-t)*t*t*c[k] + t**3*d[k]
                  for k in (0, 1)) for t in np.linspace(0, 1, count)]


def accents():
    # Each sprite stays within its own outer-window footprint. Antlers and
    # a leaf-shaped ear provide a readable silhouette without a full head.
    im = Image.new("RGBA", (716, 870))
    draw = ImageDraw.Draw(im)
    branches = [([(394, 342), (398, 244), (341, 191), (352, 58)], 25),
                ([(369, 205), (288, 189), (279, 130), (283, 82)], 17),
                ([(387, 267), (462, 213), (473, 155), (462, 117)], 19),
                ([(353, 128), (416, 100), (425, 68), (419, 32)], 14),
                ([(296, 157), (243, 139), (235, 111), (237, 98)], 12)]
    for points, width in branches:
        curve = bezier(points)
        draw.line(curve, fill=(163, 117, 70, 255), width=width, joint="curve")
        draw.ellipse((curve[-1][0]-width/2, curve[-1][1]-width/2,
                      curve[-1][0]+width/2, curve[-1][1]+width/2), fill=(163, 117, 70, 255))
        draw.line([(x-3,y) for x,y in curve], fill=(218, 179, 115, 255), width=max(2,width//4))
    outline = (bezier([(288, 418), (187, 414), (104, 351), (79, 276)]) +
               bezier([(79, 276), (190, 266), (300, 305), (288, 418)]))
    draw.polygon(outline, fill=(106, 68, 39, 255))
    inner = (bezier([(263, 393), (191, 380), (139, 336), (113, 298)]) +
             bezier([(113, 298), (201, 306), (253, 334), (263, 393)]))
    draw.polygon(inner, fill=(190, 146, 96, 255))
    # Deterministic fine hairs along the edge of the ear.
    rng = random.Random(125)
    for _ in range(420):
        t = rng.random()
        p = outline[int(t * (len(outline)-1))]
        draw.line([p, (p[0] + rng.uniform(-8, 8), p[1] + rng.uniform(-10, 6))],
                  fill=(150, 109, 65, 180), width=1)
    # A tapered furry brow anchors the antler to the eye. In the sprite's
    # final coordinates the eye centre is (358, 559), not the image centre.
    brow = bezier([(155, 489), (234, 306), (488, 306), (563, 489)], count=300)
    for i, (x, y) in enumerate(brow):
        taper = math.sin(math.pi * i / (len(brow)-1)) ** 0.65
        for _ in range(13):
            spread = rng.uniform(-8, 26) * taper
            color = rng.choice([(102,67,38,225), (150,104,59,230),
                                (185,141,91,225), (215,178,127,190)])
            draw.line([(x + rng.uniform(-2,2), y+spread),
                       (x + rng.uniform(-7,7), y+spread-rng.uniform(4,17)*taper)],
                      fill=color, width=1)
    im.save(OUT / "accent-left.png")
    ImageOps.mirror(im).save(OUT / "accent-right.png")


def catchlight():
    im = Image.new("RGBA", (256, 128))
    draw = ImageDraw.Draw(im)
    draw.ellipse((24, 16, 153, 73), fill=(255, 237, 205, 215))
    draw.ellipse((169, 72, 193, 96), fill=(255, 244, 225, 170))
    im.save(OUT / "catchlight.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    maps()
    nose()
    accents()
    catchlight()
    print("Christmas UV maps and sprites written to", OUT)


if __name__ == "__main__":
    main()
