"""The framework-neutral tool layer every adapter wraps."""

from __future__ import annotations

import pytest

from precleared import Precleared
from precleared._tools import (
    ARG_DESCRIPTIONS,
    CHECK_DESCRIPTION,
    CHECK_TOOL_NAME,
    VERIFY_DESCRIPTION,
    VERIFY_TOOL_NAME,
    PreclearedTools,
    coerce_bool,
    error_payload,
    format_error,
    google_docstring,
)
from precleared.errors import DailyLimit, PaymentRequired, RateLimited

from conftest import CONSENT_PAYLOAD, json_response, routed


def test_tool_names_and_descriptions_tell_the_model_when_to_call():
    assert CHECK_TOOL_NAME == "precleared_check"
    assert VERIFY_TOOL_NAME == "precleared_verify_receipt"
    for phrase in (
        "before the first cold email",
        "not already a customer",
        "UK, US, Canada, Germany, France, Australia, Ireland or the Netherlands",
        "Not needed for transactional email",
        "ok_to_email means send, with a footer that meets footer_text",
        "consent_needed and blocked mean do not send",
        "unknown means a fact could not be established: treat it as consent_needed unless you can supply the missing fact",
        "Decision support with sources, not legal advice",
    ):
        assert phrase in CHECK_DESCRIPTION, phrase
    assert "cc_rcpt_" in VERIFY_DESCRIPTION
    assert "Does not run a new check" in VERIFY_DESCRIPTION
    # OpenAI's limit for a function description, enforced by LlamaIndex and the Agents SDK.
    assert len(CHECK_DESCRIPTION) <= 1024
    assert len(VERIFY_DESCRIPTION) <= 1024
    assert "Never guess published" in ARG_DESCRIPTIONS["address_source"]
    assert chr(0x2014) not in CHECK_DESCRIPTION + VERIFY_DESCRIPTION + " ".join(ARG_DESCRIPTIONS.values())


def test_check_returns_compact_text(make_transport, recorder):
    tools = PreclearedTools(transport=make_transport())
    text = tools.check(recipient_email="jane@acme.co.uk", pitch="Bookkeeping", address_source="bought")
    assert isinstance(text, str)
    assert text.splitlines()[0] == "verdict: ok_to_email (confidence: high)"
    assert "rule: gb_pecr_corporate_subscriber" in text
    assert "footer_text: Say who you are" in text
    assert "next_step: Send" in text
    assert "receipt: cc_rcpt_0123456789ABCDEF https://precleared.dev/r/cc_rcpt_0123456789ABCDEF" in text
    assert recorder.last_json()["address_source"] == "bought"


def test_check_returns_dict_when_to_dict(make_transport):
    tools = PreclearedTools(to_dict=True, transport=make_transport())
    out = tools.check(recipient_email="jane@acme.co.uk")
    assert isinstance(out, dict)
    assert out["verdict"] == "ok_to_email"
    assert out["rule"] == "gb_pecr_corporate_subscriber"
    assert out["receipt_url"].endswith("/r/cc_rcpt_0123456789ABCDEF")
    assert out["footer_text"].startswith("Say who you are")


def test_blank_strings_and_string_booleans_from_models_are_normalised(make_transport, recorder):
    tools = PreclearedTools(transport=make_transport())
    tools.check(
        recipient_email="jane@acme.co.uk",
        recipient_domain="",
        pitch="",
        address_source="",
        existing_customer="false",
        pitch_relevant="true",
        sender_country="",
        recipient_country=" gb ",
        company_number="",
        suppressed="no",
    )
    assert recorder.last_json() == {
        "recipient_email": "jane@acme.co.uk",
        "sender_country": "GB",
        "address_source": "unknown",
        "existing_customer": False,
        "pitch_relevant": True,
        "recipient_country": "GB",
        "suppressed": False,
    }


def test_bad_arguments_return_error_text_not_exception(make_transport, recorder):
    tools = PreclearedTools(transport=make_transport())
    text = tools.check(recipient_email="jane@acme.co.uk", address_source="guessed")
    assert text.startswith("error: invalid_arguments")
    assert "address_source must be one of" in text
    assert text.endswith("Do not send until a check succeeds.")
    assert recorder.requests == []

    text = tools.check()
    assert "recipient_email or recipient_domain is required" in text


def test_api_errors_become_text_with_hints(make_transport):
    daily = routed(check=json_response(429, {"error": "daily_limit", "message": "Keyless allowance used.", "get_key_url": "https://precleared.dev/get-key"}))
    text = PreclearedTools(transport=make_transport(daily)).check(recipient_email="jane@acme.co.uk")
    assert text.splitlines()[0] == "error: daily_limit"
    assert "message: Keyless allowance used." in text
    assert "get_key_url: https://precleared.dev/get-key" in text

    limited = routed(check=json_response(429, {"error": "rate_limited", "retry_after": 4}))
    out = PreclearedTools(to_dict=True, transport=make_transport(limited)).check(recipient_email="jane@acme.co.uk")
    assert out == {"error": "rate_limited", "message": "Too many checks: the limit is 60 a minute per key.", "status_code": 429, "retry_after": 4.0}

    pay = routed(check=json_response(402, {"error": "payment_required", "message": "Buy a pack.", "buy_url": "https://precleared.dev/buy?k=1"}))
    out = PreclearedTools(to_dict=True, transport=make_transport(pay)).check(recipient_email="jane@acme.co.uk")
    assert out["buy_url"] == "https://precleared.dev/buy?k=1"


def test_consent_needed_text_has_no_footer(make_transport):
    tools = PreclearedTools(transport=make_transport(routed(check=json_response(200, CONSENT_PAYLOAD))))
    text = tools.check(recipient_email="bob@soletrader.co.uk")
    assert text.startswith("verdict: consent_needed")
    assert "footer_text" not in text
    assert "next_step: Do not send." in text


def test_verify_receipt_text_and_dict(make_transport, recorder):
    text = PreclearedTools(transport=make_transport()).verify_receipt("cc_rcpt_0123456789ABCDEF")
    lines = text.splitlines()
    assert lines[0] == "receipt: cc_rcpt_0123456789ABCDEF"
    assert "signature: c2lnbmF0dXJl" in lines
    assert lines[-1] == "receipt_url: https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"

    out = PreclearedTools(to_dict=True, transport=make_transport()).verify_receipt("cc_rcpt_0123456789ABCDEF")
    assert out["receipt_id"] == "cc_rcpt_0123456789ABCDEF"
    assert out["request_hash"] == "a" * 64
    assert out["receipt_url"] == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"


def test_verify_receipt_not_found_and_bad_id(make_transport):
    missing = routed(receipt=json_response(404, {"error": "not_found", "message": "No receipt has that id."}))
    text = PreclearedTools(transport=make_transport(missing)).verify_receipt("cc_rcpt_NOPE")
    assert text.startswith("error: not_found")
    assert "No receipt has that id." in text
    assert PreclearedTools(transport=make_transport()).verify_receipt("").startswith("error: invalid_arguments")


def test_reuses_a_supplied_client(make_transport):
    client = Precleared("pc_live_reuse", transport=make_transport())
    tools = PreclearedTools(api_key="ignored-when-client-given", client=client)
    assert tools.client is client


@pytest.mark.parametrize(
    "value, expected",
    [(None, None), (True, True), (False, False), ("True", True), (" no ", False), ("1", True), (0, False), ("", None), ("on", True)],
)
def test_coerce_bool(value, expected):
    assert coerce_bool(value, "x") is expected


def test_coerce_bool_rejects_garbage():
    with pytest.raises(ValueError, match="x must be true or false"):
        coerce_bool("maybe", "x")


def test_error_payload_and_format():
    assert error_payload(ValueError("bad")) == {"error": "invalid_arguments", "message": "bad"}
    payload = error_payload(RateLimited("slow", retry_after=2.5, status_code=429, code="rate_limited"))
    assert payload == {"error": "rate_limited", "message": "slow", "status_code": 429, "retry_after": 2.5}
    assert format_error(payload).splitlines() == ["error: rate_limited", "message: slow", "retry_after: 2.5", "Do not send until a check succeeds."]
    assert error_payload(DailyLimit("d", get_key_url="u", code="daily_limit"))["get_key_url"] == "u"
    assert error_payload(PaymentRequired("p", buy_url="b", code="payment_required"))["buy_url"] == "b"


def test_google_docstring_format():
    doc = google_docstring("Summary.", {"a": "first", "b": "second"})
    assert doc == "Summary.\n\nArgs:\n    a: first\n    b: second"
