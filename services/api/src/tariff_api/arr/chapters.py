"""ARR chapter localisation (ARR spec section 6, ADR-0018): which page spans of an order are
ARR chapters, and which taxonomy branch each serves, from the commission mapping's heading
cues over the page text.  Pure functions; the worker stage stores the proposals and a
reviewer confirms, corrects or excludes them before anything is read."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .taxonomy import Mapping

CHAPTERS_VERSION = "2"
# a chapter that runs to the end of the document is capped and flagged: the reviewer sets
# its true end (the annexures after the last ARR chapter are not ARR)
MAX_TAIL_PAGES = 30
# a section number has components of one or two digits ("4.", "6.15."); a date ("17.06.2026")
# or a value ("121.89") is not one
_HEADING_NUMBER = re.compile(
    r"^\s*(?:chapter\s+[0-9ivx]+[:.\-–]?\s*|[0-9]{1,2}(?:\.[0-9]{1,2})*[.)]?\s+|[a-z][.)]\s+)", re.I
)
_SECTION_NUMBER = re.compile(r"^\s*([0-9]{1,2}(?:\.[0-9]{1,2}){0,1})\.?\s+(?=\S)")
_SENTENCE_END = re.compile(r"[.;:,]\s*$")
_LEADER = re.compile(r"(?:\.\s?){5,}|…{2,}|_{5,}")
_CAPTION = re.compile(r"^\s*(?:table|annexure|figure|format|statement)\s*(?:no\.?\s*)?[0-9ivx]+", re.I)
_FY_TEXT = re.compile(r"(?:FY\s*)?20\d{2}\s*[-–/]\s*(?:20)?\d{2}", re.I)
_NUMBER_TOKEN = re.compile(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?%?\)?(?![A-Za-z])")
FURNITURE_MIN_PAGES = 5


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
    """A short line that is numbered or set apart, not a sentence of the analysis, a table
    row, a table caption or a contents entry.  Body text mentions "power purchase" on every
    page; only a heading opens a chapter."""
    t = line.strip()
    if not t or len(t) > 90 or _LEADER.search(t) or _CAPTION.match(t):
        return False
    body = _HEADING_NUMBER.sub("", t, count=1)
    # a table row: several numbers, or cells set apart by wide gaps
    if len(_NUMBER_TOKEN.findall(_FY_TEXT.sub(" ", body))) >= 2 or len(re.findall(r"\S\s{3,}\S", t)) >= 2:
        return False
    if _HEADING_NUMBER.match(t):
        if _SENTENCE_END.search(t) or not body or body[0].islower():
            return False
        words = re.findall(r"[A-Za-z][A-Za-z'&-]*", body)
        small = {"and", "of", "the", "for", "in", "on", "to", "by", "a", "an", "or", "as", "at", "with", "from"}
        capitalised = [w for w in words if w.lower() in small or w[0].isupper()]
        # a numbered paragraph is prose: many words, mostly not capitalised
        return not (len(words) >= 7 and len(capitalised) / len(words) < 0.6)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True
    return False


def _longest_run(heads: list) -> list:
    """The heaviest subsequence whose section numbers never decrease (document order kept):
    a heading weighs one, a heading that carries a branch cue two, so a stray list item does
    not displace a section on a tie."""
    n = len(heads)
    weight = [1 + (1 if h[2] else 0) for h in heads]
    best = weight[:]
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if heads[j][1] <= heads[i][1] and best[j] + weight[i] > best[i]:
                best[i], prev[i] = best[j] + weight[i], j
    i = max(range(n), key=lambda k: best[k]) if n else -1
    out = []
    while i != -1:
        out.append(heads[i])
        i = prev[i]
    return out[::-1]


def furniture(page_lines: dict[int, list[str]]) -> set[str]:
    """Running headers and footers: a line printed in the first or last three lines of at
    least ``FURNITURE_MIN_PAGES`` pages ("AGGREGATE REVENUE REQUIREMENT OF FY 2026-27" on every
    page of that part).  Page furniture is never a chapter heading."""
    seen: dict[str, set[int]] = {}
    for page, lines in page_lines.items():
        for ln in [*lines[:3], *lines[-3:]]:
            key = _norm(ln)
            if key:
                seen.setdefault(key, set()).add(page)
    return {k for k, pages in seen.items() if len(pages) >= FURNITURE_MIN_PAGES}


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


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
    document capped at ``MAX_TAIL_PAGES``.  Consecutive headings of one branch merge.

    Running headers and footers, contents entries, table captions, table rows and numbered
    paragraphs are not headings.  When the order numbers its sections, only one- or two-level
    section headings ("4.", "6.15.") open chapters; a running header names the part a chapter
    sits in (the true-up, the APR, the ARR of a year) in the chapter's note."""
    skip = furniture(page_lines)
    # every heading in document order: (page, section number or None, branch cue or None, text)
    heads: list[tuple[int, tuple[int, ...] | None, str | None, str]] = []
    part_of: dict[int, str] = {}
    for page in sorted(page_lines):
        lines = page_lines[page]
        if lines and sum(1 for ln in lines if _LEADER.search(ln)) >= max(3, len(lines) // 4):
            continue  # a contents page
        for ln in [*lines[:3], *lines[-3:]]:
            n = _norm(ln)
            if n in skip and len(ln.strip()) > 12 and not re.search(r"^[#\s/|-]+$|\bpage\b|# of #", n):
                part_of.setdefault(page, ln.strip()[:120])
        for line in lines:
            if _norm(line) in skip or not looks_like_heading(line):
                continue
            m = _SECTION_NUMBER.match(line)
            number = tuple(int(x) for x in m.group(1).split(".")) if m else None
            hit = _cue(mapping, line)
            if number is not None or hit:
                heads.append((page, number, hit[0] if hit else None, line.strip()[:300]))
    numbered = [h for h in heads if h[1] is not None]
    if numbered:
        # the order numbers its sections: keep the longest run of section numbers that never
        # goes backwards (a list item "5.1" inside section 4.16, or "3." inside a section, is
        # not a section), and only those open or close chapters
        sections = _longest_run(numbered)
        cues = [(pg, branch, text, num) for pg, num, branch, text in sections if branch]
        boundaries = [(pg, num) for pg, num, _b, _t in sections if num is not None and len(num) == 1]
        # a part's own heading ("4.  Truing-up for FY 2024-25"): a one-level section that names
        # a year or a part, looked up among every heading (not only the run, which a stray
        # earlier "4.2" can push it out of)
        tops = [
            (pg, num[0], text)
            for pg, num, _b, text in numbered
            if len(num) == 1
            and (_FY_TEXT.search(text) or re.search(r"tru(?:e|ing)[- ]?up|performance|revenue", text, re.I))
        ]
    else:
        cues = [(pg, branch, text, None) for pg, _n, branch, text in heads if branch]
        boundaries = []
        tops = []
    merged: list[tuple[int, str, str, tuple[int, ...] | None]] = []
    for c in cues:
        if merged and merged[-1][1] == c[1]:
            continue
        merged.append(c)
    out: list[ChapterProposal] = []
    for i, (page, branch, text, _numbered) in enumerate(merged):
        notes = []
        if i + 1 < len(merged):
            nxt = merged[i + 1][0]
            end = max(page, nxt if nxt > page else page)
            # a top-level section without a cue ("4. TRUE UP OF FY 2024-25") ends the chapter
            this = merged[i][3]
            stop = [
                b_page
                for b_page, b_num in boundaries
                if page < b_page < end and this is not None and b_num[0] > this[0]
            ]
            if stop:
                end = min(stop)
        else:
            end = min(page_count, page + MAX_TAIL_PAGES - 1)
            if end < page_count:
                notes.append(f"last chapter capped at {MAX_TAIL_PAGES} pages; set its true end page")
        this = merged[i][3]
        top = [t for t in tops if this is not None and t[1] == this[0] and t[0] <= page]
        if top and top[-1][2] != text:
            notes.append(f"in section: {top[-1][2][:120]}")
        if part_of.get(page):
            notes.append(f"in the part headed: {part_of[page]}")
        out.append(ChapterProposal(i + 1, branch, text, page, page, end, "; ".join(notes) or None))
    return out


def part_from_note(note: str | None) -> str | None:
    """The part a chapter sits in, as its proposal recorded it: its top-level section ("in
    section: 4. Truing-up for FY 2024-25"), else the running header of its pages."""
    for key in ("in section", "in the part headed"):
        m = re.search(rf"{key}:\s*(.+?)\s*(?:;|$)", note or "")
        if m:
            return m.group(1)
    return None
