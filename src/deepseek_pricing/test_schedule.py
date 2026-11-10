#!/usr/bin/env python3
"""Unit tests for deepseek_pricing.schedule."""
import collections.abc
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deepseek_pricing import schedule  # noqa: E402

UTC = ZoneInfo("UTC")


def utc(*args):
    """Build an aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)


class PricingRulesTests(unittest.TestCase):

    def test_weekday_boundaries_follow_utc_hours(self):
        # The documented windows are 01:00-04:00 and 06:00-10:00 UTC.
        self.assertFalse(schedule.is_peak(utc(2026, 11, 10, 0, 59)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 10, 1, 0)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 10, 3, 59)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 10, 4, 0)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 10, 5, 59)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 10, 6, 0)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 10, 9, 59)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 10, 10, 0)))

    def test_the_documented_windows_are_peak_every_weekday(self):
        # 2026-11-09 is a Monday; every documented hour is peak.
        for hour in (1, 2, 3, 6, 7, 8, 9):
            with self.subTest(hour=hour):
                self.assertTrue(schedule.is_peak(utc(2026, 11, 9, hour, 30)))

    def test_evening_utc_is_not_peak(self):
        # 17:00-02:00 UTC used to be peak when the hours were read as
        # Beijing time; under the documented UTC rule it is off-peak.
        for hour in (17, 19, 22, 23, 0):
            with self.subTest(hour=hour):
                self.assertFalse(
                    schedule.is_peak(utc(2026, 11, 10, hour, 30))
                )

    def test_weekend_is_never_peak(self):
        # 2026-11-07 is a Saturday.
        self.assertFalse(schedule.is_peak(utc(2026, 11, 7, 1, 30)))

    def test_holiday_is_never_peak(self):
        # 2026-10-01 is China's National Day.
        self.assertFalse(schedule.is_peak(utc(2026, 10, 1, 1, 30)))

    def test_is_peak_accepts_other_timezones(self):
        beijing = ZoneInfo("Asia/Shanghai")
        # Beijing 09:30 is 01:30 UTC, inside the first window.
        self.assertTrue(schedule.is_peak(datetime(2026, 11, 10, 9, 30,
                                                  tzinfo=beijing)))


class BoundaryTests(unittest.TestCase):

    def test_next_boundary_mid_peak(self):
        # 01:30 UTC is inside the 01:00-04:00 window -> 04:00.
        boundary = schedule.next_boundary(utc(2026, 11, 10, 1, 30))
        self.assertEqual(boundary, utc(2026, 11, 10, 4, 0))

    def test_next_boundary_mid_non_peak(self):
        # 05:00 UTC sits between windows -> 06:00.
        boundary = schedule.next_boundary(utc(2026, 11, 10, 5, 0))
        self.assertEqual(boundary, utc(2026, 11, 10, 6, 0))

    def test_next_boundary_before_peak(self):
        # 00:30 UTC -> the 01:00 window start.
        boundary = schedule.next_boundary(utc(2026, 11, 10, 0, 30))
        self.assertEqual(boundary, utc(2026, 11, 10, 1, 0))

    def test_next_boundary_after_last_peak(self):
        # 11:00 UTC is after both windows -> next UTC midnight.
        boundary = schedule.next_boundary(utc(2026, 11, 10, 11, 0))
        self.assertEqual(boundary, utc(2026, 11, 11, 0, 0))

    def test_find_boundary_skips_non_peak_day(self):
        # Saturday is all non-peak; the first change is Monday 01:00 UTC.
        boundary = schedule.find_boundary(utc(2026, 11, 7, 5, 0))
        self.assertEqual(boundary, utc(2026, 11, 9, 1, 0))

    def test_find_boundary_ends_at_peak_start(self):
        # 00:00 UTC is off-peak; the next change is the 01:00 window.
        boundary = schedule.find_boundary(utc(2026, 11, 10, 0, 0))
        self.assertEqual(boundary, utc(2026, 11, 10, 1, 0))

    def test_find_boundary_across_utc_midnight(self):
        # 23:00 UTC on a weekday is off-peak until the next day's 01:00.
        boundary = schedule.find_boundary(utc(2026, 11, 10, 23, 0))
        self.assertEqual(boundary, utc(2026, 11, 11, 1, 0))

    def test_find_boundary_always_changes_state(self):
        for start in (
            utc(2026, 11, 10, 0, 0),
            utc(2026, 11, 10, 1, 0),
            utc(2026, 11, 10, 5, 0),
            utc(2026, 11, 10, 9, 0),
            utc(2026, 11, 10, 14, 0),
            utc(2026, 11, 14, 12, 0),
        ):
            with self.subTest(start=start):
                boundary = schedule.find_boundary(start)
                self.assertGreater(boundary, start)
                self.assertNotEqual(
                    schedule.is_peak(start), schedule.is_peak(boundary)
                )


class PricingPeriodsIteratorTests(unittest.TestCase):

    def test_returns_an_iterator(self):
        periods = schedule.pricing_periods(2, utc(2026, 11, 10, 2, 0))
        self.assertIs(iter(periods), periods)
        self.assertIsInstance(periods, collections.abc.Iterator)
        self.assertNotIsInstance(periods, (list, tuple, dict))

    def test_current_peak_period_is_included(self):
        # 02:00 UTC is inside the 01:00-04:00 window, which closes at 04:00.
        periods = list(schedule.pricing_periods(3, utc(2026, 11, 10, 2, 0)))
        self.assertEqual(periods[0]["startTime"],
                         utc(2026, 11, 10, 2, 0).isoformat())
        self.assertEqual(periods[0]["endTime"],
                         utc(2026, 11, 10, 4, 0).isoformat())
        self.assertEqual(periods[0]["pricing"], "PEAK")

    def test_current_non_peak_period_is_included(self):
        # 05:00 UTC sits between the two windows, ending at 06:00.
        period = next(schedule.pricing_periods(1, utc(2026, 11, 10, 5, 0)))
        self.assertEqual(period["startTime"],
                         utc(2026, 11, 10, 5, 0).isoformat())
        self.assertEqual(period["endTime"],
                         utc(2026, 11, 10, 6, 0).isoformat())
        self.assertEqual(period["pricing"], "NONPEAK")

    def test_periods_are_contiguous_and_alternate(self):
        periods = list(schedule.pricing_periods(6, utc(2026, 11, 10, 2, 0)))
        self.assertEqual(len(periods), 6)
        for previous, current in zip(periods, periods[1:]):
            self.assertEqual(previous["endTime"], current["startTime"])
            self.assertNotEqual(previous["pricing"], current["pricing"])

    def test_zero_periods(self):
        self.assertEqual(
            list(schedule.pricing_periods(0, utc(2026, 11, 10, 2, 0))), []
        )

    def test_default_count_is_three(self):
        periods = schedule.pricing_periods(now=utc(2026, 11, 10, 2, 0))
        self.assertEqual(len(list(periods)), 3)

    def test_default_now_is_used(self):
        self.assertEqual(len(list(schedule.pricing_periods(1))), 1)

    def test_negative_count_is_rejected_eagerly(self):
        with self.assertRaises(ValueError):
            schedule.pricing_periods(-1, utc(2026, 11, 10, 2, 0))

    def test_naive_datetime_is_rejected_eagerly(self):
        with self.assertRaises(ValueError):
            schedule.pricing_periods(1, datetime(2026, 11, 10, 2, 0))

    def test_is_lazy_but_repeatable_for_new_calls(self):
        first = schedule.pricing_periods(2, utc(2026, 11, 10, 2, 0))
        second = schedule.pricing_periods(2, utc(2026, 11, 10, 2, 0))
        self.assertEqual(next(first), next(second))

    def test_times_are_iso_utc(self):
        for period in schedule.pricing_periods(2, utc(2026, 11, 10, 2, 0)):
            self.assertTrue(period["startTime"].endswith("+00:00"))
            self.assertTrue(period["endTime"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
