# -*- coding: utf-8 -*-
"""Redis-backed store for console channel push messages."""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from redis.asyncio import Redis, from_url
from redis.exceptions import ResponseError

_DEFAULT_TENANT = "default"
_MAX_AGE_SECONDS = 60
_MAX_MESSAGES = 500
_KEY_PREFIX = "swe:console-push"
_DEFAULT_STORE: "RedisConsolePushStore | None" = None


def _normalize_tenant(tenant_id: Optional[str]) -> str:
    return tenant_id or _DEFAULT_TENANT


def _get_redis_url() -> str:
    for env_name in ("SWE_CONSOLE_PUSH_REDIS_URL", "REDIS_URL"):
        value = os.getenv(env_name)
        if value:
            return value
    raise RuntimeError(
        "Console push delivery requires Redis. "
        "Set SWE_CONSOLE_PUSH_REDIS_URL or REDIS_URL."
    )


class RedisConsolePushStore:
    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str = _KEY_PREFIX,
        max_age_seconds: int = _MAX_AGE_SECONDS,
        max_messages: int = _MAX_MESSAGES,
    ):
        self._client = client
        self._key_prefix = key_prefix
        self._max_age_seconds = max_age_seconds
        self._max_messages = max_messages

    def _key(self, session_id: str, tenant_id: Optional[str] = None) -> str:
        tenant = _normalize_tenant(tenant_id)
        return f"{self._key_prefix}:{tenant}:{session_id}"

    def _drain_key(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        tenant = _normalize_tenant(tenant_id)
        return (
            f"{self._key_prefix}:__drain__:{tenant}:{session_id}:"
            f"{uuid.uuid4()}"
        )

    def _drain_pattern(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        tenant = _normalize_tenant(tenant_id)
        return f"{self._key_prefix}:__drain__:{tenant}:{session_id}:*"

    def _tenant_drain_pattern(self, tenant_id: Optional[str] = None) -> str:
        tenant = _normalize_tenant(tenant_id)
        return f"{self._key_prefix}:__drain__:{tenant}:*"

    async def _rename_for_drain(
        self,
        key: str,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> str | None:
        drain_key = self._drain_key(session_id, tenant_id)
        try:
            await self._client.rename(key, drain_key)
        except ResponseError:
            return None
        return drain_key

    async def _scan_keys(self, pattern: str) -> List[str]:
        cursor = 0
        keys: List[str] = []
        while True:
            cursor, batch = await self._client.scan(cursor=cursor, match=pattern)
            keys.extend(batch)
            if cursor == 0:
                return keys

    async def _drain_rows(self, drain_keys: List[str]) -> List[Dict[str, Any]]:
        cutoff = time.time() - self._max_age_seconds
        out: List[Dict[str, Any]] = []
        for drain_key in drain_keys:
            await self._client.zremrangebyscore(drain_key, "-inf", cutoff)
            rows = await self._client.zrange(drain_key, 0, -1)
            if rows:
                out.extend(json.loads(row) for row in rows)
            await self._client.delete(drain_key)
        out.sort(key=lambda item: item["ts"])
        return out

    async def append(
        self,
        session_id: str,
        text: str,
        *,
        sticky: bool = False,
        tenant_id: Optional[str] = None,
    ) -> None:
        if not session_id or not text:
            return

        ts = time.time()
        payload = json.dumps(
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "sticky": sticky,
                "ts": ts,
            },
            separators=(",", ":"),
        )
        key = self._key(session_id, tenant_id)

        await self._client.zremrangebyscore(
            key,
            "-inf",
            ts - self._max_age_seconds,
        )
        await self._client.zadd(key, {payload: ts})
        size = await self._client.zcard(key)
        if size > self._max_messages:
            await self._client.zremrangebyrank(
                key,
                0,
                size - self._max_messages - 1,
            )
        await self._client.expire(key, self._max_age_seconds)

    async def take(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []

        drain_keys = await self._scan_keys(
            self._drain_pattern(session_id, tenant_id),
        )
        live_drain_key = await self._rename_for_drain(
            self._key(session_id, tenant_id),
            session_id,
            tenant_id,
        )
        if live_drain_key is not None:
            drain_keys.append(live_drain_key)
        if not drain_keys:
            return []

        return self._strip_ts(await self._drain_rows(drain_keys))

    async def take_all(
        self,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        tenant = _normalize_tenant(tenant_id)
        pattern = f"{self._key_prefix}:{tenant}:*"
        drain_keys = await self._scan_keys(self._tenant_drain_pattern(tenant_id))
        keys = await self._scan_keys(pattern)
        for key in keys:
            if f"{self._key_prefix}:__drain__:" in key:
                continue
            session_id = key.rsplit(":", 1)[-1]
            drain_key = await self._rename_for_drain(key, session_id, tenant_id)
            if drain_key is not None:
                drain_keys.append(drain_key)
        return self._strip_ts(await self._drain_rows(drain_keys))

    async def get_recent(
        self,
        max_age_seconds: int = _MAX_AGE_SECONDS,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative")

        tenant = _normalize_tenant(tenant_id)
        pattern = f"{self._key_prefix}:{tenant}:*"
        out: List[Dict[str, Any]] = []
        cursor = 0
        cutoff = time.time() - max_age_seconds
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern)
            for key in keys:
                await self._client.zremrangebyscore(key, "-inf", cutoff)
                rows = await self._client.zrange(key, 0, -1)
                out.extend(json.loads(row) for row in rows)
            if cursor == 0:
                break
        out.sort(key=lambda item: item["ts"])
        return self._strip_ts(out)

    async def clear_tenant(self, tenant_id: Optional[str] = None) -> None:
        tenant = _normalize_tenant(tenant_id)
        cursor = 0
        pattern = f"{self._key_prefix}:{tenant}:*"
        drain_pattern = self._tenant_drain_pattern(tenant_id)
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern)
            if keys:
                await self._client.delete(*keys)
            if cursor == 0:
                break
        drain_keys = await self._scan_keys(drain_pattern)
        if drain_keys:
            await self._client.delete(*drain_keys)

    async def get_stats(self) -> Dict[str, Any]:
        cursor = 0
        totals: Dict[str, int] = {}
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor,
                match=f"{self._key_prefix}:*",
            )
            for key in keys:
                remainder = key[len(f"{self._key_prefix}:") :]
                if remainder.startswith("__drain__:"):
                    continue
                tenant_id, _session_id = remainder.split(":", 1)
                totals[tenant_id] = totals.get(tenant_id, 0) + await (
                    self._client.zcard(key)
                )
            if cursor == 0:
                break
        return {
            "tenant_count": len(totals),
            "tenants": totals,
        }

    @staticmethod
    def _strip_ts(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "text": item["text"],
                "sticky": bool(item.get("sticky", False)),
            }
            for item in msgs
        ]


def _get_default_store() -> RedisConsolePushStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = RedisConsolePushStore(
            from_url(_get_redis_url(), decode_responses=True),
        )
    return _DEFAULT_STORE


async def append(
    session_id: str,
    text: str,
    *,
    sticky: bool = False,
    tenant_id: Optional[str] = None,
) -> None:
    await _get_default_store().append(
        session_id,
        text,
        sticky=sticky,
        tenant_id=tenant_id,
    )


async def take(
    session_id: str,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return await _get_default_store().take(session_id, tenant_id=tenant_id)


async def take_all(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return await _get_default_store().take_all(tenant_id=tenant_id)


async def get_recent(
    max_age_seconds: int = _MAX_AGE_SECONDS,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return await _get_default_store().get_recent(
        max_age_seconds=max_age_seconds,
        tenant_id=tenant_id,
    )


async def clear_tenant(tenant_id: Optional[str] = None) -> None:
    await _get_default_store().clear_tenant(tenant_id=tenant_id)


async def get_stats() -> Dict[str, Any]:
    return await _get_default_store().get_stats()
