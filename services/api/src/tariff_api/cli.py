"""``tariff-api`` command line: migrations, OpenAPI export, seed data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import get_settings
from .models import DatasetKind

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
    p.add_argument("object_key")
    p.add_argument("--dataset", choices=[k.value for k in DatasetKind], default=DatasetKind.real.value)
    p.add_argument(
        "--actor",
        required=True,
        help="email of the person registering the source (recorded in the audit trail)",
    )
    p.add_argument("--provenance", default=None, help="where the document came from, if known")
    p.set_defaults(fn=cmd_ingest)

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
