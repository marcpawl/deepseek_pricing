---
name: git
description: Commit with git using a message file and `git commit -F`. Use
  whenever work is ready for review before committing, or when the work is
  about to be committed.
---

# Committing with git in this repository

## The rule

**Never pass the commit message on the command line.** Write it to a
temporary file first, then commit with `-F`:

```bash
# 1. Write the message to a temporary file.
$EDITOR "$(mktemp)"
# ...or write it with the Write tool to a path under /tmp.

# 2. Commit, reading the message from that file.
git commit -F /tmp/commit_msg.txt

# 3. Remove the file.
rm /tmp/commit_msg.txt
```

`git commit -m "<message>"` is **not** used, and neither is a bare
`git commit` (which opens an editor).

## When this applies

- **The task's work is ready for review, before it is committed.** Write the
  message to the file at that point — it is the artifact the reviewer reads,
  and writing it first is what makes the review a review of the message as
  well as the diff.
- **The work is about to be committed.** Same file, same `-F` flag.

Both moments use one file. Write it once, review it, then commit from it.

## Why a file, not `-m`

A bare `git commit` **hangs** without a TTY. `EDITOR=vim` is set in this
environment, so git opens vim, vim exits with

```
Vim: Error reading input, exiting...
error: There was a problem with the editor 'vim'.
Please supply the message using either -m or -F option.
```

and the commit never happens — usually only after the pre-commit gates have
already run and timed out. Writing the file and passing `-F` removes the
editor from the loop entirely.

`-m` avoids the editor too, but it is the fragile option: the messages in
this repository contain backticks, apostrophes, `$`, `!`, and multi-paragraph
bodies. Each of those is a shell-quoting hazard, and one badly quoted
character silently mangles the message. A file has no quoting at all.

## Message content

Match the existing log. Look at it before writing:

```bash
git log --format='=== %h%n%B' -5
```

Shape:

- **Subject line**, imperative mood, no trailing period, **≤ 72 columns**
  (`Evaluate peak hours in UTC and verify them against the docs`).
- **Blank line**, then a body wrapped at **72–79 columns**. This repository
  wraps at 79; do not exceed it.
- Explain **why**, not just what — the diff already says what changed.
  Compare options considered and say why the chosen one won.
- Reference the specific files, functions and tests that carry the change.
- Quote the source of truth verbatim when the change is about matching an
  external specification. `2fe102e` opens with the DeepSeek paragraph, which
  is what made "the hours were read in the wrong zone" legible without
  opening the docs.
- End with the trailer block (see below).

Repository-specific wisdom worth carrying into the body when relevant:

- A behaviour change that a reader could reasonably "fix" back to the old way
  deserves the reason it was chosen. Reporting periods in UTC rather than in
  the offset given to `--start-at` is one; so is having no `--skip-verify`
  flag, where the answer to "the docs changed" is to read them, not to
  bypass the check.
- Say when a test was verified to *bite*. "Flipping one `pricing` label fails
  two tests" is evidence; "tests updated" is not.
- Tests are named by class where it helps the reviewer find them.

## Required trailer

Every commit ends with the Continue trailer, verbatim:

```
Generated with [Continue](https://continue.dev)

Co-Authored-By: Continue <noreply@continue.dev>
```

## Do not bypass the gates

The pre-commit hook (`.githooks/pre-commit`, wired up by
`git config core.hooksPath .githooks`) runs, in order:

1. `scripts/dev.py pycodestyle --staged` — PEP 8 on the **staged** files
   only, max line length 79.
2. `scripts/dev.py test` — `unittest` discovery over `src/` and `scripts/`.

There is no compiler in this project, so there is no compile database, no
`clang-tidy`, and no build step to run first. A fresh clone only needs
`uv sync --dev`.

Note that the hook's test step walks the **working tree**, not the index.
Splitting one logical change into several commits therefore runs tests on
code that is not in the commit being made. If that matters, `mv` the
not-yet-staged test files aside, commit, then `mv` them back — rather than
reaching for `--no-verify`.

`git commit --no-verify` is not part of this workflow. Use it only when the
user explicitly asks for it.

## What CI actually does

`.github/workflows/ci.yml` is the only workflow. It triggers on two events
only: `push` to `main`, and `pull_request` targeting `main`.

Whether a push to a feature branch runs CI therefore depends on whether a
pull request is already open for it. With a PR open, every push to the
branch re-runs both jobs (the runs show `event: pull_request` and
`headSha` = the branch tip). With no PR open, a `dev/*` push runs nothing:
open the pull request to get the checks. Do not assume a green local run
means CI has seen the commit — check with `gh run list --branch <branch>`.

**`build-and-test`** — the main gate:

1. `uv sync --dev`
2. **Verify the published pricing rules**, unstubbed. This step runs
   `pricing_doc.verify_published_rules()` for real and fails on two things:
   the documentation cannot be fetched at all, or the paragraph that
   `schedule` implements is gone or has been reworded. It exists because the
   unit tests stub the check to stay offline, which would otherwise leave the
   real call unexercised anywhere in CI.
3. `scripts/dev.py pycodestyle`
4. `scripts/dev.py test`

**`cli-without-tkinter`** — proves the CLI works where tkinter is absent,
by installing a `sys.meta_path` blocker that makes `import tkinter` raise.
It runs `--help` and `json --max-periods 2` and asserts each exits 0 with
non-empty stdout, then re-runs `json` and parses the output. Its `json` run
performs the rules check for real too, so this job also fails when the docs
are unreachable — intended, since that is the failure a user would see.

Because of that network step, a red CI run does not always mean the code
regressed. Read the failure before changing anything:

- `could not read https://api-docs.deepseek.com/...` means the fetch failed
  (site down, DNS, timeout). Nothing in this repository fixes that; re-run
  the job.
- `the pricing rules paragraph is missing from ...` means the page loaded
  and the text changed. That is a real finding: update `PRICING_RULES_TEXT`
  and `schedule.py` together, as the message says.

Locally, the same two checks are:

```bash
uv run python scripts/dev.py pycodestyle
uv run python scripts/dev.py test
```

and the network-dependent one, which the offline test suite does not cover:

```bash
uv run python -c \
  'from deepseek_pricing import pricing_doc; pricing_doc.verify_published_rules()'
```

## Full example

From this repository's own log (`2fe102e`), abridged in the middle to keep
the shape clear:

```bash
cat > /tmp/commit_msg.txt <<'EOF'
Evaluate peak hours in UTC and verify them against the docs

The DeepSeek pricing page states the peak windows in UTC:

    Off-peak rates are half of the peak rates. Peak hours are 01:00 -
    04:00 and 06:00 - 10:00 UTC, Monday through Friday, excluding
    Chinese public holidays. All other hours are off-peak, including
    weekends and Chinese public holidays in full.

`schedule` had been reading 01:00-04:00 and 06:00-10:00 as Beijing hours,
which made the real peak windows 17:00-20:00 and 22:00-02:00 UTC - eight
hours out from what the page says. That is now fixed in two halves.

The rules are evaluated in UTC. `is_peak` converts to UTC before testing
the hour, while the weekend/holiday exclusion still uses the Beijing date,
because "Chinese public holiday" is a Chinese calendar rule. The two
never disagree where it matters: the windows are 01:00-10:00 UTC, which
is 09:00-18:00 in Beijing on the same date. Periods default to
`now = datetime.now(tz=UTC)`, so the output carries `+00:00`.

The paragraph is also the only thing justifying the local schedule, so
`pricing_doc` fetches the page at startup and `main` refuses to run when
the text is gone or reworded. A silent drift between page and code is
exactly the failure worth catching; guessing a new rule is worse than
stopping. There is no override flag: the answer to "the docs changed" is
to read them, not to bypass the check.

Unit tests stub the check so they stay offline and deterministic, which
leaves the real call unexercised; CI therefore runs it unstubbed and
fails when the page is unreachable or the paragraph has changed.

Generated with [Continue](https://continue.dev)

Co-Authored-By: Continue <noreply@continue.dev>
EOF

git add -A
git commit -F /tmp/commit_msg.txt
rm /tmp/commit_msg.txt

# CI reacts to pull_request events targeting main, so it runs on this
# push only while a PR is open for the branch. Confirm with:
#   gh run list --branch dev/json --limit 3
git push origin dev/json
```

A quoted heredoc (`<<'EOF'`) keeps backticks, `$` and the quotation marks in
the quoted paragraph literal, which matters when the message is built with a
shell command. Writing the file with the Write tool avoids the heredoc
entirely.
