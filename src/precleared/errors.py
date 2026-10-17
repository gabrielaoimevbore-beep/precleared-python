"""Exceptions raised by the Precleared client.

Every error raised after a request has been sent is a subclass of
:class:`PreclearedError`. Bad arguments are reported before any request is
made, as a plain :class:`ValueError`.

None of these exceptions ever carries the API key or the request headers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class PreclearedError(Exception):
    """Base class for every error raised by the client after a request.

    Attributes:
        message: Plain-English description, taken from the API when it sent one.
        status_code: HTTP status of the response, or ``None`` for network errors.
        code: The API's short error code (for example ``daily_limit``), if any.
        body: The parsed JSON error body, if the API sent one.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.body = body if body is not None else {}

    def __str__(self) -> str:
        return self.message


class InvalidRequest(PreclearedError):
    """HTTP 400: the API rejected the request body. The message names the field."""


class InvalidKey(PreclearedError):
    """HTTP 401: the key is wrong (``invalid_key``) or has been revoked (``revoked_key``)."""


class PaymentRequired(PreclearedError):
    """HTTP 402: the free daily checks are used and the key has no pack credits.

    Attributes:
        buy_url: Checkout link for a pack on this key (GBP 39 for 2,000 checks).
    """

    def __init__(self, message: str, *, buy_url: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.buy_url = buy_url


class DailyLimit(PreclearedError):
    """HTTP 429 ``daily_limit``: the free daily allowance is used up.

    Keyless use allows 10 REST checks a day, shared by everyone on the same
    network. A free key allows 25 a day.

    Attributes:
        get_key_url: Where to get a free key.
    """

    def __init__(self, message: str, *, get_key_url: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.get_key_url = get_key_url


class RateLimited(PreclearedError):
    """HTTP 429 ``rate_limited``: more than 60 checks a minute on one key.

    Attributes:
        retry_after: Seconds to wait before trying again, when the API said.
    """

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ReceiptNotFound(PreclearedError):
    """HTTP 404 from the receipt endpoint: no receipt has that id."""


class ServerError(PreclearedError):
    """HTTP 5xx: Precleared itself failed. Safe to retry after a short wait."""


class NetworkError(PreclearedError):
    """The request never completed: DNS, connection or timeout failure.

    The underlying ``httpx`` exception is available as ``__cause__``.
    """


__all__ = [
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
