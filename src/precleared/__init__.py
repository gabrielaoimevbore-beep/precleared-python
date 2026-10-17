"""Precleared: a cold-email legality check for AI agents.

One check per recipient, before the first cold email::

    from precleared import Precleared

    result = Precleared().check("jane@acme.co.uk", pitch="Bookkeeping software", address_source="unknown")
    if result.ok:
        ...  # send, with a footer that meets result.footer_text

Decision support with sources, not legal advice.
"""

from ._version import __version__
from .client import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, AsyncPrecleared, Precleared
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
from .models import (
    ADDRESS_SOURCES,
    DEFAULT_BASE_URL,
    VERDICTS,
    CheckResult,
    Health,
    Reason,
    Receipt,
    Usage,
)

__all__ = [
    "__version__",
    # Clients
    "Precleared",
    "AsyncPrecleared",
    # Models
    "CheckResult",
    "Receipt",
    "Reason",
    "Usage",
    "Health",
    # Errors
    "PreclearedError",
    "InvalidRequest",
    "InvalidKey",
    "PaymentRequired",
    "DailyLimit",
    "RateLimited",
    "ReceiptNotFound",
    "ServerError",
    "NetworkError",
    # Constants
    "ADDRESS_SOURCES",
    "VERDICTS",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
]
