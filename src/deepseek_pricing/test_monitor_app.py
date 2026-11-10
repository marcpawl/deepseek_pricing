#!/usr/bin/env python3
"""Unit tests for the schedule-driven parts of the monitor app.

The Tk window itself is not created: the helpers under test never touch
it, so the instance is built with ``object.__new__``.
"""
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deepseek_pricing import gui, schedule  # noqa: E402

UTC = ZoneInfo("UTC")


def utc(*args):
    """Build an aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)


def make_app():
    """Create an app instance without constructing the Tk window."""
    return object.__new__(gui.DeepSeekMonitorApp)


class StatusColorTests(unittest.TestCase):

    def test_peak_is_red(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 9, 2, 0)), "red")

    def test_far_from_peak_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 0, 0)), "green")

    def test_within_warning_window_is_yellow(self):
        app = make_app()
        # The 01:00 UTC window opens at 01:00, so 00:50 is ten minutes out.
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 0, 50)),
                         "yellow")

    def test_just_outside_warning_window_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 10, 0, 44)),
                         "green")

    def test_weekend_is_green(self):
        app = make_app()
        self.assertEqual(app.compute_color(utc(2026, 11, 7, 1, 30)),
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
        now = utc(2026, 11, 10, 5, 0)
        windows = app.get_next_non_peak_windows(now, count=1)
        self.assertEqual(windows[0][0], now)

    def test_peak_now_skips_to_next_non_peak(self):
        app = make_app()
        # 02:00 UTC is inside the 01:00-04:00 window, which closes at 04:00.
        windows = app.get_next_non_peak_windows(utc(2026, 11, 10, 2, 0),
                                                count=1)
        self.assertEqual(windows[0][0], utc(2026, 11, 10, 4, 0))

    def test_count_is_respected(self):
        app = make_app()
        for count in (0, 1, 5):
            windows = app.get_next_non_peak_windows(utc(2026, 11, 10, 5, 0),
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
        now = utc(2026, 11, 10, 5, 0)
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


class FakeScrollbar:
    """Records grid/grid_remove calls instead of touching a real window."""

    def __init__(self, mapped=False):
        self.mapped = mapped
        self.set_calls = []
        self.grid_calls = 0
        self.grid_remove_calls = 0

    def set(self, first, last):
        self.set_calls.append((first, last))

    def winfo_ismapped(self):
        return self.mapped

    def grid(self):
        self.mapped = True
        self.grid_calls += 1

    def grid_remove(self):
        self.mapped = False
        self.grid_remove_calls += 1


class FakeCanvas:
    """Records the scroll moves requested by the wheel handler."""

    def __init__(self, content_height=100, view_height=200):
        self.scrolls = []
        self.moves = []
        self.content_height = content_height
        self.view_height = view_height

    def bbox(self, _tag):
        return (0, 0, 100, self.content_height)

    def winfo_height(self):
        return self.view_height

    def yview_scroll(self, steps, units):
        self.scrolls.append((steps, units))

    def yview_moveto(self, fraction):
        self.moves.append(fraction)


class FakeEvent:
    def __init__(self, delta=0, num=None):
        self.delta = delta
        self.num = num


class ScrollbarTests(unittest.TestCase):

    def make_scroll_app(self, mapped=False, content_height=300,
                        view_height=200):
        app = make_app()
        app.scrollbar = FakeScrollbar(mapped=mapped)
        app.canvas = FakeCanvas(
            content_height=content_height, view_height=view_height
        )
        return app

    def test_scrollbar_appears_when_text_overflows(self):
        app = self.make_scroll_app(mapped=False)
        app.sync_scrollbar("0.0", "0.5")
        self.assertTrue(app.scrollbar.mapped)
        self.assertEqual(app.scrollbar.grid_calls, 1)
        self.assertEqual(app.scrollbar.set_calls, [("0.0", "0.5")])

    def test_scrollbar_hidden_when_text_fits(self):
        app = self.make_scroll_app(mapped=True, content_height=100)
        app.sync_scrollbar("0.0", "1.0")
        self.assertFalse(app.scrollbar.mapped)
        self.assertEqual(app.scrollbar.grid_remove_calls, 1)
        self.assertEqual(app.canvas.moves, [0.0])

    def test_scrollbar_stays_hidden_when_text_fits(self):
        app = self.make_scroll_app(mapped=False, content_height=100)
        app.sync_scrollbar("0.0", "1.0")
        self.assertFalse(app.scrollbar.mapped)
        self.assertEqual(app.scrollbar.grid_calls, 0)
        self.assertEqual(app.scrollbar.grid_remove_calls, 0)

    def test_fitting_text_hides_scrollbar_even_with_stale_fractions(self):
        # Scrolling down then shrinking the text leaves the yview
        # fractions below (0.0, 1.0); the canvas height decides.
        app = self.make_scroll_app(mapped=True, content_height=100)
        app.sync_scrollbar("0.1", "0.3")
        self.assertFalse(app.scrollbar.mapped)

    def test_exactly_fitting_text_hides_scrollbar(self):
        app = self.make_scroll_app(mapped=True, content_height=200,
                                   view_height=200)
        app.sync_scrollbar("0.0", "1.0")
        self.assertFalse(app.scrollbar.mapped)

    def test_wheel_does_nothing_without_scrollbar(self):
        app = self.make_scroll_app(mapped=False)
        app.scroll_wheel(FakeEvent(delta=-120))
        self.assertEqual(app.canvas.scrolls, [])

    def test_wheel_direction_from_delta(self):
        app = self.make_scroll_app(mapped=True)
        app.scroll_wheel(FakeEvent(delta=120))
        app.scroll_wheel(FakeEvent(delta=-120))
        self.assertEqual(app.canvas.scrolls, [(-1, "units"), (1, "units")])

    def test_wheel_direction_from_x11_button(self):
        app = self.make_scroll_app(mapped=True)
        app.scroll_wheel(FakeEvent(num=4))
        app.scroll_wheel(FakeEvent(num=5))
        self.assertEqual(app.canvas.scrolls, [(-1, "units"), (1, "units")])

    def test_wheel_ignores_events_without_direction(self):
        app = self.make_scroll_app(mapped=True)
        app.scroll_wheel(FakeEvent())
        self.assertEqual(app.canvas.scrolls, [])


class MissingTkinterTests(unittest.TestCase):
    """The module must stay importable when tkinter is not installed.

    Ubuntu ships tkinter as a separate ``python3-tk`` package, and CI
    installs neither, so importing this module must not require it.
    The probe runs in a subprocess because ``sys.modules`` cannot be
    un-imported once another test module has loaded tkinter.
    """

    PROBE = """
import sys


class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'")
        return None


sys.meta_path.insert(0, Blocker())
sys.path.insert(0, {src!r})

from deepseek_pricing import gui
app = object.__new__(gui.DeepSeekMonitorApp)
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime(2026, 11, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
print(app.compute_color(now))
print(len(app.get_next_non_peak_windows(now)))
"""

    def test_import_and_helpers_work_without_tkinter(self):
        result = subprocess.run(
            [sys.executable, "-c", self.PROBE.format(src=str(SRC_DIR))],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["green", "3"])

    def test_tkinter_is_not_imported_at_module_scope(self):
        self.assertNotIn("tkinter", gui.__dict__)


if __name__ == "__main__":
    unittest.main()
