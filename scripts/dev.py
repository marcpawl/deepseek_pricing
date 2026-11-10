#!/usr/bin/env python3
"""Developer helper commands for the deepseek_pricing project."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGETS = ("src", "scripts", ".githooks")
SKIPPED_DIRECTORIES = ("__pycache__", ".venv", ".git")

# Matches a shebang that runs python, directly or through env.
PYTHON_SHEBANG = re.compile(
    rb"^#!"
    rb"(?:"
    rb"(?:\S*/)?python"          # /usr/bin/python3, python3.12, bin/python
    rb"|"
    rb"(?:\S*/)?env\s+(?:-\S+\s+)*python"  # /usr/bin/env [-S] python3
    rb")"
)


def repo_path(*parts):
    """Return an absolute path inside the repository root."""
    return os.path.join(REPO_ROOT, *parts)


def is_python_file(path):
    """True if the path is a python file by suffix or shebang."""
    path = Path(path)
    if path.suffix == ".py":
        return True
    try:
        with path.open("rb") as stream:
            first_line = stream.readline()
    except (OSError, ValueError):
        return False
    return bool(PYTHON_SHEBANG.match(first_line))


def collect_python_files(targets):
    """Return sorted python file Paths found under the given targets."""
    files = []
    for target in targets:
        target_path = Path(repo_path(target))
        if target_path.is_file():
            if is_python_file(target_path):
                files.append(target_path)
            continue
        for root, dirnames, filenames in os.walk(target_path):
            dirnames[:] = sorted(
                d for d in dirnames if d not in SKIPPED_DIRECTORIES
            )
            for filename in sorted(filenames):
                candidate = Path(root) / filename
                if is_python_file(candidate):
                    files.append(candidate)
    files.sort()
    return files


def files_in_git_index():
    """Return repository relative paths of the files staged in git."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    lines = (line.strip() for line in result.stdout.splitlines())
    return [line for line in lines if line]


def select_targets(requested, use_git_index=False):
    """Resolve the list of scripts that pycodestyle should check."""
    targets = list(requested or DEFAULT_TARGETS)
    if not use_git_index:
        return targets

    staged = set(files_in_git_index())
    selected = []
    for target in collect_python_files(targets):
        rel = os.path.relpath(target, REPO_ROOT)
        if rel in staged:
            selected.append(target)
    return selected


def cmd_pycodestyle(args):
    """Check PEP 8 compliance of the project's python files."""
    import pycodestyle

    targets = [
        str(target)
        for target in select_targets(args.targets, use_git_index=args.staged)
    ]
    if not targets:
        print("pycodestyle: no python files to check")
        return 0

    style = pycodestyle.StyleGuide(
        quiet=False,
        paths=targets,
        max_line_length=args.max_line_length,
    )
    report = style.check_files()
    if report.total_errors:
        print(f"pycodestyle: {report.total_errors} finding(s) found")
        return 1
    print(f"pycodestyle: no findings in {len(targets)} file(s)")
    return 0


TEST_DIRECTORIES = ("src", "scripts")


def cmd_test(args):
    """Run the project's unit tests with unittest."""
    status = 0
    for directory in TEST_DIRECTORIES:
        top_level = repo_path(directory)
        status = status or subprocess.call(
            [
                sys.executable, "-m", "unittest", "discover", "-v",
                "-s", top_level, "-t", top_level,
            ],
            cwd=REPO_ROOT,
        )
    return status


def build_parser():
    """Build the argument parser for all developer commands."""
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Developer helper commands for deepseek_pricing.",
    )
    subparsers = parser.add_subparsers(
        dest="command", metavar="command", required=True
    )

    pep8 = subparsers.add_parser(
        "pycodestyle",
        help="Check PEP 8 compliance of python files.",
        description=(
            "Check PEP 8 compliance of python files under "
            f"{', '.join(DEFAULT_TARGETS)}."
        ),
    )
    pep8.add_argument(
        "targets",
        nargs="*",
        help=(
            "Files or directories to check. Defaults to "
            f"{', '.join(DEFAULT_TARGETS)}."
        ),
    )
    pep8.add_argument(
        "--staged",
        action="store_true",
        help="Only check files staged in the git index (used by pre-commit).",
    )
    pep8.add_argument(
        "--max-line-length",
        type=int,
        default=79,
        help="Maximum allowed line length (default: 79).",
    )
    pep8.set_defaults(func=cmd_pycodestyle)

    tests = subparsers.add_parser(
        "test",
        help="Run the unit tests.",
        description=(
            "Run the unit tests in "
            f"{', '.join(TEST_DIRECTORIES)}/ with unittest."
        ),
    )
    tests.set_defaults(func=cmd_test)

    return parser


def main(argv=None):
    """Run the requested developer command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
