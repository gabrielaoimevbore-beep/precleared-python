"""AsyncPrecleared mirrors the sync client over httpx.AsyncClient."""

from __future__ import annotations

import httpx
import pytest

from precleared import (
    AsyncPrecleared,
    DailyLimit,
    InvalidKey,
    NetworkError,
    PaymentRequired,
    RateLimited,
    ReceiptNotFound,
    ServerError,
)

from conftest import CONSENT_PAYLOAD, json_response, routed

pytestmark = pytest.mark.anyio

KEY = "pc_live_async0123456789abcdef"


async def test_async_check_success(make_async_client, recorder):
    async with make_async_client(api_key=KEY) as client:
        result = await client.check("jane@acme.co.uk", pitch="Bookkeeping", address_source="given")
    assert result.ok is True
    assert result.rule == "gb_pecr_corporate_subscriber"
    assert result.receipt_url == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"
    assert recorder.last.headers["authorization"] == f"Bearer {KEY}"
    assert recorder.last.headers["user-agent"] == "precleared-python/0.1.0"
    assert recorder.last_json()["address_source"] == "given"
    assert client._http.is_closed


async def test_async_check_consent_needed(make_async_client):
    client = make_async_client(routed(check=json_response(200, CONSENT_PAYLOAD)))
    result = await client.check(recipient_domain="soletrader.co.uk")
    assert result.must_not_send is True
    await client.aclose()


async def test_async_validation_happens_before_request(make_async_client, recorder):
    client = make_async_client()
    with pytest.raises(ValueError, match="address_source"):
        await client.check("jane@acme.co.uk", address_source="guessed")
    with pytest.raises(ValueError, match="required"):
        await client.check()
    assert recorder.requests == []


@pytest.mark.parametrize(
    "status, payload, headers, exc_type",
    [
        (401, {"error": "revoked_key", "message": "revoked"}, {}, InvalidKey),
        (402, {"error": "payment_required", "buy_url": "https://precleared.dev/buy"}, {}, PaymentRequired),
        (429, {"error": "daily_limit", "get_key_url": "https://precleared.dev/get-key"}, {}, DailyLimit),
        (429, {"error": "rate_limited"}, {"Retry-After": "3"}, RateLimited),
        (500, {"error": "server_error"}, {}, ServerError),
    ],
)
async def test_async_error_mapping(make_async_client, status, payload, headers, exc_type):
    client = make_async_client(routed(check=json_response(status, payload, headers=headers)))
    with pytest.raises(exc_type) as info:
        await client.check("jane@acme.co.uk")
    assert info.value.status_code == status
    if exc_type is RateLimited:
        assert info.value.retry_after == 3.0
    if exc_type is DailyLimit:
        assert info.value.get_key_url == "https://precleared.dev/get-key"
    if exc_type is PaymentRequired:
        assert info.value.buy_url == "https://precleared.dev/buy"


async def test_async_network_error(make_async_client):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client = make_async_client(routed(check=boom))
    with pytest.raises(NetworkError) as info:
        await client.check("jane@acme.co.uk")
    assert isinstance(info.value.__cause__, httpx.ConnectTimeout)


async def test_async_verify_receipt_and_404(make_async_client, recorder):
    client = make_async_client()
    receipt = await client.verify_receipt("cc_rcpt_0123456789ABCDEF")
    assert receipt.id == "cc_rcpt_0123456789ABCDEF"
    assert receipt.signature == "c2lnbmF0dXJl"
    assert recorder.last.url.params["id"] == "cc_rcpt_0123456789ABCDEF"

    missing = make_async_client(routed(receipt=json_response(404, {"error": "not_found", "message": "none"})))
    with pytest.raises(ReceiptNotFound):
        await missing.verify_receipt("cc_rcpt_NOPE")


async def test_async_health(make_async_client):
    health = await make_async_client().health()
    assert health.ok is True
    assert health.worker_ok is True


def test_async_repr_hides_key():
    client = AsyncPrecleared(KEY)
    assert KEY not in repr(client)
    assert repr(client).startswith("AsyncPrecleared(")
