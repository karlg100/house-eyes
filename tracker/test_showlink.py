"""Tests for the show-controller link (no broker needed):  python3 -m pytest tracker/"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from showlink import SHOW_DEFAULTS, ShowLink, parse_switch, read_password  # noqa: E402


class FakeClient:
    def __init__(self, cid):
        self.cid, self.pub, self.subs, self.will, self.user = cid, [], [], None, None
        self.on_connect = self.on_disconnect = self.on_message = None

    def username_pw_set(self, u, p): self.user = (u, p)
    def will_set(self, t, p, qos=0, retain=False): self.will = (t, p, retain)
    def reconnect_delay_set(self, a, b): pass
    def connect_async(self, host, port, keepalive=60): self.addr = (host, port)
    def loop_start(self): pass
    def loop_stop(self): pass
    def disconnect(self): pass
    def subscribe(self, t, qos=0): self.subs.append(t)
    def publish(self, t, p, qos=0, retain=False): self.pub.append((t, p, retain))


class Msg:
    def __init__(self, topic, payload): self.topic, self.payload = topic, payload.encode()


def make(**over):
    sec = dict(SHOW_DEFAULTS, host="broker", username="home-pi", **over)
    clock = [1000.0]
    link = ShowLink(sec, client_factory=FakeClient, clock=lambda: clock[0])
    return link, link.client, clock


def test_no_host_means_no_link_and_tracking_stays_on():
    link = ShowLink(dict(SHOW_DEFAULTS))
    assert link.client is None and link.tracking is True
    link.status(3, "single", 10, 10)          # harmless


def test_connect_announces_online_and_listens_for_the_switch(monkeypatch):
    monkeypatch.setenv("HAUNT_MQTT_PASSWORD", "pw")
    link, c, clock = make()
    assert c.will == ("haunt/eyes/online", "0", True) and c.user == ("home-pi", "pw")
    c.on_connect(c, None, {}, 0)
    assert c.subs == ["haunt/eyes/tracking/set"] and ("haunt/eyes/online", "1", True) in c.pub


def test_switch_turns_tracking_off_and_on_and_ignores_junk():
    link, c, clock = make()
    c.on_connect(c, None, {}, 0)
    c.on_message(c, None, Msg("haunt/eyes/tracking/set", "0"))
    assert link.tracking is False
    c.on_message(c, None, Msg("haunt/eyes/tracking/set", "banana"))
    assert link.tracking is False
    c.on_message(c, None, Msg("haunt/eyes/tracking/set", "1"))
    assert link.tracking is True
    assert parse_switch(" ON ") is True and parse_switch("off") is False


def test_status_on_change_and_every_few_seconds_retained():
    link, c, clock = make()
    c.on_connect(c, None, {}, 0)
    link.status(0, "idle", 8.0, 7.5)
    link.status(0, "idle", 8.0, 7.5)          # nothing changed, too soon
    st = [json.loads(p) for t, p, r in c.pub if t == "haunt/eyes/status"]
    assert len(st) == 1 and st[0]["tracking"] is True and st[0]["people"] == 0
    link.status(2, "split", 8.0, 7.5)         # changed: at once
    clock[0] += 3
    link.status(2, "split", 8.0, 7.5)         # unchanged, but status_every passed
    link.handle_switch("0")
    link.status(2, "split", 8.0, 7.5)         # switch changed: at once
    st = [json.loads(p) for t, p, r in c.pub if t == "haunt/eyes/status"]
    assert [s["people"] for s in st] == [0, 2, 2, 2] and st[-1]["tracking"] is False
    assert all(r for t, p, r in c.pub if t == "haunt/eyes/status")


def test_nothing_published_while_disconnected():
    link, c, clock = make()
    link.status(1, "single", 1, 1)
    assert not [t for t, p, r in c.pub if t == "haunt/eyes/status"]


def test_password_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HAUNT_MQTT_PASSWORD", raising=False)
    f = tmp_path / "pw"
    f.write_text("secret\n")
    assert read_password({"password_file": str(f)}) == "secret"
    assert read_password({"password_file": ""}) is None


def test_paho_2_style_refusal_is_not_treated_as_connected():
    link, c, clock = make()

    class RC:
        is_failure = True
    c.on_connect(c, None, {}, RC())
    assert link.connected is False and c.subs == []
