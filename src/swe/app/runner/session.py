# -*- coding: utf-8 -*-
"""Safe JSON session with authoritative checkpoint metadata."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Sequence, Union

import aiofiles
from agentscope.session import SessionBase

from .session_models import (
    SessionCheckpointConflictError,
    SessionCheckpointKey,
)

logger = logging.getLogger(__name__)


# Characters forbidden in Windows filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    """Replace characters that are illegal in Windows filenames with ``--``.

    >>> sanitize_filename('discord:dm:12345')
    'discord--dm--12345'
    >>> sanitize_filename('normal-name')
    'normal-name'
    """
    return _UNSAFE_FILENAME_RE.sub("--", name)


class SafeJSONSession(SessionBase):
    """SessionBase subclass with optional checkpoint-metadata coordination."""

    def __init__(
        self,
        save_dir: str = "./",
        tenant_id: str | None = None,
        checkpoint_repo=None,
    ) -> None:
        self.save_dir = save_dir
        self.tenant_id = tenant_id or "default"
        self._checkpoint_repo = checkpoint_repo
        self._cached_versions: dict[SessionCheckpointKey, int | None] = {}

    def _get_save_path(self, session_id: str, user_id: str) -> str:
        os.makedirs(self.save_dir, exist_ok=True)
        safe_sid = sanitize_filename(session_id)
        safe_uid = sanitize_filename(user_id) if user_id else ""
        if safe_uid:
            file_path = f"{safe_uid}_{safe_sid}.json"
        else:
            file_path = f"{safe_sid}.json"
        return os.path.join(self.save_dir, file_path)

    def _get_checkpoint_path(
        self,
        session_id: str,
        user_id: str,
        version: int,
    ) -> str:
        base = Path(self._get_save_path(session_id, user_id=user_id))
        return str(base.with_suffix(f".v{version}.json"))

    def _get_checkpoint_key(
        self,
        session_id: str,
        user_id: str,
    ) -> SessionCheckpointKey:
        return SessionCheckpointKey(
            tenant_id=self.tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def _read_json_file(self, path: str) -> dict:
        async with aiofiles.open(
            path,
            "r",
            encoding="utf-8",
            errors="surrogatepass",
        ) as file:
            return json.loads(await file.read())

    async def _write_json_file(
        self,
        path: str,
        payload_text: str,
        *,
        mode: str = "w",
    ) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(
            path,
            mode,
            encoding="utf-8",
            errors="surrogatepass",
        ) as file:
            await file.write(payload_text)

    async def _delete_file(self, path: str) -> None:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            return

    async def _legacy_get_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        if os.path.exists(session_save_path):
            states = await self._read_json_file(session_save_path)
            logger.info(
                "Get session state dict from %s successfully.",
                session_save_path,
            )
            return states

        if allow_not_exist:
            logger.info(
                "Session file %s does not exist. Return empty state dict.",
                session_save_path,
            )
            return {}

        raise ValueError(
            f"Failed to get session state for file {session_save_path} "
            "because it does not exist.",
        )

    async def _save_state_payload(
        self,
        session_id: str,
        user_id: str,
        state_dicts: dict,
    ) -> None:
        if self._checkpoint_repo is None:
            session_save_path = self._get_save_path(session_id, user_id=user_id)
            await self._write_json_file(
                session_save_path,
                json.dumps(state_dicts, ensure_ascii=False),
            )
            logger.info(
                "Saved session state to %s successfully.",
                session_save_path,
            )
            return

        key = self._get_checkpoint_key(session_id, user_id)
        if key in self._cached_versions:
            expected_version = self._cached_versions[key]
        else:
            latest = await self._checkpoint_repo.get_latest(key)
            expected_version = latest.version if latest is not None else None
            self._cached_versions[key] = expected_version

        next_version = 1 if expected_version is None else expected_version + 1
        blob_path = self._get_checkpoint_path(
            session_id,
            user_id,
            next_version,
        )
        payload_text = json.dumps(state_dicts, ensure_ascii=False)
        try:
            await self._write_json_file(
                blob_path,
                payload_text,
                mode="x",
            )
        except FileExistsError as exc:
            latest = await self._checkpoint_repo.get_latest(key)
            raise SessionCheckpointConflictError(
                key=key,
                expected_version=expected_version,
                actual_version=(
                    latest.version if latest is not None else expected_version
                ),
            ) from exc
        payload_sha256 = hashlib.sha256(
            payload_text.encode("utf-8", errors="surrogatepass"),
        ).hexdigest()

        try:
            record = await self._checkpoint_repo.write_checkpoint(
                key=key,
                expected_version=expected_version,
                blob_path=blob_path,
                payload_sha256=payload_sha256,
            )
        except Exception:
            await self._delete_file(blob_path)
            raise

        self._cached_versions[key] = record.version
        logger.info("Saved session checkpoint to %s successfully.", blob_path)

    async def _import_legacy_session(
        self,
        session_id: str,
        user_id: str,
        legacy_path: str,
    ) -> dict:
        states = await self._read_json_file(legacy_path)
        key = self._get_checkpoint_key(session_id, user_id)
        blob_path = self._get_checkpoint_path(session_id, user_id, 1)
        payload_text = json.dumps(states, ensure_ascii=False)
        payload_sha256 = hashlib.sha256(
            payload_text.encode("utf-8", errors="surrogatepass"),
        ).hexdigest()
        try:
            await self._write_json_file(blob_path, payload_text, mode="x")
        except FileExistsError:
            latest = await self._checkpoint_repo.get_latest(key)
            if latest is not None:
                self._cached_versions[key] = latest.version
                return await self._read_json_file(latest.blob_path)

        try:
            record = await self._checkpoint_repo.write_checkpoint(
                key=key,
                expected_version=None,
                blob_path=blob_path,
                payload_sha256=payload_sha256,
            )
        except SessionCheckpointConflictError:
            latest = await self._checkpoint_repo.get_latest(key)
            if latest is None:
                raise
            self._cached_versions[key] = latest.version
            return await self._read_json_file(latest.blob_path)
        except Exception:
            await self._delete_file(blob_path)
            raise

        self._cached_versions[key] = record.version
        logger.info(
            "Imported legacy session file %s into checkpoint %s.",
            legacy_path,
            blob_path,
        )
        return states

    async def save_session_state(
        self,
        session_id: str,
        user_id: str = "",
        **state_modules_mapping,
    ) -> None:
        state_dicts = {
            name: state_module.state_dict()
            for name, state_module in state_modules_mapping.items()
        }
        await self._save_state_payload(session_id, user_id, state_dicts)

    async def load_session_state(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
        **state_modules_mapping,
    ) -> None:
        states = await self.get_session_state_dict(
            session_id,
            user_id=user_id,
            allow_not_exist=allow_not_exist,
        )
        for name, state_module in state_modules_mapping.items():
            if name in states:
                state_module.load_state_dict(states[name])

    async def update_session_state(
        self,
        session_id: str,
        key: Union[str, Sequence[str]],
        value,
        user_id: str = "",
        create_if_not_exist: bool = True,
    ) -> None:
        states = await self.get_session_state_dict(
            session_id,
            user_id=user_id,
            allow_not_exist=create_if_not_exist,
        )

        path = key.split(".") if isinstance(key, str) else list(key)
        if not path:
            raise ValueError("key path is empty")

        cur = states
        for k in path[:-1]:
            if k not in cur or not isinstance(cur[k], dict):
                cur[k] = {}
            cur = cur[k]

        cur[path[-1]] = value

        await self._save_state_payload(session_id, user_id, states)
        logger.info("Updated session state key '%s' successfully.", key)

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        if self._checkpoint_repo is None:
            return await self._legacy_get_state_dict(
                session_id,
                user_id=user_id,
                allow_not_exist=allow_not_exist,
            )

        key = self._get_checkpoint_key(session_id, user_id)
        record = await self._checkpoint_repo.get_latest(key)
        if record is not None:
            self._cached_versions[key] = record.version
            return await self._read_json_file(record.blob_path)

        legacy_path = self._get_save_path(session_id, user_id=user_id)
        if os.path.exists(legacy_path):
            return await self._import_legacy_session(
                session_id,
                user_id,
                legacy_path,
            )

        self._cached_versions[key] = None
        if allow_not_exist:
            return {}

        raise ValueError(
            f"Failed to get session state for file {legacy_path} "
            "because it does not exist.",
        )
