import pytest

from swe.app.runner.shared_run_coordinator import RedisSharedRunCoordinator

from tests.unit.runner.test_shared_run_coordinator import FakeRedis


@pytest.mark.asyncio
async def test_completed_run_remains_queryable_after_tracker_cleanup(
    tmp_path,
):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.manager import ChatManager
    from swe.app.runner.models import ChatSpec
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository
    from swe.app.runner.repo.mysql_run_repo import MysqlChatRunRepository
    from swe.app.runner.run_models import ChatRunContext
    from swe.app.runner.task_tracker import TaskTracker

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}",
    )
    manager = ChatManager(
        repo=MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1"),
        run_repo=MysqlChatRunRepository(
            engine,
            tenant_id="tenant-a",
            agent_id="a1",
        ),
    )
    tracker = TaskTracker(
        coordinator=RedisSharedRunCoordinator(
            redis_client=FakeRedis(),
            namespace="tenant-a:a1",
            lease_ttl_seconds=30,
            heartbeat_seconds=0.01,
            cancel_ttl_seconds=60,
        ),
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )
    tracker.bind_chat_manager(manager)

    chat = ChatSpec(
        id="chat-1",
        name="Alpha",
        session_id="console:alice",
        user_id="alice",
        channel="console",
    )
    await manager.create_chat(chat)

    async def stream_fn(_payload):
        yield "data: {\"message\": \"ok\"}\n\n"

    queue, _ = await tracker.attach_or_start(
        chat.id,
        {"payload": "ignored"},
        stream_fn,
        run_context=ChatRunContext.from_chat(chat),
    )

    async for _ in tracker.stream_from_queue(queue, chat.id):
        pass

    assert await tracker.get_status(chat.id) == "idle"
    runs = await manager.list_runs(chat.id, limit=10)
    assert len(runs) == 1
    assert runs[0].status == "completed"


@pytest.mark.asyncio
async def test_failed_run_persists_failure_result(tmp_path):
    from swe.app.persistence.mysql import create_control_store_engine
    from swe.app.runner.manager import ChatManager
    from swe.app.runner.models import ChatSpec
    from swe.app.runner.repo.mysql_chat_repo import MysqlChatRepository
    from swe.app.runner.repo.mysql_run_repo import MysqlChatRunRepository
    from swe.app.runner.run_models import ChatRunContext
    from swe.app.runner.task_tracker import TaskTracker

    engine = create_control_store_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}",
    )
    manager = ChatManager(
        repo=MysqlChatRepository(engine, tenant_id="tenant-a", agent_id="a1"),
        run_repo=MysqlChatRunRepository(
            engine,
            tenant_id="tenant-a",
            agent_id="a1",
        ),
    )
    tracker = TaskTracker(
        coordinator=RedisSharedRunCoordinator(
            redis_client=FakeRedis(),
            namespace="tenant-a:a1",
            lease_ttl_seconds=30,
            heartbeat_seconds=0.01,
            cancel_ttl_seconds=60,
        ),
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )
    tracker.bind_chat_manager(manager)

    chat = ChatSpec(
        id="chat-2",
        name="Beta",
        session_id="console:bob",
        user_id="bob",
        channel="console",
    )
    await manager.create_chat(chat)

    async def stream_fn(_payload):
        raise RuntimeError("boom")
        yield "data: {}\n\n"

    queue, _ = await tracker.attach_or_start(
        chat.id,
        {"payload": "ignored"},
        stream_fn,
        run_context=ChatRunContext.from_chat(chat),
    )

    async for _ in tracker.stream_from_queue(queue, chat.id):
        pass

    runs = await manager.list_runs(chat.id, limit=10)
    assert runs[0].status == "failed"
    assert "boom" in (runs[0].error or "")
