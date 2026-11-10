#!/usr/bin/env python3
"""Unit tests for deepseek_pricing.schedule."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import jsonschema  # noqa: E402

from deepseek_pricing import schedule  # noqa: E402

SCHEMA_PATH = SRC_DIR / "deepseek_pricing.schema.json"
UTC = ZoneInfo("UTC")


def utc(*args):
    """Build an aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)


class LoadSchemaMixin:

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text())

    def assert_matches_schema(self, data):
        jsonschema.validate(instance=data, schema=self.schema)


class PricingRulesTests(unittest.TestCase):

    def test_weekday_boundaries_follow_beijing_hours(self):
        # Beijing peak windows are 01:00-04:00 and 06:00-10:00, i.e.
        # 17:00-20:00 and 22:00-02:00 UTC.
        self.assertTrue(schedule.is_peak(utc(2026, 11, 9, 17, 0)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 9, 19, 59)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 9, 20, 0)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 9, 21, 59)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 9, 22, 0)))
        self.assertTrue(schedule.is_peak(utc(2026, 11, 10, 1, 59)))
        self.assertFalse(schedule.is_peak(utc(2026, 11, 10, 2, 0)))

    def test_weekend_is_never_peak(self):
        # 2026-11-07 is a Saturday.
        self.assertFalse(schedule.is_peak(utc(2026, 11, 7, 1, 30)))

    def test_holiday_is_never_peak(self):
        # 2026-10-01 is China's National Day.
        self.assertFalse(schedule.is_peak(utc(2026, 10, 1, 1, 30)))

    def test_is_peak_accepts_other_timezones(self):
        beijing = ZoneInfo("Asia/Shanghai")
        self.assertTrue(schedule.is_peak(datetime(2026, 11, 10, 9, 30,
                                                  tzinfo=beijing)))


class BoundaryTests(unittest.TestCase):

    def test_next_boundary_mid_peak(self):
        # Beijing 01:30 is inside the 01:00-04:00 window -> 04:00.
        boundary = schedule.next_boundary(utc(2026, 11, 9, 17, 30))
        self.assertEqual(boundary, utc(2026, 11, 9, 20, 0))

    def test_next_boundary_mid_non_peak(self):
        # Beijing 05:00 sits between windows -> 06:00.
        boundary = schedule.next_boundary(utc(2026, 11, 9, 21, 0))
        self.assertEqual(boundary, utc(2026, 11, 9, 22, 0))

    def test_next_boundary_before_peak(self):
        # Beijing 00:30 -> the 01:00 window start.
        boundary = schedule.next_boundary(utc(2026, 11, 9, 16, 30))
        self.assertEqual(boundary, utc(2026, 11, 9, 17, 0))

    def test_next_boundary_after_last_peak(self):
        # Beijing 19:00 is after both windows -> next Beijing midnight.
        boundary = schedule.next_boundary(utc(2026, 11, 10, 11, 0))
        self.assertEqual(boundary, utc(2026, 11, 10, 16, 0))

    def test_find_boundary_skips_non_peak_day(self):
        # Saturday is all non-peak; the first change is Monday 01:00
        # Beijing = Sunday 17:00 UTC.
        boundary = schedule.find_boundary(utc(2026, 11, 7, 5, 0))
        self.assertEqual(boundary, utc(2026, 11, 8, 17, 0))

    def test_find_boundary_ends_at_peak_start(self):
        # Beijing 10:00 is between windows; the next change is the start
        # of the 17:00 UTC window, five non-peak hours later.
        boundary = schedule.find_boundary(utc(2026, 11, 10, 2, 0))
        self.assertEqual(boundary, utc(2026, 11, 10, 17, 0))

    def test_find_boundary_always_changes_state(self):
        for start in (
            utc(2026, 11, 10, 0, 0),
            utc(2026, 11, 10, 1, 0),
            utc(2026, 11, 10, 5, 0),
            utc(2026, 11, 10, 9, 0),
            utc(2026, 11, 14, 12, 0),
        ):
            with self.subTest(start=start):
                boundary = schedule.find_boundary(start)
                self.assertGreater(boundary, start)
                self.assertNotEqual(
                    schedule.is_peak(start), schedule.is_peak(boundary)
                )


class PricingPeriodTests(LoadSchemaMixin, unittest.TestCase):

    def test_current_peak_period_is_included(self):
        # Beijing 01:30 is peak, ending when the 04:00 window closes.
        data = schedule.pricing_periods(3, utc(2026, 11, 9, 17, 30))
        periods = data["periods"]
        self.assertEqual(periods[0]["startTime"],
                         utc(2026, 11, 9, 17, 30).isoformat())
        self.assertEqual(periods[0]["endTime"],
                         utc(2026, 11, 9, 20, 0).isoformat())
        self.assertEqual(periods[0]["pricing"], "PEAK")

    def test_current_non_peak_period_is_included(self):
        data = schedule.pricing_periods(1, utc(2026, 11, 10, 2, 0))
        self.assertEqual(data["periods"][0]["pricing"], "NONPEAK")

    def test_periods_are_contiguous_and_alternate(self):
        data = schedule.pricing_periods(6, utc(2026, 11, 10, 2, 0))
        periods = data["periods"]
        self.assertEqual(len(periods), 6)
        for previous, current in zip(periods, periods[1:]):
            self.assertEqual(previous["endTime"], current["startTime"])
            self.assertNotEqual(previous["pricing"], current["pricing"])

    def test_zero_periods(self):
        data = schedule.pricing_periods(0, utc(2026, 11, 10, 2, 0))
        self.assertEqual(data, {"version": 1, "periods": []})

    def test_default_count_is_three(self):
        data = schedule.pricing_periods(now=utc(2026, 11, 10, 2, 0))
        self.assertEqual(len(data["periods"]), 3)

    def test_default_now_is_used(self):
        data = schedule.pricing_periods(1)
        self.assertEqual(len(data["periods"]), 1)

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            schedule.pricing_periods(1, datetime(2026, 11, 10, 2, 0))

    def test_negative_count_is_rejected(self):
        with self.assertRaises(ValueError):
            schedule.pricing_periods(-1, utc(2026, 11, 10, 2, 0))

    def test_matches_schema_from_peak(self):
        self.assert_matches_schema(
            schedule.pricing_periods(4, utc(2026, 11, 10, 1, 30))
        )

    def test_matches_schema_from_weekend(self):
        self.assert_matches_schema(
            schedule.pricing_periods(5, utc(2026, 11, 7, 5, 0))
        )

    def test_matches_schema_from_holiday(self):
        self.assert_matches_schema(
            schedule.pricing_periods(5, utc(2026, 10, 1, 3, 0))
        )

    def test_times_are_iso_utc(self):
        data = schedule.pricing_periods(2, utc(2026, 11, 10, 2, 0))
        for period in data["periods"]:
            self.assertTrue(period["startTime"].endswith("+00:00"))
            self.assertTrue(period["endTime"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
