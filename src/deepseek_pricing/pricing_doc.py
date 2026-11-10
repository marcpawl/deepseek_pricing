#!/usr/bin/env python3
"""Verify that the published pricing rules still say what we implement.

The schedule in :mod:`deepseek_pricing.schedule` is derived from one
paragraph of the DeepSeek API documentation. If that paragraph changes,
the local rules are no longer justified by anything, so it is checked at
startup and the command refuses to run when it no longer matches.

The check is deliberately strict about the wording: any change to the
paragraph is a change to the specification, which is exactly the moment
a human should look rather than a moment to guess.
"""
import urllib.error
import urllib.request

PRICING_DOC_URL = "https://api-docs.deepseek.com/quick_start/pricing"

# The paragraph the local rules implement. Peak hours are stated in UTC
# there, which is why `schedule` evaluates the rules in UTC too.
PRICING_RULES_TEXT = (
    "Off-peak rates are half of the peak rates. Peak hours are "
    "01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday, "
    "excluding Chinese public holidays. All other hours are off-peak, "
    "including weekends and Chinese public holidays in full."
)

# The page is a static HTML document, so the paragraph appears in the
# body verbatim. A short timeout keeps an unreachable host from hanging
# the GUI or the JSON command.
REQUEST_TIMEOUT = 10


class PricingDocError(RuntimeError):
    """The published pricing rules could not be confirmed."""


def fetch_pricing_page(url=PRICING_DOC_URL, timeout=REQUEST_TIMEOUT):
    """Return the pricing page body as text.

    Network and HTTP failures are reported as :class:`PricingDocError` so
    that callers have one exception to handle rather than the several
    that ``urllib`` raises.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise PricingDocError(
            f"could not read {url}: {error}"
        ) from error


def verify_pricing_doc(text):
    """Raise :class:`PricingDocError` if ``text`` lost the rules paragraph.

    ``text`` is the page body, which may carry HTML around the paragraph,
    so a plain substring test is enough and does not need an HTML parser.
    """
    if PRICING_RULES_TEXT in text:
        return
    raise PricingDocError(
        "the pricing rules paragraph is missing from "
        f"{PRICING_DOC_URL}. The published rules may have changed, so the "
        "local schedule in deepseek_pricing.schedule can no longer be "
        "trusted. Expected this text:\n\n"
        f"    {PRICING_RULES_TEXT}\n\n"
        "Check the page, then update PRICING_RULES_TEXT and schedule.py "
        "together."
    )


def verify_published_rules(url=PRICING_DOC_URL, timeout=REQUEST_TIMEOUT):
    """Fetch the pricing page and confirm the rules paragraph is intact."""
    verify_pricing_doc(fetch_pricing_page(url, timeout=timeout))
