"""Clause candidates (milestone 13, R-RULE): for each draft calculation rule, the pages of a
regulation where the rule's words and its parameter values appear — **proposals for a reviewer
to verify, never a verification.**  A rule's clause becomes verified only when a person checks
the excerpt against the page (``Clause.verified``); this module never sets it.

The ranking is plain: each page scores by the distinct significant words of the rule's title it
contains, and much more by the rule's regulation parameter values (``20`` percent read as
"20%", "20 %", "20 per cent"), because a page that states the value is where the clause is.  Without a value on
the page, at least three of the title's words (all of them, for a shorter title) must appear —
otherwise nothing is proposed: no proposal is better than noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rules import Rule

STOP = {
    "the", "and", "for", "from", "with", "year", "years", "of", "a", "an", "on", "in", "to", "by", "as",
    "its", "their", "total", "each", "per", "into", "than", "this", "that", "under", "over", "after",
    "before", "which", "what", "when", "rule", "draft", "computed", "projected", "petitioner",
}  # fmt: skip


@dataclass
class Candidate:
    page: int  # 1-based
    score: int
    words: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    snippet: str = ""


def terms(rule: Rule) -> tuple[list[str], list[str]]:
    """The rule's significant title words and its parameter values, as they may be printed."""
    words = sorted({w.lower() for w in re.findall(r"[A-Za-z&]{4,}", rule.title) if w.lower() not in STOP})
    values: list[str] = []
    for spec in rule.inputs.values():
        if spec.source == "regulation" and spec.value is not None:
            v = str(spec.value).rstrip("0").rstrip(".") if "." in str(spec.value) else str(spec.value)
            if spec.unit == "percent":
                values += [f"{v}%", f"{v} %", f"{v} per cent", f"{v}percent"]
            else:
                values.append(v)
    return words, values


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def rank(pages: list[str], rule: Rule, *, top: int = 3) -> list[Candidate]:
    """Pages ranked for one rule: a title word counts 1, a parameter value printed on the page 5.
    A page with no title word is never proposed (a bare number is everywhere)."""
    words, values = terms(rule)
    out: list[Candidate] = []
    for i, raw in enumerate(pages, start=1):
        text = _norm(raw)
        hit_words = [w for w in words if re.search(rf"\b{re.escape(w)}", text)]
        if not hit_words:
            continue
        hit_values = sorted({v for v in values if re.search(rf"(?<![\d.]){re.escape(v.lower())}", text)})
        if not hit_values and len(hit_words) < min(3, len(words)):
            continue  # words alone are weak evidence: a contents page names every topic
        score = len(hit_words) + 5 * len(hit_values)
        anchor = hit_values[0].lower() if hit_values else hit_words[0]
        at = text.find(anchor)
        snippet = raw_snippet(raw, at, text) if at >= 0 else ""
        out.append(Candidate(i, score, hit_words, hit_values, snippet))
    out.sort(key=lambda c: (-c.score, c.page))
    return out[:top]


def raw_snippet(raw: str, at: int, normalised: str, width: int = 220) -> str:
    """About ``width`` characters of the page around the anchor, whitespace collapsed."""
    flat = re.sub(r"\s+", " ", raw)
    start = max(0, at - width // 2)
    return ("…" if start else "") + flat[start : start + width].strip() + ("…" if start + width < len(flat) else "")
