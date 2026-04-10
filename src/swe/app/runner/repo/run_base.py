# -*- coding: utf-8 -*-
"""Repository interface for durable chat run records."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..run_models import ChatRunRecord, ChatRunStatus


class BaseChatRunRepository(ABC):
    """Abstract repository for durable chat run facts."""

    @abstractmethod
    async def create_run(self, record: ChatRunRecord) -> ChatRunRecord:
        raise NotImplementedError

    @abstractmethod
    async def finish_run(
        self,
        run_id: str,
        *,
        status: ChatRunStatus,
        error: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_runs(
        self,
        chat_id: str,
        *,
        limit: int,
    ) -> list[ChatRunRecord]:
        raise NotImplementedError
