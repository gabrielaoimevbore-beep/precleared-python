"""OpenAI Agents SDK tools for Precleared.

Requires the ``openai-agents`` extra::

    pip install "precleared[openai-agents]"

Usage::

    from agents import Agent
    from precleared.openai_agents import precleared_tools

    agent = Agent(name="SDR", instructions="...", tools=precleared_tools())
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

try:
    from agents import FunctionTool, function_tool
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "precleared.openai_agents needs the openai-agents package. "
        "Install it with: pip install 'precleared[openai-agents]'"
    ) from exc

from ._tools import (
    ARG_DESCRIPTIONS,
    CHECK_DESCRIPTION,
    CHECK_TOOL_NAME,
    VERIFY_DESCRIPTION,
    VERIFY_TOOL_NAME,
    PreclearedTools,
    google_docstring,
)

_CHECK_ARGS = [
    "recipient_email",
    "recipient_domain",
    "pitch",
    "address_source",
    "existing_customer",
    "pitch_relevant",
    "sender_country",
    "recipient_country",
    "company_number",
    "suppressed",
]


def _check_tool(runner: PreclearedTools) -> FunctionTool:
    def precleared_check(
        recipient_email: Optional[str] = None,
        recipient_domain: Optional[str] = None,
        pitch: Optional[str] = None,
        address_source: str = "unknown",
        existing_customer: bool = False,
        pitch_relevant: Optional[bool] = None,
        sender_country: str = "GB",
        recipient_country: Optional[str] = None,
        company_number: Optional[str] = None,
        suppressed: Optional[bool] = None,
    ) -> Union[str, Dict[str, Any]]:
        return runner.check(
            recipient_email=recipient_email,
            recipient_domain=recipient_domain,
            pitch=pitch,
            address_source=address_source,
            existing_customer=existing_customer,
            pitch_relevant=pitch_relevant,
            sender_country=sender_country,
            recipient_country=recipient_country,
            company_number=company_number,
            suppressed=suppressed,
        )

    precleared_check.__doc__ = google_docstring(
        CHECK_DESCRIPTION, {name: ARG_DESCRIPTIONS[name] for name in _CHECK_ARGS}
    )
    return function_tool(
        precleared_check,
        name_override=CHECK_TOOL_NAME,
        description_override=CHECK_DESCRIPTION,
    )


def _verify_tool(runner: PreclearedTools) -> FunctionTool:
    def precleared_verify_receipt(receipt_id: str) -> Union[str, Dict[str, Any]]:
        return runner.verify_receipt(receipt_id)

    precleared_verify_receipt.__doc__ = google_docstring(
        VERIFY_DESCRIPTION, {"receipt_id": ARG_DESCRIPTIONS["receipt_id"]}
    )
    return function_tool(
        precleared_verify_receipt,
        name_override=VERIFY_TOOL_NAME,
        description_override=VERIFY_DESCRIPTION,
    )


def precleared_check_tool(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> FunctionTool:
    """``precleared_check`` as an Agents SDK ``FunctionTool``.

    Returns compact text by default. Pass ``to_dict=True`` for a dictionary.
    """
    return _check_tool(PreclearedTools(api_key, to_dict=to_dict, **client_kwargs))


def precleared_verify_receipt_tool(
    api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any
) -> FunctionTool:
    """``precleared_verify_receipt`` as an Agents SDK ``FunctionTool``."""
    return _verify_tool(PreclearedTools(api_key, to_dict=to_dict, **client_kwargs))


def precleared_tools(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> List[FunctionTool]:
    """Both tools, sharing one client. Pass straight to ``Agent(tools=...)``."""
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return [_check_tool(runner), _verify_tool(runner)]


__all__ = ["precleared_check_tool", "precleared_verify_receipt_tool", "precleared_tools"]
