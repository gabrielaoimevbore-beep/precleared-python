"""CrewAI adapter, tested against the installed crewai."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("crewai")

from precleared._tools import CHECK_DESCRIPTION, VERIFY_DESCRIPTION  # noqa: E402
from precleared.crewai import (  # noqa: E402
    PreclearedCheckTool,
    PreclearedVerifyReceiptTool,
    precleared_tools,
)

from conftest import json_response, routed  # noqa: E402


def test_tools_have_names_descriptions_and_schemas(make_transport):
    check = PreclearedCheckTool(transport=make_transport())
    verify = PreclearedVerifyReceiptTool(transport=make_transport())
    assert check.name == "precleared_check"
    assert verify.name == "precleared_verify_receipt"
    # CrewAI may append argument details to the description; the guidance must be intact.
    assert CHECK_DESCRIPTION in check.description
    assert VERIFY_DESCRIPTION in verify.description
    fields = check.args_schema.model_fields
    assert set(fields) >= {"recipient_email", "pitch", "address_source", "existing_customer", "suppressed"}
    assert fields["address_source"].default == "unknown"
    assert set(verify.args_schema.model_fields) == {"receipt_id"}


def test_run_returns_compact_text(make_transport, recorder):
    check = PreclearedCheckTool(transport=make_transport())
    text = check.run(recipient_email="jane@acme.co.uk", pitch="Bookkeeping", address_source="given")
    assert str(text).startswith("verdict: ok_to_email (confidence: high)")
    assert "receipt: cc_rcpt_0123456789ABCDEF" in str(text)
    assert recorder.last_json()["address_source"] == "given"

    verify = PreclearedVerifyReceiptTool(transport=make_transport())
    assert str(verify.run(receipt_id="cc_rcpt_0123456789ABCDEF")).startswith("receipt: cc_rcpt_0123456789ABCDEF")


def test_to_dict_returns_dict(make_transport):
    check = PreclearedCheckTool(transport=make_transport(), to_dict=True)
    out = check._run(recipient_email="jane@acme.co.uk")
    assert isinstance(out, dict)
    assert out["verdict"] == "ok_to_email"


def test_precleared_tools_share_one_client(make_transport, recorder):
    check, verify = precleared_tools("pc_live_crew_secret", transport=make_transport())
    assert [check.name, verify.name] == ["precleared_check", "precleared_verify_receipt"]
    assert check._runner.client is verify._runner.client
    check.run(recipient_email="jane@acme.co.uk")
    assert recorder.last.headers["authorization"] == "Bearer pc_live_crew_secret"


def test_api_error_is_returned_as_text(make_transport):
    bad = routed(check=json_response(401, {"error": "revoked_key", "message": "This key was revoked."}))
    check = PreclearedCheckTool("pc_live_old", transport=make_transport(bad))
    text = str(check.run(recipient_email="jane@acme.co.uk"))
    assert text.startswith("error: revoked_key")
    assert "This key was revoked." in text
    assert "pc_live_old" not in text


def test_api_key_never_appears_in_repr_or_dump(make_transport):
    key = "pc_live_crewai_secret"
    check = PreclearedCheckTool(key, transport=make_transport())
    assert key not in repr(check)
    assert key not in json.dumps(check.model_dump(), default=str)
    assert not hasattr(check, "api_key")
