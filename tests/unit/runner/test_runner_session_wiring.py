from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.app.runner.runner import AgentRunner


@pytest.mark.asyncio
async def test_runner_init_handler_injects_tenant_and_checkpoint_repo(
    monkeypatch,
    tmp_path,
):
    created = {}

    class FakeSession:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr(
        "swe.app.runner.runner.SafeJSONSession",
        FakeSession,
    )

    runner = AgentRunner(
        agent_id="agent-1",
        tenant_id="tenant-a",
        workspace_dir=tmp_path,
        session_checkpoint_repo="checkpoint-repo",
    )

    await runner.init_handler()

    assert created["tenant_id"] == "tenant-a"
    assert created["checkpoint_repo"] == "checkpoint-repo"
    assert created["save_dir"] == str(tmp_path / "sessions")


@pytest.mark.asyncio
async def test_create_session_checkpoint_service_injects_runner_repo(
    monkeypatch,
    tmp_path,
):
    from swe.app.workspace.service_factories import (
        create_session_checkpoint_service,
    )

    created = {}

    class FakeRunner:
        def set_session_checkpoint_repo(self, repo):
            created["runner_repo"] = repo

    class FakeRepo:
        def __init__(self, engine, agent_id):
            created["repo_args"] = (engine, agent_id)

        async def close(self):
            return None

    async def _ensure_schema(engine):
        created["schema_engine"] = engine

    monkeypatch.setattr(
        "swe.app.workspace.service_factories.create_control_store_engine",
        lambda dsn=None: "engine",
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.ensure_control_store_schema",
        _ensure_schema,
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.MySQLSessionCheckpointRepository",
        FakeRepo,
    )

    ws = SimpleNamespace(
        agent_id="agent-1",
        tenant_id="tenant-a",
        _service_manager=SimpleNamespace(services={"runner": FakeRunner()}),
    )

    repo = await create_session_checkpoint_service(ws, None)

    assert created["schema_engine"] == "engine"
    assert created["repo_args"] == ("engine", "agent-1")
    assert created["runner_repo"] is repo
