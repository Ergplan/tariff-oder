"""The ARR taxonomy and the per-commission mappings, loaded from
`packages/arr-taxonomy/` (ARR spec sections 2 and 3).  Data, not code: a line code is
stable for ever; generic aliases live in the taxonomy, commission words in the mapping."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Unit = Literal["INR_crore", "MU", "percent", "MW", "INR_per_kWh", "number"]
Branch = Literal["shared", "distribution", "transmission"]
Kind = Literal["group", "printed", "computed", "detail"]


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_.]*$")
    label: str
    unit: Unit | None
    kind: Kind
    branch: Branch
    parent: str | None
    aliases: list[str] = Field(default_factory=list)
    note: str | None = None
    by_category: bool = False
    sign: Literal[-1, 1] | None = None


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^ARR-I\d+$")
    name: str
    expression: str
    tolerance: dict[str, float] | None = None
    severity: Literal["blocking", "advisory"]
    cross_order: bool = False
    note: str | None = None


class Coded(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    label: str
    note: str | None = None


class Taxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["arr-taxonomy"]
    version: int = Field(ge=1)
    status: str
    canonical_units: dict[str, str]
    unit_conversions: dict[str, float]
    fiscal_year_format: str
    value_types: list[Coded]
    reason_categories: list[Coded]
    line_items: list[LineItem]
    identities: list[Identity]

    def by_code(self) -> dict[str, LineItem]:
        return {i.code: i for i in self.line_items}


class Regulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    title: str
    year: int | None = None
    amendments: list[str] = Field(default_factory=list)
    control_periods: list[dict[str, str | None]] = Field(default_factory=list)
    source_id: str | None = None
    note: str | None = None


class Noted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None = None
    note: str | None = None


class UnitConvention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    money: str = "INR_crore"
    energy: str = "MU"
    note: str | None = None


class DecidedYear(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fy: str = Field(pattern=r"^FY\d{4}-\d{2}$")
    value_type: str


class OrderExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_type: str
    decides: list[DecidedYear]
    note: str | None = None


class ChapterCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: str
    heading_patterns: list[str]
    note: str | None = None


class PatternList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = None
    patterns: list[dict[str, str]] = Field(default_factory=list)


class EntryList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = None
    entries: list[dict[str, str | int | list[int] | None]] = Field(default_factory=list)


class Mapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z]+-arr$")
    version: int = Field(ge=1)
    taxonomy_version: int
    commission: str
    status: str
    licensees: dict[str, list[str]]
    regulations: list[Regulation]
    return_basis: Noted
    gap_convention: Noted
    unit_convention: UnitConvention
    orders_expected: list[OrderExpected] = Field(default_factory=list)
    chapter_map: list[ChapterCue]
    year_columns: PatternList
    voice_columns: PatternList
    label_aliases: EntryList
    regulation_clauses: EntryList
    unplaced: EntryList
    known_quirks: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ files


def taxonomy_dir() -> Path:
    env = os.environ.get("ARR_TAXONOMY_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "arr-taxonomy"
        if candidate.is_dir():
            return candidate
    return Path("packages/arr-taxonomy")


@lru_cache(maxsize=1)
def load_taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(json.loads((taxonomy_dir() / "taxonomy.json").read_text()))


def mapping_files() -> dict[str, list[tuple[int, Path]]]:
    out: dict[str, list[tuple[int, Path]]] = {}
    for path in sorted((taxonomy_dir() / "mappings").glob("*-arr.v*.json")):
        m = re.fullmatch(r"([a-z]+)-arr\.v(\d+)\.json", path.name)
        if m:
            out.setdefault(m.group(1).upper(), []).append((int(m.group(2)), path))
    return out


def load_mapping(commission: str, version: int | None = None) -> Mapping:
    files = mapping_files().get(commission.upper())
    if not files:
        raise FileNotFoundError(f"no ARR mapping for commission {commission!r}")
    chosen = max(files)[1] if version is None else next(p for v, p in files if v == version)
    return Mapping.model_validate(json.loads(chosen.read_text()))


# ------------------------------------------------------------------ placing printed labels

_NUMBERING = re.compile(r"^\s*(?:\(?[a-z0-9]{1,3}[.)]\s*|[ivx]{1,4}[.)]\s*|\d+(?:\.\d+)*\s+)", re.I)
_UNIT_HINT = re.compile(
    r"\(\s*(?:rs\.?|inr|₹)?\s*(?:in\s+)?(?:crore|cr\.?|lakh|lakhs|million|mu|%|percent|mw|kwh)\s*\)", re.I
)
_PUNCT = re.compile(r"[^a-z0-9%&/ ]+")
_WS = re.compile(r"\s+")


def norm_label(text: str) -> str:
    """The comparable form of a printed row label: no numbering, no unit hint in brackets,
    no trailing colon, lower case, one space, "&" kept as "and"."""
    t = text.strip()
    t = _NUMBERING.sub("", t)
    t = _UNIT_HINT.sub(" ", t)
    t = t.lower().replace("&", " and ").replace("/", " / ")
    t = _PUNCT.sub(" ", t)
    t = re.sub(r"\b(?:less|add|total)\s*:\s*", lambda m: m.group(0).replace(":", " "), t)
    return _WS.sub(" ", t).strip(" :-")


@dataclass(frozen=True)
class Placement:
    code: str
    matched: str  # the alias or label that matched
    how: Literal["exact", "contains"]


class Placer:
    """Places a printed label on the taxonomy: an exact alias first, then the longest alias
    contained in the label as whole words.  Collisions between branches are resolved by the
    licensee kind (a distribution order's "transmission charges" is a cost, a transmission
    order's is its tariff); collisions inside one branch are a data error the tests catch."""

    def __init__(self, taxonomy: Taxonomy, mapping: Mapping | None = None, licensee_kind: str = "distribution"):
        self.kind = licensee_kind
        self._unit: dict[str, str | None] = {i.code: i.unit for i in taxonomy.line_items}
        self._exact: dict[str, list[tuple[str, str]]] = {}  # norm alias -> [(code, branch)]
        for item in taxonomy.line_items:
            if item.kind == "group":
                continue
            for alias in [item.label, *item.aliases]:
                n = norm_label(alias)
                if n and (item.code, item.branch) not in self._exact.setdefault(n, []):
                    self._exact[n].append((item.code, item.branch))
        if mapping is not None:
            for e in mapping.label_aliases.entries:
                n = norm_label(str(e.get("label") or ""))
                if n and e.get("code"):
                    # a commission's own word outranks the generic ones
                    self._exact[n] = [(str(e["code"]), "mapping")]
        self._by_len = sorted(self._exact, key=len, reverse=True)

    def _pick(self, options: list[tuple[str, str]], unit_hint: str | None) -> str | None:
        """One code, or None when the label alone cannot say which: the licensee kind first
        (a mapping entry counts as the commission's own kind), then the unit the table is
        printed in (a "Solar" row is energy in an MU table and cost in a crore table)."""
        codes = list(dict.fromkeys(c for c, _ in options))
        if len(codes) == 1:
            return codes[0]
        preferred = list(dict.fromkeys(c for c, b in options if b in (self.kind, "mapping")))
        if len(preferred) == 1:
            return preferred[0]
        pool = preferred or list(dict.fromkeys(c for c, b in options if b == "shared")) or codes
        if len(pool) == 1:
            return pool[0]
        if unit_hint:
            by_unit = [c for c in pool if self._unit.get(c) == unit_hint]
            if len(by_unit) == 1:
                return by_unit[0]
        return None  # ambiguous: reported, never guessed

    def place(self, label: str, unit_hint: str | None = None) -> Placement | None:
        n = norm_label(label)
        if not n:
            return None
        if n in self._exact:
            code = self._pick(self._exact[n], unit_hint)
            return Placement(code, n, "exact") if code else None
        for alias in self._by_len:
            if len(alias) < 4:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", n):
                code = self._pick(self._exact[alias], unit_hint)
                if code:
                    return Placement(code, alias, "contains")
        return None

    def options(self, label: str) -> list[str]:
        """Every code an exact alias of this label names (for reporting an ambiguous line)."""
        return sorted({c for c, _ in self._exact.get(norm_label(label), [])})

    def collisions(self) -> dict[str, list[str]]:
        """Aliases that map to more than one code inside one branch with the same unit: a
        taxonomy defect, since neither the licensee kind nor the table's unit can resolve it
        (the energy / cost twins of a power-purchase source are resolved by the unit)."""
        out: dict[str, list[str]] = {}
        for alias, opts in self._exact.items():
            by_branch: dict[str, set[str]] = {}
            for code, branch in opts:
                by_branch.setdefault(branch, set()).add(code)
            for branch, codes in by_branch.items():
                units = [self._unit.get(c) for c in codes]
                if len(codes) > 1 and len(set(units)) < len(units):
                    out[f"{alias} [{branch}]"] = sorted(codes)
        return out
