from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.runner.session import SafeJSONSession
from swe.app.runner.session_models import (
    SessionCheckpointConflictError,
    SessionCheckpointKey,
    SessionCheckpointRecord,
)


class _StateModule:
    def __init__(self, state=None):
        self._state = state or {}

    def state_dict(self):
        return self._state

    def load_state_dict(self, state):
        self._state = state


class _CheckpointRepo:
    def __init__(self):
        self.records = {}

    async def get_latest(self, key: SessionCheckpointKey):
        return self.records.get(key)

    async def write_checkpoint(
        self,
        *,
        key: SessionCheckpointKey,
        expected_version: int | None,
        blob_path: str,
        payload_sha256: str,
    ):
        current = self.records.get(key)
        actual_version = current.version if current else None
        if actual_version != expected_version:
            raise SessionCheckpointConflictError(
                key=key,
                expected_version=expected_version,
                actual_version=actual_version,
            )
        version = 1 if current is None else current.version + 1
        record = SessionCheckpointRecord(
            key=key,
            version=version,
            blob_path=blob_path,
            payload_sha256=payload_sha256,
        )
        self.records[key] = record
        return record


class _FailingRepo(_CheckpointRepo):
    async def write_checkpoint(self, **kwargs):
        raise RuntimeError("metadata write failed")


@pytest.mark.asyncio
async def test_session_uses_metadata_driven_latest_checkpoint(tmp_path):
    repo = _CheckpointRepo()
    session_a = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )
    session_b = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )

    await session_a.save_session_state(
        "console:user-1",
        user_id="user-1",
        agent=_StateModule({"memory": {"messages": ["hello"]}}),
    )

    state = await session_b.get_session_state_dict(
        "console:user-1",
        user_id="user-1",
    )

    assert state == {"agent": {"memory": {"messages": ["hello"]}}}
    blobs = sorted(tmp_path.glob("*.json"))
    assert [path.name for path in blobs] == ["user-1_console--user-1.v1.json"]


@pytest.mark.asyncio
async def test_stale_writer_conflict_does_not_overwrite_newer_checkpoint(
    tmp_path,
):
    repo = _CheckpointRepo()
    session_a = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )
    session_b = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )

    await session_a.get_session_state_dict("console:user-1", user_id="user-1")
    await session_b.get_session_state_dict("console:user-1", user_id="user-1")

    await session_a.save_session_state(
        "console:user-1",
        user_id="user-1",
        agent=_StateModule({"memory": {"messages": ["first"]}}),
    )

    with pytest.raises(SessionCheckpointConflictError):
        await session_b.save_session_state(
            "console:user-1",
            user_id="user-1",
            agent=_StateModule({"memory": {"messages": ["stale"]}}),
        )

    state = await session_a.get_session_state_dict(
        "console:user-1",
        user_id="user-1",
    )
    assert state == {"agent": {"memory": {"messages": ["first"]}}}


@pytest.mark.asyncio
async def test_failed_metadata_write_cleans_up_orphaned_blob(tmp_path):
    session = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=_FailingRepo(),
    )

    with pytest.raises(RuntimeError, match="metadata write failed"):
        await session.save_session_state(
            "console:user-1",
            user_id="user-1",
            agent=_StateModule({"memory": {"messages": ["boom"]}}),
        )

    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.asyncio
async def test_legacy_session_file_is_imported_on_first_read(tmp_path):
    repo = _CheckpointRepo()
    session = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )
    legacy_path = tmp_path / "user-1_console--user-1.json"
    legacy_payload = {"agent": {"memory": {"messages": ["legacy"]}}}
    legacy_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    state = await session.get_session_state_dict(
        "console:user-1",
        user_id="user-1",
    )

    assert state == legacy_payload
    blobs = sorted(tmp_path.glob("*.json"))
    assert [path.name for path in blobs] == [
        "user-1_console--user-1.json",
        "user-1_console--user-1.v1.json",
    ]
    record = await repo.get_latest(
        SessionCheckpointKey(
            tenant_id="tenant-a",
            user_id="user-1",
            session_id="console:user-1",
        ),
    )
    assert record is not None
    assert Path(record.blob_path).name == "user-1_console--user-1.v1.json"


@pytest.mark.asyncio
async def test_legacy_import_reuses_existing_blob_created_by_other_instance(
    tmp_path,
):
    repo = _CheckpointRepo()
    session = SafeJSONSession(
        save_dir=str(tmp_path),
        tenant_id="tenant-a",
        checkpoint_repo=repo,
    )
    legacy_payload = {"agent": {"memory": {"messages": ["legacy"]}}}
    legacy_path = tmp_path / "user-1_console--user-1.json"
    blob_path = tmp_path / "user-1_console--user-1.v1.json"
    legacy_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    blob_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    state = await session.get_session_state_dict(
        "console:user-1",
        user_id="user-1",
    )

    assert state == legacy_payload
    record = await repo.get_latest(
        SessionCheckpointKey(
            tenant_id="tenant-a",
            user_id="user-1",
            session_id="console:user-1",
        ),
    )
    assert record is not None
    assert Path(record.blob_path) == blob_path
