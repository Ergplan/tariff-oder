"""SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
        future=True,
    )


def init_db(settings: Settings) -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = build_engine(settings)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("database not initialised; call init_db() first")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _session_factory is None:
        raise RuntimeError("database not initialised; call init_db() first")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(engine: Engine) -> dict:
    with engine.connect() as conn:
        version = conn.execute(text("select version()")).scalar_one()
        head = conn.execute(text("select version_num from alembic_version")).scalar_one_or_none()
        vector = conn.execute(text("select extversion from pg_extension where extname='vector'")).scalar_one_or_none()
    return {"server_version": version, "migration_head": head, "pgvector_version": vector}
