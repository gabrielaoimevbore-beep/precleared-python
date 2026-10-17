"""LlamaIndex adapter, tested against the installed llama-index-core."""

from __future__ import annotations

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.tools import FunctionTool, ToolOutput  # noqa: E402

from precleared._tools import CHECK_DESCRIPTION, VERIFY_DESCRIPTION  # noqa: E402
from precleared.llamaindex import (  # noqa: E402
    precleared_check_tool,
    precleared_tools,
    precleared_verify_receipt_tool,
)

from conftest import json_response, routed  # noqa: E402


def test_tools_are_function_tools_with_metadata(make_transport):
    check, verify = precleared_tools(transport=make_transport())
    assert isinstance(check, FunctionTool) and isinstance(verify, FunctionTool)
    assert check.metadata.name == "precleared_check"
    assert verify.metadata.name == "precleared_verify_receipt"
    assert check.metadata.description == CHECK_DESCRIPTION
    assert verify.metadata.description == VERIFY_DESCRIPTION

    fields = check.metadata.fn_schema.model_fields
    assert set(fields) >= {"recipient_email", "pitch", "address_source", "existing_customer", "suppressed"}
    assert fields["address_source"].default == "unknown"
    assert fields["address_source"].description.startswith("How the address was obtained")
    assert set(verify.metadata.fn_schema.model_fields) == {"receipt_id"}

    openai_tool = check.metadata.to_openai_tool()
    assert openai_tool["function"]["name"] == "precleared_check"
    assert "address_source" in openai_tool["function"]["parameters"]["properties"]


def test_single_tool_factories(make_transport):
    assert precleared_check_tool(transport=make_transport()).metadata.name == "precleared_check"
    assert precleared_verify_receipt_tool(transport=make_transport()).metadata.name == "precleared_verify_receipt"


def test_call_returns_tool_output_with_compact_text(make_transport, recorder):
    check, verify = precleared_tools(transport=make_transport())
    output = check.call(recipient_email="jane@acme.co.uk", pitch="Bookkeeping", address_source="scraped")
    assert isinstance(output, ToolOutput)
    assert output.tool_name == "precleared_check"
    assert output.content.startswith("verdict: ok_to_email (confidence: high)")
    assert "footer_text:" in output.content
    assert recorder.last_json()["address_source"] == "scraped"

    receipt = verify.call(receipt_id="cc_rcpt_0123456789ABCDEF")
    assert receipt.content.startswith("receipt: cc_rcpt_0123456789ABCDEF")


def test_to_dict_keeps_dict_in_raw_output(make_transport):
    check, _ = precleared_tools(transport=make_transport(), to_dict=True)
    output = check.call(recipient_email="jane@acme.co.uk")
    assert isinstance(output.raw_output, dict)
    assert output.raw_output["verdict"] == "ok_to_email"
    assert output.raw_output["receipt_url"].endswith("/r/cc_rcpt_0123456789ABCDEF")


def test_api_error_is_returned_as_text(make_transport):
    pay = routed(check=json_response(402, {"error": "payment_required", "buy_url": "https://precleared.dev/buy"}))
    check, _ = precleared_tools(transport=make_transport(pay))
    output = check.call(recipient_email="jane@acme.co.uk")
    assert output.content.startswith("error: payment_required")
    assert "buy_url: https://precleared.dev/buy" in output.content


def test_api_key_is_sent_but_never_shown(make_transport, recorder):
    key = "pc_live_llamaindex_secret"
    check, _ = precleared_tools(key, transport=make_transport())
    check.call(recipient_email="jane@acme.co.uk")
    assert recorder.last.headers["authorization"] == f"Bearer {key}"
    assert key not in repr(check) and key not in repr(check.metadata)


@pytest.mark.anyio
async def test_acall_works(make_transport):
    check, _ = precleared_tools(transport=make_transport())
    output = await check.acall(recipient_email="jane@acme.co.uk")
    assert output.content.startswith("verdict: ok_to_email")
