"""CrewAI tools for Precleared.

Requires the ``crewai`` extra::

    pip install "precleared[crewai]"

Usage::

    from precleared.crewai import PreclearedCheckTool, PreclearedVerifyReceiptTool

    agent = Agent(role="SDR", goal="...", backstory="...",
                  tools=[PreclearedCheckTool(), PreclearedVerifyReceiptTool()])

The API key is held privately and does not appear in the tool's repr or
``model_dump()``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, Union

try:
    from crewai.tools import BaseTool
except ImportError:  # pragma: no cover - depends on the installed CrewAI version
    try:
        from crewai_tools import BaseTool  # type: ignore[no-redef]
    except ImportError as exc:
        raise ImportError(
            "precleared.crewai needs crewai. Install it with: pip install 'precleared[crewai]'"
        ) from exc

from pydantic import BaseModel, PrivateAttr

from ._schemas import PreclearedCheckArgs, PreclearedVerifyReceiptArgs
from ._tools import (
    CHECK_DESCRIPTION,
    CHECK_TOOL_NAME,
    VERIFY_DESCRIPTION,
    VERIFY_TOOL_NAME,
    PreclearedTools,
)


_CLIENT_KWARGS = ("base_url", "timeout", "user_agent", "transport")


class _PreclearedBaseTool(BaseTool):
    """Shared plumbing. ``api_key`` is passed to ``__init__`` but is not a
    pydantic field, so it never shows up in ``repr()`` or ``model_dump()``."""

    to_dict: bool = False
    _runner: PreclearedTools = PrivateAttr()

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        to_dict: bool = False,
        client: Any = None,
        **data: Any,
    ) -> None:
        client_kwargs = {k: data.pop(k) for k in _CLIENT_KWARGS if k in data}
        super().__init__(to_dict=to_dict, **data)
        self._runner = PreclearedTools(api_key, to_dict=to_dict, client=client, **client_kwargs)


class PreclearedCheckTool(_PreclearedBaseTool):
    """``precleared_check``: is it legal to cold-email this recipient?"""

    name: str = CHECK_TOOL_NAME
    description: str = CHECK_DESCRIPTION
    args_schema: Type[BaseModel] = PreclearedCheckArgs

    def _run(self, **kwargs: Any) -> Union[str, Dict[str, Any]]:
        return self._runner.check(**kwargs)


class PreclearedVerifyReceiptTool(_PreclearedBaseTool):
    """``precleared_verify_receipt``: fetch a signed receipt by id."""

    name: str = VERIFY_TOOL_NAME
    description: str = VERIFY_DESCRIPTION
    args_schema: Type[BaseModel] = PreclearedVerifyReceiptArgs

    def _run(self, receipt_id: str = "", **kwargs: Any) -> Union[str, Dict[str, Any]]:
        return self._runner.verify_receipt(receipt_id)


def precleared_tools(api_key: Optional[str] = None, *, to_dict: bool = False, **client_kwargs: Any) -> List[BaseTool]:
    """Both tools, sharing one client."""
    runner = PreclearedTools(api_key, to_dict=to_dict, **client_kwargs)
    return [
        PreclearedCheckTool(client=runner.client, to_dict=to_dict),
        PreclearedVerifyReceiptTool(client=runner.client, to_dict=to_dict),
    ]


__all__ = ["PreclearedCheckTool", "PreclearedVerifyReceiptTool", "precleared_tools"]
