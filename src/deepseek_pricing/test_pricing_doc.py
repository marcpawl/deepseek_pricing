#!/usr/bin/env python3
"""Unit tests for deepseek_pricing.pricing_doc.

The real check fetches the DeepSeek documentation, so most of these tests
call :func:`verify_pricing_doc` directly with a page body they control.
That covers the interesting behaviour - present, missing, and the shape
of the complaint - without depending on the network.
"""
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deepseek_pricing import pricing_doc  # noqa: E402


class VerifyPricingDocTests(unittest.TestCase):

    def test_the_expected_paragraph_is_present(self):
        page = f"<html><body><p>{pricing_doc.PRICING_RULES_TEXT}</p></body>"
        # A page that contains the paragraph verifies without raising.
        self.assertIsNone(pricing_doc.verify_pricing_doc(page))

    def test_the_bare_paragraph_is_present(self):
        self.assertIsNone(
            pricing_doc.verify_pricing_doc(pricing_doc.PRICING_RULES_TEXT)
        )

    def test_a_missing_paragraph_is_rejected(self):
        with self.assertRaises(pricing_doc.PricingDocError):
            pricing_doc.verify_pricing_doc("<html><body>Nothing here</body>")

    def test_altered_wording_is_rejected(self):
        # A changed specification is exactly what must not pass silently,
        # so even a near-miss is a failure.
        altered = pricing_doc.PRICING_RULES_TEXT.replace("half", "a third")
        with self.assertRaises(pricing_doc.PricingDocError):
            pricing_doc.verify_pricing_doc(altered)

    def test_reworded_hours_are_rejected(self):
        altered = pricing_doc.PRICING_RULES_TEXT.replace(
            "01:00 - 04:00 and 06:00 - 10:00", "02:00 - 05:00"
        )
        with self.assertRaises(pricing_doc.PricingDocError):
            pricing_doc.verify_pricing_doc(altered)

    def test_the_error_names_the_url(self):
        with self.assertRaises(pricing_doc.PricingDocError) as caught:
            pricing_doc.verify_pricing_doc("")
        self.assertIn(pricing_doc.PRICING_DOC_URL, str(caught.exception))

    def test_the_error_quotes_the_expected_text(self):
        # The message has to say what was looked for, or the reader cannot
        # tell whether the page or the local copy is the one that changed.
        with self.assertRaises(pricing_doc.PricingDocError) as caught:
            pricing_doc.verify_pricing_doc("")
        self.assertIn(pricing_doc.PRICING_RULES_TEXT, str(caught.exception))

    def test_the_error_points_at_the_file_to_update(self):
        with self.assertRaises(pricing_doc.PricingDocError) as caught:
            pricing_doc.verify_pricing_doc("")
        self.assertIn("schedule.py", str(caught.exception))


class FetchPricingPageTests(unittest.TestCase):
    """The network seams are replaced, so these tests stay offline."""

    def fake_response(self, body, charset="utf-8"):
        response = mock.MagicMock()
        response.read.return_value = body
        response.headers.get_content_charset.return_value = charset
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_the_page_body_is_returned(self):
        response = self.fake_response(b"<p>hello</p>")
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response):
            self.assertEqual(pricing_doc.fetch_pricing_page(), "<p>hello</p>")

    def test_the_documented_url_is_requested(self):
        response = self.fake_response(b"body")
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response) as urlopen:
            pricing_doc.fetch_pricing_page()
        self.assertEqual(urlopen.call_args[0][0],
                         pricing_doc.PRICING_DOC_URL)

    def test_the_configured_timeout_is_used(self):
        response = self.fake_response(b"body")
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response) as urlopen:
            pricing_doc.fetch_pricing_page()
        self.assertEqual(urlopen.call_args[1]["timeout"],
                         pricing_doc.REQUEST_TIMEOUT)

    def test_the_declared_charset_is_honoured(self):
        response = self.fake_response("café".encode("latin-1"),
                                      charset="latin-1")
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response):
            self.assertEqual(pricing_doc.fetch_pricing_page(), "café")

    def test_a_url_error_becomes_a_pricing_doc_error(self):
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("down")):
            with self.assertRaises(pricing_doc.PricingDocError) as caught:
                pricing_doc.fetch_pricing_page()
        self.assertIn(pricing_doc.PRICING_DOC_URL, str(caught.exception))

    def test_a_timeout_becomes_a_pricing_doc_error(self):
        # A socket timeout surfaces as OSError, not URLError.
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               side_effect=OSError("timed out")):
            with self.assertRaises(pricing_doc.PricingDocError):
                pricing_doc.fetch_pricing_page()

    def test_an_undecodable_charset_becomes_a_pricing_doc_error(self):
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               side_effect=ValueError("bad charset")):
            with self.assertRaises(pricing_doc.PricingDocError):
                pricing_doc.fetch_pricing_page()

    def test_a_missing_charset_falls_back_to_utf8(self):
        # A server that omits the charset must not stop the check.
        response = self.fake_response("café".encode("utf-8"), charset=None)
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response):
            self.assertEqual(pricing_doc.fetch_pricing_page(), "café")

    def test_undecodable_bytes_do_not_abort_the_check(self):
        # The paragraph is ASCII, so a stray byte elsewhere on the page
        # should be replaced rather than raise.
        response = self.fake_response(b"\xff<p>page</p>")
        with mock.patch.object(pricing_doc.urllib.request, "urlopen",
                               return_value=response):
            self.assertIn("<p>page</p>", pricing_doc.fetch_pricing_page())


class VerifyPublishedRulesTests(unittest.TestCase):

    def test_it_verifies_the_fetched_page(self):
        page = f"<p>{pricing_doc.PRICING_RULES_TEXT}</p>"
        with mock.patch.object(pricing_doc, "fetch_pricing_page",
                               return_value=page):
            self.assertIsNone(pricing_doc.verify_published_rules())

    def test_it_rejects_a_page_without_the_paragraph(self):
        with mock.patch.object(pricing_doc, "fetch_pricing_page",
                               return_value="<p>moved on</p>"):
            with self.assertRaises(pricing_doc.PricingDocError):
                pricing_doc.verify_published_rules()

    def test_a_fetch_failure_propagates(self):
        with mock.patch.object(pricing_doc, "fetch_pricing_page",
                               side_effect=pricing_doc.PricingDocError("no")):
            with self.assertRaises(pricing_doc.PricingDocError):
                pricing_doc.verify_published_rules()


class ParagraphConstantTests(unittest.TestCase):
    """Guard the constant itself against a careless edit.

    The schedule implements 01:00-04:00 and 06:00-10:00 UTC. If the
    constant drifts from that, the check would compare the page against
    something the code no longer does.
    """

    def test_it_states_the_hours_the_schedule_implements(self):
        from deepseek_pricing import schedule

        for start, end in schedule.PEAK_HOURS:
            expected = f"{start:02d}:00 - {end:02d}:00"
            self.assertIn(expected, pricing_doc.PRICING_RULES_TEXT)

    def test_it_says_the_hours_are_utc(self):
        self.assertIn("UTC", pricing_doc.PRICING_RULES_TEXT)

    def test_it_names_the_chinese_holiday_exclusions(self):
        self.assertIn("Chinese public holidays",
                      pricing_doc.PRICING_RULES_TEXT)


if __name__ == "__main__":
    unittest.main()
