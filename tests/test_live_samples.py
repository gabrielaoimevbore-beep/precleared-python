"""Exact responses captured from the live API on 2026-10-17, replayed through
a mock transport. They pin the real field names so a parser change that
breaks on genuine output fails here, without any network access.

Captured with: recipient_email support@precleared.dev (a public address, and
masked by the API anyway), recipient_country GB, address_source published,
pitch "integration test". Receipt id cc_rcpt_E21TTJV8D9JAYTQZ.
"""

from __future__ import annotations

import pytest

from precleared import Precleared
from precleared._tools import PreclearedTools

from conftest import json_response, routed

LIVE_CHECK = {
    "verdict": "consent_needed",
    "confidence": "medium",
    "reasons": [
        {
            "rule_key": "gb_individual_consent",
            "text": (
                "The recipient is a sole trader or a partnership in England, Wales or Northern Ireland. "
                "PECR treats them as individual subscribers, so unsolicited marketing email needs their "
                "prior consent, or the soft opt-in for existing customers."
            ),
            "source_title": "PECR 2003 regulation 22(2) and ICO Guide to PECR",
            "source_url": "https://www.legislation.gov.uk/uksi/2003/2426/regulation/22",
        }
    ],
    "rules_applied": ["gb_individual_consent"],
    "footer_text": None,
    "next_step": "Do not cold email. Use a route they offer, such as their contact form, or obtain consent first.",
    "facts": {
        "recipient_email_masked": "s***@precleared.dev",
        "recipient_domain": "precleared.dev",
        "recipient_country": "GB",
        "country_source": "caller",
        "legal_form": "individual",
        "legal_form_source": "website",
        "company_number": None,
        "company_name": None,
        "company_status": None,
        "director_first_name": None,
        "address_type": "role",
        "syntax_ok": True,
        "mx_ok": True,
        "disposable": False,
        "suppressed": False,
    },
    "receipt": {
        "id": "cc_rcpt_E21TTJV8D9JAYTQZ",
        "created_at": "2026-10-17T10:15:22.590Z",
        "request_hash": "36830a6f0c0d441cc0672e02f6ab02c8e6fedaf6e42e7e67c06750afd0363fb5",
        "response_hash": "0c07fee9789c58fe165b693e45c0a2114a4082b3a9f6c04cb1cca636972633bd",
        "signature": "gPAeSzHg2wRuSsMd0Iy28UM1eojy5IoAND7A/GfuV29e9GjeQmTJgOlVQzwH9qRNKtyvKJ/3UWW9e6Xee33QCA==",
        "algorithm": "ed25519",
        "key_version": "k1",
        "verify_url": "https://precleared.dev/api/v1/receipt?id=cc_rcpt_E21TTJV8D9JAYTQZ",
    },
    "rules_version": "v1-draft",
    "usage": {"free_remaining_today": 99, "credits_remaining": 0},
    "disclaimer": (
        "Decision support with sources, not legal advice. "
        "The receipt proves what was asked and answered, not that an email was sent."
    ),
}

LIVE_RECEIPT = {
    "id": "cc_rcpt_E21TTJV8D9JAYTQZ",
    "created_at": "2026-10-17T10:15:22.59+00:00",
    "verdict": "consent_needed",
    "confidence": "medium",
    "rules_applied": ["gb_individual_consent"],
    "recipient_domain": "precleared.dev",
    "recipient_email_masked": "s***@precleared.dev",
    "sender_country": "GB",
    "rules_version": "v1-draft",
    "request_hash": "36830a6f0c0d441cc0672e02f6ab02c8e6fedaf6e42e7e67c06750afd0363fb5",
    "response_hash": "0c07fee9789c58fe165b693e45c0a2114a4082b3a9f6c04cb1cca636972633bd",
    "signature": "gPAeSzHg2wRuSsMd0Iy28UM1eojy5IoAND7A/GfuV29e9GjeQmTJgOlVQzwH9qRNKtyvKJ/3UWW9e6Xee33QCA==",
    "algorithm": "ed25519",
    "key_version": "k1",
    "public_key": "MCowBQYDK2VwAyEAxKYMJSUl95O2MxJPAHNR5HeGD8DFEoNZLP7UZ3cafMM=",
}

LIVE_HEALTH = {
    "status": "ok",
    "checked_at": "2026-10-17T02:30:02.442963+00:00",
    "api_ok": True,
    "mcp_ok": True,
    "worker_ok": True,
}


@pytest.fixture
def live_client(make_transport) -> Precleared:
    handler = routed(
        check=json_response(200, LIVE_CHECK),
        receipt=json_response(200, LIVE_RECEIPT),
        health=json_response(200, LIVE_HEALTH),
    )
    return Precleared(transport=make_transport(handler))


def test_live_check_sample_parses(live_client):
    result = live_client.check("support@precleared.dev", recipient_country="GB", address_source="published", pitch="integration test")
    assert result.verdict == "consent_needed"
    assert result.must_not_send is True
    assert result.ok is False
    assert result.confidence == "medium"
    assert result.rule == "gb_individual_consent"
    assert result.reason.source_title == "PECR 2003 regulation 22(2) and ICO Guide to PECR"
    assert result.footer_text is None
    assert result.next_step.startswith("Do not cold email.")
    assert result.facts["legal_form"] == "individual"
    assert result.facts["legal_form_source"] == "website"
    assert result.facts["recipient_email_masked"] == "s***@precleared.dev"
    assert result.receipt_id == "cc_rcpt_E21TTJV8D9JAYTQZ"
    assert result.receipt_url == "https://precleared.dev/r/cc_rcpt_E21TTJV8D9JAYTQZ"
    assert result.receipt.verify_url == "https://precleared.dev/api/v1/receipt?id=cc_rcpt_E21TTJV8D9JAYTQZ"
    assert result.receipt.key_version == "k1"
    assert result.rules_version == "v1-draft"
    assert result.usage.free_remaining_today == 99
    assert result.disclaimer.startswith("Decision support with sources, not legal advice.")
    assert result.raw == LIVE_CHECK


def test_live_receipt_sample_parses(live_client):
    receipt = live_client.verify_receipt("cc_rcpt_E21TTJV8D9JAYTQZ")
    assert receipt.id == "cc_rcpt_E21TTJV8D9JAYTQZ"
    assert receipt.verdict == "consent_needed"
    assert receipt.confidence == "medium"
    assert receipt.rules_applied == ["gb_individual_consent"]
    assert receipt.recipient_email_masked == "s***@precleared.dev"
    assert receipt.sender_country == "GB"
    assert receipt.algorithm == "ed25519"
    assert receipt.key_version == "k1"
    assert receipt.public_key == "MCowBQYDK2VwAyEAxKYMJSUl95O2MxJPAHNR5HeGD8DFEoNZLP7UZ3cafMM="
    assert receipt.request_hash == LIVE_CHECK["receipt"]["request_hash"]
    assert receipt.response_hash == LIVE_CHECK["receipt"]["response_hash"]
    assert receipt.signature == LIVE_CHECK["receipt"]["signature"]
    assert receipt.verify_url is None
    assert receipt.raw == LIVE_RECEIPT


def test_live_health_sample_parses(live_client):
    health = live_client.health()
    assert health.ok is True
    assert health.checked_at == "2026-10-17T02:30:02.442963+00:00"
    assert (health.api_ok, health.mcp_ok, health.worker_ok) == (True, True, True)


def test_live_samples_through_the_tool_layer(make_transport):
    handler = routed(check=json_response(200, LIVE_CHECK), receipt=json_response(200, LIVE_RECEIPT))
    tools = PreclearedTools(transport=make_transport(handler))
    text = tools.check(recipient_email="support@precleared.dev", recipient_country="GB", address_source="published", pitch="integration test")
    lines = text.splitlines()
    assert lines[0] == "verdict: consent_needed (confidence: medium)"
    assert lines[1] == "rule: gb_individual_consent"
    assert lines[2].startswith("reason: The recipient is a sole trader")
    assert lines[2].endswith("https://www.legislation.gov.uk/uksi/2003/2426/regulation/22")
    assert lines[3] == "next_step: Do not cold email. Use a route they offer, such as their contact form, or obtain consent first."
    assert lines[4] == "receipt: cc_rcpt_E21TTJV8D9JAYTQZ https://precleared.dev/r/cc_rcpt_E21TTJV8D9JAYTQZ"
    assert len(lines) == 5

    receipt_text = tools.verify_receipt("cc_rcpt_E21TTJV8D9JAYTQZ")
    assert receipt_text.splitlines()[0] == "receipt: cc_rcpt_E21TTJV8D9JAYTQZ"
    assert "verdict: consent_needed" in receipt_text
    assert "public_key" not in receipt_text
    assert receipt_text.splitlines()[-1] == "receipt_url: https://precleared.dev/r/cc_rcpt_E21TTJV8D9JAYTQZ"
