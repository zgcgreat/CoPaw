# -*- coding: utf-8 -*-
"""Chat repository for storing chat/session specs."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import ChatSpec
from ...channels.schema import DEFAULT_CHANNEL


class BaseChatRepository(ABC):
    """Abstract repository for chat specs persistence."""

    @abstractmethod
    async def list_chats(self) -> list[ChatSpec]:
        raise NotImplementedError

    @abstractmethod
    async def get_chat(self, chat_id: str) -> Optional[ChatSpec]:
        raise NotImplementedError

    @abstractmethod
    async def get_chat_by_session(
        self,
        session_id: str,
        user_id: str,
        channel: str = DEFAULT_CHANNEL,
    ) -> Optional[ChatSpec]:
        raise NotImplementedError

    @abstractmethod
    async def upsert_chat(self, spec: ChatSpec) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_chats(self, chat_ids: list[str]) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def filter_chats(
        self,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> list[ChatSpec]:
        raise NotImplementedError

    async def get_chat_by_id(
        self,
        session_id: str,
        user_id: str,
        channel: str = DEFAULT_CHANNEL,
    ) -> Optional[ChatSpec]:
        """Backward-compatible alias for older call sites."""
        return await self.get_chat_by_session(
            session_id,
            user_id,
            channel,
        )
