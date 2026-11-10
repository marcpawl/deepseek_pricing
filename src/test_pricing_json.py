#!/usr/bin/env python3
"""Unit tests for src/pricing_json.py."""
import inspect
import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryFile
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import jsonschema  # noqa: E402

import pricing_json  # noqa: E402
from deepseek_pricing import schedule  # noqa: E402

SCHEMA_PATH = SRC_DIR / "deepseek_pricing.schema.json"
UTC = ZoneInfo("UTC")
# Tuesday 2026-11-10 02:00 UTC is non-peak; peak starts at 17:00 UTC.
WORKDAY = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)


def schema():
    """Load the JSON schema that the output must satisfy."""
    return json.loads(SCHEMA_PATH.read_text())


def schedule_periods(count=20, now=WORKDAY):
    """Build the schedule generator used by the tests."""
    return schedule.pricing_periods(count, now)


def render(*args, **kwargs):
    """Run print_pricing_json into a StringIO and return the text."""
    buffer = io.StringIO()
    pricing_json.print_pricing_json(*args, file=buffer, **kwargs)
    return buffer.getvalue()


def document(*args, **kwargs):
    """Render and parse the document."""
    return json.loads(render(*args, **kwargs))


def prices(doc):
    """Return the pricing labels from a rendered document."""
    return [period["pricing"] for period in doc["periods"]]


class DefaultsTests(unittest.TestCase):

    def test_default_max_periods_is_five(self):
        self.assertEqual(len(document(schedule_periods())["periods"]), 5)

    def test_limits_default_to_max_periods(self):
        self.assertEqual(
            len(document(schedule_periods(), max_periods=6)["periods"]), 6
        )

    def test_default_limits_do_not_stop_early(self):
        # Alternating periods: five periods never hit a cap of five.
        self.assertEqual(prices(document(schedule_periods())),
                         ["NONPEAK", "PEAK", "NONPEAK", "PEAK", "NONPEAK"])

    def test_parameter_defaults(self):
        parameters = inspect.signature(
            pricing_json.print_pricing_json
        ).parameters
        self.assertEqual(parameters["max_periods"].default, 5)
        self.assertIsNone(parameters["max_peak_periods"].default)
        self.assertIsNone(parameters["max_nonpeak_periods"].default)


class LimitsTests(unittest.TestCase):

    def test_max_periods_limits_total(self):
        self.assertEqual(
            len(document(schedule_periods(), max_periods=3)["periods"]), 3
        )

    def test_max_peak_stops_at_first_peak(self):
        doc = document(schedule_periods(), max_periods=10,
                       max_peak_periods=1)
        self.assertEqual(prices(doc), ["NONPEAK", "PEAK"])

    def test_max_nonpeak_stops_at_first_nonpeak(self):
        doc = document(schedule_periods(), max_periods=10,
                       max_nonpeak_periods=1)
        self.assertEqual(prices(doc), ["NONPEAK"])

    def test_zero_peak_periods_produces_empty_document(self):
        self.assertEqual(
            document(schedule_periods(), max_peak_periods=0),
            {"version": 1, "periods": []},
        )

    def test_zero_nonpeak_periods_stops_before_first_nonpeak(self):
        self.assertEqual(
            document(schedule_periods(), max_nonpeak_periods=0),
            {"version": 1, "periods": []},
        )

    def test_zero_max_periods_yields_empty_list(self):
        self.assertEqual(
            document(schedule_periods(), max_periods=0),
            {"version": 1, "periods": []},
        )

    def test_starting_on_peak_with_peak_limit_zero(self):
        peak_now = datetime(2026, 11, 9, 17, 30, tzinfo=UTC)
        self.assertEqual(
            document(schedule_periods(now=peak_now), max_peak_periods=0),
            {"version": 1, "periods": []},
        )

    def test_stops_consuming_the_iterator(self):
        consumed = []

        def generator():
            for period in schedule_periods(1000):
                consumed.append(period)
                yield period

        render(generator(), max_periods=10, max_peak_periods=1)
        # The generator must not be walked past the first peak.
        self.assertEqual(len(consumed), 2)

    def test_stops_at_max_periods_without_over_consuming(self):
        consumed = []

        def generator():
            for period in schedule_periods(1000):
                consumed.append(period)
                yield period

        render(generator(), max_periods=2)
        self.assertEqual(len(consumed), 2)

    def test_keeps_original_order(self):
        starts = [p["startTime"]
                  for p in document(schedule_periods(),
                                    max_periods=6)["periods"]]
        self.assertEqual(starts, sorted(starts))

    def test_negative_limits_are_rejected(self):
        for kwargs in (
            {"max_periods": -1},
            {"max_peak_periods": -1},
            {"max_nonpeak_periods": -1},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    render(schedule_periods(), **kwargs)


class OutputTests(unittest.TestCase):

    def test_matches_schema(self):
        jsonschema.validate(instance=document(schedule_periods()),
                            schema=schema())

    def test_matches_schema_from_peak(self):
        peak_now = datetime(2026, 11, 9, 17, 30, tzinfo=UTC)
        jsonschema.validate(
            instance=document(schedule_periods(now=peak_now),
                              max_periods=4),
            schema=schema(),
        )

    def test_matches_schema_when_limited(self):
        jsonschema.validate(
            instance=document(schedule_periods(), max_periods=2,
                              max_peak_periods=1, max_nonpeak_periods=1),
            schema=schema(),
        )

    def test_empty_document_matches_schema(self):
        jsonschema.validate(instance={"version": 1, "periods": []},
                            schema=schema())

    def test_version_is_one(self):
        self.assertEqual(document(schedule_periods())["version"], 1)

    def test_output_is_indented_json(self):
        text = render(schedule_periods(), max_periods=1)
        self.assertIn('"version": 1', text)
        self.assertIn('  "periods": [', text)
        self.assertIn("\n", text)

    def test_output_ends_with_newline(self):
        self.assertTrue(
            render(schedule_periods(), max_periods=1).endswith("}\n")
        )

    def test_empty_iterator_is_valid(self):
        self.assertEqual(document(iter(())), {"version": 1, "periods": []})


class FileHandleTests(unittest.TestCase):

    def test_defaults_to_standard_output(self):
        buffer = io.StringIO()
        stdout = sys.stdout
        sys.stdout = buffer
        try:
            pricing_json.print_pricing_json(schedule_periods(),
                                            max_periods=2)
        finally:
            sys.stdout = stdout
        self.assertEqual(len(json.loads(buffer.getvalue())["periods"]), 2)

    def test_file_default_is_none(self):
        parameters = inspect.signature(
            pricing_json.print_pricing_json
        ).parameters
        self.assertIsNone(parameters["file"].default)

    def test_writes_to_an_open_file(self):
        with TemporaryFile(mode="w+") as handle:
            pricing_json.print_pricing_json(schedule_periods(),
                                            max_periods=2, file=handle)
            handle.seek(0)
            doc = json.load(handle)
        self.assertEqual(len(doc["periods"]), 2)
        jsonschema.validate(instance=doc, schema=schema())

    def test_writes_to_a_string_io(self):
        buffer = io.StringIO()
        pricing_json.print_pricing_json(schedule_periods(),
                                        max_periods=1, file=buffer)
        self.assertEqual(len(json.loads(buffer.getvalue())["periods"]), 1)

    def test_does_not_write_to_stdout_when_file_given(self):
        buffer = io.StringIO()
        stdout = io.StringIO()
        original = sys.stdout
        sys.stdout = stdout
        try:
            pricing_json.print_pricing_json(schedule_periods(),
                                            max_periods=1, file=buffer)
        finally:
            sys.stdout = original
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotEqual(buffer.getvalue(), "")

    def test_returns_none(self):
        buffer = io.StringIO()
        self.assertIsNone(
            pricing_json.print_pricing_json(schedule_periods(), file=buffer)
        )


if __name__ == "__main__":
    unittest.main()
