"""Link to the front-lawn show controller (the "haunt" director) over MQTT.

Optional: with no [show] host in tracker.ini, or without paho-mqtt installed,
the tracker runs on its own exactly as before (tracking always on).

    <prefix>/eyes/tracking/set   in, retained, from the director: 1 = follow
                                 people, 0 = don't (the eyes wander on their own)
    <prefix>/eyes/online         out, retained: 1, and 0 as the last will
    <prefix>/eyes/status         out, retained JSON every few seconds and on change:
                                 {"tracking", "people", "mode", "camera_fps",
                                  "detector_fps", "host", "ts"}

The broker password comes from HAUNT_MQTT_PASSWORD (EnvironmentFile
/etc/house-eyes/env) or from password_file.
"""

import json
import logging
import os
import socket
import threading
import time

log = logging.getLogger("showlink")

SHOW_DEFAULTS = {
    "host": "",                 # MQTT broker of the show controller; empty = no link
    "port": "1883",
    "username": "",
    "password_file": "",        # or HAUNT_MQTT_PASSWORD in /etc/house-eyes/env
    "prefix": "haunt",
    "status_every": "2",        # seconds between status messages
}


def read_password(section):
    pw = os.environ.get("HAUNT_MQTT_PASSWORD")
    if pw:
        return pw
    path = (section.get("password_file") or "").strip()
    if path:
        try:
            with open(path) as fh:
                return fh.read().strip() or None
        except OSError as exc:
            log.warning("cannot read %s: %s", path, exc)
    return None


def parse_switch(payload):
    """'1'/'on'/'true' -> True, '0'/'off'/'false' -> False, anything else -> None."""
    word = payload.strip().lower()
    if word in ("1", "on", "true", "yes"):
        return True
    if word in ("0", "off", "false", "no"):
        return False
    return None


class ShowLink:
    """Tracking switch in, status out. Thread-safe: paho calls back on its own thread."""

    def __init__(self, section, client_factory=None, clock=time.time):
        self.prefix = (section.get("prefix") or "haunt").strip()
        self.host = (section.get("host") or "").strip()
        self.status_every = float(section.get("status_every") or 2)
        self.clock = clock
        self.tracking = True          # until the director says otherwise
        self.connected = False
        self._last_status = None
        self._next_status = 0.0
        self._lock = threading.Lock()
        self.client = None
        self.t_set = "%s/eyes/tracking/set" % self.prefix
        self.t_online = "%s/eyes/online" % self.prefix
        self.t_status = "%s/eyes/status" % self.prefix
        if not self.host:
            log.info("no [show] host: running on our own (tracking always on)")
            return
        if client_factory is None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                log.warning("paho-mqtt not installed: no link to the show controller "
                            "(sudo apt install python3-paho-mqtt)")
                return
            client_factory = lambda cid: _paho_client(mqtt, cid)
        c = client_factory("house-eyes-%s" % socket.gethostname())
        user = (section.get("username") or "").strip()
        if user:
            c.username_pw_set(user, read_password(section))
        c.will_set(self.t_online, "0", qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(1, 30)
        try:
            c.connect_async(self.host, int(section.get("port") or 1883), keepalive=30)
        except (OSError, ValueError) as exc:
            log.warning("show link: %s (will retry)", exc)
        c.loop_start()
        self.client = c
        log.info("show link: %s:%s, prefix %s", self.host, section.get("port"), self.prefix)

    # paho callbacks (accept both the 1.x and 2.x signatures)
    def _on_connect(self, client, userdata, flags, rc, *rest):
        if getattr(rc, "is_failure", False) or (isinstance(rc, int) and rc != 0):
            log.warning("show link: broker refused the connection (%s)", rc)
            return
        self.connected = True
        client.subscribe(self.t_set, qos=1)
        client.publish(self.t_online, "1", qos=1, retain=True)
        with self._lock:
            self._last_status = None          # send the status again at once
            self._next_status = 0.0
        log.info("show link: connected")

    def _on_disconnect(self, client, userdata, *rest):
        if self.connected:
            log.warning("show link: lost the broker (retrying)")
        self.connected = False

    def _on_message(self, client, userdata, msg):
        if msg.topic != self.t_set:
            return
        self.handle_switch(msg.payload.decode("utf-8", "replace"))

    def handle_switch(self, payload):
        on = parse_switch(payload)
        if on is None:
            log.warning("show link: ignoring tracking switch %r", payload[:40])
            return
        if on != self.tracking:
            log.info("tracking %s (from the show controller)", "ON" if on else "OFF: the eyes wander")
        with self._lock:
            self.tracking = on
            self._next_status = 0.0

    def status(self, people, mode, camera_fps, detector_fps):
        """Call every loop; publishes when something changed or every status_every s."""
        if self.client is None or not self.connected:
            return
        body = {"tracking": self.tracking, "people": int(people), "mode": mode,
                "camera_fps": round(camera_fps, 1), "detector_fps": round(detector_fps, 1)}
        now = self.clock()
        key = (body["tracking"], body["people"], body["mode"])
        with self._lock:
            if key == self._last_status and now < self._next_status:
                return
            self._last_status = key
            self._next_status = now + self.status_every
        body.update(host=socket.gethostname(), ts=round(now, 1))
        self.client.publish(self.t_status, json.dumps(body, separators=(",", ":")), qos=0, retain=True)

    def close(self):
        if self.client is None:
            return
        try:
            self.client.publish(self.t_online, "0", qos=1, retain=True)
            time.sleep(0.2)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:      # noqa: BLE001 - on the way out
            pass


def _paho_client(mqtt, client_id):
    try:                                   # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except AttributeError:                 # 1.x (Debian bullseye's python3-paho-mqtt)
        return mqtt.Client(client_id=client_id)
