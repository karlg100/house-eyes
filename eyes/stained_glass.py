"""Backlit stained-glass tree, with independent light per glass pane.

The artwork is immutable. A precomputed data map identifies each pane's
phase and vertical centre, so the GPU animates light without sliding or
warping the lead lines. No runtime image processing or extra dependencies.
"""
import math


def lighting_parameters(controller, epoch):
    """Six floats for GLSL unif[16:18], also used by the offline preview."""
    level = controller.level()  # advances automatic pulses using a monotonic clock
    now = controller.clock()
    with controller.lock:
        mode = controller.mode
        start, duration = controller.start, controller.duration
    progress = min(1.0, max(0.0, (now-start)/duration)) if start is not None else 0.0
    animated = mode == "auto" or start is not None
    # Keep shader time small without a visible jump: 120*pi matches 0.5 rad/s.
    elapsed = (now-epoch) % (120.0 * math.pi)
    return (elapsed, level, progress, float(animated), float(mode == "on"), 0.0)


class GlassDecor:
    def __init__(self, pi3d, radius, spacing, options, controller):
        self.controller = controller
        self.epoch = controller.clock()
        self.radius = radius
        self.options = options
        glass = pi3d.Texture("graphics/stained-glass/sclera.png", mipmap=False,
                             filter=pi3d.constants.GL_LINEAR)
        iris = pi3d.Texture("graphics/stained-glass/iris.png", mipmap=False,
                            filter=pi3d.constants.GL_LINEAR)
        panel_shader = pi3d.Shader("shaders/glass_window")
        self.panels = []
        for i, x in enumerate((-spacing, 0, spacing)):
            panel = pi3d.Sprite(w=radius*options.window_width,
                                h=radius*options.window_height,
                                x=x, z=-radius-43)
            panel.set_draw_details(panel_shader, [glass, iris])
            panel.set_custom_data(48, (0, 0, 0.5, 0, options.window_width,
                                      options.window_height, float(i != 1), i*0.31, 0))
            self.panels.append(panel)
        texture = pi3d.Texture("graphics/stained-glass/tree.png", mipmap=False,
                               filter=pi3d.constants.GL_LINEAR, blend=True)
        data_map = pi3d.Texture("graphics/stained-glass/tree-panes.png", mipmap=False,
                                filter=pi3d.constants.GL_NEAREST)
        width = radius * 2.0 * options.tree_scale
        self.tree = pi3d.Sprite(w=width, h=width * texture.iy / texture.ix,
                               x=0, y=options.tree_y, z=-radius-44)
        self.tree.set_draw_details(pi3d.Shader("shaders/stained_glass"), [texture, data_map])

    def draw_windows(self, left_rotation, right_rotation, pupil, left_blink, right_blink):
        for panel, rotation, blink in zip((self.panels[0],self.panels[2]),
                                         (left_rotation,right_rotation),(left_blink,right_blink)):
            rx,ry = map(math.radians,rotation)
            panel.set_custom_data(48, (-0.75*math.sin(ry), -0.65*math.sin(rx),
                                      pupil, blink))
        # Let the middle glass field share a gentle version of the pair's
        # gaze flow while the tree keeps its own lighting animation.
        lrx,lry = map(math.radians,left_rotation)
        rrx,rry = map(math.radians,right_rotation)
        self.panels[1].set_custom_data(48,(-0.1875*(math.sin(lry)+math.sin(rry)),
                                          -0.1625*(math.sin(lrx)+math.sin(rrx)),
                                          pupil,0.15*(left_blink+right_blink)))
        for panel in self.panels:
            panel.draw()

    def draw(self):
        self.tree.set_custom_data(48, lighting_parameters(self.controller, self.epoch))
        self.tree.draw()
