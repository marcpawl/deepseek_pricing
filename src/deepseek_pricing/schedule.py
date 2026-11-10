#!/usr/bin/env python3
"""Calculate DeepSeek peak and non-peak pricing periods.

Pricing rules, as published in the DeepSeek API documentation and
verified at startup by :mod:`deepseek_pricing.pricing_doc`:

* Weekends and Chinese public holidays are always non-peak.
* On other days, 01:00-04:00 and 06:00-10:00 **UTC** are peak; the rest
  is non-peak.

The hours are UTC hours, not Beijing hours: the documentation states
them in UTC, so a UTC timestamp is what the rule is evaluated against.
Chinese public holidays are still taken from the Chinese calendar, which
is why the weekend/holiday test needs the Beijing date of the instant
rather than the UTC one - those can differ by a day near midnight.

Periods are reported as ISO 8601 timestamps in the timezone of ``now``.
That is UTC (``+00:00``) by default, matching the units of the published
rule; pass an aware datetime in another timezone to get the periods
expressed in that timezone instead. Each timestamp keeps a UTC offset, so
the instants are unambiguous wherever they are compared.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

SCHEMA_VERSION = 1
BEIJING = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")
PEAK = "PEAK"
NONPEAK = "NONPEAK"
# Peak hour ranges in UTC, as half-open [start, end) hours.
PEAK_HOURS = ((1, 4), (6, 10))
# Search horizon used when looking for the next scheduling boundary.
MAX_LOOK_AHEAD = timedelta(days=30)


def is_non_peak_day(calendar_date, holiday_calendar):
    """True if the date is a weekend or a Chinese public holiday.

    The exclusion is a Chinese calendar rule, so the date passed in is
    the Beijing date of the instant. That is also the UTC date for every
    instant that can be peak: the windows are 01:00-10:00 UTC, which is
    09:00-18:00 in Beijing on the same date, so the two never disagree
    where it matters.
    """
    return (
        calendar_date.weekday() in (5, 6)
        or calendar_date in holiday_calendar
    )


def is_peak(ts):
    """True if an aware datetime falls inside a peak pricing window."""
    utc_ts = ts.astimezone(UTC)
    beijing_date = utc_ts.astimezone(BEIJING).date()
    calendar = holidays.China(years=beijing_date.year)
    if is_non_peak_day(beijing_date, calendar):
        return False
    return any(
        start <= utc_ts.hour < end for start, end in PEAK_HOURS
    )


def next_boundary(ts):
    """Return the next moment at which the pricing state changes."""
    utc_ts = ts.astimezone(UTC)
    beijing_date = utc_ts.astimezone(BEIJING).date()
    calendar = holidays.China(years=beijing_date.year)
    candidates = []

    # On a weekday, the window edges left on this UTC date are candidates.
    utc_date = utc_ts.date()
    if not is_non_peak_day(beijing_date, calendar):
        for start, end in PEAK_HOURS:
            for hour in (start, end):
                candidate = datetime.combine(
                    utc_date, time(hour), tzinfo=UTC
                )
                if candidate > utc_ts:
                    candidates.append(candidate)

    # The next UTC midnight is always a candidate: the calendar date
    # changes, and with it the weekday or the holiday set. It also covers
    # the following day's edges, because ``find_boundary`` asks again from
    # the midnight it lands on - an instant after 10:00 UTC is therefore
    # followed by midnight, not by the next day's 01:00 edge directly.
    candidates.append(
        datetime.combine(utc_date + timedelta(days=1), time(0), tzinfo=UTC)
    )

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

    ``now`` defaults to the current UTC time, so the timestamps are
    reported with a ``+00:00`` offset - the same units the published peak
    hours are stated in. Pass an aware datetime in another timezone to
    get the periods expressed in that timezone instead.

    The arguments are validated immediately, so invalid input raises
    ``ValueError`` here rather than on the first ``next()`` call.
    """
    if count < 0:
        raise ValueError("count must not be negative")

    if now is None:
        now = datetime.now(tz=UTC)
    elif now.tzinfo is None:
        raise ValueError("now must be timezone aware")

    return iter_pricing_periods(count, now)
