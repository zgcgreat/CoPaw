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
