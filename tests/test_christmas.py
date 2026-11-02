"""Run from the repo root: python3 -m unittest discover -s tests -v."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eyes"))
from seasonal import NoseGlow, theme_options


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Midpoint:
    def uniform(self, low, high):
        return (low + high) / 2


class NoseTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.nose = NoseGlow(every=(10, 20), clock=self.clock, rng=Midpoint())

    def test_auto_waits_then_fades_and_reschedules(self):
        self.assertEqual(self.nose.level(), 0)
        self.clock.now = 14.9
        self.assertEqual(self.nose.level(), 0)
        self.clock.now = 15
        self.assertEqual(self.nose.level(), 0)
        self.clock.now = 15.4
        self.assertTrue(0 < self.nose.level() < 1)
        self.clock.now = 16.5
        self.assertEqual(self.nose.level(), 1)
        self.clock.now = 18.5
        self.assertTrue(0 < self.nose.level() < 1)
        self.clock.now = 19
        self.assertEqual(self.nose.level(), 0)
        self.assertEqual(self.nose.next_pulse, 34)

    def test_on_and_off_override_active_pulse(self):
        self.assertTrue(self.nose.command("nose on"))
        self.clock.now = 500
        self.assertEqual(self.nose.level(), 1)
        self.nose.command("nose pulse")
        self.nose.command("nose off")
        self.assertEqual(self.nose.level(), 0)
        self.clock.now = 900
        self.assertEqual(self.nose.level(), 0)

    def test_timed_pulse_returns_to_previous_mode(self):
        for mode in ("off", "on", "auto"):
            with self.subTest(mode=mode):
                self.clock.now = 0
                self.nose.command("nose " + mode)
                self.assertTrue(self.nose.command("nose pulse 4"))
                self.clock.now = 1
                self.assertEqual(self.nose.level(), 1)
                self.clock.now = 4.1
                self.assertEqual(self.nose.level(), 1 if mode == "on" else 0)
                self.assertEqual(self.nose.mode, mode)

    def test_malformed_commands_do_not_change_state(self):
        self.nose.command("nose on")
        for message in ("", "0 0", "nose", "nose pulse nan", "nose pulse inf",
                        "nose pulse -1", "nose pulse 0", "nose pulse 31",
                        "nose pulse wat", "nose pulse 2 junk", "nose on 4",
                        "nose blink", "notnose off"):
            with self.subTest(message=message):
                self.assertFalse(self.nose.command(message))
                self.assertEqual(self.nose.level(), 1)

    def test_auto_command_restarts_quiet_interval(self):
        self.nose.command("nose on")
        self.clock.now = 3
        self.nose.command("NOSE AUTO\n")
        self.assertEqual(self.nose.level(), 0)
        self.assertEqual(self.nose.next_pulse, 18)

    def test_bounds_are_finite_through_whole_envelope(self):
        for duration in (0.5, 4, 30):
            self.clock.now = 0
            self.nose.command("nose pulse %s" % duration)
            for step in range(101):
                self.clock.now = duration * step / 100
                self.assertTrue(0 <= self.nose.level() <= 1)

    def test_theme_defaults_and_projection_options(self):
        self.assertEqual(theme_options([]).theme, "halloween")
        args = theme_options(["--theme", "christmas", "--nose-every", "8", "16",
                              "--nose-y", "-20", "--no-antlers", ":0"])
        self.assertEqual(args.nose_every, [8, 16])
        self.assertEqual(args.nose_y, -20)
        self.assertTrue(args.no_antlers)


if __name__ == "__main__":
    unittest.main()
