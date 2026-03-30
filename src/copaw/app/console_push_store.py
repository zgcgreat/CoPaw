# -*- coding: utf-8 -*-
"""Redis-based store for console channel push messages."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

from ..store.redis_store import ConsolePushStore as _ConsolePushStore
from ..constant import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    REDIS_SSL,
    REDIS_MODE,
)

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None
_store: Optional[_ConsolePushStore] = None
_MAX_AGE_SECONDS = 60


def _get_store() -> _ConsolePushStore:
    global _redis_client, _store
    if _store is None:
        if REDIS_MODE == "cluster":
            from ..constant import get_redis_seeds

            seeds = get_redis_seeds()
            startup_nodes = [
                {"host": h, "port": int(p)}
                for h, p in (s.split(":") for s in seeds)
            ]
            _redis_client = RedisCluster(
                startup_nodes=startup_nodes,
                password=REDIS_PASSWORD or None,
                ssl=REDIS_SSL,
                decode_responses=False,
                skip_full_coverage_check=True,
            )
        else:
            redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
            if REDIS_SSL:
                redis_url = redis_url.replace("redis://", "rediss://")
            _redis_client = Redis.from_url(
                redis_url,
                password=REDIS_PASSWORD or None,
                decode_responses=False,
            )
        _store = _ConsolePushStore(_redis_client, ttl=_MAX_AGE_SECONDS)
    return _store


async def append(user_id: str | None, session_id: str, text: str) -> None:
    store = _get_store()
    await store.append(user_id, session_id, text)


async def take(user_id: str | None, session_id: str) -> List[Dict[str, Any]]:
    store = _get_store()
    return await store.take(user_id, session_id)


async def take_all(user_id: str | None = None) -> List[Dict[str, Any]]:
    store = _get_store()
    return await store.take_all(user_id)


async def get_recent(
    user_id: str | None = None,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> List[Dict[str, Any]]:
    store = _get_store()
    return await store.get_recent(user_id, max_age_seconds)


def _strip_ts(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"id": m["id"], "text": m["text"]} for m in msgs]
