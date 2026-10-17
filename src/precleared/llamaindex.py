"""LlamaIndex tools for Precleared.

Requires the ``llamaindex`` extra::

    pip install "precleared[llamaindex]"

Usage::

    from precleared.llamaindex import precleared_tools

    agent = FunctionAgent(tools=precleared_tools(), llm=llm)
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    from llama_index.core.tools import FunctionTool
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "precleared.llamaindex needs llama-index-core. Install it with: pip install 'precleared[llamaindex]'"
    ) from exc

from ._schemas import PreclearedCheckArgs, PreclearedVerifyReceiptArgs
from ._tools import (
    CHECK_DESCRIPTION,
    CHECK_TOOL_NAME,
    VERIFY_DESCRIPTION,
    VERIFY_TOOL_NAME,
    PreclearedTools,
)


def _check_tool(runner: PreclearedTools) -> FunctionTool:
    return FunctionTool.from_defaults(
        fn=runner.check,
        name=CHECK_TOOL_NAME,
        description=CHECK_DESCRIPTION,
        fn_schema=PreclearedCheckArgs,
    )


def _verify_tool(runner: PreclearedTools) -> FunctionTool:
    return FunctionTool.from_defaults(
        fn=runner.verify_receipt,
        name=VERIFY_TOOL_NAME,
        description=VERIFY_DESCRIPTION,
        fn_schema=PreclearedVerifyReceiptArgs,
    )


def precleared_check_tool(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> FunctionTool:
    """``precleared_check`` as a LlamaIndex ``FunctionTool``.

    Returns compact text by default. Pass ``to_dict=True`` for a dictionary.
    """
    return _check_tool(PreclearedTools(api_key, to_dict=to_dict, **client_kwargs))


def precleared_verify_receipt_tool(
    api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any
) -> FunctionTool:
    """``precleared_verify_receipt`` as a LlamaIndex ``FunctionTool``."""
    return _verify_tool(PreclearedTools(api_key, to_dict=to_dict, **client_kwargs))


def precleared_tools(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> List[FunctionTool]:
    """Both tools, sharing one client."""
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return [_check_tool(runner), _verify_tool(runner)]


__all__ = ["precleared_check_tool", "precleared_verify_receipt_tool", "precleared_tools"]
