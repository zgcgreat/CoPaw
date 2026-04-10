# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from dataclasses import dataclass

from redis import asyncio as redis_asyncio

from ...constant import (
    SHARED_RUN_CANCEL_TTL_SECONDS,
    SHARED_RUN_HEARTBEAT_SECONDS,
    SHARED_RUN_LEASE_TTL_SECONDS,
    SHARED_RUN_REDIS_URL,
)


@dataclass(frozen=True)
class SharedRunLease:
    run_key: str
    owner_instance_id: str
    status: str
    started_at: float
    heartbeat_at: float
    cancel_requested: bool = False


class SharedRunCoordinationError(RuntimeError):
    pass


class RunOwnedByAnotherInstanceError(SharedRunCoordinationError):
    def __init__(self, run_key: str, owner_instance_id: str):
        self.run_key = run_key
        self.owner_instance_id = owner_instance_id
        super().__init__(
            f"Run '{run_key}' is already owned by '{owner_instance_id}'",
        )


def build_runtime_instance_id() -> str:
    hostname = os.environ.get("HOSTNAME") or socket.gethostname()
    return f"{hostname}:{os.getpid()}"


class RedisSharedRunCoordinator:
    def __init__(
        self,
        *,
        namespace: str,
        redis_url: str = SHARED_RUN_REDIS_URL,
        lease_ttl_seconds: int = SHARED_RUN_LEASE_TTL_SECONDS,
        heartbeat_seconds: float = SHARED_RUN_HEARTBEAT_SECONDS,
        cancel_ttl_seconds: int = SHARED_RUN_CANCEL_TTL_SECONDS,
        redis_client=None,
    ) -> None:
        self.namespace = namespace
        self.lease_ttl_seconds = lease_ttl_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.cancel_ttl_seconds = cancel_ttl_seconds
        self._redis = redis_client or redis_asyncio.from_url(
            redis_url,
            decode_responses=True,
        )

    async def _call(self, awaitable):
        try:
            return await awaitable
        except Exception as exc:
            raise SharedRunCoordinationError(
                "shared run coordination unavailable",
            ) from exc

    def _lease_key(self, run_key: str) -> str:
        return f"{self.namespace}:chat-run:{run_key}"

    def _cancel_key(self, run_key: str) -> str:
        return f"{self.namespace}:chat-run-cancel:{run_key}"

    async def start_run(
        self,
        run_key: str,
        owner_instance_id: str,
    ) -> SharedRunLease:
        await self._call(self._redis.ping())
        now = time.time()
        payload = json.dumps(
            {
                "run_key": run_key,
                "owner_instance_id": owner_instance_id,
                "status": "running",
                "started_at": now,
                "heartbeat_at": now,
            },
        )
        created = await self._call(
            self._redis.set(
                self._lease_key(run_key),
                payload,
                ex=self.lease_ttl_seconds,
                nx=True,
            ),
        )
        if not created:
            current = await self.get_run(run_key)
            if current is not None:
                raise RunOwnedByAnotherInstanceError(
                    run_key,
                    current.owner_instance_id,
                )
            return await self.start_run(run_key, owner_instance_id)
        try:
            await self._call(self._redis.delete(self._cancel_key(run_key)))
        except SharedRunCoordinationError:
            with contextlib.suppress(Exception):
                await self._redis.delete(self._lease_key(run_key))
            raise
        return SharedRunLease(
            run_key=run_key,
            owner_instance_id=owner_instance_id,
            status="running",
            started_at=now,
            heartbeat_at=now,
        )

    async def refresh_run(
        self,
        run_key: str,
        owner_instance_id: str,
    ) -> SharedRunLease | None:
        current = await self.get_run(run_key)
        if current is None or current.owner_instance_id != owner_instance_id:
            return None
        payload = json.dumps(
            {
                "run_key": current.run_key,
                "owner_instance_id": current.owner_instance_id,
                "status": "running",
                "started_at": current.started_at,
                "heartbeat_at": time.time(),
            },
        )
        await self._call(
            self._redis.set(
                self._lease_key(run_key),
                payload,
                ex=self.lease_ttl_seconds,
            ),
        )
        return await self.get_run(run_key)

    async def get_run(self, run_key: str) -> SharedRunLease | None:
        raw = await self._call(self._redis.get(self._lease_key(run_key)))
        if raw is None:
            return None
        payload = json.loads(raw)
        cancel_requested = await self._call(
            self._redis.get(self._cancel_key(run_key)),
        )
        return SharedRunLease(
            run_key=payload["run_key"],
            owner_instance_id=payload["owner_instance_id"],
            status=payload["status"],
            started_at=payload["started_at"],
            heartbeat_at=payload["heartbeat_at"],
            cancel_requested=cancel_requested is not None,
        )

    async def request_cancel(self, run_key: str) -> bool:
        lease = await self.get_run(run_key)
        if lease is None:
            return False
        await self._call(
            self._redis.set(
                self._cancel_key(run_key),
                "1",
                ex=self.cancel_ttl_seconds,
            ),
        )
        return True

    async def clear_run(self, run_key: str, owner_instance_id: str) -> None:
        lease = await self.get_run(run_key)
        if lease is None:
            await self._call(self._redis.delete(self._cancel_key(run_key)))
            return
        if lease.owner_instance_id != owner_instance_id:
            return
        await self._call(
            self._redis.delete(
                self._lease_key(run_key),
                self._cancel_key(run_key),
            ),
        )

    async def close(self) -> None:
        await self._call(self._redis.aclose())
