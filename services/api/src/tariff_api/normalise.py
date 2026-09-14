"""Deterministic value normalisation (Section 6.7): one versioned rule set, one rule id per
transformation, the original text always kept.  Nothing here converts paise to rupees or
guesses a unit: a value whose unit cannot be read from its own text is returned without one
and the caller binds it from the header, row, title or footnote (recording the source) or
flags it.

Value states (Section 5.2): ``value``, ``zero``, ``not_applicable``, ``absent_in_source``,
``unknown``, ``cross_reference``, ``formula``, ``footnote_only``.  ``Nil`` becomes state
``zero`` with *no numeric value* and the flag ``nil_word``: a printed statement that nothing is
charged, distinguishable from a printed ``0`` and never a number that can be summed.
``-``/``NA`` are ``not_applicable``; a blank cell is ``unknown``; a bare marker is
``footnote_only``.  None of these is ever ``0``.

Bump ``NORMALISE_VERSION`` when a rule changes; every normalised value records the rules that
fired so a later audit can say which version read it."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

NORMALISE_VERSION = "1"

_MARKERS = ("**", "*", "#", "†", "‡", "^")
_DASHES = "-–—‐"
_NA = re.compile(r"^(n\.?\s?a\.?|not\s+applicable|nil\s*/\s*na)$", re.I)
_NIL = re.compile(r"^nil$", re.I)
_XREF = re.compile(
    r"^(?:rate\s+)?(?:as\s+applicable\s+(?:to|for)|as\s+(?:applicable|per|for)|same\s+as)\s+(?P<target>.+?)\s*$",
    re.I,
)
_FORMULA = re.compile(r"[=]|\bformula\b|\bcomputed\b", re.I)
_PERCENT = re.compile(r"^(?P<sign>\(\s*[+-]\s*\)|[+-])?\s*(?P<num>\d+(?:[.,]\d+)*)\s*%\s*(?P<rest>.*)$", re.I)
_PAREN_NEG = re.compile(r"^\(\s*(?P<num>[\d,]+(?:\.\d+)?)\s*\)$")
_BRACKETED_SECOND = re.compile(r"^(?P<num>[\d,]+(?:\.\d+)?)\s*\(\s*(?P<second>[\d,]+(?:\.\d+)?%?)\s*\)$")
_CURRENCY_PREFIX = re.compile(r"^(?:rs\.?|re\.?|inr|₹)\s*", re.I)
_PAISE = re.compile(r"\b(paise|paisa|ps\.?|p)\b\.?", re.I)
_TRAILING_SLASH_DASH = re.compile(r"/-\s*")
_NUMBER = re.compile(r"^(?P<num>\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)$")
_STRAY_SPACE = re.compile(r"^(\d+)\s+\.\s*(\d+)$|^(\d+)\.\s+(\d+)$|^(\d+)\s+(\d{2})$")
_INDIAN = re.compile(r"^\d{1,2}(,\d{2})*,\d{3}(\.\d+)?$")
_WESTERN = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
_UNIT = re.compile(
    r"(?:/|\bper\b)\s*(?P<u>kwh|kvah|kva|kw|bhp|hp|unit|units|connection|bill|month|annum|year|day|kvarh|mw)\b",
    re.I,
)
_FREQ = re.compile(r"(?:/|\bper\b)\s*(?P<f>month|annum|year|day|bill|billing\s+period)\b", re.I)
_OF_BASE = re.compile(r"\bof\s+(?:the\s+)?(?P<base>[a-z][a-z /&-]{2,60}?)\s*$", re.I)

_UNIT_CANON = {
    "kwh": "kWh",
    "kvah": "kVAh",
    "kvarh": "kVArh",
    "kva": "kVA",
    "kw": "kW",
    "mw": "MW",
    "bhp": "BHP",
    "hp": "HP",
    "unit": "unit",
    "units": "unit",
    "connection": "connection",
    "bill": "bill",
}
_FREQ_CANON = {"month": "per_month", "annum": "per_annum", "year": "per_annum", "day": "per_day", "bill": "per_bill"}


@dataclass
class Normalised:
    original_text: str
    value_state: str
    value: str | None = None  # exact decimal as printed, as a string
    currency: str | None = None  # rupees | paise
    per_unit: str | None = None  # kWh, kVAh, kW, kVA, HP, BHP, unit, connection, bill
    frequency: str | None = None  # per_month | per_annum | per_day | per_bill
    percent: bool = False
    percent_of: str | None = None  # named base for percent components, when printed
    sign: int | None = None  # explicit (+)/(-) on adjustments
    reference: str | None = None  # cross_reference target text
    footnote_markers: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    version: str = NORMALISE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_markers(text: str) -> tuple[str, list[str]]:
    markers: list[str] = []
    changed = True
    while changed:
        changed = False
        for m in _MARKERS:
            if text.endswith(m):
                text, markers = text[: -len(m)].rstrip(), [*markers, m]
                changed = True
            elif text.startswith(m):
                text, markers = text[len(m) :].lstrip(), [*markers, m]
                changed = True
    return text, markers


def _decimal_ok(s: str) -> bool:
    try:
        Decimal(s)
        return True
    except InvalidOperation:
        return False


def normalise_value(text: str | None) -> Normalised:
    """Normalise one cell or value token.  Deterministic; never raises on odd input."""
    raw = "" if text is None else str(text)
    n = Normalised(original_text=raw, value_state="unknown")
    s = re.sub(r"\s+", " ", raw).strip()
    if s != raw:
        n.rules.append("N01.collapse_whitespace")
    s, markers = _strip_markers(s)
    if markers:
        n.footnote_markers = markers
        n.rules.append("N02.footnote_marker")
    if not s:
        n.value_state = "footnote_only" if markers else "unknown"
        n.rules.append("N03.blank" if not markers else "N03.marker_only")
        return n
    if s in _DASHES or _NA.match(s):
        n.value_state = "not_applicable"
        n.rules.append("N04.dash_or_na")
        return n
    if _NIL.match(s):
        n.value_state = "zero"
        n.flags.append("nil_word")
        n.rules.append("N05.nil_word")
        return n
    m = _XREF.match(s)
    if m:
        n.value_state = "cross_reference"
        n.reference = m["target"].strip().rstrip(".")
        n.rules.append("N06.cross_reference")
        return n

    # percentages: `(+) 15%`, `(-) 15%`, `15 %`, `0%`, `1% of energy charge bill`
    m = _PERCENT.match(s)
    if m:
        n.percent = True
        n.rules.append("N11.percent")
        sign = (m["sign"] or "").replace("(", "").replace(")", "").strip()
        if sign:
            n.sign = 1 if sign == "+" else -1
            n.rules.append("N11a.signed_adjustment")
        num = m["num"].replace(",", "")
        n.value = num
        rest = m["rest"].strip()
        ob = _OF_BASE.search(rest) if rest else None
        if ob:
            n.percent_of = ob["base"].strip()
            n.rules.append("N11b.percent_of_base")
        n.value_state = "zero" if Decimal(num) == 0 else "value"
        if n.value_state == "zero":
            n.rules.append("N14.zero_form")
        return n
    if _FORMULA.search(s):
        n.value_state = "formula"
        n.rules.append("N07.formula_text")
        return n

    body = s
    # currency and unit words around the number
    if _CURRENCY_PREFIX.match(body):
        n.currency = "rupees"
        body = _CURRENCY_PREFIX.sub("", body, count=1)
        n.rules.append("N08.rupee_prefix")
    if _PAISE.search(body):
        n.currency = "paise" if n.currency is None else n.currency
        if n.currency == "rupees":
            n.flags.append("currency_conflict")
        body = _PAISE.sub("", body)
        n.rules.append("N08a.paise_word")
    if _TRAILING_SLASH_DASH.search(body):
        body = _TRAILING_SLASH_DASH.sub(" ", body)
        n.rules.append("N10.trailing_slash_dash")
    fm = _FREQ.search(body)
    for um in _UNIT.finditer(body):
        u = um["u"].lower()
        if u in _UNIT_CANON:
            n.per_unit = _UNIT_CANON[u]
            n.rules.append("N13.unit_suffix")
            break
    if fm:
        n.frequency = _FREQ_CANON.get(fm["f"].lower().split()[0], None) or "per_bill"
        n.rules.append("N13a.frequency_suffix")
        if n.per_unit is None and n.frequency == "per_month" and re.search(r"\bper month\b|/\s*month", body, re.I):
            # `Rs. 15/- per month` with no capacity unit: a per-connection charge (F.2 hazard 4)
            n.per_unit = "connection"
            n.flags.append("per_connection_inferred")
            n.rules.append("N13b.per_connection")
    # remove unit/frequency words, keep the number
    body = _UNIT.sub(" ", body)
    body = _FREQ.sub(" ", body)
    body = re.sub(r"\b(per|/)\s*$", "", body.strip(), flags=re.I).strip(" /")
    m = _BRACKETED_SECOND.match(body)
    if m:
        # `122 (12.84)`: a charge with a second figure in brackets (a loss beside a wheeling
        # charge in an injection/drawal matrix).  The first number is the value; the bracketed
        # one is kept as a flag for the reader that knows the matrix layout, never dropped.
        body = m["num"]
        n.flags.append(f"bracketed_secondary_value:{m['second']}")
        n.rules.append("N17.bracketed_secondary_value")
    m = _PAREN_NEG.match(body)
    if m:
        body = "-" + m["num"]
        n.rules.append("N12.parenthesised_negative")
    sm = _STRAY_SPACE.match(body)
    if sm:
        parts = [g for g in sm.groups() if g]
        body = parts[0] + "." + parts[1]
        n.flags.append("stray_space_in_number")
        n.rules.append("N09a.stray_space")
    neg = body.startswith("-")
    core = body[1:] if neg else body
    if _NUMBER.match(core):
        if "," in core:
            if _INDIAN.match(core):
                n.rules.append("N09.indian_grouping")
            elif _WESTERN.match(core):
                n.rules.append("N09.western_grouping")
            else:
                n.flags.append("irregular_grouping")
                n.rules.append("N09b.irregular_grouping")
            core = core.replace(",", "")
        if core.startswith("."):
            core = "0" + core
        if not _decimal_ok(core):
            n.value_state = "unknown"
            n.flags.append("unparsed_text")
            return n
        n.value = ("-" if neg else "") + core
        n.value_state = "zero" if Decimal(core) == 0 else "value"
        n.rules.append("N14.zero_form" if n.value_state == "zero" else "N15.number")
        return n
    n.value_state = "unknown"
    n.flags.append("unparsed_text")
    n.rules.append("N16.unparsed")
    return n


# ------------------------------------------------------------------ slabs


@dataclass
class SlabBound:
    original_text: str
    lower: str | None
    upper: str | None
    lower_inclusive: bool | None
    upper_inclusive: bool | None
    inclusivity: str  # explicit | inferred | ambiguous | none
    kind: str  # absolute | telescopic_first | telescopic_next | open
    unit: str | None
    rules: list[str] = field(default_factory=list)
    reference: str | None = None  # a bound defined by another quantity (`in excess of contract demand`)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SLAB_UNIT = re.compile(r"\b(kwh|kvah|kva|kw|hp|bhp|units?)\b", re.I)
_NUM = r"(?P<{}>\d+(?:,\d+)*(?:\.\d+)?)"
_S_UPTO_INCL = re.compile(r"^\s*up\s*to\s+and\s+including\s+" + _NUM.format("n"), re.I)
_S_UPTO = re.compile(r"^\s*(?:up\s*to|upto|till)\s+" + _NUM.format("n"), re.I)
_S_FIRST = re.compile(r"^\s*(?:for\s+the\s+)?first\s+" + _NUM.format("n"), re.I)
_S_NEXT = re.compile(r"^\s*next\s+" + _NUM.format("n"), re.I)
_S_RANGE = re.compile(
    r"^\s*(?:above\s+)?" + _NUM.format("a") + r"\s*(?:[a-z]+\s+)?(?:[-–—]|up\s*to|to)\s*" + _NUM.format("b"), re.I
)
_S_ABOVE = re.compile(r"^\s*(?:above|beyond|in\s+excess\s+of|exceeding|more\s+than|over)\s+" + _NUM.format("n"), re.I)
_S_ANDABOVE = re.compile(r"^\s*" + _NUM.format("n") + r"\s*(?:[a-z]+\s+)?(?:and|&)\s+above", re.I)
_S_EXCESS_REF = re.compile(
    r"^\s*(?:for\s+)?(?:billing\s+demand\s+|demand\s+)?in\s+excess\s+of\s+(?:the\s+)?"
    r"(?P<ref>contract(?:ed)?\s+demand|sanctioned\s+load|connected\s+load|billing\s+demand)\b",
    re.I,
)
_S_GT = re.compile(r"^\s*(?P<op>>=|>|≥)\s*" + _NUM.format("n"), re.I)
_S_LT = re.compile(r"^\s*(?P<op><=|<|≤|below|less\s+than|under)\s*" + _NUM.format("n"), re.I)


def parse_slab(text: str) -> SlabBound | None:
    """Parse one slab label.  Inclusivity is ``explicit`` only when the words say so (``up to
    and including``, ``>``); ``inferred`` records the convention applied (``up to N`` includes
    N; ``above N`` excludes N; ``101-150`` includes both ends); a caller comparing adjacent
    slabs may downgrade it to ``ambiguous`` (Section 6.7)."""
    s = re.sub(r"\s+", " ", text or "").strip()
    if not s:
        return None
    unit_m = _SLAB_UNIT.search(s)
    unit = _UNIT_CANON.get(unit_m.group(1).lower(), unit_m.group(1)) if unit_m else None

    def num(x: str) -> str:
        return x.replace(",", "")

    if m := _S_UPTO_INCL.match(s):
        return SlabBound(s, None, num(m["n"]), None, True, "explicit", "absolute", unit, ["S01.up_to_and_including"])
    if m := _S_UPTO.match(s):
        return SlabBound(s, None, num(m["n"]), None, True, "inferred", "absolute", unit, ["S02.up_to_inclusive"])
    if m := _S_FIRST.match(s):
        return SlabBound(s, "0", num(m["n"]), True, True, "inferred", "telescopic_first", unit, ["S03.first_n"])
    if m := _S_NEXT.match(s):
        return SlabBound(s, None, num(m["n"]), False, True, "inferred", "telescopic_next", unit, ["S04.next_n"])
    if m := _S_EXCESS_REF.match(s):
        ref = re.sub(r"\s+", "_", m["ref"].lower())
        return SlabBound(s, None, None, False, None, "explicit", "open", unit, ["S12.excess_of_reference"], ref)
    if (m := _S_RANGE.match(s)) is None and (m := _S_ABOVE.match(s)):
        return SlabBound(s, num(m["n"]), None, False, None, "inferred", "open", unit, ["S05.above_exclusive"])
    if m := _S_RANGE.match(s):
        above = s.lower().startswith("above")
        return SlabBound(
            s,
            num(m["a"]),
            num(m["b"]),
            not above,
            True,
            "inferred",
            "absolute",
            unit,
            ["S06.range_above_to" if above else "S06.range_inclusive_ends"],
        )
    if m := _S_ANDABOVE.match(s):
        return SlabBound(s, num(m["n"]), None, True, None, "explicit", "open", unit, ["S07.n_and_above"])
    if m := _S_GT.match(s):
        incl = m["op"] in (">=", "≥")
        return SlabBound(s, num(m["n"]), None, incl, None, "explicit", "open", unit, ["S08.gt_operator"])
    if m := _S_LT.match(s):
        incl = m["op"] in ("<=", "≤")
        return SlabBound(s, None, num(m["n"]), None, incl, "explicit", "absolute", unit, ["S09.lt_operator"])
    return None


def check_slab_sequence(bounds: list[SlabBound]) -> list[SlabBound]:
    """Adjacent slabs that both claim a boundary (``up to 100`` then ``100 - 300``) or leave a
    gap (``up to 100`` then ``above 101``) make the inclusivity ambiguous: recorded, routed to
    review, never silently resolved."""
    for prev, cur in zip(bounds, bounds[1:], strict=False):
        if prev.upper is None or cur.lower is None:
            continue
        pu, cl = Decimal(prev.upper), Decimal(cur.lower)
        integral = pu == pu.to_integral_value() and cl == cl.to_integral_value()
        step = Decimal(1) if integral else Decimal(0)
        last_covered = pu if prev.upper_inclusive else pu - step
        first_covered = cl if cur.lower_inclusive else cl + step
        both_claim = first_covered <= last_covered
        gap = first_covered > last_covered + step if integral else first_covered > last_covered
        if both_claim or gap:
            reason = "S10.boundary_claimed_twice" if both_claim else "S11.gap_between_slabs"
            for b in (prev, cur):
                if b.inclusivity != "explicit":
                    b.inclusivity = "ambiguous"
                if reason not in b.rules:
                    b.rules.append(reason)
    return bounds


# ------------------------------------------------------------------ unit hints in headers/titles

_HINT_CURRENCY_PAISE = re.compile(r"\b(paise|paisa|ps\.?)\b|\(p\)|\bp/", re.I)
_HINT_CURRENCY_RUPEE = re.compile(r"\b(rs\.?|rupees?|inr)\b|₹|in\s+rupees", re.I)
_HINT_UNIT = re.compile(
    r"(?:/|\bper\b|\bin\b)\s*(?P<u>kwh|kvah|kvarh|kva|kw|bhp|hp|unit|units|connection|bill)\b", re.I
)
_HINT_FREQ = re.compile(r"(?:/|\bper\b)\s*(?P<f>month|annum|year|day|bill)\b", re.I)
_HINT_PERCENT = re.compile(r"%|\bpercent(age)?\b", re.I)


def unit_hint(text: str | None) -> dict[str, Any]:
    """Currency / unit / frequency words found in a header, super-header, title, row-unit cell
    or footnote — used to bind a unit to a numeric cell that carries none itself, with the
    source recorded by the caller (Section 6.6).  Returns only what the text says."""
    s = text or ""
    out: dict[str, Any] = {"currency": None, "per_unit": None, "frequency": None, "percent": False}
    if _HINT_CURRENCY_PAISE.search(s):
        out["currency"] = "paise"
    elif _HINT_CURRENCY_RUPEE.search(s):
        out["currency"] = "rupees"
    m = _HINT_UNIT.search(s)
    if m:
        out["per_unit"] = _UNIT_CANON.get(m["u"].lower(), m["u"])
    f = _HINT_FREQ.search(s)
    if f:
        out["frequency"] = _FREQ_CANON.get(f["f"].lower(), "per_bill")
    if _HINT_PERCENT.search(s):
        out["percent"] = True
    return out
