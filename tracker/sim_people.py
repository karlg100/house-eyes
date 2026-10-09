#!/usr/bin/env python3
"""Simulate pedestrians to exercise people.py without a camera.

    python3 sim_people.py            # run all scenarios, print a report

Each scenario generates walkers (and some who stop to look), turns them into
noisy detection boxes with dropouts, and runs PeopleTracker + Attention at
12 detections/s, like the NCS2. It reports mode changes, how often each eye
changes who it watches, ID swaps, and checks that the eyes never cross.
"""

import random
import sys

from people import Attention, Calibration, PeopleTracker, gaze_message

FPS = 12.0


class Walker:
    def __init__(self, rng, t0, x=None, speed=None, stop_at=None, stop_for=0.0, depth=None):
        self.rng = rng
        self.dir = rng.choice((-1, 1))
        self.x = x if x is not None else (-0.1 if self.dir > 0 else 1.1)
        self.speed = speed if speed is not None else rng.uniform(0.08, 0.16)  # frame widths/s
        self.depth = depth if depth is not None else rng.uniform(0.0, 1.0)      # 0 far .. 1 near
        self.stop_at, self.stop_for, self.stopped = stop_at, stop_for, None
        self.t0 = t0

    def step(self, t, dt):
        if self.stop_at is not None and self.stopped is None and abs(self.x - self.stop_at) < 0.02:
            self.stopped = t
        if self.stopped is not None and t - self.stopped < self.stop_for:
            return
        self.x += self.dir * self.speed * dt

    def box(self):
        h = 0.25 + 0.35 * self.depth
        feet = 0.55 + 0.4 * self.depth
        w = h * 0.4
        return (self.x - w / 2, feet - h, self.x + w / 2, feet)

    def visible(self):
        return 0.0 <= self.x <= 1.0


def run(name, walkers_fn, seconds, seed=1, verbose=False):
    rng = random.Random(seed)
    tracker = PeopleTracker(lost_after=1.0)
    att = Attention(rng=random.Random(seed + 1))
    cal = Calibration()
    walkers, t, dt = [], 0.0, 1.0 / FPS
    modes, eye_changes, last_ids = [], [0, 0, 0], [None, None, None]
    crossings = 0
    gt_by_track = {}
    id_swaps = 0
    msgs = 0
    mode_time, changes_by_mode = {}, {}
    while t < seconds:
        walkers_fn(rng, t, dt, walkers)
        for w in walkers:
            w.step(t, dt)
        walkers = [w for w in walkers if -0.2 <= w.x <= 1.2]
        boxes = []
        for i, w in enumerate(walkers):
            if w.visible() and rng.random() > 0.12:          # 12% missed detections
                b = w.box()
                j = [rng.gauss(0, 0.006) for _ in range(4)]
                boxes.append(tuple(b[k] + j[k] for k in range(4)) + (0.9,))
                boxes[-1] = boxes[-1] + (id(w),)
        tracker.update(boxes, t)
        # ID swap = a tracked person was matched to a different real walker
        for p in tracker.confirmed():
            if p.tag is not None and p.last_seen == t:
                if p.id in gt_by_track and gt_by_track[p.id] != p.tag:
                    id_swaps += 1
                gt_by_track[p.id] = p.tag
        mode, eyes, pupil = att.update(tracker.confirmed(), cal, t)
        mode_time[mode] = mode_time.get(mode, 0.0) + dt
        if not modes or modes[-1][1] != mode:
            modes.append((round(t, 1), mode, len(tracker.confirmed())))
        if eyes:
            msgs += 1
            xs = [g[0] for _, g in eyes]
            if not (xs[0] <= xs[1] + 1e-9 and xs[1] <= xs[2] + 1e-9):
                crossings += 1   # allowed briefly when watched people pass each other
            for i, (p, _) in enumerate(eyes):
                if last_ids[i] is not None and p.id != last_ids[i]:
                    eye_changes[i] += 1
                    changes_by_mode[mode] = changes_by_mode.get(mode, 0) + 1
                last_ids[i] = p.id
            if verbose and int(t * FPS) % int(FPS) == 0:
                print("  t=%5.1f %-6s n=%2d %s" % (t, mode, len(tracker.confirmed()),
                                                    gaze_message(eyes, pupil)))
        else:
            last_ids = [None, None, None]
        t += dt
    mins = seconds / 60.0
    print("== %s (%.0f s)" % (name, seconds))
    print("   modes: %s" % " -> ".join("%s@%s(n=%d)" % (m, ts, n) for ts, m, n in modes[:12]),
          "..." if len(modes) > 12 else "")
    print("   target changes per minute (left, centre, right eye): %s"
          % ", ".join("%.1f" % (c / mins) for c in eye_changes))
    print("   per mode: %s" % ", ".join("%s %.0fs %.1f changes/eye/min" % (m, mode_time[m], changes_by_mode.get(m, 0) / 3 / (mode_time[m] / 60)) for m in mode_time if m != "idle"))
    print("   ID swaps: %d   frames with eyes crossed: %d of %d"
          % (id_swaps, crossings, msgs))
    return 0


def single(rng, t, dt, ws):
    if not ws and t < 1:
        ws.append(Walker(rng, t, speed=0.1, depth=0.7))


def four_spread(rng, t, dt, ws):
    if t < dt:  # 4 people at different spots; two standing still to look
        ws.append(Walker(rng, t, x=0.05, speed=0.03, depth=0.4))
        ws.append(Walker(rng, t, x=0.35, speed=0.12, depth=0.8))
        ws.append(Walker(rng, t, x=0.7, speed=0.0, depth=0.6))
        ws.append(Walker(rng, t, x=0.95, speed=0.0, depth=0.3))


def crossing(rng, t, dt, ws):
    if t < dt:
        a = Walker(rng, t, x=0.1, speed=0.12, depth=0.6); a.dir = 1
        b = Walker(rng, t, x=0.9, speed=0.12, depth=0.62); b.dir = -1
        ws += [a, b]


def busy(rng, t, dt, ws):
    if rng.random() < dt * 0.35:          # a new walker every ~3 s
        ws.append(Walker(rng, t))


def crowd(rng, t, dt, ws):
    if t < dt:
        for _ in range(25):
            ws.append(Walker(rng, t, x=rng.uniform(0, 1), speed=rng.uniform(0.0, 0.1)))
    if rng.random() < dt * 2.0:
        ws.append(Walker(rng, t))


if __name__ == "__main__":
    v = "-v" in sys.argv
    bad = 0
    bad += run("1 person walking past", single, 15, verbose=v)
    bad += run("4 people spread out, 2 standing", four_spread, 40, verbose=v)
    bad += run("2 people crossing", crossing, 10, verbose=v)
    bad += run("busy sidewalk", busy, 180, verbose=v)
    bad += run("crowd of ~25", crowd, 60, verbose=v)
    sys.exit(1 if bad else 0)
