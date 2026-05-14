"""Postgres async session + schema initialization."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.core.config import settings
from backend.core.logging import logger


# ----------------------------------------------------------------------
# Base must be defined HERE — backend/models/models.py imports it from us.
# ----------------------------------------------------------------------
Base = declarative_base()


engine = create_async_engine(
    settings.postgres_dsn,           # <-- the only line that changed
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a per-request session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def _apply_migrations() -> None:
    """Apply every .sql file in migrations/ in lexicographic order."""
    if not MIGRATIONS_DIR.exists():
        return
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        return
    async with engine.begin() as conn:
        for sql_path in sql_files:
            sql_text = sql_path.read_text(encoding="utf-8")
            statements = [s.strip() for s in sql_text.split(";") if s.strip()]
            for stmt in statements:
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    logger.warning(
                        f"Migration {sql_path.name} statement skipped: {e}"
                    )
            logger.info(f"Applied migration: {sql_path.name}")


async def init_db() -> None:
    """Create tables (idempotent) and apply migrations."""
    # Lazy import to avoid circular dependency at module load time
    from backend.models import models as _models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _apply_migrations()