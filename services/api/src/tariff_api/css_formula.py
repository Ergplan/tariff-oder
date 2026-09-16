"""Cross-subsidy surcharge as a computation, not a number (Section 5.1, VAL-07).

Orders that follow the Tariff Policy print the surcharge formula

    S = T − [ C / (1 − L/100) + D + R ]

with T the tariff payable by the category, C the weighted average cost of power purchase,
D the aggregate of transmission, distribution and wheeling charges at the voltage level
(often derived on the page as DC + TC + WC), L the aggregate losses at that level in per
cent, and R the per-unit carrying cost of regulatory assets; the computed S is then capped
(20% of T under the policy) and the leviable value chosen (this year's computed, or the
lower of last year's and this year's).  This module recognises the formula statement and
the symbol definitions in the page text, reads the parameter tables inside the CSS region
into `{level: {symbol: {value, unit, evidence}}}` and recomputes S so that a candidate
carries the arithmetic behind it.  Nothing here invents a value: every input is a printed
cell with its evidence; the recomputed S is compared with what the order printed and a
mismatch is a finding, never a correction.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .tariff_schema import EvidenceRef

CSS_FORMULA_VERSION = "1"

# the formula as printed (dashes, brackets and spacing vary between orders)
FORMULA = re.compile(
    r"\bS\s*=\s*T\s*[-–—]\s*\[?\s*\{?\s*C\s*/\s*\(\s*1\s*[-–—]\s*L\s*/\s*100\s*\)\s*\+\s*D\s*\+\s*R\s*\}?\s*\]?",
    re.I,
)
# "T is the tariff payable by the relevant category of consumers ..."
DEFINITION = re.compile(r"^\s*(?:where\s*:?\s*)?\b(T|C|D|L|R|S)\s+(?:is|=|:|means|denotes)\s+(.{8,300})$", re.I)

# symbol from a row or column label: "(T)", "Tariff (T) Rs/kWh", "D = DC + TC + WC"
_SYMBOL_PAREN = re.compile(r"\((DC|TC|WC|T|C|D|L|R|S)\)")
_SYMBOL_EQ = re.compile(r"^\s*(DC|TC|WC|T|C|D|L|R|S)\s*=")
_DESCRIPTORS: list[tuple[str, re.Pattern[str]]] = [
    ("DC", re.compile(r"distribution charge", re.I)),
    ("TC", re.compile(r"transmission charge", re.I)),
    ("WC", re.compile(r"wheeling charge", re.I)),
    ("D", re.compile(r"aggregate.{0,40}charge|transmission,? distribution (and|&) wheeling", re.I)),
    ("C", re.compile(r"(weighted )?average (cost|price) of power purchase|power purchase cost", re.I)),
    ("L", re.compile(r"\bloss(es)?\b", re.I)),
    ("R", re.compile(r"regulatory asset|carrying cost", re.I)),
    (
        "S",
        re.compile(
            r"cross[- ]subsidy surcharge.{0,30}(computed|as per formula|formula)|computed (css|surcharge)", re.I
        ),
    ),
    ("CAP", re.compile(r"\bcap\b|20\s*%\s*of", re.I)),
    ("T", re.compile(r"\btariff\b|average billing rate|\bABR\b", re.I)),
]
_PAISE = re.compile(r"\bpaise\b|\bps\.?\b|\bp/", re.I)
_LEVEL = re.compile(
    r"\b(inter[- ]?state|intra[- ]?state|ehv|\d{2,3}\s*kv|below\s+\d+\s*kv|above\s+\d+\s*kv|400\s*v|ht|lt|hv)\b", re.I
)


def symbol_of(label: str) -> str | None:
    """Which formula symbol a row or column label names, or None."""
    m = _SYMBOL_PAREN.search(label) or _SYMBOL_EQ.match(label)
    if m:
        return m.group(1).upper()
    for sym, pat in _DESCRIPTORS:
        if pat.search(label):
            return sym
    return None


def norm_level(text: str) -> str | None:
    """`33 kV`, `33KV`, `at 33 kV level` → `33kv`; used to pair parameter columns with the
    approved table's voltage column.  None when no level is named."""
    m = _LEVEL.search(text)
    if not m:
        return None
    return re.sub(r"[\s\-]", "", m.group(1).lower())


_BAND = re.compile(r"(below|above|up\s*to|upto|at|and above|&\s*above)?\s*(\d{2,3})\s*kv", re.I)


def band_key(text: str) -> str | None:
    """A voltage band as a comparable, readable key: `Supply below 11 kV` → `below 11 kV`;
    `at 11 kV up to 66 kV` → `11 kV, up to 66 kV`; `above 11 kV and up to 33 kV` →
    `above 11 kV, up to 33 kV`; `132 kV#` → `132 kV`; `HT`/`LT`/`EHV` without numbers → the
    word.  Used to pair a computation row with the approved row for the same band; different
    bands never pair."""
    parts = []
    for m in _BAND.finditer(text):
        mod = (m.group(1) or "").lower().replace(" ", "")
        n = m.group(2)
        word = {
            "below": "below ",
            "above": "above ",
            "upto": "up to ",
            "andabove": "and above ",
            "&above": "and above ",
        }
        parts.append(f"{word.get(mod, '')}{n} kV")
    if parts:
        return ", ".join(parts)
    m = re.search(r"\b(ehv|ht|lt|hv|lv)\b", text, re.I)
    return m.group(1).lower() if m else None


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v is not None and str(v) != "" else None
    except InvalidOperation:
        return None


def formula_statements(page_texts: dict[int, str]) -> dict[str, Any]:
    """The formula line and the symbol definitions as printed, each with its evidence."""
    out: dict[str, Any] = {"formula": None, "definitions": {}}
    for page, text in sorted(page_texts.items()):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            ln = line.strip()
            if not ln:
                continue
            if out["formula"] is None and FORMULA.search(ln):
                out["formula"] = {"text": ln[:300], "page_index": page, "line_no": i + 1}
            m = DEFINITION.match(ln)
            if m and m.group(1).upper() not in out["definitions"]:
                out["definitions"][m.group(1).upper()] = {"text": ln[:300], "page_index": page, "line_no": i + 1}
    return out


def read_parameters(cells: list[dict[str, Any]]) -> tuple[dict[str, dict[str, dict[str, Any]]], set[tuple[int, int]]]:
    """Parameter grids inside the CSS region: cells whose row (or column) label names a
    formula symbol and whose column (or row) label names a level.  Returns
    `{level: {symbol: {value, unit, evidence}}}` and the (page, grid) ids consumed, so the
    caller does not also read them as an approved table."""
    params: dict[str, dict[str, dict[str, Any]]] = {}
    consumed: set[tuple[int, int]] = set()
    by_grid: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for c in cells:
        by_grid.setdefault((c["page_index"], c["grid_ordinal"]), []).append(c)
    for gid, gcells in sorted(by_grid.items()):
        rows_syms = {symbol_of(" ".join(c["row_path"])) for c in gcells} - {None, "CAP"}
        cols_syms = {symbol_of(" ".join(c["header_path"])) for c in gcells} - {None, "CAP"}
        if len(rows_syms) >= 2:
            sym_from, level_from = "row_path", "header_path"
        elif len(cols_syms) >= 2:
            sym_from, level_from = "header_path", "row_path"
        else:
            continue
        found = False
        for c in gcells:
            if c["value_state"] not in ("value", "zero"):
                continue
            sym = symbol_of(" ".join(c[sym_from]))
            level = band_key(" ".join(c[level_from])) or norm_level(" ".join(c[level_from]))
            if sym is None or level is None:
                continue
            label = " ".join(c[sym_from])
            if _PAISE.search(label) or c.get("currency") == "paise":
                unit = "paise"
            elif sym == "L" or "%" in label:
                unit = "percent"
            else:
                unit = "rupees"
            params.setdefault(level, {})[sym] = {
                "value": c["normalised"].get("value"),
                "unit": unit,
                "label": label[:120],
                "evidence": EvidenceRef(
                    page_index=c["page_index"],
                    kind="cell",
                    grid_ordinal=c["grid_ordinal"],
                    row=c["row"],
                    col=c["col"],
                    header_path=c["header_path"],
                    row_path=c["row_path"],
                    excerpt=c["raw"][:400],
                ).model_dump(),
            }
            found = True
        if found:
            consumed.add(gid)
    return params, consumed


def rupees(p: dict[str, Any] | None) -> Decimal | None:
    """A parameter value in Rs/kWh (paise inputs are converted; percentages returned as is)."""
    if not p:
        return None
    v = _dec(p.get("value"))
    if v is None:
        return None
    return v / Decimal(100) if p.get("unit") == "paise" else v


def compute(params: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """S = T − [C/(1 − L/100) + D + R] from the printed inputs; D from DC + TC + WC when D
    itself is not printed; R defaults to 0 only when the order prints no R at all, and the
    result says so.  Missing T, C or L means no computation — never a guessed number."""
    t, c, l_ = rupees(params.get("T")), rupees(params.get("C")), _dec((params.get("L") or {}).get("value"))
    d = rupees(params.get("D"))
    d_components = None
    if d is None and all(k in params for k in ("DC", "TC", "WC")):
        parts = [rupees(params[k]) for k in ("DC", "TC", "WC")]
        if all(x is not None for x in parts):
            d = sum(parts, Decimal(0))
            d_components = {k: str(rupees(params[k])) for k in ("DC", "TC", "WC")}
    r = rupees(params.get("R"))
    assumed: list[str] = []
    if r is None:
        r = Decimal(0)
        assumed.append("R taken as 0: the order prints no carrying cost of regulatory assets")
    missing = [s for s, v in (("T", t), ("C", c), ("L", l_), ("D", d)) if v is None]
    if missing:
        return {"computed": None, "missing": missing, "assumed": assumed}
    if l_ >= 100:
        return {"computed": None, "missing": [], "assumed": assumed, "error": f"L = {l_}% is not a valid loss"}
    s = t - (c / (Decimal(1) - l_ / Decimal(100)) + d + r)
    return {
        "computed": str(s.quantize(Decimal("0.0001"))),
        "cap_20pct_of_T": str((t * Decimal("0.2")).quantize(Decimal("0.0001"))),
        "d_used": str(d),
        "d_components": d_components,
        "missing": [],
        "assumed": assumed,
    }


def derivation_for(level: str, params: dict[str, dict[str, Any]], statements: dict[str, Any]) -> dict[str, Any]:
    """The derivation dict a candidate carries: inputs with evidence, the formula as
    printed, the definitions, the recomputation and what was assumed."""
    comp = compute(params)
    return {
        "rule": "css_formula",
        "formula": "S = T - [C/(1 - L/100) + D + R]",
        "formula_as_printed": statements.get("formula"),
        "definitions": statements.get("definitions") or {},
        "level": level,
        "inputs": {k: v for k, v in params.items() if k not in ("S", "CAP")},
        "printed_computed": (params.get("S") or {}).get("value"),
        "printed_cap": (params.get("CAP") or {}).get("value"),
        **comp,
        "css_formula_version": CSS_FORMULA_VERSION,
    }
