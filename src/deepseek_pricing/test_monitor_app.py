#!/usr/bin/env python3
"""Unit tests for the schedule-driven parts of the monitor app.

The Tk window itself is not created: the helpers under test never touch
it, so the instance is built with ``object.__new__``.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deepseek_pricing import DeepSeekMonitorApp, schedule  # noqa: E402

UTC = ZoneInfo("UTC")


def utc(*args):
    """Build an aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)


def make_app():
    """Create an app instance without constructing the Tk window."""
    return object.__new__(DeepSeekMonitorApp)


class StatusColorTests(unittest.TestCase):

    def test_peak_is_red(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 9, 17, 30)), "red")

    def test_far_from_peak_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 2, 0)), "green")

    def test_within_warning_window_is_yellow(self):
        app = make_app()
        # Non-peak ends and peak starts at 17:00 UTC.
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 16, 50)),
                         "yellow")

    def test_just_outside_warning_window_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 16, 44)),
                         "green")

    def test_weekend_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 7, 17, 30)),
                         "green")


class NonPeakWindowTests(unittest.TestCase):

    def test_windows_exclude_peak_periods(self):
        app = make_app()
        windows = app.get_next_non_peak_windows(utc(2026, 11, 10, 2, 0))
        self.assertEqual(len(windows), 3)
        for start, end in windows:
            self.assertEqual(schedule.is_peak(start), False)
            self.assertGreater(end, start)

    def test_windows_are_ordered_and_reach_past_today(self):
        app = make_app()
        windows = app.get_next_non_peak_windows(utc(2026, 11, 10, 2, 0))
        for previous, current in zip(windows, windows[1:]):
            self.assertLess(previous[1], current[0])

    def test_first_window_contains_now_when_non_peak(self):
        app = make_app()
        now = utc(2026, 11, 10, 2, 0)
        windows = app.get_next_non_peak_windows(now, count=1)
        self.assertEqual(windows[0][0], now)

    def test_peak_now_skips_to_next_non_peak(self):
        app = make_app()
        windows = app.get_next_non_peak_windows(utc(2026, 11, 9, 17, 30),
                                                count=1)
        self.assertEqual(windows[0][0], utc(2026, 11, 9, 20, 0))

    def test_count_is_respected(self):
        app = make_app()
        for count in (0, 1, 5):
            windows = app.get_next_non_peak_windows(utc(2026, 11, 10, 2, 0),
                                                    count=count)
            self.assertEqual(len(windows), count)

    def test_parsed_datetimes_are_aware(self):
        app = make_app()
        for start, end in app.get_next_non_peak_windows(utc(2026, 11, 10)):
            self.assertIsNotNone(start.tzinfo)
            self.assertIsNotNone(end.tzinfo)


class PricingPeriodHelperTests(unittest.TestCase):

    def test_helper_mirrors_schedule_iterator(self):
        app = make_app()
        now = utc(2026, 11, 10, 2, 0)
        expected = list(schedule.pricing_periods(3, now))
        actual = app.get_pricing_periods(now, count=3)
        self.assertEqual(
            [(p["start"], p["end"], p["pricing"]) for p in actual],
            [
                (
                    datetime.fromisoformat(p["startTime"]),
                    datetime.fromisoformat(p["endTime"]),
                    p["pricing"],
                )
                for p in expected
            ],
        )

    def test_evaluate_status_renders_schedule(self):
        app = make_app()
        color, text = app.evaluate_status()
        self.assertIn(color, ("green", "yellow", "red"))
        self.assertIn("UPCOMING SCHEDULE", text)
        self.assertIn("WINDOW #1", text)
        self.assertIn("Local   |", text)
        self.assertIn("Beijing |", text)


if __name__ == "__main__":
    unittest.main()
