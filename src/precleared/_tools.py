"""Framework-neutral logic behind the LangChain, CrewAI, LlamaIndex and
OpenAI Agents adapters: tool names, descriptions, argument descriptions and
the two functions the tools call.

This module depends only on the core client, so it imports without any
framework installed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

import httpx

from .client import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, Precleared, Timeout
from .errors import DailyLimit, PaymentRequired, PreclearedError, RateLimited
from .models import ADDRESS_SOURCES, DEFAULT_BASE_URL

CHECK_TOOL_NAME = "precleared_check"
VERIFY_TOOL_NAME = "precleared_verify_receipt"

# Kept under 1024 characters: the OpenAI limit for a function description,
# which LlamaIndex and the Agents SDK enforce.
CHECK_DESCRIPTION = (
    "Check whether a cold or marketing email to one recipient is legal. "
    "Call this once per address before the first cold email to anyone who is not already a customer, "
    "in the UK, US, Canada, Germany, France, Australia, Ireland or the Netherlands, including every "
    "address in a lead list. Not needed for transactional email such as invoices or password resets. "
    "It applies the local rules (UK PECR, US CAN-SPAM, Canadian CASL and others) using live lookups "
    "such as UK Companies House. Returns a verdict, the rule that decided it with its source, "
    "footer_text, next_step and a signed receipt id. ok_to_email means send, with a footer that meets "
    "footer_text (a requirement, not wording to paste). consent_needed and blocked mean do not send; "
    "follow next_step. unknown means a fact could not be established: treat it as consent_needed unless "
    "you can supply the missing fact (such as recipient_country or company_number) and check again. "
    "Nothing is sent to the recipient. Decision support with sources, not legal advice."
)

VERIFY_DESCRIPTION = (
    "Fetch a Precleared receipt by its id (cc_rcpt_...) to show that a cold-email check happened and what "
    "it said. Use it when a client, auditor or regulator asks for evidence of a check, or to re-read a past "
    "verdict without spending another check. Returns the receipt id, time, request and response hashes, "
    "Ed25519 signature and verification URL. Does not run a new check and sends nothing to anyone."
)

ARG_DESCRIPTIONS: Dict[str, str] = {
    "recipient_email": "The address you want to email. Give this or recipient_domain.",
    "recipient_domain": "The recipient's domain when you have no address yet, for example acme.co.uk.",
    "pitch": "What you are offering, in one sentence.",
    "address_source": (
        "How the address was obtained: published (the recipient put it on their own website or a public "
        "listing so people can contact them), bought (from a data vendor or list), scraped (collected from "
        "the web by a tool), given (the recipient gave it to you directly) or unknown. "
        "Use unknown when you are not sure. Never guess published."
    ),
    "existing_customer": "True only if the recipient has bought from the sender before.",
    "pitch_relevant": (
        "True if the pitch relates to the recipient's role or business, false if it does not. "
        "Leave unset when unsure."
    ),
    "sender_country": "Two-letter code for where the sender is based, for example GB or US. Default GB.",
    "recipient_country": (
        "Two-letter country code for the recipient when you know it. Otherwise Precleared works it out "
        "from the domain, the register and the website."
    ),
    "company_number": (
        "UK Companies House number when known. Raises confidence for UK recipients and can resolve an "
        "unknown verdict."
    ),
    "suppressed": "True if the address is on the sender's own suppression or unsubscribe list.",
    "receipt_id": "Receipt id from a previous check, starting cc_rcpt_. A receipt URL also works.",
}

_TRUE = {"true", "yes", "y", "1", "on"}
_FALSE = {"false", "no", "n", "0", "off"}


def coerce_bool(value: Any, name: str) -> Optional[bool]:
    """Models sometimes send booleans as strings. Accept the obvious forms."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "":
            return None
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise ValueError(f"{name} must be true or false, got {value!r}")


def _blank_to_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def error_payload(exc: Exception) -> Dict[str, Any]:
    """Structured description of a failure, safe to hand to a model."""
    if isinstance(exc, PreclearedError):
        payload: Dict[str, Any] = {
            "error": exc.code or type(exc).__name__,
            "message": exc.message,
        }
        if exc.status_code is not None:
            payload["status_code"] = exc.status_code
        if isinstance(exc, RateLimited) and exc.retry_after is not None:
            payload["retry_after"] = exc.retry_after
        if isinstance(exc, PaymentRequired) and exc.buy_url:
            payload["buy_url"] = exc.buy_url
        if isinstance(exc, DailyLimit) and exc.get_key_url:
            payload["get_key_url"] = exc.get_key_url
        return payload
    return {"error": "invalid_arguments", "message": str(exc)}


def format_error(payload: Dict[str, Any]) -> str:
    lines = [f"error: {payload.get('error')}", f"message: {payload.get('message')}"]
    for key in ("retry_after", "buy_url", "get_key_url"):
        if key in payload:
            lines.append(f"{key}: {payload[key]}")
    lines.append("Do not send until a check succeeds.")
    return "\n".join(lines)


class PreclearedTools:
    """The two tool functions, bound to one client.

    Every framework adapter builds its tool objects around an instance of
    this class. ``check`` and ``verify_receipt`` never raise for API
    failures: they return an error description so the model can react
    (wait, get a key, fix an argument). Bad arguments are reported the same
    way.

    Args:
        api_key: Optional ``pc_live_...`` key, or ``None`` for keyless use.
        to_dict: Return compact dictionaries instead of compact text.
        client: An existing :class:`~precleared.Precleared` to reuse.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        to_dict: bool = False,
        client: Optional[Precleared] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Timeout = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.client = (
            client
            if client is not None
            else Precleared(
                api_key, base_url=base_url, timeout=timeout, user_agent=user_agent, transport=transport
            )
        )
        self.to_dict = bool(to_dict)

    def _failure(self, exc: Exception) -> Union[str, Dict[str, Any]]:
        payload = error_payload(exc)
        return payload if self.to_dict else format_error(payload)

    def check(
        self,
        recipient_email: Optional[str] = None,
        recipient_domain: Optional[str] = None,
        pitch: Optional[str] = None,
        address_source: Optional[str] = "unknown",
        existing_customer: Optional[bool] = False,
        pitch_relevant: Optional[bool] = None,
        sender_country: Optional[str] = "GB",
        recipient_country: Optional[str] = None,
        company_number: Optional[str] = None,
        suppressed: Optional[bool] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Run one check and return compact text (or a dict when ``to_dict``)."""
        try:
            source = _blank_to_none(address_source) or "unknown"
            result = self.client.check(
                _blank_to_none(recipient_email),
                recipient_domain=_blank_to_none(recipient_domain),
                pitch=_blank_to_none(pitch),
                address_source=source,
                sender_country=_blank_to_none(sender_country) or "GB",
                existing_customer=coerce_bool(existing_customer, "existing_customer") or False,
                pitch_relevant=coerce_bool(pitch_relevant, "pitch_relevant"),
                company_number=_blank_to_none(company_number),
                recipient_country=_blank_to_none(recipient_country),
                suppressed=coerce_bool(suppressed, "suppressed"),
            )
        except (PreclearedError, ValueError) as exc:
            return self._failure(exc)
        return result.summary() if self.to_dict else result.summary_text()

    def verify_receipt(self, receipt_id: str) -> Union[str, Dict[str, Any]]:
        """Fetch one receipt and return compact text (or a dict when ``to_dict``)."""
        try:
            receipt = self.client.verify_receipt(receipt_id)
        except (PreclearedError, ValueError) as exc:
            return self._failure(exc)
        if self.to_dict:
            out = receipt.summary()
            out["receipt_url"] = receipt.page_url(self.client.base_url)
            return out
        return receipt.summary_text() + f"\nreceipt_url: {receipt.page_url(self.client.base_url)}"


def google_docstring(summary: str, params: Dict[str, str]) -> str:
    """Build a Google-style docstring so frameworks that read docstrings
    (OpenAI Agents SDK) get the same argument descriptions as the others."""
    lines = [summary, "", "Args:"]
    for name, text in params.items():
        lines.append(f"    {name}: {text}")
    return "\n".join(lines)


__all__ = [
    "ADDRESS_SOURCES",
    "ARG_DESCRIPTIONS",
    "CHECK_DESCRIPTION",
    "CHECK_TOOL_NAME",
    "VERIFY_DESCRIPTION",
    "VERIFY_TOOL_NAME",
    "PreclearedTools",
    "coerce_bool",
    "error_payload",
    "format_error",
    "google_docstring",
]
