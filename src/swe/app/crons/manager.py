# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ...config import get_heartbeat_config
from ...config.config import HeartbeatConfig

from ..tenant_context import bind_tenant_context
from ..console_push_store import append as push_store_append
from .coordination import (
    CoordinationConfig,
    CronCoordination,
    execution_lock_context,
)
from .executor import CronExecutor
from .heartbeat import (
    is_cron_expression,
    parse_heartbeat_cron,
    parse_heartbeat_every,
    run_heartbeat_once,
)
from .models import CronJobSpec, CronJobState
from .repo.base import BaseJobRepository

HEARTBEAT_JOB_ID = "_heartbeat"

logger = logging.getLogger(__name__)


@dataclass
class _Runtime:
    sem: asyncio.Semaphore


class CronManager:
    """Manages scheduled cron jobs and heartbeat.

    This class has been refactored to support Redis-coordinated leadership:
    - Passive initialization: The manager is created but scheduler not started
    - Explicit activation: When leadership is acquired, start() is called
    - Explicit deactivation: When leadership is lost, stop() is called
    - Reload from repo: When configuration changes, reload() rebuilds schedule
    """

    def __init__(
        self,
        *,
        repo: BaseJobRepository,
        heartbeat_repo: Any = None,
        runner: Any,
        channel_manager: Any,
        timezone: str = "UTC",  # pylint: disable=redefined-outer-name
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        coordination_config: Optional[CoordinationConfig] = None,
    ):
        self._repo = repo
        self._heartbeat_repo = heartbeat_repo
        self._runner = runner
        self._channel_manager = channel_manager
        self._agent_id = agent_id
        self._tenant_id = tenant_id
        self._timezone = timezone

        # Scheduler is created but NOT started in __init__
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._executor = CronExecutor(
            runner=runner,
            channel_manager=channel_manager,
        )

        self._lock = asyncio.Lock()
        self._states: Dict[str, CronJobState] = {}
        self._rt: Dict[str, _Runtime] = {}
        self._started = False

        # Coordination for multi-instance leadership
        self._coordination: Optional[CronCoordination] = None
        if coordination_config is not None and coordination_config.enabled:
            self._coordination = CronCoordination(
                tenant_id=tenant_id,
                agent_id=agent_id or "default",
                config=coordination_config,
            )
            # Set callbacks
            self._coordination.set_reload_callback(self._on_reload_signal)
            self._coordination.set_lease_lost_callback(self._on_lease_lost)
            self._coordination.set_become_leader_callback(self._on_become_leader)

        self._active_jobs: set[str] = set()  # Track which jobs are scheduled

    @property
    def is_started(self) -> bool:
        """Check if the scheduler is currently started."""
        return self._started

    @property
    def is_leader(self) -> bool:
        """Check if this instance is the current leader (if coordination enabled)."""
        if self._coordination is None:
            return True  # No coordination = always leader
        return self._coordination.is_leader

    async def initialize(self) -> None:
        """Passive initialization - prepare resources but don't start scheduler.

        This is called during workspace setup. The scheduler is NOT started
        here - that happens in activate() when leadership is confirmed.
        """
        async with self._lock:
            if self._scheduler is not None:
                return

            self._scheduler = AsyncIOScheduler(timezone=self._timezone)
            logger.debug(
                "CronManager initialized (passive): agent=%s",
                self._agent_id,
            )

    async def connect_coordination(self) -> bool:
        """Connect to Redis coordination.

        Returns True if connected/coordination enabled, False otherwise.
        """
        if self._coordination is None:
            return True  # No coordination needed

        return await self._coordination.connect()

    async def disconnect_coordination(self) -> None:
        """Disconnect from Redis coordination."""
        if self._coordination is not None:
            await self._coordination.disconnect()

    async def activate(self) -> bool:
        """Activate scheduling - acquire leadership and start scheduler.

        Returns True if this instance became the active leader,
        False if this is a follower.

        Raises:
            RedisNotAvailableError: If coordination is enabled but Redis is not available.
        """
        await self.initialize()

        # Connect coordination first
        connected = await self.connect_coordination()

        if self._coordination is not None:
            # Coordination is enabled - we must connect to Redis
            if not connected:
                logger.error(
                    "CronManager failed to activate: Redis coordination enabled "
                    "but Redis is not available (agent=%s)",
                    self._agent_id,
                )
                raise RuntimeError(
                    "Redis coordination is enabled but Redis is not available. "
                    "Please check Redis connection or disable coordination.",
                )

            # Try to acquire leadership
            is_leader = await self._coordination.activate()
            if not is_leader:
                logger.info(
                    "CronManager activated as follower: agent=%s",
                    self._agent_id,
                )
                # Start candidate loop for automatic failover
                await self._coordination.start_candidate_loop()
                return False
            logger.info(
                "CronManager activated as leader: agent=%s instance=%s",
                self._agent_id,
                self._coordination.instance_id,
            )
        else:
            logger.info(
                "CronManager activated (no coordination): agent=%s",
                self._agent_id,
            )

        # Start the scheduler
        try:
            await self._do_start()
        except Exception:
            logger.exception(
                "Failed to start scheduler during activate: agent=%s",
                self._agent_id,
            )
            await self._cleanup_failed_leader_startup()
            raise
        return True

    async def deactivate(self) -> None:
        """Deactivate scheduling - stop scheduler and release leadership."""
        await self._do_stop()

        if self._coordination is not None:
            await self._coordination.deactivate()
            logger.info(
                "CronManager deactivated: agent=%s",
                self._agent_id,
            )

    async def reload(self) -> None:
        """Reload jobs from repository and rebuild schedule.

        This is called when:
        - A reload signal is received from another instance
        - Local cron mutations are made
        """
        async with self._lock:
            if not self._started or self._scheduler is None:
                logger.debug(
                    "Cannot reload: scheduler not started (agent=%s)",
                    self._agent_id,
                )
                return

            logger.info(
                "Reloading cron schedule from repository: agent=%s",
                self._agent_id,
            )

            # Clear existing jobs (except heartbeat)
            jobs_to_remove = [
                job_id
                for job_id in self._active_jobs
                if job_id != HEARTBEAT_JOB_ID
            ]
            for job_id in jobs_to_remove:
                if self._scheduler.get_job(job_id):
                    self._scheduler.remove_job(job_id)
                self._active_jobs.discard(job_id)

            # Load jobs from repo
            try:
                jobs_file = await self._repo.load()
                for job in jobs_file.jobs:
                    try:
                        await self._register_or_update(job)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.warning(
                            "Skipping invalid cron job during reload: "
                            "job_id=%s name=%s error=%s",
                            job.id,
                            job.name,
                            repr(e),
                        )
            except Exception as e:  # pylint: disable=broad-except
                logger.error("Failed to reload jobs from repository: %s", e)

            # Reload heartbeat
            await self._update_heartbeat()

            logger.info(
                "Cron schedule reloaded: agent=%s jobs=%d",
                self._agent_id,
                len(self._active_jobs),
            )

    async def _do_start(self) -> None:
        """Internal: Start the scheduler and load initial jobs."""
        async with self._lock:
            if self._started:
                return

            if self._scheduler is None:
                raise RuntimeError("CronManager not initialized")

            jobs_file = await self._repo.load()

            self._scheduler.start()
            for job in jobs_file.jobs:
                try:
                    await self._register_or_update(job)
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(
                        "Skipping invalid cron job during startup: "
                        "job_id=%s name=%s cron=%s error=%s",
                        job.id,
                        job.name,
                        job.schedule.cron,
                        repr(e),
                    )
                    if job.enabled:
                        disabled_job = job.model_copy(
                            update={"enabled": False},
                        )
                        await self._repo.upsert_job(disabled_job)
                        logger.warning(
                            "Auto-disabled invalid cron job: "
                            "job_id=%s name=%s",
                            job.id,
                            job.name,
                        )

            # Heartbeat: scheduled job when enabled in config
            await self._update_heartbeat()

            self._started = True
            logger.info(
                "CronManager started: agent=%s jobs=%d",
                self._agent_id,
                len(self._active_jobs),
            )

    async def _do_stop(self) -> None:
        """Internal: Stop the scheduler."""
        async with self._lock:
            if not self._started:
                return
            if self._scheduler is not None:
                self._scheduler.shutdown(wait=False)
            self._started = False
            self._active_jobs.clear()
            logger.info("CronManager stopped: agent=%s", self._agent_id)

    def _on_reload_signal(self) -> None:
        """Callback invoked when a reload signal is received."""
        logger.info(
            "Received reload signal, scheduling reload: agent=%s",
            self._agent_id,
        )
        # Schedule reload in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.reload())
        except RuntimeError:
            # No event loop running - this shouldn't happen in normal operation
            logger.warning(
                "Cannot schedule reload: no event loop (agent=%s)",
                self._agent_id,
            )

    def _on_lease_lost(self) -> None:
        """Callback invoked when the leadership lease is lost.

        This stops the scheduler to prevent duplicate executions.
        """
        logger.warning(
            "Lease lost callback invoked, deactivating scheduler: agent=%s",
            self._agent_id,
        )
        # Schedule deactivate in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.deactivate())
        except RuntimeError:
            # No event loop running - this shouldn't happen in normal operation
            logger.warning(
                "Cannot schedule deactivate: no event loop (agent=%s)",
                self._agent_id,
            )

    def _on_become_leader(self) -> None:
        """Callback invoked when this instance becomes leader via candidate loop.

        This starts the scheduler to begin cron execution.
        If startup fails, releases the lease to allow another instance to take over.
        """
        logger.info(
            "Become leader callback invoked, starting scheduler: agent=%s",
            self._agent_id,
        )
        # Schedule start in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._become_leader_and_start())
        except RuntimeError:
            # No event loop running - this shouldn't happen in normal operation
            logger.warning(
                "Cannot schedule start: no event loop (agent=%s)",
                self._agent_id,
            )

    async def _become_leader_and_start(self) -> None:
        """Internal: Start scheduler after becoming leader via candidate loop.

        This wrapper handles startup failures by releasing the lease,
        allowing another instance to take over.
        """
        try:
            await self._do_start()
            logger.info(
                "Successfully started scheduler after becoming leader: agent=%s",
                self._agent_id,
            )
        except Exception:
            logger.exception(
                "Failed to start scheduler after becoming leader: agent=%s",
                self._agent_id,
            )
            try:
                await self._cleanup_failed_leader_startup()
            except Exception:
                logger.exception(
                    "Unexpected error during startup failure cleanup: "
                    "agent=%s",
                    self._agent_id,
                )
            return

    async def _cleanup_failed_leader_startup(self) -> None:
        """Rollback partial startup and release leadership on startup failure.

        Never raises: best-effort cleanup for callback/background safety.
        """
        # _do_start() can fail after starting APScheduler but before _started=True.
        # Roll back scheduler runtime state before manager-level cleanup.
        had_running_scheduler = self._scheduler is not None and getattr(
            self._scheduler, "running", False
        )
        safe_to_release = True
        if had_running_scheduler:
            safe_to_release = self._rollback_partially_started_scheduler()

        if had_running_scheduler and not safe_to_release:
            # Scheduler may still run jobs: keep coordination ownership to
            # avoid split-brain duplicate execution.
            self._started = True
            logger.error(
                "Emergency path: scheduler not safely stopped during startup "
                "rollback, keeping leadership: agent=%s",
                self._agent_id,
            )
            return

        self._started = False
        self._active_jobs.clear()
        self._rt.clear()

        if self._coordination is not None:
            logger.warning(
                "Releasing lease due to startup failure: agent=%s",
                self._agent_id,
            )
        try:
            await self.deactivate()
        except Exception:
            logger.exception(
                "Failed to deactivate during startup failure cleanup: "
                "agent=%s",
                self._agent_id,
            )
            return

    def _rollback_partially_started_scheduler(self) -> bool:
        """Try to stop/disable a running scheduler after startup failure."""
        if self._scheduler is None:
            return True

        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            logger.exception(
                "Failed to shutdown scheduler during rollback: agent=%s",
                self._agent_id,
            )
            return self._best_effort_disable_scheduler()

        # AsyncIOScheduler is not restartable after shutdown.
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        return True

    def _best_effort_disable_scheduler(self) -> bool:
        """Best-effort disable path when scheduler.shutdown() fails."""
        if self._scheduler is None:
            return True

        paused = False
        removed = False

        try:
            self._scheduler.pause()
            paused = True
        except Exception:
            logger.exception(
                "Failed to pause scheduler during rollback: agent=%s",
                self._agent_id,
            )

        try:
            self._scheduler.remove_all_jobs()
            removed = True
            self._active_jobs.clear()
        except Exception:
            logger.exception(
                "Failed to remove scheduler jobs during rollback: agent=%s",
                self._agent_id,
            )

        if paused or removed:
            logger.warning(
                "Scheduler shutdown failed, used disable fallback: "
                "agent=%s paused=%s removed=%s",
                self._agent_id,
                paused,
                removed,
            )
            return True
        return False

    async def _update_heartbeat(self) -> None:
        """Update heartbeat job based on current config."""
        if self._scheduler is None:
            return

        # Remove existing heartbeat job if present
        if self._scheduler.get_job(HEARTBEAT_JOB_ID):
            self._scheduler.remove_job(HEARTBEAT_JOB_ID)
            self._active_jobs.discard(HEARTBEAT_JOB_ID)

        hb = await self.get_heartbeat_config()
        if getattr(hb, "enabled", False):
            trigger = self._build_heartbeat_trigger(hb.every)
            self._scheduler.add_job(
                self._heartbeat_callback,
                trigger=trigger,
                id=HEARTBEAT_JOB_ID,
                replace_existing=True,
            )
            self._active_jobs.add(HEARTBEAT_JOB_ID)
            logger.info(
                "Heartbeat job scheduled for agent %s: every=%s",
                self._agent_id,
                hb.every,
            )

    # ----- read/state -----

    async def list_jobs(self) -> list[CronJobSpec]:
        return await self._repo.list_jobs()

    async def get_job(self, job_id: str) -> Optional[CronJobSpec]:
        return await self._repo.get_job(job_id)

    async def get_heartbeat_config(self) -> HeartbeatConfig:
        if self._heartbeat_repo is None:
            return get_heartbeat_config(self._agent_id)
        return await self._heartbeat_repo.get()

    async def update_heartbeat_config(
        self,
        config: HeartbeatConfig,
    ) -> HeartbeatConfig:
        if self._heartbeat_repo is None:
            raise RuntimeError("Heartbeat repository is not configured")

        async with self._lock:
            saved = await self._heartbeat_repo.set(config)
            if self._started and self._scheduler is not None:
                await self._update_heartbeat()

        if self._coordination is not None:
            try:
                await self._coordination.publish_reload()
            except Exception:  # pylint: disable=broad-except
                logger.warning(
                    "Failed to publish reload signal after heartbeat update",
                    exc_info=True,
                )

        return saved

    def get_state(self, job_id: str) -> CronJobState:
        return self._states.get(job_id, CronJobState())

    # ----- write/control -----

    async def create_or_replace_job(self, spec: CronJobSpec) -> None:
        async with self._lock:
            await self._repo.upsert_job(spec)
            if self._started and self._scheduler is not None:
                await self._register_or_update(spec)

    async def delete_job(self, job_id: str) -> bool:
        async with self._lock:
            if self._started and self._scheduler is not None:
                if self._scheduler.get_job(job_id):
                    self._scheduler.remove_job(job_id)
                self._active_jobs.discard(job_id)
            self._states.pop(job_id, None)
            self._rt.pop(job_id, None)
            return await self._repo.delete_job(job_id)

    async def pause_job(self, job_id: str) -> bool:
        """Pause a job - disables execution and persists to repository.

        Args:
            job_id: The job ID to pause.

        Returns:
            True if job was found and paused, False otherwise.
        """
        async with self._lock:
            # Get current job from repo
            job = await self._repo.get_job(job_id)
            if not job:
                return False

            # Update the job to disabled
            if job.enabled:
                disabled_job = job.model_copy(update={"enabled": False})
                await self._repo.upsert_job(disabled_job)

            # Pause in scheduler if started
            if self._started and self._scheduler is not None:
                if self._scheduler.get_job(job_id):
                    self._scheduler.pause_job(job_id)

            return True

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job - enables execution and persists to repository.

        Args:
            job_id: The job ID to resume.

        Returns:
            True if job was found and resumed, False otherwise.
        """
        async with self._lock:
            # Get current job from repo
            job = await self._repo.get_job(job_id)
            if not job:
                return False

            # Update the job to enabled
            if not job.enabled:
                enabled_job = job.model_copy(update={"enabled": True})
                await self._repo.upsert_job(enabled_job)

            # Resume in scheduler if started
            if self._started and self._scheduler is not None:
                if self._scheduler.get_job(job_id):
                    self._scheduler.resume_job(job_id)

            return True

    async def reschedule_heartbeat(self) -> None:
        """Reload heartbeat config and update or remove the heartbeat job.

        Note: This should be called after activate() when the manager is leader.
        """
        async with self._lock:
            if not self._started:
                logger.warning(
                    f"CronManager not started for agent {self._agent_id}, "
                    f"cannot reschedule heartbeat. This should not happen.",
                )
                return

            await self._update_heartbeat()

    async def run_job(self, job_id: str) -> None:
        """Trigger a job to run in the background (fire-and-forget).

        This is a MANUAL execution - it bypasses the execution lock and
        does NOT participate in timed de-duplication.

        Raises KeyError if the job does not exist.
        The actual execution happens asynchronously; errors are logged
        and reflected in the job state but NOT propagated to the caller.
        """
        job = await self._repo.get_job(job_id)
        if not job:
            raise KeyError(f"Job not found: {job_id}")
        logger.info(
            "cron run_job (manual, bypasses execution lock): "
            "job_id=%s channel=%s task_type=%s "
            "target_user_id=%s target_session_id=%s",
            job_id,
            job.dispatch.channel,
            job.task_type,
            (job.dispatch.target.user_id or "")[:40],
            (job.dispatch.target.session_id or "")[:40],
        )
        task = asyncio.create_task(
            self._execute_once(job),
            name=f"c ron-run-{job_id}",
        )
        task.add_done_callback(lambda t: self._task_done_cb(t, job))

    # ----- callbacks -----

    def _task_done_cb(self, task: asyncio.Task, job: CronJobSpec) -> None:
        """Suppress and log exceptions from fire-and-forget tasks.

        On failure, push an error message to the console push store so
        the frontend can display it.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "cron background task %s failed: %s",
                task.get_name(),
                repr(exc),
            )
            # Push error to the console for the frontend to display
            session_id = job.dispatch.target.session_id
            if session_id:
                error_text = f"❌ Cron job [{job.name}] failed: {exc}"

                async def _push_error() -> None:
                    await push_store_append(
                        session_id,
                        error_text,
                        tenant_id=job.tenant_id,
                    )

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(_push_error())
                else:
                    loop.create_task(_push_error())

    # ----- internal -----

    async def _register_or_update(self, spec: CronJobSpec) -> None:
        if self._scheduler is None:
            return

        # Validate and build trigger first. If cron is invalid, fail fast
        # without mutating scheduler/runtime state.
        trigger = self._build_trigger(spec)

        # per-job concurrency semaphore
        self._rt[spec.id] = _Runtime(
            sem=asyncio.Semaphore(spec.runtime.max_concurrency),
        )

        # replace existing
        if self._scheduler.get_job(spec.id):
            self._scheduler.remove_job(spec.id)

        self._scheduler.add_job(
            self._scheduled_callback,
            trigger=trigger,
            id=spec.id,
            args=[spec.id],
            misfire_grace_time=spec.runtime.misfire_grace_seconds,
            replace_existing=True,
        )
        self._active_jobs.add(spec.id)

        if not spec.enabled:
            self._scheduler.pause_job(spec.id)

        # update next_run
        aps_job = self._scheduler.get_job(spec.id)
        st = self._states.get(spec.id, CronJobState())
        st.next_run_at = aps_job.next_run_time if aps_job else None
        self._states[spec.id] = st

    def _build_trigger(self, spec: CronJobSpec) -> CronTrigger:
        # enforce 5 fields (no seconds)
        parts = [p for p in spec.schedule.cron.split() if p]
        if len(parts) != 5:
            raise ValueError(
                f"cron must have 5 fields, got {len(parts)}:"
                f" {spec.schedule.cron}",
            )

        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=spec.schedule.timezone,
        )

    def _build_heartbeat_trigger(
        self,
        every: str,
    ) -> Union[CronTrigger, IntervalTrigger]:
        """Build a trigger from the heartbeat *every* value.

        Returns CronTrigger for cron expressions,
        IntervalTrigger for interval strings.
        """
        if is_cron_expression(every):
            minute, hour, day, month, day_of_week = parse_heartbeat_cron(every)
            return CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
        interval_seconds = parse_heartbeat_every(every)
        return IntervalTrigger(seconds=interval_seconds)

    async def _scheduled_callback(self, job_id: str) -> None:
        """Callback invoked by APScheduler for timed execution.

        This uses the execution lock to prevent duplicate runs during
        leadership transitions.
        """
        # Check if we're still the leader
        if self._coordination is not None and not self._coordination.is_leader:
            logger.debug(
                "Skipping scheduled job: not leader (agent=%s, job=%s)",
                self._agent_id,
                job_id,
            )
            return

        job = await self._repo.get_job(job_id)
        if not job:
            return

        # Use execution lock for timed execution
        if self._coordination is not None:
            async with execution_lock_context(
                self._coordination,
                job_id,
                job.runtime.timeout_seconds,
            ) as acquired:
                if not acquired:
                    logger.info(
                        "Skipping duplicate timed execution: "
                        "job_id=%s (another instance holds the lock)",
                        job_id,
                    )
                    st = self._states.get(job_id, CronJobState())
                    st.last_status = "skipped"
                    st.last_run_at = datetime.now(timezone.utc)
                    self._states[job_id] = st
                    return

                await self._execute_once(job)
        else:
            # No coordination - execute directly
            await self._execute_once(job)

        # refresh next_run
        if self._scheduler is not None:
            aps_job = self._scheduler.get_job(job_id)
            st = self._states.get(job_id, CronJobState())
            st.next_run_at = aps_job.next_run_time if aps_job else None
            self._states[job_id] = st

    async def _heartbeat_callback(self) -> None:
        """Run one heartbeat (HEARTBEAT.md as query, optional dispatch)."""
        # Check if we're still the leader
        if self._coordination is not None and not self._coordination.is_leader:
            logger.debug(
                "Skipping heartbeat: not leader (agent=%s)",
                self._agent_id,
            )
            return

        try:
            # Get workspace_dir from runner if available
            workspace_dir = None
            if hasattr(self._runner, "workspace_dir"):
                workspace_dir = self._runner.workspace_dir

            tenant_id = None
            if (
                hasattr(self._runner, "_workspace")
                and self._runner._workspace is not None
            ):
                tenant_id = getattr(self._runner._workspace, "tenant_id", None)

            with bind_tenant_context(
                tenant_id=tenant_id,
                workspace_dir=workspace_dir,
            ):
                await run_heartbeat_once(
                    runner=self._runner,
                    channel_manager=self._channel_manager,
                    agent_id=self._agent_id,
                    workspace_dir=workspace_dir,
                    heartbeat_config=await self.get_heartbeat_config(),
                )
        except asyncio.CancelledError:
            logger.info("heartbeat cancelled")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("heartbeat run failed")

    async def _execute_once(self, job: CronJobSpec) -> None:
        rt = self._rt.get(job.id)
        if not rt:
            rt = _Runtime(sem=asyncio.Semaphore(job.runtime.max_concurrency))
            self._rt[job.id] = rt

        async with rt.sem:
            st = self._states.get(job.id, CronJobState())
            st.last_status = "running"
            self._states[job.id] = st

            try:
                await self._executor.execute(job)
                st.last_status = "success"
                st.last_error = None
                logger.info(
                    "cron _execute_once: job_id=%s status=success",
                    job.id,
                )
            except asyncio.CancelledError:
                st.last_status = "cancelled"
                st.last_error = "Job was cancelled"
                logger.info(
                    "cron _execute_once: job_id=%s status=cancelled",
                    job.id,
                )
                raise
            except Exception as e:  # pylint: disable=broad-except
                st.last_status = "error"
                st.last_error = repr(e)
                logger.warning(
                    "cron _execute_once: job_id=%s status=error error=%s",
                    job.id,
                    repr(e),
                )
                raise
            finally:
                st.last_run_at = datetime.now(timezone.utc)
                self._states[job.id] = st

    # ----- Legacy API compatibility -----

    async def start(self) -> None:
        """Legacy start method - calls activate().

        DEPRECATED: Use activate() instead for proper coordination support.
        """
        await self.activate()

    async def stop(self) -> None:
        """Legacy stop method - calls deactivate().

        DEPRECATED: Use deactivate() instead for proper coordination support.
        """
        await self.deactivate()
