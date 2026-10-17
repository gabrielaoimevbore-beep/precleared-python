"""Pydantic argument models shared by the LangChain, CrewAI and LlamaIndex
adapters. Imported only by those adapters, so the core package does not
need pydantic.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ._tools import ARG_DESCRIPTIONS as _D


class PreclearedCheckArgs(BaseModel):
    """Arguments for ``precleared_check``."""

    recipient_email: Optional[str] = Field(default=None, description=_D["recipient_email"])
    recipient_domain: Optional[str] = Field(default=None, description=_D["recipient_domain"])
    pitch: Optional[str] = Field(default=None, description=_D["pitch"])
    address_source: str = Field(default="unknown", description=_D["address_source"])
    existing_customer: bool = Field(default=False, description=_D["existing_customer"])
    pitch_relevant: Optional[bool] = Field(default=None, description=_D["pitch_relevant"])
    sender_country: str = Field(default="GB", description=_D["sender_country"])
    recipient_country: Optional[str] = Field(default=None, description=_D["recipient_country"])
    company_number: Optional[str] = Field(default=None, description=_D["company_number"])
    suppressed: Optional[bool] = Field(default=None, description=_D["suppressed"])


class PreclearedVerifyReceiptArgs(BaseModel):
    """Arguments for ``precleared_verify_receipt``."""

    receipt_id: str = Field(description=_D["receipt_id"])


__all__ = ["PreclearedCheckArgs", "PreclearedVerifyReceiptArgs"]
