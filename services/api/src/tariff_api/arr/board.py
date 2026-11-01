"""The ARR readings board (increment 49): every order whose ARR is being read, by state and
commission — how far its reading has come, what its chapter preview found, how many of its
values a reviewer has decided — and the next human step that unblocks it.  Read-only: the
board decides nothing; every step it names is a person's (CLAUDE.md rule 1)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CandidateRecord, Commission, SourceDocument
from ..services.review import arr_mapping_confirmed
from ..services.sources import licensees_of
from .taxonomy import load_mapping

_DECIDED = ("approved", "corrected", "rejected", "unresolved")


def _preview_totals(summary: dict | None) -> dict[str, Any] | None:
    pv = (summary or {}).get("preview")
    if not pv:
        return None
    chs = pv.get("chapters") or []
    hints = [f for c in chs for f in (c.get("findings") or []) if f.get("reconciles_if")]
    return {
        "chapters": len(chs),
        "tables": sum(int(c.get("tables") or 0) for c in chs),
        "tables_read": sum(int(c.get("tables_read") or 0) for c in chs),
        "values": sum(int(c.get("values") or 0) for c in chs),
        "identity_blocking": sum(int(c.get("identity_blocking") or 0) for c in chs),
        "explained_by_a_convention": len(hints),
        "rules": pv.get("rules"),
    }


def next_step(arr_state: str | None, counts: Counter, mapping_confirmed: bool, is_fixture: bool) -> str:
    """The next human step for one order, in words."""
    if arr_state is None:
        return "An administrator starts the ARR reading."
    if arr_state in ("chapters_pending", "reading"):
        return "Wait: the reading job is running."
    if arr_state == "chapters_proposed":
        return (
            "A reviewer confirms the chapters: exclude the parts flagged as petition or hearing, set the "
            "last chapter's end, confirm."
        )
    pending = counts.get("pending", 0) + counts.get("awaiting_second_review", 0)
    if arr_state in ("awaiting_review", "extracted"):
        if not mapping_confirmed and not is_fixture:
            return (
                f"{pending} value(s) await review, but the commission's mapping is not confirmed: a reviewer "
                "confirms the mapping first (real values cannot be approved until then)."
            )
        return f"A reviewer decides the {pending} pending value(s), then publishes." if pending else "Publish."
    if arr_state == "published":
        return "Published: its reviewed values are facts in the licensee's history."
    return f"State {arr_state}: see the order's ARR page."


def readings(session: Session) -> dict[str, Any]:
    from .workbench import conventions

    sources = (
        session.execute(
            select(SourceDocument).where(SourceDocument.arr_state.is_not(None)).order_by(SourceDocument.acquired_at)
        )
        .scalars()
        .all()
    )
    by_commission: dict[str, list[SourceDocument]] = {}
    for src in sources:
        if src.utility is not None:
            by_commission.setdefault(src.utility.commission.code, []).append(src)
    states: dict[str, dict[str, Any]] = {}
    totals: Counter = Counter()
    for code, srcs in sorted(by_commission.items()):
        com = session.execute(select(Commission).where(Commission.code == code)).scalar_one()
        try:
            m = load_mapping(code, fallback=True)
            mapping = {"id": m.id, "version": m.version, "status": m.status.split(";")[0][:80]}
        except FileNotFoundError:
            mapping = None
        questions = conventions(session, code, srcs)
        labels: set[str] = set()
        for s in srcs:
            for u in ((s.arr_summary or {}).get("scan") or {}).get("unplaced") or []:
                labels.add(str(u.get("key") or u.get("example") or "").lower())
        orders = []
        for src in srcs:
            counts = Counter(
                session.execute(
                    select(CandidateRecord.review_status).where(
                        CandidateRecord.source_id == src.id, CandidateRecord.payload_kind == "arr"
                    )
                ).scalars()
            )
            ok, why = arr_mapping_confirmed(session, src)
            fixture = src.dataset.kind.value == "fixture"
            preview = _preview_totals(src.arr_summary)
            orders.append(
                {
                    "source_id": str(src.id),
                    "order": src.original_filename,
                    "dataset": src.dataset.kind.value,
                    "pages": src.page_count,
                    "licensees": [u.code for u in licensees_of(session, src)],
                    "arr_state": src.arr_state,
                    "preview": preview,
                    "candidates": dict(counts),
                    "decided": sum(counts.get(k, 0) for k in _DECIDED),
                    "mapping_confirmed": ok,
                    "next_step": next_step(src.arr_state, counts, ok, fixture),
                }
            )
            totals["orders"] += 1
            totals["real_orders"] += 0 if fixture else 1
            totals["values_previewed"] += (preview or {}).get("values", 0) if not fixture else 0
            totals["candidates_decided"] += orders[-1]["decided"]
        st = states.setdefault(
            com.jurisdiction.code, {"code": com.jurisdiction.code, "name": com.jurisdiction.name, "commissions": []}
        )
        st["commissions"].append(
            {
                "code": code,
                "name": com.name,
                "mapping": mapping,
                "mapping_confirmed": bool(mapping and mapping["status"].lower().startswith("confirmed")),
                "unplaced_labels": len(labels - {""}),
                "conventions_open": sum(1 for q in questions if not q.get("decision")),
                "conventions": len(questions),
                "orders": orders,
            }
        )
    out = sorted(states.values(), key=lambda s: s["name"])
    totals["states"] = len(out)
    return {
        "states": out,
        "totals": dict(totals),
        "note": (
            "Previews are what reading each proposed chapter would yield, recorded nowhere as data; values become "
            "facts only when a reviewer approves them under a confirmed mapping and they are published."
        ),
    }
