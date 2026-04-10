# -*- coding: utf-8 -*-
"""Migration-aware repository wrapper for chat metadata."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..models import ChatSpec
from .base import BaseChatRepository

logger = logging.getLogger(__name__)


class MigratingChatRepository(BaseChatRepository):
    """Delegate to the authoritative repo after importing legacy JSON once."""

    def __init__(
        self,
        authoritative_repo: BaseChatRepository,
        *,
        import_repo: BaseChatRepository | None = None,
        parity_check: bool = False,
    ) -> None:
        self._authoritative_repo = authoritative_repo
        self._import_repo = import_repo
        self._parity_check = parity_check
        self._import_lock = asyncio.Lock()
        self._import_complete = import_repo is None
        self.path = getattr(authoritative_repo, "path", "<unknown>")

    async def _maybe_check_parity(self) -> None:
        if not self._parity_check or self._import_repo is None:
            return

        primary_ids = {
            chat.id for chat in await self._authoritative_repo.list_chats()
        }
        fallback_ids = {chat.id for chat in await self._import_repo.list_chats()}
        if primary_ids != fallback_ids:
            logger.warning(
                "chat repository parity mismatch primary_only=%s fallback_only=%s",
                sorted(primary_ids - fallback_ids),
                sorted(fallback_ids - primary_ids),
            )

    async def _ensure_imported(self) -> None:
        if self._import_complete:
            await self._maybe_check_parity()
            return

        async with self._import_lock:
            if self._import_complete:
                await self._maybe_check_parity()
                return

            assert self._import_repo is not None
            if await self._authoritative_repo.list_chats():
                self._import_complete = True
                await self._maybe_check_parity()
                return

            for chat in await self._import_repo.list_chats():
                await self._authoritative_repo.upsert_chat(chat)
            self._import_complete = True

        await self._maybe_check_parity()

    async def list_chats(self) -> list[ChatSpec]:
        await self._ensure_imported()
        return await self._authoritative_repo.list_chats()

    async def get_chat(self, chat_id: str) -> Optional[ChatSpec]:
        await self._ensure_imported()
        return await self._authoritative_repo.get_chat(chat_id)

    async def get_chat_by_session(
        self,
        session_id: str,
        user_id: str,
        channel: str,
    ) -> Optional[ChatSpec]:
        await self._ensure_imported()
        return await self._authoritative_repo.get_chat_by_session(
            session_id,
            user_id,
            channel,
        )

    async def upsert_chat(self, spec: ChatSpec) -> None:
        await self._ensure_imported()
        await self._authoritative_repo.upsert_chat(spec)

    async def delete_chats(self, chat_ids: list[str]) -> bool:
        await self._ensure_imported()
        return await self._authoritative_repo.delete_chats(chat_ids)

    async def filter_chats(
        self,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> list[ChatSpec]:
        await self._ensure_imported()
        return await self._authoritative_repo.filter_chats(
            user_id=user_id,
            channel=channel,
        )
