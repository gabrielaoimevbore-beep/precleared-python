"""Synchronous client: request building, response mapping and error classes."""

from __future__ import annotations

import httpx
import pytest

import precleared
from precleared import (
    CheckResult,
    DailyLimit,
    InvalidKey,
    InvalidRequest,
    NetworkError,
    PaymentRequired,
    Precleared,
    PreclearedError,
    RateLimited,
    Receipt,
    ReceiptNotFound,
    ServerError,
)
from precleared.client import DEFAULT_USER_AGENT

from conftest import (
    CONSENT_PAYLOAD,
    HEALTH_PAYLOAD,
    OK_PAYLOAD,
    RECEIPT_PAYLOAD,
    UNKNOWN_PAYLOAD,
    json_response,
    routed,
)

KEY = "pc_live_0123456789abcdef0123456789abcdef"


# -- success path ------------------------------------------------------------


def test_check_maps_success_response(make_client, recorder):
    client = make_client()
    result = client.check("jane@acme.co.uk", pitch="Bookkeeping software", address_source="unknown")

    assert isinstance(result, CheckResult)
    assert result.verdict == "ok_to_email"
    assert result.confidence == "high"
    assert result.ok is True
    assert result.must_not_send is False
    assert result.needs_more_facts is False
    assert result.rule == "gb_pecr_corporate_subscriber"
    assert result.rules_applied == ["gb_pecr_corporate_subscriber"]
    assert result.footer_text == OK_PAYLOAD["footer_text"]
    assert result.next_step == OK_PAYLOAD["next_step"]
    assert result.facts["legal_form"] == "limited_company"
    assert result.disclaimer == "Decision support with sources, not legal advice."
    assert result.rules_version == "2026-10-01"
    assert result.raw == OK_PAYLOAD

    assert len(result.reasons) == 2
    first, note = result.reasons
    assert first.rule_key == "gb_pecr_corporate_subscriber"
    assert first.source_title.startswith("ICO guidance")
    assert first.source_url.startswith("https://ico.org.uk/")
    assert note.rule_key is None and note.note.startswith("Legal form")
    assert result.notes == [note.note]

    assert isinstance(result.receipt, Receipt)
    assert result.receipt.id == "cc_rcpt_0123456789ABCDEF"
    assert result.receipt.signature == "c2lnbmF0dXJl"
    assert result.receipt.algorithm == "ed25519"
    assert result.receipt_id == "cc_rcpt_0123456789ABCDEF"
    assert result.receipt_url == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"

    assert result.usage.free_remaining_today == 9
    assert result.usage.credits_remaining == 0
    assert result.usage.low_balance is None


def test_check_sends_expected_body_and_headers_keyless(make_client, recorder):
    client = make_client()
    client.check("jane@acme.co.uk", pitch="  Bookkeeping software  ")

    request = recorder.last
    assert request.method == "POST"
    assert str(request.url) == "https://precleared.dev/api/v1/check"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["user-agent"] == "precleared-python/0.1.1" == DEFAULT_USER_AGENT
    assert request.headers["accept"] == "application/json"
    assert "authorization" not in request.headers

    body = recorder.last_json()
    assert body == {
        "recipient_email": "jane@acme.co.uk",
        "sender_country": "GB",
        "address_source": "unknown",
        "existing_customer": False,
        "pitch": "Bookkeeping software",
    }


def test_address_source_is_always_sent_and_defaults_to_unknown(make_client, recorder):
    """address_source changes verdicts, so the client always sends it and never assumes published."""
    make_client().check("jane@acme.co.uk")
    assert recorder.last_json()["address_source"] == "unknown"


def test_check_with_key_sends_bearer_header(make_client, recorder):
    make_client(api_key=KEY).check("jane@acme.co.uk")
    assert recorder.last.headers["authorization"] == f"Bearer {KEY}"


def test_key_is_read_from_environment(monkeypatch, make_transport, recorder):
    monkeypatch.setenv("PRECLEARED_API_KEY", f"  {KEY}  ")
    client = Precleared(transport=make_transport())
    assert client.has_api_key is True
    client.check("jane@acme.co.uk")
    assert recorder.last.headers["authorization"] == f"Bearer {KEY}"


def test_blank_key_means_keyless(make_transport, recorder):
    client = Precleared("   ", transport=make_transport())
    assert client.has_api_key is False
    client.check("jane@acme.co.uk")
    assert "authorization" not in recorder.last.headers


def test_check_all_optional_fields(make_client, recorder):
    make_client().check(
        recipient_domain="acme.co.uk",
        pitch="Bookkeeping",
        address_source="Published",
        sender_country="us",
        existing_customer=True,
        pitch_relevant=True,
        company_number=1234567,
        recipient_country="gb",
        default_recipient_country="ie",
        suppressed=False,
    )
    assert recorder.last_json() == {
        "recipient_domain": "acme.co.uk",
        "sender_country": "US",
        "address_source": "published",
        "existing_customer": True,
        "pitch": "Bookkeeping",
        "pitch_relevant": True,
        "company_number": "1234567",
        "recipient_country": "GB",
        "default_recipient_country": "IE",
        "suppressed": False,
    }


def test_none_fields_are_omitted(make_client, recorder):
    make_client().check(
        "jane@acme.co.uk",
        pitch=None,
        pitch_relevant=None,
        company_number=None,
        recipient_country=None,
        default_recipient_country=None,
        suppressed=None,
    )
    body = recorder.last_json()
    for key in ("pitch", "pitch_relevant", "company_number", "recipient_country", "default_recipient_country", "suppressed"):
        assert key not in body


def test_extra_fields_are_forwarded(make_client, recorder):
    make_client().check("jane@acme.co.uk", campaign_id="spring-26", address_source="given")
    body = recorder.last_json()
    assert body["campaign_id"] == "spring-26"
    assert body["address_source"] == "given"


def test_consent_needed_and_blocked_must_not_send(make_client):
    result = make_client(routed(check=json_response(200, CONSENT_PAYLOAD))).check("bob@soletrader.co.uk")
    assert result.verdict == "consent_needed"
    assert result.ok is False
    assert result.must_not_send is True
    assert result.footer_text is None
    assert result.rule == "gb_pecr_individual_subscriber"

    blocked = dict(CONSENT_PAYLOAD, verdict="blocked")
    result = make_client(routed(check=json_response(200, blocked))).check("bob@soletrader.co.uk")
    assert result.must_not_send is True


def test_unknown_verdict_is_flagged_not_treated_as_blocked(make_client):
    result = make_client(routed(check=json_response(200, UNKNOWN_PAYLOAD))).check("x@acme.co.uk")
    assert result.verdict == "unknown"
    assert result.ok is False
    assert result.must_not_send is False
    assert result.needs_more_facts is True
    assert result.rule is None
    assert result.notes[0].startswith("Companies House could not be searched")


def test_custom_base_url_changes_receipt_url(make_client):
    result = make_client(base_url="https://staging.example.test/").check("jane@acme.co.uk")
    assert result.receipt_url == "https://staging.example.test/r/cc_rcpt_0123456789ABCDEF"


# -- client-side validation ----------------------------------------------------


@pytest.mark.parametrize("bad", ["guessed", "public", "", "published ", None, 3])
def test_address_source_validation(make_client, recorder, bad):
    client = make_client()
    if bad == "published ":
        # Whitespace and case are forgiven; only genuinely unknown values fail.
        client.check("jane@acme.co.uk", address_source=bad)
        assert recorder.last_json()["address_source"] == "published"
        return
    with pytest.raises(ValueError, match="address_source must be one of published, bought, scraped, given, unknown"):
        client.check("jane@acme.co.uk", address_source=bad)
    assert recorder.requests == []


def test_missing_recipient_raises_before_any_request(make_client, recorder):
    with pytest.raises(ValueError, match="recipient_email or recipient_domain is required"):
        make_client().check()
    with pytest.raises(ValueError):
        make_client().check("   ", recipient_domain="")
    assert recorder.requests == []


@pytest.mark.parametrize("field", ["sender_country", "recipient_country", "default_recipient_country"])
@pytest.mark.parametrize("bad", ["GBR", "G", "", "U K", 44])
def test_country_code_validation(make_client, field, bad):
    with pytest.raises(ValueError, match=f"{field} must be a two-letter country code"):
        make_client().check("jane@acme.co.uk", **{field: bad})


@pytest.mark.parametrize("field", ["existing_customer", "pitch_relevant", "suppressed"])
def test_bool_fields_must_be_bool(make_client, field):
    with pytest.raises(ValueError, match=f"{field} must be True or False"):
        make_client().check("jane@acme.co.uk", **{field: "yes"})


def test_bad_base_url_rejected():
    with pytest.raises(ValueError, match="base_url"):
        Precleared(base_url="precleared.dev")


# -- error classes -------------------------------------------------------------


def test_400_invalid_request(make_client):
    handler = routed(check=json_response(400, {"error": "invalid_request", "message": "recipient_email is not an email address"}))
    with pytest.raises(InvalidRequest) as info:
        make_client(handler).check("not-an-email")
    exc = info.value
    assert isinstance(exc, PreclearedError)
    assert exc.status_code == 400
    assert exc.code == "invalid_request"
    assert str(exc) == "recipient_email is not an email address"
    assert exc.body["error"] == "invalid_request"


@pytest.mark.parametrize("code", ["invalid_key", "revoked_key"])
def test_401_invalid_or_revoked_key(make_client, code):
    handler = routed(check=json_response(401, {"error": code, "message": f"{code} message"}))
    with pytest.raises(InvalidKey) as info:
        make_client(handler, api_key=KEY).check("jane@acme.co.uk")
    assert info.value.code == code
    assert info.value.status_code == 401
    assert KEY not in str(info.value)
    assert KEY not in repr(info.value.body)


def test_402_payment_required_exposes_buy_url(make_client):
    payload = {"error": "payment_required", "message": "Free checks used and no credits left.", "buy_url": "https://precleared.dev/buy?key=abc"}
    with pytest.raises(PaymentRequired) as info:
        make_client(routed(check=json_response(402, payload)), api_key=KEY).check("jane@acme.co.uk")
    assert info.value.buy_url == "https://precleared.dev/buy?key=abc"
    assert info.value.code == "payment_required"
    assert info.value.status_code == 402


def test_429_daily_limit_exposes_get_key_url(make_client):
    payload = {"error": "daily_limit", "message": "Keyless use is over for the day.", "get_key_url": "https://precleared.dev/get-key"}
    with pytest.raises(DailyLimit) as info:
        make_client(routed(check=json_response(429, payload))).check("jane@acme.co.uk")
    assert info.value.get_key_url == "https://precleared.dev/get-key"
    assert info.value.code == "daily_limit"
    assert not isinstance(info.value, RateLimited)


def test_429_daily_limit_inferred_from_get_key_url_when_code_missing(make_client):
    payload = {"message": "Daily limit reached.", "get_key_url": "https://precleared.dev/get-key"}
    with pytest.raises(DailyLimit):
        make_client(routed(check=json_response(429, payload))).check("jane@acme.co.uk")


def test_429_rate_limited_with_retry_after_in_body(make_client):
    payload = {"error": "rate_limited", "message": "Slow down.", "retry_after": 12}
    with pytest.raises(RateLimited) as info:
        make_client(routed(check=json_response(429, payload))).check("jane@acme.co.uk")
    assert info.value.retry_after == 12.0
    assert info.value.code == "rate_limited"
    assert not isinstance(info.value, DailyLimit)


def test_429_rate_limited_parses_retry_after_header_seconds(make_client):
    handler = routed(check=json_response(429, {"error": "rate_limited", "message": "Slow down."}, headers={"Retry-After": "7"}))
    with pytest.raises(RateLimited) as info:
        make_client(handler).check("jane@acme.co.uk")
    assert info.value.retry_after == 7.0


def test_429_rate_limited_parses_retry_after_http_date(make_client):
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    when = datetime.now(timezone.utc) + timedelta(seconds=90)
    handler = routed(check=json_response(429, {"error": "rate_limited"}, headers={"Retry-After": format_datetime(when, usegmt=True)}))
    with pytest.raises(RateLimited) as info:
        make_client(handler).check("jane@acme.co.uk")
    assert info.value.retry_after is not None
    assert 80 <= info.value.retry_after <= 91
    assert "60 a minute" in str(info.value)


def test_429_without_code_or_hints_is_rate_limited_with_none_retry(make_client):
    with pytest.raises(RateLimited) as info:
        make_client(routed(check=json_response(429, {}))).check("jane@acme.co.uk")
    assert info.value.retry_after is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_server_error(make_client, status):
    handler = routed(check=json_response(status, {"error": "server_error", "message": "Something broke."}))
    with pytest.raises(ServerError) as info:
        make_client(handler).check("jane@acme.co.uk")
    assert info.value.status_code == status
    assert info.value.code == "server_error"


def test_non_json_error_body_still_maps(make_client):
    handler = routed(check=lambda request: httpx.Response(503, text="<html>bad gateway</html>"))
    with pytest.raises(ServerError) as info:
        make_client(handler).check("jane@acme.co.uk")
    assert info.value.body == {}
    assert "503" in str(info.value)


def test_unexpected_status_is_base_error(make_client):
    handler = routed(check=json_response(418, {"error": "teapot", "message": "no"}))
    with pytest.raises(PreclearedError) as info:
        make_client(handler).check("jane@acme.co.uk")
    assert type(info.value) is PreclearedError
    assert info.value.status_code == 418


def test_success_with_non_json_body_raises(make_client):
    handler = routed(check=lambda request: httpx.Response(200, text="ok"))
    with pytest.raises(PreclearedError, match="not JSON") as info:
        make_client(handler).check("jane@acme.co.uk")
    assert info.value.code == "invalid_response"


def test_success_without_verdict_raises(make_client):
    with pytest.raises(ValueError, match="no verdict"):
        make_client(routed(check=json_response(200, {"facts": {}}))).check("jane@acme.co.uk")


def test_connection_failure_becomes_network_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(NetworkError) as info:
        make_client(routed(check=handler)).check("jane@acme.co.uk")
    assert isinstance(info.value.__cause__, httpx.ConnectError)
    assert "ConnectError" in str(info.value)
    assert info.value.status_code is None


def test_timeout_becomes_network_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(NetworkError):
        make_client(routed(check=handler)).check("jane@acme.co.uk")


# -- receipts and health -------------------------------------------------------


def test_verify_receipt_success(make_client, recorder):
    receipt = make_client().verify_receipt("cc_rcpt_0123456789ABCDEF")
    assert isinstance(receipt, Receipt)
    assert receipt.id == "cc_rcpt_0123456789ABCDEF"
    assert receipt.request_hash == "a" * 64
    assert receipt.response_hash == "b" * 64
    assert receipt.signature == "c2lnbmF0dXJl"
    assert receipt.algorithm == "ed25519"
    assert receipt.key_version == "v1"
    assert receipt.public_key.startswith("MCowBQYDK2VwAyEA")
    assert receipt.verify_url is None
    assert receipt.verdict == "ok_to_email"
    assert receipt.confidence == "high"
    assert receipt.rules_applied == ["gb_pecr_corporate_subscriber"]
    assert receipt.recipient_email_masked == "j***@acme.co.uk"
    assert receipt.recipient_domain == "acme.co.uk"
    assert receipt.sender_country == "GB"
    assert receipt.rules_version == "2026-10-01"
    assert receipt.page_url() == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"
    assert receipt.raw == RECEIPT_PAYLOAD
    assert "public_key" not in receipt.summary()
    assert "rules_applied: gb_pecr_corporate_subscriber" in receipt.summary_text()

    request = recorder.last
    assert request.method == "GET"
    assert request.url.path == "/api/v1/receipt"
    assert request.url.params["id"] == "cc_rcpt_0123456789ABCDEF"


def test_verify_receipt_accepts_wrapped_payload(make_client):
    wrapped = {"receipt": dict(RECEIPT_PAYLOAD, public_key=None), "public_key": "PUBKEY", "verified": True}
    del wrapped["receipt"]["public_key"]
    receipt = make_client(routed(receipt=json_response(200, wrapped))).verify_receipt("cc_rcpt_0123456789ABCDEF")
    assert receipt.id == "cc_rcpt_0123456789ABCDEF"
    assert receipt.public_key == "PUBKEY"
    assert receipt.raw["verified"] is True


def test_verify_receipt_accepts_receipt_url(make_client, recorder):
    make_client().verify_receipt("https://precleared.dev/r/cc_rcpt_0123456789ABCDEF")
    assert recorder.last.url.params["id"] == "cc_rcpt_0123456789ABCDEF"


@pytest.mark.parametrize("bad", ["", "   ", None, "https://example.com/not-a-receipt"])
def test_verify_receipt_rejects_bad_ids(make_client, recorder, bad):
    with pytest.raises(ValueError):
        make_client().verify_receipt(bad)
    assert recorder.requests == []


def test_verify_receipt_404(make_client):
    handler = routed(receipt=json_response(404, {"error": "not_found", "message": "No receipt has that id."}))
    with pytest.raises(ReceiptNotFound) as info:
        make_client(handler).verify_receipt("cc_rcpt_MISSING")
    assert info.value.status_code == 404


def test_health(make_client, recorder):
    health = make_client().health()
    assert health.ok is True
    assert health.status == "ok"
    assert health.checked_at == HEALTH_PAYLOAD["checked_at"]
    assert (health.api_ok, health.mcp_ok, health.worker_ok) == (True, True, True)
    assert health.raw == HEALTH_PAYLOAD
    assert recorder.last.url.path == "/api/v1/health"


def test_health_degraded(make_client):
    handler = routed(health=json_response(200, {"status": "degraded", "api_ok": True, "mcp_ok": False, "worker_ok": True}))
    health = make_client(handler).health()
    assert health.ok is False
    assert health.mcp_ok is False


# -- hygiene -------------------------------------------------------------------


def test_repr_never_shows_the_key():
    client = Precleared(KEY)
    assert KEY not in repr(client)
    assert "api_key=<set>" in repr(client)
    assert "api_key=None" in repr(Precleared())
    assert not hasattr(client, "api_key")


def test_context_manager_closes_client(make_transport):
    with Precleared(transport=make_transport()) as client:
        client.check("jane@acme.co.uk")
    assert client._http.is_closed


def test_custom_user_agent_and_timeout(make_transport, recorder):
    client = Precleared(transport=make_transport(), user_agent="my-agent/2.0", timeout=5)
    client.check("jane@acme.co.uk")
    assert recorder.last.headers["user-agent"] == "my-agent/2.0"
    assert client._http.timeout == httpx.Timeout(5)


def test_public_exports():
    for name in (
        "Precleared", "AsyncPrecleared", "CheckResult", "Receipt", "Reason", "Usage", "Health",
        "PreclearedError", "InvalidRequest", "InvalidKey", "PaymentRequired", "DailyLimit",
        "RateLimited", "ReceiptNotFound", "ServerError", "NetworkError",
    ):
        assert name in precleared.__all__
        assert hasattr(precleared, name)
    assert precleared.__version__ == "0.1.1"
    for cls in (InvalidRequest, InvalidKey, PaymentRequired, DailyLimit, RateLimited, ReceiptNotFound, ServerError, NetworkError):
        assert issubclass(cls, PreclearedError)
