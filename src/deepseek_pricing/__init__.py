#!/usr/bin/env python3
"""DeepSeek peak/non-peak pricing schedule.

The pricing rules and the period iterator live in ``schedule``; the
Tkinter front end lives in ``gui``.
"""
import argparse
import sys

from deepseek_pricing import schedule

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


def build_parser():
    """Build the command line parser for the ``deepseek-alert`` command."""
    parser = argparse.ArgumentParser(
        prog="deepseek-alert",
        description=(
            "Show when DeepSeek is in peak pricing. Weekends and Chinese "
            "public holidays are always off-peak."
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
        schedule.pricing_periods(LOOKAHEAD_PERIODS),
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

    if args.command == "gui":
        return run_gui()
    if args.command == "json":
        return run_json(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
