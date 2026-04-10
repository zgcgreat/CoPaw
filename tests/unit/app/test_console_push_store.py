# -*- coding: utf-8 -*-
import asyncio
import importlib
import json
import time

import fakeredis.aioredis
import pytest


@pytest.fixture
async def fake_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


@pytest.mark.asyncio
async def test_take_reads_message_written_by_separate_store_instance(
    fake_client,
):
    from swe.app.console_push_store import RedisConsolePushStore

    writer = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
    )
    reader = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
    )

    await writer.append("session-a", "hello", tenant_id="tenant-a")
    messages = await reader.take("session-a", tenant_id="tenant-a")

    assert len(messages) == 1
    assert messages[0]["text"] == "hello"
    assert messages[0]["sticky"] is False
    assert messages[0]["id"]


@pytest.mark.asyncio
async def test_take_is_isolated_by_tenant_and_session(fake_client):
    from swe.app.console_push_store import RedisConsolePushStore

    store = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
    )

    await store.append("session-a", "tenant-a only", tenant_id="tenant-a")
    await store.append(
        "session-b",
        "same tenant other session",
        tenant_id="tenant-a",
    )
    await store.append("session-a", "tenant-b only", tenant_id="tenant-b")

    assert [
        m["text"] for m in await store.take("session-a", tenant_id="tenant-a")
    ] == ["tenant-a only"]
    assert [
        m["text"] for m in await store.take("session-b", tenant_id="tenant-a")
    ] == ["same tenant other session"]
    assert [
        m["text"] for m in await store.take("session-a", tenant_id="tenant-b")
    ] == ["tenant-b only"]


@pytest.mark.asyncio
async def test_append_trims_to_max_messages(fake_client):
    from swe.app.console_push_store import RedisConsolePushStore

    store = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
        max_messages=2,
    )

    await store.append("session-a", "one", tenant_id="tenant-a")
    await store.append("session-a", "two", tenant_id="tenant-a")
    await store.append("session-a", "three", tenant_id="tenant-a")

    assert [
        m["text"] for m in await store.take("session-a", tenant_id="tenant-a")
    ] == ["two", "three"]


@pytest.mark.asyncio
async def test_take_drops_expired_messages(fake_client):
    from swe.app.console_push_store import RedisConsolePushStore

    store = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
        max_age_seconds=0,
    )

    await store.append("session-a", "expired", tenant_id="tenant-a")
    await asyncio.sleep(0.01)

    assert await store.take("session-a", tenant_id="tenant-a") == []


class AppendDuringReadRedis:
    def __init__(self, inner):
        self._inner = inner
        self._target_key = None
        self._injected = False

    def inject_after_read(self, key: str) -> None:
        self._target_key = key
        self._injected = False

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def zrange(self, key, start, end):
        rows = await self._inner.zrange(key, start, end)
        if self._target_key is not None and not self._injected:
            self._injected = True
            now = time.time()
            payload = json.dumps(
                {
                    "id": "late-message",
                    "text": "late arrival",
                    "sticky": False,
                    "ts": now,
                },
                separators=(",", ":"),
            )
            await self._inner.zadd(self._target_key, {payload: now})
        return rows


@pytest.mark.asyncio
async def test_take_preserves_message_appended_during_polling(fake_client):
    from swe.app.console_push_store import RedisConsolePushStore

    client = AppendDuringReadRedis(fake_client)
    store = RedisConsolePushStore(
        client,
        key_prefix="test:console-push",
    )
    key = store._key("session-a", "tenant-a")

    await store.append("session-a", "first", tenant_id="tenant-a")
    client.inject_after_read(key)

    drained = await store.take("session-a", tenant_id="tenant-a")
    follow_up = await store.take("session-a", tenant_id="tenant-a")

    assert [m["text"] for m in drained] == ["first"]
    assert [m["text"] for m in follow_up] == ["late arrival"]


@pytest.mark.asyncio
async def test_take_recovers_messages_left_in_drain_key(fake_client):
    from swe.app.console_push_store import RedisConsolePushStore

    store = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
    )
    key = store._key("session-a", "tenant-a")
    drain_key = store._drain_key("session-a", "tenant-a")

    await store.append("session-a", "orphaned", tenant_id="tenant-a")
    await fake_client.rename(key, drain_key)

    assert [m["text"] for m in await store.take("session-a", "tenant-a")] == [
        "orphaned",
    ]


@pytest.mark.asyncio
async def test_get_stats_keeps_tenant_id_when_session_contains_colon(
    fake_client,
):
    from swe.app.console_push_store import RedisConsolePushStore

    store = RedisConsolePushStore(
        fake_client,
        key_prefix="test:console-push",
    )

    await store.append("console:alice", "hello", tenant_id="tenant-a")

    assert await store.get_stats() == {
        "tenant_count": 1,
        "tenants": {"tenant-a": 1},
    }


def test_default_store_requires_redis_url(monkeypatch):
    module = importlib.import_module("swe.app.console_push_store")
    monkeypatch.delenv("SWE_CONSOLE_PUSH_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(module, "_DEFAULT_STORE", None, raising=False)

    with pytest.raises(RuntimeError, match="Console push delivery requires Redis"):
        module._get_default_store()
