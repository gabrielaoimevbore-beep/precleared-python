"""OpenAI Agents SDK adapter, tested against the installed openai-agents."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("agents")

from agents import FunctionTool, RunContextWrapper  # noqa: E402

try:  # ToolContext arrived in later SDK versions; earlier ones pass a RunContextWrapper.
    from agents.tool_context import ToolContext
except ImportError:  # pragma: no cover - depends on the installed SDK version
    ToolContext = None  # type: ignore[assignment,misc]

from precleared._tools import CHECK_DESCRIPTION, VERIFY_DESCRIPTION  # noqa: E402
from precleared.openai_agents import (  # noqa: E402
    precleared_check_tool,
    precleared_tools,
    precleared_verify_receipt_tool,
)

from conftest import json_response, routed  # noqa: E402

pytestmark = pytest.mark.anyio

FULL_ARGS = {
    "recipient_email": "jane@acme.co.uk",
    "recipient_domain": None,
    "pitch": "Bookkeeping software",
    "address_source": "unknown",
    "existing_customer": False,
    "pitch_relevant": None,
    "sender_country": "GB",
    "recipient_country": None,
    "company_number": None,
    "suppressed": None,
}


def _ctx(tool_name: str, arguments: dict):
    if ToolContext is None:
        return RunContextWrapper(context=None)
    payload = json.dumps(arguments)
    try:
        return ToolContext(context=None, tool_name=tool_name, tool_call_id="call_1", tool_arguments=payload)
    except TypeError:  # SDKs between the two shapes have no tool_arguments
        return ToolContext(context=None, tool_name=tool_name, tool_call_id="call_1")


async def _invoke(tool: FunctionTool, arguments: dict):
    return await tool.on_invoke_tool(_ctx(tool.name, arguments), json.dumps(arguments))


def test_tools_have_names_descriptions_and_schemas(make_transport):
    check, verify = precleared_tools(transport=make_transport())
    assert isinstance(check, FunctionTool) and isinstance(verify, FunctionTool)
    assert check.name == "precleared_check"
    assert verify.name == "precleared_verify_receipt"
    assert check.description == CHECK_DESCRIPTION
    assert verify.description == VERIFY_DESCRIPTION

    props = check.params_json_schema["properties"]
    assert set(props) == set(FULL_ARGS)
    assert props["address_source"]["description"].startswith("How the address was obtained")
    assert set(verify.params_json_schema["properties"]) == {"receipt_id"}
    assert "cc_rcpt_" in verify.params_json_schema["properties"]["receipt_id"]["description"]


def test_single_tool_factories(make_transport):
    assert precleared_check_tool(transport=make_transport()).name == "precleared_check"
    assert precleared_verify_receipt_tool(transport=make_transport()).name == "precleared_verify_receipt"


async def test_invoke_returns_compact_text(make_transport, recorder):
    check, verify = precleared_tools(transport=make_transport())
    text = await _invoke(check, FULL_ARGS)
    assert isinstance(text, str)
    assert text.startswith("verdict: ok_to_email (confidence: high)")
    assert "receipt: cc_rcpt_0123456789ABCDEF" in text
    body = recorder.last_json()
    assert body["address_source"] == "unknown"
    assert body["pitch"] == "Bookkeeping software"
    assert "recipient_domain" not in body

    receipt = await _invoke(verify, {"receipt_id": "cc_rcpt_0123456789ABCDEF"})
    assert receipt.startswith("receipt: cc_rcpt_0123456789ABCDEF")


async def test_partial_arguments_are_accepted(make_transport, recorder):
    check, _ = precleared_tools(transport=make_transport())
    text = await _invoke(check, {"recipient_email": "jane@acme.co.uk"})
    assert text.startswith("verdict: ok_to_email")
    assert recorder.last_json()["address_source"] == "unknown"


async def test_to_dict_returns_dict(make_transport):
    check, _ = precleared_tools(transport=make_transport(), to_dict=True)
    out = await _invoke(check, FULL_ARGS)
    if isinstance(out, str):  # SDKs before ToolContext stringify non-str results
        assert "'verdict': 'ok_to_email'" in out
        assert "'rule': 'gb_pecr_corporate_subscriber'" in out
    else:
        assert isinstance(out, dict)
        assert out["verdict"] == "ok_to_email"
        assert out["rule"] == "gb_pecr_corporate_subscriber"


async def test_api_error_is_returned_as_text(make_transport):
    limited = routed(check=json_response(429, {"error": "rate_limited", "retry_after": 5}))
    check, _ = precleared_tools(transport=make_transport(limited))
    text = await _invoke(check, FULL_ARGS)
    assert text.startswith("error: rate_limited")
    assert "retry_after: 5.0" in text


async def test_api_key_is_sent_but_never_shown(make_transport, recorder):
    key = "pc_live_agents_secret"
    check, _ = precleared_tools(key, transport=make_transport())
    await _invoke(check, FULL_ARGS)
    assert recorder.last.headers["authorization"] == f"Bearer {key}"
    assert key not in repr(check)
