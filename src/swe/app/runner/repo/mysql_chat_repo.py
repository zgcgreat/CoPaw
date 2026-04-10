# -*- coding: utf-8 -*-
"""MySQL-backed chat repository."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from ...persistence.mysql import (
    create_control_store_session_factory,
    ensure_control_store_schema,
)
from ..models import ChatSpec
from .base import BaseChatRepository
from .mysql_schema import chat_specs_table


class MysqlChatRepository(BaseChatRepository):
    """Tenant- and agent-scoped authoritative chat repository."""

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
        self.path = f"mysql://{tenant_id}/{agent_id}/chat_specs"

    def _scope(self):
        return (
            chat_specs_table.c.tenant_id == self._tenant_id,
            chat_specs_table.c.agent_id == self._agent_id,
        )

    @staticmethod
    def _row_to_spec(row) -> ChatSpec:
        payload = dict(row._mapping)
        payload["id"] = payload.pop("chat_id")
        payload["meta"] = payload.get("meta") or {}
        return ChatSpec.model_validate(payload)

    @staticmethod
    def _spec_values(spec: ChatSpec) -> dict:
        payload = spec.model_dump(mode="python")
        payload["chat_id"] = payload.pop("id")
        return payload

    async def list_chats(self) -> list[ChatSpec]:
        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            result = await session.execute(
                select(chat_specs_table)
                .where(*self._scope())
                .order_by(chat_specs_table.c.updated_at.desc()),
            )
        return [self._row_to_spec(row) for row in result.fetchall()]

    async def get_chat(self, chat_id: str) -> Optional[ChatSpec]:
        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            result = await session.execute(
                select(chat_specs_table).where(
                    *self._scope(),
                    chat_specs_table.c.chat_id == chat_id,
                ),
            )
            row = result.fetchone()
        return None if row is None else self._row_to_spec(row)

    async def get_chat_by_session(
        self,
        session_id: str,
        user_id: str,
        channel: str,
    ) -> Optional[ChatSpec]:
        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            result = await session.execute(
                select(chat_specs_table).where(
                    *self._scope(),
                    chat_specs_table.c.session_id == session_id,
                    chat_specs_table.c.user_id == user_id,
                    chat_specs_table.c.channel == channel,
                ),
            )
            row = result.fetchone()
        return None if row is None else self._row_to_spec(row)

    async def upsert_chat(self, spec: ChatSpec) -> None:
        await ensure_control_store_schema(self._engine)
        values = self._spec_values(spec)
        values["tenant_id"] = self._tenant_id
        values["agent_id"] = self._agent_id

        async with self._session_factory() as session:
            existing = await session.execute(
                select(chat_specs_table.c.chat_id).where(
                    *self._scope(),
                    chat_specs_table.c.chat_id == spec.id,
                ),
            )
            if existing.scalar_one_or_none() is None:
                await session.execute(insert(chat_specs_table).values(**values))
            else:
                await session.execute(
                    update(chat_specs_table)
                    .where(
                        *self._scope(),
                        chat_specs_table.c.chat_id == spec.id,
                    )
                    .values(**values),
                )
            await session.commit()

    async def delete_chats(self, chat_ids: list[str]) -> bool:
        if not chat_ids:
            return False

        await ensure_control_store_schema(self._engine)
        async with self._session_factory() as session:
            result = await session.execute(
                delete(chat_specs_table).where(
                    *self._scope(),
                    chat_specs_table.c.chat_id.in_(chat_ids),
                ),
            )
            await session.commit()
        return bool(result.rowcount)

    async def filter_chats(
        self,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> list[ChatSpec]:
        await ensure_control_store_schema(self._engine)
        query = select(chat_specs_table).where(*self._scope())
        if user_id is not None:
            query = query.where(chat_specs_table.c.user_id == user_id)
        if channel is not None:
            query = query.where(chat_specs_table.c.channel == channel)

        async with self._session_factory() as session:
            result = await session.execute(
                query.order_by(chat_specs_table.c.updated_at.desc()),
            )
        return [self._row_to_spec(row) for row in result.fetchall()]
