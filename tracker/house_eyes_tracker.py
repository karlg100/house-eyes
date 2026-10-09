#!/usr/bin/env python3
"""house-eyes people tracker.

Reads a camera, finds people, follows each of them with a stable ID, decides
who each of the three eyes should watch, and sends tri-eyes.py the gaze
points over UDP several times a second (see people.py for the behaviour).
The eyes go back to wandering on their own when the messages stop.

    camera -> detector (NCS2 or motion) -> people.py (tracking, attention,
    calibration) -> UDP

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

from people import Attention, Calibration, PeopleTracker, gaze_message

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
    "tracking": {
        "lost_after": "1.0",    # seconds unseen before a person is forgotten
        "confirm_hits": "2",    # detections before a new person counts
        "smooth": "0.5",        # 0..1, weight given to each new detection
        "lead": "0.15",         # seconds; look ahead along the walking direction
    },
    "attention": {
        "split": "yes",         # yes: with 2-3+ people each eye picks its own person
        "dwell_min": "3.0",     # seconds an eye stays on a person before it may move on
        "dwell_max": "7.0",
        "newcomer_bonus": "1.0",  # how strongly new arrivals attract attention
        "still_bonus": "0.8",   # ... and people who stop to look
        "crowd_enter": "7",     # this many people or more -> crowd mode
        "crowd_exit": "5",      # back to normal at this many or fewer
        "glance_min": "0.5",    # crowd mode: seconds between darting glances
        "glance_max": "1.5",
        "crowd_pupil": "0.95",  # crowd mode pupil size (0 small .. 1 wide)
        "close_height": "0.45", # someone this tall in frame is "close" (0 = off)
        "close_pupil": "0.85",  # ... and the pupils widen to this
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
                        b"<p style='padding:8px'>Dots under a person show which eye watches "
                        b"them: red = screen-left eye, green = centre, blue = screen-right. "
                        b"White boxes: watched; orange: not watched. Blue frame: region of "
                        b"interest. Top bar: where each eye is told to look (same colours).</p>"
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

    EYE_COLOURS = ((60, 60, 255), (60, 255, 60), (255, 120, 60))   # L, C, R (BGR)

    def show(self, frame, people, mode, eyes, pupil, roi, t):
        self.next = t + self.interval
        img = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
        h, w = img.shape[:2]
        cv2.rectangle(img, (int(roi[0] * w), int(roi[1] * h)),
                      (int(roi[2] * w) - 1, int(roi[3] * h) - 1), (255, 128, 0), 1)
        watched = {}
        for i, (p, _) in enumerate(eyes or []):
            watched.setdefault(p.id, []).append(i)
        for p in people:
            b = p.box
            cv2.rectangle(img, (int(b[0] * w), int(b[1] * h)), (int(b[2] * w), int(b[3] * h)),
                          (255, 255, 255) if p.id in watched else (0, 200, 255), 1)
            cv2.putText(img, "%d x=%.2f" % (p.id, p.cx), (int(b[0] * w) + 2, int(b[1] * h) + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            for k, i in enumerate(watched.get(p.id, [])):
                cv2.circle(img, (int(p.cx * w) - 8 + 8 * k, int(p.feet * h)), 5,
                           self.EYE_COLOURS[i], -1)
        cv2.rectangle(img, (0, 0), (w, 16), (40, 40, 40), -1)
        for i, (_, g) in enumerate(eyes or []):
            gx = int((g[0] + 1) / 2 * w)
            cv2.rectangle(img, (gx - 3, 2 + 4 * i), (gx + 3, 6 + 4 * i), self.EYE_COLOURS[i], -1)
        cv2.putText(img, "%s  people=%d%s" % (mode, len(people),
                                               "  pupil=%.2f" % pupil if pupil is not None else ""),
                    (6, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
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
    trk, att, cal = cfg["tracking"], cfg["attention"], cfg["calibration"]
    tracker = PeopleTracker(lost_after=float(trk["lost_after"]),
                            confirm_hits=int(trk["confirm_hits"]),
                            smooth=float(trk["smooth"]),
                            min_height=float(cfg["detector"]["min_height"]), roi=roi)
    attention = Attention(dwell_min=float(att["dwell_min"]), dwell_max=float(att["dwell_max"]),
                          newcomer_bonus=float(att["newcomer_bonus"]),
                          still_bonus=float(att["still_bonus"]), split=cfg_bool(att["split"]),
                          crowd_enter=int(att["crowd_enter"]), crowd_exit=int(att["crowd_exit"]),
                          glance_min=float(att["glance_min"]), glance_max=float(att["glance_max"]),
                          crowd_pupil=float(att["crowd_pupil"]),
                          close_height=float(att["close_height"]),
                          close_pupil=float(att["close_pupil"]), lead=float(trk["lead"]))
    calibration = Calibration(x_left=float(cal["x_left"]), x_right=float(cal["x_right"]),
                              flip_x=cfg_bool(cal["flip_x"]), y_at_top=float(cal["y_at_top"]),
                              y_at_bottom=float(cal["y_at_bottom"]))
    pport = int(cfg["preview"]["port"])
    preview = Preview(pport, float(cfg["preview"]["fps"])) if pport else None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (cfg["output"]["host"], int(cfg["output"]["port"]))
    send_every = 1.0 / float(cfg["output"]["rate"])
    next_send = 0.0
    seq, frames, dets, last_stats = 0, 0, 0, time.time()
    mode, eyes, pupil, last_mode = "idle", None, None, "idle"
    mode_secs, peak = {}, 0

    while True:
        frame, seq, stamp = source.latest(seq)
        now = time.time()
        if frame is not None:
            frames += 1
            for t, boxes in detector.submit(frame, stamp):
                dets += 1
                tracker.update(boxes, t)
        people = tracker.confirmed()
        peak = max(peak, len(people))
        prev_t = getattr(attention, "last_t", None) or now
        mode, eyes, pupil = attention.update(people, calibration, now)
        mode_secs[mode] = mode_secs.get(mode, 0.0) + max(0.0, now - prev_t)
        if mode != last_mode:
            log.info("mode: %s -> %s (%d people)", last_mode, mode, len(people))
            last_mode = mode
        if eyes and now >= next_send:
            next_send = now + send_every
            if not args.no_send:
                sock.sendto(gaze_message(eyes, pupil).encode(), dest)
        if preview and frame is not None and preview.wanted(now):
            preview.show(frame, people, mode, eyes, pupil, roi, now)
        if now - last_stats >= args.stats:
            el = now - last_stats
            log.info("stats: camera %.1f fps, detector %.1f fps, people now %d (peak %d), %s",
                     frames / el, dets / el, len(people), peak,
                     ", ".join("%s %.0f%%" % (m, 100 * v / el) for m, v in sorted(mode_secs.items())))
            frames, dets, last_stats, peak, mode_secs = 0, 0, now, 0, {}


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
