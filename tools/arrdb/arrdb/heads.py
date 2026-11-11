"""Canonical ARR heads: the printed row label of a summary table, mapped to one code.

The label as printed is always kept next to the code; the code only groups rows so that a
question such as "depreciation approved for every DISCOM" can be answered across orders whose
tables word the same head differently.  A label no rule matches is ``other``.
"""

from __future__ import annotations

import re

# (code, name, pattern) — the first match wins, so specific heads come before general ones.
HEADS: list[tuple[str, str, str]] = [
    ("nti", "Non-tariff income (deducted)", r"non[- ]?tariff|other income|income from other business"),
    (
        "regulatory_asset",
        "Regulatory asset / past gap recovery",
        r"regulatory asset|amorti[sz]|past (gap|arr)|true[- ]?up (impact|gap)|"
        r"previous (year|years).{0,20}gap|impact of",
    ),
    ("gap", "Revenue gap / (surplus)", r"\bgap\b|\bsurplus\b|\bdeficit\b"),
    (
        "revenue",
        "Revenue from tariff",
        r"revenue (from|at|through)|expected revenue|revenue (billed|realised|realized)|"
        r"revenue from sale|sale of power|existing tariff|tariff income",
    ),
    ("interest_wc", "Interest on working capital", r"working capital"),
    ("interest_sd", "Interest on security deposit", r"security deposit|consumer.{0,12}deposit|\bs\.?\s?d\b"),
    (
        "interest_loan",
        "Interest on loans",
        r"interest on (long[- ]term )?(project |capital )?loan|interest (and|&) finance|"
        r"interest on borrowing|interest on loan|loan interest|interest charges|\binterest\b(?!.*capitali)",
    ),
    ("finance_charges", "Finance and bank charges", r"finance charge|bank (and|&) finance|guarantee fee"),
    ("tax", "Income tax", r"income tax|tax on (income|roe)|(?<!water )\btax\b"),
    ("roe", "Return on equity", r"return on (equity|capital|net fixed)|\bro[ec]\b|reasonable return"),
    ("bad_debts", "Provision for bad debts", r"bad (and doubtful )?debt|doubtful"),
    ("depreciation", "Depreciation", r"depreciation"),
    ("employee", "Employee expenses", r"employee|salar|terminal|pension|retir"),
    ("ag", "A&G expenses", r"a\s*&\s*g\b|administrat|general expense"),
    ("rm", "R&M expenses", r"r\s*&\s*m\b|repair"),
    ("om", "O&M expenses", r"o\s*&\s*m|operation (and|&) maintenance|operation and maint"),
    (
        "power_purchase",
        "Power purchase cost",
        r"power purchase|purchase of power|cost of power|energy purchase|"
        r"bulk supply|power procurement",
    ),
    (
        "transmission",
        "Transmission and SLDC charges",
        r"transmission|\bsldc\b|pgcil|ptcul|\bists\b|load despatch|wheeling",
    ),
    ("carrying_cost", "Carrying cost", r"carrying cost|holding cost"),
    ("net_arr", "Net ARR", r"net (aggregate )?(revenue requirement|arr)|arr after|net arr|net revenue"),
    (
        "arr",
        "ARR (aggregate / total revenue requirement)",
        r"aggregate revenue requirement|total revenue requirement|"
        r"revenue requirement|\barr\b|total expenditure|total cost|gross arr|total distribution cost",
    ),
]

_COMPILED = [(c, re.compile(p, re.I)) for c, _, p in HEADS]

HEAD_NAMES = {c: n for c, n, _ in HEADS} | {"other": "Other (see the printed label)"}


def head_of(label: str) -> str:
    """The canonical head of a printed label ('other' when no rule matches)."""
    text = re.sub(r"\s+", " ", label).strip()
    for code, rx in _COMPILED:
        if rx.search(text):
            return code
    return "other"
