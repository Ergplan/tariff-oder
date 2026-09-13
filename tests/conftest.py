"""Test harness: real PostgreSQL, filesystem object store, local identity adapter.

Set ``TARIFF_TEST_DATABASE_URL`` to point at a scratch database.  The schema is dropped and
migrated from empty at session start (migration replay is itself a tested requirement).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

TEST_DB = os.environ.get("TARIFF_TEST_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/tariff_test")

ADMIN = "admin@example.com"
REVIEWER = "reviewer@example.com"
ANALYST = "analyst@example.com"


def _configure_env(tmp_root: Path) -> None:
    os.environ["DEPLOYMENT_PROFILE"] = "local"
    os.environ["ENVIRONMENT_NAME"] = "test"
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ["OBJECT_STORE_BACKEND"] = "filesystem"
    os.environ["OBJECT_STORE_ROOT"] = str(tmp_root / "object-store")
    os.environ["SECRETS_BACKEND"] = "env"
    os.environ["IDENTITY_BACKEND"] = "local"
    os.environ["LOCAL_USER_ALLOWLIST"] = f"{ADMIN}:administrator,{REVIEWER}:reviewer,{ANALYST}:analyst"
    os.environ["GOLDEN_MANIFEST_PATH"] = str(ROOT / "tests" / "golden" / "manifest.json")
    os.environ["JOB_LEASE_SECONDS"] = os.environ.get("JOB_LEASE_SECONDS", "3")
    os.environ["JOB_HEARTBEAT_SECONDS"] = "1"
    os.environ["INVENTORY_CHECKPOINT_EVERY_PAGES"] = "2"
    os.environ["LOG_FORMAT"] = "text"
    os.environ["LOG_LEVEL"] = "WARNING"


@pytest.fixture(scope="session")
def env_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("tariff")
    _configure_env(root)
    return root


@pytest.fixture(scope="session")
def migrated_db(env_root: Path):
    """Drop everything and replay migrations from empty."""
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_DB, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    from tariff_api.cli import main as cli_main
    from tariff_api.config import reset_settings_cache

    reset_settings_cache()
    assert cli_main(["migrate"]) == 0
    yield TEST_DB


@pytest.fixture()
def object_store_root(env_root: Path, tmp_path: Path):
    """A fresh object store per test.  Object keys are immutable by design, so a store shared
    across tests would serve an earlier test's bytes for the same key."""
    root = tmp_path / "object-store"
    root.mkdir(parents=True, exist_ok=True)
    previous = os.environ["OBJECT_STORE_ROOT"]
    os.environ["OBJECT_STORE_ROOT"] = str(root)
    yield root
    os.environ["OBJECT_STORE_ROOT"] = previous


@pytest.fixture()
def clean_tables(migrated_db):
    """Truncate mutable tables between tests (audit_events is append-only and is not truncated
    by row deletes; TRUNCATE bypasses the row trigger, which is intentional for tests only)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_DB, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE idempotency_records, job_events, jobs, source_pages, source_documents, "
                "utilities, commissions, jurisdictions, users, datasets, audit_events RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()
    yield


@pytest.fixture()
def app(clean_tables, object_store_root):
    from tariff_api.config import get_settings, reset_settings_cache
    from tariff_api.db import dispose_db
    from tariff_api.main import create_app

    reset_settings_cache()
    application = create_app(get_settings())
    yield application
    dispose_db()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def headers(user: str, **extra: str) -> dict[str, str]:
    return {"X-Local-User": user, **extra}


@pytest.fixture()
def storage(app):
    """The object store the API and worker share in this test."""
    return app.state.adapters.storage


@pytest.fixture()
def runner(app):
    """In-process worker.  It builds its own adapters with no identity provider, exactly as the
    real worker process does — it must never be able to authenticate anyone."""
    from tariff_api.adapters import build_adapters
    from tariff_worker.main import HANDLERS
    from tariff_worker.runner import Runner

    adapters = build_adapters(app.state.settings, include_identity=False)
    assert adapters.identity is None
    return Runner(app.state.settings, adapters, HANDLERS, worker_name="test-worker-A")
