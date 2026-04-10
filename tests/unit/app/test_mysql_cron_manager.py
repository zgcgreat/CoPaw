from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.crons.manager import HEARTBEAT_JOB_ID, CronManager
from swe.config.config import HeartbeatConfig


class _HeartbeatRepo:
    def __init__(self, config: HeartbeatConfig | None = None):
        self.config = config or HeartbeatConfig()
        self.saved: list[HeartbeatConfig] = []

    async def get(self) -> HeartbeatConfig:
        return self.config.model_copy(deep=True)

    async def set(self, config: HeartbeatConfig) -> HeartbeatConfig:
        self.config = config.model_copy(deep=True)
        self.saved.append(self.config.model_copy(deep=True))
        return self.config.model_copy(deep=True)


class _Scheduler:
    def __init__(self):
        self.jobs: dict[str, object] = {}
        self.paused: list[str] = []
        self.resumed: list[str] = []

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def add_job(self, func, trigger, id, replace_existing=False, args=None, misfire_grace_time=None):  # pylint: disable=too-many-arguments,redefined-builtin
        self.jobs[id] = SimpleNamespace(next_run_time=None)

    def remove_job(self, job_id: str):
        self.jobs.pop(job_id, None)

    def pause_job(self, job_id: str):
        self.paused.append(job_id)

    def resume_job(self, job_id: str):
        self.resumed.append(job_id)


@pytest.mark.asyncio
async def test_pause_and_resume_persist_enabled_flag():
    repo = AsyncMock()
    repo.get_job.side_effect = [
        SimpleNamespace(enabled=True, model_copy=lambda update: SimpleNamespace(**update)),
        SimpleNamespace(enabled=False, model_copy=lambda update: SimpleNamespace(**update)),
    ]
    heartbeat_repo = _HeartbeatRepo()
    manager = CronManager(
        repo=repo,
        heartbeat_repo=heartbeat_repo,
        runner=object(),
        channel_manager=object(),
    )
    manager._scheduler = _Scheduler()
    manager._started = True
    manager._scheduler.jobs["job-1"] = object()

    assert await manager.pause_job("job-1") is True
    assert await manager.resume_job("job-1") is True
    assert repo.upsert_job.await_count == 2
    assert manager._scheduler.paused == ["job-1"]
    assert manager._scheduler.resumed == ["job-1"]


@pytest.mark.asyncio
async def test_update_heartbeat_config_persists_reloads_and_publishes():
    heartbeat_repo = _HeartbeatRepo()
    manager = CronManager(
        repo=AsyncMock(),
        heartbeat_repo=heartbeat_repo,
        runner=object(),
        channel_manager=object(),
        agent_id="agent-1",
    )
    manager._scheduler = _Scheduler()
    manager._started = True
    manager._coordination = SimpleNamespace(publish_reload=AsyncMock())

    saved = await manager.update_heartbeat_config(
        HeartbeatConfig(enabled=True, every="15m", target="last"),
    )

    assert saved == HeartbeatConfig(
        enabled=True,
        every="15m",
        target="last",
    )
    assert HEARTBEAT_JOB_ID in manager._scheduler.jobs
    manager._coordination.publish_reload.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_callback_uses_durable_repo_config(monkeypatch):
    heartbeat_repo = _HeartbeatRepo(
        HeartbeatConfig(enabled=True, every="15m", target="last"),
    )
    runner = SimpleNamespace(workspace_dir="/tmp/ws", _workspace=None)
    manager = CronManager(
        repo=AsyncMock(),
        heartbeat_repo=heartbeat_repo,
        runner=runner,
        channel_manager=object(),
        agent_id="agent-1",
    )
    called = {}

    async def _run_once(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(
        "swe.app.crons.manager.run_heartbeat_once",
        _run_once,
    )

    await manager._heartbeat_callback()

    assert called["heartbeat_config"] == HeartbeatConfig(
        enabled=True,
        every="15m",
        target="last",
    )
