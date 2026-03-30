# -*- coding: utf-8 -*-
"""Redis-based store for tracking background model download tasks.

Multiple downloads can run concurrently. Completed/failed results are retained
until explicitly cleared so the frontend can poll for the final state.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

from .download_task_store_models import DownloadTask, DownloadTaskStatus
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
_TASK_TTL = 3600  # 1 hour default TTL for tasks


def _get_redis_client() -> Redis | RedisCluster:
    """Get or create the Redis client singleton."""
    global _redis_client
    if _redis_client is None:
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
    return _redis_client


def _task_key(task_id: str) -> str:
    """Generate Redis key for a task."""
    return f"copaw:download:task:{task_id}"


def _index_key(backend: Optional[str] = None) -> str:
    """Generate index key for task tracking."""
    if backend:
        return f"copaw:download:index:{backend}"
    return "copaw:download:index:all"


async def create_task(
    repo_id: str,
    filename: Optional[str],
    backend: str,
    source: str,
) -> DownloadTask:
    """Create a new pending download task."""
    task = DownloadTask(
        repo_id=repo_id,
        filename=filename,
        backend=backend,
        source=source,
    )
    client = _get_redis_client()
    key = _task_key(task.task_id)
    task_data = task.model_dump()
    task_json = json.dumps(task_data)

    async with client.pipeline() as pipe:
        # Save task data
        pipe.set(key, task_json, ex=_TASK_TTL)
        # Add to backend-specific index
        index_key = _index_key(backend)
        pipe.sadd(index_key, task.task_id)
        pipe.expire(index_key, _TASK_TTL)
        # Add to global index
        global_index_key = _index_key()
        pipe.sadd(global_index_key, task.task_id)
        pipe.expire(global_index_key, _TASK_TTL)
        await pipe.execute()

    logger.debug(f"Created download task {task.task_id} for {repo_id}")
    return task


async def get_tasks(backend: Optional[str] = None) -> List[DownloadTask]:
    """Return all tasks, optionally filtered by backend."""
    client = _get_redis_client()
    index_key = _index_key(backend)
    tasks = []

    try:
        task_ids = await client.smembers(index_key)
        if not task_ids:
            return tasks

        for task_id_bytes in task_ids:
            task_id = (
                task_id_bytes.decode("utf-8")
                if isinstance(task_id_bytes, bytes)
                else task_id_bytes
            )
            task = await get_task(task_id)
            if task:
                tasks.append(task)

        return tasks
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        raise


async def get_task(task_id: str) -> Optional[DownloadTask]:
    """Return a specific task by ID."""
    client = _get_redis_client()
    key = _task_key(task_id)

    try:
        raw_task = await client.get(key)
        if raw_task is None:
            return None

        task_data = json.loads(raw_task)
        return DownloadTask(**task_data)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON for task {task_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}")
        raise


async def update_status(
    task_id: str,
    status: DownloadTaskStatus,
    *,
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """Update the status of a task. No-op if task_id doesn't exist."""
    client = _get_redis_client()
    key = _task_key(task_id)

    try:
        raw_task = await client.get(key)
        if raw_task is None:
            return

        task_data = json.loads(raw_task)
        task = DownloadTask(**task_data)
        task.status = status
        task.updated_at = task_data.get("updated_at", task.created_at)
        if error is not None:
            task.error = error
        if result is not None:
            task.result = result
        task.updated_at = task.updated_at  # This will be current time

        # Calculate remaining TTL
        ttl = await client.ttl(key)
        new_ttl = max(ttl, _TASK_TTL) if ttl > 0 else _TASK_TTL

        await client.set(key, json.dumps(task.model_dump()), ex=new_ttl)
        logger.debug(f"Updated task {task_id} status to {status}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON for task {task_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to update task {task_id}: {e}")
        raise


async def cancel_task(task_id: str) -> bool:
    """Cancel a pending or downloading task.

    Returns True if cancelled, False if task not found or not cancellable.
    """
    client = _get_redis_client()
    key = _task_key(task_id)

    try:
        raw_task = await client.get(key)
        if raw_task is None:
            return False

        task_data = json.loads(raw_task)
        task = DownloadTask(**task_data)

        if task.status not in (
            DownloadTaskStatus.PENDING,
            DownloadTaskStatus.DOWNLOADING,
        ):
            return False

        task.status = DownloadTaskStatus.CANCELLED
        task.updated_at = task.updated_at  # Update timestamp

        # Calculate remaining TTL
        ttl = await client.ttl(key)
        new_ttl = max(ttl, _TASK_TTL) if ttl > 0 else _TASK_TTL

        await client.set(key, json.dumps(task.model_dump()), ex=new_ttl)
        logger.debug(f"Cancelled task {task_id}")
        return True
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON for task {task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        raise


async def clear_completed(backend: Optional[str] = None) -> None:
    """Remove tasks in a terminal state (completed/failed/cancelled)."""
    client = _get_redis_client()
    terminal_statuses = (
        DownloadTaskStatus.COMPLETED,
        DownloadTaskStatus.FAILED,
        DownloadTaskStatus.CANCELLED,
    )

    try:
        tasks = await get_tasks(backend)
        for task in tasks:
            if task.status in terminal_statuses:
                await _delete_task(client, task.task_id, task.backend)
                logger.debug(f"Cleared completed task {task.task_id}")
    except Exception as e:
        logger.error(f"Failed to clear completed tasks: {e}")
        raise


async def _delete_task(
    client: Redis | RedisCluster,
    task_id: str,
    backend: Optional[str],
) -> None:
    """Delete a task from Redis."""
    key = _task_key(task_id)

    async with client.pipeline() as pipe:
        # Delete task data
        pipe.delete(key)
        # Remove from backend-specific index
        if backend:
            index_key = _index_key(backend)
            pipe.srem(index_key, task_id)
        # Remove from global index
        global_index_key = _index_key()
        pipe.srem(global_index_key, task_id)
        await pipe.execute()
