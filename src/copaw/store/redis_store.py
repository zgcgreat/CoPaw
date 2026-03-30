# -*- coding: utf-8 -*-
"""Redis-based temporary data storage with TTL."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Union

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

logger = logging.getLogger(__name__)

# Type alias for Redis client (supports both standalone and cluster)
RedisClient = Union[Redis, RedisCluster]


class RedisHashStore:
    """Hash-based storage with automatic TTL expiration.

    Uses Redis Hash for field storage with TTL on the entire key.
    Suitable for temporary data like console_push, download_tasks.
    """

    def __init__(self, redis: RedisClient, key_prefix: str, default_ttl: int):
        """Initialize store.

        Args:
            redis: Redis client (standalone or cluster).
            key_prefix: Key prefix for namespacing.
            default_ttl: Default TTL in seconds.
        """
        self.redis = redis
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

    def _make_key(self, identifier: str) -> str:
        """Generate storage key."""
        return f"{self.key_prefix}:{identifier}"

    async def set(
        self,
        identifier: str,
        field: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
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

    async def scan_keys(self, pattern: str) -> list[str]:
        """Scan for keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., 'copaw:console:push:user1:*').

        Returns:
            List of matching keys (decoded strings).
        """
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        return keys


class ConsolePushStore:
    """Store for console push messages with user isolation.

    Uses Redis List for message storage to support multiple sessions per user.
    Each user has a list of messages that can be filtered by session_id.
    """

    def __init__(self, redis: RedisClient, ttl: int = 60):
        """Initialize store.

        Args:
            redis: Redis client (standalone or cluster).
            ttl: TTL in seconds for messages.
        """
        self._redis = redis
        self._ttl = ttl
        self._key_prefix = "copaw:push"

    def _make_key(self, user_id: str | None) -> str:
        """Generate storage key for user."""
        if user_id:
            return f"{self._key_prefix}:{user_id}"
        return f"{self._key_prefix}:default"

    async def append(
        self,
        user_id: str | None,
        session_id: str,
        text: str,
        ttl: int | None = None,
    ) -> None:
        """Append a message to the user's message list.

        Args:
            user_id: Optional user identifier for isolation.
            session_id: Session identifier.
            text: Message text.
            ttl: Optional custom TTL (uses default if not specified).
        """
        key = self._make_key(user_id)
        message = {
            "session_id": session_id,
            "text": text,
            "timestamp": time.time(),
        }

        # Use pipeline for atomic operation
        async with self._redis.pipeline() as pipe:
            pipe.rpush(key, json.dumps(message))
            pipe.expire(key, ttl or self._ttl)
            await pipe.execute()

    async def take(
        self,
        user_id: str | None,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Take all messages for a specific session (removes them after retrieval).

        Args:
            user_id: Optional user identifier for isolation.
            session_id: Session identifier to filter by.

        Returns:
            List of messages for the session.
        """
        key = self._make_key(user_id)

        # Get all messages
        raw_messages = await self._redis.lrange(key, 0, -1)
        if not raw_messages:
            await self._redis.delete(key)
            return []

        # Parse and filter by session_id
        messages = []
        for raw in raw_messages:
            msg = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if msg.get("session_id") == session_id:
                messages.append(msg)

        # Delete the entire key after reading (like the original implementation)
        await self._redis.delete(key)

        return messages

    async def take_all(
        self,
        user_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Take all messages for a user (removes them after retrieval).

        Args:
            user_id: Optional user identifier to filter by.

        Returns:
            List of all messages for the user.
        """
        key = self._make_key(user_id)

        # Use pipeline to get and delete atomically
        async with self._redis.pipeline() as pipe:
            pipe.lrange(key, 0, -1)
            pipe.delete(key)
            results = await pipe.execute()

        raw_messages = results[0] if results else []
        if not raw_messages:
            return []

        # Parse all messages
        messages = []
        for raw in raw_messages:
            msg = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            messages.append(msg)

        return messages

    async def get_recent(
        self,
        user_id: str | None = None,
        max_age_seconds: int = 60,
    ) -> List[Dict[str, Any]]:
        """Get recent messages within time window (removes them after retrieval).

        Args:
            user_id: Optional user identifier for isolation.
            max_age_seconds: Maximum age of messages to retrieve.

        Returns:
            List of recent messages (within max_age_seconds).
        """
        cutoff_time = time.time() - max_age_seconds
        key = self._make_key(user_id)

        # Get all messages
        raw_messages = await self._redis.lrange(key, 0, -1)
        if not raw_messages:
            await self._redis.delete(key)
            return []

        # Filter by timestamp
        messages = []
        for raw in raw_messages:
            msg = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if msg.get("timestamp", 0) >= cutoff_time:
                messages.append(msg)

        # Delete all messages after reading (as per requirement)
        await self._redis.delete(key)

        return messages


class DownloadTaskStore:
    """Store for download tasks with indexing by backend.

    Supports saving tasks with metadata, retrieving by ID,
    and listing/filtering by backend type (e.g., 'nas', 's3').
    """

    def __init__(self, redis: RedisClient, ttl: int = 3600):
        """Initialize store.

        Args:
            redis: Redis client (standalone or cluster).
            ttl: TTL in seconds for tasks.
        """
        self._redis = redis
        self._ttl = ttl
        self._key_prefix = "copaw:download:task"
        self._index_prefix = "copaw:download:index"

    def _make_key(self, task_id: str) -> str:
        """Generate storage key for task."""
        return f"{self._key_prefix}:{task_id}"

    def _make_index_key(self, backend: str) -> str:
        """Generate index key for backend."""
        return f"{self._index_prefix}:{backend}"

    async def save(self, task: Dict[str, Any]) -> None:
        """Save a download task.

        Args:
            task: Task dictionary with 'task_id' and 'backend' keys.

        Raises:
            ValueError: If task_id is missing from task.
        """
        task_id = task.get("task_id")
        if not task_id:
            raise ValueError("task is missing required 'task_id' field")

        backend = task.get("backend", "unknown")
        key = self._make_key(task_id)
        index_key = self._make_index_key(backend)
        all_index_key = self._make_index_key("all")

        # Use pipeline for atomic operation
        async with self._redis.pipeline() as pipe:
            pipe.set(key, json.dumps(task))
            pipe.sadd(index_key, task_id)
            pipe.sadd(all_index_key, task_id)
            pipe.expire(key, self._ttl)
            pipe.expire(index_key, self._ttl)
            await pipe.execute()

    async def get(self, task_id: str) -> Dict[str, Any] | None:
        """Get a task by ID.

        Args:
            task_id: Task identifier.

        Returns:
            Task dictionary or None if not found.
        """
        key = self._make_key(task_id)
        result = await self._redis.get(key)

        if result is None:
            return None

        return json.loads(
            result.decode() if isinstance(result, bytes) else result
        )

    async def get_all(
        self, backend: str | None = None
    ) -> List[Dict[str, Any]]:
        """Get all tasks, optionally filtered by backend.

        Args:
            backend: Optional backend filter (e.g., 'nas', 's3').

        Returns:
            List of task dictionaries.
        """
        # Get task IDs from index
        if backend:
            index_key = self._make_index_key(backend)
        else:
            index_key = self._make_index_key("all")

        task_ids = await self._redis.smembers(index_key)
        if not task_ids:
            return []

        # Fetch each task
        tasks = []
        for task_id_bytes in task_ids:
            task_id = (
                task_id_bytes.decode()
                if isinstance(task_id_bytes, bytes)
                else task_id_bytes
            )
            task = await self.get(task_id)
            if task:
                tasks.append(task)

        return tasks

    async def delete(self, task_id: str) -> bool:
        """Delete a task by ID.

        Args:
            task_id: Task identifier.

        Returns:
            True if deleted, False if task not found.
        """
        task = await self.get(task_id)
        if task is None:
            return False

        backend = task.get("backend", "unknown")
        key = self._make_key(task_id)
        index_key = self._make_index_key(backend)
        all_index_key = self._make_index_key("all")

        # Use pipeline for atomic deletion
        async with self._redis.pipeline() as pipe:
            pipe.delete(key)
            pipe.srem(index_key, task_id)
            pipe.srem(all_index_key, task_id)
            await pipe.execute()

        return True
