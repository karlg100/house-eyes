"""People tracking and attention for house-eyes. Pure Python, no camera or
OpenCV needed, so it can be simulated and tested anywhere (see sim_people.py).

PeopleTracker  turns per-frame detection boxes into people with stable IDs
               that survive crossings and brief occlusion.
Attention      decides where each of the three eyes looks:
                 0 people      -> nothing (the eyes wander on their own)
                 1 person      -> all three eyes watch them
                 2-3 people    -> the eyes split up, ordered left to right
                 4+ people     -> the eyes pick the most interesting three and
                                  move between people every few seconds
                 crowd         -> each eye darts between random people, pupils wide

Coordinates: boxes are fractions of the camera frame (0..1). Gaze points
are -1..1 in projector screen space, produced by the Calibration object.
"""

import math
import random


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class Person:
    __slots__ = ("id", "box", "vx", "vy", "hits", "first_seen", "last_seen",
                 "still_since", "watched", "last_update", "tag")

    def __init__(self, pid, box, t):
        self.id = pid
        self.box = list(box[:4])
        self.vx = self.vy = 0.0          # frame fractions per second (feet point)
        self.hits = 1
        self.first_seen = self.last_seen = self.last_update = t
        self.still_since = None
        self.watched = 0.0               # seconds of attention received (decays)
        self.tag = box[5] if len(box) > 5 else None   # test harness ground truth

    @property
    def cx(self):
        return (self.box[0] + self.box[2]) / 2

    @property
    def feet(self):
        return self.box[3]

    @property
    def height(self):
        return self.box[3] - self.box[1]

    def predicted_box(self, t):
        dt = min(t - self.last_update, 1.0)
        dx, dy = self.vx * dt, self.vy * dt
        b = self.box
        return (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)

    def aim(self, t, lead):
        """Where to look: the feet point, coasted to time t plus `lead` seconds."""
        dt = min(t - self.last_update, 1.0) + lead
        return (self.cx + self.vx * dt, self.feet + self.vy * dt)

    def speed(self):
        return math.hypot(self.vx, self.vy)


class PeopleTracker:
    def __init__(self, lost_after=1.0, confirm_hits=2, smooth=0.5, min_height=0.08,
                 roi=(0, 0, 1, 1), still_speed=0.04):
        self.lost_after = lost_after      # seconds unseen before a person is forgotten
        self.confirm_hits = confirm_hits  # detections needed before a person counts
        self.smooth = smooth              # 0..1, weight of the new detection
        self.min_height = min_height
        self.roi = roi
        self.still_speed = still_speed    # below this (frame widths/s) someone is "standing"
        self.people = {}
        self.next_id = 1

    def _wanted(self, b):
        cx, feet, h = (b[0] + b[2]) / 2, b[3], b[3] - b[1]
        x0, y0, x1, y1 = self.roi
        return h >= self.min_height and x0 <= cx <= x1 and y0 <= feet <= y1

    def update(self, boxes, t):
        dets = [b for b in boxes if self._wanted(b)]
        tracks = list(self.people.values())
        # Score every track/detection pair; greedily take the best matches.
        pairs = []
        for tr in tracks:
            pb = tr.predicted_box(t)
            pcx, pfeet, ph = (pb[0] + pb[2]) / 2, pb[3], max(pb[3] - pb[1], 1e-3)
            for j, d in enumerate(dets):
                iou = _iou(pb, d)
                dist = math.hypot((d[0] + d[2]) / 2 - pcx, d[3] - pfeet) / ph
                size = abs((d[3] - d[1]) - ph) / ph      # people at other depths differ in size
                if (iou > 0.1 or dist < 0.6) and size < 0.5:
                    pairs.append((iou - 0.5 * dist - 1.0 * size, tr, j))
        pairs.sort(key=lambda p: -p[0])
        used_t, used_d = set(), set()
        for _, tr, j in pairs:
            if tr.id in used_t or j in used_d:
                continue
            used_t.add(tr.id)
            used_d.add(j)
            self._absorb(tr, dets[j], t)
        for j, d in enumerate(dets):
            if j not in used_d:
                p = Person(self.next_id, d, t)
                self.people[p.id] = p
                self.next_id += 1
        for pid in [pid for pid, p in self.people.items() if t - p.last_seen > self.lost_after]:
            del self.people[pid]

    def _absorb(self, tr, d, t):
        dt = max(t - tr.last_update, 1e-3)
        a = self.smooth
        old_cx, old_feet = tr.cx, tr.feet
        tr.box = [tr.box[i] + (d[i] - tr.box[i]) * a for i in range(4)]
        kv = 1.0 - math.exp(-dt / 0.4)
        tr.vx += ((tr.cx - old_cx) / dt - tr.vx) * kv
        tr.vy += ((tr.feet - old_feet) / dt - tr.vy) * kv
        tr.hits += 1
        tr.last_seen = tr.last_update = t
        tr.tag = d[5] if len(d) > 5 else None
        if tr.speed() < self.still_speed:
            if tr.still_since is None:
                tr.still_since = t
        else:
            tr.still_since = None

    def confirmed(self):
        return [p for p in self.people.values() if p.hits >= self.confirm_hits]


class Calibration:
    def __init__(self, x_left=0.0, x_right=1.0, flip_x=False, y_at_top=-0.1, y_at_bottom=-0.7):
        self.x_left, self.x_right, self.flip_x = x_left, x_right, flip_x
        self.y_at_top, self.y_at_bottom = y_at_top, y_at_bottom

    def gaze(self, aim):
        x, feet = aim
        span = self.x_right - self.x_left
        gx = -1.0 + 2.0 * (x - self.x_left) / (span if abs(span) > 1e-6 else 1.0)
        if self.flip_x:
            gx = -gx
        gy = self.y_at_top + (self.y_at_bottom - self.y_at_top) * min(max(feet, 0.0), 1.0)
        return (max(-1.0, min(1.0, gx)), max(-1.0, min(1.0, gy)))


class Attention:
    """Chooses who each eye watches. Eyes are ordered screen-left, centre,
    screen-right; whoever is further left (in gaze space) gets a further-left
    eye, so the eyes never cross."""

    def __init__(self, dwell_min=3.0, dwell_max=7.0, newcomer_bonus=1.0, newcomer_time=3.0,
                 still_bonus=0.8, still_after=1.0, boredom=0.15, split=True,
                 crowd_enter=7, crowd_exit=5, glance_min=0.5, glance_max=1.5,
                 crowd_pupil=0.95, close_height=0.45, close_pupil=0.85, lead=0.15,
                 uncross_after=1.0,
                 rng=None):
        self.dwell_min, self.dwell_max = dwell_min, dwell_max
        self.newcomer_bonus, self.newcomer_time = newcomer_bonus, newcomer_time
        self.still_bonus, self.still_after = still_bonus, still_after
        self.boredom = boredom
        self.split = split
        self.crowd_enter, self.crowd_exit = crowd_enter, crowd_exit
        self.glance_min, self.glance_max = glance_min, glance_max
        self.crowd_pupil = crowd_pupil
        self.close_height, self.close_pupil = close_height, close_pupil
        self.lead = lead
        self.rng = rng or random.Random()
        self.mode = "idle"
        self.selected = {}        # person id -> dwell end time
        self.center_id = None     # who the centre eye watches when 2 are selected
        self.center_until = 0.0
        self.crowd_eyes = [None, None, None]   # [(person id, until)] per eye
        self.eye_ids = None       # person id per eye (screen-left, centre, right)
        self.crossed_since = None
        self.uncross_after = uncross_after
        self.last_t = None

    # -- scoring -----------------------------------------------------------
    def interest(self, p, t):
        s = p.height * 2.0                                   # nearer = bigger
        s += self.newcomer_bonus * math.exp(-(t - p.first_seen) / self.newcomer_time)
        if p.still_since is not None and t - p.still_since >= self.still_after:
            s += self.still_bonus                            # stopped to look at us
        s -= self.boredom * p.watched
        return s

    def _dwell(self, t):
        return t + self.rng.uniform(self.dwell_min, self.dwell_max)

    # -- main entry ----------------------------------------------------------
    def update(self, people, cal, t):
        """people: confirmed Person list. Returns (mode, eyes, pupil) where eyes
        is None (no target) or a list of 3 (person, (gx, gy)) in screen order."""
        dt = 0.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t
        alive = {p.id: p for p in people}
        for p in people:                                     # boredom fades
            p.watched *= math.exp(-dt / 20.0)
        n = len(people)
        prev = self.mode
        if n == 0:
            self.mode = "idle"
        elif self.mode == "crowd" and n > self.crowd_exit:
            self.mode = "crowd"
        elif n >= self.crowd_enter:
            self.mode = "crowd"
        elif n == 1 or not self.split:
            self.mode = "single"
        else:
            self.mode = "split"
        if self.mode != prev:
            self.selected.clear()
            self.center_id = None
            self.crowd_eyes = [None, None, None]
            self.eye_ids = None
        if self.mode == "idle":
            return self.mode, None, None
        if self.mode == "crowd":
            return self.mode, self._crowd(alive, cal, t), self.crowd_pupil
        eyes = self._watch(alive, cal, t)
        for person, _ in eyes:
            person.watched += dt / 3.0                       # 3 eyes share the time
        near = max(p.height for p in people)
        pupil = self.close_pupil if self.close_height and near >= self.close_height else None
        return self.mode, eyes, pupil

    def _watch(self, alive, cal, t):
        slots = 1 if self.mode == "single" else min(3, len(alive))
        for pid in [pid for pid in self.selected if pid not in alive]:
            del self.selected[pid]
        # Replace people whose dwell ran out, if someone more interesting is waiting.
        for pid, until in list(self.selected.items()):
            if t < until:
                continue
            waiting = [p for p in alive.values() if p.id not in self.selected]
            if waiting:
                best = max(waiting, key=lambda p: self.interest(p, t))
                if self.interest(best, t) > self.interest(alive[pid], t) - 0.3 or len(self.selected) > slots:
                    del self.selected[pid]
                    self.selected[best.id] = self._dwell(t)
                    continue
            self.selected[pid] = self._dwell(t)
        while len(self.selected) > slots:                   # mode shrank
            worst = min(self.selected, key=lambda pid: self.interest(alive[pid], t))
            del self.selected[worst]
        while len(self.selected) < slots:
            waiting = [p for p in alive.values() if p.id not in self.selected]
            if not waiting:
                break
            best = max(waiting, key=lambda p: self.interest(p, t))
            self.selected[best.id] = self._dwell(t)
        chosen = [alive[pid] for pid in self.selected]
        pts = {p.id: cal.gaze(p.aim(t, self.lead)) for p in chosen}
        chosen.sort(key=lambda p: pts[p.id][0])
        if len(chosen) == 1:
            ids = [chosen[0].id] * 3
        elif len(chosen) == 2:
            if self.center_id not in self.selected or t >= self.center_until:
                options = [p for p in chosen if p.id != self.center_id] or chosen
                self.center_id = max(options, key=lambda p: self.interest(p, t)).id
                self.center_until = self._dwell(t)
            ids = [chosen[0].id, self.center_id, chosen[1].id]
        else:
            ids = [p.id for p in chosen]
        ids = self._sticky(ids, pts, t)
        return [(alive[pid], pts[pid]) for pid in ids]

    def _sticky(self, ids, pts, t):
        """`ids` is the left-to-right assignment. When the same people are
        being watched as last time, keep each eye on its person even if they
        walk past each other; only if the eyes stay crossed for more than
        `uncross_after` seconds are they re-sorted."""
        prev = self.eye_ids
        if prev is not None and sorted(prev) == sorted(ids):
            xs = [pts[pid][0] for pid in prev]
            if xs[0] <= xs[1] <= xs[2]:
                self.crossed_since = None
                ids = prev
            else:
                if self.crossed_since is None:
                    self.crossed_since = t
                if t - self.crossed_since <= self.uncross_after:
                    ids = prev
                else:
                    self.crossed_since = None
        elif prev is not None:
            # Someone new is being watched: move only the eyes that must move,
            # if that doesn't leave the eyes crossed.
            remaining = list(ids)
            keep = [None, None, None]
            for i, pid in enumerate(prev):
                if pid in remaining:
                    keep[i] = pid
                    remaining.remove(pid)
            remaining.sort(key=lambda pid: pts[pid][0])
            for i in range(3):
                if keep[i] is None:
                    keep[i] = remaining.pop(0)
            xs = [pts[pid][0] for pid in keep]
            if xs[0] <= xs[1] <= xs[2]:
                ids = keep
            self.crossed_since = None
        self.eye_ids = list(ids)
        return ids

    def _crowd(self, alive, cal, t):
        ids = list(alive)
        for i in range(3):
            cur = self.crowd_eyes[i]
            if cur is None or cur[0] not in alive or t >= cur[1]:
                self.crowd_eyes[i] = (self.rng.choice(ids),
                                      t + self.rng.uniform(self.glance_min, self.glance_max))
        eyes = []
        for pid, _ in self.crowd_eyes:
            p = alive[pid]
            eyes.append((p, cal.gaze(p.aim(t, self.lead))))
        # Keep the eyes from crossing: sort the chosen points left to right.
        eyes.sort(key=lambda e: e[1][0])
        return eyes


def gaze_message(eyes, pupil):
    """UDP payload for tri-eyes.py."""
    pts = [g for _, g in eyes]
    if pts[0] == pts[1] == pts[2]:
        msg = "%.3f %.3f" % pts[0]
    else:
        msg = " ".join("%.3f %.3f" % g for g in pts)
    if pupil is not None:
        msg += " p=%.2f" % pupil
    return msg
