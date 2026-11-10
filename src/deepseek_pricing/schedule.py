#!/usr/bin/env python3
"""Calculate DeepSeek peak and non-peak pricing periods.

Pricing rules, evaluated in Beijing time (UTC+8):

* Weekends and Chinese public holidays are always non-peak.
* On other days, 01:00-04:00 and 06:00-10:00 are peak; the rest is
  non-peak.

Periods are reported in UTC as ISO 8601 timestamps.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

SCHEMA_VERSION = 1
BEIJING = ZoneInfo("Asia/Shanghai")
PEAK = "PEAK"
NONPEAK = "NONPEAK"
# Peak hour ranges in Beijing time, as half-open [start, end) hours.
PEAK_HOURS = ((1, 4), (6, 10))
# Search horizon used when looking for the next scheduling boundary.
MAX_LOOK_AHEAD = timedelta(days=30)


def is_non_peak_day(beijing_date, holiday_calendar):
    """True if the Beijing date is a weekend or a Chinese holiday."""
    return (
        beijing_date.weekday() in (5, 6)
        or beijing_date in holiday_calendar
    )


def is_peak(ts):
    """True if an aware datetime falls inside a peak pricing window."""
    beijing_ts = ts.astimezone(BEIJING)
    calendar = holidays.China(years=beijing_ts.year)
    if is_non_peak_day(beijing_ts.date(), calendar):
        return False
    return any(
        start <= beijing_ts.hour < end for start, end in PEAK_HOURS
    )


def next_boundary(ts):
    """Return the next moment at which the pricing state changes."""
    beijing_ts = ts.astimezone(BEIJING)
    beijing_date = beijing_ts.date()
    candidates = []

    # Next Beijing midnight ends the current calendar day.
    candidates.append(
        datetime.combine(
            beijing_date + timedelta(days=1), time(0), tzinfo=BEIJING
        )
    )

    calendar = holidays.China(years=beijing_date.year)
    if not is_non_peak_day(beijing_date, calendar):
        for start, end in PEAK_HOURS:
            for hour in (start, end):
                candidate = datetime.combine(
                    beijing_date, time(hour), tzinfo=BEIJING
                )
                if candidate > beijing_ts:
                    candidates.append(candidate)

    return min(candidates).astimezone(ts.tzinfo)


def find_boundary(ts):
    """Return the next boundary, skipping any state that does not change."""
    state = is_peak(ts)
    boundary = next_boundary(ts)
    limit = ts + MAX_LOOK_AHEAD
    while is_peak(boundary) == state and boundary < limit:
        boundary = next_boundary(boundary)
    return boundary


def pricing_period(start, end):
    """Build a pricing period dictionary as described by the schema."""
    return {
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "pricing": PEAK if is_peak(start) else NONPEAK,
    }


def iter_pricing_periods(count, now):
    """Yield ``count`` pricing periods starting at ``now``."""
    start = now
    for _ in range(count):
        end = find_boundary(start)
        yield pricing_period(start, end)
        start = end


def pricing_periods(count=3, now=None):
    """Return an iterator of the current and following pricing periods.

    The current period starts at ``now`` and each subsequent period starts
    where the previous one ends, so the periods alternate between PEAK and
    NONPEAK. Each yielded item follows the ``PricingPeriod`` definition in
    ``deepseek_pricing.schema.json``.

    The arguments are validated immediately, so invalid input raises
    ``ValueError`` here rather than on the first ``next()`` call.
    """
    if count < 0:
        raise ValueError("count must not be negative")

    if now is None:
        now = datetime.now(tz=BEIJING)
    elif now.tzinfo is None:
        raise ValueError("now must be timezone aware")

    return iter_pricing_periods(count, now)
