# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from .mysql_schema import session_checkpoints_table
from .session_checkpoint_base import BaseSessionCheckpointRepository
from ..session_models import (
    SessionCheckpointConflictError,
    SessionCheckpointKey,
    SessionCheckpointRecord,
)


class MySQLSessionCheckpointRepository(BaseSessionCheckpointRepository):
    """Authoritative compare-and-set repository for session checkpoints."""

    def __init__(self, engine: AsyncEngine, agent_id: str):
        self._engine = engine
        self._agent_id = agent_id

    async def get_latest(
        self,
        key: SessionCheckpointKey,
    ) -> SessionCheckpointRecord | None:
        row = await self._fetch_latest_row(key)
        if row is None:
            return None
        return self._record_from_row(key, row)

    async def write_checkpoint(
        self,
        *,
        key: SessionCheckpointKey,
        expected_version: int | None,
        blob_path: str,
        payload_sha256: str,
    ) -> SessionCheckpointRecord:
        current_row = await self._fetch_latest_row(key)
        actual_version = (
            int(current_row["version"]) if current_row is not None else None
        )

        if actual_version != expected_version:
            raise SessionCheckpointConflictError(
                key=key,
                expected_version=expected_version,
                actual_version=actual_version,
            )

        if current_row is None:
            try:
                version = await self._insert_first_row(
                    key=key,
                    blob_path=blob_path,
                    payload_sha256=payload_sha256,
                )
            except IntegrityError as exc:
                latest = await self._fetch_latest_row(key)
                raise SessionCheckpointConflictError(
                    key=key,
                    expected_version=expected_version,
                    actual_version=(
                        int(latest["version"]) if latest is not None else None
                    ),
                ) from exc
        else:
            try:
                version = await self._update_existing_row(
                    key=key,
                    expected_version=expected_version,
                    blob_path=blob_path,
                    payload_sha256=payload_sha256,
                )
            except SessionCheckpointConflictError:
                raise

        return SessionCheckpointRecord(
            key=key,
            version=version,
            blob_path=blob_path,
            payload_sha256=payload_sha256,
        )

    async def _fetch_latest_row(self, key: SessionCheckpointKey):
        stmt = (
            select(
                session_checkpoints_table.c.tenant_id,
                session_checkpoints_table.c.user_id,
                session_checkpoints_table.c.session_id,
                session_checkpoints_table.c.version,
                session_checkpoints_table.c.blob_path,
                session_checkpoints_table.c.payload_sha256,
            )
            .where(
                session_checkpoints_table.c.tenant_id == key.tenant_id,
                session_checkpoints_table.c.agent_id == self._agent_id,
                session_checkpoints_table.c.user_id == key.user_id,
                session_checkpoints_table.c.session_id == key.session_id,
            )
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(stmt)).mappings().first()
        return dict(row) if row is not None else None

    async def _insert_first_row(
        self,
        *,
        key: SessionCheckpointKey,
        blob_path: str,
        payload_sha256: str,
    ) -> int:
        stmt = insert(session_checkpoints_table).values(
            tenant_id=key.tenant_id,
            agent_id=self._agent_id,
            user_id=key.user_id,
            session_id=key.session_id,
            version=1,
            blob_path=blob_path,
            payload_sha256=payload_sha256,
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)
        return 1

    async def _update_existing_row(
        self,
        *,
        key: SessionCheckpointKey,
        expected_version: int,
        blob_path: str,
        payload_sha256: str,
    ) -> int:
        next_version = expected_version + 1
        stmt = (
            update(session_checkpoints_table)
            .where(
                session_checkpoints_table.c.tenant_id == key.tenant_id,
                session_checkpoints_table.c.agent_id == self._agent_id,
                session_checkpoints_table.c.user_id == key.user_id,
                session_checkpoints_table.c.session_id == key.session_id,
                session_checkpoints_table.c.version == expected_version,
            )
            .values(
                version=next_version,
                blob_path=blob_path,
                payload_sha256=payload_sha256,
            )
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(stmt)
        if result.rowcount == 0:
            latest = await self._fetch_latest_row(key)
            raise SessionCheckpointConflictError(
                key=key,
                expected_version=expected_version,
                actual_version=(
                    int(latest["version"]) if latest is not None else None
                ),
            )
        return next_version

    async def close(self) -> None:
        await self._engine.dispose()

    @staticmethod
    def _record_from_row(
        key: SessionCheckpointKey,
        row,
    ) -> SessionCheckpointRecord:
        return SessionCheckpointRecord(
            key=key,
            version=int(row["version"]),
            blob_path=row["blob_path"],
            payload_sha256=row["payload_sha256"],
        )
