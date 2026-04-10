import asyncio

import pytest

from swe.app.runner.shared_run_coordinator import (
    RedisSharedRunCoordinator,
    SharedRunCoordinationError,
    RunOwnedByAnotherInstanceError,
)

from tests.unit.runner.test_shared_run_coordinator import FakeRedis


async def _slow_stream(_payload):
    while True:
        await asyncio.sleep(0.05)
        yield "data: {\"chunk\": \"tick\"}\n\n"


@pytest.mark.asyncio
async def test_non_owner_reads_running_status_from_shared_lease():
    from swe.app.runner.task_tracker import TaskTracker

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        heartbeat_seconds=0.01,
        cancel_ttl_seconds=60,
    )
    owner = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )
    observer = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-b:456",
        heartbeat_seconds=0.01,
    )

    queue, is_new = await owner.attach_or_start("chat-1", {}, _slow_stream)
    assert is_new is True
    assert queue is not None

    await asyncio.sleep(0.02)

    assert await observer.get_status("chat-1") == "running"
    assert await observer.get_owner("chat-1") == "pod-a:123"

    await owner.request_stop("chat-1")
    await asyncio.sleep(0.05)
    assert await observer.get_status("chat-1") == "idle"


@pytest.mark.asyncio
async def test_non_owner_stop_cancels_owner_run():
    from swe.app.runner.task_tracker import TaskTracker

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        heartbeat_seconds=0.01,
        cancel_ttl_seconds=60,
    )
    owner = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )
    observer = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-b:456",
        heartbeat_seconds=0.01,
    )

    await owner.attach_or_start("chat-1", {}, _slow_stream)
    await asyncio.sleep(0.02)

    assert await observer.request_stop("chat-1") is True

    await asyncio.sleep(0.05)
    assert await owner.get_status("chat-1") == "idle"


@pytest.mark.asyncio
async def test_second_tracker_cannot_start_duplicate_run():
    from swe.app.runner.task_tracker import TaskTracker

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        heartbeat_seconds=0.01,
        cancel_ttl_seconds=60,
    )
    owner = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )
    observer = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-b:456",
        heartbeat_seconds=0.01,
    )

    await owner.attach_or_start("chat-1", {}, _slow_stream)
    await asyncio.sleep(0.02)

    with pytest.raises(RunOwnedByAnotherInstanceError):
        await observer.attach_or_start("chat-1", {}, _slow_stream)


@pytest.mark.asyncio
async def test_same_tracker_concurrent_start_attaches_without_conflict():
    from swe.app.runner.task_tracker import TaskTracker

    class SlowStartCoordinator(RedisSharedRunCoordinator):
        async def start_run(self, run_key: str, owner_instance_id: str):
            await asyncio.sleep(0.02)
            return await super().start_run(run_key, owner_instance_id)

    redis = FakeRedis()
    coordinator = SlowStartCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        heartbeat_seconds=0.01,
        cancel_ttl_seconds=60,
    )
    tracker = TaskTracker(
        coordinator=coordinator,
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )

    results = await asyncio.gather(
        tracker.attach_or_start("chat-1", {}, _slow_stream),
        tracker.attach_or_start("chat-1", {}, _slow_stream),
    )

    assert sorted(is_new for _queue, is_new in results) == [False, True]

    await tracker.request_stop("chat-1")


@pytest.mark.asyncio
async def test_tracker_cancels_local_run_when_heartbeat_refresh_fails():
    from swe.app.runner.task_tracker import TaskTracker

    class RefreshFailsCoordinator(RedisSharedRunCoordinator):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._refresh_attempts = 0

        async def refresh_run(self, run_key: str, owner_instance_id: str):
            self._refresh_attempts += 1
            if self._refresh_attempts == 1:
                raise SharedRunCoordinationError(
                    "shared run coordination unavailable",
                )
            return await super().refresh_run(run_key, owner_instance_id)

    redis = FakeRedis()
    tracker = TaskTracker(
        coordinator=RefreshFailsCoordinator(
            redis_client=redis,
            namespace="tenant-a:agent-a",
            lease_ttl_seconds=30,
            heartbeat_seconds=0.01,
            cancel_ttl_seconds=60,
        ),
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )

    await tracker.attach_or_start("chat-1", {}, _slow_stream)

    await asyncio.sleep(0.06)

    assert await tracker.has_active_tasks() is False


@pytest.mark.asyncio
async def test_tracker_cancels_local_run_when_cancel_watch_fails():
    from swe.app.runner.task_tracker import TaskTracker

    class CancelWatchFailsCoordinator(RedisSharedRunCoordinator):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._get_attempts = 0

        async def get_run(self, run_key: str):
            self._get_attempts += 1
            if self._get_attempts >= 2:
                raise SharedRunCoordinationError(
                    "shared run coordination unavailable",
                )
            return await super().get_run(run_key)

        async def refresh_run(self, run_key: str, owner_instance_id: str):
            current = await super().get_run(run_key)
            if current is None or current.owner_instance_id != owner_instance_id:
                return None
            return current

    redis = FakeRedis()
    tracker = TaskTracker(
        coordinator=CancelWatchFailsCoordinator(
            redis_client=redis,
            namespace="tenant-a:agent-a",
            lease_ttl_seconds=30,
            heartbeat_seconds=0.01,
            cancel_ttl_seconds=60,
        ),
        instance_id="pod-a:123",
        heartbeat_seconds=0.01,
    )

    await tracker.attach_or_start("chat-1", {}, _slow_stream)

    await asyncio.sleep(0.06)

    assert await tracker.has_active_tasks() is False
