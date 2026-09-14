"""Clause-outline reconstruction (Section 6.6) for prose-structured schedules: the GERC shape
``11. RATE: HTP-1`` → ``11.1. DEMAND CHARGE`` → ``(a) For the first 500 kVA of billing demand …
Rs. 150/- per kVA per month``.  Every value line resolves to an explicit clause path, a
rate-block role, and the unit parsed from the line itself; ``PLUS`` joins the parts of one
tariff; ``ALTERNATIVELY`` opens another alternative of an option group; ``Rate as per
<category>`` is a cross-reference; two-column value lines bind each value to its column
header as a metering-type dimension; a condition clause (billing demand definition) is kept
as a condition, never as a number.  Pure functions over page text; bump ``CLAUSE_VERSION`` on
change."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .normalise import Normalised, normalise_value, parse_slab

CLAUSE_VERSION = "1"

_CATEGORY = re.compile(r"^\s*(?P<num>\d{1,2})\.\s*RATE\s*:\s*(?P<code>.+?)\s*$", re.I)
_SUBCLAUSE = re.compile(r"^\s*(?P<num>\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(?P<title>.+?)\s*$")
_LETTERED = re.compile(r"^\s*\((?P<letter>[a-z]|[ivx]{1,4})\)\s*(?P<body>.+?)\s*$", re.I)
_CONNECTOR = re.compile(r"^\s*(?P<c>PLUS|ALTERNATIVELY|OR)\s*$")
_BASE_NOUN = r"(?:bill|charges?|tariff|demand|amount|rate)"
_AMOUNT = re.compile(
    r"(?:Rs\.?\s*\d[\d,]*(?:\.\d+)?\s*(?:/-)?(?:\s*(?:per|/)\s*[A-Za-z]+(?:\s*(?:per|/)\s*[A-Za-z]+)*)?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:Paise|paise|Ps\.?)\s*(?:per\s+Unit|/\s*unit|per\s+unit)?"
    r"|\(?[+-]?\)?\s*\d+(?:\.\d+)?\s*%(?:\s+of\s+(?:the\s+)?(?:[A-Za-z]+\s+){0,3}" + _BASE_NOUN + r"\b)?)"
)
_XREF_LINE = re.compile(
    r"\b(rate\s+as\s+per|as\s+applicable\s+to|same\s+as)\s+(?P<target>[A-Z][A-Z0-9 ()/-]{1,30})", re.I
)
_TWO_COL_HEADER = re.compile(r"(?P<a>[A-Za-z-]+\s+Energy\s+Charge)\s{2,}(?P<b>[A-Za-z-]+\s+Energy\s+Charge)", re.I)
_TIME_WINDOW = re.compile(r"(?P<a>\d{1,2}:\d{2})\s*(?:hrs\.?\s*)?(?:to|-|–|—)\s*(?P<b>\d{1,2}:\d{2})", re.I)
_ELLIPSIS = re.compile(r"\s*(?:\.{3}|…)\s*")

# Rate-block role from the sub-clause title vocabulary (F.1).  Opposite-direction terms with
# near-identical names (S21) resolve to different roles with an explicit sign.  A condition
# heading (`BILLING DEMAND`) is matched only as a whole title, never inside a slab phrase.
_ROLE_RULES: list[tuple[re.Pattern[str], str, int | None]] = [
    (re.compile(r"^\s*[\d.]*\s*billing\s+demand\s*$", re.I), "condition", None),
    (re.compile(r"time\s+of\s+use\s+discount|tou\s+discount|\brebate", re.I), "rebate", -1),
    (re.compile(r"time\s+of\s+use\s+charges?|tou\s+charges?|peak\s+charges?", re.I), "tou_surcharge", 1),
    (re.compile(r"fixed\s+charges?", re.I), "fixed", None),
    (re.compile(r"demand\s+charges?", re.I), "demand", None),
    (re.compile(r"energy\s+charges?", re.I), "energy", None),
    (re.compile(r"minimum\s+(bill|charges?)", re.I), "minimum", None),
    (re.compile(r"power\s+factor", re.I), "power_factor", None),
    (re.compile(r"penalt(y|ies)|surcharge", re.I), "penalty", 1),
    (re.compile(r"hp\s+based\s+tariff|metered\s+tariff|tatkal", re.I), "option", None),
]


@dataclass
class ClauseValue:
    page_index: int
    line_no: int
    category_code: str | None
    clause_path: list[str]
    role: str
    connector: str | None  # PLUS joins this value to the previous block
    alternative: int  # index of the alternative within the category's option group; 0 = first / none
    line_text: str
    normalised: dict[str, Any]
    dimension: dict[str, str] | None = None  # e.g. {"metering_type": "pre_paid"}
    slab: dict[str, Any] | None = None
    time_window: str | None = None
    sign: int | None = None
    kind: str = "value"  # value | cross_reference | condition
    parameters: list[str] = field(default_factory=list)  # further amounts on a rule line (thresholds)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClauseCategory:
    code: str
    heading: str
    page_index: int
    line_no: int
    alternatives: int = 0  # > 1 when ALTERNATIVELY appeared: the answer must present the group
    values: int = 0
    cross_references: int = 0
    conditions: int = 0


@dataclass
class ClauseOutline:
    values: list[ClauseValue] = field(default_factory=list)
    categories: list[ClauseCategory] = field(default_factory=list)
    unresolved_lines: list[dict[str, Any]] = field(default_factory=list)  # amounts with no clause path
    version: str = CLAUSE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "values": [v.to_dict() for v in self.values],
            "categories": [asdict(c) for c in self.categories],
            "unresolved_lines": self.unresolved_lines,
        }


def _role_for(titles: list[str]) -> tuple[str, int | None]:
    for title in reversed(titles):
        for rx, role, sign in _ROLE_RULES:
            if rx.search(title):
                return role, sign
    return "other", None


def _metering(header: str) -> str:
    h = header.lower()
    if "pre" in h:
        return "pre_paid"
    if "post" in h:
        return "post_paid"
    return re.sub(r"\s+", "_", h)


def _norm(amount: str) -> Normalised:
    n = normalise_value(amount)
    if n.value_state == "value" and n.currency is None and not n.percent:
        n.flags.append("currency_unresolved")
    return n


def reconstruct(pages: list[tuple[int, str]]) -> ClauseOutline:
    """``pages`` is ``[(page_index, text_in_reading_order), ...]`` for the clause-outline
    region.  State (category, sub-clause titles by depth, alternative index, pending
    connector, two-column header) carries across page boundaries because clauses do."""
    out = ClauseOutline()
    category: ClauseCategory | None = None
    heading = ""
    titles: dict[int, str] = {}  # depth (number of numeric components) -> title line
    applicability: str | None = None  # a lettered line without an amount scopes what follows
    alternative = 0
    alt_depth = 0  # depth of the titles that ALTERNATIVELY separates; a shallower title ends the group
    pending: str | None = None
    two_col: tuple[str, str] | None = None

    def path() -> list[str]:
        return [heading, *[titles[k] for k in sorted(titles)]]

    for page_index, text in pages:
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            m = _CATEGORY.match(line)
            if m:
                code = re.sub(r"\s+", " ", m["code"]).strip()
                category = ClauseCategory(code=code, heading=line, page_index=page_index, line_no=line_no)
                out.categories.append(category)
                heading, titles, applicability, alternative, pending, two_col = line, {}, None, 0, None, None
                continue
            m = _CONNECTOR.match(line)
            if m:
                if m["c"].upper() == "PLUS":
                    pending = "PLUS"
                else:
                    alternative += 1
                    alt_depth = max(titles) if titles else 0
                    if category:
                        category.alternatives = alternative + 1
                    pending = "ALTERNATIVELY"
                continue
            sub = _SUBCLAUSE.match(line)
            if sub and category and sub["num"].split(".")[0] == heading.split(".")[0].strip():
                depth = sub["num"].count(".") + 1
                if alternative and depth < alt_depth:
                    alternative = 0  # a sibling of the clause that held the alternatives: group closed
                for k in [k for k in titles if k >= depth]:
                    del titles[k]
                titles[depth] = line
                applicability, two_col = None, None
                if not _AMOUNT.search(sub["title"]):
                    continue  # a pure title; a title that carries an amount falls through as a value
            h = _TWO_COL_HEADER.search(line)
            if h and not _AMOUNT.search(line):
                two_col = (h["a"].strip(), h["b"].strip())
                continue
            lettered = _LETTERED.match(line)
            body = lettered["body"] if lettered else line
            amounts = [a.strip() for a in _AMOUNT.findall(line)]
            xref = _XREF_LINE.search(body)
            if not amounts and not xref:
                if lettered and category:
                    applicability = line
                continue
            if category is None:
                out.unresolved_lines.append({"page_index": page_index, "line_no": line_no, "text": line[:200]})
                continue
            item_path = (
                path()
                if line in titles.values()
                else [*path(), *([applicability] if applicability and not lettered else []), line]
            )
            role, sign = _role_for([p for p in item_path if p != line] or item_path)
            label = re.sub(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\.?\s*", "", _ELLIPSIS.split(body)[0])
            slab = parse_slab(label)
            tw = _TIME_WINDOW.search(line)
            window = f"{tw['a']}-{tw['b']}" if tw else None
            common = dict(
                page_index=page_index,
                line_no=line_no,
                category_code=category.code,
                clause_path=item_path,
                role=role,
                connector=pending,
                alternative=alternative,
                line_text=line,
            )
            if role == "condition":
                out.values.append(ClauseValue(**common, normalised={}, kind="condition", parameters=amounts))
                category.conditions += 1
                pending = None
                continue
            if xref and not amounts:
                nv = normalise_value(f"as applicable to {xref['target'].strip()}")
                out.values.append(
                    ClauseValue(
                        **common, normalised=nv.to_dict(), slab=slab.to_dict() if slab else None, kind="cross_reference"
                    )
                )
                category.cross_references += 1
                pending = None
                continue
            if two_col and len(amounts) >= 2:
                for header, amount in zip(two_col, amounts[:2], strict=False):
                    nv = _norm(amount)
                    out.values.append(
                        ClauseValue(
                            **common,
                            normalised=nv.to_dict(),
                            dimension={"metering_type": _metering(header), "column_header": header},
                            slab=slab.to_dict() if slab else None,
                            sign=sign,
                        )
                    )
                    category.values += 1
            elif role in ("power_factor", "penalty", "rebate", "minimum") and len(amounts) > 1:
                # a rule line: the first amount is the component, the rest are its thresholds
                nv = _norm(amounts[0])
                out.values.append(
                    ClauseValue(
                        **common,
                        normalised=nv.to_dict(),
                        time_window=window,
                        sign=sign if nv.sign is None else nv.sign,
                        parameters=amounts[1:],
                    )
                )
                category.values += 1
            else:
                for amount in amounts:
                    nv = _norm(amount)
                    out.values.append(
                        ClauseValue(
                            **common,
                            normalised=nv.to_dict(),
                            slab=slab.to_dict() if slab else None,
                            time_window=window,
                            sign=sign if nv.sign is None else nv.sign,
                        )
                    )
                    category.values += 1
            pending = None
            if xref and amounts:
                nv = normalise_value(f"as applicable to {xref['target'].strip()}")
                out.values.append(
                    ClauseValue(**{**common, "connector": None}, normalised=nv.to_dict(), kind="cross_reference")
                )
                category.cross_references += 1
    return out


def summarise(outline: ClauseOutline) -> dict[str, Any]:
    roles: dict[str, int] = {}
    for v in outline.values:
        roles[v.role] = roles.get(v.role, 0) + 1
    return {
        "version": outline.version,
        "categories": len(outline.categories),
        "values": sum(1 for v in outline.values if v.kind == "value"),
        "cross_references": sum(1 for v in outline.values if v.kind == "cross_reference"),
        "conditions": sum(1 for v in outline.values if v.kind == "condition"),
        "option_groups": sum(1 for c in outline.categories if c.alternatives > 1),
        "roles": roles,
        "unresolved_lines": len(outline.unresolved_lines),
        "currency_unresolved": sum(1 for v in outline.values if "currency_unresolved" in v.normalised.get("flags", [])),
    }
