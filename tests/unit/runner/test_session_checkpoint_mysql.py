from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from swe.app.runner.session_models import (
    SessionCheckpointConflictError,
    SessionCheckpointKey,
    SessionCheckpointRecord,
)


@pytest.mark.asyncio
async def test_first_write_returns_version_one(monkeypatch):
    from swe.app.runner.repo.session_checkpoint_mysql import (
        MySQLSessionCheckpointRepository,
    )

    repo = MySQLSessionCheckpointRepository(engine=object(), agent_id="agent-1")
    key = SessionCheckpointKey(
        tenant_id="tenant-a",
        user_id="user-1",
        session_id="console:user-1",
    )

    monkeypatch.setattr(repo, "_fetch_latest_row", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "_insert_first_row", AsyncMock(return_value=1))

    record = await repo.write_checkpoint(
        key=key,
        expected_version=None,
        blob_path="/tmp/blob.v1.json",
        payload_sha256="b" * 64,
    )

    assert record == SessionCheckpointRecord(
        key=key,
        version=1,
        blob_path="/tmp/blob.v1.json",
        payload_sha256="b" * 64,
    )


@pytest.mark.asyncio
async def test_stale_writer_raises_conflict_with_actual_version(monkeypatch):
    from swe.app.runner.repo.session_checkpoint_mysql import (
        MySQLSessionCheckpointRepository,
    )

    repo = MySQLSessionCheckpointRepository(engine=object(), agent_id="agent-1")
    key = SessionCheckpointKey(
        tenant_id="tenant-a",
        user_id="user-1",
        session_id="console:user-1",
    )
    current_row = {
        "tenant_id": "tenant-a",
        "user_id": "user-1",
        "session_id": "console:user-1",
        "version": 3,
        "blob_path": "/tmp/blob.v3.json",
        "payload_sha256": "c" * 64,
    }

    monkeypatch.setattr(
        repo,
        "_fetch_latest_row",
        AsyncMock(return_value=current_row),
    )

    with pytest.raises(SessionCheckpointConflictError) as exc_info:
        await repo.write_checkpoint(
            key=key,
            expected_version=2,
            blob_path="/tmp/blob.v4.json",
            payload_sha256="d" * 64,
        )

    assert exc_info.value.actual_version == 3


@pytest.mark.asyncio
async def test_get_latest_returns_record_from_row(monkeypatch):
    from swe.app.runner.repo.session_checkpoint_mysql import (
        MySQLSessionCheckpointRepository,
    )

    repo = MySQLSessionCheckpointRepository(engine=object(), agent_id="agent-1")
    key = SessionCheckpointKey(
        tenant_id="tenant-a",
        user_id="user-1",
        session_id="console:user-1",
    )
    monkeypatch.setattr(
        repo,
        "_fetch_latest_row",
        AsyncMock(
            return_value={
                "tenant_id": "tenant-a",
                "user_id": "user-1",
                "session_id": "console:user-1",
                "version": 5,
                "blob_path": "/tmp/blob.v5.json",
                "payload_sha256": "e" * 64,
            },
        ),
    )

    record = await repo.get_latest(key)

    assert record == SessionCheckpointRecord(
        key=key,
        version=5,
        blob_path="/tmp/blob.v5.json",
        payload_sha256="e" * 64,
    )
