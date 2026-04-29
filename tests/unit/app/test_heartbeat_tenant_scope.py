# -*- coding: utf-8 -*-
"""Regression tests for tenant-aware heartbeat config access."""

# pylint: disable=protected-access
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.crons import heartbeat as heartbeat_module
from swe.app.crons.heartbeat import run_heartbeat_once
from swe.app.crons.manager import CronManager
from swe.config import config as config_module
from swe.config import utils as config_utils
from swe.config.llm_workload import (
    LLM_WORKLOAD_CHAT,
    LLM_WORKLOAD_CRON,
    bind_llm_workload,
    get_current_llm_workload,
)


@pytest.mark.asyncio
async def test_run_heartbeat_once_uses_longer_default_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "HEARTBEAT.md").write_text("ping", encoding="utf-8")

    class FakeRunner:
        async def stream_query(self, request):
            observed["request"] = request
            observed["workload"] = get_current_llm_workload()
            yield {"type": "message", "text": "pong"}

    class FakeChannelManager:
        async def send_event(self, **kwargs) -> None:
            observed["dispatch"] = kwargs

    async def fake_wait_for(awaitable, timeout):
        observed["timeout"] = timeout
        return await awaitable

    monkeypatch.setattr(heartbeat_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        heartbeat_module,
        "get_heartbeat_config",
        lambda agent_id=None, *, tenant_id=None: SimpleNamespace(
            active_hours=None,
            target="main",
        ),
    )

    await run_heartbeat_once(
        runner=FakeRunner(),
        channel_manager=FakeChannelManager(),
        agent_id="default",
        tenant_id="tenant-a",
        workspace_dir=workspace_dir,
    )

    assert observed["timeout"] == 7200
    assert observed["workload"] == LLM_WORKLOAD_CRON
    assert get_current_llm_workload() == LLM_WORKLOAD_CHAT


def test_get_heartbeat_config_uses_tenant_scoped_agent_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, str | None] = {}

    def fake_load_agent_config(
        agent_id: str,
        config_path=None,
        *,
        tenant_id: str | None = None,
    ) -> SimpleNamespace:
        del config_path
        observed["agent_id"] = agent_id
        observed["tenant_id"] = tenant_id
        return SimpleNamespace(
            heartbeat=SimpleNamespace(enabled=True, every="5m"),
        )

    monkeypatch.setattr(
        config_utils,
        "load_agent_config",
        fake_load_agent_config,
    )

    hb = config_utils.get_heartbeat_config(
        "default",
        tenant_id="tenant-a",
    )

    assert observed == {
        "agent_id": "default",
        "tenant_id": "tenant-a",
    }
    assert hb.enabled is True
    assert hb.every == "5m"


def test_update_last_dispatch_saves_tenant_scoped_agent_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}
    agent_config = SimpleNamespace(last_dispatch=None)

    def fake_load_agent_config(
        agent_id: str,
        config_path=None,
        *,
        tenant_id: str | None = None,
    ) -> SimpleNamespace:
        del config_path
        observed["load"] = (agent_id, tenant_id)
        return agent_config

    def fake_save_agent_config(
        agent_id: str,
        config,
        config_path=None,
        *,
        tenant_id: str | None = None,
    ) -> None:
        del config_path
        observed["save"] = (agent_id, tenant_id, config.last_dispatch)

    monkeypatch.setattr(
        config_utils,
        "load_agent_config",
        fake_load_agent_config,
    )
    monkeypatch.setattr(
        config_utils,
        "save_agent_config",
        fake_save_agent_config,
    )

    config_utils.update_last_dispatch(
        channel="console",
        user_id="user-a",
        session_id="session-a",
        agent_id="default",
        tenant_id="tenant-a",
    )

    assert observed["load"] == ("default", "tenant-a")
    saved_agent_id, saved_tenant_id, last_dispatch = observed["save"]
    assert saved_agent_id == "default"
    assert saved_tenant_id == "tenant-a"
    assert last_dispatch.channel == "console"
    assert last_dispatch.user_id == "user-a"
    assert last_dispatch.session_id == "session-a"


@pytest.mark.asyncio
async def test_cron_manager_update_heartbeat_uses_runtime_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    def fake_get_heartbeat_config(
        agent_id: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> SimpleNamespace:
        observed["heartbeat_lookup"] = (agent_id, tenant_id)
        return SimpleNamespace(enabled=True, every="5m")

    class FakeScheduler:
        def get_job(self, job_id: str):
            observed["get_job"] = job_id

        def add_job(self, callback, trigger, **kwargs):
            observed["add_job"] = (
                callback,
                trigger,
                kwargs["id"],
                kwargs["replace_existing"],
            )

    manager = CronManager(
        repo=object(),
        runner=object(),
        channel_manager=object(),
        agent_id="default",
        tenant_id="tenant-a",
    )
    manager._scheduler = FakeScheduler()
    monkeypatch.setattr(
        manager,
        "_build_heartbeat_trigger",
        lambda every: f"trigger:{every}",
    )

    monkeypatch.setattr(
        "swe.config.utils.get_heartbeat_config",
        fake_get_heartbeat_config,
    )

    await manager._update_heartbeat()  # pylint: disable=protected-access

    assert observed["heartbeat_lookup"] == ("default", "tenant-a")
    assert observed["get_job"] == "_heartbeat"
    assert observed["add_job"][1:] == (
        "trigger:5m",
        "_heartbeat",
        True,
    )


@pytest.mark.asyncio
async def test_cron_manager_heartbeat_callback_binds_cron_workload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}
    manager = CronManager(
        repo=object(),
        runner=SimpleNamespace(workspace_dir=None, _workspace=None),
        channel_manager=object(),
        agent_id="default",
        tenant_id="tenant-a",
    )

    async def fake_run_heartbeat_once(workspace_dir: Any) -> None:
        del workspace_dir
        observed["workload"] = get_current_llm_workload()

    monkeypatch.setattr(
        manager,
        "_run_heartbeat_once",
        fake_run_heartbeat_once,
    )

    with bind_llm_workload(LLM_WORKLOAD_CHAT):
        await manager._heartbeat_callback()  # pylint: disable=protected-access
        assert get_current_llm_workload() == LLM_WORKLOAD_CHAT

    assert observed["workload"] == LLM_WORKLOAD_CRON


@pytest.mark.asyncio
async def test_run_heartbeat_once_loads_last_dispatch_from_runtime_tenant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "HEARTBEAT.md").write_text("ping", encoding="utf-8")

    class FakeRunner:
        async def stream_query(self, request):
            observed["request"] = request
            yield {"type": "message", "text": "pong"}

    class FakeChannelManager:
        async def send_event(
            self,
            *,
            channel,
            user_id,
            session_id,
            event,
            meta,
        ) -> None:
            observed["dispatch"] = (
                channel,
                user_id,
                session_id,
                event,
                meta,
            )

    def fake_get_heartbeat_config(
        agent_id: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> SimpleNamespace:
        observed["heartbeat_lookup"] = (agent_id, tenant_id)
        return SimpleNamespace(active_hours=None, target="last")

    def fake_load_agent_config(
        agent_id: str,
        config_path=None,
        *,
        tenant_id: str | None = None,
    ) -> SimpleNamespace:
        del config_path
        observed["last_dispatch_lookup"] = (agent_id, tenant_id)
        return SimpleNamespace(
            last_dispatch=SimpleNamespace(
                channel="console",
                user_id="user-a",
                session_id="session-a",
            ),
        )

    monkeypatch.setattr(
        heartbeat_module,
        "get_heartbeat_config",
        fake_get_heartbeat_config,
    )
    monkeypatch.setattr(
        config_module,
        "load_agent_config",
        fake_load_agent_config,
    )

    await run_heartbeat_once(
        runner=FakeRunner(),
        channel_manager=FakeChannelManager(),
        agent_id="default",
        tenant_id="tenant-a",
        workspace_dir=workspace_dir,
    )

    assert observed["heartbeat_lookup"] == ("default", "tenant-a")
    assert observed["last_dispatch_lookup"] == ("default", "tenant-a")
    assert observed["dispatch"] == (
        "console",
        "user-a",
        "session-a",
        {"type": "message", "text": "pong"},
        {},
    )
