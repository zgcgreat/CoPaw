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
