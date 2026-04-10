# -*- coding: utf-8 -*-
"""Durable run models for chat execution facts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import ChatSpec

ChatRunStatus = Literal["running", "completed", "failed", "cancelled"]


class ChatRunRecord(BaseModel):
    """Durable run record persisted independently from runtime ownership."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    chat_id: str
    status: ChatRunStatus
    session_id: str
    user_id: str
    channel: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    finished_at: datetime | None = None
    error: str | None = None


class ChatRunContext(BaseModel):
    """Minimal context needed to create a durable run record."""

    chat_id: str
    session_id: str
    user_id: str
    channel: str

    @classmethod
    def from_chat(cls, chat: ChatSpec) -> "ChatRunContext":
        return cls(
            chat_id=chat.id,
            session_id=chat.session_id,
            user_id=chat.user_id,
            channel=chat.channel,
        )
