# -*- coding: utf-8 -*-
"""Tests for Workspace class."""
import tempfile
from pathlib import Path
import pytest


@pytest.mark.asyncio
async def test_workspace_creation():
    """Test workspace instance creation."""
    from swe.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == "test123"
        assert workspace.workspace_dir == workspace_dir
        assert workspace_dir.exists()
        assert not workspace._started  # pylint: disable=W0212


@pytest.mark.asyncio
async def test_workspace_components_none_before_start():
    """Test that workspace components are None before start()."""
    from swe.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.runner is None
        assert workspace.channel_manager is None
        assert workspace.memory_manager is None
        assert workspace.mcp_manager is None
        assert workspace.cron_manager is None
        assert workspace.chat_manager is None


@pytest.mark.asyncio
async def test_workspace_default_agent():
    """Test workspace with 'default' agent ID."""
    from swe.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "default"
        workspace = Workspace(
            agent_id="default",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == "default"
        assert workspace.workspace_dir.name == "default"


@pytest.mark.asyncio
async def test_workspace_short_uuid_agent():
    """Test workspace with short UUID agent ID."""
    from swe.app.workspace import Workspace
    from swe.config.config import generate_short_agent_id

    short_id = generate_short_agent_id()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / short_id
        workspace = Workspace(
            agent_id=short_id,
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == short_id
        assert len(workspace.agent_id) == 6
        assert workspace.workspace_dir.name == short_id


def test_workspace_repr():
    """Test workspace string representation."""
    from swe.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        repr_str = repr(workspace)
        assert "test123" in repr_str
        assert "stopped" in repr_str
        assert "Workspace" in repr_str


@pytest.mark.asyncio
async def test_create_cron_service_uses_mysql_storage_and_importer(
    monkeypatch,
    tmp_path,
):
    from types import SimpleNamespace

    from swe.app.workspace.service_factories import create_cron_service

    created = {}

    class FakeRunner:
        workspace_dir = tmp_path

    class FakeStore:
        def __init__(self, settings):
            created["settings"] = settings

        async def ensure_schema(self):
            created["schema"] = True

    class FakeJobRepo:
        def __init__(self, store, scope):
            created["job_scope"] = scope

    class FakeHeartbeatRepo:
        def __init__(self, store, scope):
            created["heartbeat_scope"] = scope

    class FakeImporter:
        def __init__(self, *, primary_repo, heartbeat_repo, legacy_repo):
            created["legacy_repo"] = legacy_repo

        async def import_if_needed(self, *, legacy_heartbeat=None):
            created["legacy_heartbeat"] = legacy_heartbeat

    class FakeCronManager:
        def __init__(self, **kwargs):
            created["manager_kwargs"] = kwargs

    monkeypatch.setattr(
        "swe.app.workspace.service_factories.CronMySQLSettings.from_env",
        classmethod(lambda cls: SimpleNamespace(database="cron")),
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.MySQLCronStore",
        FakeStore,
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.MysqlJobRepository",
        FakeJobRepo,
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.MysqlHeartbeatRepository",
        FakeHeartbeatRepo,
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.CronStorageImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "swe.app.workspace.service_factories.CronManager",
        FakeCronManager,
    )

    class FakeWorkspace:
        agent_id = "agent-1"
        tenant_id = "tenant-a"
        workspace_dir = tmp_path
        _config = SimpleNamespace(heartbeat="legacy-heartbeat")
        _service_manager = SimpleNamespace(
            services={
                "runner": FakeRunner(),
                "channel_manager": object(),
            },
        )

        def _get_cron_coordination_config(self):
            return "coordination-config"

    await create_cron_service(FakeWorkspace(), None)

    assert created["schema"] is True
    assert created["job_scope"].tenant_id == "tenant-a"
    assert created["job_scope"].agent_id == "agent-1"
    assert created["heartbeat_scope"] == created["job_scope"]
    assert created["legacy_heartbeat"] == "legacy-heartbeat"
    assert created["manager_kwargs"]["coordination_config"] == (
        "coordination-config"
    )
