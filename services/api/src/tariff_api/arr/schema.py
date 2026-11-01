"""The ARR candidate (ARR spec section 1, ADR-0018): what the commission printed for one
licensee, line item, fiscal year and voice in one order, with the evidence that shows it.
Stored in the shared ``candidates`` envelope with ``payload_kind = 'arr'``; the same model is
the tool schema an ARR channel returns.  Exact decimals as strings, the printed unit and
column heading kept beside the canonical value, never a number the order did not print."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..tariff_schema import EvidenceRef

ARR_SCHEMA_VERSION = "arr-1"
FY_RE = re.compile(r"^FY\d{4}-\d{2}$")

ValueType = Literal["petitioned", "approved", "provisional_true_up", "final_true_up", "actual", "control_period"]
ArrValueState = Literal["value", "zero", "absent_in_source", "unknown", "not_applicable"]
ReasonCategory = Literal[
    "normative",
    "prudence_check",
    "audited_accounts",
    "carried_forward",
    "disallowed",
    "deferred",
    "not_stated",
]
# fields a reviewer's correction may change (the identity fields of the fact included: a
# misplaced line or a wrong year column is the commonest ARR reading error)
ARR_CORRECTABLE_FIELDS = frozenset(
    {
        "line_code",
        "fiscal_year",
        "value_type",
        "category_code",
        "stated_value",
        "stated_unit",
        "column_label",
        "canonical_value",
        "canonical_unit",
        "conversion",
        "value_state",
        "basis",
        "reason_category",
        "regulation_clause",
        "notes",
    }
)


def _decimal(v: str | None) -> str | None:
    if v is None:
        return None
    try:
        Decimal(v)
    except InvalidOperation as e:
        raise ValueError(f"must be a decimal string, got {v!r}") from e
    return v


class ReasoningQuote(BaseModel):
    """A verbatim sentence of the commission's analysis with its own page and line; found on
    the page mechanically or it is not kept (ADR-0016)."""

    text: str = Field(max_length=600)
    page_index: int = Field(ge=1)
    line_no: int | None = None
    found_on_page: bool = False


class ArrCandidate(BaseModel):
    """One proposed ARR fact.  Never a published fact; never a projection."""

    family: Literal["arr_line"] = "arr_line"
    line_code: str = Field(pattern=r"^[A-Z][A-Z0-9_.]*$")
    fiscal_year: str
    value_type: ValueType
    as_of_order: str  # the source document id that printed it
    category_code: str | None = None  # only for by_category lines
    utility: str | None = None
    value_state: ArrValueState
    stated_value: str | None = None  # exactly as printed (commas removed), a decimal string
    stated_unit: str | None = None  # INR_crore, INR_lakh, MU, percent, ...
    column_label: str | None = Field(default=None, max_length=200)  # the heading that named year and voice
    canonical_value: str | None = None
    canonical_unit: str | None = None
    conversion: str | None = None  # "INR_lakh->INR_crore x0.01", "identity"
    basis: Literal["normative", "actual"] | None = None
    original_text: str = Field(max_length=400)  # the printed row label
    evidence: list[EvidenceRef] = Field(min_length=1)
    reasoning_quote: ReasoningQuote | None = None
    reason_category: ReasonCategory | None = None
    regulation_clause: dict[str, Any] | None = None
    derivation: dict[str, Any] | None = None
    missing: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)
    notes: str | None = None
    rationale: str | None = None

    @field_validator("fiscal_year")
    @classmethod
    def _fy(cls, v: str) -> str:
        if not FY_RE.match(v):
            raise ValueError(f"fiscal_year must look like FY2026-27, got {v!r}")
        return v

    @field_validator("stated_value", "canonical_value")
    @classmethod
    def _dec(cls, v: str | None) -> str | None:
        return _decimal(v)

    @field_validator("reason_category")
    @classmethod
    def _quote_required(cls, v: str | None, info: Any) -> str | None:
        # a reason category is proposed only with its quote (ARR spec section 1)
        if v is not None and info.data.get("reasoning_quote") is None:
            raise ValueError("reason_category needs a reasoning_quote")
        return v

    def key(self) -> str:
        """The fact identity (ARR spec section 1) for channel comparison and duplicates."""
        return "|".join(
            [
                "arr",
                self.utility or "",
                self.line_code,
                self.fiscal_year,
                self.value_type,
                self.as_of_order,
                (self.category_code or "").upper(),
            ]
        )


class ArrExtractionOutput(BaseModel):
    """What one ARR channel returns for one chapter."""

    schema_version: str = ARR_SCHEMA_VERSION
    candidates: list[ArrCandidate] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    notes: str | None = None


def arr_tool_schema() -> dict[str, Any]:
    return ArrExtractionOutput.model_json_schema()


# ------------------------------------------------------------------ units

_UNIT_WORDS = (
    (re.compile(r"\b(?:rs\.?|inr|₹)?\s*(?:in\s+)?crores?\b|\bcr\.?\b", re.I), "INR_crore"),
    (re.compile(r"\b(?:rs\.?|inr|₹)?\s*(?:in\s+)?lakhs?\b|\blacs?\b", re.I), "INR_lakh"),
    (re.compile(r"\bmillion\s+units?\b|\bmus?\b", re.I), "MU"),
    (re.compile(r"%|\bper\s*cent\b|\bpercent\b", re.I), "percent"),
    (re.compile(r"\bmw\b", re.I), "MW"),
    (re.compile(r"\b(?:rs\.?|inr)\s*/\s*kwh\b|\brs\.?\s*per\s*kwh\b", re.I), "INR_per_kWh"),
    (re.compile(r"\bpaise\s*/\s*kwh\b", re.I), "paise_per_kWh"),
)


def unit_from_text(text: str) -> str | None:
    """The unit a caption or heading states, or None.  Never guessed from the numbers."""
    for rx, unit in _UNIT_WORDS:
        if rx.search(text or ""):
            return unit
    return None


def to_canonical(value: str, unit: str | None, conversions: dict[str, float]) -> tuple[str | None, str | None, str]:
    """Canonical value and unit with the conversion applied, exact in Decimal.  A unit the
    taxonomy has no conversion for stays as printed (canonical = stated)."""
    if unit is None:
        return None, None, "unit_unknown"
    canonical = {
        "INR_crore": "INR_crore",
        "INR_lakh": "INR_crore",
        "INR_million": "INR_crore",
        "INR": "INR_crore",
        "MU": "MU",
        "kWh": "MU",
        "MWh": "MU",
        "GWh": "MU",
        "percent": "percent",
        "MW": "MW",
        "INR_per_kWh": "INR_per_kWh",
        "paise_per_kWh": "INR_per_kWh",
    }.get(unit)
    if canonical is None:
        return value, unit, "identity"
    if canonical == unit:
        return value, unit, "identity"
    factor = conversions.get(f"{unit}->{canonical}")
    if factor is None:
        return None, None, f"no_conversion:{unit}->{canonical}"
    out = (Decimal(value) * Decimal(str(factor))).normalize()
    return format(out, "f"), canonical, f"{unit}->{canonical} x{factor}"
