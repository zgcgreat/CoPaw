# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod

from ..session_models import SessionCheckpointKey, SessionCheckpointRecord


class BaseSessionCheckpointRepository(ABC):
    @abstractmethod
    async def get_latest(
        self,
        key: SessionCheckpointKey,
    ) -> SessionCheckpointRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def write_checkpoint(
        self,
        *,
        key: SessionCheckpointKey,
        expected_version: int | None,
        blob_path: str,
        payload_sha256: str,
    ) -> SessionCheckpointRecord:
        raise NotImplementedError

    async def close(self) -> None:
        return None
