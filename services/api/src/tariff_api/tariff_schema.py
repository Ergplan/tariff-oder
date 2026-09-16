"""Versioned tariff candidate schema (Sections 5.1, 5.2, 6.8).  This is the contract every
extraction channel returns and every candidate row stores: exact decimals as strings, the
original text, the unit as read, a `value_state` on every numeric field, a decision status
on every network-charge family, and cell- or clause-level evidence.  The same pydantic model
is the JSON schema handed to the provider (tool input schema), so a channel can only return
what the schema allows — and structural validity is still not factual verification.
Bump ``SCHEMA_VERSION`` when a field changes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2"

Family = Literal[
    "retail_tariff",
    "wheeling_charge",
    "oa_loss",
    "distribution_loss_approved",
    "cross_subsidy_surcharge",
    "additional_surcharge",
    "banking_rule",
    "green_tariff",
    "transmission_reference",
]
FAMILIES: tuple[str, ...] = Family.__args__  # type: ignore[attr-defined]
NETWORK_FAMILIES = (
    "wheeling_charge",
    "oa_loss",
    "distribution_loss_approved",
    "cross_subsidy_surcharge",
    "additional_surcharge",
    "banking_rule",
    "green_tariff",
    "transmission_reference",
)

ComponentType = Literal[
    "energy",
    "fixed",
    "demand",
    "minimum",
    "tod_adjustment",
    "rebate",
    "surcharge",
    "subsidy",
    "green_premium",
    "charge",  # network families: the leviable value
    "loss",
    "condition",
    "cross_reference",
]
ValueState = Literal[
    "value",
    "zero",
    "absent_in_source",
    "unknown",
    "unchanged_reference",
    "not_applicable",
    "formula",
    "cross_reference",
    "not_yet_verified",
]
DecisionStatus = Literal[
    "approved",
    "approved_zero",
    "deferred_to_separate_petition",
    "not_levied_pending_petition",
    "by_reference",
    "parameter_specified",
    "absent_in_source",
]
Currency = Literal["rupees", "paise"]


class EvidenceRef(BaseModel):
    """Where a field was read.  A table cell (page, grid, row, col) or a clause line (page,
    line, clause path); the excerpt is the exact text of that cell or line."""

    page_index: int = Field(ge=1)
    kind: Literal["cell", "clause", "prose"]
    grid_ordinal: int | None = None
    row: int | None = None
    col: int | None = None
    line_no: int | None = None
    header_path: list[str] = Field(default_factory=list)
    row_path: list[str] = Field(default_factory=list)
    clause_path: list[str] = Field(default_factory=list)
    excerpt: str = Field(max_length=400)


SlabBasis = Literal["consumption", "connected_load", "contracted_load", "billing_demand", "sanctioned_load", "unknown"]


class Slab(BaseModel):
    lower: str | None = None
    upper: str | None = None
    lower_inclusive: bool | None = None
    upper_inclusive: bool | None = None
    inclusivity: Literal["explicit", "inferred", "ambiguous", "none"] = "none"
    kind: Literal["absolute", "telescopic_first", "telescopic_next", "open"] = "absolute"
    basis: SlabBasis = "unknown"
    unit: str | None = None
    original_text: str | None = None
    reference: str | None = None


class Applicability(BaseModel):
    """The dimensions a rate varies over (Section 5.2, category/version)."""

    voltage: str | None = None
    load_band: Slab | None = None
    slab: Slab | None = None
    season: str | None = None
    time_band: str | None = None  # "19:00-02:00"
    metering_type: Literal["post_paid", "pre_paid", "smart", "tod_capable"] | None = None
    consumer_class: str | None = None  # e.g. BPL
    rural_urban: Literal["rural", "urban"] | None = None
    alternative: int | None = None  # index within an option group (0-based); None = no group
    rate_block: str | None = None  # lettered block text (UPERC "(a) Consumers getting supply as per ...")
    description: str | None = None  # row description as printed (Metered, Unmetered, ...)


class Candidate(BaseModel):
    """One proposed fact.  Never a published fact; separate table, separate routes."""

    family: Family
    category_code: str | None = None
    component_type: ComponentType
    value: str | None = None  # exact decimal as printed, as a string; None unless value_state is value/zero
    value_state: ValueState
    original_text: str = Field(max_length=400)
    currency: Currency | None = None
    per_unit: str | None = None  # kWh, kVAh, kW, kVA, HP, BHP, unit, connection, percent
    frequency: str | None = None  # per_month, per_annum, per_bill
    billing_basis: str | None = None  # sanctioned load, contracted load, billing demand, energy, per connection
    adjustment: Literal["absolute", "percent_of"] | None = None
    adjustment_base: str | None = None  # named base for percent components
    sign: int | None = None
    applicability: Applicability = Field(default_factory=Applicability)
    period: str | None = None  # "FY2026-27"
    utility: str | None = None
    decision_status: DecisionStatus | None = None
    reference_target: str | None = None  # for cross_reference / by_reference
    conditions: list[str] = Field(default_factory=list)  # verbatim condition or footnote texts
    derivation: dict[str, Any] | None = None  # printed inputs/arithmetic behind a network value (VAL-07 recomputes)
    evidence: list[EvidenceRef] = Field(min_length=1)
    missing: list[str] = Field(default_factory=list)  # field names the channel could not read
    ambiguous: list[str] = Field(default_factory=list)
    notes: str | None = None
    # Why the reviewer is being shown this value (schema 2): a rule-written sentence naming
    # the table, row and column or the clause, and the verbatim page text that gives the
    # cue — the caption above the table, the paragraph that decides the value.  Never a
    # number the order did not print.
    rationale: str | None = None
    context: list[str] = Field(default_factory=list)

    @field_validator("value")
    @classmethod
    def _decimal_string(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from decimal import Decimal, InvalidOperation

        try:
            Decimal(v)
        except InvalidOperation as e:
            raise ValueError(f"value must be a decimal string, got {v!r}") from e
        return v

    def key(self) -> str:
        """Identity for channel comparison and duplicate detection: what the fact is about."""
        a = self.applicability
        parts = [
            self.family,
            self.category_code or "",
            self.component_type,
            a.voltage or "",
            a.description or "",
            (a.slab.original_text if a.slab else "") or "",
            (a.load_band.original_text if a.load_band else "") or "",
            a.season or "",
            a.time_band or "",
            a.metering_type or "",
            a.consumer_class or "",
            a.rate_block or "",
            str(a.alternative) if a.alternative is not None else "",
            self.period or "",
            self.utility or "",
        ]
        return "|".join(parts)


class ExtractionOutput(BaseModel):
    """What one channel returns for one unit of input (a region page or a clause block)."""

    schema_version: str = SCHEMA_VERSION
    candidates: list[Candidate] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)  # things the channel could not read at all
    notes: str | None = None


def tool_schema() -> dict[str, Any]:
    """The JSON schema a provider receives as the structured-output tool input."""
    return ExtractionOutput.model_json_schema()
