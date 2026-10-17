"""LangChain / LangGraph tools for Precleared.

Requires the ``langchain`` extra::

    pip install "precleared[langchain]"

Usage::

    from precleared.langchain import precleared_tools

    tools = precleared_tools()                  # keyless, 10 checks a day per network
    tools = precleared_tools(api_key="pc_live_...")
    agent = create_react_agent(model, tools)
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    from langchain_core.tools import StructuredTool
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "precleared.langchain needs langchain-core. Install it with: pip install 'precleared[langchain]'"
    ) from exc

from ._schemas import PreclearedCheckArgs, PreclearedVerifyReceiptArgs
from ._tools import (
    CHECK_DESCRIPTION,
    CHECK_TOOL_NAME,
    VERIFY_DESCRIPTION,
    VERIFY_TOOL_NAME,
    PreclearedTools,
)


def precleared_check_tool(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> StructuredTool:
    """``precleared_check`` as a LangChain ``StructuredTool``.

    Returns compact text by default (verdict, rule, footer_text, next_step,
    receipt URL). Pass ``to_dict=True`` for a dictionary instead.
    """
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return StructuredTool.from_function(
        func=runner.check,
        name=CHECK_TOOL_NAME,
        description=CHECK_DESCRIPTION,
        args_schema=PreclearedCheckArgs,
    )


def precleared_verify_receipt_tool(
    api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any
) -> StructuredTool:
    """``precleared_verify_receipt`` as a LangChain ``StructuredTool``."""
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return StructuredTool.from_function(
        func=runner.verify_receipt,
        name=VERIFY_TOOL_NAME,
        description=VERIFY_DESCRIPTION,
        args_schema=PreclearedVerifyReceiptArgs,
    )


def precleared_tools(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> List[StructuredTool]:
    """Both tools, sharing one client. Pass straight to an agent's ``tools``."""
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return [
        StructuredTool.from_function(
            func=runner.check,
            name=CHECK_TOOL_NAME,
            description=CHECK_DESCRIPTION,
            args_schema=PreclearedCheckArgs,
        ),
        StructuredTool.from_function(
            func=runner.verify_receipt,
            name=VERIFY_TOOL_NAME,
            description=VERIFY_DESCRIPTION,
            args_schema=PreclearedVerifyReceiptArgs,
        ),
    ]


__all__ = ["precleared_check_tool", "precleared_verify_receipt_tool", "precleared_tools"]
