#!/usr/bin/env python3
"""Write pricing periods as schema-conformant JSON.

The document produced here matches ``deepseek_pricing.schema.json``::

    {
      "version": 1,
      "periods": [
        {"startTime": ..., "endTime": ..., "pricing": "PEAK" | "NONPEAK"}
      ]
    }
"""
import json
import sys

from deepseek_pricing import schedule

DEFAULT_MAX_PERIODS = 5


def select_periods(periods, max_periods, max_peak_periods,
                   max_nonpeak_periods):
    """Collect periods from the iterator, stopping at the first limit.

    Iteration stops as soon as ``max_periods`` periods have been emitted
    or a peak/non-peak cap is reached, whichever happens first, so the
    generator is never walked past the point where a constraint is met.
    """
    iterator = iter(periods)
    selected = []
    peak_count = 0
    nonpeak_count = 0
    while True:
        if (len(selected) >= max_periods
                or peak_count >= max_peak_periods
                or nonpeak_count >= max_nonpeak_periods):
            break
        try:
            period = next(iterator)
        except StopIteration:
            break
        if period["pricing"] == schedule.PEAK:
            peak_count += 1
        else:
            nonpeak_count += 1
        selected.append(period)
    return selected


def format_pricing_json(periods, max_periods=DEFAULT_MAX_PERIODS,
                        max_peak_periods=None, max_nonpeak_periods=None):
    """Return the pricing periods document as formatted JSON text.

    ``max_peak_periods`` and ``max_nonpeak_periods`` default to
    ``max_periods`` when they are not given.
    """
    if max_peak_periods is None:
        max_peak_periods = max_periods
    if max_nonpeak_periods is None:
        max_nonpeak_periods = max_periods
    limits = (
        ("max_periods", max_periods),
        ("max_peak_periods", max_peak_periods),
        ("max_nonpeak_periods", max_nonpeak_periods),
    )
    for name, value in limits:
        if value < 0:
            raise ValueError(f"{name} must not be negative")

    document = {
        "version": schedule.SCHEMA_VERSION,
        "periods": select_periods(
            periods,
            max_periods,
            max_peak_periods,
            max_nonpeak_periods,
        ),
    }
    return json.dumps(document, indent=2)


def print_pricing_json(periods, max_periods=DEFAULT_MAX_PERIODS,
                       max_peak_periods=None, max_nonpeak_periods=None,
                       file=None):
    """Write the pricing periods document to a file handle.

    ``file`` defaults to ``sys.stdout``, following the same convention as
    the built-in ``print``. Pass any object with a ``write`` method, such
    as an open file or an ``io.StringIO``, to capture the output.
    """
    if file is None:
        file = sys.stdout
    text = format_pricing_json(
        periods,
        max_periods=max_periods,
        max_peak_periods=max_peak_periods,
        max_nonpeak_periods=max_nonpeak_periods,
    )
    print(text, file=file)
