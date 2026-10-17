"""Typed views over the JSON the Precleared API returns.

Every model keeps the full response under ``.raw`` so nothing is lost when
the API adds fields this version does not know about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_BASE_URL = "https://precleared.dev"

VERDICTS = ("ok_to_email", "consent_needed", "blocked", "unknown")
ADDRESS_SOURCES = ("published", "bought", "scraped", "given", "unknown")


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _opt_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


@dataclass
class Reason:
    """One entry in ``CheckResult.reasons``.

    A reason is either the rule that decided the verdict (``rule_key``,
    ``text`` and a source) or a note about the facts (``note``).
    """

    rule_key: Optional[str] = None
    text: Optional[str] = None
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    note: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Reason:
        if isinstance(data, str):
            return cls(note=data, raw={"note": data})
        if not isinstance(data, dict):
            return cls(raw={})
        return cls(
            rule_key=_opt_str(data.get("rule_key")),
            text=_opt_str(data.get("text")),
            source_title=_opt_str(data.get("source_title")),
            source_url=_opt_str(data.get("source_url")),
            note=_opt_str(data.get("note")),
            raw=dict(data),
        )

    def describe(self) -> str:
        """One line of plain text for a model or a log."""
        parts: List[str] = []
        if self.text:
            parts.append(self.text)
        elif self.note:
            parts.append(self.note)
        if self.source_title and self.source_url:
            parts.append(f"Source: {self.source_title}, {self.source_url}")
        elif self.source_url:
            parts.append(f"Source: {self.source_url}")
        elif self.source_title:
            parts.append(f"Source: {self.source_title}")
        return " ".join(parts)


@dataclass
class Receipt:
    """A signed record that a check happened and what it said.

    Returned inside every check response and by ``verify_receipt``. The
    receipt endpoint also returns the verdict the check gave, the masked
    address and the Ed25519 public key; those fields are ``None`` on the
    receipt embedded in a check response.

    The signature is Ed25519 over the string ``request_hash.response_hash``;
    the public key is served at ``/api/v1/public-key``.
    """

    id: str
    created_at: Optional[str] = None
    request_hash: Optional[str] = None
    response_hash: Optional[str] = None
    signature: Optional[str] = None
    algorithm: Optional[str] = None
    key_version: Optional[str] = None
    verify_url: Optional[str] = None
    public_key: Optional[str] = None
    verdict: Optional[str] = None
    confidence: Optional[str] = None
    rules_applied: List[str] = field(default_factory=list)
    recipient_domain: Optional[str] = None
    recipient_email_masked: Optional[str] = None
    sender_country: Optional[str] = None
    rules_version: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    _SUMMARY_FIELDS = (
        "created_at",
        "verdict",
        "confidence",
        "rules_applied",
        "recipient_email_masked",
        "recipient_domain",
        "sender_country",
        "rules_version",
        "request_hash",
        "response_hash",
        "signature",
        "algorithm",
        "key_version",
        "verify_url",
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Receipt:
        if not isinstance(data, dict):
            raise TypeError("receipt must be a JSON object")
        receipt_id = data.get("id") or data.get("receipt_id")
        if not receipt_id:
            raise ValueError("receipt has no id")
        rules_raw = data.get("rules_applied")
        return cls(
            id=str(receipt_id),
            created_at=_opt_str(data.get("created_at")),
            request_hash=_opt_str(data.get("request_hash")),
            response_hash=_opt_str(data.get("response_hash")),
            signature=_opt_str(data.get("signature")),
            algorithm=_opt_str(data.get("algorithm")),
            key_version=_opt_str(data.get("key_version")),
            verify_url=_opt_str(data.get("verify_url")),
            public_key=_opt_str(data.get("public_key")),
            verdict=_opt_str(data.get("verdict")),
            confidence=_opt_str(data.get("confidence")),
            rules_applied=[str(item) for item in rules_raw] if isinstance(rules_raw, list) else [],
            recipient_domain=_opt_str(data.get("recipient_domain")),
            recipient_email_masked=_opt_str(data.get("recipient_email_masked")),
            sender_country=_opt_str(data.get("sender_country")),
            rules_version=_opt_str(data.get("rules_version")),
            raw=dict(data),
        )

    def page_url(self, base_url: str = DEFAULT_BASE_URL) -> str:
        """Human-readable receipt page, ``https://precleared.dev/r/<id>``."""
        return f"{base_url.rstrip('/')}/r/{self.id}"

    def summary(self) -> Dict[str, Any]:
        """Compact dictionary for structured tool output (no public key)."""
        out: Dict[str, Any] = {"receipt_id": self.id}
        for name in self._SUMMARY_FIELDS:
            value = getattr(self, name)
            if value is None or value == []:
                continue
            out[name] = value
        return out

    def summary_text(self) -> str:
        """Compact text for a model: one ``name: value`` line per known field."""
        lines = [f"receipt: {self.id}"]
        for name, value in self.summary().items():
            if name == "receipt_id":
                continue
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            lines.append(f"{name}: {value}")
        return "\n".join(lines)


@dataclass
class Usage:
    """Allowance information returned with every check."""

    free_remaining_today: Optional[int] = None
    credits_remaining: Optional[int] = None
    low_balance: Optional[bool] = None
    top_up_url: Optional[str] = None
    notice: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Usage:
        if not isinstance(data, dict):
            return cls(raw={})
        return cls(
            free_remaining_today=_opt_int(data.get("free_remaining_today")),
            credits_remaining=_opt_int(data.get("credits_remaining")),
            low_balance=_opt_bool(data.get("low_balance")),
            top_up_url=_opt_str(data.get("top_up_url")),
            notice=_opt_str(data.get("notice")),
            raw=dict(data),
        )


@dataclass
class Health:
    """Result of ``GET /api/v1/health``: the latest five-minute pulse."""

    status: str
    checked_at: Optional[str] = None
    api_ok: Optional[bool] = None
    mcp_ok: Optional[bool] = None
    worker_ok: Optional[bool] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @classmethod
    def from_dict(cls, data: Any) -> Health:
        if not isinstance(data, dict):
            raise TypeError("health must be a JSON object")
        return cls(
            status=str(data.get("status") or "unknown"),
            checked_at=_opt_str(data.get("checked_at")),
            api_ok=_opt_bool(data.get("api_ok")),
            mcp_ok=_opt_bool(data.get("mcp_ok")),
            worker_ok=_opt_bool(data.get("worker_ok")),
            raw=dict(data),
        )


@dataclass
class CheckResult:
    """The answer to one check.

    Attributes:
        verdict: ``ok_to_email``, ``consent_needed``, ``blocked`` or ``unknown``.
        confidence: ``high``, ``medium`` or ``low``.
        reasons: The rule that decided the verdict, with its source, plus notes.
        rules_applied: Rule keys used, in order.
        footer_text: What the email footer must include. A requirement to
            meet, not wording to paste.
        next_step: One line on what to do next.
        facts: What Precleared established about the address and company.
        receipt: Signed receipt for this check.
        usage: Remaining free checks and pack credits.
        disclaimer: Fixed line: decision support with sources, not legal advice.
        rules_version: Version of the rule set used.
        raw: The full response as returned by the API.
    """

    verdict: str
    confidence: Optional[str] = None
    reasons: List[Reason] = field(default_factory=list)
    rules_applied: List[str] = field(default_factory=list)
    footer_text: Optional[str] = None
    next_step: Optional[str] = None
    facts: Dict[str, Any] = field(default_factory=dict)
    receipt: Optional[Receipt] = None
    usage: Optional[Usage] = None
    disclaimer: Optional[str] = None
    rules_version: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    base_url: str = field(default=DEFAULT_BASE_URL, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, base_url: str = DEFAULT_BASE_URL) -> CheckResult:
        if not isinstance(data, dict):
            raise TypeError("check response must be a JSON object")
        verdict = data.get("verdict")
        if not isinstance(verdict, str) or not verdict:
            raise ValueError("check response has no verdict")

        reasons_raw = data.get("reasons")
        reasons = [Reason.from_dict(item) for item in reasons_raw] if isinstance(reasons_raw, list) else []

        rules_raw = data.get("rules_applied")
        rules_applied = [str(item) for item in rules_raw] if isinstance(rules_raw, list) else []

        receipt_raw = data.get("receipt")
        receipt = None
        if isinstance(receipt_raw, dict) and (receipt_raw.get("id") or receipt_raw.get("receipt_id")):
            receipt = Receipt.from_dict(receipt_raw)

        facts = data.get("facts")

        return cls(
            verdict=verdict,
            confidence=_opt_str(data.get("confidence")),
            reasons=reasons,
            rules_applied=rules_applied,
            footer_text=_opt_str(data.get("footer_text")),
            next_step=_opt_str(data.get("next_step")),
            facts=dict(facts) if isinstance(facts, dict) else {},
            receipt=receipt,
            usage=Usage.from_dict(data["usage"]) if isinstance(data.get("usage"), dict) else None,
            disclaimer=_opt_str(data.get("disclaimer")),
            rules_version=_opt_str(data.get("rules_version")),
            raw=dict(data),
            base_url=base_url,
        )

    # Convenience views -------------------------------------------------

    @property
    def ok(self) -> bool:
        """True when the verdict is ``ok_to_email``."""
        return self.verdict == "ok_to_email"

    @property
    def must_not_send(self) -> bool:
        """True for ``consent_needed`` and ``blocked``.

        ``unknown`` is not included here on purpose: it means a fact could not
        be established. Treat it as ``consent_needed`` unless you can supply
        the missing fact and check again. See :attr:`needs_more_facts`.
        """
        return self.verdict in ("consent_needed", "blocked")

    @property
    def needs_more_facts(self) -> bool:
        """True when the verdict is ``unknown``."""
        return self.verdict == "unknown"

    @property
    def rule(self) -> Optional[str]:
        """``rule_key`` of the first reason, which is the rule that decided."""
        for reason in self.reasons:
            if reason.rule_key:
                return reason.rule_key
        return None

    @property
    def reason(self) -> Optional[Reason]:
        """The reason that carries the rule that decided the verdict, if any."""
        for reason in self.reasons:
            if reason.rule_key:
                return reason
        return None

    @property
    def notes(self) -> List[str]:
        """Notes from the reasons list: every entry that is not the rule."""
        out: List[str] = []
        for item in self.reasons:
            if item.rule_key:
                continue
            text = item.note or item.text
            if text:
                out.append(text)
        return out

    @property
    def receipt_id(self) -> Optional[str]:
        return self.receipt.id if self.receipt else None

    @property
    def receipt_url(self) -> Optional[str]:
        """Receipt page, ``https://precleared.dev/r/<id>``, or ``None``."""
        if self.receipt is None:
            return None
        return self.receipt.page_url(self.base_url)

    def summary(self) -> Dict[str, Any]:
        """Compact dictionary with what a sending agent needs to decide."""
        reason = self.reason
        out: Dict[str, Any] = {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "rule": self.rule,
            "reason": (reason.text or reason.note) if reason else None,
            "source_title": reason.source_title if reason else None,
            "source_url": reason.source_url if reason else None,
            "notes": self.notes,
            "footer_text": self.footer_text,
            "next_step": self.next_step,
            "receipt_id": self.receipt_id,
            "receipt_url": self.receipt_url,
        }
        if self.usage is not None:
            out["free_remaining_today"] = self.usage.free_remaining_today
            out["credits_remaining"] = self.usage.credits_remaining
        if self.disclaimer:
            out["disclaimer"] = self.disclaimer
        return out

    def summary_text(self) -> str:
        """Compact text for a model: verdict, rule, footer_text, next_step, receipt."""
        lines = [f"verdict: {self.verdict}" + (f" (confidence: {self.confidence})" if self.confidence else "")]
        if self.rule:
            lines.append(f"rule: {self.rule}")
        reason = self.reason
        if reason is not None:
            described = reason.describe()
            if described:
                lines.append(f"reason: {described}")
        for note in self.notes:
            lines.append(f"note: {note}")
        if self.footer_text:
            lines.append(f"footer_text: {self.footer_text}")
        if self.next_step:
            lines.append(f"next_step: {self.next_step}")
        if self.receipt is not None:
            lines.append(f"receipt: {self.receipt.id} {self.receipt_url}")
        return "\n".join(lines)


__all__ = [
    "ADDRESS_SOURCES",
    "DEFAULT_BASE_URL",
    "VERDICTS",
    "CheckResult",
    "Health",
    "Reason",
    "Receipt",
    "Usage",
]
