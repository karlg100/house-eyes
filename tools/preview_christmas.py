#!/usr/bin/env python3
"""Offline preview of the actual tri-eyes meshes without Pi GPIO or OpenGL.

Runs renderer initialization and frame() with a recording pi3d substitute,
then rasterizes the recorded triangles. Geometry, UVs, placement and draw
order come from tri-eyes.py. Lighting is approximate, not a GPU screenshot.
Requires Pillow, NumPy and svg.path (no pi3d). Also used by integration tests.
"""
import argparse
import math
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EYES = ROOT / "eyes"


class Buffer:
    def __init__(self, shape, vertices, uv, indices, normals, smooth=False):
        self.array_buffer = np.column_stack((vertices, normals, uv)).astype(float)
        self.indices = np.asarray(indices, dtype=int)


class Shape:
    drawn = []

    def __init__(self, *args, x=0, y=0, z=0, **kwargs):
        self.xyz = np.array([x, y, z], dtype=float)
        self.rx = self.ry = 0
        self.alpha = 1
        self.buf = []
        self.custom_data = np.zeros(60)

    def set_textures(self, textures):
        self.texture = textures[0]
        self.textures = textures

    def set_shader(self, shader):
        self.shader = shader

    def set_draw_details(self, shader, textures):
        self.set_shader(shader)
        self.set_textures(textures)

    def set_alpha(self, alpha):
        self.alpha = alpha

    def set_custom_data(self, index_from, data):
        self.custom_data[index_from:index_from+len(data)] = data

    def positionX(self, x):
        self.xyz[0] = x

    def positionY(self, y):
        self.xyz[1] = y

    def positionZ(self, z):
        self.xyz[2] = z

    def rotateToX(self, value):
        self.rx = value

    def rotateToY(self, value):
        self.ry = value

    def re_init(self, pts):
        self.buf[0].array_buffer[:, :3] = pts

    def draw(self):
        self.drawn.append(self)


class Texture:
    def __init__(self, filename, **kwargs):
        self.name = filename
        self.image = np.asarray(Image.open(EYES / filename).convert("RGBA"), dtype=float)
        self.iy, self.ix = self.image.shape[:2]


class Sprite(Shape):
    def __init__(self, w, h, **kwargs):
        super().__init__(**kwargs)
        self.buf = [Buffer(self, [(-w/2,h/2,0), (w/2,h/2,0), (w/2,-h/2,0), (-w/2,-h/2,0)],
                           [(0,0), (1,0), (1,1), (0,1)], [(3,0,1), (1,2,3)], [(0,0,-1)]*4)]


class Lathe(Shape):
    def __init__(self, path, sides):
        super().__init__()
        vertices, normals, uv, faces = [], [], [], []
        length = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(path,path[1:]))
        v = 0
        previous = path[0]
        for i, (x,y) in enumerate(path):
            dx, dy = x-previous[0], y-previous[1]
            distance = math.hypot(dx, dy)
            if distance:
                dx, dy = dx/distance, dy/distance
            v += distance / length
            for j in range(sides+1):
                a = 2 * math.pi * j / sides
                vertices.append((x*math.sin(a), y, x*math.cos(a)))
                normals.append((-math.sin(a)*dy, dx, -math.cos(a)*dy))
                uv.append((1-j/sides, v))
                if i < len(path)-1 and j < sides:
                    n = i*(sides+1)+j
                    faces.extend([(n+1,n,n+sides+1), (n+sides+1,n+sides+2,n+1)])
            previous = (x,y)
        self.buf = [Buffer(self, vertices, uv, faces, normals)]


def load_scene(theme="christmas", width=1600, height=800, radius=160, extra=()):
    """Initialize the real renderer without running its infinite main loop."""
    display = types.SimpleNamespace(width=width, height=height,
                                    set_background=lambda *a: None, loop_running=lambda: True)
    pi3d = types.ModuleType("pi3d")
    pi3d.Shape, pi3d.Buffer, pi3d.Lathe, pi3d.Sprite = Shape, Buffer, Lathe, Sprite
    pi3d.Texture, pi3d.Shader = Texture, lambda name: name
    pi3d.Display = types.SimpleNamespace(create=lambda **k: display)
    pi3d.Camera = pi3d.Light = lambda **k: None
    pi3d.Keyboard = lambda: types.SimpleNamespace(read=lambda: -1)
    pi3d.constants = types.SimpleNamespace(GL_LINEAR=9729, GL_NEAREST=9728)
    pi3d.Utility = types.SimpleNamespace(from_polar=lambda angle:
        (math.cos(math.radians(angle)), math.sin(math.radians(angle))))
    gpio = types.ModuleType("RPi.GPIO")
    gpio.BCM, gpio.IN, gpio.PUD_UP, gpio.LOW = 11, 1, 22, 0
    gpio.setmode = gpio.setup = lambda *a, **k: None
    gpio.input = lambda pin: 1
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    bonnet = types.ModuleType("snake_eyes_bonnet")
    bonnet.SnakeEyesBonnet = None
    modules = {"pi3d":pi3d, "RPi":rpi, "RPi.GPIO":gpio, "snake_eyes_bonnet":bonnet}
    argv = ["tri-eyes.py", "--theme", theme, "--gaze-port", "0", "--no-rogue",
            "--radius", str(radius), "--nose-mode", "on"] + list(extra)
    source = (EYES / "tri-eyes.py").read_text().split("# MAIN LOOP --")[0]
    old_cwd = Path.cwd()
    sys.path.insert(0, str(EYES))
    try:
        os.chdir(EYES)
        # gfxutil must bind to this recording module, even after another test.
        with patch.dict(sys.modules, modules), patch.object(sys, "argv", argv):
            sys.modules.pop("gfxutil", None)
            scene = {"__name__":"preview_renderer", "__file__":str(EYES / "tri-eyes.py")}
            exec(compile(source, str(EYES / "tri-eyes.py"), "exec"), scene)
    finally:
        os.chdir(old_cwd)
        sys.path.pop(0)
    scene["AUTOBLINK"] = False
    scene["startTime"] = scene["time"].time()
    scene["holdDuration"] = 9999
    scene["curX"] = scene["curY"] = 0
    scene["trackingPos"] = 0.4
    return scene


def draw_scene(scene, pupil=0.55):
    Shape.drawn = []
    scene["frame"](pupil)
    return list(Shape.drawn)


def tree_gain(pane, parameters):
    """CPU equivalent of stained_glass.fs, for offline previews only."""
    elapsed, level, progress, animated, steady, _ = parameters
    shimmer = 0.045 * np.sin(elapsed * 0.5 + pane[...,0] * 6.2831853)
    d = (pane[...,1] - (1.12 - 1.24 * progress)) / 0.16
    sweep = np.exp(-d*d) * level
    star_progress = np.clip((progress-0.5)/0.35,0,1)
    star_progress = star_progress**2*(3-2*star_progress)
    star = (pane[...,1] < 0.21) * level * star_progress
    light = 0.73 + shimmer + 0.22*sweep + 0.22*star
    gain = (0.36 + 0.64*steady)*(1-animated) + light*animated
    return np.where(pane[...,2] >= 0.5, np.clip(gain,0,1), 0.73)


def glass_window_colour(uv, body, iris, params):
    """CPU equivalent of glass_window.fs for previewing complete windows."""
    gx,gy,pupil,blink,width,height,enabled,offset,_ = params
    def smooth(a,b,x):
        t=np.clip((x-a)/(b-a),0,1)
        return t*t*(3-2*t)
    def sample(texture,coords):
        coords=coords%1
        ix=(coords[...,0]*(texture.ix-1)).astype(int)
        iy=(coords[...,1]*(texture.iy-1)).astype(int)
        return texture.image[iy,ix,:3]/255
    p=(uv-0.5)*np.array([width,height])
    border=2*uv-1
    anchor=(1-border[...,0]**4)*(1-border[...,1]**4)
    flow=anchor*(.30+.70*np.exp(-.30*np.sum(p*p,axis=-1)))
    rest=p-np.array([gx,gy])*flow[...,None]
    blink=np.clip(blink,0,1)
    rest[...,1]+=.38*blink*p[...,1]/np.sqrt(.04+p[...,1]**2)*np.exp(-.60*np.abs(p[...,1]))*anchor
    rest+=.08*(pupil-.5)*p/np.sqrt(.10+np.sum(p*p,axis=-1))[...,None]*flow[...,None]
    p=rest
    r=np.linalg.norm(p,axis=-1)
    angle=np.arctan2(p[...,1],p[...,0])/(2*np.pi)+.5
    material=np.stack([angle+offset,np.log(1+r*1.8)*.60],axis=-1)
    glass=sample(body,material)
    x=np.abs(p[...,0])
    h=0.53*np.maximum(0,1-x*x)**0.65*(1-np.clip(blink,0,1))
    edge=np.abs(p[...,1])-h
    within=1-smooth(0.98,1,x)
    inside=(1-smooth(-0.008,0.008,edge))*within
    eye=glass.copy()
    pr=0.14+0.13*np.clip(pupil,0,1)
    radial=np.clip((r-pr)/(0.52-pr),0,1)
    iriscolour=sample(iris,np.stack([angle,radial],axis=-1))
    mask=(1-smooth(0.51,0.53,r))[...,None]
    eye=eye*(1-mask)+iriscolour*mask
    mask=(1-smooth(pr-0.008,pr+0.008,r))[...,None]
    eye=eye*(1-mask)+glass*np.array([0.10,0.12,0.25])*mask
    lead=np.maximum(1-smooth(0.009,0.021,np.abs(r-0.52)),
                    1-smooth(0.007,0.017,np.abs(r-pr)))[...,None]
    black=np.array([0.006,0.008,0.018])
    eye=eye*(1-lead)+black*lead
    colour=glass*(1-inside[...,None])+eye*inside[...,None]
    lead=((1-smooth(0.009,0.023,np.abs(edge)))*within)[...,None]
    colour=colour*(1-lead)+black*lead
    return (glass*(1-enabled)+colour*enabled)*255


def rasterize(shapes, width, height):
    rgb = np.zeros((height, width, 3), dtype=float)
    depth = np.full((height,width), np.inf)
    for shape in shapes:
        a = math.radians(shape.rx)
        b = math.radians(shape.ry)
        rx = np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
        ry = np.array([[math.cos(b),0,math.sin(b)],[0,1,0],[-math.sin(b),0,math.cos(b)]])
        rotation = ry @ rx
        buf = shape.buf[0]
        vertices = buf.array_buffer[:,:3] @ rotation.T + shape.xyz
        normals = buf.array_buffer[:,3:6] @ rotation.T
        screen = vertices.copy()
        screen[:,0] += width/2
        screen[:,1] = height/2 - screen[:,1]
        tex = shape.texture
        for ids in buf.indices:
            tri = screen[ids]
            xmin, ymin = np.maximum(0, np.floor(tri[:,:2].min(axis=0))).astype(int)
            xmax, ymax = np.minimum([width-1,height-1], np.ceil(tri[:,:2].max(axis=0))).astype(int)
            if xmax < xmin or ymax < ymin:
                continue
            x0,y0 = tri[0,:2]
            x1,y1 = tri[1,:2]
            x2,y2 = tri[2,:2]
            den = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(den) < 1e-8:
                continue
            yy,xx = np.mgrid[ymin:ymax+1,xmin:xmax+1]
            xx,yy = xx+0.5,yy+0.5
            w0 = ((y1-y2)*(xx-x2)+(x2-x1)*(yy-y2))/den
            w1 = ((y2-y0)*(xx-x2)+(x0-x2)*(yy-y2))/den
            w2 = 1-w0-w1
            weights = np.stack([w0,w1,w2],axis=-1)
            z = weights @ tri[:,2]
            region_depth = depth[ymin:ymax+1,xmin:xmax+1]
            inside = (weights.min(axis=-1) >= -1e-9) & (z < region_depth)
            if not np.any(inside):
                continue
            uv = weights @ buf.array_buffer[ids,6:8]
            # pi3d uses GL_REPEAT; v stays within [0,1], u may include a 0.5 offset.
            tx = (uv[:,:,0] % 1 * (tex.ix-1)).astype(int)
            ty = np.clip(uv[:,:,1]*(tex.iy-1),0,tex.iy-1).astype(int)
            colors = tex.image[ty,tx].copy()
            alpha = colors[:,:,3] / 255 * shape.alpha
            inside &= alpha > 0.001
            if shape.shader == "shaders/glass_window":
                colors[:,:,:3] = glass_window_colour(uv,shape.textures[0],shape.textures[1],
                                                     shape.custom_data[48:57])
            elif shape.shader == "shaders/stained_glass":
                data_map = shape.textures[1]
                mx = np.clip((uv[:,:,0]*data_map.ix).astype(int),0,data_map.ix-1)
                my = np.clip((uv[:,:,1]*data_map.iy).astype(int),0,data_map.iy-1)
                pane = data_map.image[my,mx,:3]/255
                colors[:,:,:3] *= tree_gain(pane,shape.custom_data[48:54])[:,:,None]
            elif shape.shader != "uv_flat":
                normal = weights @ normals[ids]
                lighting = np.clip(normal @ np.array([0,-0.707,-0.707]),0,1)+0.2
                colors[:,:,:3] *= lighting[:,:,None]
            region = rgb[ymin:ymax+1,xmin:xmax+1]
            blended = colors[:,:,:3]*alpha[:,:,None]+region*(1-alpha[:,:,None])
            region[inside] = blended[inside]
            region_depth[inside] = z[inside]
    return Image.fromarray(np.uint8(np.clip(rgb,0,255)))


def glow_animation(scene, shapes, width, height, output):
    """Static mesh pose + actual NoseGlow envelope, reduced for easy sharing."""
    decor = scene["decor"]
    base = rasterize([s for s in shapes if s not in (decor.nose,decor.lit,decor.halo)],
                     width,height).convert("RGBA")
    now = [0.0]
    glow = scene["NoseGlow"]("off", clock=lambda: now[0])

    def paste(frame, sprite, alpha):
        if alpha <= 0:
            return
        vertices = sprite.buf[0].array_buffer[:,:3]
        size = tuple(np.rint(np.ptp(vertices[:,:2],axis=0)).astype(int))
        tex = Image.fromarray(sprite.texture.image.astype("uint8")).resize(size, Image.Resampling.LANCZOS)
        tex.putalpha(tex.getchannel("A").point(lambda n: int(n*alpha)))
        xy = (round(width/2+sprite.xyz[0]-size[0]/2), round(height/2-sprite.xyz[1]-size[1]/2))
        frame.alpha_composite(tex, xy)

    frames = []
    for i in range(72):
        now[0] = i / 10
        if i == 12:
            glow.command("nose pulse 4")
        level = glow.level()
        frame = base.copy()
        paste(frame, decor.halo, level)
        paste(frame, decor.nose, 1)
        paste(frame, decor.lit, level)
        frames.append(frame.convert("RGB").resize((960,round(height*960/width)), Image.Resampling.LANCZOS))
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=100,
                   loop=0, optimize=False, disposal=2)
    print("Nose glow demonstration (static eye pose):", output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/christmas-preview.png")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--radius", type=int, default=160)
    parser.add_argument("--animate", action="store_true", help="also write a nose-glow GIF")
    args = parser.parse_args()
    scene = load_scene(width=args.width, height=args.height, radius=args.radius)
    shapes = draw_scene(scene)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rasterize(shapes,args.width,args.height).save(args.output)
    print("Offline mesh preview (approximate lighting):", args.output)
    if args.animate:
        glow_animation(scene,shapes,args.width,args.height,args.output.with_suffix(".gif"))


if __name__ == "__main__":
    main()
