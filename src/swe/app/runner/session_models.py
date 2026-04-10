# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionCheckpointKey:
    tenant_id: str
    user_id: str
    session_id: str


@dataclass(frozen=True)
class SessionCheckpointRecord:
    key: SessionCheckpointKey
    version: int
    blob_path: str
    payload_sha256: str


class SessionCheckpointConflictError(RuntimeError):
    def __init__(
        self,
        *,
        key: SessionCheckpointKey,
        expected_version: int | None,
        actual_version: int | None,
    ) -> None:
        self.key = key
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            "Session checkpoint conflict for "
            f"{key.tenant_id}/{key.user_id}/{key.session_id}: "
            f"expected={expected_version}, actual={actual_version}",
        )
