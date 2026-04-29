# -*- coding: utf-8 -*-
"""Redis-backed coordination for cron leadership and cron definition state.

This module provides primitives for:
- Agent lease: Leadership election per tenant+agent
- Lease preflight: Scheduler-originated ownership re-validation
- Legacy execution lock: Non-default timed execution compatibility surface
- Reload pub/sub: Notify leader of cron configuration changes
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, Optional, Any

logger = logging.getLogger(__name__)

# Optional Redis import - coordination is disabled if redis is not available
redis_lib: Any = None
ClusterNode: Any = None

REDIS_AVAILABLE = False
try:
    import redis.asyncio as _redis_lib
    from redis.asyncio.cluster import ClusterNode as _ClusterNode

    redis_lib = _redis_lib
    ClusterNode = _ClusterNode
    REDIS_AVAILABLE = True
except ImportError:
    pass


@dataclass
class CoordinationConfig:
    """Configuration for Redis coordination."""

    enabled: bool = False
    # Redis connection - supports both standalone and cluster modes
    redis_url: str = "redis://localhost:6379/0"
    redis_access: str = ""
    # Cluster mode configuration
    cluster_mode: bool = False
    cluster_nodes: Optional[
        list
    ] = None  # List of ClusterNode or dict {"host": str, "port": int}
    cluster_startup_nodes: Optional[list] = None
    # Additional cluster options
    cluster_skip_full_coverage_check: bool = True
    cluster_max_connections: int = 50
    # Lease configuration
    lease_ttl_seconds: int = 30
    lease_renew_interval_seconds: int = 10
    lease_renew_failure_threshold: int = 3
    # Execution lock configuration
    lock_ttl_seconds: int = 120  # Default, should be derived from job timeout
    lock_safety_margin_seconds: int = 30
    # Definition mutation lock configuration
    definition_lock_timeout_seconds: float = 10.0
    # Reload pub/sub configuration
    reload_channel_prefix: str = "swe:cron:reload"


class CronCoordinationError(Exception):
    """Base exception for coordination errors."""

    pass


class LeaseLostError(CronCoordinationError):
    """Raised when the agent lease is lost."""

    pass


class RedisNotAvailableError(CronCoordinationError):
    """Raised when Redis is not available but coordination is requested."""

    pass


class DefinitionLockTimeoutError(CronCoordinationError):
    """Raised when the definition mutation lock cannot be acquired in time."""

    pass


class AgentLease:
    """Redis-backed lease for cron leadership per tenant+agent.

    Only one instance can hold the lease for a given tenant+agent at a time.
    The lease must be periodically renewed. If renewal fails, the holder
    must deactivate scheduling.
    """

    def __init__(
        self,
        redis_client: Any,
        tenant_id: Optional[str],
        agent_id: str,
        instance_id: str,
        config: CoordinationConfig,
        on_lease_lost: Optional[Callable[[], None]] = None,
    ):
        self._redis = redis_client
        self._tenant_id = tenant_id or "default"
        self._agent_id = agent_id
        self._instance_id = instance_id
        self._config = config
        self._on_lease_lost = on_lease_lost

        self._key = f"swe:cron:lease:{self._tenant_id}:{agent_id}"
        self._owned = False
        self._renew_task: Optional[asyncio.Task] = None
        self._stop_renew = asyncio.Event()
        self._consecutive_failures = 0

    @property
    def is_owned(self) -> bool:
        """Check if this instance currently owns the lease."""
        return self._owned

    async def acquire(self) -> bool:
        """Attempt to acquire the lease.

        Returns True if lease was acquired, False otherwise.
        """
        if not REDIS_AVAILABLE:
            raise RedisNotAvailableError("Redis is not available")

        try:
            # Try to set the key with NX (only if not exists) and EX (expiry)
            acquired = await self._redis.set(
                self._key,
                self._instance_id,
                nx=True,
                ex=self._config.lease_ttl_seconds,
            )
            if acquired:
                self._owned = True
                self._consecutive_failures = 0
                logger.info(
                    "Acquired cron lease: tenant=%s agent=%s instance=%s",
                    self._tenant_id,
                    self._agent_id,
                    self._instance_id,
                )
                # Start background renewal task
                self._start_renewal()
                return True
            else:
                # Check if we already own it (maybe after restart)
                current = await self._redis.get(self._key)
                if current and current.decode() == self._instance_id:
                    self._owned = True
                    self._consecutive_failures = 0
                    logger.info(
                        "Reclaimed existing cron lease: tenant=%s agent=%s",
                        self._tenant_id,
                        self._agent_id,
                    )
                    self._start_renewal()
                    return True
                return False
        except Exception as e:
            logger.warning("Failed to acquire lease: %s", e)
            return False

    async def release(self) -> None:
        """Release the lease.

        Safe to call even if lease is not owned.
        """
        if not self._owned:
            return

        # Stop renewal first
        await self._stop_renewal()

        try:
            # Only delete if we still own it (compare instance_id)
            current = await self._redis.get(self._key)
            if current and current.decode() == self._instance_id:
                await self._redis.delete(self._key)
                logger.info(
                    "Released cron lease: tenant=%s agent=%s",
                    self._tenant_id,
                    self._agent_id,
                )
        except Exception as e:
            logger.warning("Error releasing lease: %s", e)
        finally:
            self._owned = False

    def _start_renewal(self) -> None:
        """Start the background lease renewal task."""
        if self._renew_task is not None:
            return
        self._stop_renew.clear()
        self._renew_task = asyncio.create_task(
            self._renew_loop(),
            name=f"lease-renew-{self._tenant_id}-{self._agent_id}",
        )

    async def _stop_renewal(self) -> None:
        """Stop the background lease renewal task."""
        if self._renew_task is None:
            return
        self._stop_renew.set()
        try:
            await asyncio.wait_for(self._renew_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
        self._renew_task = None

    async def _renew_loop(self) -> None:
        """Background task that periodically renews the lease."""
        lease_lost = False
        try:
            while not self._stop_renew.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_renew.wait(),
                        timeout=self._config.lease_renew_interval_seconds,
                    )
                    return  # Stop requested
                except asyncio.TimeoutError:
                    pass

                try:
                    # Renew the lease only if we still own it
                    current = await self._redis.get(self._key)
                    if not current or current.decode() != self._instance_id:
                        # Lease was stolen or expired
                        logger.warning(
                            "Lease lost (stolen or expired): tenant=%s agent=%s",
                            self._tenant_id,
                            self._agent_id,
                        )
                        self._owned = False
                        lease_lost = True
                        return

                    # Extend the lease
                    await self._redis.expire(
                        self._key,
                        self._config.lease_ttl_seconds,
                    )
                    self._consecutive_failures = 0
                    logger.debug(
                        "Renewed cron lease: tenant=%s agent=%s",
                        self._tenant_id,
                        self._agent_id,
                    )
                except Exception as e:
                    self._consecutive_failures += 1
                    logger.warning(
                        "Lease renewal failed (%d/%d): %s",
                        self._consecutive_failures,
                        self._config.lease_renew_failure_threshold,
                        e,
                    )
                    if (
                        self._consecutive_failures
                        >= self._config.lease_renew_failure_threshold
                    ):
                        logger.error(
                            "Lease renewal failed too many times, "
                            "considering lease lost: tenant=%s agent=%s",
                            self._tenant_id,
                            self._agent_id,
                        )
                        self._owned = False
                        lease_lost = True
                        return
        finally:
            # Call the lease lost callback if lease was lost
            if lease_lost and self._on_lease_lost is not None:
                try:
                    self._on_lease_lost()
                except Exception:  # pylint: disable=broad-except
                    logger.exception("Lease lost callback failed")


class ExecutionLock:
    """Redis-backed execution lock for timed job de-duplication.

    Prevents duplicate execution of the same timed job across instances
    during leadership transitions.
    """

    def __init__(
        self,
        redis_client: Any,
        tenant_id: Optional[str],
        agent_id: str,
        job_id: str,
        ttl_seconds: int,
    ):
        self._redis = redis_client
        self._tenant_id = tenant_id or "default"
        self._agent_id = agent_id
        self._job_id = job_id
        self._ttl_seconds = ttl_seconds
        self._key = f"swe:cron:exec:{self._tenant_id}:{agent_id}:{job_id}"

    @property
    def ttl_seconds(self) -> int:
        """Get the TTL of the execution lock in seconds."""
        return self._ttl_seconds

    async def acquire(self) -> bool:
        """Attempt to acquire the execution lock.

        Returns True if lock was acquired, False if already locked.
        """
        if not REDIS_AVAILABLE:
            raise RedisNotAvailableError("Redis is not available")

        try:
            # Try to set with NX (only if not exists)
            acquired = await self._redis.set(
                self._key,
                str(uuid.uuid4()),
                nx=True,
                ex=self._ttl_seconds,
            )
            return bool(acquired)
        except Exception as e:
            logger.warning("Failed to acquire execution lock: %s", e)
            # Fail safe: don't execute if we can't confirm lock
            return False

    async def release(self) -> None:
        """Release the execution lock."""
        try:
            await self._redis.delete(self._key)
        except Exception as e:
            logger.warning("Error releasing execution lock: %s", e)


class DefinitionLock:
    """Redis-backed lock for serializing jobs.json definition mutation."""

    def __init__(
        self,
        redis_client: Any,
        tenant_id: Optional[str],
        agent_id: str,
        ttl_seconds: int,
    ):
        self._redis = redis_client
        self._tenant_id = tenant_id or "default"
        self._agent_id = agent_id
        self._ttl_seconds = ttl_seconds
        self._token = str(uuid.uuid4())
        self._key = f"swe:cron:deflock:{self._tenant_id}:{agent_id}"

    async def acquire(self) -> bool:
        """Attempt to acquire the definition lock."""
        if not REDIS_AVAILABLE:
            raise RedisNotAvailableError("Redis is not available")

        try:
            acquired = await self._redis.set(
                self._key,
                self._token,
                nx=True,
                ex=self._ttl_seconds,
            )
            return bool(acquired)
        except Exception as e:
            raise CronCoordinationError(
                f"Failed to acquire definition lock: {e}",
            ) from e

    async def release(self) -> None:
        """Release the definition lock if still held by this lock token."""
        try:
            current = await self._redis.get(self._key)
            if not current:
                return
            owner = (
                current.decode()
                if isinstance(current, bytes)
                else str(current)
            )
            if owner == self._token:
                await self._redis.delete(self._key)
        except Exception as e:
            logger.warning("Error releasing definition lock: %s", e)


class ReloadPublisher:
    """Publishes reload signals for cron configuration changes."""

    def __init__(
        self,
        redis_client: Any,
        config: CoordinationConfig,
    ):
        self._redis = redis_client
        self._config = config

    async def publish(
        self,
        tenant_id: Optional[str],
        agent_id: str,
        version: Optional[int] = None,
    ) -> bool:
        """Publish a reload signal for the given tenant+agent.

        Returns True if published successfully, False otherwise.
        """
        if not REDIS_AVAILABLE:
            raise RedisNotAvailableError("Redis is not available")

        try:
            channel = f"{self._config.reload_channel_prefix}:{tenant_id or 'default'}:{agent_id}"
            message = json.dumps(
                {
                    "tenant_id": tenant_id or "default",
                    "agent_id": agent_id,
                    "definition_version": version,
                    "timestamp": str(uuid.uuid4()),  # Unique id for dedup
                },
            )
            await self._redis.publish(channel, message)
            logger.debug(
                "Published cron reload signal: tenant=%s agent=%s",
                tenant_id,
                agent_id,
            )
            return True
        except Exception as e:
            logger.warning("Failed to publish reload signal: %s", e)
            return False


class ReloadSubscriber:
    """Subscribes to reload signals for cron configuration changes."""

    def __init__(
        self,
        redis_client: Any,
        tenant_id: Optional[str],
        agent_id: str,
        config: CoordinationConfig,
        on_reload: Callable[[], None],
    ):
        self._redis = redis_client
        self._tenant_id = tenant_id or "default"
        self._agent_id = agent_id
        self._config = config
        self._on_reload = on_reload
        self._channel = (
            f"{config.reload_channel_prefix}:{self._tenant_id}:{agent_id}"
        )
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the subscriber."""
        if not REDIS_AVAILABLE:
            raise RedisNotAvailableError("Redis is not available")

        if self._task is not None:
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._subscribe_loop(),
            name=f"reload-sub-{self._tenant_id}-{self._agent_id}",
        )
        logger.debug(
            "Started reload subscriber: tenant=%s agent=%s",
            self._tenant_id,
            self._agent_id,
        )

    async def stop(self) -> None:
        """Stop the subscriber."""
        if self._task is None:
            return

        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.debug(
            "Stopped reload subscriber: tenant=%s agent=%s",
            self._tenant_id,
            self._agent_id,
        )

    async def _subscribe_loop(self) -> None:
        """Background task that listens for reload signals."""
        try:
            async with self._redis.pubsub() as pubsub:
                await pubsub.subscribe(self._channel)
                logger.info(
                    "Subscribed to reload channel: %s",
                    self._channel,
                )

                while not self._stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True),
                            timeout=1.0,
                        )
                        if message is not None:
                            logger.info(
                                "Received reload signal for tenant=%s agent=%s payload=%s",
                                self._tenant_id,
                                self._agent_id,
                                message.get("data"),
                            )
                            try:
                                self._on_reload()
                            except Exception:  # pylint: disable=broad-except
                                logger.exception("Reload callback failed")
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.warning("Redis error in subscribe loop: %s", e)
                        await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Subscribe loop failed")


class CronCoordination:
    """Main coordination interface for cron leadership and reload signaling.

    This class manages the lifecycle of:
    - Agent lease (leadership election)
    - Reload pub/sub (configuration change notifications)
    """

    def __init__(
        self,
        tenant_id: Optional[str],
        agent_id: str,
        config: CoordinationConfig,
    ):
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._config = config
        self._instance_id = str(uuid.uuid4())

        self._redis: Optional[Any] = None
        self._pubsub_client: Optional[Any] = None
        self._lease: Optional[AgentLease] = None
        self._reload_subscriber: Optional[ReloadSubscriber] = None
        self._on_reload: Optional[Callable[[], None]] = None
        self._on_lease_lost: Optional[Callable[[], None]] = None
        self._on_become_leader: Optional[Callable[[], None]] = None
        self._candidate_task: Optional[asyncio.Task] = None
        self._stop_candidate = asyncio.Event()

    @property
    def instance_id(self) -> str:
        """Get the unique instance ID."""
        return self._instance_id

    @property
    def is_leader(self) -> bool:
        """Check if this instance is the current leader."""
        if self._lease is None:
            return False
        return self._lease.is_owned

    async def preflight_scheduler_execution(
        self,
        *,
        job_id: str,
        schedule_type: str,
    ) -> bool:
        """Re-validate lease ownership immediately before scheduler work.

        Scheduler-originated cron and heartbeat handlers run under an
        at-least-once failover model. This preflight narrows obvious stale
        leader windows, but correctness still depends on handler idempotency.
        """
        if self._lease is None or not self._lease.is_owned:
            logger.info(
                "Scheduler preflight rejected: lease not owned "
                "(tenant=%s agent=%s schedule_type=%s job_id=%s)",
                self._tenant_id or "default",
                self._agent_id,
                schedule_type,
                job_id,
            )
            return False

        if self._redis is None:
            logger.warning(
                "Scheduler preflight rejected: Redis unavailable "
                "(tenant=%s agent=%s schedule_type=%s job_id=%s)",
                self._tenant_id or "default",
                self._agent_id,
                schedule_type,
                job_id,
            )
            return False

        try:
            current = await self._redis.get(self._lease._key)  # noqa: SLF001
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Scheduler preflight rejected: lease check failed "
                "(tenant=%s agent=%s schedule_type=%s job_id=%s error=%s)",
                self._tenant_id or "default",
                self._agent_id,
                schedule_type,
                job_id,
                exc,
            )
            return False

        if not current:
            logger.info(
                "Scheduler preflight rejected: lease key missing "
                "(tenant=%s agent=%s schedule_type=%s job_id=%s)",
                self._tenant_id or "default",
                self._agent_id,
                schedule_type,
                job_id,
            )
            return False

        owner = (
            current.decode() if isinstance(current, bytes) else str(current)
        )
        if owner != self._instance_id:
            logger.info(
                "Scheduler preflight rejected: lease owned by another instance "
                "(tenant=%s agent=%s schedule_type=%s job_id=%s owner=%s local=%s)",
                self._tenant_id or "default",
                self._agent_id,
                schedule_type,
                job_id,
                owner,
                self._instance_id,
            )
            return False
        return True

    async def connect(self) -> bool:
        """Connect to Redis (standalone or cluster mode).

        Returns True if connected successfully, False otherwise.
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis is not available (redis-py not installed)")
            return False

        if not self._config.enabled:
            logger.debug("Coordination is disabled in config")
            return False

        try:
            if self._config.cluster_mode:
                # Connect to Redis Cluster
                self._redis = await self._connect_cluster()
                # Create separate pub/sub client for cluster mode
                self._pubsub_client = await self._create_pubsub_client()
            else:
                # Connect to standalone Redis
                if redis_lib is None:
                    raise RedisNotAvailableError("Redis library not available")
                self._redis = redis_lib.from_url(
                    self._config.redis_url,
                    decode_responses=False,
                )
                # In standalone mode, use the same client for pub/sub
                self._pubsub_client = self._redis

            # Test connection
            if self._redis is not None:
                await self._redis.ping()
            logger.info(
                "Connected to Redis for cron coordination: %s (cluster=%s)",
                self._config.redis_url
                if not self._config.cluster_mode
                else "cluster",
                self._config.cluster_mode,
            )
            return True
        except Exception as e:
            logger.warning("Failed to connect to Redis: %s", e)
            self._redis = None
            self._pubsub_client = None
            return False

    def _build_cluster_startup_nodes(self) -> list:
        """Build list of ClusterNode objects from configuration.

        Returns:
            List of ClusterNode objects for RedisCluster startup.
        """
        if not ClusterNode:
            raise RedisNotAvailableError("ClusterNode not available")

        nodes = []

        # First try cluster_nodes from config
        if self._config.cluster_nodes:
            for node in self._config.cluster_nodes:
                if isinstance(node, dict):
                    nodes.append(
                        ClusterNode(
                            host=node["host"],
                            port=node.get("port", 6379),
                        ),
                    )
                elif isinstance(node, ClusterNode):
                    nodes.append(node)

        # Then try cluster_startup_nodes
        if not nodes and self._config.cluster_startup_nodes:
            for node in self._config.cluster_startup_nodes:
                if isinstance(node, dict):
                    nodes.append(
                        ClusterNode(
                            host=node["host"],
                            port=node.get("port", 6379),
                        ),
                    )
                elif isinstance(node, ClusterNode):
                    nodes.append(node)

        # Finally, parse from redis_url
        if not nodes:
            url = self._config.redis_url
            # Remove redis:// or rediss:// prefix
            if "://" in url:
                url = url.split("://", 1)[1]
            # Remove auth part if present (user:pass@host)
            if "@" in url:
                url = url.split("@", 1)[1]
            # Parse host:port pairs
            for host_port in url.split(","):
                if ":" in host_port:
                    host, port_str = host_port.rsplit(":", 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        port = 6379
                    nodes.append(ClusterNode(host=host, port=port))
                else:
                    nodes.append(ClusterNode(host=host_port, port=6379))

        return nodes

    def _parse_redis_url(self) -> dict:
        """Parse redis_url to extract connection parameters.

        For cluster mode with comma-separated URLs (host1:6379,host2:6380),
        only parses the first node for auth credentials.

        Returns:
            Dict with host, port, username, password, ssl, db.
        """
        import urllib.parse

        url = self._config.redis_url

        # For cluster mode with comma-separated nodes, extract just the first node
        # for auth parsing (e.g., redis://user:pass@host1:6379,host2:6380)
        if self._config.cluster_mode and "," in url:
            # Split and take first node, but preserve the scheme and auth
            if "://" in url:
                scheme, rest = url.split("://", 1)
                # rest might be: user:pass@host1:6379,host2:6380
                if "@" in rest:
                    auth, nodes = rest.split("@", 1)
                    first_node = nodes.split(",")[0]
                    url = f"{scheme}://{auth}@{first_node}"
                else:
                    first_node = rest.split(",")[0]
                    url = f"{scheme}://{first_node}"

        parsed = urllib.parse.urlparse(url)

        result = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 6379,
            "username": None,
            "password": None,
            "ssl": parsed.scheme == "rediss",
            "db": 0,
        }

        # Extract auth
        if parsed.username:
            result["username"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password

        # Extract db from path
        if parsed.path and parsed.path.strip("/"):
            try:
                result["db"] = int(parsed.path.strip("/"))
            except ValueError:
                pass

        return result

    async def _connect_cluster(self) -> Any:
        """Connect to Redis Cluster.

        Returns Redis cluster client.
        """
        if not redis_lib:
            raise RedisNotAvailableError("Redis library not available")

        # Import cluster-specific classes
        from redis.asyncio.cluster import RedisCluster

        # Build startup nodes as ClusterNode objects
        startup_nodes = self._build_cluster_startup_nodes()

        if not startup_nodes:
            raise RedisNotAvailableError(
                "No cluster nodes configured. "
                "Please set cluster_nodes or provide nodes in redis_url.",
            )

        # Parse URL for auth and SSL settings
        url_params = self._parse_redis_url()

        logger.debug(
            "Connecting to Redis Cluster with %d nodes",
            len(startup_nodes),
        )

        cluster = RedisCluster(
            startup_nodes=startup_nodes,
            max_connections=self._config.cluster_max_connections,
            decode_responses=False,
            require_full_coverage=not self._config.cluster_skip_full_coverage_check,
            password=self._config.redis_access,
            username=url_params["username"],
            ssl=url_params["ssl"],
        )
        return cluster

    async def _create_pubsub_client(self) -> Any:
        """Create a standalone Redis client for pub/sub operations.

        In cluster mode, RedisCluster doesn't support pubsub(), so we need
        a standalone client connected to a specific node for pub/sub.

        Returns:
            Standalone Redis client for pub/sub.
        """
        if not redis_lib:
            raise RedisNotAvailableError("Redis library not available")

        if self._config.cluster_mode:
            # In cluster mode, connect to the first startup node for pub/sub
            startup_nodes = self._build_cluster_startup_nodes()
            if not startup_nodes:
                raise RedisNotAvailableError(
                    "No cluster nodes for pub/sub client",
                )

            # Parse URL for auth
            url_params = self._parse_redis_url()

            # Create standalone client to first node
            first_node = startup_nodes[0]
            client = redis_lib.Redis(
                host=first_node.host,
                port=first_node.port,
                password=self._config.redis_access,
                username=url_params["username"],
                ssl=url_params["ssl"],
                decode_responses=False,
            )
            return client
        else:
            # In standalone mode, use the same connection
            if self._redis is None:
                raise RedisNotAvailableError("Redis not connected")
            return self._redis

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        # Stop candidate loop
        await self.stop_candidate_loop()

        await self.deactivate()

        if (
            self._pubsub_client is not None
            and self._pubsub_client is not self._redis
        ):
            try:
                await self._pubsub_client.close()
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("Error closing pubsub client: %s", e)
            self._pubsub_client = None

        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("Error closing Redis connection: %s", e)
            self._redis = None

    async def activate(self) -> bool:
        """Activate this instance as a leader candidate.

        This acquires the lease and starts listening for reload signals.
        Returns True if this instance became the leader, False if follower.

        Raises:
            RedisNotAvailableError: If coordination is enabled but Redis is not available.
        """
        if self._redis is None:
            logger.error(
                "Cannot activate: Redis coordination enabled but not connected",
            )
            raise RedisNotAvailableError(
                "Redis coordination is enabled but Redis is not available. "
                "Please check Redis connection or disable coordination.",
            )

        # Create and acquire lease
        self._lease = AgentLease(
            redis_client=self._redis,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            instance_id=self._instance_id,
            config=self._config,
            on_lease_lost=self._on_lease_lost,
        )

        acquired = await self._lease.acquire()

        # Start reload subscriber regardless of leader/follower status
        if self._on_reload is not None and self._pubsub_client is not None:
            # Only create if not already started
            if self._reload_subscriber is None:
                self._reload_subscriber = ReloadSubscriber(
                    redis_client=self._pubsub_client,
                    tenant_id=self._tenant_id,
                    agent_id=self._agent_id,
                    config=self._config,
                    on_reload=self._on_reload,
                )
                await self._reload_subscriber.start()

        return acquired

    async def deactivate(self) -> None:
        """Deactivate this instance, releasing leadership if held."""
        # Stop candidate loop first (we don't want to immediately re-acquire)
        await self.stop_candidate_loop()

        if self._reload_subscriber is not None:
            await self._reload_subscriber.stop()
            self._reload_subscriber = None

        if self._lease is not None:
            await self._lease.release()
            self._lease = None

    async def publish_reload(self, version: Optional[int] = None) -> bool:
        """Publish a reload signal.

        Can be called from any instance (leader or follower).
        """
        # Use _pubsub_client in cluster mode, _redis in standalone mode
        # RedisCluster doesn't have publish() method
        client = (
            self._pubsub_client if self._config.cluster_mode else self._redis
        )
        if client is None:
            return False

        publisher = ReloadPublisher(
            redis_client=client,
            config=self._config,
        )
        if version is None:
            return await publisher.publish(self._tenant_id, self._agent_id)
        return await publisher.publish(
            self._tenant_id,
            self._agent_id,
            version=version,
        )

    async def get_definition_version(self) -> int:
        """Read the latest cron definition version for this tenant+agent."""
        if self._redis is None:
            raise RedisNotAvailableError("Not connected to Redis")

        key = (
            f"swe:cron:defver:{self._tenant_id or 'default'}:{self._agent_id}"
        )
        raw = await self._redis.get(key)
        if raw is None:
            return 0
        if isinstance(raw, bytes):
            raw = raw.decode()
        return int(raw)

    async def bump_definition_version(self) -> int:
        """Advance and return the latest cron definition version."""
        if self._redis is None:
            raise RedisNotAvailableError("Not connected to Redis")

        key = (
            f"swe:cron:defver:{self._tenant_id or 'default'}:{self._agent_id}"
        )
        return int(await self._redis.incr(key))

    async def ensure_definition_version(self, version: int) -> int:
        """Ensure the shared definition version is at least ``version``."""
        if self._redis is None:
            raise RedisNotAvailableError("Not connected to Redis")

        key = (
            f"swe:cron:defver:{self._tenant_id or 'default'}:{self._agent_id}"
        )
        script = """
local current = redis.call('GET', KEYS[1])
if (not current) or (tonumber(current) < tonumber(ARGV[1])) then
    redis.call('SET', KEYS[1], ARGV[1])
    return tonumber(ARGV[1])
end
return tonumber(current)
"""
        return int(await self._redis.eval(script, 1, key, version))

    async def acquire_definition_lock(self) -> DefinitionLock:
        """Acquire the tenant+agent definition mutation lock."""
        if self._redis is None:
            raise RedisNotAvailableError("Not connected to Redis")

        ttl_seconds = max(self._config.lease_ttl_seconds, 30)
        lock = DefinitionLock(
            redis_client=self._redis,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            ttl_seconds=ttl_seconds,
        )
        timeout_seconds = max(
            float(self._config.definition_lock_timeout_seconds),
            0.05,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while True:
            acquired = await lock.acquire()
            if acquired:
                return lock
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise DefinitionLockTimeoutError(
                    "Timed out acquiring cron definition lock: "
                    f"tenant={self._tenant_id or 'default'} "
                    f"agent={self._agent_id} "
                    f"lock_ttl_seconds={ttl_seconds} "
                    f"wait_timeout_seconds={timeout_seconds}",
                )
            await asyncio.sleep(min(0.05, remaining))

    def set_reload_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback to invoke when a reload signal is received."""
        self._on_reload = callback

    def set_lease_lost_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback to invoke when the lease is lost."""
        self._on_lease_lost = callback

    def set_become_leader_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback to invoke when this instance becomes leader."""
        self._on_become_leader = callback

    async def start_candidate_loop(self) -> None:
        """Start the candidate loop for automatic failover.

        This loop periodically retries to acquire leadership when not leader.
        Should be called after connect() but before or after activate().
        """
        if self._candidate_task is not None:
            return

        self._stop_candidate.clear()
        self._candidate_task = asyncio.create_task(
            self._candidate_loop(),
            name=f"candidate-{self._tenant_id or 'default'}-{self._agent_id}",
        )
        logger.debug(
            "Started candidate loop: tenant=%s agent=%s",
            self._tenant_id,
            self._agent_id,
        )

    async def stop_candidate_loop(self) -> None:
        """Stop the candidate loop."""
        if self._candidate_task is None:
            return

        self._stop_candidate.set()
        try:
            await asyncio.wait_for(self._candidate_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._candidate_task.cancel()
            try:
                await self._candidate_task
            except asyncio.CancelledError:
                pass
        self._candidate_task = None
        logger.debug(
            "Stopped candidate loop: tenant=%s agent=%s",
            self._tenant_id,
            self._agent_id,
        )

    async def _candidate_loop(self) -> None:
        """Background task that periodically retries to acquire leadership."""
        # Wait a bit before first attempt to avoid thundering herd on startup
        try:
            await asyncio.wait_for(
                self._stop_candidate.wait(),
                timeout=self._config.lease_renew_interval_seconds,
            )
            return  # Stop requested
        except asyncio.TimeoutError:
            pass

        while not self._stop_candidate.is_set():
            try:
                # If already leader, just wait
                if self.is_leader:
                    await asyncio.wait_for(
                        self._stop_candidate.wait(),
                        timeout=self._config.lease_renew_interval_seconds,
                    )
                    return

                # Try to activate (acquire leadership)
                logger.debug(
                    "Candidate loop attempting to become leader: "
                    "tenant=%s agent=%s",
                    self._tenant_id,
                    self._agent_id,
                )
                became_leader = await self.activate()

                if became_leader:
                    logger.info(
                        "Candidate loop became leader: tenant=%s agent=%s",
                        self._tenant_id,
                        self._agent_id,
                    )
                    # Notify via callback
                    if self._on_become_leader is not None:
                        try:
                            self._on_become_leader()
                        except Exception:  # pylint: disable=broad-except
                            logger.exception("Become leader callback failed")
                    return

                # Not leader, wait before retry
                await asyncio.wait_for(
                    self._stop_candidate.wait(),
                    timeout=self._config.lease_renew_interval_seconds,
                )
                return  # Stop requested

            except asyncio.TimeoutError:
                continue  # Retry
            except Exception:  # pylint: disable=broad-except
                logger.exception("Candidate loop error")
                # Wait before retry
                try:
                    await asyncio.wait_for(
                        self._stop_candidate.wait(),
                        timeout=self._config.lease_renew_interval_seconds,
                    )
                    return  # Stop requested
                except asyncio.TimeoutError:
                    continue

    def create_execution_lock(
        self,
        job_id: str,
        timeout_seconds: int,
    ) -> ExecutionLock:
        """Create a legacy execution lock for a specific job.

        Args:
            job_id: The job ID to lock
            timeout_seconds: The job timeout (lock will cover timeout + margin)

        Returns:
            ExecutionLock instance.

        This API is retained only for explicit compatibility paths. The default
        scheduler-originated execution contract now relies on lease preflight
        and idempotent handlers instead of timed execution lock de-duplication.
        """
        if self._redis is None:
            raise RedisNotAvailableError("Not connected to Redis")

        ttl = timeout_seconds + self._config.lock_safety_margin_seconds
        return ExecutionLock(
            redis_client=self._redis,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            job_id=job_id,
            ttl_seconds=ttl,
        )

    async def ensure_connected(self) -> bool:
        """Ensure Redis connection is active, reconnect if needed.

        Returns True if connected, False otherwise.
        """
        if self._redis is None:
            return await self.connect()

        try:
            await self._redis.ping()
            return True
        except Exception:
            logger.warning("Redis connection lost, attempting to reconnect")
            self._redis = None
            return await self.connect()


@asynccontextmanager
async def execution_lock_context(
    coordination: CronCoordination,
    job_id: str,
    timeout_seconds: int,
) -> AsyncGenerator[bool, None]:
    """Legacy async context manager for explicit execution-lock usage.

    Usage:
        async with execution_lock_context(coord, job_id, timeout) as acquired:
            if acquired:
                # Execute the job
                pass
            else:
                # Skip duplicate execution
                pass

    Note: The lock is NOT released when the context exits. It will
    naturally expire after timeout + safety_margin. This prevents
    duplicate executions if another instance takes over leadership.

    This helper is no longer part of the default timed scheduler path.
    """
    lock = coordination.create_execution_lock(job_id, timeout_seconds)
    acquired = await lock.acquire()
    try:
        yield acquired
    finally:
        # Do NOT release the lock - let it expire naturally.
        # This prevents duplicate executions during leadership transitions.
        # The lock TTL covers: timeout_seconds + lock_safety_margin_seconds
        if acquired:
            logger.debug(
                "Execution lock will expire naturally: job_id=%s (TTL=%ds)",
                job_id,
                lock.ttl_seconds,
            )
