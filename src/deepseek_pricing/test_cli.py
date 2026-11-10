#!/usr/bin/env python3
"""Unit tests for the deepseek-alert command line interface."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import jsonschema  # noqa: E402

import deepseek_pricing  # noqa: E402
from deepseek_pricing import main  # noqa: E402
from deepseek_pricing.schedule import UTC  # noqa: E402

SCHEMA_PATH = SRC_DIR / "deepseek_pricing.schema.json"


def schema():
    """Load the JSON schema that the output must satisfy."""
    return json.loads(SCHEMA_PATH.read_text())


@contextlib.contextmanager
def stubbed_rules_check(replacement=None):
    """Replace the published-rules check for the duration of a test.

    The check fetches the DeepSeek documentation, so a test that runs a
    command must stub it. ``replacement`` is what
    ``pricing_doc.verify_published_rules`` becomes; by default it is a
    no-op that confirms the rules.
    """
    if replacement is None:
        def replacement():
            return None
    original = deepseek_pricing.pricing_doc.verify_published_rules
    deepseek_pricing.pricing_doc.verify_published_rules = replacement
    try:
        yield replacement
    finally:
        deepseek_pricing.pricing_doc.verify_published_rules = original


def run(argv):
    """Run the CLI and return the status with its stdout and stderr.

    argparse writes help to stdout and usage errors to stderr, so both
    are captured to keep the test output readable. The published-rules
    check is stubbed out: it is a network call, and the tests that care
    about it are in :class:`PublishedRulesTests`.
    """
    out, err = io.StringIO(), io.StringIO()
    with stubbed_rules_check():
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            status = main(argv)
    return status, out.getvalue(), err.getvalue()


def run_json(argv):
    """Run the ``json`` command and return the parsed document."""
    status, out, _ = run(argv)
    return status, json.loads(out)


def parse(argv):
    """Parse arguments, returning the exit status instead of raising."""
    parser = deepseek_pricing.build_parser()
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            args = parser.parse_args(argv)
    except SystemExit as exit_error:
        return exit_error.code, None, out.getvalue(), err.getvalue()
    return 0, args, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):

    def test_parser_program_name(self):
        self.assertEqual(deepseek_pricing.build_parser().prog,
                         "deepseek-alert")

    def test_no_command_by_default(self):
        # A missing command is what makes main() print the help text.
        self.assertIsNone(parse([])[1].command)

    def test_accepts_json_command(self):
        self.assertEqual(parse(["json"])[1].command, "json")

    def test_accepts_gui_command(self):
        self.assertEqual(parse(["gui"])[1].command, "gui")

    def test_unknown_command_is_rejected(self):
        status, args, _, err = parse(["nope"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("invalid choice", err)

    def test_two_commands_are_rejected(self):
        # The commands are subcommands, so only the first is taken as the
        # command and "json" is left over as a stray argument.
        status, args, _, err = parse(["gui", "json"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("unrecognized arguments: json", err)

    def test_json_limits_default_to_none(self):
        args = parse(["json"])[1]
        self.assertIsNone(args.max_periods)
        self.assertIsNone(args.max_peak_periods)
        self.assertIsNone(args.max_nonpeak_periods)

    def test_accepts_json_limits(self):
        args = parse([
            "json", "--max-periods", "2",
            "--max-peak-periods", "1",
            "--max-nonpeak-periods", "1",
        ])[1]
        self.assertEqual(args.max_periods, 2)
        self.assertEqual(args.max_peak_periods, 1)
        self.assertEqual(args.max_nonpeak_periods, 1)

    def test_rejects_non_integer_limit(self):
        status, _, _, err = parse(["json", "--max-periods", "x"])
        self.assertEqual(status, 2)
        self.assertIn("invalid int value", err)

    def test_rejects_negative_limits(self):
        # Each limit is validated by argparse, so a negative value is a
        # usage error here rather than a ValueError from pricing_json.
        for option in ("--max-periods", "--max-peak-periods",
                       "--max-nonpeak-periods"):
            with self.subTest(option=option):
                status, args, _, err = parse(["json", option, "-1"])
                self.assertEqual(status, 2)
                self.assertIsNone(args)
                self.assertIn("must not be negative", err)

    def test_accepts_zero_limit(self):
        self.assertEqual(parse(["json", "--max-periods", "0"])[1]
                         .max_periods, 0)

    def test_accepts_negative_looking_value_after_option(self):
        # argparse must consume "-1" as the option's value, not mistake it
        # for an option of its own, so the error names the right option.
        _, _, _, err = parse(["json", "--max-periods", "-1"])
        self.assertIn("argument --max-periods", err)

    def test_help_exits_zero(self):
        status, _, out, _ = parse(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("usage: deepseek-alert", out)

    def test_help_lists_the_commands(self):
        out = parse(["--help"])[2]
        self.assertIn("{json,gui}", out)

    def test_json_help_lists_the_limits(self):
        status, _, out, _ = parse(["json", "--help"])
        self.assertEqual(status, 0)
        for option in ("--max-periods", "--max-peak-periods",
                       "--max-nonpeak-periods"):
            self.assertIn(option, out)

    def test_gui_help_omits_the_limits(self):
        status, _, out, _ = parse(["gui", "--help"])
        self.assertEqual(status, 0)
        self.assertNotIn("--max", out)
        self.assertNotIn("--start-at", out)


class RemovedFlagTests(unittest.TestCase):
    """The old ``--json`` and ``--gui`` flags are gone, not aliased.

    They became subcommands, so the flags must fail loudly. Keeping them
    as aliases would leave two spellings of every command to document and
    test, and argparse cannot put the limit options on a flag anyway.
    """

    def test_json_flag_is_rejected(self):
        status, args, _, err = parse(["--json"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("unrecognized arguments: --json", err)

    def test_gui_flag_is_rejected(self):
        status, args, _, err = parse(["--gui"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("unrecognized arguments: --gui", err)

    def test_error_points_at_the_replacement(self):
        # The usage line names the commands, so the correction is visible
        # without reading the release notes.
        _, _, _, err = parse(["--json"])
        self.assertIn("{json,gui}", err)


class JsonOnlyOptionTests(unittest.TestCase):
    """The ``--max-*`` limits belong to the ``json`` command alone.

    They used to sit on the top-level parser, where ``--gui --max-periods
    2`` silently parsed and ignored the value. As options of the ``json``
    subparser they cannot be given to any other command.
    """

    def test_limits_are_rejected_without_a_command(self):
        # argparse reads the "2" as the command name, so the complaint is
        # about an invalid choice rather than the stray option. Either way
        # it is a usage error: exit 2 and nothing parsed.
        status, args, _, err = parse(["--max-periods", "2"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("error:", err)

    def test_limits_are_rejected_by_gui(self):
        status, args, _, err = parse(["gui", "--max-periods", "2"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("unrecognized arguments", err)

    def test_every_limit_is_rejected_by_gui(self):
        for option in ("--max-periods", "--max-peak-periods",
                       "--max-nonpeak-periods"):
            with self.subTest(option=option):
                status, args, _, _ = parse(["gui", option, "1"])
                self.assertEqual(status, 2)
                self.assertIsNone(args)

    def test_limits_are_accepted_by_json(self):
        self.assertEqual(parse(["json", "--max-periods", "2"])[1]
                         .max_periods, 2)


class StartAtTests(unittest.TestCase):
    """``--start-at`` anchors the periods at a supplied instant.

    The value carries its own offset, which is how the instant is known,
    but the output is always UTC: the peak hours are published in UTC, so
    ``schedule`` evaluates them there and reports them there. A ``+08:00``
    timestamp therefore names the instant rather than the output offset.
    The parsing is covered here as well, because
    ``datetime.fromisoformat`` accepts a timestamp with no offset at all
    and ``pricing_periods`` would then reject it with a traceback instead
    of a usage error.
    """

    def test_defaults_to_none(self):
        # None is what makes pricing_periods use the current time.
        self.assertIsNone(parse(["json"])[1].start_at)

    def test_accepts_offset_timestamp(self):
        args = parse(["json", "--start-at", "2026-11-10T23:15:00+08:00"])[1]
        self.assertEqual(
            args.start_at,
            datetime(2026, 11, 10, 15, 15, tzinfo=UTC),
        )

    def test_converts_an_offset_timestamp_to_utc(self):
        args = parse(["json", "--start-at", "2026-11-10T23:15:00+08:00"])[1]
        self.assertEqual(args.start_at.utcoffset(), timedelta(0))

    def test_accepts_zulu_timestamp(self):
        args = parse(["json", "--start-at", "2026-11-10T15:15:00Z"])[1]
        self.assertEqual(args.start_at.utcoffset(), timedelta(0))

    def test_equals_form_is_accepted(self):
        args = parse(["json", "--start-at=2026-11-10T23:15:00+08:00"])[1]
        self.assertEqual(
            args.start_at, datetime(2026, 11, 10, 15, 15, tzinfo=UTC)
        )

    def test_starts_the_periods_at_the_given_instant(self):
        # 23:15 +08:00 is 15:15 UTC, off-peak until the 01:00 window.
        doc = run_json(["json", "--start-at", "2026-11-10T23:15:00+08:00",
                        "--max-periods", "3"])[1]
        self.assertEqual(
            [p["startTime"] for p in doc["periods"]],
            ["2026-11-10T15:15:00+00:00",
             "2026-11-11T01:00:00+00:00",
             "2026-11-11T04:00:00+00:00"],
        )

    def test_periods_are_always_expressed_in_utc(self):
        doc = run_json(["json", "--start-at", "2026-11-10T15:15:00Z",
                        "--max-periods", "2"])[1]
        self.assertEqual(
            [p["startTime"] for p in doc["periods"]],
            ["2026-11-10T15:15:00+00:00", "2026-11-11T01:00:00+00:00"],
        )

    def test_start_at_output_matches_schema(self):
        doc = run_json(["json", "--start-at", "2026-11-10T23:15:00+08:00"])[1]
        jsonschema.validate(instance=doc, schema=schema())

    def test_without_start_at_the_first_period_is_now(self):
        first = run_json(["json", "--max-periods", "1"])[1]["periods"][0]
        start = datetime.fromisoformat(first["startTime"])
        elapsed = (datetime.now(tz=UTC) - start).total_seconds()
        self.assertLess(abs(elapsed), 60)

    def test_rejects_unparseable_timestamp(self):
        status, args, _, err = parse(["json", "--start-at", "garbage"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("invalid ISO 8601 timestamp", err)

    def test_rejects_timestamp_without_offset(self):
        # fromisoformat parses this into a naive datetime, which
        # pricing_periods refuses; catch it at the parser instead.
        for value in ("2026-11-10T23:15", "2026-11-10"):
            with self.subTest(value=value):
                status, args, _, err = parse(["json", "--start-at", value])
                self.assertEqual(status, 2)
                self.assertIsNone(args)
                self.assertIn("needs a UTC offset", err)

    def test_rejects_missing_value(self):
        status, args, _, err = parse(["json", "--start-at"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("expected one argument", err)

    def test_bad_timestamp_exits_two_without_a_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                main(["json", "--start-at", "garbage"])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn("Traceback", err.getvalue())

    def test_gui_does_not_accept_start_at(self):
        status, args, _, err = parse(["gui", "--start-at",
                                      "2026-11-10T23:15:00+08:00"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("unrecognized arguments", err)


class UsageErrorTests(unittest.TestCase):
    """Usage errors must exit through argparse, not a traceback.

    Before the limits were given an argparse ``type``, a negative value
    was accepted by the parser and only rejected by
    ``pricing_json.format_pricing_json``, so ``--max-periods -1`` printed
    a ``ValueError`` traceback and exited 1 instead of the usage error and
    exit status 2 that every other bad option produces.
    """

    def test_negative_limit_exits_two_without_a_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                main(["json", "--max-periods", "-1"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("must not be negative", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class JsonCommandTests(unittest.TestCase):

    def test_json_exits_zero(self):
        self.assertEqual(run(["json"])[0], 0)

    def test_json_writes_only_to_stdout(self):
        status, out, err = run(["json", "--max-periods", "1"])
        self.assertEqual(status, 0)
        self.assertNotEqual(out, "")
        self.assertEqual(err, "")

    def test_json_defaults_to_five_periods(self):
        self.assertEqual(len(run_json(["json"])[1]["periods"]), 5)

    def test_json_matches_schema(self):
        doc = run_json(["json"])[1]
        jsonschema.validate(instance=doc, schema=schema())

    def test_json_respects_max_periods(self):
        self.assertEqual(len(run_json(["json", "--max-periods", "2"])[1]
                             ["periods"]), 2)

    def test_json_respects_max_peak_periods(self):
        doc = run_json(["json", "--max-peak-periods", "1",
                        "--max-periods", "10"])[1]
        self.assertEqual(
            [p["pricing"] for p in doc["periods"]].count("PEAK"), 1
        )

    def test_json_respects_max_nonpeak_periods(self):
        doc = run_json(["json", "--max-nonpeak-periods", "1",
                        "--max-periods", "10"])[1]
        self.assertEqual(
            [p["pricing"] for p in doc["periods"]].count("NONPEAK"), 1
        )

    def test_json_zero_periods(self):
        self.assertEqual(run_json(["json", "--max-periods", "0"])[1],
                         {"version": 1, "periods": []})

    def test_json_does_not_start_the_gui(self):
        # A GUI would block in mainloop, so returning is the assertion.
        self.assertEqual(run_json(["json", "--max-periods", "1"])[0], 0)


class GuiCommandTests(unittest.TestCase):

    def test_gui_starts_the_monitor(self):
        calls = []
        original = deepseek_pricing.run_gui
        deepseek_pricing.run_gui = lambda: calls.append(True) or 0
        try:
            status = run(["gui"])[0]
        finally:
            deepseek_pricing.run_gui = original
        self.assertEqual(status, 0)
        self.assertEqual(calls, [True])


class PublishedRulesTests(unittest.TestCase):
    """The published-rules check gates both commands.

    The schedule is only justified by one paragraph of the DeepSeek
    documentation, so the command refuses to run when that paragraph is
    gone. The check is a network call, which is why every other test
    stubs it and these are the ones that exercise it.
    """

    def test_failure_stops_the_json_command(self):
        def fail():
            raise deepseek_pricing.pricing_doc.PricingDocError("changed")

        out, err = io.StringIO(), io.StringIO()
        with stubbed_rules_check(fail):
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                status = main(["json"])
        self.assertEqual(status, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("deepseek-alert: changed", err.getvalue())

    def test_failure_is_reported_on_stderr(self):
        def fail():
            raise deepseek_pricing.pricing_doc.PricingDocError("changed")

        err = io.StringIO()
        with stubbed_rules_check(fail):
            status = deepseek_pricing.verify_published_rules(error_file=err)
        self.assertEqual(status, 1)
        self.assertIn("deepseek-alert: changed", err.getvalue())

    def test_failure_does_not_start_the_gui(self):
        calls = []

        def fail():
            raise deepseek_pricing.pricing_doc.PricingDocError("changed")

        original = deepseek_pricing.run_gui
        deepseek_pricing.run_gui = lambda: calls.append(True) or 0
        try:
            err = io.StringIO()
            with stubbed_rules_check(fail):
                with contextlib.redirect_stderr(err):
                    status = main(["gui"])
        finally:
            deepseek_pricing.run_gui = original
        self.assertEqual(status, 1)
        self.assertEqual(calls, [])

    def test_success_returns_zero(self):
        self.assertEqual(deepseek_pricing.verify_published_rules(
            error_file=io.StringIO()), 0)

    def test_no_command_skips_the_check(self):
        calls = []

        def record():
            calls.append(True)

        out = io.StringIO()
        with stubbed_rules_check(record):
            with contextlib.redirect_stdout(out):
                status = main([])
        self.assertEqual(status, 0)
        self.assertEqual(calls, [])

    def test_help_skips_the_check(self):
        calls = []

        def record():
            calls.append(True)

        with stubbed_rules_check(record):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(calls, [])


class DefaultCommandTests(unittest.TestCase):

    def test_no_argument_prints_help(self):
        status, out, _ = run([])
        self.assertEqual(status, 0)
        self.assertIn("usage: deepseek-alert", out)
        self.assertIn("json", out)
        self.assertIn("gui", out)

    def test_help_option_raises_system_exit(self):
        # main(["--help"]) does not return: argparse's help action exits
        # with status 0. Callers that loop over argv must expect this.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as caught:
                main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("usage: deepseek-alert", out.getvalue())


class TkinterIndependenceTests(unittest.TestCase):
    """Importing the package must not pull in tkinter.

    These checks run in a subprocess so they cannot be fooled by another
    test module having already imported tkinter into ``sys.modules``.
    """

    def assert_not_imported(self, module):
        program = (
            "import sys\n"
            "import deepseek_pricing\n"
            "print('yes' if {!r} in sys.modules else 'no')\n"
        ).format(module)
        result = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "no")

    def test_package_import_does_not_import_tkinter(self):
        # The json command and --help must work without a display.
        self.assert_not_imported("tkinter")

    def test_package_import_does_not_import_gui(self):
        self.assert_not_imported("deepseek_pricing.gui")


if __name__ == "__main__":
    unittest.main()
