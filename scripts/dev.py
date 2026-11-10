#!/usr/bin/env python3
"""Developer helper commands for the deepseek_pricing project."""
import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGETS = ("src", "scripts", ".githooks")


def repo_path(*parts):
    """Return an absolute path inside the repository root."""
    return os.path.join(REPO_ROOT, *parts)


def collect_python_files(targets):
    """Return sorted python file paths found under the given targets."""
    files = []
    for target in targets:
        target_path = repo_path(target)
        if os.path.isfile(target_path):
            if target_path.endswith(".py"):
                files.append(target_path)
            continue
        for root, dirnames, filenames in os.walk(target_path):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in ("__pycache__", ".venv", ".git")
            )
            for filename in sorted(filenames):
                if filename.endswith(".py"):
                    files.append(os.path.join(root, filename))
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

    targets = select_targets(args.targets, use_git_index=args.staged)
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


def cmd_test(args):
    """Run the project's unit tests with unittest."""
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        repo_path("scripts"),
        "-p",
        "test_*.py",
        "-t",
        repo_path("scripts"),
        "-v",
    ]
    return subprocess.call(command, cwd=REPO_ROOT)


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
        description="Run the unit tests in scripts/ with unittest.",
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
