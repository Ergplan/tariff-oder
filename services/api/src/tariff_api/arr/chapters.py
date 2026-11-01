"""ARR chapter localisation (ARR spec section 6, ADR-0018): which page spans of an order are
ARR chapters, and which taxonomy branch each serves, from the commission mapping's heading
cues over the page text.  Pure functions; the worker stage stores the proposals and a
reviewer confirms, corrects or excludes them before anything is read."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .taxonomy import Mapping

CHAPTERS_VERSION = "1"
# a chapter that runs to the end of the document is capped and flagged: the reviewer sets
# its true end (the annexures after the last ARR chapter are not ARR)
MAX_TAIL_PAGES = 30
_HEADING_NUMBER = re.compile(r"^\s*(?:chapter\s+[0-9ivx]+[:.\-–]?\s*|[0-9]+(?:\.[0-9]+)*[.)]?\s+|[a-z][.)]\s+)", re.I)
_SENTENCE_END = re.compile(r"[.;:,]\s*$")


@dataclass(frozen=True)
class ChapterProposal:
    ordinal: int
    branch: str
    cue_text: str
    cue_page: int
    page_start: int
    page_end: int
    note: str | None = None


def looks_like_heading(line: str) -> bool:
    """A short line that is numbered or set apart, not a sentence of the analysis.  Body text
    mentions "power purchase" on every page; only a heading opens a chapter."""
    t = line.strip()
    if not t or len(t) > 90:
        return False
    if _HEADING_NUMBER.match(t):
        return not _SENTENCE_END.search(t)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True
    return False


def _cue(mapping: Mapping, line: str) -> tuple[str, str] | None:
    body = _HEADING_NUMBER.sub("", line.strip()).lower()
    best: tuple[int, str, str] | None = None
    for ch in mapping.chapter_map:
        for pat in ch.heading_patterns:
            p = pat.lower()
            if re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", body):
                # the longest matching pattern wins ("power purchase cost" over "cost")
                if best is None or len(p) > best[0]:
                    best = (len(p), ch.branch, pat)
    return (best[1], best[2]) if best else None


def propose_chapters(page_lines: dict[int, list[str]], mapping: Mapping, page_count: int) -> list[ChapterProposal]:
    """Chapters in document order.  A chapter starts at a heading that carries one of the
    mapping's cues and runs to the page of the next chapter heading (inclusive, so a table
    above the next heading on that page stays in), or, for the last one, to the end of the
    document capped at ``MAX_TAIL_PAGES``.  Consecutive headings of one branch merge."""
    cues: list[tuple[int, str, str]] = []  # (page, branch, line)
    for page in sorted(page_lines):
        for line in page_lines[page]:
            if not looks_like_heading(line):
                continue
            hit = _cue(mapping, line)
            if hit:
                cues.append((page, hit[0], line.strip()[:300]))
    merged: list[tuple[int, str, str]] = []
    for c in cues:
        if merged and merged[-1][1] == c[1]:
            continue
        merged.append(c)
    out: list[ChapterProposal] = []
    for i, (page, branch, text) in enumerate(merged):
        note = None
        if i + 1 < len(merged):
            nxt = merged[i + 1][0]
            end = max(page, nxt if nxt > page else page)
        else:
            end = min(page_count, page + MAX_TAIL_PAGES - 1)
            if end < page_count:
                note = f"last chapter capped at {MAX_TAIL_PAGES} pages; set its true end page"
        out.append(ChapterProposal(i + 1, branch, text, page, page, end, note))
    return out
