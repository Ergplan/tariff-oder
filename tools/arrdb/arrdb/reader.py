"""Read the ARR summary tables of a tariff order PDF, row by row, from its text layer.

A table is found by its printed title ("Table 4.52: Revenue Requirement approved by the
Commission for FY 2026-27").  Its header rows give each value column a meaning — the licensee
(combined orders print one column group per DISCOM), the year and the voice (claimed by the
petitioner, approved / admitted by the Commission, actual) — and every data row keeps its
printed label, the page, and the line as printed (the quote).

Nothing here is reviewed: a value is what the text layer says at that place, and the column
meaning is a reading of the header that a person can check against the quote and the page.
Scanned pages without a text layer yield nothing (they are reported, not guessed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from .heads import head_of

NUM = re.compile(r"^\(?[-–]?\(?\d[\d,]*(\.\d+)?\)?\**$")
DASH = re.compile(r"^(-|–|—|nil|na|n\.a\.?)$", re.I)
TITLE = re.compile(r"^table\b", re.I)
ARR_TITLE = re.compile(
    r"revenue requirement|\barr\b|summary of (the )?(approved )?(arr|revenue)|aggregate revenue",
    re.I,
)
NOT_ARR_TITLE = re.compile(
    r"allocation|segregation|wheeling|retail supply business|supply business|cross[- ]subsid|"
    r"category[- ]wise|power purchase|sales|energy|loss|capital|depreciation|o\s*&\s*m|employee|"
    r"interest|return on|tariff schedule|rate schedule|recovery|carrying|voltage|\bcss\b|"
    r"open access|subsidy|kwh|per unit|connected load|number of consumer|billing determinant|parameters|"
    r"consumer category|load\b|\bmu\b",
    re.I,
)
OTHER_ENTITY = re.compile(
    r"\bgenco\b|generat|\btransco\b|transmission (licensee|company|business|utility)|\bsldc\b|power station|"
    r"thermal|hydro|cspgcl|csptcl|upptcl|ptcul|ujvn|htps|dspm|kwtpp|abvtpp|hasdeo|\btps\b",
    re.I,
)
PART_COLUMN = re.compile(
    r"agricultur|retail|\bwires?\b|\bsupply\b|htps|dspm|kwtpp|abvtpp|hasdeo|\bunits?\b|\buom\b|\bmus?\b|"
    r"deviation|formula|reference|variance|difference|\bratio\b|%|\bkwh\b|\bmw\b",
    re.I,
)
PART_BUSINESS = re.compile(
    r"\bwires?\b|supply business|retail supply|wheeling business|distribution business \(w|"
    r"\bw(heeling)?\s*&\s*r",
    re.I,
)
TOC = re.compile(r"\.{4,}|…{2,}")
YEAR = re.compile(
    r"\bFY\s*'?\s*(20)?(\d{2})\s*[-–/]\s*(20)?(\d{2})\b|\b(20\d{2})\s*[-–/]\s*(20)?(\d{2})\b|\bFY\s*'?\s*(\d{2})\b",
    re.I,
)
UNIT = [
    (re.compile(r"\bcrore|\bcrs?\b\.?|\brs\.?\s*(in\s*)?crs?|\binr\s*crore", re.I), "crore", 1.0),
    (re.compile(r"\blakh|\blac?s\b|\blacs\b", re.I), "lakh", 0.01),
    (re.compile(r"\bmillion|\brs\.?\s*mn\b|\bmn\b", re.I), "million", 0.1),
]
SERIAL = re.compile(r"^(\(?[ivxlc]+[.)]|\(?[a-z][.)]|\d{1,2}[.)]?|[a-z]|[A-Z](=[A-Z+\-*/()]+)?|[ivx]+)$", re.I)


def fy(start: int) -> str:
    return f"FY{start}-{(start + 1) % 100:02d}"


def years_in(text: str) -> list[str]:
    out: list[str] = []
    for m in YEAR.finditer(text):
        if m.group(2) and m.group(4):
            a, b = int(m.group(2)), int(m.group(4))
        elif m.group(5):
            a, b = int(m.group(5)) % 100, int(m.group(7))
        elif m.group(8):
            # "FY24" names the year ending in March 2024 (FY2023-24), as HPERC's tables do
            b = int(m.group(8))
            a = b - 1
        else:
            continue
        if (a + 1) % 100 != b % 100 or not 5 <= a <= 45:
            continue
        y = fy(2000 + a)
        if y not in out:
            out.append(y)
    return out


def number(tok: str) -> float | None:
    t = tok.replace("–", "-").replace("*", "")
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.strip("()-")
    try:
        v = float(t.replace(",", ""))
    except ValueError:
        return None
    return -v if neg else v


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Row:
    words: list[Word]
    page: int
    height: float = 842.0

    @property
    def y(self) -> float:
        return min(w.y0 for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def split(self) -> tuple[list[Word], list[Word]]:
        """(label words, value words): values are the numeric or dash tokens after the label.
        A dash followed by more words is part of the label ("Additional Claim – Past ARR")."""
        words = list(self.words)
        while words and SERIAL.match(words[0].text) and len(words) > 1 and not NUM.match(words[1].text):
            words.pop(0)
        label: list[Word] = []
        values: list[Word] = []
        for w in words:
            is_val = bool(NUM.match(w.text) or DASH.match(w.text))
            if is_val and label:
                values.append(w)
            elif is_val:
                label.append(w)  # a number before any word: part of the label ("2024-25")
            elif values:
                if w.text in {"*", "#", "@", "%"}:
                    continue
                if all(DASH.match(v.text) for v in values):
                    label.extend(values)
                    values = []
                    label.append(w)
                # otherwise a trailing word (a unit, a footnote) is ignored
            else:
                label.append(w)
        # a bare reference letter between label and values (MPERC's "C", "D=A-B-C")
        while len(label) > 1 and re.fullmatch(r"[A-Z](=[A-Z+\-*/()]+)?|\([A-Z]\)", label[-1].text):
            label.pop()
        # a label made only of numbers is not a label (a values-only row)
        if label and all(NUM.match(w.text) or DASH.match(w.text) for w in label):
            values = label + values
            label = []
        return label, values


def page_rows(page: Any, pno: int, tol: float = 2.5) -> list[Row]:
    ws = [Word(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
    ws.sort(key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    rows: list[list[Word]] = []
    ys: list[float] = []
    for w in ws:
        cy = (w.y0 + w.y1) / 2
        if rows and abs(cy - ys[-1]) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
            ys.append(cy)
    return [Row(sorted(r, key=lambda w: w.x0), pno, page.rect.height) for r in rows]


def phrases(words: list[Word], gap: float = 9.0) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.x0):
        if out and w.x0 - out[-1][-1].x1 <= gap:
            out[-1].append(w)
        else:
            out.append([w])
    return out


@dataclass
class Column:
    xc: float
    x0: float
    x1: float
    header: list[str] = field(default_factory=list)


def cluster(values: list[Word], rows: list[list[Word]] | None = None) -> list[Column]:
    """The value columns of a table.  The rows printing the most values set the columns (a
    number in every column); a count seen in two or more rows wins over a single row's stray
    extra number.  Without rows, values are grouped by their right edges."""
    if rows:
        counts = [len(r) for r in rows if r]
        if counts:
            best = max(counts)
            for n in sorted(set(counts), reverse=True):
                if counts.count(n) >= 2 or n == max(counts) and len(counts) == 1:
                    best = n
                    break
            full = [sorted(r, key=lambda w: w.x0) for r in rows if len(r) == best]
            cols: list[Column] = []
            for i in range(best):
                x0s = sorted(r[i].x0 for r in full)
                x1s = sorted(r[i].x1 for r in full)
                x0, x1 = x0s[len(x0s) // 2], x1s[len(x1s) // 2]
                cols.append(Column((x0 + x1) / 2, x0, x1))
            # widen each column to the values that fall in it
            for r in rows:
                for w in r:
                    i = place(cols, w)
                    if i is not None:
                        c = cols[i]
                        c.x0, c.x1 = min(c.x0, w.x0), max(c.x1, w.x1)
            for c in cols:
                c.xc = (c.x0 + c.x1) / 2
            return cols
    cols = []
    for w in sorted(values, key=lambda w: w.x1):
        if cols and abs(cols[-1].x1 - w.x1) <= 8:
            c = cols[-1]
            c.x0, c.x1 = min(c.x0, w.x0), max(c.x1, w.x1)
            c.xc = (c.x0 + c.x1) / 2
        else:
            cols.append(Column(w.xc, w.x0, w.x1))
    return sorted(cols, key=lambda c: c.xc)


def place(cols: list[Column], w: Word) -> int | None:
    """The column a value belongs to: the one it overlaps most, else the nearest within reach."""
    best, ov = None, 0.0
    for i, c in enumerate(cols):
        o = min(c.x1, w.x1) - max(c.x0, w.x0)
        if o > ov:
            best, ov = i, o
    if best is not None:
        return best
    i = min(range(len(cols)), key=lambda i: abs(cols[i].xc - w.xc))
    return i if abs(cols[i].xc - w.xc) <= 30 else None


def nearest(cols: list[Column], x: float) -> int:
    return min(range(len(cols)), key=lambda i: abs(cols[i].xc - x))


def label_header(cols: list[Column], header_rows: list[Row]) -> None:
    """Give each column the header words above it.  A header row with fewer phrases than
    columns is a group row (a licensee or a year over several columns): each column takes the
    phrase whose span, widened to the midpoints between phrases, holds its centre."""
    for r in header_rows:
        ps = [p for p in phrases(r.words) if not (len(p) == 1 and len(p[0].text) <= 1)]
        if not ps:
            continue
        # phrases left of the first column are the label column's header ("Particulars")
        ps = [p for p in ps if p[-1].x1 > cols[0].x0 - 30]
        if not ps:
            continue
        if len(ps) >= len(cols):
            for p in ps:
                i = nearest(cols, (p[0].x0 + p[-1].x1) / 2)
                cols[i].header.append(" ".join(w.text for w in p))
        else:
            centres = [(p[0].x0 + p[-1].x1) / 2 for p in ps]
            bounds = [
                (
                    -1e9 if i == 0 else (centres[i - 1] + centres[i]) / 2,
                    1e9 if i == len(ps) - 1 else (centres[i] + centres[i + 1]) / 2,
                )
                for i in range(len(ps))
            ]
            for c in cols:
                for p, (lo, hi) in zip(ps, bounds, strict=True):
                    pc = (p[0].x0 + p[-1].x1) / 2
                    reach = max(60.0, 1.5 * (p[-1].x1 - p[0].x0))
                    if lo <= c.xc < hi and abs(c.xc - pc) <= reach:
                        c.header.append(" ".join(w.text for w in p))
                        break


def unit_of(texts: list[str]) -> tuple[str | None, float | None]:
    for t in texts:
        for rx, name, factor in UNIT:
            if rx.search(t):
                return name, factor
    return None, None


STRICT_APPROVED = re.compile(r"approv|admit|allow|determin|consider|trued?[- ]?up|disallow", re.I)
CLAIMED = re.compile(r"claim|propos|petition|submi|project|sought|filed|asked|requested|estimat", re.I)
ACTUAL = re.compile(r"actual|audited|accounts", re.I)
LOOSE_APPROVED = re.compile(r"commission|\bnow\b|final|review", re.I)
EARLIER = re.compile(
    r"provisional|(myt|tariff|earlier|previous|last|apr)\s*(order|t\.?o\.?)|order dated|as per (the )?order|"
    r"approved in (the )?(myt|tariff|to\b|apr|earlier|previous)|\bto\b.{0,4}approv|^apr$|"
    r"approved (in|vide) (order|t\.?o\.?)|^(arr|apr|t\.?o\.?|tariff order|myt( order)?)$",
    re.I,
)


def voice_of(text: str) -> str | None:
    """claimed, approved, approved_earlier (an earlier order's approval quoted for comparison),
    actual, or None when the words do not say."""
    t = text.strip()
    if not t:
        return None
    if EARLIER.search(t):
        return "approved_earlier"
    firm = re.search(r"approv|admit|allow|determin|consider|disallow", t, re.I)
    if CLAIMED.search(t) and (
        not firm or re.search(r"(claimed|proposed|projected|submitted|sought) (by|for|in)", t, re.I)
    ):
        return "claimed"
    if STRICT_APPROVED.search(t):
        return "approved"
    if ACTUAL.search(t):
        return "actual"
    if LOOSE_APPROVED.search(t):
        return "approved"
    return None


@dataclass
class Table:
    title: str
    page: int
    unit: str | None
    factor: float | None
    columns: list[dict[str, Any]]
    lines: list[dict[str, Any]]
    pages: list[int]


def is_paragraph(r: Row) -> bool:
    label, values = r.split()
    return not values and len(r.words) >= 9


FOOTER = re.compile(r"regulatory commission|^page\s*\d+|^\d{1,4}$|\bpage\s+\d+\s*(of\s*\d+)?$", re.I)


def is_footer(r: Row, height: float) -> bool:
    return r.y > height * 0.8 and bool(FOOTER.search(r.text)) and len(r.words) <= 10


def read_tables(
    path: str, licensees: list[str], aliases: dict[str, list[str]] | None = None, title_rx: re.Pattern[str] = ARR_TITLE
) -> dict[str, Any]:
    """Every ARR summary table of the PDF, with its rows and its columns' meanings."""
    doc = pymupdf.open(path)
    aliases = aliases or {}
    no_text = 0
    rows_by_page: list[list[Row]] = []
    heights: list[float] = []
    for i, pg in enumerate(doc):
        rs = page_rows(pg, i + 1)
        if sum(len(r.words) for r in rs) < 15:
            no_text += 1
        heights.append(pg.rect.height)
        rows_by_page.append([r for r in rs if not is_footer(r, pg.rect.height) and r.y > pg.rect.height * 0.03])
    tables: list[Table] = []
    for pi, rows in enumerate(rows_by_page):
        for ri, r in enumerate(rows):
            if not TITLE.match(r.words[0].text):
                continue
            title = r.text
            nxt_title = 0
            # a title can run over two rows: only when the first row is visibly unfinished
            if (
                ri + 1 < len(rows)
                and not rows[ri + 1].split()[1]
                and len(rows[ri + 1].words) <= 14
                and not TITLE.match(rows[ri + 1].words[0].text)
                and rows[ri + 1].y - r.y < 26
            ):
                nxt = rows[ri + 1].text
                unfinished = (
                    len(r.words) <= 4
                    or not re.search(r"\)\s*$|crore\.?\s*$|\bcr\.?\s*$|lakh\.?\s*$", title, re.I)
                    and (
                        re.search(r"\b(of|for|the|and|by|in|&|to|from|with|on|as)\s*$|[-–:,]\s*$", title, re.I)
                        or re.match(r"^[a-z(]|^(for|of|by|and|as|in)\b", nxt)
                        or re.search(r"^\(?rs\.?|crore|lakh", nxt, re.I)
                    )
                )
                if unfinished:
                    title = f"{title} {nxt}"
                    nxt_title = 1
            if TOC.search(title) or not title_rx.search(title) or NOT_ARR_TITLE.search(title):
                continue
            if PART_BUSINESS.search(title) and not re.search(r"combined|consolidated|total", title, re.I):
                continue  # the wires or the supply business alone is a part of the ARR, not the ARR
            if re.search(r"categor|agricultur|\bLT\b|\bHT\b|consumer class", title):
                continue  # an ARR split across consumer categories
            if OTHER_ENTITY.search(title) and not any(
                re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", title, re.I)
                for code in licensees
                for n in [code, *aliases.get(code, [])]
                if len(n) > 3
            ):
                continue  # a generation or transmission company's table in a combined order
            # the sentence just above the title, read backwards to the nearest row naming a year
            above = ""
            for x in reversed(rows[max(0, ri - 5) : ri]):
                above = f"{x.text} {above}"
                if years_in(x.text):
                    break
            t = read_one(rows_by_page, pi, ri + 1 + nxt_title, title, licensees, aliases, above)
            if t and len(t.lines) >= 4:
                tables.append(t)
    return {
        "pages": len(doc),
        "pages_without_text": no_text,
        "tables": [t.__dict__ for t in tables],
    }


def body_rows(rows_by_page: list[list[Row]], pi: int, start: int) -> tuple[list[Row], list[Row]]:
    """(header rows, body rows) of the table whose title is just above rows_by_page[pi][start]."""
    header: list[Row] = []
    body: list[Row] = []
    cur_pi, cur_rows, k = pi, rows_by_page[pi], start
    while True:
        if k >= len(cur_rows):
            if not body or cur_pi + 1 >= len(rows_by_page):
                break
            nxt = rows_by_page[cur_pi + 1]
            j = 0
            stop = False
            while j < len(nxt) and j < 8 and not nxt[j].split()[1]:
                # a running header at the top of the page is not the end of the table
                if TITLE.match(nxt[j].words[0].text) or (is_paragraph(nxt[j]) and nxt[j].y > 0.12 * nxt[j].height):
                    stop = True
                    break
                j += 1
            if stop or j >= len(nxt) or TITLE.match(nxt[j].words[0].text):
                break
            cur_pi += 1
            cur_rows = nxt
            k = j
            continue
        r = cur_rows[k]
        k += 1
        if TITLE.match(r.words[0].text):
            break
        label, values = r.split()
        if not body:
            ltext = " ".join(w.text for w in label)
            if values and label and (not years_in(ltext) or any("." in v.text for v in values)):
                body.append(r)
            elif values and not label and header:
                # a values-only row under a label printed above it: that row is the label, not header
                h = header[-1]
                if (
                    not voice_of(h.text)
                    and not years_in(h.text)
                    and not re.search(r"particulars|s\.\s*no", h.text, re.I)
                ):
                    body.append(header.pop())
                body.append(r)
            else:
                header.append(r)
                if len(header) > 8:
                    return [], []
            continue
        words_only = sum(1 for w in r.words if not NUM.match(w.text) and not DASH.match(w.text))
        if is_paragraph(r) or (re.match(r"^\d+\.\d+\.?$", r.words[0].text) and words_only >= 5):
            break
        if re.match(r"^(note|source|\*|#)", r.text, re.I) and not values:
            break
        body.append(r)
    # a body that ended in label-only rows: drop them (they are the next paragraph's heading)
    while body and not body[-1].split()[1]:
        if (
            len(body) >= 2
            and body[-2].split()[1]
            and body[-1].page == body[-2].page
            and body[-1].y - body[-2].y < 14
            and len(body[-1].words) <= 4
        ):
            break  # the last line of a wrapped label, printed just below its values
        body.pop()
    return header, body


def column_meaning(c: Column, title: str, licensees: list[str], names: dict[str, list[str]]) -> dict[str, Any]:
    htext = " ".join(c.header)

    def named(text: str) -> str | None:
        for code, ns in names.items():
            if any(re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", text, re.I) for n in ns):
                return code
        return None

    lic = named(htext)
    if (
        lic is None
        and len(licensees) > 1
        and re.search(r"\btotal\b|\bstate\b|\ball\b|consolidated|combined", htext, re.I)
    ):
        lic = "TOTAL"
    if lic is None:
        lic = named(title)
    if lic is None and len(licensees) == 1:
        lic = licensees[0]
    hy = years_in(htext)
    ty = years_in(title)
    year = hy[0] if hy else (ty[0] if len(ty) == 1 else None)
    voice = voice_of(htext)
    classes = {
        k
        for k, rx in (("c", CLAIMED), ("a", re.compile(r"approv|admit|allow|determin|consider", re.I)), ("e", EARLIER))
        if rx.search(htext)
    }
    if len(classes) > 1:
        # header words of two voices over one column: the lowest phrase with a voice is its own
        for ph in reversed(c.header):
            if CLAIMED.search(ph) or STRICT_APPROVED.search(ph) or EARLIER.search(ph):
                voice = voice_of(ph)
                break
    if voice is None:
        bare = htext
        for ns in names.values():
            for n in ns:
                bare = re.sub(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", " ", bare, flags=re.I)
        bare = re.sub(
            r"fy\s*[\d\-–]+|20\d\d[-–]\d\d|\bdiscoms?\b|\(rs[^)]*\)|rs\.?|crore|\bcr\b", " ", bare, flags=re.I
        ).strip()
        if htext and not bare and named(htext) and len(licensees) == 1:
            voice = "claimed"  # a column headed with the licensee's own name is its submission
        else:
            voice = voice_of(re.sub(r"\bfor\s+(the\s+)?fy.*$", "", title, flags=re.I)) or voice_of(title)
    # an "Approved" column inside a table of the petitioner's submission quotes an earlier approval
    tv = voice_of(re.sub(r"\bfor\s+(the\s+)?fy.*$", "", title, flags=re.I))
    if (
        voice == "approved"
        and tv == "claimed"
        and re.search(r"submi|propos|claim|petitioner", title, re.I)
        and not re.search(r"approv|admit|allow", title, re.I)
    ):
        voice = "approved_earlier"
    part = bool(PART_COLUMN.search(htext))
    if part:
        voice = None  # a part of the figure (a business, a category, a unit column): not the licensee's ARR
    return {"header": htext, "licensee": lic, "fiscal_year": year, "voice": voice, "x": round(c.xc, 1), "part": part}


def read_one(
    rows_by_page: list[list[Row]],
    pi: int,
    start: int,
    title: str,
    licensees: list[str],
    aliases: dict[str, list[str]],
    above: str = "",
) -> Table | None:
    header, body = body_rows(rows_by_page, pi, start)
    if not body:
        return None
    pages = sorted({r.page for r in body})
    first = [r for r in body if r.page == pages[0]]
    cols = cluster([], [r.split()[1] for r in first])
    if not cols or len(cols) > 16:
        return None
    label_header(cols, header)
    page_cols: dict[int, list[Column] | None] = {pages[0]: cols}
    for p in pages[1:]:
        pc = cluster([], [r.split()[1] for r in body if r.page == p])
        aligned = sum(1 for c in pc if any(abs(c.xc - d.xc) < 15 for d in cols))
        if aligned >= max(1, 0.6 * len(pc)):
            page_cols[p] = cols  # the same columns, with a stray number or two beside them
        elif len(pc) == len(cols):
            page_cols[p] = pc  # the page is laid out afresh: the same columns in the same order
        else:
            page_cols[p] = None  # a continuation whose columns cannot be matched: not read
    rows = rows_by_page[pi]
    unit, factor = unit_of([title, *(r.text for r in header[:4])])
    if unit is None:
        near = [r.text for r in rows[max(0, start - 4) : start + 2] if len(r.words) <= 6]
        unit, factor = unit_of(near)
    names = {code: [code, *aliases.get(code, [])] for code in licensees}
    columns = [column_meaning(c, title, licensees, names) for c in cols]
    # what the header and title leave open, the sentence that introduces the table may say
    # ("the final ARR submitted by the Petitioner for FY 2024-25 is tabulated hereunder")
    ay = years_in(above)
    av = voice_of(above) if above else None
    for c in columns:
        c["year_from"] = "header" if years_in(c["header"]) else ("title" if c["fiscal_year"] else None)
        c["voice_from"] = "header" if voice_of(c["header"]) else ("title" if c["voice"] else None)
        if c["fiscal_year"] is None and len(ay) == 1:
            c["fiscal_year"], c["year_from"] = ay[0], "text above the table"
        if c["voice"] is None and av in ("claimed", "approved"):
            c["voice"], c["voice_from"] = av, "text above the table"
    lines: list[dict[str, Any]] = []
    pending: list[str] = []
    group: str | None = None
    last_from_pending = False
    last_row: Row | None = None
    last_lines: list[dict[str, Any]] = []
    for bi, r in enumerate(body):
        label, values = r.split()
        ltext = " ".join(w.text for w in label).strip(" :-")
        if not values:
            nxt = body[bi + 1] if bi + 1 < len(body) else None
            # the rest of a wrapped label, printed just below its values ("Charges")
            if (
                last_from_pending
                and last_row is not None
                and r.y - last_row.y < 14
                and r.page == last_row.page
                and (nxt is None or nxt.split()[0] or nxt.y - r.y > 14)
            ):
                for ln in last_lines:
                    ln["label"] = f"{ln['label']} {ltext}"
                    ln["head"] = head_of(ln["label"])
                    ln["quote"] = f"{ln['quote']} / {r.text}"
                last_from_pending = False
                continue
            pending.append(ltext)
            continue
        from_pending = False
        row_voice = None
        if not ltext and pending:
            ltext = " ".join(pending)
            pending = []
            from_pending = True
        elif (
            pending
            and ltext
            and (ltext[0].islower() or (ltext.endswith(")") and "(" not in ltext))
            and last_row is not None
            and r.y - last_row.y < 40
        ):
            # the second line of a wrapped label carries the values ("Interest on short-term" / "borrowings 46.93")
            ltext = f"{' '.join(pending)} {ltext}"
            pending = []
        elif pending:
            group = " ".join(pending)
            pending = []
        if group and re.fullmatch(r"(proposed|approved|claimed|admitted|petition|allowed|projected)", ltext, re.I):
            # a voice as the row label under a heading row: the heading is the head (OERC's Table 83)
            row_voice = voice_of(ltext)
            ltext = f"{group} ({ltext})"
        if not ltext:
            ltext = group or ""
        pc = page_cols.get(r.page)
        if pc is None:
            continue
        cells: dict[int, Word] = {}
        for v in values:
            i = place(pc, v)
            if i is None:
                continue
            cells.setdefault(i, v)
        emitted: list[dict[str, Any]] = []
        for i, v in sorted(cells.items()):
            val = number(v.text) if NUM.match(v.text) else None
            if val is None:
                continue
            emitted.append(
                {
                    "row_voice": row_voice,
                    "label": ltext,
                    "group": group,
                    "head": head_of(ltext),
                    "column": i,
                    "value_printed": v.text,
                    "value": val,
                    "page": r.page,
                    "quote": r.text,
                }
            )
        lines.extend(emitted)
        last_from_pending, last_lines = from_pending, emitted
        last_row = r
    # a table printed with years as rows and heads as columns (UERC's element-wise true-up)
    labelled = [ln for ln in lines if ln["label"]]
    yearly = [ln for ln in labelled if years_in(ln["label"]) and len(ln["label"]) <= 16]
    transposed = bool(labelled) and len(yearly) >= 0.6 * len(labelled)
    if transposed:
        out = []
        for ln in yearly:
            col = columns[ln["column"]]
            h = re.sub(r"^particulars\s*", "", col["header"], flags=re.I)
            out.append({**ln, "label": h, "head": head_of(h), "row_year": years_in(ln["label"])[0]})
        lines = out
    used = sorted({ln["column"] for ln in lines})
    return Table(
        title=title,
        page=pi + 1,
        unit=unit,
        factor=factor,
        columns=[{**c, "index": i} for i, c in enumerate(columns) if i in used],
        lines=lines,
        pages=pages,
    )
