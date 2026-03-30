# -*- coding: utf-8 -*-
"""Tests for RedlockDistributedLock."""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.copaw.lock.redlock import RedlockDistributedLock
from src.copaw.lock.lock_token import LockToken


class TestRedlockDistributedLock:
    """Test RedlockDistributedLock with mocked Redis."""

    @pytest.fixture
    def mock_discovery(self):
        """Create mock ClusterNodeDiscovery."""
        discovery = MagicMock()
        discovery.force_refresh = AsyncMock()
        discovery.get_masters = AsyncMock()
        return discovery

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        client = MagicMock()
        client.set = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, mock_discovery, mock_redis):
        """Test successful lock acquisition."""
        mock_discovery.get_masters.return_value = [mock_redis, mock_redis, mock_redis]
        mock_redis.set.return_value = True

        redlock = RedlockDistributedLock(
            node_discovery=mock_discovery,
            single_node_timeout_ms=50,
            retry_count=1,
        )

        token = await redlock.acquire("test:resource", ttl=10000)

        assert token is not None
        assert token.resource == "test:resource"
        assert token.quorum == 2  # 3 nodes / 2 + 1
        mock_discovery.force_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_parallel(self, mock_discovery):
        """Test that lock acquisition is parallel, not sequential."""
        call_times = []

        async def mock_set(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Small delay
            return True

        redis1 = MagicMock()
        redis1.set = mock_set
        redis2 = MagicMock()
        redis2.set = mock_set

        mock_discovery.get_masters.return_value = [redis1, redis2]

        redlock = RedlockDistributedLock(
            node_discovery=mock_discovery,
            single_node_timeout_ms=100,
            retry_count=1,
        )

        await redlock.acquire("test:resource", ttl=10000)

        # Parallel calls should have similar timestamps
        assert len(call_times) == 2
        time_diff = abs(call_times[0] - call_times[1])
        assert time_diff < 0.005  # Should be nearly simultaneous

    @pytest.mark.asyncio
    async def test_acquire_lock_fails_below_quorum(self, mock_discovery, mock_redis):
        """Test lock acquisition fails when less than quorum nodes succeed."""
        # 3 nodes, need quorum=2, only 1 succeeds
        mock_redis_success = MagicMock()
        mock_redis_success.set = AsyncMock(return_value=True)
        mock_redis_fail = MagicMock()
        mock_redis_fail.set = AsyncMock(return_value=False)

        mock_discovery.get_masters.return_value = [
            mock_redis_success, mock_redis_fail, mock_redis_fail
        ]

        redlock = RedlockDistributedLock(
            node_discovery=mock_discovery,
            single_node_timeout_ms=50,
            retry_count=1,
        )

        token = await redlock.acquire("test:resource", ttl=10000)

        assert token is None

    @pytest.mark.asyncio
    async def test_release_lock(self, mock_discovery, mock_redis):
        """Test lock release."""
        mock_redis.eval = AsyncMock(return_value=1)
        mock_discovery.get_masters.return_value = [mock_redis]

        redlock = RedlockDistributedLock(node_discovery=mock_discovery)

        token = LockToken(
            resource="test:resource",
            value="abc-123",
            validity=5000.0,
            nodes=[mock_redis],
            quorum=1,
            discovery_time=1234567890.0,
        )

        await redlock.release(token)

        mock_redis.eval.assert_called_once()

    def test_lock_key_validation(self, mock_discovery):
        """Test user_id validation for hash tag."""
        redlock = RedlockDistributedLock(node_discovery=mock_discovery)

        # Valid user_id
        key = redlock.get_lock_key("alice")
        assert key == "copaw:cron:user:{alice}"

        # User_id with braces should be sanitized
        key = redlock.get_lock_key("{alice")
        assert key == "copaw:cron:user:{alice}"

        key = redlock.get_lock_key("alice}")
        assert key == "copaw:cron:user:{alice}"
