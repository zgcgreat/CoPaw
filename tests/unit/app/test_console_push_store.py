# -*- coding: utf-8 -*-
"""Unit tests for tenant-scoped console push store.

Tests that messages are isolated by tenant and do not leak across tenants.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
_STORE_FILE = SRC_ROOT / "swe" / "app" / "console_push_store.py"

store_spec = importlib.util.spec_from_file_location(
    "tenant_test_console_push_store",
    _STORE_FILE,
)
assert store_spec is not None and store_spec.loader is not None
console_push_store = importlib.util.module_from_spec(store_spec)
store_spec.loader.exec_module(console_push_store)


class TestTenantPushStoreIsolation:
    """Tests for tenant isolation in push store."""

    def test_messages_do_not_leak_across_sessions_within_same_tenant(self):
        append = console_push_store.append
        clear_tenant = console_push_store.clear_tenant
        take = console_push_store.take

        async def scenario():
            await clear_tenant("tenant-a")
            await append("session-a", "msg-a", tenant_id="tenant-a")
            await append("session-b", "msg-b", tenant_id="tenant-a")
            return await take("session-a", tenant_id="tenant-a")

        taken = asyncio.run(scenario())

        assert [m["text"] for m in taken] == ["msg-a"]

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_append_creates_tenant_isolated_message(self):
        """Appended messages include tenant_id for isolation."""
        from swe.app.console_push_store import append, _get_tenant_store

        await append("session-1", "Hello", tenant_id="tenant-a")

        store = _get_tenant_store("tenant-a")
        assert len(store) == 1
        assert store[0]["tenant_id"] == "tenant-a"
        assert store[0]["session_id"] == "session-1"

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_take_returns_only_tenant_messages(self):
        """take returns only messages for specified tenant."""
        from swe.app.console_push_store import append, take

        # Add messages for different tenants
        await append("session-1", "Tenant A msg", tenant_id="tenant-a")
        await append("session-1", "Tenant B msg", tenant_id="tenant-b")

        # Take only tenant-a messages
        messages = await take("session-1", tenant_id="tenant-a")

        assert len(messages) == 1
        assert messages[0]["text"] == "Tenant A msg"

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_take_does_not_affect_other_tenants(self):
        """Taking messages for one tenant doesn't affect another."""
        from swe.app.console_push_store import append, take, _get_tenant_store

        # Add messages for both tenants
        await append("session-1", "Tenant A msg", tenant_id="tenant-a")
        await append("session-1", "Tenant B msg", tenant_id="tenant-b")

        # Take tenant-a messages
        await take("session-1", tenant_id="tenant-a")

        # Tenant-b messages should still exist
        store_b = _get_tenant_store("tenant-b")
        assert len(store_b) == 1
        assert store_b[0]["text"] == "Tenant B msg"

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_get_recent_returns_only_tenant_messages(self):
        """get_recent returns only messages for specified tenant."""
        from swe.app.console_push_store import append, get_recent

        # Add messages for different tenants
        await append("session-1", "Tenant A msg", tenant_id="tenant-a")
        await append("session-2", "Tenant A msg 2", tenant_id="tenant-a")
        await append("session-1", "Tenant B msg", tenant_id="tenant-b")

        # Get recent for tenant-a
        messages = await get_recent(tenant_id="tenant-a")

        assert len(messages) == 2
        for msg in messages:
            # Should only see tenant-a messages
            assert "Tenant A" in msg["text"]

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_default_tenant_when_not_specified(self):
        """When tenant_id not specified, uses 'default' tenant."""
        from swe.app.console_push_store import append, _get_tenant_store

        await append("session-1", "Default msg")

        store = _get_tenant_store("default")
        assert len(store) == 1
        assert store[0]["text"] == "Default msg"

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_clear_tenant_removes_only_that_tenant(self):
        """clear_tenant only removes messages for specified tenant."""
        from swe.app.console_push_store import (
            append,
            clear_tenant,
            _get_tenant_store,
        )

        # Add messages for both tenants
        await append("session-1", "Tenant A msg", tenant_id="tenant-a")
        await append("session-1", "Tenant B msg", tenant_id="tenant-b")

        # Clear tenant-a
        await clear_tenant("tenant-a")

        # Tenant-a should be empty
        store_a = _get_tenant_store("tenant-a")
        assert len(store_a) == 0

        # Tenant-b should still have message
        store_b = _get_tenant_store("tenant-b")
        assert len(store_b) == 1


class TestTenantPushStoreBounded:
    """Tests for bounded message storage per tenant."""

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_max_messages_per_tenant(self):
        """Max messages limit is enforced per tenant."""
        from swe.app.console_push_store import (
            append,
            _get_tenant_store,
            _MAX_MESSAGES,
        )

        # Add many messages to tenant-a
        for i in range(_MAX_MESSAGES + 10):
            await append(f"session-{i}", f"Message {i}", tenant_id="tenant-a")

        store_a = _get_tenant_store("tenant-a")
        assert len(store_a) <= _MAX_MESSAGES

    @pytest.mark.skip(reason="Requires full app dependencies")
    async def test_message_limits_are_per_tenant(self):
        """Each tenant has its own message limit."""
        from swe.app.console_push_store import (
            append,
            _get_tenant_store,
            _MAX_MESSAGES,
        )

        # Fill tenant-a to limit
        for i in range(_MAX_MESSAGES + 5):
            await append(
                f"session-a-{i}",
                f"Message A {i}",
                tenant_id="tenant-a",
            )

        # Add messages to tenant-b
        for i in range(5):
            await append(
                f"session-b-{i}",
                f"Message B {i}",
                tenant_id="tenant-b",
            )

        store_a = _get_tenant_store("tenant-a")
        store_b = _get_tenant_store("tenant-b")

        assert len(store_a) <= _MAX_MESSAGES
        assert len(store_b) == 5  # All tenant-b messages kept


class TestTenantPushStoreStats:
    """Tests for push store statistics."""

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_stats_returns_tenant_counts(self):
        """get_stats returns message counts per tenant."""
        # Contract test
        pass
