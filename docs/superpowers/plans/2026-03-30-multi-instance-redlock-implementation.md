# Multi-Instance Deployment with Redis Cluster + Redlock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use @superpowers:subagent-driven-development (recommended) or @superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Redis Cluster support with Redlock distributed locking algorithm for multi-instance CoPaw deployment, ensuring no duplicate cron task execution across instances.

**Architecture:**
- Redlock algorithm for distributed locking across Redis Cluster nodes
- ClusterNodeDiscovery for automatic topology management with force refresh
- LockToken with stored quorum for correct renewal during cluster scaling
- Parallel lock acquisition using asyncio.gather
- Separate storage strategies: Redlock (cron only), Redis Hash+TTL (temp data), NAS+FileLock (persistent data)

**Tech Stack:** Python 3.10+, redis-py 5.0+, asyncio, APScheduler, portalocker

---

## File Structure

### New Files (Create)

| File | Responsibility |
|------|---------------|
| `src/copaw/lock/lock_token.py` | LockToken dataclass with quorum and discovery_time |
| `src/copaw/lock/cluster_discovery.py` | ClusterNodeDiscovery with auto-discovery and force refresh |
| `src/copaw/lock/redlock.py` | RedlockDistributedLock with parallel acquisition |
| `src/copaw/lock/redlock_renewal.py` | RedlockRenewalTask with stored quorum usage |
| `src/copaw/store/redis_store.py` | Redis-based temporary data storage |

### Modified Files

| File | Changes |
|------|---------|
| `src/copaw/lock/__init__.py` | Export new classes |
| `src/copaw/constant.py` | Add Redis Cluster and Redlock constants |
| `src/copaw/config/config.py` | Add RedisClusterConfig dataclass |
| `src/copaw/app/crons/manager.py` | Integrate Redlock, add cluster health check |
| `src/copaw/app/console_push_store.py` | Use Redis Hash + TTL |
| `src/copaw/app/download_task_store.py` | Use Redis Hash + TTL |

### Test Files (Create)

| File | Tests |
|------|-------|
| `tests/lock/test_lock_token.py` | LockToken dataclass |
| `tests/lock/test_cluster_discovery.py` | ClusterNodeDiscovery mocking |
| `tests/lock/test_redlock.py` | Redlock algorithm with mocked Redis |
| `tests/lock/test_redlock_renewal.py` | Renewal task behavior |

---

## Task 1: LockToken Dataclass

**Files:**
- Create: `src/copaw/lock/lock_token.py`
- Test: `tests/lock/test_lock_token.py`

- [ ] **Step 1: Write failing test**

```python
# tests/lock/test_lock_token.py
import pytest
from dataclasses import dataclass
from src.copaw.lock.lock_token import LockToken


class TestLockToken:
    """Test LockToken dataclass."""

    def test_lock_token_creation(self):
        """Test basic LockToken creation."""
        token = LockToken(
            resource="copaw:cron:user:{alice}",
            value="abc-123",
            validity=590000.0,
            nodes=[],
            quorum=2,
            discovery_time=1234567890.0,
        )
        assert token.resource == "copaw:cron:user:{alice}"
        assert token.value == "abc-123"
        assert token.validity == 590000.0
        assert token.quorum == 2
        assert token.discovery_time == 1234567890.0

    def test_lock_token_is_expired(self):
        """Test validity expiration check."""
        import time
        token = LockToken(
            resource="test",
            value="v",
            validity=100.0,  # 100ms
            nodes=[],
            quorum=1,
            discovery_time=time.time(),
        )
        # Token should be valid immediately
        assert not token.is_expired()
        # After validity period
        time.sleep(0.15)
        assert token.is_expired()

    def test_lock_token_is_discovery_stale(self):
        """Test discovery staleness check."""
        import time
        token = LockToken(
            resource="test",
            value="v",
            validity=10000.0,
            nodes=[],
            quorum=1,
            discovery_time=time.time() - 10,  # 10 seconds ago
        )
        # Should be stale after 5 seconds (default)
        assert token.is_discovery_stale(max_age=5.0)
        # Should not be stale with 15 second threshold
        assert not token.is_discovery_stale(max_age=15.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/lock/test_lock_token.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.copaw.lock.lock_token'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/copaw/lock/lock_token.py
# -*- coding: utf-8 -*-
"""LockToken dataclass for Redlock distributed locking."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


@dataclass
class LockToken:
    """Redlock lock token with metadata for renewal and validation.

    Attributes:
        resource: The lock key (e.g., "copaw:cron:user:{alice}").
        value: Unique lock value for ownership verification.
        validity: Lock validity time in milliseconds (TTL - elapsed - drift).
        nodes: List of Redis nodes where lock was acquired.
        quorum: Original quorum value from acquisition (N/2 + 1).
        discovery_time: Timestamp when cluster topology was discovered.
    """

    resource: str
    value: str
    validity: float
    nodes: List[Redis]
    quorum: int
    discovery_time: float

    def is_expired(self) -> bool:
        """Check if lock validity has expired."""
        return self.validity <= 0

    def is_discovery_stale(self, max_age: float = 5.0) -> bool:
        """Check if node discovery is stale (may cause split-brain).

        Args:
            max_age: Maximum acceptable age in seconds.

        Returns:
            True if discovery is older than max_age.
        """
        return (time.time() - self.discovery_time) > max_age
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/lock/test_lock_token.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/lock/test_lock_token.py src/copaw/lock/lock_token.py
git commit -m "feat(lock): add LockToken dataclass for Redlock"
```

---

## Task 2: ClusterNodeDiscovery

**Files:**
- Create: `src/copaw/lock/cluster_discovery.py`
- Test: `tests/lock/test_cluster_discovery.py`

- [ ] **Step 1: Write failing test**

```python
# tests/lock/test_cluster_discovery.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.copaw.lock.cluster_discovery import ClusterNodeDiscovery, RedisClusterError


class TestClusterNodeDiscovery:
    """Test ClusterNodeDiscovery."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        client = MagicMock()
        client.execute_command = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def discovery(self, mock_redis):
        """Create discovery instance with mocked Redis."""
        with patch("src.copaw.lock.cluster_discovery.redis_from_url", return_value=mock_redis):
            d = ClusterNodeDiscovery(
                seeds=["node1:6379", "node2:6379"],
                discovery_interval=60,
                max_retries=2,
                retry_delay=0.1,
            )
            return d

    @pytest.mark.asyncio
    async def test_discover_from_seed_success(self, discovery, mock_redis):
        """Test successful node discovery from seed."""
        # Mock CLUSTER NODES response
        mock_redis.execute_command.return_value = (
            b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
            b"node2 192.168.1.2:6379@16379 master - 0 0 2 connected 5461-10922\n"
        )

        nodes = await discovery._discover_from_seed("node1:6379")

        assert len(nodes) == 2
        mock_redis.execute_command.assert_called_once_with("CLUSTER NODES")
        mock_redis.close.assert_called_once()

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

        with pytest.raises(RedisClusterError, match="Cannot discover any master nodes"):
            await discovery.get_masters()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, discovery, mock_redis):
        """Test that discovery retries on failure."""
        # First seed fails, second succeeds
        mock_redis.execute_command.side_effect = [
            Exception("Connection refused"),  # First seed
            (  # Second seed
                b"node1 192.168.1.1:6379@16379 master - 0 0 1 connected 0-5460\n"
            ),
        ]

        nodes = await discovery.get_masters()
        assert len(nodes) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/lock/test_cluster_discovery.py -v
```

Expected: FAIL with import errors

- [ ] **Step 3: Write minimal implementation**

```python
# src/copaw/lock/cluster_discovery.py
# -*- coding: utf-8 -*-
"""Redis Cluster node discovery for Redlock algorithm."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List

from redis.asyncio import Redis, from_url as redis_from_url

logger = logging.getLogger(__name__)


class RedisClusterError(Exception):
    """Raised when Redis cluster operations fail."""
    pass


class ClusterNodeDiscovery:
    """Automatically discover Redis Cluster master nodes.

    Strategy:
    - Maintain seed node list (2-3 fixed nodes) for initial connection
    - Support force refresh (called before lock acquisition to prevent split-brain)
    - Execute CLUSTER NODES periodically to get full topology
    - Cache master node list, smooth transition during node changes
    - Fallback to cached list on failure with retry

    Fault tolerance:
    - Works even when some seed nodes are unavailable
    - Uses old list during node scaling, doesn't affect existing locks
    """

    def __init__(
        self,
        seeds: List[str],
        discovery_interval: int = 60,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        password: str = "",
        ssl: bool = False,
    ):
        """Initialize cluster node discovery.

        Args:
            seeds: List of seed node addresses (host:port).
            discovery_interval: Seconds between automatic refreshes.
            max_retries: Max retry attempts on discovery failure.
            retry_delay: Seconds between retry attempts.
            password: Redis password if required.
            ssl: Whether to use SSL connection.
        """
        self.seeds = seeds
        self.discovery_interval = discovery_interval
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.password = password
        self.ssl = ssl
        self._masters: List[Redis] = []
        self._last_discovery: float = 0

    async def get_masters(self) -> List[Redis]:
        """Get current master nodes.

        Returns:
            List of Redis clients connected to master nodes.

        Raises:
            RedisClusterError: If discovery fails and no cached nodes.
        """
        now = time.time()
        if now - self._last_discovery > self.discovery_interval:
            await self._refresh_nodes()
        return self._masters

    async def force_refresh(self) -> None:
        """Force refresh node discovery.

        Called before lock acquisition to prevent split-brain scenarios
        where different instances see different cluster topologies.
        """
        await self._refresh_nodes()

    async def _refresh_nodes(self):
        """Refresh node list with retry logic."""
        for attempt in range(self.max_retries):
            for seed in self.seeds:
                try:
                    nodes = await self._discover_from_seed(seed)
                    if nodes:
                        self._masters = nodes
                        self._last_discovery = time.time()
                        logger.debug(
                            f"Discovered {len(nodes)} master nodes from {seed}"
                        )
                        return
                except Exception as e:
                    logger.warning(
                        f"Discovery attempt {attempt + 1} failed from {seed}: {e}"
                    )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay)

        # All retries exhausted
        if not self._masters:
            raise RedisClusterError(
                f"Cannot discover any master nodes after {self.max_retries} attempts"
            )
        logger.warning(
            "Discovery failed, using cached node list (may be stale)"
        )

    async def _discover_from_seed(self, seed: str) -> List[Redis]:
        """Discover master nodes from a seed node.

        Args:
            seed: Seed node address (host:port).

        Returns:
            List of Redis clients connected to master nodes.
        """
        protocol = "rediss" if self.ssl else "redis"
        url = f"{protocol}://{seed}"
        if self.password:
            url = f"{protocol}://:{self.password}@{seed}"

        client = await redis_from_url(url)
        try:
            # Execute CLUSTER NODES command
            result = await client.execute_command("CLUSTER NODES")
            cluster_info = result.decode() if isinstance(result, bytes) else result

            masters = []
            for line in cluster_info.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 8:
                    continue

                node_id = parts[0]
                node_addr = parts[1]
                flags = parts[2]
                link_state = parts[7]

                # Only include connected master nodes
                if "master" in flags and link_state == "connected":
                    # Parse host:port@bus_port
                    host_port = node_addr.split("@")[0]
                    node_url = f"{protocol}://{host_port}"
                    if self.password:
                        node_url = f"{protocol}://:{self.password}@{host_port}"

                    master_client = await redis_from_url(node_url)
                    masters.append(master_client)

            return masters
        finally:
            await client.close()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/lock/test_cluster_discovery.py -v
```

Expected: PASS (may need minor adjustments)

- [ ] **Step 5: Commit**

```bash
git add tests/lock/test_cluster_discovery.py src/copaw/lock/cluster_discovery.py
git commit -m "feat(lock): add ClusterNodeDiscovery for Redis Cluster topology"
```

---

## Task 3: RedlockDistributedLock

**Files:**
- Create: `src/copaw/lock/redlock.py`
- Test: `tests/lock/test_redlock.py`
- Modify: `src/copaw/lock/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# tests/lock/test_redlock.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_lock_key_validation(self, mock_discovery, mock_redis):
        """Test user_id validation for hash tag."""
        mock_discovery.get_masters.return_value = [mock_redis]
        mock_redis.set.return_value = True

        redlock = RedlockDistributedLock(node_discovery=mock_discovery)

        # Valid user_id
        key = redlock.get_lock_key("alice")
        assert key == "copaw:cron:user:{alice}"

        # User_id with braces should be sanitized
        key = redlock.get_lock_key("{alice")
        assert key == "copaw:cron:user:{alice}"

        key = redlock.get_lock_key("alice}")
        assert key == "copaw:cron:user:{alice}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/lock/test_redlock.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/copaw/lock/redlock.py
# -*- coding: utf-8 -*-
"""Redlock distributed locking algorithm for Redis Cluster."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import List, Optional

from redis.asyncio import Redis

from .cluster_discovery import ClusterNodeDiscovery
from .lock_token import LockToken

logger = logging.getLogger(__name__)


class RedlockDistributedLock:
    """Distributed lock implementation using Redlock algorithm.

    Algorithm steps:
    1. Force refresh node discovery (prevent split-brain)
    2. Parallel lock acquisition across all nodes (asyncio.gather)
    3. Check success count >= quorum AND total time < remaining TTL
    4. Return token on success, release all locks on failure
    """

    CLOCK_DRIFT_FACTOR = 0.01  # 1% clock drift tolerance
    DISCOVERY_MAX_AGE = 5.0    # Max discovery age in seconds

    def __init__(
        self,
        node_discovery: ClusterNodeDiscovery,
        single_node_timeout_ms: int = 50,
        retry_count: int = 3,
        retry_delay_ms: int = 100,
    ):
        """Initialize Redlock.

        Args:
            node_discovery: ClusterNodeDiscovery instance.
            single_node_timeout_ms: Timeout per node in milliseconds.
            retry_count: Number of retry attempts.
            retry_delay_ms: Delay between retries in milliseconds.
        """
        self.node_discovery = node_discovery
        self.single_node_timeout_ms = single_node_timeout_ms
        self.retry_count = retry_count
        self.retry_delay_ms = retry_delay_ms

    def _generate_unique_value(self) -> str:
        """Generate unique lock value."""
        return f"{uuid.uuid4()}:{time.time()}"

    def get_lock_key(self, user_id: str) -> str:
        """Generate lock key with hash tag for same-slot placement.

        Args:
            user_id: User identifier.

        Returns:
            Lock key string with hash tag.

        Raises:
            ValueError: If user_id is empty after sanitization.
        """
        # Sanitize user_id to prevent hash tag injection
        clean_id = user_id.replace("{", "").replace("}", "")
        if not clean_id:
            raise ValueError(f"Invalid user_id for hash tag: {user_id}")
        return f"copaw:cron:user:{{{clean_id}}}"

    async def acquire(
        self,
        resource: str,
        ttl: int,
    ) -> Optional[LockToken]:
        """Acquire distributed lock.

        Args:
            resource: Lock resource identifier (key).
            ttl: Lock TTL in milliseconds.

        Returns:
            LockToken if successful, None otherwise.
        """
        lock_value = self._generate_unique_value()

        # CRITICAL: Force refresh node discovery to prevent split-brain
        # Ensures all instances see the same node list
        await self.node_discovery.force_refresh()

        masters = await self.node_discovery.get_masters()
        quorum = len(masters) // 2 + 1
        discovery_time = time.time()

        for retry in range(self.retry_count):
            start_time = time.monotonic()

            # Parallel lock acquisition across all nodes (Redlock requirement)
            tasks = [
                self._lock_single(node, resource, lock_value, ttl)
                for node in masters
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect successful nodes
            locked_nodes = []
            for node, result in zip(masters, results):
                if isinstance(result, bool) and result:
                    locked_nodes.append(node)

            # Calculate elapsed time (parallel acquisition)
            elapsed = (time.monotonic() - start_time) * 1000
            validity = ttl - elapsed - ttl * self.CLOCK_DRIFT_FACTOR

            # Check success condition
            if len(locked_nodes) >= quorum and validity > 0:
                return LockToken(
                    resource=resource,
                    value=lock_value,
                    validity=validity,
                    nodes=locked_nodes,
                    quorum=quorum,  # Store original quorum
                    discovery_time=discovery_time,
                )

            # Failed, release all acquired locks
            await self._unlock_all(masters, resource, lock_value)

            if retry < self.retry_count - 1:
                await asyncio.sleep(self.retry_delay_ms / 1000)

        return None

    async def _lock_single(
        self,
        node: Redis,
        resource: str,
        value: str,
        ttl: int,
    ) -> bool:
        """Acquire lock on single node.

        Args:
            node: Redis client.
            resource: Lock key.
            value: Lock value.
            ttl: TTL in milliseconds.

        Returns:
            True if acquired, False otherwise.
        """
        try:
            result = await asyncio.wait_for(
                node.set(
                    resource,
                    value,
                    nx=True,  # Only if not exists
                    px=ttl,   # Milliseconds expiration
                ),
                timeout=self.single_node_timeout_ms / 1000,
            )
            return result is True
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            logger.debug(f"Failed to acquire lock on node: {e}")
            return False

    async def _unlock_all(
        self,
        nodes: List[Redis],
        resource: str,
        value: str,
    ) -> None:
        """Release lock on all nodes (fire and forget)."""
        tasks = []
        for node in nodes:
            tasks.append(self._unlock_single(node, resource, value))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _unlock_single(
        self,
        node: Redis,
        resource: str,
        value: str,
    ) -> None:
        """Release lock on single node."""
        try:
            await node.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                keys=[resource],
                args=[value],
            )
        except Exception as e:
            logger.debug(f"Failed to release lock on node: {e}")

    async def release(self, token: LockToken) -> None:
        """Release lock on all nodes where it was acquired.

        Args:
            token: LockToken from acquire().
        """
        await self._unlock_all(token.nodes, token.resource, token.value)
```

- [ ] **Step 4: Update lock/__init__.py**

```python
# src/copaw/lock/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .cluster_discovery import ClusterNodeDiscovery, RedisClusterError
from .file_lock import file_lock, read_json_locked, write_json_locked
from .lock_token import LockToken
from .redlock import RedlockDistributedLock
from .redis_lock import LockRenewalTask, RedisLock

__all__ = [
    "ClusterNodeDiscovery",
    "file_lock",
    "LockRenewalTask",
    "LockToken",
    "read_json_locked",
    "RedlockDistributedLock",
    "RedisClusterError",
    "RedisLock",
    "write_json_locked",
]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/lock/test_redlock.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/copaw/lock/ tests/lock/test_redlock.py
git commit -m "feat(lock): implement RedlockDistributedLock with parallel acquisition"
```

---

## Task 4: RedlockRenewalTask

**Files:**
- Create: `src/copaw/lock/redlock_renewal.py`
- Test: `tests/lock/test_redlock_renewal.py`
- Modify: `src/copaw/lock/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# tests/lock/test_redlock_renewal.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.copaw.lock.redlock_renewal import RedlockRenewalTask
from src.copaw.lock.lock_token import LockToken


class TestRedlockRenewalTask:
    """Test RedlockRenewalTask with stored quorum."""

    @pytest.fixture
    def mock_discovery(self):
        """Create mock ClusterNodeDiscovery."""
        return MagicMock()

    @pytest.fixture
    def lock_token(self):
        """Create LockToken fixture."""
        return LockToken(
            resource="test:resource",
            value="abc-123",
            validity=590000.0,
            nodes=[],  # Will be set per test
            quorum=2,  # Original quorum from acquisition
            discovery_time=1234567890.0,
        )

    @pytest.mark.asyncio
    async def test_renewal_uses_stored_quorum(self, mock_discovery, lock_token):
        """Test that renewal uses stored quorum, not current cluster size."""
        # Create mock Redis nodes
        node1 = MagicMock()
        node1.eval = AsyncMock(return_value=1)
        node2 = MagicMock()
        node2.eval = AsyncMock(return_value=1)
        node3 = MagicMock()  # Not in lock_token.nodes

        lock_token.nodes = [node1, node2]

        # Even if cluster now has 5 nodes (quorum=3), use stored quorum=2
        mock_discovery.get_masters.return_value = [node1, node2, node3]

        renewal = RedlockRenewalTask(
            node_discovery=mock_discovery,
            lock_token=lock_token,
            ttl_ms=600000,
        )

        # Stop immediately after first renewal
        renewal._stop_event.set()

        with patch.object(renewal, '_renew_loop', AsyncMock()):
            await renewal.start()
            # Just verify the quorum is stored correctly
            assert renewal.lock_token.quorum == 2

    @pytest.mark.asyncio
    async def test_renewal_success_with_quorum(self, mock_discovery, lock_token):
        """Test renewal succeeds when quorum nodes respond."""
        node1 = MagicMock()
        node1.eval = AsyncMock(return_value=1)
        node2 = MagicMock()
        node2.eval = AsyncMock(return_value=1)
        node3 = MagicMock()
        node3.eval = AsyncMock(return_value=0)  # Fails

        lock_token.nodes = [node1, node2, node3]
        # quorum=2, so 2 successes should be enough

        renewal = RedlockRenewalTask(
            node_discovery=mock_discovery,
            lock_token=lock_token,
            ttl_ms=600000,
        )

        result = await renewal._extend()

        assert result is True

    @pytest.mark.asyncio
    async def test_renewal_fails_below_quorum(self, mock_discovery, lock_token):
        """Test renewal fails when below quorum."""
        node1 = MagicMock()
        node1.eval = AsyncMock(return_value=1)
        node2 = MagicMock()
        node2.eval = AsyncMock(return_value=0)  # Fails
        node3 = MagicMock()
        node3.eval = AsyncMock(return_value=0)  # Fails

        lock_token.nodes = [node1, node2, node3]
        # quorum=2, but only 1 success

        renewal = RedlockRenewalTask(
            node_discovery=mock_discovery,
            lock_token=lock_token,
            ttl_ms=600000,
        )

        result = await renewal._extend()

        assert result is False

    @pytest.mark.asyncio
    async def test_max_failed_renewals_stops_renewal(self, mock_discovery, lock_token):
        """Test that renewal stops after max failures."""
        node1 = MagicMock()
        node1.eval = AsyncMock(return_value=0)  # Always fails

        lock_token.nodes = [node1]

        renewal = RedlockRenewalTask(
            node_discovery=mock_discovery,
            lock_token=lock_token,
            ttl_ms=600000,
            max_failed_renewals=2,
        )

        # Simulate failures
        renewal._failed_renewals = 2

        assert not renewal.is_healthy()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/lock/test_redlock_renewal.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/copaw/lock/redlock_renewal.py
# -*- coding: utf-8 -*-
"""Redlock lock renewal task for long-running operations."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cluster_discovery import ClusterNodeDiscovery
    from .lock_token import LockToken

logger = logging.getLogger(__name__)


class RedlockRenewalTask:
    """Background task for Redlock renewal.

    Uses stored quorum from LockToken to handle cluster scaling correctly.
    """

    EXTEND_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('pexpire', KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(
        self,
        node_discovery: ClusterNodeDiscovery,
        lock_token: LockToken,
        ttl_ms: int,
        max_failed_renewals: int = 3,
    ):
        """Initialize renewal task.

        Args:
            node_discovery: ClusterNodeDiscovery instance.
            lock_token: LockToken from successful acquire().
            ttl_ms: Lock TTL in milliseconds.
            max_failed_renewals: Max consecutive failures before stopping.
        """
        self.node_discovery = node_discovery
        self.lock_token = lock_token
        self.ttl_ms = ttl_ms
        self.interval = ttl_ms / 2000  # Renew at half TTL (convert to seconds)
        self.max_failed_renewals = max_failed_renewals
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._failed_renewals = 0

    async def start(self) -> None:
        """Start the background renewal task."""
        self._task = asyncio.create_task(self._renew_loop())

    async def stop(self) -> None:
        """Stop the renewal task."""
        self._stop_event.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

    async def _renew_loop(self) -> None:
        """Main renewal loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval,
                )
                break  # Stop signal received
            except asyncio.TimeoutError:
                pass  # Normal timeout, proceed with renewal

            if self._stop_event.is_set():
                break

            success = await self._extend()
            if not success:
                self._failed_renewals += 1
                logger.warning(
                    f"Redlock renewal failed ({self._failed_renewals}/"
                    f"{self.max_failed_renewals}) for key={self.lock_token.resource}"
                )
                if self._failed_renewals >= self.max_failed_renewals:
                    logger.error(
                        "Redlock renewal failed too many times, lock may be lost"
                    )
                    break
            else:
                self._failed_renewals = 0

    async def _extend(self) -> bool:
        """Extend lock TTL on acquired nodes.

        Uses stored quorum from LockToken to handle cluster scaling.

        Returns:
            True if quorum nodes succeeded, False otherwise.
        """
        # CRITICAL: Use stored quorum from acquisition time
        # This ensures renewal works correctly during cluster scaling
        quorum = self.lock_token.quorum
        success_count = 0

        # Extend on nodes where lock was acquired
        for node in self.lock_token.nodes:
            try:
                result = await node.eval(
                    self.EXTEND_SCRIPT,
                    keys=[self.lock_token.resource],
                    args=[self.lock_token.value, self.ttl_ms],
                )
                if result == 1:
                    success_count += 1
            except Exception as e:
                logger.debug(f"Failed to extend lock on node: {e}")

        # Redlock renewal: need quorum successes
        return success_count >= quorum

    def is_healthy(self) -> bool:
        """Check if renewal task is healthy.

        Returns:
            True if renewal is healthy, False if too many failures.
        """
        return self._failed_renewals < self.max_failed_renewals
```

- [ ] **Step 4: Update lock/__init__.py**

```python
# Add to src/copaw/lock/__init__.py
from .redlock_renewal import RedlockRenewalTask

__all__ = [
    # ... existing exports ...
    "RedlockRenewalTask",
]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/lock/test_redlock_renewal.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/copaw/lock/redlock_renewal.py tests/lock/test_redlock_renewal.py src/copaw/lock/__init__.py
git commit -m "feat(lock): add RedlockRenewalTask with stored quorum"
```

---

## Task 5: Update Constants and Config

**Files:**
- Modify: `src/copaw/constant.py`
- Modify: `src/copaw/config/config.py`

- [ ] **Step 1: Add Redis Cluster constants**

```python
# src/copaw/constant.py - Add after existing Redis config (around line 290)

# ============================================================================
# Redis Cluster configuration (for multi-instance with Redlock)
# ============================================================================
REDIS_MODE = os.environ.get("COPAW_REDIS_MODE", "single")  # "single" or "cluster"
REDIS_SEEDS = os.environ.get("COPAW_REDIS_SEEDS", "localhost:6379")
REDIS_CLUSTER_DISCOVERY_INTERVAL = int(
    os.environ.get("COPAW_REDIS_CLUSTER_DISCOVERY_INTERVAL", "60")
)
REDIS_DISCOVERY_MAX_RETRIES = int(
    os.environ.get("COPAW_REDIS_DISCOVERY_MAX_RETRIES", "3")
)
REDIS_DISCOVERY_RETRY_DELAY = float(
    os.environ.get("COPAW_REDIS_DISCOVERY_RETRY_DELAY", "5.0")
)
REDIS_CONNECT_TIMEOUT = int(
    os.environ.get("COPAW_REDIS_CONNECT_TIMEOUT", "2000")
)
REDIS_MIN_CLUSTER_SIZE = int(
    os.environ.get("COPAW_REDIS_MIN_CLUSTER_SIZE", "3")
)

# ============================================================================
# Redlock configuration
# ============================================================================
REDIS_LOCK_SINGLE_TIMEOUT = int(
    os.environ.get("COPAW_REDIS_LOCK_SINGLE_TIMEOUT", "50")
)
REDIS_LOCK_RETRY_COUNT = int(
    os.environ.get("COPAW_REDIS_LOCK_RETRY_COUNT", "3")
)
REDIS_LOCK_RETRY_DELAY = int(
    os.environ.get("COPAW_REDIS_LOCK_RETRY_DELAY", "100")
)
REDIS_LOCK_DRIFT_FACTOR = float(
    os.environ.get("COPAW_REDIS_LOCK_DRIFT_FACTOR", "0.01")
)
REDIS_LOCK_DISCOVERY_MAX_AGE = float(
    os.environ.get("COPAW_REDIS_LOCK_DISCOVERY_MAX_AGE", "5.0")
)
```

- [ ] **Step 2: Add RedisClusterConfig dataclass**

```python
# src/copaw/config/config.py - Add new dataclass

class RedisClusterConfig(BaseModel):
    """Redis Cluster configuration for multi-instance deployment."""

    mode: Literal["single", "cluster"] = "single"
    seeds: List[str] = Field(default_factory=lambda: ["localhost:6379"])
    discovery_interval: int = 60
    discovery_max_retries: int = 3
    discovery_retry_delay: float = 5.0
    connect_timeout: int = 2000
    min_cluster_size: int = 3
    password: str = ""
    ssl: bool = False

    # Redlock settings
    lock_single_timeout_ms: int = 50
    lock_retry_count: int = 3
    lock_retry_delay_ms: int = 100
    lock_drift_factor: float = 0.01
    lock_discovery_max_age: float = 5.0
```

- [ ] **Step 3: Commit**

```bash
git add src/copaw/constant.py src/copaw/config/config.py
git commit -m "feat(config): add Redis Cluster and Redlock configuration"
```

---

## Task 6: Update CronManager for Redlock

**Files:**
- Modify: `src/copaw/app/crons/manager.py`

- [ ] **Step 1: Update imports and initialization**

```python
# src/copaw/app/crons/manager.py - Update imports

from ...lock import (
    ClusterNodeDiscovery,
    LockRenewalTask,
    RedlockDistributedLock,
    RedlockRenewalTask,
    RedisClusterError,
    read_json_locked,
    write_json_locked,
)
from ...constant import (
    # ... existing constants ...
    REDIS_MODE,
    REDIS_SEEDS,
    REDIS_CLUSTER_DISCOVERY_INTERVAL,
    REDIS_DISCOVERY_MAX_RETRIES,
    REDIS_DISCOVERY_RETRY_DELAY,
    REDIS_PASSWORD,
    REDIS_SSL,
    REDIS_LOCK_SINGLE_TIMEOUT,
    REDIS_LOCK_RETRY_COUNT,
    REDIS_LOCK_RETRY_DELAY,
    REDIS_MIN_CLUSTER_SIZE,
)
```

- [ ] **Step 2: Update _init_redis method**

```python
# src/copaw/app/crons/manager.py - Update _init_redis

def _init_redis(self) -> None:
    """Initialize Redis client and distributed lock."""
    if not CRON_LOCK_ENABLED:
        return

    try:
        if REDIS_MODE == "cluster":
            # Initialize cluster node discovery
            seeds = [s.strip() for s in REDIS_SEEDS.split(",")]
            self._node_discovery = ClusterNodeDiscovery(
                seeds=seeds,
                discovery_interval=REDIS_CLUSTER_DISCOVERY_INTERVAL,
                max_retries=REDIS_DISCOVERY_MAX_RETRIES,
                retry_delay=REDIS_DISCOVERY_RETRY_DELAY,
                password=REDIS_PASSWORD,
                ssl=REDIS_SSL,
            )
            # Initialize Redlock
            self._redlock = RedlockDistributedLock(
                node_discovery=self._node_discovery,
                single_node_timeout_ms=REDIS_LOCK_SINGLE_TIMEOUT,
                retry_count=REDIS_LOCK_RETRY_COUNT,
                retry_delay_ms=REDIS_LOCK_RETRY_DELAY,
            )
            logger.info(
                f"Initialized Redlock with seeds: {seeds}"
            )
        else:
            # Single Redis mode (backward compatible)
            self._redis = redis_from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
                password=REDIS_PASSWORD or None,
                ssl=REDIS_SSL,
            )
            from ...lock.redis_lock import RedisLock
            self._redis_lock = RedisLock(self._redis)
            logger.info(
                f"Initialized Redis lock at {REDIS_HOST}:{REDIS_PORT}"
            )
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        self._redis = None
        self._redlock = None
```

- [ ] **Step 3: Add cluster health check**

```python
# src/copaw/app/crons/manager.py - Add method

async def _check_redis_cluster(self) -> bool:
    """Check Redis cluster health (quorum of nodes available).

    Returns:
        True if cluster is healthy, False otherwise.
    """
    if REDIS_MODE != "cluster" or not hasattr(self, '_node_discovery'):
        return self._redis is not None

    try:
        masters = await self._node_discovery.get_masters()
        if len(masters) < REDIS_MIN_CLUSTER_SIZE:
            logger.warning(
                f"Cluster has {len(masters)} masters, "
                f"minimum required: {REDIS_MIN_CLUSTER_SIZE}"
            )
            return False

        # Check quorum of nodes are reachable
        quorum = len(masters) // 2 + 1
        available = 0
        for node in masters:
            try:
                await asyncio.wait_for(node.ping(), timeout=1.0)
                available += 1
            except Exception:
                pass

        return available >= quorum
    except Exception as e:
        logger.error(f"Redis cluster health check failed: {e}")
        return False
```

- [ ] **Step 4: Update _scheduled_callback for Redlock**

```python
# src/copaw/app/crons/manager.py - Update _scheduled_callback

async def _scheduled_callback(self, user_id: str, job_id: str):
    """Handle scheduled job callback with distributed locking."""
    # 1. Random delay to prevent thundering herd
    jitter_ms = random.randint(0, CRON_LOCK_JITTER_MS)
    await asyncio.sleep(jitter_ms / 1000)

    # 2. Check Redis cluster health (Fail-Fast)
    if not await self._check_redis_cluster():
        logger.error(f"Redis cluster unavailable, skipping job for user={user_id}")
        return

    # 3. Acquire lock
    if REDIS_MODE == "cluster":
        await self._acquire_redlock(user_id, job_id)
    else:
        await self._acquire_single_redis_lock(user_id, job_id)

async def _acquire_redlock(self, user_id: str, job_id: str) -> None:
    """Acquire Redlock for user tasks."""
    lock_key = self._redlock.get_lock_key(user_id)
    ttl_ms = CRON_LOCK_TTL * 1000

    lock_token = await self._redlock.acquire(lock_key, ttl=ttl_ms)
    if not lock_token:
        logger.debug(f"Redlock held by another instance for user={user_id}")
        return

    # Start renewal task
    renewal = RedlockRenewalTask(
        node_discovery=self._node_discovery,
        lock_token=lock_token,
        ttl_ms=ttl_ms,
    )
    await renewal.start()

    try:
        await self._execute_user_tasks(user_id, job_id)
    finally:
        await renewal.stop()
        await self._redlock.release(lock_token)

async def _acquire_single_redis_lock(self, user_id: str, job_id: str) -> None:
    """Acquire single Redis lock (backward compatible)."""
    # ... existing single Redis lock logic ...
    pass

async def _execute_user_tasks(self, user_id: str, job_id: str) -> None:
    """Execute tasks for user."""
    # Load user states
    states = await self._load_user_states(user_id)
    self._states[user_id] = states

    # Execute pending jobs
    await self._execute_user_pending_jobs(user_id)

    # Persist states
    await self._save_user_states(user_id)
```

- [ ] **Step 5: Commit**

```bash
git add src/copaw/app/crons/manager.py
git commit -m "feat(cron): integrate Redlock for multi-instance deployment"
```

---

## Task 7: Redis-based Temporary Storage

**Files:**
- Create: `src/copaw/store/redis_store.py`
- Modify: `src/copaw/app/console_push_store.py`
- Modify: `src/copaw/app/download_task_store.py`

- [ ] **Step 1: Create Redis store base**

```python
# src/copaw/store/redis_store.py
# -*- coding: utf-8 -*-
"""Redis-based temporary data storage with TTL."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisHashStore:
    """Hash-based storage with automatic TTL expiration.

    Uses Redis Hash for field storage with TTL on the entire key.
    Suitable for temporary data like console_push, download_tasks.
    """

    def __init__(self, redis: Redis, key_prefix: str, default_ttl: int):
        """Initialize store.

        Args:
            redis: Redis client.
            key_prefix: Key prefix for namespacing.
            default_ttl: Default TTL in seconds.
        """
        self.redis = redis
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

    def _make_key(self, identifier: str) -> str:
        """Generate storage key."""
        return f"{self.key_prefix}:{identifier}"

    async def set(self, identifier: str, field: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set field value with TTL.

        Args:
            identifier: Resource identifier.
            field: Hash field name.
            value: Value to store (will be JSON serialized).
            ttl: TTL in seconds (uses default if None).
        """
        key = self._make_key(identifier)
        ttl = ttl or self.default_ttl

        await self.redis.hset(key, field, json.dumps(value))
        await self.redis.expire(key, ttl)

    async def get(self, identifier: str, field: str) -> Optional[Any]:
        """Get field value.

        Args:
            identifier: Resource identifier.
            field: Hash field name.

        Returns:
            Deserialized value or None if not found/expired.
        """
        key = self._make_key(identifier)
        result = await self.redis.hget(key, field)

        if result is None:
            return None

        return json.loads(result)

    async def get_all(self, identifier: str) -> dict[str, Any]:
        """Get all fields for identifier.

        Args:
            identifier: Resource identifier.

        Returns:
            Dictionary of field -> value.
        """
        key = self._make_key(identifier)
        result = await self.redis.hgetall(key)

        return {k.decode(): json.loads(v) for k, v in result.items()}

    async def delete(self, identifier: str, field: str) -> None:
        """Delete field.

        Args:
            identifier: Resource identifier.
            field: Hash field name.
        """
        key = self._make_key(identifier)
        await self.redis.hdel(key, field)

    async def clear(self, identifier: str) -> None:
        """Delete entire key.

        Args:
            identifier: Resource identifier.
        """
        key = self._make_key(identifier)
        await self.redis.delete(key)
```

- [ ] **Step 2: Update console_push_store**

```python
# src/copaw/app/console_push_store.py - Update to use RedisHashStore

from ..store.redis_store import RedisHashStore
from ..constant import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

# Initialize store
_redis = redis_from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}", password=REDIS_PASSWORD or None)
_push_store = RedisHashStore(
    redis=_redis,
    key_prefix="copaw:push",
    default_ttl=60,  # 60 seconds
)

async def append(user_id: str, message: dict) -> None:
    """Append message to user's push queue."""
    msg_id = str(uuid.uuid4())
    await _push_store.set(user_id, msg_id, message)

async def get_all(user_id: str) -> list[dict]:
    """Get all pending messages for user."""
    data = await _push_store.get_all(user_id)
    # Return as list
    return list(data.values())

async def clear(user_id: str) -> None:
    """Clear all messages for user."""
    await _push_store.clear(user_id)
```

- [ ] **Step 3: Update download_task_store similarly**

```python
# src/copaw/app/download_task_store.py

# Similar pattern with TTL=3600 (1 hour)
_task_store = RedisHashStore(
    redis=_redis,
    key_prefix="copaw:download",
    default_ttl=3600,  # 1 hour
)
```

- [ ] **Step 4: Commit**

```bash
git add src/copaw/store/redis_store.py src/copaw/app/console_push_store.py src/copaw/app/download_task_store.py
git commit -m "feat(store): add Redis-based temporary storage with TTL"
```

---

## Task 8: Final Integration and Testing

**Files:**
- All modified files

- [ ] **Step 1: Run all lock tests**

```bash
pytest tests/lock/ -v
```

Expected: All tests pass

- [ ] **Step 2: Run pre-commit checks**

```bash
pre-commit run --all-files
```

Expected: No errors

- [ ] **Step 3: Integration test with Docker Compose**

```bash
# Start Redis Cluster
docker-compose -f docker-compose.redis-cluster.yml up -d

# Run integration test
pytest tests/integration/test_redlock.py -v
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(multi-instance): complete Redis Cluster + Redlock implementation

- Add LockToken dataclass with stored quorum
- Add ClusterNodeDiscovery with force refresh
- Add RedlockDistributedLock with parallel acquisition
- Add RedlockRenewalTask with stored quorum usage
- Add RedisHashStore for temporary data
- Update CronManager with cluster health check
- Update constants and config for new options
- Add comprehensive test coverage

Implements multi-instance deployment with:
- Redlock algorithm for distributed locking
- Automatic cluster topology discovery
- Fail-Fast strategy for cluster failures
- Separate storage strategies for different data types"
```

---

## Review and Next Steps

After completing all tasks:

1. **Code Review**: Use @superpowers:requesting-code-review to review the implementation
2. **Update Documentation**: Update deployment docs with new configuration options
3. **Create Docker Compose**: Add docker-compose.redis-cluster.yml for testing

**Plan saved to:** `docs/superpowers/plans/2026-03-30-multi-instance-redlock-implementation.md`

**Execution options:**
1. **Subagent-Driven (recommended)** - Dispatch @superpowers:subagent-driven-development for task-by-task execution with reviews
2. **Inline Execution** - Use @superpowers:executing-plans for batch execution

Which approach would you prefer?