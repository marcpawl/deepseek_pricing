#!/usr/bin/env python3
"""Unit tests for scripts/dev.py."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import dev  # noqa: E402


def capture(function, *args, **kwargs):
    """Run a function and return (return value, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = function(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def tempfile_python(source):
    """Create a temporary python file inside the repository tree."""
    handle, path = tempfile.mkstemp(suffix=".py", dir=dev.REPO_ROOT)
    with os.fdopen(handle, "w") as stream:
        stream.write(source)
    try:
        yield path
    finally:
        os.unlink(path)


class ParserTests(unittest.TestCase):

    def test_parser_requires_a_command(self):
        parser = dev.build_parser()
        with self.assertRaises(SystemExit):
            capture(parser.parse_args, [])

    def test_parser_rejects_unknown_command(self):
        parser = dev.build_parser()
        with self.assertRaises(SystemExit):
            capture(parser.parse_args, ["does-not-exist"])

    def test_pycodestyle_defaults(self):
        parser = dev.build_parser()
        args = parser.parse_args(["pycodestyle"])
        self.assertEqual(args.command, "pycodestyle")
        self.assertEqual(args.targets, [])
        self.assertFalse(args.staged)
        self.assertEqual(args.max_line_length, 79)

    def test_pycodestyle_accepts_targets_and_options(self):
        parser = dev.build_parser()
        args = parser.parse_args(
            ["pycodestyle", "--staged", "--max-line-length", "100", "src"]
        )
        self.assertEqual(args.targets, ["src"])
        self.assertTrue(args.staged)
        self.assertEqual(args.max_line_length, 100)


class CollectPythonFilesTests(unittest.TestCase):

    def test_finds_project_python_files(self):
        files = dev.collect_python_files(["src", "scripts"])
        relatives = [os.path.relpath(f, dev.REPO_ROOT) for f in files]
        self.assertIn(
            os.path.join("src", "deepseek_pricing", "__init__.py"),
            relatives,
        )
        self.assertIn(os.path.join("scripts", "dev.py"), relatives)
        self.assertTrue(all(f.endswith(".py") for f in files))

    def test_returns_empty_list_for_missing_target(self):
        self.assertEqual(dev.collect_python_files(["no-such-dir"]), [])

    def test_single_file_target(self):
        files = dev.collect_python_files(["scripts/dev.py"])
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("dev.py"))

    def test_targets_are_sorted(self):
        files = dev.collect_python_files(["src"])
        self.assertEqual(files, sorted(files))


class SelectTargetsTests(unittest.TestCase):

    def test_uses_defaults_when_nothing_requested(self):
        self.assertEqual(
            dev.select_targets([]), list(dev.DEFAULT_TARGETS)
        )

    def test_keeps_requested_targets_without_staged(self):
        self.assertEqual(
            dev.select_targets(["src"], use_git_index=False), ["src"]
        )

    def test_staged_filters_to_index_files(self):
        with mock.patch.object(
            dev, "files_in_git_index", return_value=["scripts/dev.py"]
        ):
            selected = dev.select_targets([], use_git_index=True)
        self.assertEqual(
            [os.path.basename(f) for f in selected], ["dev.py"]
        )

    def test_staged_with_no_matching_files(self):
        with mock.patch.object(dev, "files_in_git_index", return_value=[]):
            self.assertEqual(dev.select_targets([], use_git_index=True), [])


class PycodestyleCommandTests(unittest.TestCase):

    def test_clean_file_passes(self):
        with tempfile_python("") as path:
            code, out, _ = capture(dev.main, ["pycodestyle", path])
        self.assertEqual(code, 0)
        self.assertIn("no findings", out)

    def test_file_with_findings_fails(self):
        with tempfile_python("x=1\n") as path:
            code, out, _ = capture(dev.main, ["pycodestyle", path])
        self.assertEqual(code, 1)
        self.assertIn("finding(s) found", out)
        self.assertIn("E225", out)

    def test_long_lines_respect_max_line_length(self):
        source = "x = '" + "a" * 90 + "'\n"
        with tempfile_python(source) as path:
            default_code, _, _ = capture(dev.main, ["pycodestyle", path])
            relaxed_code, _, _ = capture(
                dev.main,
                ["pycodestyle", "--max-line-length", "120", path],
            )
        self.assertEqual(default_code, 1)
        self.assertEqual(relaxed_code, 0)

    def test_no_files_to_check(self):
        with tempfile_python("") as path:
            with mock.patch.object(
                dev, "files_in_git_index", return_value=[]
            ):
                code, out, _ = capture(
                    dev.main, ["pycodestyle", "--staged", path]
                )
        self.assertEqual(code, 0)
        self.assertIn("no python files to check", out)

    def test_staged_files_are_checked(self):
        with tempfile_python("x=1\n") as path:
            rel = os.path.relpath(path, dev.REPO_ROOT)
            with mock.patch.object(
                dev, "files_in_git_index", return_value=[rel]
            ):
                code, _, _ = capture(
                    dev.main, ["pycodestyle", "--staged", path]
                )
        self.assertEqual(code, 1)

    def test_repository_is_pep8_clean(self):
        code, out, err = capture(dev.main, ["pycodestyle"])
        self.assertEqual(code, 0, msg=out + err)


class TestCommandTests(unittest.TestCase):

    def test_parser_accepts_test_command(self):
        parser = dev.build_parser()
        args = parser.parse_args(["test"])
        self.assertEqual(args.command, "test")

    def test_test_command_runs_unittest_discovery(self):
        with mock.patch.object(
            dev.subprocess, "call", return_value=0
        ) as call:
            code, _, _ = capture(dev.main, ["test"])
        self.assertEqual(code, 0)
        command = call.call_args[0][0]
        self.assertEqual(command[0], sys.executable)
        self.assertIn("unittest", command)
        self.assertIn("discover", command)

    def test_test_command_propagates_failure(self):
        with mock.patch.object(dev.subprocess, "call", return_value=1):
            code, _, _ = capture(dev.main, ["test"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
