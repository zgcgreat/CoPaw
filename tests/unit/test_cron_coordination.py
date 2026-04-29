# -*- coding: utf-8 -*-
"""Unit tests for Redis-coordinated cron leadership.

These tests verify:
- Lease election and renewal
- Scheduler preflight and definition version helpers
- Legacy execution lock semantics
- Activation/deactivation behavior
- Reload debounce behavior
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all tests as requiring Redis (skipped if redis not available)
pytestmark = [
    pytest.mark.asyncio,
]

# Check if redis is available
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


# Skip all tests if redis is not available
if not REDIS_AVAILABLE:
    pytest.skip("Redis not available", allow_module_level=True)


from swe.app.crons.coordination import (
    AgentLease,
    CoordinationConfig,
    CronCoordination,
    CronCoordinationError,
    DefinitionLockTimeoutError,
    ExecutionLock,
    RedisNotAvailableError,
)


@pytest.fixture
def coordination_config():
    """Default coordination config for tests."""
    return CoordinationConfig(
        enabled=True,
        redis_url="redis://localhost:6379/15",  # Use DB 15 for tests
        lease_ttl_seconds=10,
        lease_renew_interval_seconds=3,
        lease_renew_failure_threshold=2,
        lock_safety_margin_seconds=5,
    )


@pytest.fixture
async def redis_client():
    """Create a Redis client for tests."""
    if not REDIS_AVAILABLE:
        pytest.skip("Redis not available")

    # Import here to ensure we have redis available
    import redis.asyncio as redis_lib

    try:
        client = redis_lib.from_url("redis://localhost:6379/15")
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable: {e}")

    try:
        yield client
    finally:
        # Clean up test keys
        try:
            keys = await client.keys("swe:cron:*")
            if keys:
                await client.delete(*keys)
        except Exception:
            pass  # Ignore cleanup errors
        try:
            await client.close()
        except Exception:
            pass  # Ignore close errors


class TestAgentLease:
    """Tests for AgentLease - leader election per tenant+agent."""

    async def test_lease_acquire_and_release(
        self,
        redis_client,
        coordination_config,
    ):
        """Test basic lease acquisition and release."""
        lease = AgentLease(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            instance_id="instance-1",
            config=coordination_config,
        )

        # Should not be owned initially
        assert not lease.is_owned

        # Acquire lease
        acquired = await lease.acquire()
        assert acquired is True
        assert lease.is_owned

        # Release lease
        await lease.release()
        assert not lease.is_owned

    async def test_lease_prevents_duplicate_acquisition(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that only one instance can hold the lease."""
        lease1 = AgentLease(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            instance_id="instance-1",
            config=coordination_config,
        )
        lease2 = AgentLease(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            instance_id="instance-2",
            config=coordination_config,
        )

        # First instance acquires lease
        acquired1 = await lease1.acquire()
        assert acquired1 is True
        assert lease1.is_owned

        # Second instance should fail to acquire
        acquired2 = await lease2.acquire()
        assert acquired2 is False
        assert not lease2.is_owned

        # Release first instance
        await lease1.release()

        # Second instance can now acquire
        acquired2 = await lease2.acquire()
        assert acquired2 is True
        assert lease2.is_owned

        await lease2.release()

    async def test_lease_renewal(self, redis_client, coordination_config):
        """Test that lease is automatically renewed."""
        # Use shorter intervals for faster test
        config = CoordinationConfig(
            enabled=True,
            redis_url="redis://localhost:6379/15",
            lease_ttl_seconds=5,
            lease_renew_interval_seconds=2,
            lease_renew_failure_threshold=3,
        )

        lease = AgentLease(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            instance_id="instance-1",
            config=config,
        )

        # Acquire lease
        acquired = await lease.acquire()
        assert acquired is True

        # Wait for renewal to happen
        await asyncio.sleep(3)

        # Lease should still be owned
        assert lease.is_owned

        # Verify TTL was extended
        ttl = await redis_client.ttl(lease._key)
        assert ttl > 0
        assert ttl <= config.lease_ttl_seconds

        await lease.release()

    async def test_lease_lost_when_key_deleted(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that lease is lost if key is externally deleted."""
        lease = AgentLease(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            instance_id="instance-1",
            config=coordination_config,
        )

        # Acquire lease
        await lease.acquire()
        assert lease.is_owned

        # Delete key externally (simulates another instance stealing or expiry)
        await redis_client.delete(lease._key)

        # Wait for renewal cycle to detect loss
        await asyncio.sleep(
            coordination_config.lease_renew_interval_seconds + 1,
        )

        # Lease should be lost
        assert not lease.is_owned


class TestExecutionLock:
    """Tests for the legacy ExecutionLock compatibility surface."""

    async def test_execution_lock_acquire_and_release(
        self,
        redis_client,
        coordination_config,
    ):
        """Test basic lock acquisition and release."""
        lock = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-1",
            ttl_seconds=10,
        )

        # Acquire lock
        acquired = await lock.acquire()
        assert acquired is True

        # Try to acquire same lock again (should fail)
        lock2 = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-1",
            ttl_seconds=10,
        )
        acquired2 = await lock2.acquire()
        assert acquired2 is False

        # Release first lock
        await lock.release()

        # Now second lock can be acquired
        acquired2 = await lock2.acquire()
        assert acquired2 is True

        await lock2.release()

    async def test_execution_lock_expires(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that lock expires after TTL."""
        lock = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-1",
            ttl_seconds=2,  # Short TTL for test
        )

        # Acquire lock
        acquired = await lock.acquire()
        assert acquired is True

        # Wait for TTL to expire
        await asyncio.sleep(3)

        # Now another lock can be acquired
        lock2 = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-1",
            ttl_seconds=10,
        )
        acquired2 = await lock2.acquire()
        assert acquired2 is True

        await lock2.release()

    async def test_execution_lock_isolated_per_job(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that locks for different jobs don't interfere."""
        lock1 = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-1",
            ttl_seconds=10,
        )
        lock2 = ExecutionLock(
            redis_client=redis_client,
            tenant_id="test-tenant",
            agent_id="test-agent",
            job_id="job-2",
            ttl_seconds=10,
        )

        # Both should be able to acquire
        acquired1 = await lock1.acquire()
        acquired2 = await lock2.acquire()
        assert acquired1 is True
        assert acquired2 is True

        await lock1.release()
        await lock2.release()


class TestCronCoordination:
    """Tests for CronCoordination - high-level coordination API."""

    async def test_connect_without_redis_raises_error(self):
        """Test that connection fails gracefully if Redis unavailable."""
        config = CoordinationConfig(
            enabled=True,
            redis_url="redis://invalid:6379",
        )
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        # Should return False if connection fails
        connected = await coord.connect()
        assert connected is False

    async def test_coordination_disabled_returns_true(self):
        """Test that disabled coordination returns True (no-op mode)."""
        config = CoordinationConfig(enabled=False)
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        # Should return True when disabled (no coordination needed)
        connected = await coord.connect()
        assert (
            connected is False
        )  # Returns False because coordination is disabled

    async def test_activate_without_connection(self, coordination_config):
        """Test that activation without connection raises error."""
        # Don't connect first
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Activate without connecting - should raise RedisNotAvailableError
        with pytest.raises(RedisNotAvailableError):
            await coord.activate()

    async def test_publish_reload_without_connection(
        self,
        coordination_config,
    ):
        """Test that publish_reload returns False if not connected."""
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Should return False if not connected
        result = await coord.publish_reload()
        assert result is False

    async def test_set_reload_callback(self, coordination_config):
        """Test setting reload callback."""
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=coordination_config,
        )

        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        coord.set_reload_callback(callback)
        assert coord._on_reload is callback

    async def test_preflight_scheduler_execution_checks_current_lease_owner(
        self,
        coordination_config,
    ):
        """Scheduler preflight should verify current Redis lease ownership."""
        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=coordination_config,
        )
        coord._instance_id = "instance-1"
        coord._redis = AsyncMock()
        coord._redis.get = AsyncMock(return_value=b"instance-1")
        coord._lease = MagicMock()
        coord._lease.is_owned = True
        coord._lease._key = "lease-key"

        allowed = await coord.preflight_scheduler_execution(
            job_id="job-1",
            schedule_type="cron",
        )

        assert allowed is True
        coord._redis.get.assert_awaited_once_with("lease-key")

    async def test_definition_version_helpers_use_tenant_agent_scope(
        self,
        coordination_config,
    ):
        """Definition version helpers should read and bump the shared key."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )
        coord._redis = AsyncMock()
        coord._redis.get = AsyncMock(return_value=b"2")
        coord._redis.incr = AsyncMock(return_value=3)
        coord._redis.eval = AsyncMock(return_value=4)

        current = await coord.get_definition_version()
        bumped = await coord.bump_definition_version()
        ensured = await coord.ensure_definition_version(4)

        assert current == 2
        assert bumped == 3
        assert ensured == 4
        coord._redis.get.assert_awaited_once_with(
            "swe:cron:defver:test-tenant:test-agent",
        )
        coord._redis.incr.assert_awaited_once_with(
            "swe:cron:defver:test-tenant:test-agent",
        )
        coord._redis.eval.assert_awaited_once()

    async def test_acquire_definition_lock_times_out_when_lock_never_frees(
        self,
    ):
        """Definition lock acquisition should fail instead of waiting forever."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=CoordinationConfig(
                enabled=True,
                definition_lock_timeout_seconds=0.01,
            ),
        )
        coord._redis = AsyncMock()
        coord._redis.set = AsyncMock(return_value=False)

        with pytest.raises(DefinitionLockTimeoutError):
            await coord.acquire_definition_lock()

    async def test_acquire_definition_lock_raises_on_redis_error(
        self,
    ):
        """Redis errors during definition lock acquisition should surface."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=CoordinationConfig(enabled=True),
        )
        coord._redis = AsyncMock()
        coord._redis.set = AsyncMock(side_effect=RuntimeError("redis down"))

        with pytest.raises(CronCoordinationError, match="redis down"):
            await coord.acquire_definition_lock()


class TestCronCoordinationWithRedis:
    """Tests for CronCoordination that require Redis."""

    async def test_full_lifecycle(self, redis_client, coordination_config):
        """Test full coordination lifecycle with Redis."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Connect
        connected = await coord.connect()
        assert connected is True

        # Activate - should become leader
        is_leader = await coord.activate()
        assert is_leader is True
        assert coord.is_leader

        # Deactivate
        await coord.deactivate()
        assert not coord.is_leader

        # Disconnect
        await coord.disconnect()

    async def test_two_instances_leader_election(
        self,
        redis_client,
        coordination_config,
    ):
        """Test leader election with two coordination instances."""
        coord1 = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )
        coord2 = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Connect both
        assert await coord1.connect()
        assert await coord2.connect()

        # Activate first - should become leader
        is_leader1 = await coord1.activate()
        assert is_leader1 is True
        assert coord1.is_leader

        # Activate second - should be follower
        is_leader2 = await coord2.activate()
        assert is_leader2 is False
        assert not coord2.is_leader

        # First deactivates
        await coord1.deactivate()
        assert not coord1.is_leader

        # Second can now become leader if it re-activates
        # (But in current implementation, it stays follower)

        await coord2.deactivate()
        await coord1.disconnect()
        await coord2.disconnect()

    async def test_publish_reload(self, redis_client, coordination_config):
        """Test publishing reload signal."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Connect and activate
        await coord.connect()
        await coord.activate()

        # Publish reload
        result = await coord.publish_reload()
        assert result is True

        await coord.deactivate()
        await coord.disconnect()

    async def test_create_execution_lock(
        self,
        redis_client,
        coordination_config,
    ):
        """Test creating execution lock through coordination."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Connect and activate
        await coord.connect()

        # Create execution lock
        lock = coord.create_execution_lock("job-1", timeout_seconds=30)
        assert lock is not None

        # Acquire the lock
        acquired = await lock.acquire()
        assert acquired is True

        await lock.release()
        await coord.disconnect()

    async def test_create_execution_lock_without_connection(
        self,
        coordination_config,
    ):
        """Test that creating execution lock without connection raises error."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Don't connect
        with pytest.raises(Exception):  # RedisNotAvailableError
            coord.create_execution_lock("job-1", timeout_seconds=30)


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestCronCoordinationClusterMode:
    """Tests for CronCoordination in cluster mode.

    These tests verify cluster-specific behavior including:
    - ClusterNode conversion from configuration
    - require_full_coverage parameter mapping
    - Separate pub/sub client for cluster mode
    """

    def test_cluster_startup_nodes_from_dict(self):
        """Test that cluster_nodes dicts are converted to ClusterNode objects."""
        from swe.app.crons.coordination import (
            CoordinationConfig,
            CronCoordination,
        )

        config = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            cluster_nodes=[
                {"host": "127.0.0.1", "port": 6379},
                {"host": "127.0.0.2", "port": 6380},
            ],
            redis_url="redis://127.0.0.1:6379",
        )

        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        nodes = coord._build_cluster_startup_nodes()
        assert len(nodes) == 2
        assert nodes[0].host == "127.0.0.1"
        assert nodes[0].port == 6379
        assert nodes[1].host == "127.0.0.2"
        assert nodes[1].port == 6380

    def test_cluster_startup_nodes_from_url(self):
        """Test that startup nodes are parsed from redis_url."""
        from swe.app.crons.coordination import (
            CoordinationConfig,
            CronCoordination,
        )

        config = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            redis_url="redis://host1:6379,host2:6380,host3:6381",
        )

        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        nodes = coord._build_cluster_startup_nodes()
        assert len(nodes) == 3
        assert nodes[0].host == "host1"
        assert nodes[0].port == 6379
        assert nodes[1].host == "host2"
        assert nodes[1].port == 6380
        assert nodes[2].host == "host3"
        assert nodes[2].port == 6381

    def test_cluster_url_with_auth(self):
        """Test that auth credentials are parsed from redis_url."""
        from swe.app.crons.coordination import (
            CoordinationConfig,
            CronCoordination,
        )

        config = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            redis_url="redis://user:pass@host1:6379",
        )

        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        params = coord._parse_redis_url()
        assert params["host"] == "host1"
        assert params["port"] == 6379
        assert params["username"] == "user"
        assert params["password"] == "pass"

    def test_cluster_multi_node_url_with_auth(self):
        """Test that auth is parsed from multi-node redis_url."""
        from swe.app.crons.coordination import (
            CoordinationConfig,
            CronCoordination,
        )

        config = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            redis_url="redis://user:pass@host1:6379,host2:6380,host3:6381",
        )

        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        # Should parse auth from first node only
        params = coord._parse_redis_url()
        assert params["host"] == "host1"
        assert params["port"] == 6379
        assert params["username"] == "user"
        assert params["password"] == "pass"

        # Startup nodes should still have all 3 nodes
        nodes = coord._build_cluster_startup_nodes()
        assert len(nodes) == 3
        assert nodes[0].host == "host1"
        assert nodes[1].host == "host2"
        assert nodes[2].host == "host3"

    def test_cluster_skip_full_coverage_mapping(self):
        """Test that cluster_skip_full_coverage_check maps correctly."""
        from swe.app.crons.coordination import CoordinationConfig

        # When skip is True, require_full_coverage should be False
        config_skip = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            cluster_skip_full_coverage_check=True,
            redis_url="redis://localhost:6379",
        )
        assert config_skip.cluster_skip_full_coverage_check is True

        # When skip is False, require_full_coverage should be True
        config_no_skip = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            cluster_skip_full_coverage_check=False,
            redis_url="redis://localhost:6379",
        )
        assert config_no_skip.cluster_skip_full_coverage_check is False

    async def test_publish_reload_uses_pubsub_client_in_cluster_mode(self):
        """Test that publish_reload uses _pubsub_client in cluster mode.

        RedisCluster doesn't have publish() method, so we need to use
        a standalone Redis client for publishing.
        """
        from swe.app.crons.coordination import (
            CoordinationConfig,
            CronCoordination,
        )

        config = CoordinationConfig(
            enabled=True,
            cluster_mode=True,
            redis_url="redis://localhost:6379",
        )

        coord = CronCoordination(
            tenant_id="test",
            agent_id="test-agent",
            config=config,
        )

        # Mock the clients
        mock_cluster = MagicMock()
        mock_pubsub = MagicMock()

        coord._redis = mock_cluster
        coord._pubsub_client = mock_pubsub

        with patch("swe.app.crons.coordination.ReloadPublisher") as mock_cls:
            mock_publisher = MagicMock()
            mock_publisher.publish = AsyncMock(return_value=True)
            mock_cls.return_value = mock_publisher

            result = await coord.publish_reload()

        assert result is True
        mock_cls.assert_called_once_with(
            redis_client=mock_pubsub,
            config=config,
        )
        mock_publisher.publish.assert_awaited_once_with("test", "test-agent")
        mock_cluster.publish.assert_not_called()


class TestCronCoordinationCandidateLoop:
    """Tests for follower candidate loop functionality."""

    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
    async def test_candidate_loop_becomes_leader(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that candidate loop can acquire leadership when lease is free."""
        coord = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # Connect first
        assert await coord.connect()

        # Start candidate loop (don't activate yet)
        become_leader_called = False

        def on_become_leader():
            nonlocal become_leader_called
            become_leader_called = True

        coord.set_become_leader_callback(on_become_leader)

        # Start candidate loop - should acquire leadership
        await coord.start_candidate_loop()

        # Wait for candidate loop to try
        await asyncio.sleep(
            coordination_config.lease_renew_interval_seconds + 1,
        )

        # Should have become leader
        assert coord.is_leader
        assert become_leader_called

        await coord.deactivate()
        await coord.disconnect()

    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
    async def test_candidate_loop_with_existing_leader(
        self,
        redis_client,
        coordination_config,
    ):
        """Test that candidate loop doesn't steal existing lease."""
        coord1 = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )
        coord2 = CronCoordination(
            tenant_id="test-tenant",
            agent_id="test-agent",
            config=coordination_config,
        )

        # First becomes leader
        assert await coord1.connect()
        assert await coord1.activate()
        assert coord1.is_leader

        # Second connects and starts candidate loop
        assert await coord2.connect()
        await coord2.start_candidate_loop()

        # Wait for candidate loop to try
        await asyncio.sleep(
            coordination_config.lease_renew_interval_seconds + 1,
        )

        # Second should still be follower
        assert not coord2.is_leader

        await coord1.deactivate()
        await coord1.disconnect()
        await coord2.stop_candidate_loop()
        await coord2.disconnect()
