# -*- coding: utf-8 -*-
"""MySQL-backed durable chat run repository."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from ...persistence.mysql import (
    create_control_store_session_factory,
    ensure_control_store_schema,
)
from ..run_models import ChatRunRecord, ChatRunStatus
from .mysql_schema import chat_runs_table
from .run_base import BaseChatRunRepository


class MysqlChatRunRepository(BaseChatRunRepository):
    """Tenant- and agent-scoped durable run store."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        tenant_id: str,
        agent_id: str,
    ) -> None:
        self._engine = engine
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._session_factory = create_control_store_session_factory(engine)

    def _scope(self):
        return (
            chat_runs_table.c.tenant_id == self._tenant_id,
            chat_runs_table.c.agent_id == self._agent_id,
        )

    @staticmethod
    def _row_to_record(row) -> ChatRunRecord:
        payload = dict(row._mapping)
        payload["id"] = payload.pop("run_id")
        return ChatRunRecord.model_validate(payload)

    async def create_run(self, record: ChatRunRecord) -> ChatRunRecord:
        await ensure_control_store_schema(self._engine)
        values = record.model_dump(mode="python")
        values["run_id"] = values.pop("id")
        values["tenant_id"] = self._tenant_id
        values["agent_id"] = self._agent_id

        async with self._session_factory() as session:
            await session.execute(insert(chat_runs_table).values(**values))
            await session.commit()
        return record

    async def finish_run(
        self,
        run_id: str,
        *,
        status: ChatRunStatus,
        error: str | None = None,
    ) -> None:
        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            await session.execute(
                update(chat_runs_table)
                .where(
                    *self._scope(),
                    chat_runs_table.c.run_id == run_id,
                )
                .values(
                    status=status,
                    finished_at=datetime.now(timezone.utc),
                    error=error,
                ),
            )
            await session.commit()

    async def list_runs(
        self,
        chat_id: str,
        *,
        limit: int,
    ) -> list[ChatRunRecord]:
        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            result = await session.execute(
                select(chat_runs_table)
                .where(
                    *self._scope(),
                    chat_runs_table.c.chat_id == chat_id,
                )
                .order_by(chat_runs_table.c.started_at.desc())
                .limit(limit),
            )
        return [self._row_to_record(row) for row in result.fetchall()]
