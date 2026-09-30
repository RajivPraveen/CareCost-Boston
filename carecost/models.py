from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def money(value) -> Decimal:
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError("Amount must be numeric") from exc
    if not result.is_finite():
        raise ValueError("Amount must be finite")
    try:
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Amount is outside supported precision") from exc


def stable_id(*values) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()[:32]


class Price(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hospital_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    code_type: Literal["CPT", "HCPCS"]
    description: str = Field(min_length=1)
    setting: Literal["inpatient", "outpatient", "both"]
    billing_class: Literal["facility", "professional", "both", "unknown"] = "unknown"
    modifiers: str = ""
    service_id: str
    price_type: Literal["cash", "gross", "negotiated"]
    payer: str = ""
    plan: str = ""
    amount: Decimal = Field(gt=0, le=1_000_000)
    source_url: str
    source_date: date
    source_sha256: str
    source_row: int = Field(ge=1)
    is_demo: bool = False
    notes: str = ""

    @field_validator("code")
    @classmethod
    def code_format(cls, value):
        value = str(value).strip().upper()
        if not re.fullmatch(r"(?:\d{5}|[A-Z]\d{4}|\d{4}[A-Z])", value):
            raise ValueError("Unsupported CPT/HCPCS code shape")
        return value

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_money(cls, value):
        return money(value)

    @property
    def price_id(self):
        # Include context and service identity; distinct bundles must not collapse.
        return stable_id(
            self.hospital_id,
            self.service_id,
            self.code_type,
            self.code,
            self.setting,
            self.billing_class,
            self.modifiers,
            self.price_type,
            self.payer,
            self.plan,
            self.amount,
            self.source_date,
            self.source_sha256,
        )


class BillLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=1000)
    code: str = ""
    code_type: Literal["CPT", "HCPCS", "unknown"] = "unknown"
    quantity: Decimal = Field(gt=0, le=100_000)
    charge: Decimal = Field(ge=0, le=10_000_000)
    service_date: date | None = None
    modifiers: str = ""
    evidence: str = Field(default="", max_length=2000)

    @field_validator("charge", mode="before")
    @classmethod
    def normalize_charge(cls, value):
        return money(value)

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value):
        if not value.is_finite():
            raise ValueError("Quantity must be finite")
        return value

    @field_validator("code", "modifiers", mode="before")
    @classmethod
    def clean_code(cls, value):
        return str(value or "").strip().upper()


class ExtractedBill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[BillLine] = Field(max_length=300)
