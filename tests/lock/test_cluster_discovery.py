# -*- coding: utf-8 -*-
"""Tests for ClusterNodeDiscovery."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.copaw.lock.cluster_discovery import ClusterNodeDiscovery, RedisClusterError


class TestClusterNodeDiscovery:
    """Test ClusterNodeDiscovery."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        client = MagicMock()
        client.execute_command = AsyncMock()
        client.aclose = AsyncMock()
        return client

    @pytest.fixture
    def discovery(self, mock_redis):
        """Create discovery instance with mocked Redis."""
        call_count = 0

        async def mock_from_url(url, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return same mock for all calls
            return mock_redis

        with patch(
            "src.copaw.lock.cluster_discovery.redis_from_url",
            side_effect=mock_from_url,
        ):
            d = ClusterNodeDiscovery(
                seeds=["node1:6379", "node2:6379"],
                discovery_interval=60,
                max_retries=2,
                retry_delay=0.1,
            )
            yield d

    @pytest.mark.asyncio
    async def test_discover_from_seed_success(self, discovery, mock_redis):
        """Test successful node discovery from seed."""
        # Mock CLUSTER NODES response with 2 master nodes
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
            b"node2 192.168.1.2:6379@16379 master - 0 0 2 connected 5461-10922\n"
        )

        nodes = await discovery._discover_from_seed("node1:6379")

        assert len(nodes) == 2
        mock_redis.execute_command.assert_called_once_with("CLUSTER NODES")

    @pytest.mark.asyncio
    async def test_get_masters_uses_cache(self, discovery, mock_redis):
        """Test that get_masters uses cached results within interval."""
        # First call should discover
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
        )

        nodes1 = await discovery.get_masters()
        assert len(nodes1) == 1

        # Second call should use cache (no new execute_command)
        mock_redis.execute_command.reset_mock()
        nodes2 = await discovery.get_masters()
        assert len(nodes2) == 1
        mock_redis.execute_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, discovery, mock_redis):
        """Test that force_refresh bypasses cache."""
        # Initial discovery
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
        )
        await discovery.get_masters()

        # Force refresh should call discovery again
        mock_redis.execute_command.reset_mock()
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
            b"node2 192.168.1.2:6379@16379 master - 0 0 2 connected 5461-10922\n"
        )
        await discovery.force_refresh()

        mock_redis.execute_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_seeds_fail_raises_error(self, discovery, mock_redis):
        """Test that error is raised when all seeds fail and no cache."""
        mock_redis.execute_command.side_effect = Exception("Connection refused")

        with pytest.raises(
            RedisClusterError,
            match="Cannot discover any master nodes",
        ):
            await discovery.get_masters()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, discovery, mock_redis):
        """Test that discovery retries on failure."""
        # First seed fails, second succeeds
        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Connection refused")
            return b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"

        mock_redis.execute_command.side_effect = mock_execute

        nodes = await discovery.get_masters()
        assert len(nodes) == 1

    @pytest.mark.asyncio
    async def test_fallback_to_cached_nodes_on_failure(self, discovery, mock_redis):
        """Test that cached nodes are used when all discovery attempts fail."""
        # First, populate cache with successful discovery
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
        )
        nodes1 = await discovery.get_masters()
        assert len(nodes1) == 1

        # Now make all discovery attempts fail (expire cache first)
        import time
        discovery._last_discovery = time.time() - 100  # Expire cache
        mock_redis.execute_command.side_effect = Exception("Connection refused")

        # Should return cached nodes instead of raising error
        nodes2 = await discovery.get_masters()
        assert len(nodes2) == 1
        assert nodes2[0] == nodes1[0]

    @pytest.mark.asyncio
    async def test_discover_empty_master_list(self, discovery, mock_redis):
        """Test discovery when cluster has no master nodes."""
        mock_redis.execute_command.return_value = b""  # No nodes

        nodes = await discovery._discover_from_seed("node1:6379")
        assert nodes == []

    @pytest.mark.asyncio
    async def test_aclose_clears_connections(self, discovery, mock_redis):
        """Test that aclose closes all connections."""
        # Populate with nodes
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
        )
        await discovery.get_masters()

        # Close should clear connections
        await discovery.aclose()
        assert discovery._masters == []
        assert discovery._last_discovery == 0
        mock_redis.aclose.assert_called()
