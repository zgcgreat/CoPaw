# -*- coding: utf-8 -*-
"""JSON-based chat repository."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .base import BaseChatRepository
from ..models import ChatSpec, ChatsFile
from ...channels.schema import DEFAULT_CHANNEL


class JsonChatRepository(BaseChatRepository):
    """chats.json repository (single-file storage).

    Stores chat_id (UUID) -> session_id mappings in a JSON file.
    Similar to JsonJobRepository pattern from crons.

    Notes:
    - Single-machine, no cross-process lock.
    - Atomic write: write tmp then replace.
    """

    def __init__(self, path: Path | str):
        """Initialize JSON chat repository.

        Args:
            path: Path to chats.json file
        """
        if isinstance(path, str):
            path = Path(path)
        self._path = path.expanduser()

    @property
    def path(self) -> Path:
        """Get the repository file path."""
        return self._path

    async def load(self) -> ChatsFile:
        """Load chat specs from JSON file.

        Returns:
            ChatsFile with all chat specs
        """
        if not self._path.exists():
            return ChatsFile(version=1, chats=[])

        data = json.loads(self._path.read_text(encoding="utf-8"))
        return ChatsFile.model_validate(data)

    async def save(self, chats_file: ChatsFile) -> None:
        """Save chat specs to JSON file atomically.

        Args:
            chats_file: ChatsFile to persist
        """
        # Create parent directory if needed
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first (atomic write)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = chats_file.model_dump(mode="json")

        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Atomic replace (shutil.move handles cross-disk on Windows)
        shutil.move(str(tmp_path), str(self._path))

    async def list_chats(self) -> list[ChatSpec]:
        cf = await self.load()
        return cf.chats

    async def get_chat(self, chat_id: str) -> ChatSpec | None:
        cf = await self.load()
        for chat in cf.chats:
            if chat.id == chat_id:
                return chat
        return None

    async def get_chat_by_session(
        self,
        session_id: str,
        user_id: str,
        channel: str = DEFAULT_CHANNEL,
    ) -> ChatSpec | None:
        cf = await self.load()
        for chat in cf.chats:
            if (
                chat.session_id == session_id
                and chat.user_id == user_id
                and chat.channel == channel
            ):
                return chat
        return None

    async def upsert_chat(self, spec: ChatSpec) -> None:
        cf = await self.load()
        for i, chat in enumerate(cf.chats):
            if chat.id == spec.id:
                cf.chats[i] = spec
                break
        else:
            cf.chats.append(spec)
        await self.save(cf)

    async def delete_chats(self, chat_ids: list[str]) -> bool:
        if not chat_ids:
            return False

        cf = await self.load()
        before = len(cf.chats)
        cf.chats = [chat for chat in cf.chats if chat.id not in chat_ids]
        if len(cf.chats) == before:
            return False
        await self.save(cf)
        return True

    async def filter_chats(
        self,
        user_id: str | None = None,
        channel: str | None = None,
    ) -> list[ChatSpec]:
        results = await self.list_chats()
        if user_id is not None:
            results = [chat for chat in results if chat.user_id == user_id]
        if channel is not None:
            results = [chat for chat in results if chat.channel == channel]
        return results
