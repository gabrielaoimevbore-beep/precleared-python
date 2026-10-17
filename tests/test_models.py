"""Model parsing, convenience properties, summaries and Retry-After parsing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from precleared import CheckResult, Health, Reason, Receipt, Usage
from precleared.client import normalise_receipt_id, parse_retry_after

from conftest import CONSENT_PAYLOAD, OK_PAYLOAD, UNKNOWN_PAYLOAD


# -- parse_retry_after ---------------------------------------------------------


@pytest.mark.parametrize(
    "body, header, expected",
    [
        (12, None, 12.0),
        (0.5, None, 0.5),
        ("30", None, 30.0),
        (None, "7", 7.0),
        (None, " 7 ", 7.0),
        (None, "0", 0.0),
        (None, "-5", 0.0),
        (-3, None, 0.0),
        (None, None, None),
        (None, "", None),
        (None, "soon", None),
        ("soon", "9", 9.0),
        (True, "9", 9.0),
        (12, "99", 12.0),
    ],
)
def test_parse_retry_after_numbers_and_fallbacks(body, header, expected):
    assert parse_retry_after(body, header) == expected


def test_parse_retry_after_http_date_in_future():
    when = datetime.now(timezone.utc) + timedelta(seconds=120)
    seconds = parse_retry_after(None, format_datetime(when, usegmt=True))
    assert 110 <= seconds <= 121


def test_parse_retry_after_http_date_in_past_is_zero():
    when = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert parse_retry_after(None, format_datetime(when, usegmt=True)) == 0.0


# -- receipt ids ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("cc_rcpt_ABC123", "cc_rcpt_ABC123"),
        ("  cc_rcpt_ABC123\n", "cc_rcpt_ABC123"),
        ("https://precleared.dev/r/cc_rcpt_ABC123", "cc_rcpt_ABC123"),
        ("https://precleared.dev/api/v1/receipt?id=cc_rcpt_ABC123", "cc_rcpt_ABC123"),
        ("legacy_id_without_prefix", "legacy_id_without_prefix"),
    ],
)
def test_normalise_receipt_id(value, expected):
    assert normalise_receipt_id(value) == expected


@pytest.mark.parametrize("value", ["", "  ", None, 42, "https://example.com/x", "two words"])
def test_normalise_receipt_id_rejects(value):
    with pytest.raises(ValueError):
        normalise_receipt_id(value)


# -- Reason --------------------------------------------------------------------


def test_reason_from_string_and_odd_shapes():
    assert Reason.from_dict("just a note").note == "just a note"
    assert Reason.from_dict(42).raw == {}
    reason = Reason.from_dict({"rule_key": "r", "text": "t", "source_title": "s", "source_url": "u", "extra": 1})
    assert reason.raw["extra"] == 1


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"text": "T", "source_title": "S", "source_url": "U"}, "T Source: S, U"),
        ({"text": "T", "source_url": "U"}, "T Source: U"),
        ({"text": "T", "source_title": "S"}, "T Source: S"),
        ({"note": "N"}, "N"),
        ({}, ""),
    ],
)
def test_reason_describe(data, expected):
    assert Reason.from_dict(data).describe() == expected


# -- Receipt and Usage ---------------------------------------------------------


def test_receipt_requires_id():
    with pytest.raises(ValueError, match="no id"):
        Receipt.from_dict({"signature": "x"})
    with pytest.raises(TypeError):
        Receipt.from_dict(["not", "a", "dict"])


def test_receipt_accepts_receipt_id_alias_and_summaries():
    receipt = Receipt.from_dict({"receipt_id": "cc_rcpt_X", "signature": "s", "key_version": "v2"})
    assert receipt.id == "cc_rcpt_X"
    assert receipt.summary() == {"receipt_id": "cc_rcpt_X", "signature": "s", "key_version": "v2"}
    assert receipt.summary_text() == "receipt: cc_rcpt_X\nsignature: s\nkey_version: v2"
    assert receipt.page_url("https://example.test/") == "https://example.test/r/cc_rcpt_X"


def test_usage_parsing_tolerates_bad_values():
    usage = Usage.from_dict({"free_remaining_today": "9", "credits_remaining": None, "low_balance": 1, "top_up_url": "https://x", "notice": "n"})
    assert usage.free_remaining_today == 9
    assert usage.credits_remaining is None
    assert usage.low_balance is True
    assert usage.top_up_url == "https://x"
    assert Usage.from_dict("nonsense").raw == {}
    assert Usage.from_dict({"free_remaining_today": "lots"}).free_remaining_today is None


def test_health_defaults():
    health = Health.from_dict({})
    assert health.status == "unknown"
    assert health.ok is False
    with pytest.raises(TypeError):
        Health.from_dict([])


# -- CheckResult ---------------------------------------------------------------


def test_check_result_requires_object_with_verdict():
    with pytest.raises(TypeError):
        CheckResult.from_dict(["nope"])
    with pytest.raises(ValueError):
        CheckResult.from_dict({"verdict": ""})


def test_check_result_tolerates_missing_sections():
    result = CheckResult.from_dict({"verdict": "blocked"})
    assert result.must_not_send is True
    assert result.reasons == []
    assert result.rules_applied == []
    assert result.facts == {}
    assert result.receipt is None
    assert result.receipt_id is None
    assert result.receipt_url is None
    assert result.usage is None
    assert result.rule is None
    assert result.reason is None
    assert result.summary_text() == "verdict: blocked"


def test_check_result_ignores_receipt_without_id():
    result = CheckResult.from_dict({"verdict": "ok_to_email", "receipt": {"signature": "x"}})
    assert result.receipt is None


def test_check_result_reasons_as_strings():
    result = CheckResult.from_dict({"verdict": "unknown", "reasons": ["Could not reach the register."]})
    assert result.notes == ["Could not reach the register."]
    assert result.reason is None
    assert result.summary()["reason"] is None
    assert result.summary()["notes"] == ["Could not reach the register."]


def test_notes_fall_back_to_text_when_entry_has_no_rule():
    result = CheckResult.from_dict({"verdict": "unknown", "reasons": [{"text": "Website unreachable."}]})
    assert result.notes == ["Website unreachable."]
    assert result.rule is None


def test_summary_dict_ok():
    summary = CheckResult.from_dict(OK_PAYLOAD).summary()
    assert summary["verdict"] == "ok_to_email"
    assert summary["confidence"] == "high"
    assert summary["rule"] == "gb_pecr_corporate_subscriber"
    assert summary["reason"].startswith("Corporate subscribers")
    assert summary["source_url"].startswith("https://ico.org.uk/")
    assert summary["notes"] == ["Legal form came from the Companies House register."]
    assert summary["footer_text"] == OK_PAYLOAD["footer_text"]
    assert summary["next_step"] == OK_PAYLOAD["next_step"]
    assert summary["receipt_id"] == "cc_rcpt_0123456789ABCDEF"
    assert summary["receipt_url"] == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"
    assert summary["free_remaining_today"] == 9
    assert summary["credits_remaining"] == 0
    assert summary["disclaimer"] == "Decision support with sources, not legal advice."


def test_summary_text_ok_is_compact_and_complete():
    text = CheckResult.from_dict(OK_PAYLOAD).summary_text()
    lines = text.splitlines()
    assert lines[0] == "verdict: ok_to_email (confidence: high)"
    assert lines[1] == "rule: gb_pecr_corporate_subscriber"
    assert lines[2].startswith("reason: Corporate subscribers") and "Source: ICO guidance" in lines[2]
    assert lines[3] == "note: Legal form came from the Companies House register."
    assert lines[4] == f"footer_text: {OK_PAYLOAD['footer_text']}"
    assert lines[5] == f"next_step: {OK_PAYLOAD['next_step']}"
    assert lines[6] == "receipt: cc_rcpt_0123456789ABCDEF https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"
    assert len(lines) == 7
    # The text never carries the whole facts block or the raw JSON.
    assert "legal_form_source" not in text
    assert "{" not in text


def test_summary_text_consent_needed_has_no_footer_line():
    text = CheckResult.from_dict(CONSENT_PAYLOAD).summary_text()
    assert "footer_text" not in text
    assert "next_step: Do not send." in text
    assert text.startswith("verdict: consent_needed (confidence: medium)")


def test_summary_text_unknown_shows_note_once():
    text = CheckResult.from_dict(UNKNOWN_PAYLOAD).summary_text()
    assert "rule:" not in text
    assert "reason:" not in text
    assert text.count("Companies House could not be searched") == 1
    assert "note: Companies House could not be searched" in text
    assert "next_step: Treat as consent_needed" in text
