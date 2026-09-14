"""Binding-schedule localisation rules (Section 6.5): *where in this document is the
Commission-approved retail tariff schedule?* — answered with a textual cue per region, never
by picking the last, largest or most numeric table.

Pure functions over per-page inputs (text, class, headings, grid count) and a reading
profile.  The worker stage builds the inputs, stores the result and opens the reviewer
checkpoint; nothing here touches the database.  Bump ``LOCALISATION_VERSION`` when a rule
changes so re-runs are visible.

Ambiguity is a halt, not a guess: several ``approved_schedule`` candidates, or none, leave
the record ``ambiguous`` with the finding that says why, and a reviewer resolves it by
correcting the regions.  Even an unambiguous result is only ``proposed`` until a reviewer
confirms it (mandatory checkpoint for every new order)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .profiles import LocatorCue, ReadingProfile

LOCALISATION_VERSION = "1"

# Contents pages quote every locator (``12.1 ANNEXURE-I: RATE SCHEDULE ....... 352``) and must
# never open a region.  Dot leaders ending in a page number are the signature.
_TOC_LINE = re.compile(r"(\.\s?){4,}\s*\d{1,4}\s*$|\s{3,}\d{1,4}\s*$")
_FY = re.compile(r"\bFY\s?(20\d\d)\s*[-–—/]\s*(\d{2,4})\b", re.I)
_MAX_LINE = 200


@dataclass
class PageInfo:
    page_index: int
    printed_label: str | None
    page_class: str
    text: str
    text_source: str  # text_layer | ocr | none
    headings: list[tuple[str, str | None]] = field(default_factory=list)  # (kind, canonical code)
    grid_count: int = 0


@dataclass
class Region:
    role: str
    page_start: int
    page_end: int
    cue_text: str
    cue_page: int
    cue_kind: str  # locator | page_class | profile_default
    sub_role: str | None = None
    utility: str | None = None
    period: str | None = None
    note: str | None = None
    origin: str = "detected"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    code: str
    severity: str  # blocking | warning | info
    message: str
    pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocalisationResult:
    status: str  # proposed | ambiguous
    regions: list[Region]
    findings: list[Finding]
    rules_version: str = LOCALISATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rules_version": self.rules_version,
            "regions": [r.to_dict() for r in self.regions],
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class _Hit:
    cue: LocatorCue
    page: int
    line: str


def is_contents_page(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    toc = sum(1 for ln in lines if _TOC_LINE.search(ln))
    return toc >= 3 and toc >= len(lines) // 4


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and len(ln.strip()) <= _MAX_LINE]


def find_hits(profile: ReadingProfile, page: PageInfo) -> list[_Hit]:
    if is_contents_page(page.text):
        return []
    hits: list[_Hit] = []
    lines = _lines(page.text)
    for cue in profile.locators:
        rx = re.compile(cue.pattern, re.I)
        line = next((ln for ln in lines if rx.search(ln) and not _TOC_LINE.search(ln)), None)
        if line is None:
            continue
        if cue.also_on_page and not all(re.search(p, page.text, re.I) for p in cue.also_on_page):
            continue
        hits.append(_Hit(cue, page.page_index, line))
    return hits


def _utility_on_page(profile: ReadingProfile, text: str) -> str | None:
    found = [u for u in profile.utilities if re.search(rf"\b{re.escape(u)}\b", text)]
    return found[0] if len(found) == 1 else None


def _periods_on_page(text: str) -> str | None:
    fys = sorted({f"FY{a}-{b[-2:]}" for a, b in _FY.findall(text)})
    return ", ".join(fys) if fys else None


def _approved_span(
    profile: ReadingProfile, pages: list[PageInfo], span_hits: list[_Hit], stop_pages: set[int]
) -> tuple[list[Region], list[Finding]]:
    """Group span hits into candidates.  A candidate starts at a hit page and runs to the last
    page carrying a schedule heading (or a further span hit) before the first stop page; hits
    inside a running candidate extend it rather than open a second one."""
    by_index = {p.page_index: p for p in pages}
    last = max(by_index) if by_index else 0
    schedule_pages = {p.page_index for p in pages if any(k == profile.schedule_heading_kind for k, _ in p.headings)}
    candidates: list[Region] = []
    findings: list[Finding] = []
    for hit in sorted(span_hits, key=lambda h: h.page):
        if candidates and candidates[-1].page_start <= hit.page <= candidates[-1].page_end + 1:
            candidates[-1].page_end = max(candidates[-1].page_end, hit.page)
            continue
        # walk forward: schedule headings and span hits extend; a stop page or image_only run ends
        end = hit.page
        p = hit.page
        span_pages = {h.page for h in span_hits}
        while p < last:
            nxt = p + 1
            if nxt in stop_pages:
                break
            info = by_index.get(nxt)
            if info is None or info.page_class == "image_only":
                break
            if nxt in schedule_pages or nxt in span_pages:
                end = nxt
            elif info.headings and end != nxt and not (nxt - 1 == hit.page):
                # a non-schedule heading (a chapter, a different annexure) after the last
                # schedule page closes the span
                break
            p = nxt
        # trailing pages with no heading at all (table continuations, closing conditions)
        # belong to the schedule up to the next heading, stop page or image-only page
        tail = end
        while tail < last:
            nxt = tail + 1
            info = by_index.get(nxt)
            if nxt in stop_pages or info is None or info.headings or info.page_class == "image_only":
                break
            tail = nxt
        end = tail
        candidates.append(
            Region(
                role="approved_schedule",
                page_start=hit.page,
                page_end=end,
                cue_text=hit.line,
                cue_page=hit.page,
                cue_kind="locator",
                note=hit.cue.note,
            )
        )
    if not candidates:
        findings.append(
            Finding(
                "approved_schedule_not_found",
                "blocking",
                "no page matched the profile's approved-schedule locators; a reviewer must mark the region",
            )
        )
    elif len(candidates) > 1:
        findings.append(
            Finding(
                "multiple_approved_schedule_candidates",
                "blocking",
                f"{len(candidates)} separate regions matched the approved-schedule locators; "
                "extraction halts until a reviewer picks one (never the last, largest or most numeric)",
                pages=[c.page_start for c in candidates],
            )
        )
    for c in candidates:
        if not any(c.page_start <= sp <= c.page_end for sp in schedule_pages):
            findings.append(
                Finding(
                    "approved_region_without_schedule_headings",
                    "warning",
                    f"pages {c.page_start}-{c.page_end} matched a locator but carry no "
                    f"`{profile.schedule_heading_kind}` heading",
                    pages=[c.page_start],
                )
            )
    return candidates, findings


def localise(profile: ReadingProfile, pages: list[PageInfo]) -> LocalisationResult:
    pages = sorted(pages, key=lambda p: p.page_index)
    hits = [h for p in pages for h in find_hits(profile, p)]
    span_hits = [h for h in hits if h.cue.role == "approved_schedule" and h.cue.scope == "span"]
    page_hits = [h for h in hits if not (h.cue.role == "approved_schedule" and h.cue.scope == "span")]
    # pages classified by a page-scope cue of another role end the approved span
    stop_roles = {"derived_not_tariff", "illustrative", "amendment_diff", "approved_summary"}
    stop_pages = {h.page for h in page_hits if h.cue.role in stop_roles}
    approved, findings = _approved_span(profile, pages, span_hits, stop_pages)
    approved_pages = {i for r in approved for i in range(r.page_start, r.page_end + 1)}

    regions: list[Region] = list(approved)
    # page-scope regions outside the approved span; same role/sub-role on adjacent pages merge
    # roles that describe *other* material never overlap the approved span; a hit there is a
    # warning.  Conditions and determinations printed inside the annexure (UPERC's green
    # tariff is general provision 20) are sub-regions and may overlap it.
    exclusive = {"existing_tariff", "proposed_tariff", "illustrative", "derived_not_tariff", "amendment_diff"}
    for hit in sorted(page_hits, key=lambda h: (h.cue.role, h.cue.sub_role or "", h.page)):
        if hit.page in approved_pages and hit.cue.role in exclusive:
            if hit.cue.role in ("proposed_tariff", "existing_tariff"):
                findings.append(
                    Finding(
                        "existing_or_proposed_cue_inside_approved_region",
                        "warning",
                        f"page {hit.page} inside the approved region mentions "
                        f"{hit.cue.role.replace('_', ' ')}: {hit.line[:80]!r}",
                        pages=[hit.page],
                    )
                )
            continue
        info = next(p for p in pages if p.page_index == hit.page)
        utility = _utility_on_page(profile, info.text)
        period = _periods_on_page(info.text)
        prev = regions[-1] if regions else None
        if (
            prev
            and prev.role == hit.cue.role
            and prev.sub_role == hit.cue.sub_role
            and prev.page_end + 1 == hit.page
            and prev.utility == utility
        ):
            prev.page_end = hit.page
            continue
        regions.append(
            Region(
                role=hit.cue.role,
                sub_role=hit.cue.sub_role,
                page_start=hit.page,
                page_end=hit.page,
                cue_text=hit.line,
                cue_page=hit.page,
                cue_kind="locator",
                utility=utility,
                period=period,
                note=hit.cue.note,
            )
        )
    # image-only runs are `other` (scanned annexures, stamps): visible, never in the schedule
    run_start = None
    for p in pages + [None]:
        if p is not None and p.page_class == "image_only" and p.page_index not in approved_pages:
            run_start = run_start if run_start is not None else p.page_index
            continue
        if run_start is not None:
            end = (p.page_index - 1) if p is not None else pages[-1].page_index
            regions.append(
                Region(
                    role="other",
                    page_start=run_start,
                    page_end=end,
                    cue_text="page class image_only",
                    cue_page=run_start,
                    cue_kind="page_class",
                    note="scanned material: OCR'd for search, never part of the schedule",
                )
            )
            run_start = None

    # expectations from the profile are findings, not truth
    exp = profile.inventory_expectations
    codes_seen = sorted(
        {c for p in pages for k, c in p.headings if k == profile.schedule_heading_kind and c},
    )
    if exp.schedule_headings is not None and len(codes_seen) != exp.schedule_headings:
        findings.append(
            Finding(
                "inventory_expectation_mismatch",
                "warning",
                f"profile expects {exp.schedule_headings} distinct `{profile.schedule_heading_kind}` codes, "
                f"inventory has {len(codes_seen)}",
            )
        )
    unexpected = [c for c in codes_seen if c in exp.absent_codes]
    if unexpected:
        findings.append(
            Finding(
                "unexpected_code_found",
                "blocking",
                f"codes the profile declares absent were found: {', '.join(unexpected)}; "
                "a reader may have hallucinated",
            )
        )
    if profile.secondary_authoritative and not any(r.role == "approved_summary" for r in regions):
        findings.append(
            Finding(
                "secondary_representation_not_found",
                "warning",
                "the profile declares a secondary authoritative table (approved_summary) and none was located",
            )
        )
    if not any(r.role == "proposed_tariff" for r in regions):
        findings.append(
            Finding("proposed_tariff_absent", "info", "no proposed-tariff region; absence recorded, not inferred"),
        )

    status = "ambiguous" if any(f.severity == "blocking" for f in findings) else "proposed"
    regions.sort(key=lambda r: (r.page_start, r.role))
    return LocalisationResult(status=status, regions=regions, findings=findings)
