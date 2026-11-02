"""Renderer integration checks using the offline geometry recorder.

Requires Pillow, NumPy and svg.path; never imports Pi GPIO or starts a GPU.
"""
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eyes"))
from preview_christmas import draw_scene, load_scene
from seasonal import lid_weights


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.christmas = load_scene()
        cls.halloween = load_scene("halloween")

    def test_christmas_draws_two_eyes_and_only_a_nose_in_center(self):
        scene = self.christmas
        drawn = draw_scene(scene)
        for name in ("centerEye", "centerIris", "centerUpperEyelid", "centerLowerEyelid"):
            self.assertNotIn(scene[name], drawn)
        for name in ("leftEye", "rightEye", "leftIris", "rightIris"):
            self.assertIn(scene[name], drawn)
        decor = scene["decor"]
        self.assertIn(decor.nose, drawn)
        self.assertIn(decor.lit, drawn)
        self.assertIn(decor.halo, drawn)
        self.assertLess(drawn.index(decor.halo), drawn.index(decor.nose))
        self.assertLess(drawn.index(decor.nose), drawn.index(decor.lit))

    def test_halloween_keeps_three_eyes_and_original_assets(self):
        scene = self.halloween
        drawn = draw_scene(scene)
        for name in ("centerEye", "centerIris", "centerUpperEyelid", "centerLowerEyelid"):
            self.assertIn(scene[name], drawn)
        self.assertIsNone(scene["decor"])
        self.assertEqual(scene["irisMap"].name, "graphics/dragon-iris.jpg")
        self.assertEqual(scene["scleraMap"].name, "graphics/dragon-sclera.png")
        self.assertEqual(scene["lidMap"].name, "graphics/lid.png")

    def test_pupils_are_horizontal_and_geometry_stays_finite(self):
        scene = self.christmas
        for name in ("pupilMinPts", "pupilMaxPts"):
            points = np.asarray(scene[name])
            self.assertGreater(np.ptp(points[:,0]), 1.9*np.ptp(points[:,1]))
        for pupil in (0, 0.5, 1):
            for shape in draw_scene(scene, pupil):
                self.assertTrue(np.isfinite(shape.buf[0].array_buffer).all())
        # Matching closed curves prevent an open slit during a blink.
        np.testing.assert_allclose(scene["upperLidClosedPts"],
                                   list(reversed(scene["lowerLidClosedPts"])), atol=1e-6)

    def test_full_blinks_and_halloween_lid_behavior(self):
        for tracking in (0, 0.4, 1):
            self.assertEqual(lid_weights(tracking, 1, True), (1,1))
            for blink in (0, 0.5, 1):
                upper,lower = lid_weights(tracking, blink)
                self.assertAlmostEqual(upper, tracking+blink*(1-tracking))
                self.assertAlmostEqual(lower, 1-tracking+blink*tracking)

    def test_projection_options_and_off_mode_keep_nose_visible(self):
        scene = load_scene(extra=["--nose-mode", "off", "--nose-y", "-32",
                                  "--nose-scale", "0.65", "--no-antlers"])
        drawn = draw_scene(scene)
        decor = scene["decor"]
        self.assertEqual(decor.accents, [])
        self.assertEqual(decor.nose.xyz[1], -32)
        self.assertIn(decor.nose, drawn)
        self.assertNotIn(decor.halo, drawn)
        self.assertNotIn(decor.lit, drawn)

    def test_tracker_outer_targets_survive_center_replacement(self):
        scene = load_scene()
        scene["gazeInput"] = types.SimpleNamespace(
            get=lambda now: ([(0.8,0.1),(-1,-1),(-0.8,0.2)], True, 0.9))
        scene["lastFrameTime"] -= 1
        draw_scene(scene)
        self.assertLess(scene["rightIris"].ry, 0)  # screen-left follows first pair
        self.assertGreater(scene["leftIris"].ry, 0)  # screen-right follows last pair
        self.assertEqual(scene["decor"].nose.rx, 0)
        self.assertEqual(scene["decor"].nose.ry, 0)

    def test_udp_nose_commands_do_not_refresh_gaze(self):
        scene = load_scene()
        # Drive the actual receiver loop with datagrams; SystemExit ends it
        # without leaving a daemon thread or a live UDP port in the test.
        receiver = scene["GazeInput"].__new__(scene["GazeInput"])
        receiver.lock = threading.Lock()
        receiver.target, receiver.stamp = None, 0
        receiver.sock = Mock()
        receiver.sock.recv.side_effect = [b"0.8 0 p=0.7", SystemExit]
        with self.assertRaises(SystemExit):
            receiver.run()
        stamp, target = receiver.stamp, receiver.target
        receiver.sock.recv.side_effect = [b"nose off", b"nose pulse nan", SystemExit]
        with self.assertRaises(SystemExit):
            receiver.run()
        self.assertEqual(receiver.stamp, stamp)
        self.assertEqual(receiver.target, target)
        self.assertEqual(scene["noseGlow"].mode, "off")
        self.assertIsNone(receiver.get(stamp+3))
        receiver.sock.recv.side_effect = [b"-1 0 0 0.5 1 0 p=1", b"nose pulse 4", SystemExit]
        with self.assertRaises(SystemExit):
            receiver.run()
        self.assertEqual(receiver.target, ([(-1,0),(0,0.5),(1,0)], True, 1))
        self.assertIsNotNone(scene["noseGlow"].start)


if __name__ == "__main__":
    unittest.main()
