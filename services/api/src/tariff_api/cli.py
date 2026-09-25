"""``tariff-api`` command line: migrations, OpenAPI export, seed data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import get_settings
from .models import DatasetKind
from .schemas import ORDER_TYPES, parse_decides

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _alembic_config():
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def cmd_migrate(args: argparse.Namespace) -> int:
    from alembic import command

    command.upgrade(_alembic_config(), args.revision)
    return 0


def cmd_downgrade(args: argparse.Namespace) -> int:
    from alembic import command

    command.downgrade(_alembic_config(), args.revision)
    return 0


def cmd_reader_measure(args: argparse.Namespace) -> int:
    """Measure the optional Docling reader against the two production readers on one PDF
    (ADR-0009): per page, how many grids each reader finds, their shapes, and how Docling's
    grids agree with PyMuPDF's under the pipeline's own agreement scoring.  Read-only; nothing
    is written to the database or to storage.  Exits 2 when Docling or its models are not
    available here, saying which."""
    from . import readers
    from .inventory import open_document

    ok, why = readers.docling_available()
    if not ok:
        print(json.dumps({"docling": why, "hint": "uv sync --extra docling  (about 6 GB; models from huggingface.co)"}))
        return 2
    data = Path(args.pdf).read_bytes()
    doc = open_document(data)
    try:
        dl_grids, run = readers.read_tables_docling(data, artifacts_path=args.artifacts_path)
    except Exception as e:  # noqa: BLE001 - the operator needs the blocked host or the model error verbatim
        print(json.dumps({"docling": "failed", "error": f"{type(e).__name__}: {str(e)[:300]}"}))
        return 2
    by_page: dict[int, list] = {}
    for g in dl_grids:
        by_page.setdefault(g.page_index, []).append(g)
    pages_out = []
    totals = {"pymupdf": 0, "pdfplumber": 0, "docling": len(dl_grids), "paired": 0, "high_agreement": 0}
    for idx in range(1, doc.page_count + 1):
        page = doc[idx - 1]
        if not page.get_text("text").strip():
            continue
        prim = readers.read_tables_pymupdf(page, idx, "lines") or readers.read_tables_pymupdf(page, idx, "text")
        sec = readers.read_tables_pdfplumber(data, idx, "lines")
        dl = by_page.get(idx, [])
        agreements = readers.score_agreement(prim, dl) if (prim or dl) else []
        paired = [a for a in agreements if a.primary_ordinal is not None and a.secondary_ordinal is not None]
        totals["pymupdf"] += len(prim)
        totals["pdfplumber"] += len(sec)
        totals["paired"] += len(paired)
        totals["high_agreement"] += sum(1 for a in paired if a.classification == "high_agreement")
        if prim or sec or dl:
            pages_out.append(
                {
                    "page": idx,
                    "pymupdf": [[g.row_count, g.col_count] for g in prim],
                    "pdfplumber": [[g.row_count, g.col_count] for g in sec],
                    "docling": [[g.row_count, g.col_count] for g in dl],
                    "docling_vs_pymupdf": [
                        {
                            "pymupdf": a.primary_ordinal,
                            "docling": a.secondary_ordinal,
                            "class": a.classification,
                            "cells_equal": a.cell_equality,
                        }
                        for a in agreements
                    ],
                }
            )
    print(json.dumps({"pdf": args.pdf, "run": run, "totals": totals, "pages": pages_out}, indent=2))
    return 0


def cmd_provider_smoke(args: argparse.Namespace) -> int:
    """A real provider run on a two-cell synthetic structure (never a real order): proves the
    key, the model, the tool schema and the cost telemetry before any order is spent on it.
    With the fixture backend it says so and exits 2; nothing here touches the database."""
    from .adapters import build_adapters
    from .config import get_settings
    from .extraction import StructureInput
    from .providers import ProviderUnavailable, build_provider

    settings = get_settings()
    adapters = build_adapters(settings, include_identity=False)
    key_present = bool(adapters.secrets.get("ANTHROPIC_API_KEY") or "")
    facts = {
        "provider_backend": settings.provider_backend,
        "model": settings.anthropic_model,
        "secrets_backend": adapters.secrets.name,
        "anthropic_key_present": key_present,  # never the value
    }
    try:
        provider = build_provider(settings, adapters.secrets)
    except ProviderUnavailable as e:
        print(json.dumps({**facts, "status": "unavailable", "reason": str(e)}))
        return 1
    if provider.is_fixture:
        print(
            json.dumps(
                {
                    **facts,
                    "status": "fixture",
                    "reason": "set PROVIDER_BACKEND=anthropic (Terraform provider_backend) and a key version",
                }
            )
        )
        return 2
    cell = {
        "page_index": 1,
        "grid_ordinal": 0,
        "row": 1,
        "col": 1,
        "raw": "Rs. 3.00/ kWh",
        "header_path": ["Energy Charge"],
        "row_path": ["Metered", "Up to 100 kWh / month"],
        "normalised": {"value": "3.00", "value_state": "value"},
        "value_state": "value",
        "currency": "rupees",
        "per_unit": "kWh",
        "frequency": None,
        "unit_source": "cell",
        "flags": [],
        "footnotes": [],
        "slab": {
            "lower": None,
            "upper": "100",
            "kind": "absolute",
            "unit": "kWh",
            "original_text": "Up to 100 kWh / month",
        },
    }
    inp = StructureInput(
        source_sha="0" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="approved_schedule",
        region_ordinal=1,
        page_indices=[1],
        cells=[cell],
        headings=[
            {"page_index": 1, "kind": "rate_schedule", "code_canonical": "LMV-1", "text": "RATE SCHEDULE LMV - 1"}
        ],
        page_texts={1: "SYNTHETIC SMOKE INPUT - NOT A TARIFF ORDER\n"},
        period="FY2026-27",
        utility="SYNTHETIC",
    )
    try:
        res = provider.extract_structure(inp)
    except ProviderUnavailable as e:
        print(json.dumps({**facts, "status": "failed", "reason": str(e)}))
        return 1
    print(
        json.dumps(
            {
                "provider": res.provider,
                "model": res.model,
                "prompt_version": res.prompt_version,
                "schema_version": res.schema_version,
                "input_tokens": res.input_tokens,
                "output_tokens": res.output_tokens,
                "cost_usd": res.cost_usd,
                "candidates": len(res.output.candidates),
                "first": res.output.candidates[0].model_dump() if res.output.candidates else None,
                "is_fixture": res.is_fixture,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def cmd_profiles_schema(args: argparse.Namespace) -> int:
    from .profiles import schema_json

    out = schema_json()
    if args.output == "-":
        sys.stdout.write(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
    return 0


def cmd_openapi(args: argparse.Namespace) -> int:
    from .main import create_app

    app = create_app()
    spec = app.openapi()
    out = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(out)
    else:
        Path(args.output).write_text(out)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from .db import init_db, session_scope
    from .seed import seed_registry

    init_db(get_settings())
    with session_scope() as s:
        created = seed_registry(s)
    print(json.dumps(created))
    return 0


def _adapters():
    """Database + platform adapters for the operational commands."""
    from .adapters import build_adapters
    from .db import init_db

    settings = get_settings()
    init_db(settings)
    # The CLI never authenticates a request; `--actor` records who ran it.
    return settings, build_adapters(settings, include_identity=False)


def cmd_inbox(args: argparse.Namespace) -> int:
    """List objects in the source bucket and whether each is registered."""
    from .db import session_scope
    from .services.sources import list_inbox

    settings, adapters = _adapters()
    with session_scope() as s:
        rows = list_inbox(s, adapters.storage, prefix=args.prefix, limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print(f"no objects under prefix {args.prefix!r} in the source bucket")
        return 0
    width = max(len(r["object_key"]) for r in rows)
    for r in rows:
        state = "registered" if r["registered"] else "not registered"
        note = " (store copy)" if r["is_content_addressed_copy"] else ""
        print(f"{r['object_key']:<{width}}  {r['size_bytes']:>12,} B  {state}{note}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Register a PDF already present in the source bucket.

    The bytes are re-read and hashed here, so the object name is never identity; the result
    reports whether this was a new registration or a deduplication, and the queued job.
    """
    from .db import session_scope
    from .services.sources import register_from_object

    if "@" not in args.actor:
        print("--actor must be the email of the person performing the registration", file=sys.stderr)
        return 2
    settings, adapters = _adapters()
    with session_scope() as s:
        source, deduplicated, job = register_from_object(
            s,
            adapters.storage,
            settings,
            object_key=args.object_key,
            dataset_kind=DatasetKind(args.dataset),
            provenance_url=args.provenance,
            actor=args.actor,
            utility_code=args.utility,
            order_type=args.order_type,
            decides=parse_decides(args.decides),
        )
        s.flush()
        result = {
            "source_id": str(source.id),
            "sha256": source.sha256,
            "size_bytes": source.size_bytes,
            "original_filename": source.original_filename,
            "dataset": args.dataset,
            "deduplicated": deduplicated,
            "golden_id": source.golden_id,
            "manifest_check": source.manifest_check,
            "state": source.state.value,
            "inventory_job_id": str(job.id) if job else None,
        }
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    """List registered sources with their pipeline state and latest job — the operator's view
    while the API is VPC-internal.  Read-only."""
    from sqlalchemy import select

    from . import golden
    from .db import session_scope
    from .models import Job, SourceDocument, SourcePage

    settings, _ = _adapters()
    with session_scope() as s:
        rows = s.execute(select(SourceDocument).order_by(SourceDocument.acquired_at)).scalars().all()
        out = []
        for src in rows:
            job = s.execute(
                select(Job).where(Job.source_id == src.id).order_by(Job.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            check = golden.current_check(settings.golden_manifest_path, src)
            out.append(
                {
                    "source_id": str(src.id),
                    "original_filename": src.original_filename,
                    "dataset": src.dataset.kind.value,
                    "state": src.state.value,
                    "state_reason": src.state_reason,
                    "page_count": src.page_count,
                    "golden_id": src.golden_id,
                    "manifest_all_match": (check or {}).get("all_match"),
                    "manifest_check": check if args.json else None,
                    "pages_with_text": src.pages_with_text,
                    "pages_without_text": src.pages_without_text,
                    "pages_without_text_layer": (
                        list(
                            s.execute(
                                select(SourcePage.page_index)
                                .where(SourcePage.source_id == src.id, SourcePage.has_text_layer.is_(False))
                                .order_by(SourcePage.page_index)
                            ).scalars()
                        )
                        if args.json
                        else None
                    ),
                    "latest_job": (
                        {
                            "id": str(job.id),
                            "type": job.job_type,
                            "status": job.status.value,
                            "stage": job.stage,
                            "attempts": job.attempts,
                            "progress": job.progress,
                            "error_type": job.error_type,
                            "error": (job.error_message or "")[:200] or None,
                        }
                        if job
                        else None
                    ),
                }
            )
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    if not out:
        print("no sources registered")
        return 0
    for r in out:
        j = r["latest_job"]
        jtxt = (
            f"{j['type']} {j['status']}" + (f" [{j['error_type']}]" if j and j["error_type"] else "") if j else "no job"
        )
        m = r["manifest_all_match"]
        manifest = "ok" if m else ("n/a" if m is None else "MISMATCH")
        print(
            f"{r['source_id']}  {r['dataset']:<7} {r['state']:<18} pages={r['page_count'] or '?':<4} "
            f"manifest={manifest}  {jtxt}  {r['original_filename']}"
        )
    return 0


def cmd_assign_profile(args: argparse.Namespace) -> int:
    """Bind a reading profile version to a source (administrator); queues a localisation
    re-run when the source is parsed or beyond.  Audited."""
    import uuid

    from .db import session_scope
    from .services.localisation import assign_profile
    from .services.sources import get_source

    settings, _ = _adapters()
    with session_scope() as s:
        src = get_source(s, uuid.UUID(args.source_id))
        profile, rerun = assign_profile(
            s, settings, src, args.profile_id, args.version, actor=args.actor, reason=args.reason
        )
        print(
            json.dumps(
                {"source_id": args.source_id, "profile": f"{profile.id}@{profile.version}", "rerun_queued": rerun}
            )
        )
    return 0


def cmd_rerun(args: argparse.Namespace) -> int:
    """Re-run one reading stage for a source (administrator).  Downstream stages re-chain."""
    import uuid

    from .db import session_scope
    from .services.sources import get_source, request_stage_rerun

    settings, _ = _adapters()
    with session_scope() as s:
        src = get_source(s, uuid.UUID(args.source_id))
        job = request_stage_rerun(s, settings, src, args.job_type, actor=args.actor)
        s.flush()
        print(
            json.dumps(
                {
                    "source_id": args.source_id,
                    "job_type": args.job_type,
                    "job_id": str(job.id),
                    "state": src.state.value,
                }
            )
        )
    return 0


def cmd_page_dump(args: argparse.Namespace) -> int:
    """Everything the pipeline holds for one page, as JSON, for diagnosing a wrong reading
    without the browser: the primary grids as read (rows, header rows, reader, agreement),
    the structure cells (row, column, header path, row path, text, state, flags) and the
    candidates whose evidence cites the page (value, block, row, channel agreement, the
    cited cell, whether the model channel had it).  Read-only."""
    import uuid

    from sqlalchemy import select

    from .adapters.storage import ObjectNotFound, ObjectStore
    from .db import session_scope
    from .models import CandidateRecord, StructureCell, TableGridRecord

    _, adapters = _adapters()
    storage: ObjectStore = adapters.storage
    sid, page = uuid.UUID(args.source_id), int(args.page)
    with session_scope() as s:
        grids = []
        for g in (
            s.execute(
                select(TableGridRecord)
                .where(
                    TableGridRecord.source_id == sid,
                    TableGridRecord.page_index == page,
                    TableGridRecord.is_primary.is_(True),
                )
                .order_by(TableGridRecord.ordinal)
            )
            .scalars()
            .all()
        ):
            try:
                rows = json.loads(storage.get(ObjectStore.ARTEFACTS, g.object_key))["grid"]["rows"]
            except (ObjectNotFound, KeyError, ValueError):
                rows = None
            grids.append(
                {
                    "ordinal": g.ordinal,
                    "reader": g.reader,
                    "strategy": g.strategy,
                    "header_rows": g.header_rows,
                    "agreement_class": g.agreement_class,
                    "risk_tags": g.risk_tags,
                    "rows": rows,
                }
            )
        cells = [
            {
                "grid": c.grid_ordinal,
                "row": c.row,
                "col": c.col,
                "header_path": c.header_path,
                "row_path": c.row_path,
                "raw": c.raw,
                "value_state": c.value_state,
                "value": (c.normalised or {}).get("value"),
                "flags": c.flags,
                "region_role": c.region_role,
            }
            for c in s.execute(
                select(StructureCell)
                .where(StructureCell.source_id == sid, StructureCell.page_index == page)
                .order_by(StructureCell.grid_ordinal, StructureCell.row, StructureCell.col)
            ).scalars()
        ]
        cands = []
        for c in s.execute(select(CandidateRecord).where(CandidateRecord.source_id == sid)).scalars():
            rec = c.record or {}
            ev = (rec.get("evidence") or [{}])[0]
            if ev.get("page_index") != page:
                continue
            a = rec.get("applicability") or {}
            cands.append(
                {
                    "family": c.family,
                    "category": c.category_code,
                    "component": c.component_type,
                    "value": c.value,
                    "value_state": c.value_state,
                    "unit": " ".join(x for x in (c.currency, c.per_unit, c.frequency) if x),
                    "block": a.get("rate_block"),
                    "row": a.get("description"),
                    "voltage": a.get("voltage"),
                    "channel_agreement": c.channel_agreement,
                    "model_had_it": c.image_record is not None,
                    "risk_tags": c.risk_tags,
                    "evidence": {
                        k: ev.get(k) for k in ("kind", "grid_ordinal", "row", "col", "header_path", "row_path")
                    },
                    "excerpt": ev.get("excerpt"),
                    "review_status": c.review_status.value if hasattr(c.review_status, "value") else c.review_status,
                }
            )
        cands.sort(
            key=lambda x: (x["evidence"].get("grid_ordinal") or 0, x["evidence"].get("row") or 0, x["component"])
        )
    print(json.dumps({"source_id": args.source_id, "page": page, "grids": grids, "cells": cells, "candidates": cands}))
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    """Assign an order to a reviewer (administrator, from the admin job).  The reviewer must
    be an active user with the reviewer role or higher; `--clear` removes the assignment."""
    import uuid

    from .auth import ROLE_RANK, known_role
    from .db import session_scope
    from .models import AuditEvent, UserRole
    from .services.sources import get_source

    settings, _ = _adapters()
    with session_scope() as s:
        src = get_source(s, uuid.UUID(args.source_id))
        reviewer = None if args.clear else (args.email or "").strip().lower()
        if reviewer:
            role = known_role(s, settings, reviewer)
            if role is None or ROLE_RANK[role] < ROLE_RANK[UserRole.reviewer]:
                print(
                    json.dumps({"error": f"{reviewer} is not an active reviewer; add with: users add --role reviewer"})
                )
                return 2
        before = src.assigned_to
        src.assigned_to = reviewer
        s.add(
            AuditEvent(
                actor=args.actor,
                action="source.assign",
                entity_type="source",
                entity_id=str(src.id),
                before={"assigned_to": before},
                after={"assigned_to": reviewer},
                reason="cli",
            )
        )
        print(json.dumps({"source_id": args.source_id, "assigned_to": reviewer, "was": before}))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Write one order's pipeline state as JSON files: to the export bucket under
    `<COMMISSION>/<UTILITY>/<name>/` (default) and/or to a local directory (`--out`)."""
    import uuid
    from pathlib import Path

    from .db import session_scope
    from .services import export as export_svc
    from .services.sources import get_source

    settings, adapters = _adapters()
    written: dict[str, Any] = {}
    with session_scope() as s:
        src = get_source(s, uuid.UUID(args.source_id))
        if args.out:
            root = Path(args.out) / export_svc.export_name(src)
            for path, data in export_svc.build_files(s, adapters.storage, settings, src).items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            written["local"] = str(root)
        if not args.no_bucket:
            keys = export_svc.write_to_bucket(s, adapters.storage, settings, src)
            written["bucket"] = {"prefix": export_svc.export_prefix(src), "files": len(keys)}
    print(json.dumps({"source_id": args.source_id, **written}))
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    """List users, or add/update one.  Role changes are audit events."""
    from sqlalchemy import select

    from .db import session_scope
    from .models import AuditEvent, User, UserRole

    _adapters()
    with session_scope() as s:
        if args.action == "list":
            rows = s.execute(select(User).order_by(User.email)).scalars().all()
            if not rows:
                print("no users registered")
            for u in rows:
                print(f"{u.email:<40} {u.role.value:<14} {'active' if u.active else 'disabled'}")
            return 0

        email = args.email.strip().lower()
        user = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        before = None
        if user is None:
            user = User(email=email, display_name=args.name, role=UserRole(args.role), active=True)
            s.add(user)
            action = "user.created"
        else:
            before = {"role": user.role.value, "active": user.active}
            user.role = UserRole(args.role)
            if args.name:
                user.display_name = args.name
            user.active = True
            action = "user.updated"
        s.flush()
        s.add(
            AuditEvent(
                actor=args.actor,
                action=action,
                entity_type="user",
                entity_id=str(user.id),
                before=before,
                after={"role": user.role.value, "active": True},
                reason="cli",
            )
        )
        print(f"{action}: {email} -> {args.role}")
    return 0


def cmd_check_config(args: argparse.Namespace) -> int:
    s = get_settings()
    from .adapters import build_adapters

    adapters = build_adapters(s)
    print(json.dumps({"profile": s.deployment_profile.value, "adapters": adapters.describe()}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tariff-api")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("migrate", help="apply migrations")
    p.add_argument("revision", nargs="?", default="head")
    p.set_defaults(fn=cmd_migrate)
    p = sub.add_parser("downgrade", help="revert migrations")
    p.add_argument("revision")
    p.set_defaults(fn=cmd_downgrade)
    p = sub.add_parser(
        "provider-smoke",
        help="one small extraction through the configured provider; reports provider, model, tokens and cost",
    )
    p.set_defaults(fn=cmd_provider_smoke)
    p = sub.add_parser(
        "reader-measure", help="measure the optional Docling reader against PyMuPDF/pdfplumber on one PDF"
    )
    p.add_argument("--pdf", required=True, help="path to a PDF (a fixture, or a real order copied from the bucket)")
    p.add_argument(
        "--artifacts-path", default=None, help="pre-downloaded Docling models directory (docling-tools models download)"
    )
    p.set_defaults(fn=cmd_reader_measure)
    p = sub.add_parser("profiles-schema", help="export the reading-profile JSON schema")
    p.add_argument("-o", "--output", default="-")
    p.set_defaults(fn=cmd_profiles_schema)
    p = sub.add_parser("openapi", help="export the OpenAPI document")
    p.add_argument("--output", "-o", default="-")
    p.set_defaults(fn=cmd_openapi)
    p = sub.add_parser("seed", help="seed jurisdictions/commissions/utilities for the initial sources")
    p.set_defaults(fn=cmd_seed)
    p = sub.add_parser("inbox", help="list objects in the source bucket and their registration state")
    p.add_argument("--prefix", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_inbox)

    p = sub.add_parser("ingest", help="register a PDF already in the source bucket")
    p.add_argument("--utility", default=None, help="utility code the order belongs to")
    p.add_argument("--order-type", default=None, choices=list(ORDER_TYPES), help="what the instrument is")
    p.add_argument(
        "--decides", default=None, help='years and voices, e.g. "FY2024-25:final_true_up,FY2026-27:approved"'
    )
    p.add_argument("object_key")
    p.add_argument("--dataset", choices=[k.value for k in DatasetKind], default=DatasetKind.real.value)
    p.add_argument(
        "--actor",
        required=True,
        help="email of the person registering the source (recorded in the audit trail)",
    )
    p.add_argument("--provenance", default=None, help="where the document came from, if known")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("sources", help="list registered sources with pipeline state and latest job")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_sources)

    p = sub.add_parser("assign-profile", help="bind a reading profile version to a source (queues localisation)")
    p.add_argument("source_id")
    p.add_argument("profile_id")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_assign_profile)

    p = sub.add_parser("rerun", help="re-run one reading stage for a source")
    p.add_argument("source_id")
    p.add_argument(
        "job_type",
        choices=[
            "triage_source",
            "parse_source",
            "localise_source",
            "grid_source",
            "extract_source",
            "validate_source",
        ],
    )
    p.add_argument("--actor", required=True)
    p.set_defaults(fn=cmd_rerun)

    p = sub.add_parser("page-dump", help="grids, structure cells and candidates of one page, as JSON (diagnostic)")
    p.add_argument("source_id")
    p.add_argument("--page", required=True)
    p.set_defaults(fn=cmd_page_dump)
    p = sub.add_parser("export", help="write an order's pipeline state as JSON files (bucket and/or --out dir)")
    p.add_argument("source_id")
    p.add_argument("--out", default=None, help="local directory; a folder named after the order is created inside")
    p.add_argument("--no-bucket", action="store_true", help="skip the export bucket")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("assign-reviewer", help="assign an order to a reviewer (or --clear)")
    p.add_argument("source_id")
    p.add_argument("--email", default=None)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--actor", required=True)
    p.set_defaults(fn=cmd_assign)
    p = sub.add_parser("users", help="list users, or add/update one")
    p.add_argument("action", choices=["list", "add"])
    p.add_argument("--email")
    p.add_argument("--role", choices=["analyst", "reviewer", "administrator"], default="analyst")
    p.add_argument("--name", default=None)
    p.add_argument("--actor", default="cli", help="who is making the change (recorded in the audit trail)")
    p.set_defaults(fn=cmd_users)

    p = sub.add_parser("check-config", help="validate profile and adapters")
    p.set_defaults(fn=cmd_check_config)
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None) == "users" and args.action == "add" and not args.email:
        parser.error("users add requires --email")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
