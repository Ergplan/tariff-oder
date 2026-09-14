"""Reading profiles (Section 6.11): per-commission / per-utility reading hints as versioned
data in ``packages/reading-profiles/profiles/<id>.v<version>.json``.

The pydantic model below *is* the profile schema.  ``packages/reading-profiles/schema.json``
is generated from it (``tariff-api profiles-schema``) and a unit test fails on drift, so the
data package and the code that reads it cannot disagree silently.  Profiles are loaded by
id and version; a profile that does not validate is a startup-time error, never a silent
default.  Nothing in a profile is a tariff value: locators, vocabularies, conventions and
expectations only.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

RegionRole = Literal[
    "approved_schedule",
    "approved_summary",
    "existing_tariff",
    "proposed_tariff",
    "amendment_diff",
    "formula_parameters",
    "network_charges",
    "loss_trajectory",
    "green_tariff",
    "illustrative",
    "derived_not_tariff",
    "other",
]

NETWORK_SUB_ROLES = (
    "wheeling_charge",
    "oa_loss",
    "cross_subsidy_surcharge",
    "additional_surcharge",
    "banking_rule",
    "green_tariff",
    "transmission_reference",
)


class LocatorCue(BaseModel):
    """One textual cue that justifies a region classification.  ``pattern`` is a
    case-insensitive regular expression matched against single lines (headings, captions,
    prose).  ``scope`` says what the hit opens: ``span`` opens the approved-schedule span
    (closed by the rules in ``tariff_api.localisation``); ``page`` classifies the page it is
    on (adjacent pages with the same role merge)."""

    role: RegionRole
    pattern: str = Field(min_length=3, max_length=300)
    scope: Literal["span", "page"] = "page"
    sub_role: str | None = None  # network_charges: one of NETWORK_SUB_ROLES
    also_on_page: list[str] = Field(default_factory=list)  # every pattern must also match on the page
    note: str | None = None  # why this cue exists (Part D/E/F reference)

    @field_validator("pattern", "also_on_page")
    @classmethod
    def _compiles(cls, v: Any) -> Any:
        for p in [v] if isinstance(v, str) else v:
            try:
                re.compile(p, re.I)
            except re.error as e:
                raise ValueError(f"pattern {p!r} does not compile: {e}") from e
        return v

    @field_validator("sub_role")
    @classmethod
    def _sub_role_known(cls, v: str | None) -> str | None:
        if v is not None and v not in NETWORK_SUB_ROLES:
            raise ValueError(f"unknown network sub-role {v!r}")
        return v


class PageLabelRule(BaseModel):
    style: Literal["identity", "roman_then_offset", "offset"]
    offset: int | None = None  # printed = index + offset for the decimal segment (KERC/GERC: -16)
    footer_pattern: str | None = None  # e.g. "Page N of 423"


class EffectiveRule(BaseModel):
    type: Literal["publication_plus_days", "first_meter_reading_on_or_after", "fixed_date", "until_next_order"]
    days: int | None = None
    note: str | None = None


class InventoryExpectations(BaseModel):
    """Expectations, not truth: an inventory that differs is a finding shown to the reviewer."""

    schedule_headings: int | None = None
    codes: list[str] = Field(default_factory=list)
    absent_codes: list[str] = Field(default_factory=list)  # a reader that reports one has hallucinated
    general_conditions: int | None = None


class ReadingProfile(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    version: int = Field(ge=1)
    commission: str
    utilities: list[str] = Field(min_length=1)
    seeded_from: str  # which spec part / review motivated this version
    page_labels: PageLabelRule
    schedule_representation: Literal["tables", "clause_outline", "mixed"]
    schedule_heading_kind: Literal["rate_schedule", "tariff_schedule", "rate_clause"]
    schedule_scope: Literal["per_utility", "shared", "shared_via_parallel_orders"]
    locators: list[LocatorCue] = Field(min_length=1)
    secondary_authoritative: bool = False  # a second approved representation must exist and agree
    header_vocabulary: list[str] = Field(default_factory=list)
    unit_placement: Literal["cell", "header", "mixed"]
    currency_convention: Literal["rupees", "paise_energy_rupee_fixed"]
    load_units: list[str] = Field(default_factory=list)
    conversion_factors: dict[str, float] = Field(default_factory=dict)
    category_code_pattern: str
    effective_rule: EffectiveRule
    tod_adjustment: Literal["percent_of_energy_charge", "absolute_paise_per_unit"]
    footnote_markers: list[str] = Field(default_factory=lambda: ["*", "**", "#"])
    inventory_expectations: InventoryExpectations = Field(default_factory=InventoryExpectations)
    known_quirks: list[str] = Field(default_factory=list)

    @field_validator("category_code_pattern")
    @classmethod
    def _code_pattern_compiles(cls, v: str) -> str:
        try:
            re.compile(v, re.I)
        except re.error as e:
            raise ValueError(f"category_code_pattern does not compile: {e}") from e
        return v

    @field_validator("locators")
    @classmethod
    def _one_span_locator(cls, v: list[LocatorCue]) -> list[LocatorCue]:
        if not any(c.role == "approved_schedule" and c.scope == "span" for c in v):
            raise ValueError("a profile needs at least one span locator for approved_schedule")
        return v

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


# ------------------------------------------------------------------ loading


def profiles_dir() -> Path:
    env = os.environ.get("READING_PROFILES_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "reading-profiles" / "profiles"
        if candidate.is_dir():
            return candidate
    return Path("packages/reading-profiles/profiles")


def _profile_path(profile_id: str, version: int) -> Path:
    return profiles_dir() / f"{profile_id}.v{version}.json"


@lru_cache(maxsize=32)
def load_profile(profile_id: str, version: int) -> ReadingProfile:
    path = _profile_path(profile_id, version)
    if not path.is_file():
        raise FileNotFoundError(f"reading profile {profile_id}@{version} not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = ReadingProfile.model_validate(data)
    if profile.id != profile_id or profile.version != version:
        raise ValueError(f"{path.name} declares {profile.ref}, expected {profile_id}@{version}")
    return profile


def list_profiles() -> list[dict[str, Any]]:
    out = []
    for path in sorted(profiles_dir().glob("*.v*.json")):
        m = re.fullmatch(r"(?P<id>[a-z0-9-]+)\.v(?P<v>\d+)\.json", path.name)
        if not m:
            continue
        p = load_profile(m["id"], int(m["v"]))
        out.append(
            {
                "id": p.id,
                "version": p.version,
                "commission": p.commission,
                "utilities": p.utilities,
                "schedule_representation": p.schedule_representation,
                "schedule_heading_kind": p.schedule_heading_kind,
                "seeded_from": p.seeded_from,
            }
        )
    return out


def latest_version(profile_id: str) -> int | None:
    versions = [p["version"] for p in list_profiles() if p["id"] == profile_id]
    return max(versions) if versions else None


def detect_profile(heading_counts: dict[str, int]) -> tuple[str | None, str]:
    """Pick a profile from the document's heading inventory: the schedule-heading kind that
    dominates names the layout family.  Deterministic and explained; a tie or an empty
    inventory detects nothing, and an administrator assigns the profile by hand."""
    by_kind = {p["schedule_heading_kind"]: p["id"] for p in list_profiles()}
    scored = sorted(((heading_counts.get(k, 0), pid) for k, pid in by_kind.items()), reverse=True)
    if not scored or scored[0][0] == 0:
        return None, "no schedule headings of any known kind in the inventory"
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, f"tie between {scored[0][1]} and {scored[1][1]} ({scored[0][0]} headings each)"
    count, pid = scored[0]
    kind = next(k for k, v in by_kind.items() if v == pid)
    return pid, f"{count} `{kind}` headings in the inventory"


def schema_json() -> str:
    return json.dumps(ReadingProfile.model_json_schema(), indent=2, sort_keys=True) + "\n"
