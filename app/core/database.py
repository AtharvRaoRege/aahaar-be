"""
Async SQLAlchemy engine, session factory, and declarative base.

PostgreSQL is the source of truth. Every request receives its own
``AsyncSession`` via the ``get_db`` dependency; sessions are never shared
across requests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (  # pyright: ignore[reportMissingImports]
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase  # pyright: ignore[reportMissingImports]

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug and not settings.is_production,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
    pool_recycle=280,
    future=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield a request-scoped session; rolls back on error, always closes."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
