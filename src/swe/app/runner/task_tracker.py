# -*- coding: utf-8 -*-
"""Task tracker for background runs: streaming, reconnect, multi-subscriber.

run_key is ChatSpec.id (chat_id). Per run: task, queues, event buffer.
Reconnects get buffer replay + new events. Cleanup when task completes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import weakref
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Coroutine

from .shared_run_coordinator import (
    RedisSharedRunCoordinator,
    build_runtime_instance_id,
)
from .run_models import ChatRunContext

logger = logging.getLogger(__name__)

_SENTINEL = None


@dataclass
class _RunState:
    """Per-run state (task, queues, buffer), guarded by tracker lock."""

    task: asyncio.Future
    queues: list[asyncio.Queue] = field(default_factory=list)
    buffer: list[str] = field(default_factory=list)
    startup_future: asyncio.Future | None = None
    heartbeat_task: asyncio.Task | None = None
    cancel_watch_task: asyncio.Task | None = None


class TaskTracker:
    """Per-workspace tracker: run_key -> RunState.

    All mutations to _runs under _lock. Producer broadcasts under lock.
    Subscribers use unbounded per-connection queues; disconnect removes them
    via :meth:`detach_subscriber`.
    """

    def __init__(
        self,
        *,
        coordinator=None,
        instance_id: str | None = None,
        heartbeat_seconds: float | None = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._runs: dict[str, _RunState] = {}
        self._coordinator = coordinator or RedisSharedRunCoordinator(
            namespace="default:default",
        )
        self._instance_id = instance_id or build_runtime_instance_id()
        self._heartbeat_seconds = (
            heartbeat_seconds
            if heartbeat_seconds is not None
            else self._coordinator.heartbeat_seconds
        )
        self._chat_manager = None

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    def bind_chat_manager(self, chat_manager) -> None:
        self._chat_manager = chat_manager

    async def get_status(self, run_key: str) -> str:
        """Return ``'idle'`` or ``'running'``."""
        lease = await self._coordinator.get_run(run_key)
        return "idle" if lease is None else "running"

    async def get_owner(self, run_key: str) -> str | None:
        lease = await self._coordinator.get_run(run_key)
        if lease is None:
            return None
        return lease.owner_instance_id

    async def has_active_tasks(self) -> bool:
        """Check if any tasks are currently running.

        Returns:
            bool: True if any tasks are active, False otherwise
        """
        async with self._lock:
            for state in self._runs.values():
                if not state.task.done():
                    return True
            return False

    async def list_active_tasks(self) -> list[str]:
        """List all currently running task keys.

        Returns:
            list[str]: List of active run_keys
        """
        async with self._lock:
            return [
                run_key
                for run_key, state in self._runs.items()
                if not state.task.done()
            ]

    async def wait_all_done(self, timeout: float = 300.0) -> bool:
        """Wait for all active tasks to complete.

        Args:
            timeout: Maximum time to wait in seconds (default: 300s = 5min)

        Returns:
            bool: True if all tasks completed, False if timeout occurred
        """

        async def _wait_loop() -> None:
            while await self.has_active_tasks():
                await asyncio.sleep(0.5)

        try:
            await asyncio.wait_for(_wait_loop(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def attach(self, run_key: str) -> asyncio.Queue | None:
        """Attach to an existing local run.

        Returns a new queue pre-filled with the event buffer, or ``None``
        if no local run is active for *run_key*.
        """
        async with self._lock:
            state = self._runs.get(run_key)
            if state is None or state.task.done():
                return None
            q: asyncio.Queue = asyncio.Queue()
            for sse in state.buffer:
                q.put_nowait(sse)
            state.queues.append(q)
            return q

    async def detach_subscriber(
        self,
        run_key: str,
        queue: asyncio.Queue,
    ) -> None:
        """Remove *queue* from *run_key*'s subscriber list.

        Idempotent if the run ended or *queue* was already removed.
        """
        async with self._lock:
            state = self._runs.get(run_key)
            if state is None:
                return
            try:
                state.queues.remove(queue)
            except ValueError:
                pass

    async def request_stop(self, run_key: str) -> bool:
        """Cancel the run. Returns ``True`` if it was running."""
        stopped = await self._coordinator.request_cancel(run_key)
        if not stopped:
            return False
        async with self._lock:
            state = self._runs.get(run_key)
            if state is not None and not state.task.done():
                state.task.cancel()
        return True

    async def attach_or_start(
        self,
        run_key: str,
        payload: Any,
        stream_fn: Callable[..., Coroutine],
        run_context: ChatRunContext | None = None,
    ) -> tuple[asyncio.Queue, bool]:
        """Attach to an existing run or start a new one.

        Returns ``(queue, is_new_run)``.
        """
        startup_future: asyncio.Future | None = None
        should_start = False
        async with self._lock:
            state = self._runs.get(run_key)
            if state is not None and not state.task.done():
                q: asyncio.Queue = asyncio.Queue()
                for sse in state.buffer:
                    q.put_nowait(sse)
                state.queues.append(q)
                startup_future = state.startup_future
            else:
                my_queue: asyncio.Queue = asyncio.Queue()
                startup_future = asyncio.get_running_loop().create_future()
                state = _RunState(
                    task=asyncio.get_running_loop().create_future(),
                    queues=[my_queue],
                    buffer=[],
                    startup_future=startup_future,
                )
                self._runs[run_key] = state
                should_start = True

        if not should_start:
            assert startup_future is not None
            if not startup_future.done():
                try:
                    await startup_future
                except Exception:
                    await self.detach_subscriber(run_key, q)
                    raise
            return q, False

        run = state
        assert run is not None
        tracker_ref = weakref.ref(self)

        async def _cancel_local_run() -> None:
            async with self._lock:
                state = self._runs.get(run_key)
                if state is not None and not state.task.done():
                    state.task.cancel()

        async def _heartbeat() -> None:
            try:
                while True:
                    await asyncio.sleep(self._heartbeat_seconds)
                    refreshed = await self._coordinator.refresh_run(
                        run_key,
                        self._instance_id,
                    )
                    if refreshed is None:
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "shared run heartbeat failed run_key=%s",
                    run_key,
                )
                await _cancel_local_run()

        async def _watch_cancel() -> None:
            try:
                while True:
                    await asyncio.sleep(self._heartbeat_seconds)
                    lease = await self._coordinator.get_run(run_key)
                    if lease is None:
                        return
                    if lease.cancel_requested:
                        async with self._lock:
                            state = self._runs.get(run_key)
                            if state is not None and not state.task.done():
                                state.task.cancel()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "shared run cancel watch failed run_key=%s",
                    run_key,
                )
                await _cancel_local_run()

        async def _producer() -> None:
            run_record = None
            try:
                if self._chat_manager is not None and run_context is not None:
                    run_record = await self._chat_manager.start_run(
                        run_context,
                    )
                async for sse in stream_fn(payload):
                    tracker = tracker_ref()
                    if tracker is None:
                        return
                    async with tracker.lock:
                        run.buffer.append(sse)
                        for q in run.queues:
                            q.put_nowait(sse)
                if run_record is not None:
                    await self._chat_manager.finish_run(
                        run_record.id,
                        status="completed",
                    )
            except asyncio.CancelledError:
                if run_record is not None:
                    await self._chat_manager.finish_run(
                        run_record.id,
                        status="cancelled",
                    )
                logger.debug("run cancelled run_key=%s", run_key)
            except Exception as exc:
                if run_record is not None:
                    await self._chat_manager.finish_run(
                        run_record.id,
                        status="failed",
                        error=str(exc),
                    )
                logger.exception("run error run_key=%s", run_key)
                err_sse = (
                    "data: "
                    f"{json.dumps({'error': 'internal server error'})}\n\n"
                )
                tracker = tracker_ref()
                if tracker is not None:
                    async with tracker.lock:
                        run.buffer.append(err_sse)
                        for q in run.queues:
                            q.put_nowait(err_sse)
            finally:
                if run.heartbeat_task is not None:
                    run.heartbeat_task.cancel()
                if run.cancel_watch_task is not None:
                    run.cancel_watch_task.cancel()
                try:
                    await self._coordinator.clear_run(
                        run_key,
                        self._instance_id,
                    )
                except Exception:
                    logger.exception(
                        "shared run clear failed run_key=%s",
                        run_key,
                    )
                tracker = tracker_ref()
                if tracker is not None:
                    async with tracker.lock:
                        for q in run.queues:
                            q.put_nowait(_SENTINEL)
                        tracker._runs.pop(run_key, None)

        try:
            await self._coordinator.start_run(run_key, self._instance_id)
        except Exception as exc:
            async with self._lock:
                current = self._runs.get(run_key)
                if current is run:
                    self._runs.pop(run_key, None)
                if (
                    run.startup_future is not None
                    and not run.startup_future.done()
                ):
                    run.startup_future.set_exception(exc)
            raise

        async with self._lock:
            run.task = asyncio.create_task(_producer())
            run.heartbeat_task = asyncio.create_task(_heartbeat())
            run.cancel_watch_task = asyncio.create_task(_watch_cancel())
            if (
                run.startup_future is not None
                and not run.startup_future.done()
            ):
                run.startup_future.set_result(None)
            run.startup_future = None
            return my_queue, True

    async def stream_from_queue(
        self,
        queue: asyncio.Queue,
        run_key: str,
    ) -> AsyncGenerator[str, None]:
        """Yield SSE strings from *queue* until the sentinel ``None``.

        Always detaches *queue* from *run_key* when this stream ends or is
        closed (including client disconnect), so reconnects do not leak queues.
        """
        try:
            while True:
                try:
                    event = await queue.get()
                    if event is _SENTINEL:
                        break
                    yield event
                except asyncio.CancelledError:
                    break
        finally:
            await self.detach_subscriber(run_key, queue)

    async def aclose(self) -> None:
        await self._coordinator.close()
