"""Seasonal configuration, glow timing and reindeer decor."""

import argparse
import math
import random
import threading
import time


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def theme_options(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--theme", choices=("halloween", "christmas", "stained-glass", "thanksgiving"), default="halloween")
    parser.add_argument("--nose-mode", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--nose-every", type=positive, nargs=2, default=(12.0, 35.0),
                        metavar=("MIN", "MAX"))
    parser.add_argument("--nose-scale", type=positive, default=0.78)
    parser.add_argument("--nose-y", type=finite, default=0.0)
    parser.add_argument("--no-antlers", action="store_true")
    parser.add_argument("--tree-mode", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--tree-every", type=positive, nargs=2, default=(8.0, 18.0))
    parser.add_argument("--tree-scale", type=positive, default=1.0)
    parser.add_argument("--tree-y", type=finite, default=0.0)
    parser.add_argument("--window-width", type=positive, default=2.3,
                        help="stained-glass window width in eye radii")
    parser.add_argument("--window-height", type=positive, default=4.0,
                        help="stained-glass window height in eye radii")
    parser.add_argument("--beak-scale", type=positive, default=1.0,
                        help="Thanksgiving beak size multiplier")
    parser.add_argument("--beak-y", type=finite, default=0.0,
                        help="Thanksgiving beak vertical adjustment in pixels, positive up")
    args, _ = parser.parse_known_args(argv)
    if args.nose_every[0] > args.nose_every[1]:
        parser.error("--nose-every MIN must be <= MAX")
    if args.tree_every[0] > args.tree_every[1]:
        parser.error("--tree-every MIN must be <= MAX")
    return args


def lid_weights(tracking, blink, christmas=False):
    """Keep reindeer eyes softly open while preserving full blink closure."""
    upper, lower = tracking, 1.0 - tracking
    if christmas:
        upper, lower = 0.16 + 0.35 * upper, 0.16 + 0.35 * lower
    return upper + blink * (1.0 - upper), lower + blink * (1.0 - lower)


class NoseGlow:
    """Thread-safe, monotonic glow envelope shared by UDP input and drawing.

    Modes: auto schedules a new pulse after each random quiet interval;
    on holds full brightness; off leaves the unlit red nose visible.
    A pulse temporarily overrides any mode, then returns to that mode.
    """

    def __init__(self, mode="auto", every=(12.0, 35.0), clock=time.monotonic, rng=None,
                 command_word="nose"):
        if mode not in ("auto", "on", "off"):
            raise ValueError("invalid nose mode")
        if len(every) != 2 or not all(math.isfinite(n) and n > 0 for n in every) or every[0] > every[1]:
            raise ValueError("invalid random interval")
        self.mode = mode
        self.command_word = command_word
        self.every = every
        self.clock = clock
        self.rng = rng or random.Random()
        self.lock = threading.Lock()
        self.start = None
        self.duration = 0.0
        self.next_pulse = self.clock() + self.rng.uniform(*every)

    def command(self, message):
        """Accept 'nose auto|on|off' or 'nose pulse [0.5..30 seconds]'.

        Invalid packets do not change state. Nose commands do not refresh
        gaze timestamps, so a show cue cannot hold a stale tracking target.
        """
        words = message.lower().split()
        if len(words) < 2 or words[0] != self.command_word:
            return False
        action = words[1]
        duration = 4.0
        if action == "pulse" and len(words) in (2, 3):
            try:
                duration = float(words[2]) if len(words) == 3 else duration
            except ValueError:
                return False
            if not math.isfinite(duration) or not 0.5 <= duration <= 30.0:
                return False
        elif action not in ("auto", "on", "off") or len(words) != 2:
            return False
        with self.lock:
            now = self.clock()
            if action == "pulse":
                self.start, self.duration = now, duration
            else:
                self.mode, self.start = action, None
                self.next_pulse = now + self.rng.uniform(*self.every)
        return True

    def level(self):
        with self.lock:
            now = self.clock()
            if self.start is not None and now >= self.start + self.duration:
                self.start = None
                self.next_pulse = now + self.rng.uniform(*self.every)
            if self.start is None and self.mode == "auto" and now >= self.next_pulse:
                self.start, self.duration = now, self.rng.uniform(2.5, 5.0)
            if self.start is None:
                return 1.0 if self.mode == "on" else 0.0
            # Smooth fade in, a warm plateau, then smooth fade out. No strobe.
            t = max(0.0, (now - self.start) / self.duration)
            ramp = min(1.0, t / 0.22, (1.0 - t) / 0.32)
            return max(0.0, ramp * ramp * (3.0 - 2.0 * ramp))


class ChristmasDecor:
    """Small unlit alpha sprites; keeps the existing pi3d eye pipeline."""

    def __init__(self, pi3d, radius, spacing, options, glow):
        self.glow = glow
        shader = pi3d.Shader("uv_flat")

        def sprite(name, width, height, x=0, y=0, z=-200):
            texture = pi3d.Texture("graphics/christmas/" + name + ".png",
                                   mipmap=False, filter=pi3d.constants.GL_LINEAR, blend=True)
            shape = pi3d.Sprite(w=width, h=height, x=x, y=y, z=z)
            shape.set_draw_details(shader, [texture])
            return shape

        self.accents = []
        self.radius = radius
        self.shines = [sprite("catchlight", radius * 0.48, radius * 0.24,
                              x=x, z=-radius - 2) for x in (-spacing, spacing)]
        self.spacing = spacing
        if not options.no_antlers:
            for side, x in (("left", -spacing), ("right", spacing)):
                self.accents.append(sprite("accent-" + side, radius * 2.8, radius * 2.8,
                                           x=x, y=radius * 0.4, z=-radius - 43))
        size = radius * options.nose_scale * 2.0
        # Draw far-to-near; the glow must never obscure the nose's surface.
        self.halo = sprite("nose-halo", size * 2.5, size * 2.5,
                           y=options.nose_y, z=-radius - 44)
        self.nose = sprite("nose", size, size, y=options.nose_y, z=-radius - 45)
        self.lit = sprite("nose-lit", size, size, y=options.nose_y, z=-radius - 46)

    def draw_accents(self):
        for shape in self.accents:
            shape.draw()

    def draw_shines(self, left_rotation, right_rotation):
        """Small corneal reflections follow the eyes and sit behind the lids."""
        for shape, x, rotation in zip(self.shines, (-self.spacing, self.spacing),
                                      (left_rotation, right_rotation)):
            rx, ry = map(math.radians, rotation)
            shape.positionX(x - self.radius * (0.22 + 0.70 * math.sin(ry)))
            shape.positionY(self.radius * (0.24 + 0.70 * math.sin(rx)))
            shape.draw()

    def draw_nose(self):
        level = self.glow.level()
        if level > 0:
            self.halo.set_alpha(level)
            self.halo.draw()
        self.nose.draw()
        if level > 0:
            self.lit.set_alpha(level)
            self.lit.draw()
