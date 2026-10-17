"""LangChain adapter, tested against the installed langchain-core."""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from langchain_core.tools import StructuredTool  # noqa: E402

from precleared._tools import CHECK_DESCRIPTION, VERIFY_DESCRIPTION  # noqa: E402
from precleared.langchain import (  # noqa: E402
    precleared_check_tool,
    precleared_tools,
    precleared_verify_receipt_tool,
)

from conftest import json_response, routed  # noqa: E402

CHECK_FIELDS = {
    "recipient_email", "recipient_domain", "pitch", "address_source", "existing_customer",
    "pitch_relevant", "sender_country", "recipient_country", "company_number", "suppressed",
}


def test_tools_are_structured_tools_with_names_and_schemas(make_transport):
    check, verify = precleared_tools(transport=make_transport())
    assert isinstance(check, StructuredTool) and isinstance(verify, StructuredTool)
    assert check.name == "precleared_check"
    assert verify.name == "precleared_verify_receipt"
    assert check.description == CHECK_DESCRIPTION
    assert verify.description == VERIFY_DESCRIPTION
    assert set(check.args) == CHECK_FIELDS
    assert check.args["address_source"]["default"] == "unknown"
    assert check.args["address_source"]["description"].startswith("How the address was obtained")
    assert check.args["existing_customer"]["default"] is False
    assert set(verify.args) == {"receipt_id"}
    assert "cc_rcpt_" in verify.args["receipt_id"]["description"]


def test_single_tool_factories(make_transport):
    assert precleared_check_tool(transport=make_transport()).name == "precleared_check"
    assert precleared_verify_receipt_tool(transport=make_transport()).name == "precleared_verify_receipt"


def test_invoke_returns_compact_text(make_transport, recorder):
    check, verify = precleared_tools(transport=make_transport())
    text = check.invoke({"recipient_email": "jane@acme.co.uk", "pitch": "Bookkeeping software"})
    assert text.startswith("verdict: ok_to_email (confidence: high)")
    assert "receipt: cc_rcpt_0123456789ABCDEF https://precleared.dev/r/cc_rcpt_0123456789ABCDEF" in text
    assert recorder.last_json()["address_source"] == "unknown"
    assert "authorization" not in recorder.last.headers

    receipt_text = verify.invoke({"receipt_id": "cc_rcpt_0123456789ABCDEF"})
    assert receipt_text.startswith("receipt: cc_rcpt_0123456789ABCDEF")


def test_invoke_with_tool_call_message_like_an_agent_loop(make_transport):
    check, _ = precleared_tools(transport=make_transport())
    message = check.invoke(
        {
            "name": "precleared_check",
            "args": {"recipient_email": "jane@acme.co.uk", "address_source": "bought", "existing_customer": False},
            "id": "call_1",
            "type": "tool_call",
        }
    )
    assert message.tool_call_id == "call_1"
    assert str(message.content).startswith("verdict: ok_to_email")


def test_to_dict_returns_dict(make_transport):
    check, verify = precleared_tools(transport=make_transport(), to_dict=True)
    out = check.invoke({"recipient_email": "jane@acme.co.uk"})
    assert isinstance(out, dict)
    assert out["verdict"] == "ok_to_email"
    assert out["receipt_url"] == "https://precleared.dev/r/cc_rcpt_0123456789ABCDEF"
    receipt = verify.invoke({"receipt_id": "cc_rcpt_0123456789ABCDEF"})
    assert receipt["receipt_id"] == "cc_rcpt_0123456789ABCDEF"


def test_api_error_is_returned_as_text(make_transport):
    limited = routed(check=json_response(429, {"error": "daily_limit", "get_key_url": "https://precleared.dev/get-key"}))
    check, _ = precleared_tools(transport=make_transport(limited))
    text = check.invoke({"recipient_email": "jane@acme.co.uk"})
    assert text.startswith("error: daily_limit")
    assert "get_key_url: https://precleared.dev/get-key" in text


def test_api_key_is_sent_but_never_shown(make_transport, recorder):
    key = "pc_live_langchain_secret"
    check, _ = precleared_tools(key, transport=make_transport())
    check.invoke({"recipient_email": "jane@acme.co.uk"})
    assert recorder.last.headers["authorization"] == f"Bearer {key}"
    assert key not in repr(check)
    assert key not in repr(check.func)


@pytest.mark.anyio
async def test_ainvoke_works(make_transport):
    check, _ = precleared_tools(transport=make_transport())
    text = await check.ainvoke({"recipient_email": "jane@acme.co.uk"})
    assert text.startswith("verdict: ok_to_email")
