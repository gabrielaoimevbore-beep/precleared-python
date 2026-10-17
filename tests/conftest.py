"""Shared fixtures. All HTTP is served by ``httpx.MockTransport``; nothing in
the test suite talks to the live API."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

from precleared import AsyncPrecleared, Precleared

OK_PAYLOAD: Dict[str, Any] = {
    "verdict": "ok_to_email",
    "confidence": "high",
    "reasons": [
        {
            "rule_key": "gb_pecr_corporate_subscriber",
            "text": "Corporate subscribers are outside the consent rule for marketing email.",
            "source_title": "ICO guidance on PECR regulation 22",
            "source_url": "https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/",
        },
        {"note": "Legal form came from the Companies House register."},
    ],
    "rules_applied": ["gb_pecr_corporate_subscriber"],
    "footer_text": "Say who you are, give a postal address and a working way to opt out.",
    "next_step": "Send, with a footer that meets footer_text.",
    "facts": {
        "address": "j***@acme.co.uk",
        "domain": "acme.co.uk",
        "country": "GB",
        "country_source": "domain",
        "legal_form": "limited_company",
        "legal_form_source": "companies_house",
        "company_number": "01234567",
        "company_status": "active",
    },
    "receipt": {
        "id": "cc_rcpt_0123456789ABCDEF",
        "created_at": "2026-10-17T10:15:00Z",
        "request_hash": "a" * 64,
        "response_hash": "b" * 64,
        "signature": "c2lnbmF0dXJl",
        "algorithm": "ed25519",
        "key_version": "v1",
        "verify_url": "https://precleared.dev/api/v1/receipt?id=cc_rcpt_0123456789ABCDEF",
    },
    "rules_version": "2026-10-01",
    "usage": {"free_remaining_today": 9, "credits_remaining": 0},
    "disclaimer": "Decision support with sources, not legal advice.",
}

CONSENT_PAYLOAD: Dict[str, Any] = {
    "verdict": "consent_needed",
    "confidence": "medium",
    "reasons": [
        {
            "rule_key": "gb_pecr_individual_subscriber",
            "text": "Sole traders and partnerships are individual subscribers and need prior consent.",
            "source_title": "PECR regulation 22",
            "source_url": "https://www.legislation.gov.uk/uksi/2003/2426/regulation/22",
        }
    ],
    "rules_applied": ["gb_pecr_individual_subscriber"],
    "footer_text": None,
    "next_step": "Do not send. Get consent another way, for example a sign-up form or a phone call.",
    "facts": {"country": "GB", "legal_form": "sole_trader", "legal_form_source": "website"},
    "receipt": {"id": "cc_rcpt_CONSENT000000001"},
    "usage": {"free_remaining_today": 8, "credits_remaining": 0},
    "disclaimer": "Decision support with sources, not legal advice.",
}

UNKNOWN_PAYLOAD: Dict[str, Any] = {
    "verdict": "unknown",
    "confidence": "low",
    "reasons": [{"note": "Companies House could not be searched by name. Try again later or pass company_number."}],
    "rules_applied": [],
    "footer_text": None,
    "next_step": "Treat as consent_needed, or pass company_number and check again.",
    "facts": {"country": "GB"},
    "receipt": {"id": "cc_rcpt_UNKNOWN000000001"},
    "usage": {"free_remaining_today": 7, "credits_remaining": 0},
    "disclaimer": "Decision support with sources, not legal advice.",
}

# Shape of GET /api/v1/receipt, as observed live: flat, with the verdict
# the check gave and the signing public key, but no verify_url.
RECEIPT_PAYLOAD: Dict[str, Any] = {
    "id": "cc_rcpt_0123456789ABCDEF",
    "created_at": "2026-10-17T10:15:00+00:00",
    "verdict": "ok_to_email",
    "confidence": "high",
    "rules_applied": ["gb_pecr_corporate_subscriber"],
    "recipient_domain": "acme.co.uk",
    "recipient_email_masked": "j***@acme.co.uk",
    "sender_country": "GB",
    "rules_version": "2026-10-01",
    "request_hash": "a" * 64,
    "response_hash": "b" * 64,
    "signature": "c2lnbmF0dXJl",
    "algorithm": "ed25519",
    "key_version": "v1",
    "public_key": "MCowBQYDK2VwAyEA" + "A" * 43 + "=",
}

HEALTH_PAYLOAD: Dict[str, Any] = {
    "status": "ok",
    "checked_at": "2026-10-17T10:20:00Z",
    "api_ok": True,
    "mcp_ok": True,
    "worker_ok": True,
}


class Recorder:
    """Collects the requests a mock transport saw."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was made"
        return self.requests[-1]

    def last_json(self) -> Dict[str, Any]:
        return json.loads(self.last.content.decode("utf-8"))


Handler = Callable[[httpx.Request], httpx.Response]


def json_response(status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=copy.deepcopy(payload), headers=headers or {})

    return handler


def routed(
    check: Optional[Handler] = None,
    receipt: Optional[Handler] = None,
    health: Optional[Handler] = None,
) -> Handler:
    """Route by path so one transport can serve all three endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/check" and request.method == "POST":
            return (check or json_response(200, OK_PAYLOAD))(request)
        if path == "/api/v1/receipt" and request.method == "GET":
            return (receipt or json_response(200, RECEIPT_PAYLOAD))(request)
        if path == "/api/v1/health" and request.method == "GET":
            return (health or json_response(200, HEALTH_PAYLOAD))(request)
        return httpx.Response(404, json={"error": "not_found", "message": f"no route {request.method} {path}"})

    return handler


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def make_transport(recorder: Recorder) -> Callable[..., httpx.MockTransport]:
    def factory(handler: Optional[Handler] = None) -> httpx.MockTransport:
        inner = handler or routed()

        def recording(request: httpx.Request) -> httpx.Response:
            request.read()
            recorder.requests.append(request)
            return inner(request)

        return httpx.MockTransport(recording)

    return factory


@pytest.fixture
def make_client(make_transport: Callable[..., httpx.MockTransport]) -> Callable[..., Precleared]:
    def factory(handler: Optional[Handler] = None, api_key: Optional[str] = None, **kwargs: Any) -> Precleared:
        return Precleared(api_key, transport=make_transport(handler), **kwargs)

    return factory


@pytest.fixture
def make_async_client(
    make_transport: Callable[..., httpx.MockTransport],
) -> Callable[..., AsyncPrecleared]:
    def factory(handler: Optional[Handler] = None, api_key: Optional[str] = None, **kwargs: Any) -> AsyncPrecleared:
        return AsyncPrecleared(api_key, transport=make_transport(handler), **kwargs)

    return factory


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the environment from leaking a real key into the tests."""
    monkeypatch.delenv("PRECLEARED_API_KEY", raising=False)
