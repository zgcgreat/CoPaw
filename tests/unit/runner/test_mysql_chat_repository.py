import asyncio

import pytest

from swe.app.runner.models import ChatSpec


@pytest.mark.asyncio
async def test_mysql_repo_is_scoped_by_tenant_and_agent(tmp_path):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    repo_a = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")
    repo_b = MysqlChatRepository(engine, tenant_id="tenant-b", agent_id="a1")

    await repo_a.upsert_chat(
        ChatSpec(
            id="chat-a",
            name="Tenant A",
            session_id="console:alice",
            user_id="alice",
            channel="console",
        ),
    )

    assert await repo_a.get_chat("chat-a") is not None
    assert await repo_b.get_chat("chat-a") is None


@pytest.mark.asyncio
async def test_mysql_repo_keeps_concurrent_creates_from_two_instances(
    tmp_path,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    repo_a = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")
    repo_b = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")

    await asyncio.gather(
        repo_a.upsert_chat(
            ChatSpec(
                id="chat-1",
                name="One",
                session_id="console:one",
                user_id="one",
                channel="console",
            ),
        ),
        repo_b.upsert_chat(
            ChatSpec(
                id="chat-2",
                name="Two",
                session_id="console:two",
                user_id="two",
                channel="console",
            ),
        ),
    )

    chats = await repo_a.list_chats()
    assert {chat.id for chat in chats} == {"chat-1", "chat-2"}


@pytest.mark.asyncio
async def test_chat_manager_get_or_create_is_idempotent_across_instances(
    tmp_path,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.manager import ChatManager
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    manager_a = ChatManager(
        repo=MysqlChatRepository(
            engine,
            tenant_id="tenant-a",
            agent_id="a1",
        ),
    )
    manager_b = ChatManager(
        repo=MysqlChatRepository(
            engine,
            tenant_id="tenant-a",
            agent_id="a1",
        ),
    )

    chat_a, chat_b = await asyncio.gather(
        manager_a.get_or_create_chat(
            session_id="console:alice",
            user_id="alice",
            channel="console",
            name="Alice Chat",
        ),
        manager_b.get_or_create_chat(
            session_id="console:alice",
            user_id="alice",
            channel="console",
            name="Alice Chat",
        ),
    )

    chats = await manager_a.list_chats(user_id="alice", channel="console")

    assert chat_a.id == chat_b.id
    assert [chat.id for chat in chats] == [chat_a.id]


@pytest.mark.asyncio
async def test_migrating_repo_imports_legacy_json_when_primary_is_empty(
    tmp_path,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.repo.json_repo import JsonChatRepository
    from swe.app.runner.repo.migrating_repo import MigratingChatRepository
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    json_repo = JsonChatRepository(tmp_path / "chats.json")
    await json_repo.upsert_chat(
        ChatSpec(
            id="legacy-chat",
            name="Legacy",
            session_id="console:legacy",
            user_id="legacy",
            channel="console",
        ),
    )

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    primary = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")
    repo = MigratingChatRepository(primary, import_repo=json_repo)

    chats = await repo.list_chats()

    assert [chat.id for chat in chats] == ["legacy-chat"]
    assert await primary.get_chat("legacy-chat") is not None


@pytest.mark.asyncio
async def test_migrating_repo_merges_missing_legacy_chats_into_non_empty_primary(
    tmp_path,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.repo.json_repo import JsonChatRepository
    from swe.app.runner.repo.migrating_repo import MigratingChatRepository
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    json_repo = JsonChatRepository(tmp_path / "chats.json")
    await json_repo.upsert_chat(
        ChatSpec(
            id="legacy-chat",
            name="Legacy",
            session_id="console:legacy",
            user_id="legacy",
            channel="console",
        ),
    )
    await json_repo.upsert_chat(
        ChatSpec(
            id="legacy-duplicate-session",
            name="Legacy Duplicate",
            session_id="console:current",
            user_id="current",
            channel="console",
        ),
    )

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    primary = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")
    await primary.upsert_chat(
        ChatSpec(
            id="current-chat",
            name="Current",
            session_id="console:current",
            user_id="current",
            channel="console",
        ),
    )
    repo = MigratingChatRepository(primary, import_repo=json_repo)

    chats = await repo.list_chats()

    assert {chat.id for chat in chats} == {"current-chat", "legacy-chat"}
    assert await primary.get_chat("legacy-chat") is not None
    assert await primary.get_chat("legacy-duplicate-session") is None


@pytest.mark.asyncio
async def test_migrating_repo_logs_parity_mismatch_when_enabled(
    tmp_path,
    monkeypatch,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.repo.json_repo import JsonChatRepository
    from swe.app.runner.repo.migrating_repo import MigratingChatRepository
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository

    json_repo = JsonChatRepository(tmp_path / "chats.json")
    await json_repo.upsert_chat(
        ChatSpec(
            id="legacy-chat",
            name="Legacy",
            session_id="console:legacy",
            user_id="legacy",
            channel="console",
        ),
    )

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
    )
    primary = MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1")
    await primary.upsert_chat(
        ChatSpec(
            id="current-chat",
            name="Current",
            session_id="console:current",
            user_id="current",
            channel="console",
        ),
    )
    repo = MigratingChatRepository(
        primary,
        import_repo=json_repo,
        parity_check=True,
    )

    warnings = []

    def _capture_warning(message, *args):
        warnings.append(message % args)

    monkeypatch.setattr(
        "swe.app.runner.repo.migrating_repo.logger.warning",
        _capture_warning,
    )

    await repo.list_chats()

    assert any("parity mismatch" in message for message in warnings)
