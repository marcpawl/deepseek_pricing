#!/usr/bin/env python3
"""Unit tests for scripts/dev.py."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
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
def tempfile_python(source, suffix=".py"):
    """Create a temporary file inside the repository tree."""
    handle, path = tempfile.mkstemp(suffix=suffix, dir=dev.REPO_ROOT)
    with os.fdopen(handle, "w") as stream:
        stream.write(source)
    try:
        yield path
    finally:
        os.unlink(path)


class IsPythonFileTests(unittest.TestCase):

    def test_py_suffix_is_python(self):
        self.assertTrue(dev.is_python_file(Path("module.py")))
        self.assertTrue(dev.is_python_file(Path("/tmp/some/module.py")))

    def test_py_suffix_without_reading_contents(self):
        with mock.patch.object(Path, "open") as mocked_open:
            self.assertTrue(dev.is_python_file(Path("module.py")))
        mocked_open.assert_not_called()

    def test_env_python_shebang_is_python(self):
        with tempfile_python("#!/usr/bin/env python3\n", suffix="") as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_env_python_versioned_shebang_is_python(self):
        with tempfile_python(
            "#!/usr/bin/env python3.12\n", suffix=""
        ) as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_env_with_flag_python_shebang_is_python(self):
        with tempfile_python(
            "#!/usr/bin/env -S python3 -u\n", suffix=""
        ) as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_env_without_python_is_not_python(self):
        with tempfile_python("#!/usr/bin/env bash\n", suffix="") as p:
            self.assertFalse(dev.is_python_file(Path(p)))

    def test_python_with_args_shebang_is_python(self):
        with tempfile_python("#!/usr/bin/python3 -u\n", suffix="") as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_versioned_python_shebang_is_python(self):
        with tempfile_python("#!/usr/bin/python3.12\n", suffix="") as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_bare_python_shebang_is_python(self):
        with tempfile_python("#!python\n", suffix="") as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_relative_path_shebang_is_python(self):
        with tempfile_python("#!bin/python -u\n", suffix="") as p:
            self.assertTrue(dev.is_python_file(Path(p)))

    def test_non_python_shebang_is_not_python(self):
        with tempfile_python("#!/bin/bash\necho hi\n", suffix="") as p:
            self.assertFalse(dev.is_python_file(Path(p)))

    def test_file_without_shebang_is_not_python(self):
        with tempfile_python("just text\n", suffix="") as p:
            self.assertFalse(dev.is_python_file(Path(p)))

    def test_empty_file_is_not_python(self):
        with tempfile_python("", suffix="") as p:
            self.assertFalse(dev.is_python_file(Path(p)))

    def test_shebang_must_be_on_first_line(self):
        with tempfile_python("\n#!/usr/bin/env python3\n", suffix="") as p:
            self.assertFalse(dev.is_python_file(Path(p)))

    def test_missing_file_is_not_python(self):
        self.assertFalse(
            dev.is_python_file(Path("/no/such/file/anywhere"))
        )

    def test_accepts_string_path(self):
        self.assertTrue(dev.is_python_file("module.py"))


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
        self.assertTrue(all(isinstance(f, Path) for f in files))
        self.assertTrue(all(dev.is_python_file(f) for f in files))

    def test_finds_shebang_only_files(self):
        files = dev.collect_python_files([".githooks"])
        relatives = [os.path.relpath(f, dev.REPO_ROOT) for f in files]
        self.assertIn(os.path.join(".githooks", "pre-commit"), relatives)

    def test_skips_non_python_files(self):
        files = dev.collect_python_files(["."])
        relatives = [os.path.relpath(f, dev.REPO_ROOT) for f in files]
        self.assertNotIn("uv.lock", relatives)
        self.assertNotIn("README.md", relatives)
        self.assertNotIn("install.sh", relatives)

    def test_returns_empty_list_for_missing_target(self):
        self.assertEqual(dev.collect_python_files(["no-such-dir"]), [])

    def test_single_file_target(self):
        files = dev.collect_python_files(["scripts/dev.py"])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "dev.py")

    def test_single_non_python_file_target(self):
        self.assertEqual(dev.collect_python_files(["README.md"]), [])

    def test_single_shebang_file_target(self):
        files = dev.collect_python_files([".githooks/pre-commit"])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "pre-commit")

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
