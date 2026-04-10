from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_create_chat_service_uses_migrating_mysql_repo(
    monkeypatch,
    tmp_path,
):
    from swe.app.workspace.service_factories import create_chat_service

    created = {}

    class FakeRunner:
        def set_chat_manager(self, manager):
            created["manager"] = manager

    class FakeTracker:
        def bind_chat_manager(self, manager):
            created["bound"] = manager

    class FakeWorkspace:
        agent_id = "agent-1"
        tenant_id = "tenant-a"
        workspace_dir = tmp_path
        _config = object()
        _task_tracker = FakeTracker()
        _service_manager = SimpleNamespace(
            services={"runner": FakeRunner()},
        )

    from swe.app.persistence import mysql as mysql_persistence

    engine = mysql_persistence.create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    monkeypatch.setattr(
        mysql_persistence,
        "create_control_store_engine",
        lambda dsn=None: engine,
    )

    await create_chat_service(FakeWorkspace(), None)

    assert created["manager"].__class__.__name__ == "ChatManager"
    assert created["manager"]._repo.__class__.__name__ == (
        "MigratingChatRepository"
    )
    assert created["bound"] is created["manager"]
