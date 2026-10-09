#!/usr/bin/env python3
"""house-eyes people tracker.

Reads a camera, finds people, picks one to watch, and sends the eyes a gaze
point over UDP ("x y", each -1..1) several times a second. tri-eyes.py eases
toward that point and goes back to wandering when the messages stop.

    camera -> detector (NCS2 or motion) -> target picker -> calibration -> UDP

Run by systemd as house-eyes-tracker.service. For a live annotated view while
calibrating, open http://eyes.local:8080/ in a browser.

Config: /etc/house-eyes/tracker.ini (see tracker.ini.example). Every option
can be overridden on the command line, e.g. --source file:/path/video.mp4
"""

import argparse
import configparser
import logging
import math
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

log = logging.getLogger("tracker")

DEFAULTS = {
    "camera": {
        # picamera2            CSI camera (Pi Camera Module)
        # usb:0                /dev/video0 via OpenCV
        # rtsp://...           network stream via OpenCV
        # file:/path/video.mp4 recorded video, looped (testing)
        "source": "picamera2",
        "width": "1280",
        "height": "720",
        "rotate": "0",          # 0, 90, 180, 270
        "hflip": "no",
    },
    "detector": {
        # myriad = person-detection network on the Neural Compute Stick 2
        # motion = background subtraction on the CPU (no stick needed)
        "type": "myriad",
        "model": "/opt/house-eyes/models/person-detection-retail-0013.xml",
        "confidence": "0.55",
        "min_height": "0.08",   # ignore people shorter than this fraction of the frame
        "requests": "2",        # parallel inferences on the stick
    },
    "target": {
        "lost_after": "0.8",    # seconds without a match before the target is dropped
        "switch_after": "8.0",  # seconds on one person before allowing a switch
        "gate": "0.25",         # max jump (fraction of frame width) to count as same person
        "smooth": "0.15",       # seconds; easing of the target position
        "lead": "0.15",         # seconds; look ahead along the walking direction
    },
    "calibration": {
        # Camera x (0 = left edge of frame, 1 = right edge) that should make
        # the eyes look full left / full right on screen.
        "x_left": "0.0",
        "x_right": "1.0",
        "flip_x": "no",         # yes if the eyes look the wrong way
        # Gaze y when the person's feet are at the top / bottom of the frame.
        "y_at_top": "-0.1",
        "y_at_bottom": "-0.7",
        # Optional: crop to a region of interest (fractions of the frame).
        "roi": "0,0,1,1",       # x0,y0,x1,y1
    },
    "output": {
        "host": "127.0.0.1",
        "port": "5005",
        "rate": "15",           # gaze messages per second while tracking
    },
    "preview": {
        "port": "8080",         # 0 disables the browser preview
        "fps": "5",
    },
}


def cfg_bool(v):
    return str(v).strip().lower() in ("1", "yes", "true", "on")


# --------------------------------------------------------------------------
# Camera sources. Each runs a thread that keeps only the newest frame, so the
# tracker never works on a stale picture.

class FrameSource(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.lock = threading.Condition()
        self.frame = None
        self.stamp = 0.0
        self.seq = 0
        self.running = True

    def publish(self, frame):
        rot = int(self.cfg["rotate"])
        if rot == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rot == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if cfg_bool(self.cfg["hflip"]):
            frame = cv2.flip(frame, 1)
        with self.lock:
            self.frame = frame
            self.stamp = time.time()
            self.seq += 1
            self.lock.notify_all()

    def latest(self, after_seq, timeout=1.0):
        with self.lock:
            if self.seq <= after_seq:
                self.lock.wait(timeout)
            if self.seq <= after_seq:
                return None, after_seq, 0.0
            return self.frame, self.seq, self.stamp

    def run(self):
        while self.running:
            try:
                self.capture_loop()
            except Exception as e:  # camera missing, stream dropped, ...
                log.warning("camera: %s; retrying in 5 s", e)
            time.sleep(5)


class PiCameraSource(FrameSource):
    def capture_loop(self):
        from picamera2 import Picamera2
        if not Picamera2.global_camera_info():
            raise RuntimeError("no CSI camera detected")
        cam = Picamera2()
        size = (int(self.cfg["width"]), int(self.cfg["height"]))
        cam.configure(cam.create_video_configuration(
            main={"size": size, "format": "RGB888"}, buffer_count=2))
        cam.start()
        log.info("camera: picamera2 %dx%d started", *size)
        try:
            while self.running:
                # RGB888 in picamera2 is BGR byte order, which is what OpenCV wants
                self.publish(cam.capture_array("main"))
        finally:
            cam.stop()
            cam.close()


class OpenCVSource(FrameSource):
    def capture_loop(self):
        src = self.cfg["source"]
        is_file = src.startswith("file:")
        if src.startswith("usb:"):
            cap = cv2.VideoCapture(int(src[4:]), cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.cfg["width"]))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.cfg["height"]))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        elif is_file:
            cap = cv2.VideoCapture(src[5:])
        else:
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError("cannot open %s" % src)
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        log.info("camera: %s opened (%dx%d @ %.0f fps)", src,
                 cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT), fps)
        try:
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    if is_file:  # loop test videos
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    raise RuntimeError("stream ended")
                self.publish(frame)
                if is_file:
                    time.sleep(1.0 / fps)  # play files at real speed
        finally:
            cap.release()


def make_source(cfg):
    if cfg["source"] == "picamera2":
        return PiCameraSource(cfg)
    return OpenCVSource(cfg)


# --------------------------------------------------------------------------
# Detectors. detect(frame) returns a list of (x0, y0, x1, y1, score) with
# coordinates as fractions of the frame.

class MyriadDetector:
    """person-detection-retail-0013 on the Intel Neural Compute Stick 2."""

    def __init__(self, cfg):
        from openvino.runtime import AsyncInferQueue, Core, Layout, Type
        from openvino.preprocess import PrePostProcessor
        self.conf = float(cfg["confidence"])
        # After a previous run exits, the stick reboots and re-enumerates on USB,
        # which takes a few seconds. Wait for it rather than failing.
        deadline = time.time() + 60
        while True:
            core = Core()
            if "MYRIAD" in core.available_devices:
                break
            if time.time() > deadline:
                raise RuntimeError("Neural Compute Stick not found (devices: %s)"
                                   % core.available_devices)
            log.info("detector: waiting for the Neural Compute Stick...")
            del core
            time.sleep(3)
        model = core.read_model(cfg["model"])
        _, _, self.h, self.w = model.input().shape
        ppp = PrePostProcessor(model)
        ppp.input().tensor().set_element_type(Type.u8).set_layout(Layout("NHWC"))
        ppp.input().model().set_layout(Layout("NCHW"))
        model = ppp.build()
        t = time.time()
        self.compiled = core.compile_model(model, "MYRIAD")
        log.info("detector: %s loaded on MYRIAD in %.1f s", os.path.basename(cfg["model"]),
                 time.time() - t)
        self.queue = AsyncInferQueue(self.compiled, int(cfg["requests"]))
        self.queue.set_callback(self._done)
        self.results = []
        self.res_lock = threading.Lock()

    def _done(self, request, userdata):
        out = request.get_output_tensor(0).data.reshape(-1, 7)
        boxes = [(float(r[3]), float(r[4]), float(r[5]), float(r[6]), float(r[2]))
                 for r in out if r[0] >= 0 and r[2] >= self.conf]
        with self.res_lock:
            self.results.append((userdata, boxes))

    def submit(self, frame, stamp):
        """Queue a frame; returns finished (stamp, boxes) results, oldest first.
        Blocks only when every request on the stick is busy, which paces the loop."""
        img = cv2.resize(frame, (self.w, self.h))
        self.queue.start_async({0: img[np.newaxis]}, stamp)
        with self.res_lock:
            done, self.results = self.results, []
        return sorted(done, key=lambda d: d[0])


class MotionDetector:
    """CPU fallback: blobs of movement. Follows anything that moves."""

    def __init__(self, cfg):
        self.min_h = float(cfg["min_height"])
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32,
                                                      detectShadows=False)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        log.info("detector: motion (CPU)")

    def submit(self, frame, stamp):
        small = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
        mask = self.bg.apply(cv2.GaussianBlur(small, (5, 5), 0))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.dilate(mask, self.kernel, iterations=2)
        h, w = mask.shape
        res = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = res[0] if len(res) == 2 else res[1]
        boxes = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bh / h >= self.min_h:
                boxes.append((x / w, y / h, (x + bw) / w, (y + bh) / h, 1.0))
        return [(stamp, boxes)]


def make_detector(cfg):
    if cfg["type"] == "myriad":
        return MyriadDetector(cfg)
    if cfg["type"] == "motion":
        return MotionDetector(cfg)
    raise ValueError("unknown detector type %r" % cfg["type"])


# --------------------------------------------------------------------------
# Target selection: stick with one person, follow them smoothly, and look a
# little ahead along their direction of travel to hide camera/detector lag.

class TargetPicker:
    def __init__(self, cfg, det_cfg, roi):
        self.lost_after = float(cfg["lost_after"])
        self.switch_after = float(cfg["switch_after"])
        self.gate = float(cfg["gate"])
        self.smooth = float(cfg["smooth"])
        self.lead = float(cfg["lead"])
        self.min_h = float(det_cfg["min_height"])
        self.roi = roi
        self.pos = None      # smoothed (x, y_feet)
        self.vel = (0.0, 0.0)
        self.seen = 0.0      # last time the target was matched
        self.since = 0.0     # when we started following this target
        self.last_t = 0.0

    def update(self, boxes, t):
        x0, y0, x1, y1 = self.roi
        people = []
        for b in boxes:
            cx, feet, height = (b[0] + b[2]) / 2, b[3], b[3] - b[1]
            if height >= self.min_h and x0 <= cx <= x1 and y0 <= feet <= y1:
                people.append((cx, feet, height))
        if self.pos is not None and t - self.seen > self.lost_after:
            log.info("target lost")
            self.pos = None
        if not people:
            return
        if self.pos is None:
            pick = max(people, key=lambda p: p[2])  # nearest = tallest
            self.pos, self.vel, self.since = (pick[0], pick[1]), (0.0, 0.0), t
            self.seen = self.last_t = t
            log.info("target acquired at x=%.2f (%d people in view)", pick[0], len(people))
            return
        near = min(people, key=lambda p: abs(p[0] - self.pos[0]))
        if abs(near[0] - self.pos[0]) > self.gate:
            if t - self.since < self.switch_after:
                return      # someone else, far away: keep watching ours for now
            self.pos, self.vel, self.since = (near[0], near[1]), (0.0, 0.0), t
            self.seen = self.last_t = t
            log.info("target switched to x=%.2f", near[0])
            return
        dt = max(t - self.last_t, 1e-3)
        k = 1.0 - math.exp(-dt / max(self.smooth, 1e-3))
        nx = self.pos[0] + (near[0] - self.pos[0]) * k
        ny = self.pos[1] + (near[1] - self.pos[1]) * k
        kv = 1.0 - math.exp(-dt / 0.5)
        self.vel = (self.vel[0] + ((nx - self.pos[0]) / dt - self.vel[0]) * kv,
                    self.vel[1] + ((ny - self.pos[1]) / dt - self.vel[1]) * kv)
        self.pos, self.seen, self.last_t = (nx, ny), t, t

    def aim(self):
        if self.pos is None:
            return None
        return (self.pos[0] + self.vel[0] * self.lead,
                self.pos[1] + self.vel[1] * self.lead)


def to_gaze(aim, cal):
    x, feet = aim
    span = float(cal["x_right"]) - float(cal["x_left"])
    gx = -1.0 + 2.0 * (x - float(cal["x_left"])) / (span if abs(span) > 1e-6 else 1.0)
    if cfg_bool(cal["flip_x"]):
        gx = -gx
    top, bottom = float(cal["y_at_top"]), float(cal["y_at_bottom"])
    gy = top + (bottom - top) * min(max(feet, 0.0), 1.0)
    return max(-1.0, min(1.0, gx)), max(-1.0, min(1.0, gy))


# --------------------------------------------------------------------------
# Browser preview for calibration: http://<pi>:8080/

class Preview:
    def __init__(self, port, fps):
        self.jpeg = None
        self.lock = threading.Lock()
        self.interval = 1.0 / max(fps, 0.5)
        self.next = 0.0
        preview = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/frame.jpg"):
                    with preview.lock:
                        data = preview.jpeg
                    if data is None:
                        self.send_error(503, "no frame yet")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                body = (b"<!doctype html><title>house-eyes tracker</title>"
                        b"<body style='margin:0;background:#111;color:#ccc;font:14px sans-serif'>"
                        b"<img id=f style='width:100%' src='/frame.jpg'>"
                        b"<p style='padding:8px'>Green box: person being watched. "
                        b"Yellow: other people. Blue frame: region of interest. "
                        b"Top bar: where the eyes are told to look.</p>"
                        b"<script>setInterval(()=>{f.src='/frame.jpg?'+Date.now()},250)</script>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log.info("preview: http://%s:%d/", socket.gethostname(), port)

    def wanted(self, t):
        return t >= self.next

    def show(self, frame, boxes, picker, gaze, roi, t):
        self.next = t + self.interval
        img = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
        h, w = img.shape[:2]
        cv2.rectangle(img, (int(roi[0] * w), int(roi[1] * h)),
                      (int(roi[2] * w) - 1, int(roi[3] * h) - 1), (255, 128, 0), 1)
        aim = picker.aim()
        for b in boxes:
            cx = (b[0] + b[2]) / 2
            mine = picker.pos is not None and abs(cx - picker.pos[0]) < 0.05
            cv2.rectangle(img, (int(b[0] * w), int(b[1] * h)), (int(b[2] * w), int(b[3] * h)),
                          (0, 255, 0) if mine else (0, 220, 255), 2)
        if aim is not None:
            cv2.circle(img, (int(aim[0] * w), int(aim[1] * h)), 6, (0, 0, 255), -1)
        cv2.rectangle(img, (0, 0), (w, 14), (40, 40, 40), -1)
        if gaze is not None:
            gx = int((gaze[0] + 1) / 2 * w)
            cv2.rectangle(img, (gx - 4, 0), (gx + 4, 14), (0, 0, 255), -1)
            cv2.putText(img, "gaze %+.2f %+.2f" % gaze, (6, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1)
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self.lock:
                self.jpeg = enc.tobytes()


# --------------------------------------------------------------------------

def load_config(path, overrides):
    cp = configparser.ConfigParser()
    cp.read_dict(DEFAULTS)
    if path and os.path.exists(path):
        cp.read(path)
        log.info("config: %s", path)
    for section, key, value in overrides:
        if value is not None:
            cp[section][key] = str(value)
    return cp


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="/etc/house-eyes/tracker.ini")
    ap.add_argument("--source", help="camera source (see config)")
    ap.add_argument("--detector", choices=["myriad", "motion"])
    ap.add_argument("--host", help="where tri-eyes.py listens")
    ap.add_argument("--no-send", action="store_true", help="track but don't move the eyes")
    ap.add_argument("--preview-port", type=int)
    ap.add_argument("--stats", type=float, default=30.0, help="seconds between stats lines")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config, [
        ("camera", "source", args.source), ("detector", "type", args.detector),
        ("output", "host", args.host), ("preview", "port", args.preview_port)])
    roi = tuple(float(v) for v in cfg["calibration"]["roi"].split(","))

    source = make_source(cfg["camera"])
    source.start()
    detector = make_detector(cfg["detector"])
    picker = TargetPicker(cfg["target"], cfg["detector"], roi)
    pport = int(cfg["preview"]["port"])
    preview = Preview(pport, float(cfg["preview"]["fps"])) if pport else None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (cfg["output"]["host"], int(cfg["output"]["port"]))
    send_every = 1.0 / float(cfg["output"]["rate"])
    next_send = 0.0
    seq, frames, dets, last_stats = 0, 0, 0, time.time()
    last_boxes, gaze = [], None

    while True:
        frame, seq, stamp = source.latest(seq)
        now = time.time()
        if frame is not None:
            frames += 1
            for t, boxes in detector.submit(frame, stamp):
                dets += 1
                last_boxes = boxes
                picker.update(boxes, t)
        aim = picker.aim()
        gaze = to_gaze(aim, cfg["calibration"]) if aim is not None else None
        if gaze is not None and now >= next_send:
            next_send = now + send_every
            if not args.no_send:
                sock.sendto(("%.3f %.3f" % gaze).encode(), dest)
        if preview and frame is not None and preview.wanted(now):
            preview.show(frame, last_boxes, picker, gaze, roi, now)
        if now - last_stats >= args.stats:
            el = now - last_stats
            log.info("stats: camera %.1f fps, detector %.1f fps, target %s",
                     frames / el, dets / el,
                     "x=%.2f gaze=%+.2f" % (picker.pos[0], gaze[0]) if gaze else "none")
            frames, dets, last_stats = 0, 0, now


if __name__ == "__main__":
    code = 0
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("tracker failed")
        code = 1
    # The OpenVINO/XLink teardown can abort noisily on exit; skip it.
    logging.shutdown()
    os._exit(code)
