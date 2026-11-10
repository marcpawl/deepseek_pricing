#!/usr/bin/env python3
"""Check that the JSON sample in README.md is what the command prints.

The README shows a `json` invocation with a fixed `--start-at`, followed
by the output it produces. Documentation drifts, so the sample is not
taken on trust: this module pulls the command and the sample out of the
markdown, runs the command, and compares the result byte for byte.
"""
import json
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

# A fenced block, capturing the language tag and the body. The non-greedy
# body stops at the first closing fence, and no block nests another.
FENCED_BLOCK = re.compile(r"^```(\w*)\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def fenced_blocks(text):
    """Return the fenced code blocks as (language, body) pairs."""
    return [
        (match.group(1), match.group(2))
        for match in FENCED_BLOCK.finditer(text)
    ]


def sample_block(text):
    """Return the body of the JSON sample shown in the README."""
    for language, body in fenced_blocks(text):
        if language == "json":
            return body
    raise AssertionError("README.md has no ```json block")


def command_block(text):
    """Return the body of the command that produces the JSON sample.

    It is the nearest plain block above the sample that mentions
    ``--start-at``, which is what makes the sample reproducible.
    """
    blocks = fenced_blocks(text)
    for index, (language, body) in enumerate(blocks):
        if language != "json":
            continue
        for earlier_language, earlier_body in reversed(blocks[:index]):
            if earlier_language == "" and "--start-at" in earlier_body:
                return earlier_body
        break
    raise AssertionError(
        "README.md has no --start-at command above the ```json block"
    )


def command_argv(body):
    """Turn a documented command into an argv that can be run here.

    ``\\`` joins the wrapped lines of the command. The ``uv run`` prefix
    is dropped and the script is run with the current interpreter, so the
    check does not depend on uv being installed or on network access.
    """
    argv = shlex.split(body.replace("\\\n", " "))
    if argv[:2] != ["uv", "run"]:
        raise AssertionError(f"expected a 'uv run' command, got: {body!r}")
    argv = argv[2:]
    return [sys.executable, *argv]


class ReadmeJsonSampleTests(unittest.TestCase):

    def setUp(self):
        self.text = README.read_text()

    def run_documented_command(self):
        argv = command_argv(command_block(self.text))
        result = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_sample_matches_the_command_output(self):
        # The exact-text comparison also catches a change to the JSON
        # formatting, which would make the sample misleading even though
        # the document still parses to the same value.
        self.assertEqual(
            self.run_documented_command().rstrip("\n"),
            sample_block(self.text).rstrip("\n"),
        )

    def test_sample_is_the_same_document(self):
        # The parsed comparison keeps a formatting failure from hiding the
        # reason: a value changing is a different bug from spacing.
        self.assertEqual(
            json.loads(self.run_documented_command()),
            json.loads(sample_block(self.text)),
        )

    def test_sample_has_the_documented_period_count(self):
        body = command_block(self.text)
        self.assertIn("--max-periods 3", body)
        self.assertEqual(
            len(json.loads(sample_block(self.text))["periods"]), 3
        )

    def test_command_block_precedes_the_sample(self):
        # The sample is introduced by the command, so a reader meets the
        # invocation before the output it explains.
        blocks = fenced_blocks(self.text)
        languages = [language for language, _ in blocks]
        sample = languages.index("json")
        command = max(
            index for index, (language, body) in enumerate(blocks)
            if language == "" and "--start-at" in body
            and index < sample
        )
        self.assertLess(command, sample)

    def test_missing_command_block_is_reported(self):
        # Without the --start-at command the sample cannot be reproduced,
        # so the helper must say so rather than silently pick another.
        text = self.text.replace("--start-at", "--something-else")
        with self.assertRaises(AssertionError):
            command_block(text)


if __name__ == "__main__":
    unittest.main()
