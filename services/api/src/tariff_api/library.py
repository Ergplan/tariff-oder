"""The regulatory library (ADR-0019): every expected or known tariff order, true-up, MYT order,
ARR/MYT petition and regulation per state, commission, licensee and year, the official URL
it is acquired from, and how far each has been read.

Levels, computed and never stored: ``missing`` (an expected slot, no URL), ``located`` (an
official URL, not yet fetched), ``failed`` (the last fetch failed, with the error),
``acquired`` (registered as a source), ``read`` (the tariff or ARR track got past
extraction), ``reviewed`` (a person has decided at least one of its readings),
``published`` (facts from it are published).  Expected slots are expectations seeded from
the registry; they hold no number."""

from __future__ import annotations

import html as html_lib
import re
import uuid
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .adapters.storage import ObjectStore
from .config import Settings
from .errors import AppError
from .models import (
    LIBRARY_KINDS,
    AuditEvent,
    CandidateRecord,
    Commission,
    DatasetKind,
    Job,
    Jurisdiction,
    LibraryEntry,
    SourceDocument,
    SourceState,
    Utility,
)
from .queue import enqueue
from .telemetry import request_id_var

LEVELS = ("missing", "located", "failed", "acquired", "read", "reviewed", "published")
_READ_STATES = {
    SourceState.extracted,
    SourceState.validated,
    SourceState.awaiting_review,
    SourceState.published,
}
# which voice of ``decides`` names the year an order belongs to in the library
_YEAR_VOICE = {
    "tariff_order": ("approved",),
    "arr_true_up_order": ("final_true_up", "provisional_true_up"),
    "arr_petition": ("petitioned",),
    "mid_term_review": ("control_period", "approved"),
}
MAX_FETCH_BYTES = 64 * 1024 * 1024


def _audit(session: Session, actor: str, action: str, entry: LibraryEntry, **kw: Any) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type="library_entry",
            entity_id=str(entry.id),
            request_id=request_id_var.get(),
            **kw,
        )
    )


def _slot(
    session: Session, commission_id: uuid.UUID, utility_id: uuid.UUID | None, kind: str, fy: str
) -> LibraryEntry | None:
    q = select(LibraryEntry).where(
        LibraryEntry.commission_id == commission_id,
        LibraryEntry.document_kind == kind,
        LibraryEntry.fiscal_year == fy,
        LibraryEntry.utility_id.is_(None) if utility_id is None else LibraryEntry.utility_id == utility_id,
    )
    return session.execute(q).scalar_one_or_none()


def seed(
    session: Session,
    *,
    fiscal_years: list[str],
    kinds: list[str],
    control_period_kinds: list[str],
    commission_kinds: list[str],
    commission_codes: list[str] | None,
    actor: str,
) -> dict[str, int]:
    """Expected slots for every real distribution and transmission licensee: one per kind
    and year, one per control-period kind ("" = the current control period), and one per
    commission-wide kind.  Existing slots are left alone.  Then registered sources are
    linked to their slots."""
    for k in [*kinds, *control_period_kinds, *commission_kinds]:
        if k not in LIBRARY_KINDS:
            raise AppError("validation_failed", f"unknown document kind {k!r}")
    created = existing = 0
    q = select(Commission).order_by(Commission.code)
    if commission_codes:
        q = q.where(Commission.code.in_(commission_codes))
    for c in session.execute(q).scalars():
        utilities = [
            u
            for u in c.utilities
            if u.licensee_kind in ("distribution", "transmission") and u.dataset.kind == DatasetKind.real
        ]
        if not utilities:
            continue
        wanted: list[tuple[uuid.UUID | None, str, str]] = [(None, k, "") for k in commission_kinds]
        for u in utilities:
            wanted += [(u.id, k, fy) for k in kinds for fy in fiscal_years]
            wanted += [(u.id, k, "") for k in control_period_kinds]
        for utility_id, kind, fy in wanted:
            if _slot(session, c.id, utility_id, kind, fy) is not None:
                existing += 1
                continue
            session.add(
                LibraryEntry(
                    commission_id=c.id,
                    utility_id=utility_id,
                    document_kind=kind,
                    fiscal_year=fy,
                    status="expected",
                    origin="seeded",
                    updated_by=actor,
                )
            )
            created += 1
        session.flush()
    linked = reconcile(session, actor=actor)
    session.add(
        AuditEvent(
            actor=actor,
            action="library.seeded",
            entity_type="library",
            entity_id="-",
            after={"created": created, "existing": existing, "linked": linked, "fiscal_years": fiscal_years},
            request_id=request_id_var.get(),
        )
    )
    return {"created": created, "existing": existing, "linked": linked}


def year_of(src: SourceDocument) -> str:
    """The library year of a registered source, from the years and voices it decides."""
    voices = _YEAR_VOICE.get(src.order_type or "")
    if not voices:
        return ""
    for v in voices:
        for d in src.decides or []:
            if d.get("value_type") == v and d.get("fiscal_year"):
                return str(d["fiscal_year"])
    return ""


def reconcile(session: Session, *, actor: str) -> int:
    """Link every registered real source with a licensee and an order type to its library
    slot (creating the slot when none was expected).  Returns the number linked now."""
    linked = 0
    for src in session.execute(
        select(SourceDocument).where(SourceDocument.utility_id.is_not(None), SourceDocument.order_type.is_not(None))
    ).scalars():
        if src.order_type not in LIBRARY_KINDS or src.dataset.kind != DatasetKind.real:
            continue
        u = src.utility
        assert u is not None
        fy = year_of(src)
        commission_wide = src.order_type in ("regulation", "regulation_amendment")
        entry = _slot(session, u.commission_id, None if commission_wide else u.id, src.order_type, fy)
        if entry is not None and entry.source_id == src.id:
            continue
        if entry is None:
            entry = LibraryEntry(
                commission_id=u.commission_id,
                utility_id=None if commission_wide else u.id,
                document_kind=src.order_type,
                fiscal_year=fy,
                origin="linked",
                url=src.provenance_url,
            )
            session.add(entry)
        elif entry.source_id is not None:
            continue  # the slot already holds another source; a person decides
        entry.source_id, entry.status, entry.updated_by = src.id, "acquired", actor
        entry.title = entry.title or src.original_filename
        session.flush()
        linked += 1
    return linked


def upsert_entry(
    session: Session,
    *,
    commission_code: str,
    utility_code: str | None,
    document_kind: str,
    fiscal_year: str,
    title: str | None,
    url: str | None,
    note: str | None,
    actor: str,
) -> LibraryEntry:
    c = session.execute(select(Commission).where(Commission.code == commission_code)).scalar_one_or_none()
    if c is None:
        raise AppError("validation_failed", f"unknown commission {commission_code}")
    u = None
    if utility_code:
        u = session.execute(select(Utility).where(Utility.code == utility_code)).scalar_one_or_none()
        if u is None or u.commission_id != c.id:
            raise AppError("validation_failed", f"{utility_code} is not a licensee of {commission_code}")
    if url is not None and not (url.startswith("https://") or url.startswith("http://")):
        raise AppError("validation_failed", "the URL must be http(s)")
    entry = _slot(session, c.id, u.id if u else None, document_kind, fiscal_year)
    before = None
    if entry is None:
        entry = LibraryEntry(
            commission_id=c.id,
            utility_id=u.id if u else None,
            document_kind=document_kind,
            fiscal_year=fiscal_year,
            origin="operator",
        )
        session.add(entry)
    else:
        before = {"url": entry.url, "status": entry.status, "title": entry.title}
    if title is not None:
        entry.title = title
    if note is not None:
        entry.note = note
    if url is not None:
        entry.url = url
        if entry.status in ("expected", "failed"):
            entry.status = "located"
    entry.updated_by = actor
    session.flush()
    _audit(session, actor, "library.entry_set", entry, before=before, after={"url": entry.url, "status": entry.status})
    return entry


def request_acquisition(session: Session, settings: Settings, entry: LibraryEntry, *, actor: str) -> Job:
    if not entry.url:
        raise AppError("validation_failed", "the entry has no URL to acquire from")
    if entry.status == "acquired":
        raise AppError("invalid_transition", "the document is already acquired")
    job, _ = enqueue(
        session,
        job_type="acquire_library_entry",
        payload={"entry_id": str(entry.id)},
        idempotency_key=f"acquire:{entry.id}:{entry.attempts + 1}",
        max_attempts=1,  # a refused download is recorded on the entry and retried by a person
        created_by=actor,
    )
    _audit(session, actor, "library.acquire_requested", entry, after={"job_id": str(job.id), "url": entry.url})
    return job


def fetch(url: str, *, timeout: float = 60.0) -> tuple[bytes, str]:
    """GET a document; (bytes, final URL).  PDF only, size-capped; the proxy and CA of the host
    are honoured (``trust_env``)."""
    with httpx.Client(follow_redirects=True, timeout=timeout, trust_env=True) as c:
        with c.stream("GET", url, headers={"User-Agent": "tariff-order-studio/1 (library acquisition)"}) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} from {r.url}")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_FETCH_BYTES:
                    raise RuntimeError(f"larger than {MAX_FETCH_BYTES} bytes")
            data = bytes(buf)
            if not data.startswith(b"%PDF"):
                raise RuntimeError(f"not a PDF ({r.headers.get('content-type', 'no content type')})")
            return data, str(r.url)


def acquire(
    session: Session, storage: ObjectStore, settings: Settings, entry: LibraryEntry, data: bytes, url: str
) -> SourceDocument:
    """Register fetched bytes exactly as an upload would be, and link the source."""
    from .services.sources import register_upload

    u = session.get(Utility, entry.utility_id) if entry.utility_id else None
    name = (entry.title or f"{entry.document_kind}_{entry.fiscal_year or 'current'}").replace("/", "-")[:180]
    src, _dedup, _job = register_upload(
        session,
        storage,
        settings,
        data=data,
        filename=name if name.lower().endswith(".pdf") else f"{name}.pdf",
        dataset_kind=DatasetKind.real,
        provenance_url=url,
        actor="library-acquisition",
        utility_code=u.code if u else None,
        order_type=entry.document_kind,
        decides=None,  # the years and voices an order decides are set by a person
    )
    entry.source_id, entry.status, entry.last_error = src.id, "acquired", None
    return src


def reading_level(session: Session, entry: LibraryEntry) -> str:
    if entry.source_id is None:
        return {"expected": "missing", "located": "located", "failed": "failed"}.get(entry.status, "missing")
    src = session.get(SourceDocument, entry.source_id)
    if src is None:
        return "missing"
    if src.state == SourceState.published or src.arr_state == "published":
        return "published"
    decided = session.execute(
        select(func.count()).where(CandidateRecord.source_id == src.id, CandidateRecord.review_status != "pending")
    ).scalar_one()
    if decided:
        return "reviewed"
    if src.state in _READ_STATES or src.arr_state in ("extracted", "awaiting_review"):
        return "read"
    return "acquired"


def coverage(session: Session, *, fiscal_years: list[str], kinds: list[str]) -> dict[str, Any]:
    entries = session.execute(select(LibraryEntry)).scalars().all()
    levels = {e.id: reading_level(session, e) for e in entries}
    by_utility: dict[uuid.UUID | None, list[LibraryEntry]] = {}
    for e in entries:
        by_utility.setdefault(e.utility_id, []).append(e)
    totals = {lv: 0 for lv in LEVELS}
    for lv in levels.values():
        totals[lv] += 1
    states = []
    for j in session.execute(select(Jurisdiction).order_by(Jurisdiction.name)).scalars():
        comms = []
        for c in sorted(j.commissions, key=lambda x: x.code):
            own = [e for e in entries if e.commission_id == c.id]
            if not own:
                continue
            util_rows = []
            for u in sorted(c.utilities, key=lambda x: x.code):
                ue = by_utility.get(u.id, [])
                if not ue:
                    continue
                cells = {
                    f"{e.document_kind}|{e.fiscal_year}": {"level": levels[e.id], "entry_id": str(e.id)} for e in ue
                }
                util_rows.append({"code": u.code, "name": u.name, "licensee_kind": u.licensee_kind, "cells": cells})
            wide = {
                f"{e.document_kind}|{e.fiscal_year}": {"level": levels[e.id], "entry_id": str(e.id)}
                for e in own
                if e.utility_id is None
            }
            comms.append({"code": c.code, "name": c.name, "commission_wide": wide, "licensees": util_rows})
        if comms:
            states.append({"code": j.code, "name": j.name, "commissions": comms})
    return {"fiscal_years": fiscal_years, "kinds": kinds, "totals": totals, "states": states}


# ------------------------------------------------------------------ discovery


_KIND_RULES: tuple[tuple[str, str], ...] = (
    (r"\bmid[- ]?term\b|\bmtr\b", "mid_term_review"),
    (r"amend\w*.*regulation|regulation\w*.*amend", "regulation_amendment"),
    (r"\bregulations?\b", "regulation"),
    (
        r"(\bmyt\b|multi[- ]?year|control period).*petition|petition.*(\bmyt\b|multi[- ]?year|control period)",
        "myt_petition",
    ),
    (r"\bmyt\b|multi[- ]?year|control period", "myt_order"),
    (r"true[- ]?up", "arr_true_up_order"),
    (r"petition", "arr_petition"),
    (r"tariff order|tariff for|\barr\b|aggregate revenue|retail tariff", "tariff_order"),
)
_HREF = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_FY_ANY = re.compile(r"(?:FY\s*)?(20\d{2})\s*[-–/]\s*(\d{2}|20\d{2})\b", re.I)


def _text(fragment: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", _TAGS.sub(" ", fragment))).strip()


def propose_from_html(page_html: str, base_url: str, *, licensees: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Proposed library entries from a listing page: every link to a PDF with its link text,
    a guessed kind, year and licensee, and why.  Guesses only: a person confirms each one
    before it is recorded.  ``licensees`` maps a licensee code to its names and aliases."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, inner in _HREF.findall(page_html):
        url = urljoin(base_url, html_lib.unescape(href.strip()))
        if not re.search(r"\.pdf(\?|#|$)", url, re.I) or url in seen:
            continue
        seen.add(url)
        text = _text(inner) or url.rsplit("/", 1)[-1]
        hay = f"{text} {url.rsplit('/', 1)[-1]}".lower()
        kind = next((k for rx, k in _KIND_RULES if re.search(rx, hay, re.I)), None)
        years = sorted(
            {
                f"FY{m.group(1)}-{m.group(2)[-2:]}"
                for m in _FY_ANY.finditer(hay)
                if int(m.group(2)[-2:]) == (int(m.group(1)) + 1) % 100
            }
        )
        hits = sorted(
            code
            for code, names in licensees.items()
            if any(re.search(rf"(?<![a-z0-9]){re.escape(n.lower())}(?![a-z0-9])", hay) for n in [code, *names] if n)
        )
        notes = []
        if kind is None:
            notes.append("kind not recognised")
        if len(years) > 1:
            notes.append(f"several years named ({', '.join(years)}): the latest is proposed")
        if not years and kind not in ("regulation", "regulation_amendment", "myt_order", "myt_petition"):
            notes.append("no financial year in the link text")
        if len(hits) > 1:
            notes.append(f"several licensees named ({', '.join(hits)})")
        if not hits and kind not in ("regulation", "regulation_amendment"):
            notes.append("no licensee named")
        out.append(
            {
                "url": url,
                "title": text[:300],
                "document_kind": kind,
                "fiscal_year": years[-1] if years and kind not in ("myt_order", "myt_petition") else "",
                "utility_code": hits[0] if len(hits) == 1 else None,
                "notes": notes,
                "complete": kind is not None and not [n for n in notes if "several" in n or "no " in n],
            }
        )
    return out


def discover(session: Session, *, commission_code: str, page_url: str, page_html: str | None) -> list[dict[str, Any]]:
    """Fetch (or take the pasted HTML of) a commission's listing page and propose entries."""
    c = session.execute(select(Commission).where(Commission.code == commission_code)).scalar_one_or_none()
    if c is None:
        raise AppError("validation_failed", f"unknown commission {commission_code}")
    if not (page_url.startswith("https://") or page_url.startswith("http://")):
        raise AppError("validation_failed", "the page URL must be http(s)")
    if page_html is None:
        try:
            with httpx.Client(follow_redirects=True, timeout=60, trust_env=True) as cl:
                r = cl.get(page_url, headers={"User-Agent": "tariff-order-studio/1 (library discovery)"})
        except httpx.HTTPError as e:
            raise AppError("provider_unavailable", f"could not fetch {page_url}: {type(e).__name__}") from e
        if r.status_code != 200:
            raise AppError("provider_unavailable", f"{page_url} answered {r.status_code}")
        page_html, page_url = r.text, str(r.url)
    names = {
        u.code: [u.name, *(u.aliases or [])]
        for u in c.utilities
        if u.licensee_kind in ("distribution", "transmission") and u.dataset.kind == DatasetKind.real
    }
    props = propose_from_html(page_html[:5_000_000], page_url, licensees=names)
    for p in props:
        p["commission_code"] = c.code
    return props
