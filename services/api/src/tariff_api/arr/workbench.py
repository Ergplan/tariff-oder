"""The mapping workbench (increment 39): what a commission's mapping does not yet place, across
every order of that commission read so far, and a reviewer's decision on each label.

A commission's mapping file is the gate on real ARR approvals (ADR-0018): until a reviewer
confirms it, real lines can be read and reviewed but not approved.  The workbench gathers the
scan's unplaced row labels (with how often and on which pages of which orders), suggests
taxonomy codes by word overlap (a suggestion, never a placement), records the reviewer's
decisions, and renders the next version of the mapping file with them for a person to commit.
The rendered file says ``draft``; confirming it is a separate human act."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import AuditEvent, Commission, MappingDecision, SourceDocument, Utility
from ..telemetry import request_id_var
from .taxonomy import load_mapping, load_taxonomy, mapping_files, norm_label

_STOP = {
    "of",
    "the",
    "and",
    "for",
    "in",
    "on",
    "to",
    "a",
    "an",
    "as",
    "per",
    "by",
    "with",
    "fy",
    "rs",
    "cr",
    "less",
    "add",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9&]+", text.lower()) if w not in _STOP and len(w) > 1}


def suggest(label: str, limit: int = 3) -> list[dict[str, Any]]:
    """Taxonomy codes whose label or aliases share the most words with this label."""
    tax = load_taxonomy()
    words = _words(label)
    if not words:
        return []
    scored = []
    for item in tax.line_items:
        if item.kind == "group":
            continue
        best = 0.0
        for name in [item.label, *item.aliases]:
            other = _words(name)
            if other:
                best = max(best, len(words & other) / len(words | other))
        if best > 0:
            scored.append((best, item.code, item.label))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"code": c, "label": lab, "score": round(sc, 2)} for sc, c, lab in scored[:limit]]


def unplaced(session: Session, commission: str) -> dict[str, Any]:
    """Every unplaced label of the commission's read orders, most frequent first, with the
    decision taken on it (if any) and suggestions."""
    c = session.execute(select(Commission).where(Commission.code == commission)).scalar_one_or_none()
    if c is None:
        raise AppError("not_found", f"commission {commission} not found")
    sources = (
        session.execute(
            select(SourceDocument)
            .join(Utility, Utility.id == SourceDocument.utility_id)
            .where(Utility.commission_id == c.id, SourceDocument.arr_summary.is_not(None))
        )
        .scalars()
        .all()
    )
    agg: dict[str, dict[str, Any]] = {}
    for src in sources:
        scan = (src.arr_summary or {}).get("scan") or {}
        for u in scan.get("unplaced") or []:
            key = norm_label(str(u.get("key") or u.get("example") or ""))
            if not key:
                continue
            row = agg.setdefault(key, {"label": key, "count": 0, "orders": [], "example": u.get("example")})
            row["count"] += int(u.get("count") or 0)
            row["orders"].append(
                {"source_id": str(src.id), "order": src.original_filename, "pages": (u.get("pages") or [])[:12]}
            )
    decisions = {
        d.label: d
        for d in session.execute(select(MappingDecision).where(MappingDecision.commission_code == c.code)).scalars()
    }
    rows = sorted(agg.values(), key=lambda r: (-r["count"], r["label"]))
    for r in rows:
        d = decisions.get(r["label"])
        r["decision"] = (
            {"kind": d.kind, "code": d.code, "note": d.note, "by": d.decided_by, "at": d.decided_at.isoformat()}
            if d
            else None
        )
        r["suggestions"] = [] if d else suggest(r["label"])
    try:
        m = load_mapping(c.code)
        mapping = {"id": m.id, "version": m.version, "status": m.status}
    except FileNotFoundError:
        mapping = None
    return {
        "commission": c.code,
        "mapping": mapping,
        "orders": [{"source_id": str(s.id), "order": s.original_filename, "arr_state": s.arr_state} for s in sources],
        "labels": rows,
        "decided": sum(1 for r in rows if r["decision"]),
        "note": (
            "Suggestions are word overlaps, never placements.  A decision becomes part of the mapping only when "
            "a person writes the next version of the mapping file and a reviewer confirms it."
        ),
    }


def decide(
    session: Session,
    commission: str,
    *,
    label: str,
    kind: str,
    code: str | None,
    note: str | None,
    example: str | None,
    actor: str,
) -> MappingDecision:
    key = norm_label(label)
    if not key:
        raise AppError("validation_failed", "an empty label")
    if kind not in ("alias", "not_a_line"):
        raise AppError("validation_failed", "kind is alias or not_a_line")
    if kind == "alias":
        if not code or code not in load_taxonomy().by_code():
            raise AppError("validation_failed", f"{code!r} is not a line of the ARR taxonomy")
    else:
        code = None
    d = session.execute(
        select(MappingDecision).where(MappingDecision.commission_code == commission, MappingDecision.label == key)
    ).scalar_one_or_none()
    before = {"kind": d.kind, "code": d.code} if d else None
    if d is None:
        d = MappingDecision(commission_code=commission, label=key, kind=kind, code=code, decided_by=actor)
        session.add(d)
    d.kind, d.code, d.note, d.decided_by = kind, code, (note or None), actor
    d.example = (example or d.example or None) and str(example or d.example)[:500]
    session.add(
        AuditEvent(
            actor=actor,
            action="arr.mapping_decision",
            entity_type="mapping",
            entity_id=commission,
            before=before,
            after={"label": key, "kind": kind, "code": code},
            reason=note,
            request_id=request_id_var.get(),
        )
    )
    session.flush()
    return d


def withdraw(session: Session, commission: str, label: str, *, actor: str) -> None:
    key = norm_label(label)
    d = session.execute(
        select(MappingDecision).where(MappingDecision.commission_code == commission, MappingDecision.label == key)
    ).scalar_one_or_none()
    if d is None:
        raise AppError("not_found", "no decision on that label")
    session.add(
        AuditEvent(
            actor=actor,
            action="arr.mapping_decision_withdrawn",
            entity_type="mapping",
            entity_id=commission,
            before={"label": key, "kind": d.kind, "code": d.code},
            request_id=request_id_var.get(),
        )
    )
    session.delete(d)


def draft(session: Session, commission: str) -> dict[str, Any]:
    """The next version of the commission's mapping file with the decisions written in: aliases
    into ``label_aliases``, "not a line" into ``unplaced``.  Status ``draft``; a person commits
    it and a reviewer confirms it."""
    files = mapping_files().get(commission.upper())
    if not files:
        raise AppError("not_found", f"no mapping file for {commission} to build on")
    version, path = max(files)
    data = copy.deepcopy(json.loads(path.read_text()))
    rows = (
        session.execute(
            select(MappingDecision)
            .where(MappingDecision.commission_code == commission)
            .order_by(MappingDecision.kind, MappingDecision.label)
        )
        .scalars()
        .all()
    )
    aliases = {norm_label(str(e.get("label") or "")): e for e in data["label_aliases"]["entries"]}
    for d in rows:
        if d.kind == "alias":
            aliases[d.label] = {
                "label": d.label,
                "code": d.code,
                "note": f"decided by {d.decided_by}" + (f": {d.note}" if d.note else ""),
            }
    data["label_aliases"]["entries"] = sorted(aliases.values(), key=lambda e: str(e["label"]))
    not_lines = {str(e.get("label")): e for e in data["unplaced"]["entries"]}
    for d in rows:
        if d.kind == "not_a_line":
            not_lines[d.label] = {
                "label": d.label,
                "decision": "not_a_line",
                "note": f"decided by {d.decided_by}" + (f": {d.note}" if d.note else ""),
            }
    data["unplaced"]["entries"] = sorted(not_lines.values(), key=lambda e: str(e["label"]))
    deciders = sorted({d.decided_by for d in rows})
    data["version"] = version + 1
    data["status"] = (
        f"draft: v{version} with {len(rows)} reviewer decision(s) by {', '.join(deciders) or 'nobody'}; "
        "not confirmed — a reviewer confirms the whole file before real lines can be approved"
    )
    return data
