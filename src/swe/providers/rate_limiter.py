# -*- coding: utf-8 -*-
"""Agent-scoped LLM request rate limiter.

How it works:
1. QPM sliding window: tracks request timestamps in a 60-second window.
   Before each call, if the window is full, the caller waits until the
   oldest timestamp slides out — proactively preventing 429s.
2. Workload-specific asyncio.Semaphore instances cap concurrent in-flight
   chat and cron LLM calls independently inside the same tenant-local agent.
3. A scoped pause timestamp: when a 429 is received every subsequent acquire()
   in the same tenant-local agent scope waits until the pause expires,
   eliminating thundering-herd retries inside that scope.
4. Per-waiter jitter: each caller adds a small random offset on top of
   the remaining pause time, so they spread out when waking up.

acquire() execution order:
    wait for 429 cooldown → wait for QPM slot → wait for semaphore slot
"""

from __future__ import annotations

import asyncio
import collections
import logging
import random
import time
from dataclasses import dataclass

from ..config.llm_workload import (
    LLMWorkload,
    normalize_llm_workload,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimiterScopeKey:
    """Tenant-local agent identity for process-local LLM limiting."""

    tenant_id: str
    agent_id: str


@dataclass(frozen=True, slots=True)
class _SharedRateLimiterConfigFingerprint:
    max_qpm: int
    default_pause_seconds: float
    jitter_range: float


@dataclass(frozen=True, slots=True)
class _WorkloadRateLimiterConfigFingerprint:
    max_concurrent: int


@dataclass(slots=True)
class _WorkloadRateLimiterRegistryEntry:
    limiter: "LLMRateLimiter"
    config: _WorkloadRateLimiterConfigFingerprint
    last_used_at: float


@dataclass(slots=True)
class _RateLimiterRegistryEntry:
    shared_state: "_SharedLLMRateLimiterState"
    shared_config: _SharedRateLimiterConfigFingerprint
    workloads: dict[LLMWorkload, _WorkloadRateLimiterRegistryEntry]
    last_used_at: float


class _SharedLLMRateLimiterState:
    """QPM and 429 cooldown state shared by all workloads in one scope."""

    def __init__(
        self,
        *,
        scope_key: RateLimiterScopeKey,
        max_qpm: int,
        default_pause_seconds: float,
        jitter_range: float,
    ) -> None:
        self._scope_key = scope_key
        self._pause_until: float = 0.0
        self._lock = asyncio.Lock()
        self._default_pause = default_pause_seconds
        self._jitter_range = jitter_range

        self._max_qpm = max_qpm
        self._request_times: collections.deque[float] = collections.deque()
        self._qpm_lock = asyncio.Lock()

        self._total_paused: int = 0
        self._total_qpm_waited: int = 0
        self._total_rate_limited: int = 0

    async def wait_for_cooldown(self, workload: LLMWorkload) -> None:
        """Wait out any shared 429 cooldown for this tenant-agent scope."""
        while True:
            now = time.monotonic()
            remaining = self._pause_until - now
            if remaining <= 0:
                break
            jitter = random.uniform(0, self._jitter_range)
            wait_time = remaining + jitter
            self._total_paused += 1
            logger.debug(
                "LLM rate limiter: 429 cooldown %.1fs "
                "(remaining=%.1fs + jitter=%.1fs, scope=%s/%s, "
                "workload=%s)",
                wait_time,
                remaining,
                jitter,
                self._scope_key.tenant_id,
                self._scope_key.agent_id,
                workload,
            )
            await asyncio.sleep(wait_time)

    async def acquire_qpm_slot(self, workload: LLMWorkload) -> None:
        """Wait until the shared 60-second QPM window has room."""
        if self._max_qpm <= 0:
            return

        while True:
            async with self._qpm_lock:
                now = time.monotonic()
                cutoff = now - 60.0
                while self._request_times and self._request_times[0] < cutoff:
                    self._request_times.popleft()

                if len(self._request_times) < self._max_qpm:
                    self._request_times.append(now)
                    return

                oldest = self._request_times[0]
                wait_time = oldest + 60.0 - now + 0.05

            self._total_qpm_waited += 1
            logger.debug(
                "LLM QPM limit (%d/min) reached, waiting %.1fs for slot "
                "(scope=%s/%s, workload=%s)",
                self._max_qpm,
                wait_time,
                self._scope_key.tenant_id,
                self._scope_key.agent_id,
                workload,
            )
            await asyncio.sleep(wait_time)

    async def report_rate_limit(
        self,
        workload: LLMWorkload,
        retry_after: float | None = None,
    ) -> None:
        """Record a 429 response in the shared tenant-agent cooldown state."""
        pause = retry_after if retry_after is not None else self._default_pause
        async with self._lock:
            new_until = time.monotonic() + pause
            if new_until > self._pause_until:
                self._pause_until = new_until
                self._total_rate_limited += 1
                logger.warning(
                    "LLM rate limiter: scoped pause set for %.1fs "
                    "(total_rate_limited=%d, scope=%s/%s, workload=%s)",
                    pause,
                    self._total_rate_limited,
                    self._scope_key.tenant_id,
                    self._scope_key.agent_id,
                    workload,
                )

    def stats(self) -> dict:
        """Return shared QPM and cooldown statistics."""
        now = time.monotonic()
        cutoff = now - 60.0
        requests_last_60s = sum(1 for t in self._request_times if t >= cutoff)
        return {
            "max_qpm": self._max_qpm,
            "requests_last_60s": requests_last_60s,
            "is_paused": now < self._pause_until,
            "pause_remaining_s": max(0.0, self._pause_until - now),
            "total_paused": self._total_paused,
            "total_qpm_waited": self._total_qpm_waited,
            "total_rate_limited": self._total_rate_limited,
        }


class LLMRateLimiter:
    """Scoped LLM request rate limiter.

    Coroutine-safe: all mutable state is protected by asyncio primitives and
    is intended for use within a single event loop.

    Args:
        max_concurrent: Maximum concurrent in-flight LLM calls (semaphore).
        max_qpm: Maximum queries per minute (sliding window). 0 = disabled.
        default_pause_seconds: Scope-local pause duration on a 429 response.
        jitter_range: Random jitter (seconds) added on top of the pause.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_qpm: int = 0,
        default_pause_seconds: float = 5.0,
        jitter_range: float = 1.0,
        shared_state: _SharedLLMRateLimiterState | None = None,
        scope_key: RateLimiterScopeKey | None = None,
        workload: LLMWorkload | str | None = None,
    ) -> None:
        self._scope_key = scope_key or RateLimiterScopeKey(
            "default",
            "default",
        )
        self._workload = normalize_llm_workload(workload)
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._shared_state = shared_state or _SharedLLMRateLimiterState(
            scope_key=self._scope_key,
            max_qpm=max_qpm,
            default_pause_seconds=default_pause_seconds,
            jitter_range=jitter_range,
        )

        # Own counter instead of reading semaphore._value (private API).
        self._in_flight: int = 0
        self._active_streams: int = 0

        self._total_acquired: int = 0

    async def acquire(self) -> None:
        """Acquire an execution permit.

        Execution order:
        1. If a scoped 429 pause is active, wait until it expires (plus
           per-waiter jitter to avoid a new burst on wake-up).  The while-loop
           re-checks after each sleep because a new 429 may have extended the
           pause while we were waiting.
        2. If RPM limiting is enabled, wait until a slot opens in the 60-second
           sliding window, then record this call's timestamp.
        3. Acquire the semaphore slot (concurrency cap).

        The hard upper-bound timeout is enforced by asyncio.wait_for() at
        every call site in RetryChatModel.
        """
        await self._shared_state.wait_for_cooldown(self._workload)
        await self._shared_state.acquire_qpm_slot(self._workload)

        await self._semaphore.acquire()
        self._in_flight += 1
        self._total_acquired += 1

    async def _acquire_qpm_slot(self) -> None:
        """Compatibility shim for older tests that reached into internals."""
        await self._shared_state.acquire_qpm_slot(self._workload)

    def release(self) -> None:
        """Release the semaphore slot.
        Must be paired with a prior acquire()."""
        self._in_flight -= 1
        self._semaphore.release()

    def begin_stream(self) -> None:
        """Mark a streaming response as active for cleanup safety."""
        self._active_streams += 1

    def end_stream(self) -> None:
        """Mark a streaming response as no longer active."""
        self._active_streams = max(0, self._active_streams - 1)

    async def report_rate_limit(
        self,
        retry_after: float | None = None,
    ) -> None:
        """Record a 429 response and set the scoped pause timestamp.

        Args:
            retry_after: Seconds from the API's Retry-After header.
                         Falls back to the configured default when None.
        """
        await self._shared_state.report_rate_limit(
            self._workload,
            retry_after=retry_after,
        )

    def stats(self) -> dict:
        """Return a snapshot of runtime statistics for logging or
        monitoring."""
        shared_stats = self._shared_state.stats()
        return {
            "workload": self._workload,
            "max_concurrent": self._max_concurrent,
            "current_in_flight": self._in_flight,
            "current_active_streams": self._active_streams,
            "current_available": max(
                0,
                self._max_concurrent - self._in_flight,
            ),
            "max_qpm": shared_stats["max_qpm"],
            "requests_last_60s": shared_stats["requests_last_60s"],
            "is_paused": shared_stats["is_paused"],
            "pause_remaining_s": shared_stats["pause_remaining_s"],
            "total_acquired": self._total_acquired,
            "total_paused": shared_stats["total_paused"],
            "total_qpm_waited": shared_stats["total_qpm_waited"],
            "total_rate_limited": shared_stats["total_rate_limited"],
        }


# Process-local scoped registry.
_limiter_registry: dict[
    RateLimiterScopeKey,
    _RateLimiterRegistryEntry,
] = {}
_registry_lock: asyncio.Lock | None = None


def _get_init_lock() -> asyncio.Lock:
    global _registry_lock
    if _registry_lock is None:
        _registry_lock = asyncio.Lock()
    return _registry_lock


def _normalize_scope_key(
    scope_key: RateLimiterScopeKey | None,
    tenant_id: str | None = None,
    agent_id: str | None = None,
) -> RateLimiterScopeKey:
    if scope_key is not None:
        return RateLimiterScopeKey(
            tenant_id=scope_key.tenant_id or "default",
            agent_id=scope_key.agent_id or "default",
        )

    resolved_tenant_id = tenant_id
    if not resolved_tenant_id:
        try:
            from ..config.context import get_current_effective_tenant_id

            resolved_tenant_id = get_current_effective_tenant_id()
        except Exception:
            resolved_tenant_id = None

    resolved_agent_id = agent_id
    if not resolved_agent_id:
        try:
            from ..app.agent_context import get_current_agent_id

            resolved_agent_id = get_current_agent_id(resolved_tenant_id)
        except Exception:
            resolved_agent_id = None

    return RateLimiterScopeKey(
        tenant_id=resolved_tenant_id or "default",
        agent_id=resolved_agent_id or "default",
    )


def resolve_rate_limiter_scope(
    scope_key: RateLimiterScopeKey | None = None,
    tenant_id: str | None = None,
    agent_id: str | None = None,
) -> RateLimiterScopeKey:
    """Resolve a limiter scope using the current tenant/agent fallbacks."""
    return _normalize_scope_key(
        scope_key,
        tenant_id=tenant_id,
        agent_id=agent_id,
    )


def _normalize_shared_config_fingerprint(
    max_qpm: int | None,
    default_pause_seconds: float | None,
    jitter_range: float | None,
) -> _SharedRateLimiterConfigFingerprint:
    from ..constant import (
        LLM_MAX_QPM,
        LLM_RATE_LIMIT_JITTER,
        LLM_RATE_LIMIT_PAUSE,
    )

    return _SharedRateLimiterConfigFingerprint(
        max_qpm=max(0, max_qpm if max_qpm is not None else LLM_MAX_QPM),
        default_pause_seconds=max(
            1.0,
            (
                default_pause_seconds
                if default_pause_seconds is not None
                else LLM_RATE_LIMIT_PAUSE
            ),
        ),
        jitter_range=max(
            0.0,
            (
                jitter_range
                if jitter_range is not None
                else LLM_RATE_LIMIT_JITTER
            ),
        ),
    )


def _normalize_workload_config_fingerprint(
    max_concurrent: int | None,
) -> _WorkloadRateLimiterConfigFingerprint:
    from ..constant import LLM_MAX_CONCURRENT

    return _WorkloadRateLimiterConfigFingerprint(
        max_concurrent=max(
            1,
            (
                max_concurrent
                if max_concurrent is not None
                else LLM_MAX_CONCURRENT
            ),
        ),
    )


async def get_rate_limiter(
    scope_key: RateLimiterScopeKey | None = None,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    workload: LLMWorkload | str | None = None,
    max_concurrent: int | None = None,
    max_qpm: int | None = None,
    default_pause_seconds: float | None = None,
    jitter_range: float | None = None,
) -> LLMRateLimiter:
    """Return the scoped LLMRateLimiter, lazily initialised.

    Limiters are process-local and keyed by effective tenant plus resolved
    agent. If a later lookup for the same scope uses changed limiter settings,
    the registry entry is replaced for subsequent calls while any in-flight
    calls on the old limiter drain naturally.

    Args:
        scope_key: Explicit tenant-local agent limiter scope.
        tenant_id: Effective tenant ID when no scope key is provided.
        agent_id: Resolved agent ID when no scope key is provided.
        workload: Workload identity whose concurrency pool should be used.
        max_concurrent: Workload-specific cap on concurrent in-flight calls.
        max_qpm: Shared maximum queries per minute. 0 = disabled.
        default_pause_seconds: Shared pause duration (s) on a 429 response.
        jitter_range: Shared random jitter (s) added on top of the pause.
    """
    resolved_scope = resolve_rate_limiter_scope(
        scope_key,
        tenant_id=tenant_id,
        agent_id=agent_id,
    )
    resolved_workload = normalize_llm_workload(workload)
    shared_config = _normalize_shared_config_fingerprint(
        max_qpm=max_qpm,
        default_pause_seconds=default_pause_seconds,
        jitter_range=jitter_range,
    )
    workload_config = _normalize_workload_config_fingerprint(max_concurrent)
    now = time.monotonic()

    entry = _limiter_registry.get(resolved_scope)
    if entry is not None and entry.shared_config == shared_config:
        workload_entry = entry.workloads.get(resolved_workload)
        if (
            workload_entry is not None
            and workload_entry.config == workload_config
        ):
            entry.last_used_at = now
            workload_entry.last_used_at = now
            return workload_entry.limiter

    async with _get_init_lock():
        entry = _limiter_registry.get(resolved_scope)
        shared_replaced = (
            entry is not None and entry.shared_config != shared_config
        )
        if entry is None or shared_replaced:
            entry = _RateLimiterRegistryEntry(
                shared_state=_SharedLLMRateLimiterState(
                    scope_key=resolved_scope,
                    max_qpm=shared_config.max_qpm,
                    default_pause_seconds=(
                        shared_config.default_pause_seconds
                    ),
                    jitter_range=shared_config.jitter_range,
                ),
                shared_config=shared_config,
                workloads={},
                last_used_at=time.monotonic(),
            )
            _limiter_registry[resolved_scope] = entry

        workload_entry = entry.workloads.get(resolved_workload)
        if (
            workload_entry is not None
            and workload_entry.config == workload_config
        ):
            entry.last_used_at = time.monotonic()
            workload_entry.last_used_at = entry.last_used_at
            return workload_entry.limiter

        limiter = LLMRateLimiter(
            max_concurrent=workload_config.max_concurrent,
            max_qpm=shared_config.max_qpm,
            default_pause_seconds=shared_config.default_pause_seconds,
            jitter_range=shared_config.jitter_range,
            shared_state=entry.shared_state,
            scope_key=resolved_scope,
            workload=resolved_workload,
        )
        entry.workloads[resolved_workload] = _WorkloadRateLimiterRegistryEntry(
            limiter=limiter,
            config=workload_config,
            last_used_at=time.monotonic(),
        )
        entry.last_used_at = time.monotonic()

        if workload_entry is None and not shared_replaced:
            logger.info(
                "LLM rate limiter initialized: scope=%s/%s, workload=%s, "
                "max_concurrent=%d, max_qpm=%d, default_pause=%.1fs, "
                "jitter=%.1fs",
                resolved_scope.tenant_id,
                resolved_scope.agent_id,
                resolved_workload,
                workload_config.max_concurrent,
                shared_config.max_qpm,
                shared_config.default_pause_seconds,
                shared_config.jitter_range,
            )
        else:
            logger.info(
                "LLM rate limiter replaced: scope=%s/%s, workload=%s, "
                "max_concurrent=%d, max_qpm=%d, default_pause=%.1fs, "
                "jitter=%.1fs",
                resolved_scope.tenant_id,
                resolved_scope.agent_id,
                resolved_workload,
                workload_config.max_concurrent,
                shared_config.max_qpm,
                shared_config.default_pause_seconds,
                shared_config.jitter_range,
            )
    return limiter


def cleanup_idle_rate_limiters(max_idle_seconds: float) -> int:
    """Remove idle scoped limiter entries with no live limiter state.

    This helper is intentionally explicit so service lifecycle code can choose
    when to run cleanup. Entries with active calls, active streams, scoped
    cooldowns, or recent QPM window entries are never removed.
    """
    now = time.monotonic()
    removed = 0
    for scope, entry in list(_limiter_registry.items()):
        shared_stats = entry.shared_state.stats()
        if shared_stats["is_paused"] or shared_stats["requests_last_60s"] > 0:
            continue
        for workload, workload_entry in list(entry.workloads.items()):
            stats = workload_entry.limiter.stats()
            if (
                stats["current_in_flight"] > 0
                or stats["current_active_streams"] > 0
            ):
                continue
            if now - workload_entry.last_used_at < max_idle_seconds:
                continue
            del entry.workloads[workload]
            removed += 1
            logger.info(
                "LLM rate limiter cleaned up: scope=%s/%s, workload=%s",
                scope.tenant_id,
                scope.agent_id,
                workload,
            )
        if not entry.workloads:
            del _limiter_registry[scope]
    return removed


def reset_rate_limiter() -> None:
    """Reset all scoped limiter entries (for testing or service restart)."""
    _limiter_registry.clear()
