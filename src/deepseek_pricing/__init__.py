#!/usr/bin/env python3
"""DeepSeek peak/non-peak pricing schedule.

The pricing rules and the period iterator live in ``schedule``; the
Tkinter front end lives in ``gui``.
"""
import argparse
import sys
from datetime import datetime

from deepseek_pricing import pricing_doc, schedule

# How far the JSON output may walk the iterator. The period limits decide
# what is actually emitted; this only bounds the search so a large
# ``--max-periods`` still terminates.
LOOKAHEAD_PERIODS = 30


def non_negative_int(value):
    """argparse type for a period limit, rejecting negatives.

    Without this the limits are only validated deep inside
    ``pricing_json.format_pricing_json``, so ``--max-periods -1`` escapes
    argparse and dies with a ``ValueError`` traceback and exit status 1.
    Raising ``ArgumentTypeError`` instead keeps it a usage error, printed
    as one line on stderr with exit status 2, like any other bad option.
    """
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid int value: {value!r}"
        ) from None
    if number < 0:
        raise argparse.ArgumentTypeError(
            f"must not be negative: {value!r}"
        )
    return number


def iso8601_with_offset(value):
    """argparse type for an ISO 8601 timestamp that has a UTC offset.

    The offset is required rather than optional. ``datetime.fromisoformat``
    happily parses ``2026-11-10T23:15`` and ``2026-11-10`` into naive
    datetimes, and those are the values that ``pricing_periods`` rejects
    with ``now must be timezone aware``. Accepting them here would only
    move that failure from a one line usage error to a traceback, so a
    missing offset is treated as the malformed input it is.

    ``Z`` is accepted: it is the ISO 8601 designator for UTC, and
    ``fromisoformat`` turns it into a UTC ``tzinfo``.

    The result is converted to UTC. The peak hours are published in UTC,
    so the output is always reported in UTC; accepting ``+08:00`` here
    means "this instant", not "report in +08:00".
    """
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid ISO 8601 timestamp: {value!r}"
        ) from None
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError(
            f"timestamp needs a UTC offset, like +08:00 or Z: {value!r}"
        )
    return timestamp.astimezone(schedule.UTC)


def build_parser():
    """Build the command line parser for the ``deepseek-alert`` command."""
    parser = argparse.ArgumentParser(
        prog="deepseek-alert",
        description=(
            "Show when DeepSeek is in peak pricing. Peak hours are "
            "01:00-04:00 and 06:00-10:00 UTC; weekends and Chinese public "
            "holidays are always off-peak."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="{json,gui}",
    )

    json_parser = subparsers.add_parser(
        "json",
        help="print the next pricing periods as JSON",
        description="Print the next pricing periods as JSON.",
    )
    json_parser.add_argument(
        "--start-at",
        type=iso8601_with_offset,
        default=None,
        metavar="TIMESTAMP",
        help=(
            "start at this ISO 8601 timestamp with a UTC offset instead of "
            "now (default: now)"
        ),
    )
    json_parser.add_argument(
        "--max-periods",
        type=non_negative_int,
        default=None,
        metavar="N",
        help="emit at most N periods (default: 5)",
    )
    json_parser.add_argument(
        "--max-peak-periods",
        type=non_negative_int,
        default=None,
        metavar="N",
        help="stop after N peak periods (default: --max-periods)",
    )
    json_parser.add_argument(
        "--max-nonpeak-periods",
        type=non_negative_int,
        default=None,
        metavar="N",
        help="stop after N non-peak periods (default: --max-periods)",
    )

    subparsers.add_parser(
        "gui",
        help="run the full screen monitor window",
        description="Run the full screen monitor window.",
    )
    return parser


def verify_published_rules(error_file=None):
    """Confirm the published pricing rules still match ``schedule``.

    This runs before either command does any work: the local schedule is
    only meaningful while the documentation still states the rule it was
    built from. ``--help`` and a bare invocation skip it, so reading the
    usage text never depends on the network.

    Returns 0 when the rules are confirmed and 1 when they are not, with
    the reason printed rather than raised - a traceback would bury the
    one line that tells the user what to do.
    """
    if error_file is None:
        error_file = sys.stderr
    try:
        pricing_doc.verify_published_rules()
    except pricing_doc.PricingDocError as error:
        print(f"deepseek-alert: {error}", file=error_file)
        return 1
    return 0


def run_gui():
    """Start the monitor window.

    ``gui`` is imported here rather than at module scope so that the
    ``json`` command and ``--help`` do not require tkinter.
    """
    from deepseek_pricing import gui

    gui.main()
    return 0


def run_json(args, file=None):
    """Print the pricing periods document described by the JSON schema."""
    from pricing_json import DEFAULT_MAX_PERIODS, print_pricing_json

    max_periods = args.max_periods
    if max_periods is None:
        max_periods = DEFAULT_MAX_PERIODS
    print_pricing_json(
        schedule.pricing_periods(LOOKAHEAD_PERIODS, args.start_at),
        max_periods=max_periods,
        max_peak_periods=args.max_peak_periods,
        max_nonpeak_periods=args.max_nonpeak_periods,
        file=file,
    )
    return 0


def main(argv=None):
    """Run the command line interface and return an exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    status = verify_published_rules()
    if status:
        return status

    if args.command == "gui":
        return run_gui()
    return run_json(args)


if __name__ == "__main__":
    sys.exit(main())
