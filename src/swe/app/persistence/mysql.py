# -*- coding: utf-8 -*-
"""Async SQLAlchemy helpers for control-store persistence."""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ...constant import MYSQL_CHAT_CONTROL_DSN

_SCHEMA_LOCKS: dict[int, asyncio.Lock] = {}
_SCHEMA_READY: set[int] = set()


def create_control_store_engine(dsn: str | None = None) -> AsyncEngine:
    """Create the shared control-store engine."""
    url = dsn or MYSQL_CHAT_CONTROL_DSN
    if not url:
        raise RuntimeError("SWE_MYSQL_CHAT_CONTROL_DSN is not configured")
    return create_async_engine(
        url,
        future=True,
        pool_pre_ping=True,
    )


def create_control_store_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create async sessions bound to the control-store engine."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def ensure_control_store_schema(engine: AsyncEngine) -> None:
    """Create control-store schema objects once per engine."""
    engine_id = id(engine)
    if engine_id in _SCHEMA_READY:
        return

    lock = _SCHEMA_LOCKS.setdefault(engine_id, asyncio.Lock())
    async with lock:
        if engine_id in _SCHEMA_READY:
            return

        from ..runner.repo.mysql_schema import CONTROL_STORE_METADATA

        async with engine.begin() as conn:
            await conn.run_sync(CONTROL_STORE_METADATA.create_all)
        _SCHEMA_READY.add(engine_id)
