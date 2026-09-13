"""Migrations replay from empty and downgrade cleanly (promotion rule 2 of Section 3.3)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def test_downgrade_and_upgrade_roundtrip(migrated_db):
    from tariff_api.cli import main as cli_main

    assert cli_main(["downgrade", "base"]) == 0
    engine = create_engine(migrated_db)
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))}
    assert tables == {"alembic_version"}
    assert cli_main(["migrate"]) == 0
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))}
        head = c.execute(text("select version_num from alembic_version")).scalar_one()
    engine.dispose()
    assert {"source_documents", "source_pages", "jobs", "job_events", "audit_events", "datasets", "users"} <= tables
    assert head == "0001_foundation"


def test_audit_events_are_append_only(migrated_db):
    engine = create_engine(migrated_db, isolation_level="AUTOCOMMIT")
    with engine.connect() as c:
        c.execute(text("insert into audit_events (actor, action, entity_type, entity_id) values ('t','a','e','1')"))
        with pytest.raises(Exception, match="append-only"):
            c.execute(text("update audit_events set actor='x' where actor='t'"))
        with pytest.raises(Exception, match="append-only"):
            c.execute(text("delete from audit_events where actor='t'"))
        c.execute(text("truncate audit_events"))
    engine.dispose()
