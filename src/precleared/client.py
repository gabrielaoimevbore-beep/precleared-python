"""Sync and async clients for the Precleared REST API.

Both clients expose the same three calls:

* ``check(...)`` runs one cold-email legality check and returns a
  :class:`~precleared.models.CheckResult`.
* ``verify_receipt(id)`` fetches a signed receipt by id and returns a
  :class:`~precleared.models.Receipt`.
* ``health()`` returns the latest service pulse as a
  :class:`~precleared.models.Health`.

The API key is sent as ``Authorization: Bearer ...`` and is never logged,
printed or included in an exception.
"""

from __future__ import annotations

import email.utils
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import httpx

from ._version import __version__
from .errors import (
    DailyLimit,
    InvalidKey,
    InvalidRequest,
    NetworkError,
    PaymentRequired,
    PreclearedError,
    RateLimited,
    ReceiptNotFound,
    ServerError,
)
from .models import ADDRESS_SOURCES, DEFAULT_BASE_URL, CheckResult, Health, Receipt

DEFAULT_USER_AGENT = f"precleared-python/{__version__}"
DEFAULT_TIMEOUT = 30.0
ENV_API_KEY = "PRECLEARED_API_KEY"

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_RECEIPT_ID_RE = re.compile(r"cc_rcpt_[0-9A-Za-z]+")

Timeout = Union[float, int, httpx.Timeout, None]


# ---------------------------------------------------------------------------
# Request building and validation (shared by both clients)
# ---------------------------------------------------------------------------


def _resolve_api_key(api_key: Optional[str]) -> Optional[str]:
    if api_key is None:
        api_key = os.environ.get(ENV_API_KEY)
    if api_key is None:
        return None
    if not isinstance(api_key, str):
        raise TypeError("api_key must be a string or None")
    api_key = api_key.strip()
    return api_key or None


def _normalise_country(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a two-letter country code such as 'GB'")
    code = value.strip().upper()
    if not _COUNTRY_RE.match(code):
        raise ValueError(f"{name} must be a two-letter country code such as 'GB', got {value!r}")
    return code


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be True or False, got {value!r}")
    return value


def build_check_body(
    recipient_email: Optional[str] = None,
    *,
    recipient_domain: Optional[str] = None,
    pitch: Optional[str] = None,
    address_source: str = "unknown",
    sender_country: str = "GB",
    existing_customer: bool = False,
    pitch_relevant: Optional[bool] = None,
    company_number: Optional[Union[str, int]] = None,
    recipient_country: Optional[str] = None,
    default_recipient_country: Optional[str] = None,
    suppressed: Optional[bool] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Validate the check fields and build the JSON body.

    Raises :class:`ValueError` before anything is sent when a field is
    malformed. ``address_source`` is always sent (``unknown`` unless you say
    otherwise), so the caller's choice is explicit in every receipt.
    """
    recipient_email = recipient_email.strip() if isinstance(recipient_email, str) else recipient_email
    recipient_domain = recipient_domain.strip() if isinstance(recipient_domain, str) else recipient_domain
    if not recipient_email and not recipient_domain:
        raise ValueError("recipient_email or recipient_domain is required")
    if recipient_email is not None and not isinstance(recipient_email, str):
        raise ValueError("recipient_email must be a string")
    if recipient_domain is not None and not isinstance(recipient_domain, str):
        raise ValueError("recipient_domain must be a string")

    if not isinstance(address_source, str):
        raise ValueError(f"address_source must be one of {', '.join(ADDRESS_SOURCES)}, got {address_source!r}")
    source = address_source.strip().lower()
    if source not in ADDRESS_SOURCES:
        raise ValueError(f"address_source must be one of {', '.join(ADDRESS_SOURCES)}, got {address_source!r}")

    body: Dict[str, Any] = {}
    if recipient_email:
        body["recipient_email"] = recipient_email
    if recipient_domain:
        body["recipient_domain"] = recipient_domain
    body["sender_country"] = _normalise_country(sender_country, "sender_country")
    body["address_source"] = source
    body["existing_customer"] = _require_bool(existing_customer, "existing_customer")

    if pitch is not None:
        if not isinstance(pitch, str):
            raise ValueError("pitch must be a string")
        pitch = pitch.strip()
        if pitch:
            body["pitch"] = pitch
    if pitch_relevant is not None:
        body["pitch_relevant"] = _require_bool(pitch_relevant, "pitch_relevant")
    if company_number is not None:
        number = str(company_number).strip()
        if number:
            body["company_number"] = number
    if recipient_country is not None:
        body["recipient_country"] = _normalise_country(recipient_country, "recipient_country")
    if default_recipient_country is not None:
        body["default_recipient_country"] = _normalise_country(
            default_recipient_country, "default_recipient_country"
        )
    if suppressed is not None:
        body["suppressed"] = _require_bool(suppressed, "suppressed")

    for key, value in extra.items():
        if value is not None and key not in body:
            body[key] = value
    return body


def normalise_receipt_id(receipt_id: Any) -> str:
    """Accept a bare id or a receipt URL and return the ``cc_rcpt_...`` id."""
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise ValueError("receipt id is required, for example 'cc_rcpt_...'")
    value = receipt_id.strip()
    match = _RECEIPT_ID_RE.search(value)
    if match:
        return match.group(0)
    if "/" in value or "?" in value or "=" in value or " " in value:
        raise ValueError(f"not a receipt id: {receipt_id!r}")
    return value


# ---------------------------------------------------------------------------
# Response handling (shared by both clients)
# ---------------------------------------------------------------------------


def parse_retry_after(body_value: Any = None, header_value: Optional[str] = None) -> Optional[float]:
    """Turn ``retry_after`` (body) or ``Retry-After`` (header) into seconds.

    The header may be a number of seconds or an HTTP-date. Returns ``None``
    when neither is usable.
    """
    if body_value is not None and not isinstance(body_value, bool):
        if isinstance(body_value, (int, float)):
            return max(0.0, float(body_value))
        try:
            return max(0.0, float(str(body_value).strip()))
        except ValueError:
            pass
    if header_value is None:
        return None
    text = header_value.strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _safe_json_object(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def error_from_response(response: httpx.Response, *, receipt: bool = False) -> PreclearedError:
    """Map an error response to the matching exception (does not raise)."""
    status = response.status_code
    body = _safe_json_object(response)
    code = _string(body.get("error"))
    message = _string(body.get("message"))
    common: Dict[str, Any] = {"status_code": status, "body": body}

    if status == 400:
        return InvalidRequest(message or "Precleared rejected the request body.", code=code or "invalid_request", **common)
    if status == 401:
        return InvalidKey(message or "The API key is invalid or has been revoked.", code=code or "invalid_key", **common)
    if status == 402:
        return PaymentRequired(
            message or "Free daily checks are used and this key has no pack credits.",
            buy_url=_string(body.get("buy_url")),
            code=code or "payment_required",
            **common,
        )
    if status == 404 and receipt:
        return ReceiptNotFound(message or "No receipt has that id.", code=code or "not_found", **common)
    if status == 429:
        retry_after = parse_retry_after(body.get("retry_after"), response.headers.get("Retry-After"))
        if code == "daily_limit" or (code is None and "get_key_url" in body):
            return DailyLimit(
                message or "The free daily allowance is used up.",
                get_key_url=_string(body.get("get_key_url")),
                code="daily_limit",
                **common,
            )
        return RateLimited(
            message or "Too many checks: the limit is 60 a minute per key.",
            retry_after=retry_after,
            code=code or "rate_limited",
            **common,
        )
    if status >= 500:
        return ServerError(message or f"Precleared returned HTTP {status}.", code=code or "server_error", **common)
    return PreclearedError(message or f"Unexpected HTTP {status} from Precleared.", code=code, **common)


def parse_json_object(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise PreclearedError(
            "Precleared returned a response that is not JSON.",
            status_code=response.status_code,
            code="invalid_response",
        ) from exc
    if not isinstance(data, dict):
        raise PreclearedError(
            "Precleared returned JSON that is not an object.",
            status_code=response.status_code,
            code="invalid_response",
        )
    return data


def receipt_from_payload(data: Dict[str, Any]) -> Receipt:
    """Build a Receipt from the receipt endpoint's JSON, flat or wrapped."""
    inner = data.get("receipt")
    if isinstance(inner, dict) and (inner.get("id") or inner.get("receipt_id")):
        merged = dict(inner)
        for key in ("public_key", "key_version", "algorithm", "verify_url"):
            if key not in merged and key in data:
                merged[key] = data[key]
        receipt = Receipt.from_dict(merged)
        receipt.raw = dict(data)
        return receipt
    return Receipt.from_dict(data)


def _wrap_network_error(exc: httpx.HTTPError) -> NetworkError:
    name = type(exc).__name__
    detail = str(exc).strip()
    message = f"Could not reach Precleared ({name})" + (f": {detail}" if detail else ".")
    return NetworkError(message, code="network_error")


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


class _Base:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Timeout = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        self._api_key = _resolve_api_key(api_key)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def has_api_key(self) -> bool:
        """Whether requests carry a key. The key itself is never exposed."""
        return self._api_key is not None

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def __repr__(self) -> str:
        key = "<set>" if self._api_key else "None"
        return f"{type(self).__name__}(base_url={self.base_url!r}, api_key={key})"


class Precleared(_Base):
    """Synchronous client.

    Args:
        api_key: ``pc_live_...`` key. Optional: without one the keyless
            allowance applies (10 checks a day per network). Falls back to
            the ``PRECLEARED_API_KEY`` environment variable.
        base_url: API origin. Only change this for testing.
        timeout: Seconds to wait for a response. A check can take up to 25
            seconds when a register or website is slow.
        user_agent: Sent on every request. Precleared's hosting refuses
            requests without a User-Agent.
        transport: An ``httpx`` transport, for tests.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Timeout = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, timeout=timeout, user_agent=user_agent)
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._headers(),
            transport=transport,
        )

    def __enter__(self) -> Precleared:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, *, receipt: bool = False, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise _wrap_network_error(exc) from exc
        if response.status_code >= 400:
            raise error_from_response(response, receipt=receipt)
        return response

    def check(
        self,
        recipient_email: Optional[str] = None,
        *,
        recipient_domain: Optional[str] = None,
        pitch: Optional[str] = None,
        address_source: str = "unknown",
        sender_country: str = "GB",
        existing_customer: bool = False,
        pitch_relevant: Optional[bool] = None,
        company_number: Optional[Union[str, int]] = None,
        recipient_country: Optional[str] = None,
        default_recipient_country: Optional[str] = None,
        suppressed: Optional[bool] = None,
        **extra: Any,
    ) -> CheckResult:
        """Check whether a cold email may lawfully be sent to one address.

        Args:
            recipient_email: The address you want to email. One of this or
                ``recipient_domain`` is required.
            recipient_domain: Check a domain when you do not have an address yet.
            pitch: What you are offering, in a sentence.
            address_source: How you got the address: ``published``, ``bought``,
                ``scraped``, ``given`` or ``unknown``. Defaults to ``unknown``.
                Only say ``published`` when the recipient put the address on
                their own website or a public listing for people to contact them.
            sender_country: Two-letter code for where you send from. Default ``GB``.
            existing_customer: True if the recipient has bought from you.
            pitch_relevant: Whether the pitch relates to the recipient's role.
            company_number: UK Companies House number, when you know it.
            recipient_country: Two-letter code. Overrides what Precleared infers.
            default_recipient_country: Used only when the country cannot be
                worked out from the address, register or website.
            suppressed: True if the address is on your own suppression list.
            **extra: Forwarded as is, for request fields newer than this client.

        Raises:
            ValueError: for a malformed field, before anything is sent.
            PreclearedError: a subclass per API error, see :mod:`precleared.errors`.
        """
        body = build_check_body(
            recipient_email,
            recipient_domain=recipient_domain,
            pitch=pitch,
            address_source=address_source,
            sender_country=sender_country,
            existing_customer=existing_customer,
            pitch_relevant=pitch_relevant,
            company_number=company_number,
            recipient_country=recipient_country,
            default_recipient_country=default_recipient_country,
            suppressed=suppressed,
            **extra,
        )
        response = self._request("POST", "/api/v1/check", json=body)
        return CheckResult.from_dict(parse_json_object(response), base_url=self.base_url)

    def verify_receipt(self, receipt_id: str) -> Receipt:
        """Fetch a signed receipt by id (``cc_rcpt_...``) or receipt URL.

        Raises :class:`~precleared.errors.ReceiptNotFound` when no receipt
        has that id.
        """
        rid = normalise_receipt_id(receipt_id)
        response = self._request("GET", "/api/v1/receipt", params={"id": rid}, receipt=True)
        return receipt_from_payload(parse_json_object(response))

    def health(self) -> Health:
        """Return the latest five-minute health pulse."""
        response = self._request("GET", "/api/v1/health")
        return Health.from_dict(parse_json_object(response))


class AsyncPrecleared(_Base):
    """Asynchronous client with the same surface as :class:`Precleared`."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Timeout = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, timeout=timeout, user_agent=user_agent)
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._headers(),
            transport=transport,
        )

    async def __aenter__(self) -> AsyncPrecleared:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, receipt: bool = False, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise _wrap_network_error(exc) from exc
        if response.status_code >= 400:
            raise error_from_response(response, receipt=receipt)
        return response

    async def check(
        self,
        recipient_email: Optional[str] = None,
        *,
        recipient_domain: Optional[str] = None,
        pitch: Optional[str] = None,
        address_source: str = "unknown",
        sender_country: str = "GB",
        existing_customer: bool = False,
        pitch_relevant: Optional[bool] = None,
        company_number: Optional[Union[str, int]] = None,
        recipient_country: Optional[str] = None,
        default_recipient_country: Optional[str] = None,
        suppressed: Optional[bool] = None,
        **extra: Any,
    ) -> CheckResult:
        """Async version of :meth:`Precleared.check`."""
        body = build_check_body(
            recipient_email,
            recipient_domain=recipient_domain,
            pitch=pitch,
            address_source=address_source,
            sender_country=sender_country,
            existing_customer=existing_customer,
            pitch_relevant=pitch_relevant,
            company_number=company_number,
            recipient_country=recipient_country,
            default_recipient_country=default_recipient_country,
            suppressed=suppressed,
            **extra,
        )
        response = await self._request("POST", "/api/v1/check", json=body)
        return CheckResult.from_dict(parse_json_object(response), base_url=self.base_url)

    async def verify_receipt(self, receipt_id: str) -> Receipt:
        """Async version of :meth:`Precleared.verify_receipt`."""
        rid = normalise_receipt_id(receipt_id)
        response = await self._request("GET", "/api/v1/receipt", params={"id": rid}, receipt=True)
        return receipt_from_payload(parse_json_object(response))

    async def health(self) -> Health:
        """Async version of :meth:`Precleared.health`."""
        response = await self._request("GET", "/api/v1/health")
        return Health.from_dict(parse_json_object(response))


__all__ = [
    "AsyncPrecleared",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
    "ENV_API_KEY",
    "Precleared",
    "build_check_body",
    "error_from_response",
    "normalise_receipt_id",
    "parse_retry_after",
    # Re-exported so ``from precleared.client import InvalidKey`` works too.
    "PreclearedError",
    "InvalidRequest",
    "InvalidKey",
    "PaymentRequired",
    "DailyLimit",
    "RateLimited",
    "ReceiptNotFound",
    "ServerError",
    "NetworkError",
]
