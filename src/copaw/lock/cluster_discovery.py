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
                        # Close old connections before replacing
                        for old_client in self._masters:
                            try:
                                await old_client.aclose()
                            except Exception as e:
                                logger.debug(
                                    f"Failed to close old connection: {e}"
                                )

                        self._masters = nodes
                        self._last_discovery = time.time()
                        logger.debug(
                            f"Discovered {len(nodes)} master nodes from {seed}",
                        )
                        return
                except Exception as e:
                    logger.warning(
                        f"Discovery attempt {attempt + 1} failed from {seed}: {e}",
                    )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay)

        # All retries exhausted
        if not self._masters:
            raise RedisClusterError(
                f"Cannot discover any master nodes after {self.max_retries} attempts",
            )
        logger.warning(
            "Discovery failed, using cached node list (may be stale)",
        )

    async def aclose(self) -> None:
        """Close all Redis connections."""
        for client in self._masters:
            try:
                await client.aclose()
            except Exception as e:
                logger.debug(f"Failed to close connection: {e}")
        self._masters.clear()
        self._last_discovery = 0

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

            # Handle different response types from Redis client
            if isinstance(result, bytes):
                cluster_info = result.decode()
            elif isinstance(result, dict):
                # Some Redis client versions return parsed dict
                # Log warning and return empty to trigger retry/fallback
                logger.warning(
                    f"Unexpected dict response from CLUSTER NODES: {result}"
                )
                return []
            else:
                cluster_info = str(result)

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
            await client.aclose()
