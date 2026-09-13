"""``tariff-api`` command line: migrations, OpenAPI export, seed data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import get_settings

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


def cmd_check_config(args: argparse.Namespace) -> int:
    s = get_settings()
    from .adapters import build_adapters

    adapters = build_adapters(s)
    print(json.dumps({"profile": s.deployment_profile.value, "adapters": adapters.describe()}))
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
    p = sub.add_parser("check-config", help="validate profile and adapters")
    p.set_defaults(fn=cmd_check_config)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
