#!/usr/bin/env python3
"""Unit tests for the deepseek-alert command line interface."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import jsonschema  # noqa: E402

import deepseek_pricing  # noqa: E402
from deepseek_pricing import main  # noqa: E402

SCHEMA_PATH = SRC_DIR / "deepseek_pricing.schema.json"


def schema():
    """Load the JSON schema that the output must satisfy."""
    return json.loads(SCHEMA_PATH.read_text())


def run(argv):
    """Run the CLI and return the status with its stdout and stderr.

    argparse writes help to stdout and usage errors to stderr, so both
    are captured to keep the test output readable.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = main(argv)
    return status, out.getvalue(), err.getvalue()


def run_json(argv):
    """Run the CLI with ``--json`` and return the parsed document."""
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

    def test_gui_defaults_to_false(self):
        self.assertFalse(parse([])[1].gui)

    def test_json_defaults_to_false(self):
        self.assertFalse(parse([])[1].json)

    def test_accepts_gui(self):
        self.assertTrue(parse(["--gui"])[1].gui)

    def test_accepts_json(self):
        self.assertTrue(parse(["--json"])[1].json)

    def test_gui_and_json_are_mutually_exclusive(self):
        status, args, _, err = parse(["--gui", "--json"])
        self.assertEqual(status, 2)
        self.assertIsNone(args)
        self.assertIn("not allowed with argument", err)

    def test_json_limits_default_to_none(self):
        args = parse(["--json"])[1]
        self.assertIsNone(args.max_periods)
        self.assertIsNone(args.max_peak_periods)
        self.assertIsNone(args.max_nonpeak_periods)

    def test_accepts_json_limits(self):
        args = parse([
            "--json", "--max-periods", "2",
            "--max-peak-periods", "1",
            "--max-nonpeak-periods", "1",
        ])[1]
        self.assertEqual(args.max_periods, 2)
        self.assertEqual(args.max_peak_periods, 1)
        self.assertEqual(args.max_nonpeak_periods, 1)

    def test_rejects_non_integer_limit(self):
        status, _, _, err = parse(["--json", "--max-periods", "x"])
        self.assertEqual(status, 2)
        self.assertIn("invalid int value", err)

    def test_rejects_negative_limits(self):
        # Each limit is validated by argparse, so a negative value is a
        # usage error here rather than a ValueError from pricing_json.
        for option in ("--max-periods", "--max-peak-periods",
                       "--max-nonpeak-periods"):
            with self.subTest(option=option):
                status, args, _, err = parse(["--json", option, "-1"])
                self.assertEqual(status, 2)
                self.assertIsNone(args)
                self.assertIn("must not be negative", err)

    def test_accepts_zero_limit(self):
        self.assertEqual(parse(["--json", "--max-periods", "0"])[1]
                         .max_periods, 0)

    def test_accepts_negative_looking_value_after_option(self):
        # argparse must consume "-1" as the option's value, not mistake it
        # for an option of its own, so the error names the right option.
        _, _, _, err = parse(["--json", "--max-periods", "-1"])
        self.assertIn("argument --max-periods", err)

    def test_help_exits_zero(self):
        status, _, out, _ = parse(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("usage: deepseek-alert", out)

    def test_unknown_option_is_rejected(self):
        status, _, _, err = parse(["--nope"])
        self.assertEqual(status, 2)
        self.assertIn("unrecognized arguments", err)

    def test_help_documents_every_option(self):
        out = parse(["--help"])[2]
        for option in ("--gui", "--json", "--max-periods",
                       "--max-peak-periods", "--max-nonpeak-periods"):
            self.assertIn(option, out)


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
                main(["--json", "--max-periods", "-1"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("must not be negative", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class JsonCommandTests(unittest.TestCase):

    def test_json_exits_zero(self):
        self.assertEqual(run(["--json"])[0], 0)

    def test_json_writes_only_to_stdout(self):
        status, out, err = run(["--json", "--max-periods", "1"])
        self.assertEqual(status, 0)
        self.assertNotEqual(out, "")
        self.assertEqual(err, "")

    def test_json_defaults_to_five_periods(self):
        self.assertEqual(len(run_json(["--json"])[1]["periods"]), 5)

    def test_json_matches_schema(self):
        doc = run_json(["--json"])[1]
        jsonschema.validate(instance=doc, schema=schema())

    def test_json_respects_max_periods(self):
        self.assertEqual(len(run_json(["--json", "--max-periods", "2"])[1]
                             ["periods"]), 2)

    def test_json_respects_max_peak_periods(self):
        doc = run_json(["--json", "--max-peak-periods", "1",
                        "--max-periods", "10"])[1]
        self.assertEqual(
            [p["pricing"] for p in doc["periods"]].count("PEAK"), 1
        )

    def test_json_respects_max_nonpeak_periods(self):
        doc = run_json(["--json", "--max-nonpeak-periods", "1",
                        "--max-periods", "10"])[1]
        self.assertEqual(
            [p["pricing"] for p in doc["periods"]].count("NONPEAK"), 1
        )

    def test_json_zero_periods(self):
        self.assertEqual(run_json(["--json", "--max-periods", "0"])[1],
                         {"version": 1, "periods": []})

    def test_json_does_not_start_the_gui(self):
        # A GUI would block in mainloop, so returning is the assertion.
        self.assertEqual(run_json(["--json", "--max-periods", "1"])[0], 0)


class GuiCommandTests(unittest.TestCase):

    def test_gui_starts_the_monitor(self):
        calls = []
        original = deepseek_pricing.run_gui
        deepseek_pricing.run_gui = lambda: calls.append(True) or 0
        try:
            status = main(["--gui"])
        finally:
            deepseek_pricing.run_gui = original
        self.assertEqual(status, 0)
        self.assertEqual(calls, [True])


class DefaultCommandTests(unittest.TestCase):

    def test_no_argument_prints_help(self):
        status, out, _ = run([])
        self.assertEqual(status, 0)
        self.assertIn("usage: deepseek-alert", out)
        self.assertIn("--json", out)
        self.assertIn("--gui", out)

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
        # --json and --help must work on machines without a display.
        self.assert_not_imported("tkinter")

    def test_package_import_does_not_import_gui(self):
        self.assert_not_imported("deepseek_pricing.gui")


if __name__ == "__main__":
    unittest.main()
