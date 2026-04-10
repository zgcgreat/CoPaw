import time

import pytest


class FakeRedis:
    def __init__(self):
        self._values = {}
        self._expires_at = {}
        self.now = time.time()

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def _purge(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is not None and expires_at <= self.now:
            self._values.pop(key, None)
            self._expires_at.pop(key, None)

    async def ping(self):
        return True

    async def set(self, key, value, ex=None, nx=False):
        self._purge(key)
        if nx and key in self._values:
            return False
        self._values[key] = value
        if ex is not None:
            self._expires_at[key] = self.now + ex
        return True

    async def get(self, key):
        self._purge(key)
        return self._values.get(key)

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            self._purge(key)
            if key in self._values:
                deleted += 1
                self._values.pop(key, None)
                self._expires_at.pop(key, None)
        return deleted

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_start_run_persists_owner_and_status():
    from swe.app.runner.shared_run_coordinator import (
        RedisSharedRunCoordinator,
    )

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        cancel_ttl_seconds=60,
    )

    lease = await coordinator.start_run("chat-1", "pod-a:123")
    observed = await coordinator.get_run("chat-1")

    assert lease.owner_instance_id == "pod-a:123"
    assert observed is not None
    assert observed.owner_instance_id == "pod-a:123"
    assert observed.status == "running"
    assert observed.cancel_requested is False


@pytest.mark.asyncio
async def test_start_run_raises_when_another_owner_is_active():
    from swe.app.runner.shared_run_coordinator import (
        RedisSharedRunCoordinator,
        RunOwnedByAnotherInstanceError,
    )

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        cancel_ttl_seconds=60,
    )

    await coordinator.start_run("chat-1", "pod-a:123")

    with pytest.raises(RunOwnedByAnotherInstanceError) as exc:
        await coordinator.start_run("chat-1", "pod-b:456")

    assert exc.value.run_key == "chat-1"
    assert exc.value.owner_instance_id == "pod-a:123"


@pytest.mark.asyncio
async def test_request_cancel_marks_active_run():
    from swe.app.runner.shared_run_coordinator import (
        RedisSharedRunCoordinator,
    )

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=30,
        cancel_ttl_seconds=60,
    )

    await coordinator.start_run("chat-1", "pod-a:123")
    stopped = await coordinator.request_cancel("chat-1")
    observed = await coordinator.get_run("chat-1")

    assert stopped is True
    assert observed is not None
    assert observed.cancel_requested is True


@pytest.mark.asyncio
async def test_expired_run_reads_as_missing():
    from swe.app.runner.shared_run_coordinator import (
        RedisSharedRunCoordinator,
    )

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=5,
        cancel_ttl_seconds=60,
    )

    await coordinator.start_run("chat-1", "pod-a:123")
    redis.advance(6)

    assert await coordinator.get_run("chat-1") is None


@pytest.mark.asyncio
async def test_start_run_clears_stale_cancel_flag_from_previous_run():
    from swe.app.runner.shared_run_coordinator import (
        RedisSharedRunCoordinator,
    )

    redis = FakeRedis()
    coordinator = RedisSharedRunCoordinator(
        redis_client=redis,
        namespace="tenant-a:agent-a",
        lease_ttl_seconds=5,
        cancel_ttl_seconds=60,
    )

    await coordinator.start_run("chat-1", "pod-a:123")
    assert await coordinator.request_cancel("chat-1") is True

    redis.advance(6)

    restarted = await coordinator.start_run("chat-1", "pod-b:456")
    observed = await coordinator.get_run("chat-1")

    assert restarted.owner_instance_id == "pod-b:456"
    assert observed is not None
    assert observed.owner_instance_id == "pod-b:456"
    assert observed.cancel_requested is False
