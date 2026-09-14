"""Page triage (Section 6.3): classify every page and record what we do not know.

Three deterministic, versioned concerns, all pure functions over primitives extracted from a
page so they can be tested without a PDF:

1. **Text-layer quality** — glyph coverage, dictionary hit rate, reading-order sanity.  A page
   with a text layer is not necessarily a page with a *usable* text layer (failure mode D2).
2. **Page class** — `narrative`, `table`, `mixed`, `annexure_cover`, `blank`, `image_only`,
   `vector_graphics_text_sparse`, `unknown`.  Never guessed: a page that does not clearly match
   is `unknown`, and `unknown` is never green in the UI.
3. **Printed page labels** — the label a human reads in the footer, which is not the PDF index
   (failure mode D5).  Labels are read from the page, reconciled with any label the PDF itself
   declares, and generalised into an explicit per-document rule with segments, so that a
   citation to "printed page 209" resolves to the right PDF page in every document shape:
   NPCL (label == index), KERC and GERC (roman front matter, then index − 16).

Bump ``TRIAGE_VERSION`` whenever a rule changes: it is recorded on every page and every stage
artefact, and a change invalidates downstream artefacts explicitly (Section 6.2).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TRIAGE_VERSION = "2"

PageClass = Literal[
    "narrative",
    "table",
    "mixed",
    "annexure_cover",
    "blank",
    "image_only",
    "vector_graphics_text_sparse",
    "unknown",
]

# Thresholds are data, not magic numbers scattered through the code: a reading profile may
# override them per commission once profiles exist (Milestone 3).
DEFAULTS = {
    "blank_max_chars": 5,
    "sparse_text_max_chars": 120,
    "image_only_min_coverage": 0.35,
    "vector_min_drawings": 150,
    "table_min_ruling_lines": 8,
    "table_min_aligned_columns": 3,
    "grid_min_h_rulings": 3,
    "grid_min_v_rulings": 2,
    "mixed_min_prose_tokens": 80,
    "cover_max_lines": 12,
    # Text-quality components are judged independently; a weighted average lets one broken
    # signal hide behind two healthy ones (a page of consonant soup with perfect glyph coverage).
    "glyph_coverage_min": 0.95,
    "dictionary_min_tokens": 30,
    "dictionary_hit_min": 0.40,
    "reading_order_min": 0.70,
}

COVER_WORDS = ("annexure", "annexures", "appendix", "schedule", "chapter", "part", "contents")


# --------------------------------------------------------------------------- text quality

# A deliberately small, auditable vocabulary: function words plus the domain words that appear
# on almost every page of an Indian tariff order.  It is a *sanity* check on glyph mapping, not
# a language model — a page whose text layer is mis-mapped scores near zero on it.
_VOCAB = {
    # function words
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "shall",
    "have",
    "has",
    "been",
    "are",
    "not",
    "any",
    "all",
    "such",
    "per",
    "as",
    "of",
    "to",
    "in",
    "on",
    "by",
    "at",
    "or",
    "is",
    "be",
    "it",
    "which",
    "may",
    "under",
    "above",
    "below",
    "other",
    "than",
    "their",
    "there",
    # domain
    "tariff",
    "tariffs",
    "commission",
    "energy",
    "charge",
    "charges",
    "consumer",
    "consumers",
    "supply",
    "electricity",
    "order",
    "petition",
    "petitioner",
    "schedule",
    "annexure",
    "applicable",
    "applicability",
    "demand",
    "fixed",
    "load",
    "voltage",
    "units",
    "unit",
    "rate",
    "rates",
    "month",
    "monthly",
    "annual",
    "year",
    "financial",
    "revenue",
    "cost",
    "distribution",
    "transmission",
    "licensee",
    "regulation",
    "regulations",
    "approved",
    "proposed",
    "existing",
    "billing",
    "meter",
    "metered",
    "connection",
    "rupees",
    "paise",
    "kwh",
    "kva",
    "kw",
    "mu",
    "crore",
    "lakh",
    "state",
    "power",
    "open",
    "access",
    "wheeling",
    "surcharge",
    "loss",
    "losses",
    "banking",
    "green",
    "category",
    "categories",
    "slab",
    "minimum",
    "maximum",
    "rebate",
    "penalty",
    "factor",
    "season",
    "seasonal",
    "hours",
}

_TOKEN = re.compile(r"[A-Za-z]{2,}")
_BAD_CHAR = re.compile("[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class TextQuality:
    """Each component is reported separately: an aggregate alone would hide which signal failed."""

    glyph_coverage: float
    dictionary_hit_rate: float
    reading_order_sanity: float
    score: float
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def glyph_coverage(text: str) -> float:
    """Fraction of characters that carry meaning.  Replacement characters, control characters
    and private-use codepoints are what a broken ToUnicode map produces."""
    if not text:
        return 0.0
    bad = len(_BAD_CHAR.findall(text))
    private = sum(1 for ch in text if unicodedata.category(ch) == "Co")
    return max(0.0, 1.0 - (bad + private) / len(text))


def dictionary_hit_rate(text: str) -> tuple[float, int]:
    """Fraction of alphabetic tokens that are recognisable words.  Low on a page whose glyphs
    are mapped to the wrong codepoints, even though extraction "succeeded"."""
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    if not tokens:
        return 0.0, 0
    hits = sum(1 for t in tokens if t in _VOCAB or _is_wordlike(t))
    return hits / len(tokens), len(tokens)


def _is_wordlike(token: str) -> bool:
    """A token not in the vocabulary can still be a real word; scrambled glyphs usually are not.
    Requires a vowel and no improbable consonant run."""
    if not any(v in token for v in "aeiou"):
        return False
    return re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", token) is None


def reading_order_sanity(lines: list[tuple[float, float, str]]) -> float:
    """Fraction of consecutive extracted lines that do not jump backwards up the page.

    ``lines`` is [(y_top, x_left, text)] in extraction order.  Interleaved columns — the
    classic two-column extraction failure — produce repeated backward jumps.
    """
    ordered = [line for line in lines if line[2].strip()]
    if len(ordered) < 2:
        return 1.0
    forward = sum(1 for a, b in zip(ordered, ordered[1:], strict=False) if b[0] >= a[0] - 1.0)
    return forward / (len(ordered) - 1)


def assess_text(text: str, lines: list[tuple[float, float, str]]) -> TextQuality:
    gc = glyph_coverage(text)
    dhr, tokens = dictionary_hit_rate(text)
    ros = reading_order_sanity(lines)
    # Weighted towards glyph coverage: a page can legitimately be mostly numbers (a rate table),
    # so a low dictionary hit rate alone must not condemn it.
    score = round(0.5 * gc + 0.2 * dhr + 0.3 * ros, 4)
    return TextQuality(
        glyph_coverage=round(gc, 4),
        dictionary_hit_rate=round(dhr, 4),
        reading_order_sanity=round(ros, 4),
        score=score,
        token_count=tokens,
    )


# --------------------------------------------------------------------------- classification


@dataclass
class PageSignals:
    """Everything classification is allowed to look at, extracted once per page."""

    text_chars: int
    line_count: int
    image_count: int
    image_area_ratio: float
    drawing_count: int
    ruling_line_count: int
    aligned_column_count: int
    rotation: int
    text: str = ""
    quality: TextQuality | None = None
    # rules v2: short rulings in both orientations — a small ruled grid (3-4 rows) whose
    # vertical strokes are shorter than the long-ruling threshold above
    h_ruling_count: int = 0
    v_ruling_count: int = 0


@dataclass
class TriageResult:
    page_class: PageClass
    quality_flags: list[str] = field(default_factory=list)
    ocr_recommended: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_class": self.page_class,
            "quality_flags": self.quality_flags,
            "ocr_recommended": self.ocr_recommended,
            "rationale": self.rationale,
        }


def classify_page(sig: PageSignals, thresholds: dict[str, Any] | None = None) -> TriageResult:
    """Classify one page.  Every branch records why, so a reviewer can see the reasoning and a
    profile author can see which cue to adjust."""
    t = {**DEFAULTS, **(thresholds or {})}
    flags: list[str] = []
    if sig.rotation:
        flags.append("rotated")

    has_text = sig.text_chars > t["blank_max_chars"]
    sparse = sig.text_chars <= t["sparse_text_max_chars"]

    ocr_for_quality = False
    if sig.quality is not None and has_text:
        q = sig.quality
        if q.glyph_coverage < t["glyph_coverage_min"]:
            flags.append("glyph_mapping_damaged")
        # Only judge word-likeness when there are enough words to judge: a rate table is
        # legitimately mostly numbers, and must not be condemned for it.
        if q.token_count >= t["dictionary_min_tokens"] and q.dictionary_hit_rate < t["dictionary_hit_min"]:
            flags.append("text_not_wordlike")
        if q.reading_order_sanity < t["reading_order_min"]:
            flags.append("suspected_column_interleaving")
        if any(f in flags for f in ("glyph_mapping_damaged", "text_not_wordlike", "suspected_column_interleaving")):
            flags.append("low_text_quality")
            flags.append("ocr_needed")
            ocr_for_quality = True

    # No usable text layer at all: is it a scan, a vector drawing, or genuinely empty?
    if not has_text:
        flags.append("no_text_layer")
        if sig.image_area_ratio >= t["image_only_min_coverage"]:
            return TriageResult(
                "image_only",
                flags + ["ocr_needed"],
                ocr_recommended=True,
                rationale=f"no text layer; a raster image covers {sig.image_area_ratio:.0%} of the page",
            )
        if sig.drawing_count >= t["vector_min_drawings"]:
            # The KERC hazard: born-digital tables drawn as vectors.  Text extraction returns
            # nothing AND image extraction returns nothing, but the page looks fine to a human.
            return TriageResult(
                "vector_graphics_text_sparse",
                flags + ["ocr_needed", "overlapping_graphics"],
                ocr_recommended=True,
                rationale=f"no text layer but {sig.drawing_count} drawing operators: rasterise and OCR",
            )
        if sig.image_count == 0 and sig.drawing_count < 5:
            return TriageResult("blank", flags, rationale="no text, no images, no drawings")
        return TriageResult(
            "unknown",
            flags + ["ocr_needed"],
            ocr_recommended=True,
            rationale="no text layer and no decisive image or vector signal",
        )

    # Sparse text over a large drawing region is still a vector table with a stray caption.
    if sparse and sig.drawing_count >= t["vector_min_drawings"]:
        return TriageResult(
            "vector_graphics_text_sparse",
            flags + ["ocr_needed", "overlapping_graphics"],
            ocr_recommended=True,
            rationale=f"only {sig.text_chars} characters over {sig.drawing_count} drawing operators",
        )

    # v2: a small ruled grid — at least three horizontal and two vertical rulings that cross
    # — is a table even when its strokes are too short to count as long rulings (found on
    # the Milestone 3b fixture: a 3-row rate table classed `narrative`, never gridded)
    small_grid = sig.h_ruling_count >= t["grid_min_h_rulings"] and sig.v_ruling_count >= t["grid_min_v_rulings"]
    table_like = (
        sig.ruling_line_count >= t["table_min_ruling_lines"]
        or sig.aligned_column_count >= t["table_min_aligned_columns"]
        or small_grid
    )
    if table_like:
        # A rate table is thousands of characters of digits; prose is measured in words.
        prose_tokens = len(_TOKEN.findall(sig.text))
        if prose_tokens >= t["mixed_min_prose_tokens"]:
            return TriageResult(
                "mixed",
                flags,
                ocr_recommended=ocr_for_quality,
                rationale=f"table structure ({sig.ruling_line_count} rulings, "
                f"{sig.aligned_column_count} aligned columns) alongside {prose_tokens} words of prose",
            )
        return TriageResult(
            "table",
            flags,
            ocr_recommended=ocr_for_quality,
            rationale=f"{sig.ruling_line_count} ruling lines, {sig.h_ruling_count}x{sig.v_ruling_count} grid "
            f"strokes and {sig.aligned_column_count} aligned columns",
        )

    if sig.line_count <= t["cover_max_lines"] and _looks_like_cover(sig.text):
        return TriageResult(
            "annexure_cover",
            flags,
            ocr_recommended=ocr_for_quality,
            rationale=f"{sig.line_count} lines containing a section heading word",
        )

    if sparse:
        return TriageResult(
            "unknown",
            flags,
            ocr_recommended=ocr_for_quality,
            rationale=f"only {sig.text_chars} characters and no table or cover signal",
        )

    return TriageResult(
        "narrative",
        flags,
        ocr_recommended=ocr_for_quality,
        rationale=f"{sig.text_chars} characters of prose, no table structure",
    )


def _looks_like_cover(text: str) -> bool:
    head = text.strip().lower()[:400]
    return any(w in head for w in COVER_WORDS)


# --------------------------------------------------------------------------- page labels

_ROMAN = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)
_LABEL_PATTERNS = [
    # "Page 12 of 423" — the NPCL footer; distinctive enough to appear anywhere on its line
    re.compile(r"\bpage\s+(?P<n>[0-9]{1,4})\s+of\s+[0-9]{1,4}\b", re.I),
    # "Page 12" / "Page - 12" / "Page No. 12", possibly after a section label as in the KERC
    # footer ("Chapter – 6 : … Page 209").  Anchored to the END of the line: "see page 12 of
    # the petition" in running prose is not a page label.
    re.compile(r"\bpage\s*(?:no\.?|#|-|–|—)?\s*(?P<n>[0-9]{1,4})\s*$", re.I),
    re.compile(r"\bpage\s*(?:no\.?|#|-|–|—)?\s*(?P<r>[ivxlcdm]{1,7})\s*$", re.I),
    # A bare number or roman numeral alone on the line
    re.compile(r"^\s*(?P<n>[0-9]{1,4})\s*$"),
    re.compile(r"^\s*(?P<r>[ivxlcdm]{1,7})\s*$", re.I),
]

ROMAN_VALUES = [
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
]


def roman_to_int(s: str) -> int | None:
    s = s.strip().lower()
    if not s or not _ROMAN.match(s):
        return None
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total, prev = 0, 0
    for ch in reversed(s):
        v = values.get(ch)
        if v is None:
            return None
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total or None


def int_to_roman(n: int, upper: bool = False) -> str:
    out = []
    for value, sym in ROMAN_VALUES:
        while n >= value:
            out.append(sym)
            n -= value
    s = "".join(out)
    return s.upper() if upper else s


@dataclass
class ObservedLabel:
    page_index: int
    value: str
    number: int
    style: Literal["decimal", "roman_lower", "roman_upper"]
    source_line: str


def extract_label(page_text: str, *, zone_lines: int = 4) -> ObservedLabel | None:
    """Find the printed page label in the footer (or header) zone of a page.

    Only the first and last few lines are considered: a rate table is full of numbers, and any
    of them would otherwise look like a page number.
    """
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    if not lines:
        return None
    candidates = lines[-zone_lines:] + lines[:2]
    for line in candidates:
        for pattern in _LABEL_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            groups = m.groupdict()
            if groups.get("n"):
                return ObservedLabel(0, groups["n"], int(groups["n"]), "decimal", line)
            raw = groups.get("r")
            if raw:
                value = roman_to_int(raw)
                if value:
                    style = "roman_upper" if raw.isupper() else "roman_lower"
                    return ObservedLabel(0, raw, value, style, line)
    return None


@dataclass
class LabelSegment:
    """A run of pages whose printed label is `index + offset`, rendered in one style."""

    start_index: int
    end_index: int
    style: str
    offset: int
    observed_pages: int

    def label_for(self, page_index: int) -> str:
        n = page_index + self.offset
        if n < 1:
            return ""
        if self.style == "decimal":
            return str(n)
        return int_to_roman(n, upper=self.style == "roman_upper")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_label_rule(observations: list[ObservedLabel], page_count: int) -> list[LabelSegment]:
    """Generalise observed labels into contiguous segments of (style, constant offset).

    A single wrong reading must not shatter the rule, so a segment is kept only if at least two
    pages agree on the same (style, offset); isolated disagreements are left unexplained rather
    than smoothed over, and their pages resolve to no label.
    """
    if not observations:
        return []
    points = sorted(((o.page_index, o.style, o.number - o.page_index) for o in observations), key=lambda p: p[0])

    runs: list[list[tuple[int, str, int]]] = []
    for point in points:
        if runs and runs[-1][-1][1] == point[1] and runs[-1][-1][2] == point[2]:
            runs[-1].append(point)
        else:
            runs.append([point])

    segments: list[LabelSegment] = []
    for run in runs:
        if len(run) < 2:
            continue  # one page agreeing with nothing is not a rule
        seg = LabelSegment(
            start_index=run[0][0],
            end_index=run[-1][0],
            style=run[0][1],
            offset=run[0][2],
            observed_pages=len(run),
        )
        # A single stray footer must not split a continuous rule in two.
        if segments and segments[-1].style == seg.style and segments[-1].offset == seg.offset:
            segments[-1].end_index = seg.end_index
            segments[-1].observed_pages += seg.observed_pages
        else:
            segments.append(seg)
    if not segments:
        return []

    # Extend each segment to the pages between it and its neighbour, so unlabelled pages inside
    # a run (a full-page table with no footer) still resolve.
    for i, seg in enumerate(segments):
        if i == 0:
            seg.start_index = 1
        if i == len(segments) - 1:
            seg.end_index = page_count
        else:
            seg.end_index = segments[i + 1].start_index - 1
    return segments


def resolve_label(
    page_index: int,
    declared: str | None,
    observed: ObservedLabel | None,
    segments: list[LabelSegment],
) -> tuple[str | None, str, list[str]]:
    """Decide the printed label for a page.  Returns (label, source, flags).

    Precedence: what the page itself shows, then the document-wide rule, then what the PDF
    declares.  A disagreement between the page and the PDF is recorded as a conflict rather
    than silently resolved — it is exactly the kind of thing that sends a citation to the
    wrong page.
    """
    flags: list[str] = []
    from_rule = next((s.label_for(page_index) for s in segments if s.start_index <= page_index <= s.end_index), "")

    if observed is not None:
        if declared and declared.strip().lower() != observed.value.strip().lower():
            flags.append("label_conflict")
        if from_rule and from_rule.lower() != observed.value.lower():
            flags.append("label_off_rule")
        return observed.value, "observed", flags
    if from_rule:
        if declared and declared.strip().lower() != from_rule.lower():
            flags.append("label_conflict")
        return from_rule, "rule", flags
    if declared:
        return declared, "declared", flags
    return None, "none", flags
