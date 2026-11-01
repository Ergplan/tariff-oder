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
_SMALL = {"and", "of", "the", "for", "in", "on", "to", "by", "a", "an", "or", "as", "at", "with", "from", "under"}
# a numbered sentence broken at the line's end, or opening like prose, is a paragraph
_PROSE_END = re.compile(
    r"\b(?:to|the|of|and|for|in|on|by|with|a|an|as|that|is|are|was|were|be|has|have|its|their|this|which)\s*$",
    re.I,
)
_PROSE_START = re.compile(
    r"^(?:the|this|these|it|its|in\s+(?:the|view|this)|on|as|based|accordingly|further|furthermore|hence|thus|"
    r"therefore|however|since|considering|regarding|with|while|after|before|during|petitioner|commission)\b",
    re.I,
)
_CHAPTER = re.compile(r"^\s*chapter\s+(\d{1,2})\s*[:.\-–]\s*(?:\S|$)", re.I)
NUMBERED_MODE_MIN = 5
# a lettered part in capitals: "B.   ARR & RETAIL SUPPLY TARIFF PROPOSAL OF THE DISCOMs" (OERC),
# "A2: AGGREGATE REVENUE REQUIREMENT FOR PETITIONERS" (MPERC, ordered by its number)
_PART_LETTER = re.compile(r"^\s*([A-Z])(\d{1,2})?\s*[.:]\s+(\S.{3,})$")
# a part that reports the petition or the hearing, not the Commission's decisions
_NOT_DECISIONS = re.compile(
    r"public\s+(?:hearing|consultation)|objection|suggestions?\s+(?:and|&)|stakeholder|brief\s+facts|"
    r"procedural\s+history|petitioner'?s?\s+submissions?\s*$|summary\s+of\s+(?:the\s+)?petition|"
    r"proposals?\s+of\s+(?:the\s+)?(?:licensees?|discoms?|petitioners?)|tariff\s+proposal\s+of|"
    r"observations\s+of\s+(?:the\s+)?(?:consumer\s+counsel|state\s+advisory)|views\s+of\s+(?:the\s+)?government",
    re.I,
)


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
        if _PROSE_END.search(body) or _PROSE_START.match(body):
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


def title_heading(line: str) -> bool:
    """An unnumbered Title Case heading ("Interest on Working Capital", "Operation & Maintenance
    Expenses"): short, every significant word capitalised, no sentence end, no number but a
    year.  Used only for orders whose numbers mark paragraphs, not sections."""
    t = line.strip()
    if not t or len(t) > 80 or _LEADER.search(t) or _CAPTION.match(t) or re.search(r"\S\s{3,}\S", t):
        return False
    if _SENTENCE_END.search(t) or not t[0].isupper() or _NUMBER_TOKEN.search(_FY_TEXT.sub(" ", t)):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'’&/()-]*", t)
    sig = [w for w in words if w.lower() not in _SMALL]
    if not 1 <= len(words) <= 10 or not sig:
        return False
    return sum(1 for w in sig if w[0].isupper()) / len(sig) >= 0.8


def lettered_parts(found: list[tuple[int, tuple[int, ...], None, str]]) -> list[tuple[int, tuple[int, ...], None, str]]:
    """Capital-lettered parts in capitals ("A. PROCEDURAL HISTORY" … "I. OBSERVATIONS AND
    DIRECTIONS OF THE COMMISSION"; "A1: ORDER" … "A8: …") are an order's parts when they run
    in order of their letters (or numbers) and pages: the first of each, kept only while both go
    forward, from the first.  Fewer than three such parts are not a structure (a table's "A."
    row is not a part)."""
    firsts: dict[int, tuple[int, tuple[int, ...], None, str]] = {}
    for f in found:
        firsts.setdefault(f[1][0], f)
    out: list[tuple[int, tuple[int, ...], None, str]] = []
    for n in sorted(firsts):
        if (not out and n != 1) or (out and (n > out[-1][1][0] + 2 or firsts[n][0] < out[-1][0])):
            break
        out.append(firsts[n])
    return out if len(out) >= 3 else []


def chapter_title(lines: list[str], k: int) -> str:
    """A "Chapter N:" line with the capitalised lines its title wraps onto ("Chapter 5: TRUE-UP
    FOR FY" over "2024-25"; "Chapter 5:" over "TRUE-UP FOR FY 2024-25")."""
    parts = [lines[k].strip()]
    for nxt in lines[k + 1 : k + 4]:
        t = nxt.strip()
        letters = [c for c in t if c.isalpha()]
        upper = not letters or sum(c.isupper() for c in letters) / len(letters) > 0.8
        if re.fullmatch(r"[\d\s.]+", t):
            break  # a page number, not a year ("2024-25") of the title
        if not t or len(t) > 80 or not upper or _SECTION_NUMBER.match(t) or _CHAPTER.match(t) or _LEADER.search(t):
            break
        parts.append(t)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def is_furniture(line: str, skip: set[str]) -> bool:
    """Whether a line is a running header or footer of the order (see :func:`furniture`)."""
    return _norm(line) in skip


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
    titled: list[tuple[int, None, str, str]] = []  # Title Case headings with a cue
    chapters_: list[tuple[int, tuple[int, ...], None, str]] = []  # "Chapter 5: TRUE-UP FOR FY 2024-25"
    numbered_prose = 0  # numbered lines that are sentences: the mark of paragraph numbering
    lettered: list[tuple[int, tuple[int, ...], None, str]] = []  # "A.  PROCEDURAL HISTORY" parts
    part_of: dict[int, str] = {}
    for page in sorted(page_lines):
        lines = page_lines[page]
        if lines and sum(1 for ln in lines if _LEADER.search(ln)) >= max(3, len(lines) // 4):
            continue  # a contents page
        for ln in [*lines[:3], *lines[-3:]]:
            n = _norm(ln)
            if n in skip and len(ln.strip()) > 12 and not re.search(r"^[#\s/|-]+$|\bpage\b|# of #", n):
                part_of.setdefault(page, ln.strip()[:120])
        for k, line in enumerate(lines):
            if _norm(line) in skip:
                continue
            cm = _CHAPTER.match(line)
            if cm and len(line.strip()) <= 120:
                chapters_.append((page, (int(cm.group(1)),), None, chapter_title(lines, k)[:300]))
            lm = _PART_LETTER.match(line)
            if lm and len(line.strip()) <= 120:
                body = [c for c in lm.group(3) if c.isalpha()]
                if body and sum(c.isupper() for c in body) / len(body) > 0.8:
                    n = int(lm.group(2)) if lm.group(2) else ord(lm.group(1)) - 64
                    lettered.append((page, (n,), None, chapter_title(lines, k)[:300]))
            if not looks_like_heading(line):
                if _SECTION_NUMBER.match(line) and len(line.strip()) > 40:
                    numbered_prose += 1
                if title_heading(line) and (hit := _cue(mapping, line)):
                    titled.append((page, None, hit[0], line.strip()[:300]))
                continue
            m = _SECTION_NUMBER.match(line)
            number = tuple(int(x) for x in m.group(1).split(".")) if m else None
            hit = _cue(mapping, line)
            if number is not None or hit:
                heads.append((page, number, hit[0] if hit else None, line.strip()[:300]))
    numbered = [h for h in heads if h[1] is not None]
    if not chapters_:
        chapters_ = lettered_parts(lettered)
    paragraphs = False
    if (
        chapters_
        and (sum(1 for h in numbered if h[2]) < NUMBERED_MODE_MIN or numbered_prose >= 10 * len(numbered))
        and numbered_prose >= max(3, 3 * len(numbered))
    ):
        # the numbers mark paragraphs, not sections: read the order by its unnumbered headings
        # (capitals or Title Case) inside its "Chapter N" parts
        numbered, paragraphs = [], True
        firsts: dict[int, tuple] = {}
        for c in chapters_:
            firsts.setdefault(c[1][0], c)
        heads = sorted([h for h in heads if h[1] is None] + titled, key=lambda h: h[0])

        def chapter_of(pg: int) -> tuple[int, ...] | None:
            before = [c for c in firsts.values() if c[0] <= pg]
            return max(before, key=lambda c: c[0])[1] if before else None

        cues = [(pg, branch, text, chapter_of(pg)) for pg, _n, branch, text in heads if branch]
        boundaries = [(c[0], c[1]) for c in firsts.values()]
        tops = [(c[0], c[1][0], c[3]) for c in firsts.values()]
    elif numbered:
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
        if merged and merged[-1][1] == c[1] and (not paragraphs or merged[-1][3] == c[3]):
            continue  # the same line again (in the same part, when the parts are "Chapter N")
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
            if paragraphs:
                # a "Chapter N" part opens on its own page: the chapter before ends a page earlier
                stop = [
                    b_page - 1
                    for b_page, b_num in boundaries
                    if page < b_page <= end and (this is None or b_num[0] > this[0])
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
        context = " ".join([top[-1][2] if top else "", part_of.get(page, "")])
        if _NOT_DECISIONS.search(context):
            notes.append("this part reports the petition or the hearing: likely not the Commission's decisions")
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
