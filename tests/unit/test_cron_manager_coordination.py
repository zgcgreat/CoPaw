# -*- coding: utf-8 -*-
"""Unit tests for CronManager with Redis coordination.

These tests verify:
- CronManager activation/deactivation with coordination
- Manual run_job stays outside scheduler ownership semantics
- Timed execution uses lease preflight by default
- Reload and definition convergence behavior
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all tests as requiring Redis
pytestmark = [
    pytest.mark.asyncio,
]

# Check if redis is available
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


from swe.app.crons.manager import CronManager, HEARTBEAT_JOB_ID
from swe.config.llm_workload import (
    LLM_WORKLOAD_CHAT,
    LLM_WORKLOAD_CRON,
    bind_llm_workload,
    get_current_llm_workload,
)
from swe.app.crons.coordination import CoordinationConfig
from swe.app.crons.models import (
    CronJobSpec,
    CronJobState,
    ScheduleSpec,
    DispatchSpec,
    DispatchTarget,
    JobRuntimeSpec,
    CronJobRequest,
    JobsFile,
)
from swe.app.crons.repo.json_repo import JsonJobRepository


class _FakeDefinitionLock:
    def __init__(self, lock: asyncio.Lock, events: list[str]):
        self._lock = lock
        self._events = events

    async def release(self) -> None:
        self._events.append("release")
        self._lock.release()


class _FakeCoordination:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.events: list[str] = []
        self.version = 0
        self.is_leader = True

    async def acquire_definition_lock(self):
        await self._lock.acquire()
        self.events.append("acquire")
        return _FakeDefinitionLock(self._lock, self.events)

    async def bump_definition_version(self):
        self.version += 1
        self.events.append(f"bump:{self.version}")
        return self.version

    async def ensure_definition_version(self, version):
        self.version = max(self.version, version)
        self.events.append(f"sync:{self.version}")
        return self.version

    async def publish_reload(self, version=None):
        self.events.append(f"publish:{version}")
        return True

    async def get_definition_version(self):
        return self.version

    async def preflight_scheduler_execution(
        self,
        *,
        job_id: str,
        schedule_type: str,
    ):
        return True

    async def deactivate(self):
        return None


@pytest.fixture
def temp_jobs_file(tmp_path):
    """Create a temporary jobs.json file."""
    return tmp_path / "jobs.json"


@pytest.fixture
def coordination_config():
    """Default coordination config for tests."""
    return CoordinationConfig(
        enabled=True,
        redis_url="redis://localhost:6379/15",  # Use DB 15 for tests
        lease_ttl_seconds=10,
        lease_renew_interval_seconds=3,
        lock_safety_margin_seconds=5,
    )


@pytest.fixture
def mock_runner():
    """Create a mock runner."""
    runner = MagicMock()
    runner.workspace_dir = Path("/tmp/test")
    return runner


@pytest.fixture
def mock_channel_manager():
    """Create a mock channel manager."""
    return MagicMock()


@pytest.fixture
def sample_job_spec():
    """Create a sample job spec."""
    return CronJobSpec(
        id="test-job",
        name="Test Job",
        enabled=True,
        tenant_id="test-tenant",
        schedule=ScheduleSpec(
            type="cron",
            cron="0 0 * * *",  # Daily at midnight
            timezone="UTC",
        ),
        task_type="text",
        text="Hello from cron",
        dispatch=DispatchSpec(
            type="channel",
            channel="console",
            target=DispatchTarget(user_id="user1", session_id="session1"),
        ),
        runtime=JobRuntimeSpec(
            max_concurrency=1,
            timeout_seconds=30,
        ),
    )


class TestCronManagerLifecycle:
    """Tests for CronManager lifecycle with coordination."""

    async def test_manager_without_coordination(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test manager works without coordination (backwards compatible)."""
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
        )

        # Initialize
        await manager.initialize()
        assert manager._scheduler is not None
        assert not manager.is_started

        # Activate (no coordination = becomes leader)
        is_leader = await manager.activate()
        assert is_leader is True
        assert manager.is_started
        assert manager.is_leader

        # Deactivate
        await manager.deactivate()
        assert not manager.is_started

    async def test_manager_with_coordination_disabled(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test manager with disabled coordination."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        # Activate (disabled = becomes leader)
        is_leader = await manager.activate()
        assert is_leader is True
        assert manager.is_started

        await manager.deactivate()


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestCronManagerWithRedis:
    """Tests for CronManager that require Redis."""

    async def test_manager_activation_with_redis(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        coordination_config,
    ):
        """Test manager activation with Redis coordination."""
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=coordination_config,
        )

        # Activate - should connect and acquire leadership
        # If Redis is not running, this will raise RuntimeError
        try:
            is_leader = await manager.activate()
            assert isinstance(is_leader, bool)

            if is_leader:
                assert manager.is_started
                assert manager.is_leader

            await manager.deactivate()
        except RuntimeError as e:
            # Redis not available - this is expected if Redis is not running
            assert (
                "Redis coordination is enabled but Redis is not available"
                in str(e)
            )

    async def test_two_managers_leader_election(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        coordination_config,
    ):
        """Test that only one manager becomes leader."""
        # Create two separate repos pointing to the same file
        repo1 = JsonJobRepository(temp_jobs_file)
        repo2 = JsonJobRepository(temp_jobs_file)

        manager1 = CronManager(
            repo=repo1,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=coordination_config,
        )
        manager2 = CronManager(
            repo=repo2,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=coordination_config,
        )

        # Activate first manager - should become leader (or raise if Redis unavailable)
        try:
            is_leader1 = await manager1.activate()

            # If Redis is running and coordination worked
            if is_leader1:
                assert manager1.is_leader

                # Activate second manager - should be follower
                is_leader2 = await manager2.activate()
                assert not is_leader2
                assert not manager2.is_leader
                assert not manager2.is_started
        except RuntimeError as e:
            # Redis not available - this is expected if Redis is not running
            assert (
                "Redis coordination is enabled but Redis is not available"
                in str(e)
            )

        await manager1.deactivate()
        await manager2.deactivate()

    async def test_manager_reload(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test manager reload functionality."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        # Activate
        await manager.activate()

        # Create a job
        job = CronJobSpec(
            id="test-job",
            name="Test Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="text",
            text="Test",
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
            ),
        )
        await manager.create_or_replace_job(job)

        # Reload
        await manager.reload()

        # Job should still exist
        jobs = await manager.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "test-job"

        await manager.deactivate()

    async def test_manager_reload_handles_repo_load_failure(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Reload should not raise if repo.load() fails mid-rebuild."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        await manager.activate()

        manager._repo.load = AsyncMock(side_effect=RuntimeError("boom"))
        manager._refresh_definition_version_locked = AsyncMock()
        manager._update_heartbeat = AsyncMock()

        await manager.reload()

        manager._update_heartbeat.assert_awaited_once()
        manager._refresh_definition_version_locked.assert_awaited_once_with(
            jobs_file=None,
        )

        await manager.deactivate()


class TestCronManagerManualRun:
    """Tests for manual run_job outside scheduler ownership semantics."""

    async def test_run_job_bypasses_execution_lock(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test that manual run_job does not use scheduler preflight."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        await manager.activate()

        # Create a job
        job = CronJobSpec(
            id="test-job",
            name="Test Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="text",
            text="Test message",
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )
        await manager.create_or_replace_job(job)

        # Run job manually - should not require scheduler preflight
        # This just schedules the execution (fire-and-forget)
        await manager.run_job("test-job")

        # Wait a bit for the task to start
        await asyncio.sleep(0.1)

        await manager.deactivate()

    async def test_run_job_binds_cron_workload_for_background_task(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Manual run_job task execution runs under cron LLM workload."""
        observed = {}
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        await manager.activate()

        job = CronJobSpec(
            id="test-job",
            name="Test Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="text",
            text="Test message",
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )
        await manager.create_or_replace_job(job)

        async def fake_execute_once(executed_job):
            observed["job_id"] = executed_job.id
            observed["workload"] = get_current_llm_workload()

        manager._execute_once = fake_execute_once

        with bind_llm_workload(LLM_WORKLOAD_CHAT):
            await manager.run_job("test-job")
            await asyncio.sleep(0)
            assert get_current_llm_workload() == LLM_WORKLOAD_CHAT

        await manager.deactivate()

        assert observed == {
            "job_id": "test-job",
            "workload": LLM_WORKLOAD_CRON,
        }

    async def test_run_job_nonexistent_raises_keyerror(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test that run_job raises KeyError for nonexistent job."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        await manager.activate()

        with pytest.raises(KeyError):
            await manager.run_job("nonexistent-job")

        await manager.deactivate()


class TestCronManagerTimedPreflight:
    """Tests for scheduler-originated lease preflight behavior."""

    async def test_scheduled_callback_skips_when_lease_preflight_fails(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        sample_job_spec,
    ):
        """Timed callbacks should skip stale leaders before work starts."""
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()
        await manager.create_or_replace_job(sample_job_spec)

        manager._coordination = MagicMock()
        manager._coordination.is_leader = True
        manager._coordination.deactivate = AsyncMock()
        manager._coordination.preflight_scheduler_execution = AsyncMock(
            return_value=False,
        )
        manager._execute_once = AsyncMock()

        await manager._scheduled_callback(sample_job_spec.id)

        manager._coordination.preflight_scheduler_execution.assert_awaited_once_with(
            job_id=sample_job_spec.id,
            schedule_type="cron",
        )
        manager._execute_once.assert_not_awaited()
        assert manager.get_state(sample_job_spec.id).last_status == "skipped"

        await manager.deactivate()

    async def test_scheduled_callback_no_longer_uses_execution_lock_by_default(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        sample_job_spec,
    ):
        """Default timed execution should rely on lease preflight, not locks."""
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()
        await manager.create_or_replace_job(sample_job_spec)

        manager._coordination = MagicMock()
        manager._coordination.is_leader = True
        manager._coordination.deactivate = AsyncMock()
        manager._coordination.create_execution_lock = MagicMock(
            side_effect=AssertionError(
                "default timed path should not use execution lock",
            ),
        )
        manager._coordination.preflight_scheduler_execution = AsyncMock(
            return_value=True,
        )
        manager._execute_once = AsyncMock()

        await manager._scheduled_callback(sample_job_spec.id)

        manager._execute_once.assert_awaited_once()
        executed_job = manager._execute_once.await_args.args[0]
        assert executed_job.id == sample_job_spec.id
        assert executed_job.task_type == sample_job_spec.task_type
        manager._coordination.create_execution_lock.assert_not_called()

        await manager.deactivate()

    async def test_heartbeat_skips_when_lease_preflight_fails(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Heartbeat should use the same preflight gate as ordinary cron jobs."""
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()

        manager._coordination = MagicMock()
        manager._coordination.is_leader = True
        manager._coordination.deactivate = AsyncMock()
        manager._coordination.preflight_scheduler_execution = AsyncMock(
            return_value=False,
        )

        heartbeat_mock = AsyncMock()
        manager._run_heartbeat_once = heartbeat_mock
        await manager._heartbeat_callback()

        manager._coordination.preflight_scheduler_execution.assert_awaited_once_with(
            job_id=HEARTBEAT_JOB_ID,
            schedule_type="heartbeat",
        )
        heartbeat_mock.assert_not_awaited()
        assert manager.get_state(HEARTBEAT_JOB_ID).last_status == "skipped"

        await manager.deactivate()


class TestCronManagerState:
    """Tests for CronManager state tracking."""

    async def test_register_schedules_prefetch_for_agent_jobs(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()

        job = CronJobSpec(
            id="test-agent-job",
            name="Test Agent Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="agent",
            request=CronJobRequest(
                input=[{"content": [{"text": "ping"}]}],
            ),
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
                meta={"workspace_dir": "/tmp/test"},
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )

        await manager.create_or_replace_job(job)

        assert (
            manager._scheduler.get_job(manager._prefetch_job_id(job.id))
            is not None
        )

        await manager.deactivate()

    async def test_prefetch_callback_updates_state_and_reschedules(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()

        job = CronJobSpec(
            id="prefetch-job",
            name="Prefetch Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="agent",
            request=CronJobRequest(
                input=[{"content": [{"text": "ping"}]}],
            ),
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
                meta={"workspace_dir": "/tmp/test"},
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )
        await manager.create_or_replace_job(job)

        prefetch_job = manager._scheduler.get_job(
            manager._prefetch_job_id(job.id),
        )
        assert prefetch_job is not None
        original_next_run_at = manager.get_state(job.id).next_run_at
        assert original_next_run_at is not None

        with patch(
            "swe.app.crons.manager.prefetch_auth_token",
        ) as prefetch_mock:
            await manager._prefetch_callback(job.id)

        prefetch_mock.assert_called_once_with(
            tenant_id="test-tenant",
            workspace_dir="/tmp/test",
        )
        state = manager.get_state(job.id)
        assert state.last_prefetch_at is not None
        assert state.last_error is None
        rescheduled = manager._scheduler.get_job(
            manager._prefetch_job_id(job.id),
        )
        assert rescheduled is not None
        assert rescheduled.next_run_time <= original_next_run_at

        await manager.deactivate()

    async def test_pause_and_resume_manage_prefetch_job(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        await manager.activate()

        job = CronJobSpec(
            id="pause-resume-job",
            name="Pause Resume Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="agent",
            request=CronJobRequest(
                input=[{"content": [{"text": "ping"}]}],
            ),
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
                meta={"workspace_dir": "/tmp/test"},
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )
        await manager.create_or_replace_job(job)

        assert (
            manager._scheduler.get_job(manager._prefetch_job_id(job.id))
            is not None
        )

        await manager.pause_job(job.id)
        assert (
            manager._scheduler.get_job(manager._prefetch_job_id(job.id))
            is None
        )

        await manager.resume_job(job.id)
        assert (
            manager._scheduler.get_job(manager._prefetch_job_id(job.id))
            is not None
        )

        await manager.deactivate()

    async def test_prefetch_run_time_is_within_one_hour_window(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        next_run_at = datetime.now(timezone.utc) + timedelta(hours=3)
        spec = CronJobSpec(
            id="window-job",
            name="Window Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="agent",
            request=CronJobRequest(
                input=[{"content": [{"text": "ping"}]}],
            ),
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
            ),
            runtime=JobRuntimeSpec(timeout_seconds=30),
        )

        run_at = manager._compute_prefetch_run_at(spec, next_run_at)

        assert run_at is not None
        assert next_run_at - timedelta(hours=1) <= run_at <= next_run_at

    async def test_job_state_tracking(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test that job state is properly tracked."""
        config = CoordinationConfig(enabled=False)
        repo = JsonJobRepository(temp_jobs_file)
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        await manager.activate()

        # Create a job
        job = CronJobSpec(
            id="test-job",
            name="Test Job",
            enabled=True,
            tenant_id="test-tenant",
            schedule=ScheduleSpec(
                type="cron",
                cron="0 0 * * *",
                timezone="UTC",
            ),
            task_type="text",
            text="Test",
            dispatch=DispatchSpec(
                type="channel",
                channel="console",
                target=DispatchTarget(user_id="user1", session_id="session1"),
            ),
        )
        await manager.create_or_replace_job(job)

        # Get initial state
        state = manager.get_state("test-job")
        assert state.last_status is None
        assert state.last_run_at is None

        await manager.deactivate()


class TestCronDefinitionMutationCoordination:
    """Tests for serialized jobs.json mutation and reload convergence."""

    async def test_mutation_saves_jobs_file_before_advancing_definition_version(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        sample_job_spec,
    ):
        """Successful writes should only advance version after save succeeds."""
        repo = JsonJobRepository(temp_jobs_file)
        coord = _FakeCoordination()
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = coord

        events = coord.events
        original_save = repo.save

        async def recording_save(jobs_file):
            events.append("save")
            await original_save(jobs_file)

        repo.save = recording_save

        await manager.create_or_replace_job(sample_job_spec)

        assert events == [
            "acquire",
            "save",
            "sync:1",
            "release",
            "publish:1",
        ]
        assert manager._definition_version == 1

    async def test_mutation_does_not_publish_or_advance_local_version_if_save_fails(
        self,
        mock_runner,
        mock_channel_manager,
        sample_job_spec,
    ):
        """A failed save must not publish reload or mark local convergence."""
        repo = AsyncMock()
        repo.load = AsyncMock(return_value=JobsFile(version=1, jobs=[]))
        repo.save = AsyncMock(side_effect=RuntimeError("disk full"))
        coord = _FakeCoordination()
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = coord

        with pytest.raises(RuntimeError, match="disk full"):
            await manager.create_or_replace_job(sample_job_spec)

        assert coord.events == ["acquire", "release"]
        assert manager._definition_version == 0

    async def test_concurrent_create_operations_preserve_both_jobs(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        sample_job_spec,
    ):
        """Concurrent writes should serialize through definition lock."""
        repo1 = JsonJobRepository(temp_jobs_file)
        repo2 = JsonJobRepository(temp_jobs_file)
        coord = _FakeCoordination()

        manager1 = CronManager(
            repo=repo1,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager2 = CronManager(
            repo=repo2,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager1._coordination = coord
        manager2._coordination = coord

        original_save = repo1.save

        async def delayed_save(jobs_file):
            await asyncio.sleep(0.05)
            await original_save(jobs_file)

        repo1.save = delayed_save

        job1 = sample_job_spec.model_copy(
            update={"id": "job-1", "name": "job-1"},
        )
        job2 = sample_job_spec.model_copy(
            update={"id": "job-2", "name": "job-2"},
        )

        await asyncio.gather(
            manager1.create_or_replace_job(job1),
            manager2.create_or_replace_job(job2),
        )

        jobs = await repo1.list_jobs()
        assert {job.id for job in jobs} == {"job-1", "job-2"}
        assert coord.events == [
            "acquire",
            "sync:1",
            "release",
            "publish:1",
            "acquire",
            "sync:2",
            "release",
            "publish:2",
        ]

    async def test_reconcile_reloads_when_definition_version_advances(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Missed reload pub/sub should still converge via periodic reconcile."""
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = MagicMock()
        manager._coordination.get_definition_version = AsyncMock(
            return_value=3,
        )
        manager._coordination.ensure_definition_version = AsyncMock(
            return_value=3,
        )
        manager._coordination.is_leader = True
        manager._definition_version = 1
        manager._started = True
        manager.reload = AsyncMock()

        await manager._reconcile_definition_version_once()

        manager.reload.assert_awaited_once()

    async def test_reconcile_repairs_redis_version_from_jobs_file_before_reloading(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """A durable jobs.json change should still converge if Redis version lags."""
        temp_jobs_file.write_text(
            """
{
  "version": 1,
  "definition_version": 2,
  "jobs": []
}
""".strip(),
            encoding="utf-8",
        )
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = MagicMock()
        manager._coordination.get_definition_version = AsyncMock(
            return_value=1,
        )
        manager._coordination.ensure_definition_version = AsyncMock(
            return_value=2,
        )
        manager._coordination.is_leader = True
        manager._definition_version = 1
        manager._started = True
        manager.reload = AsyncMock()

        await manager._reconcile_definition_version_once()

        manager._coordination.ensure_definition_version.assert_awaited_once_with(
            2,
        )
        manager.reload.assert_awaited_once()

    async def test_delete_job_keeps_local_scheduler_state_when_persistence_fails(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """delete_job should not mutate in-memory state before persistence succeeds."""
        manager = CronManager(
            repo=JsonJobRepository(temp_jobs_file),
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._started = True
        manager._scheduler = MagicMock()
        manager._scheduler.get_job.return_value = object()
        manager._active_jobs.add("job-1")
        manager._states["job-1"] = CronJobState()
        manager._rt["job-1"] = object()
        manager._mutate_jobs_file_locked = AsyncMock(
            side_effect=RuntimeError("persist failed"),
        )

        with pytest.raises(RuntimeError, match="persist failed"):
            await manager.delete_job("job-1")

        manager._scheduler.remove_job.assert_not_called()
        assert "job-1" in manager._active_jobs
        assert "job-1" in manager._states
        assert "job-1" in manager._rt


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestCronManagerFailoverIntegration:
    """Integration test for automatic failover between managers."""

    async def test_follower_takes_over_after_leader_loses_lease(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
        coordination_config,
    ):
        """Test that follower automatically takes over when leader loses lease."""
        # Use shorter intervals for faster test
        config = CoordinationConfig(
            enabled=True,
            redis_url="redis://localhost:6379/15",
            lease_ttl_seconds=3,
            lease_renew_interval_seconds=1,
        )

        # Create two managers
        repo1 = JsonJobRepository(temp_jobs_file)
        repo2 = JsonJobRepository(temp_jobs_file)

        leader = CronManager(
            repo=repo1,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )
        follower = CronManager(
            repo=repo2,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=config,
        )

        try:
            # Leader activates and becomes leader
            is_leader = await leader.activate()
            if not is_leader:
                pytest.skip("Could not acquire leadership for test")

            assert leader.is_leader
            assert leader.is_started

            # Follower activates as follower
            is_follower_leader = await follower.activate()
            assert not is_follower_leader
            assert not follower.is_leader
            assert not follower.is_started

            # Create a job while leader
            job = CronJobSpec(
                id="test-job",
                name="Test Job",
                enabled=True,
                tenant_id="test-tenant",
                schedule=ScheduleSpec(
                    type="cron",
                    cron="0 0 * * *",
                    timezone="UTC",
                ),
                task_type="text",
                text="Test",
                dispatch=DispatchSpec(
                    type="channel",
                    channel="console",
                    target=DispatchTarget(
                        user_id="user1",
                        session_id="session1",
                    ),
                ),
            )
            await leader.create_or_replace_job(job)

            # Leader deactivates (simulates lease loss or shutdown)
            await leader.deactivate()

            # Wait for follower's candidate loop to detect and take over
            # Wait longer than lease TTL + candidate loop interval
            await asyncio.sleep(config.lease_ttl_seconds + 2)

            # Follower should now be leader
            assert follower.is_leader
            assert follower.is_started

        except RuntimeError as e:
            if (
                "Redis coordination is enabled but Redis is not available"
                in str(e)
            ):
                pytest.skip("Redis not available")
            raise
        finally:
            await leader.deactivate()
            await follower.deactivate()
            await leader.disconnect_coordination()
            await follower.disconnect_coordination()


class TestCronManagerLeaderStartupCallback:
    """Unit tests for manager callback/rollback behavior."""

    async def test_callback_startup_failure_no_task_exception(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test callback path uses manager cleanup and doesn't leak task error."""
        # Use a repo that will fail to load.
        failing_repo = AsyncMock()
        failing_repo.load = AsyncMock(
            side_effect=RuntimeError("Simulated repo load failure"),
        )

        manager = CronManager(
            repo=failing_repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()
        original_deactivate = manager.deactivate
        manager.deactivate = AsyncMock(wraps=original_deactivate)

        # Initialize scheduler.
        await manager.initialize()

        loop = asyncio.get_running_loop()
        created_tasks = []
        original_create_task = loop.create_task

        def _capture_task(coro):
            task = original_create_task(coro)
            created_tasks.append(task)
            return task

        with patch.object(loop, "create_task", side_effect=_capture_task):
            manager._on_become_leader()

        assert len(created_tasks) == 1
        await created_tasks[0]

        # Failure should be handled internally (no task exception leak),
        # and leadership cleanup should still run.
        assert created_tasks[0].exception() is None
        manager.deactivate.assert_awaited_once()
        manager._coordination.deactivate.assert_awaited_once()
        assert not manager.is_started

    async def test_callback_cleanup_failure_no_task_exception(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test callback path swallows cleanup failures too."""
        failing_repo = AsyncMock()
        failing_repo.load = AsyncMock(
            side_effect=RuntimeError("Simulated repo load failure"),
        )

        manager = CronManager(
            repo=failing_repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()
        manager.deactivate = AsyncMock(
            side_effect=RuntimeError("Simulated cleanup failure"),
        )

        await manager.initialize()

        loop = asyncio.get_running_loop()
        created_tasks = []
        original_create_task = loop.create_task

        def _capture_task(coro):
            task = original_create_task(coro)
            created_tasks.append(task)
            return task

        with patch.object(loop, "create_task", side_effect=_capture_task):
            manager._on_become_leader()

        assert len(created_tasks) == 1
        await created_tasks[0]
        assert created_tasks[0].exception() is None

    async def test_activate_leader_startup_failure_runs_cleanup_then_raises(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test activate() leader path wires startup failure through cleanup."""
        repo = AsyncMock()
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()
        manager._coordination.connect = AsyncMock(return_value=True)
        manager._coordination.activate = AsyncMock(return_value=True)
        manager._coordination.instance_id = "i-1"
        manager._do_start = AsyncMock(
            side_effect=RuntimeError("Simulated startup failure"),
        )
        manager._cleanup_failed_leader_startup = AsyncMock()

        with pytest.raises(RuntimeError, match="Simulated startup failure"):
            await manager.activate()

        manager._cleanup_failed_leader_startup.assert_awaited_once()

    async def test_callback_rolls_back_real_partial_scheduler_startup(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test startup failure cleanup rolls back real partial start window."""
        repo = AsyncMock()
        repo.load = AsyncMock(return_value=MagicMock(jobs=[]))
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()

        await manager.initialize()

        original_scheduler = manager._scheduler
        assert original_scheduler is not None
        with patch.object(
            original_scheduler,
            "shutdown",
            wraps=original_scheduler.shutdown,
        ) as shutdown_mock:
            manager._update_heartbeat = AsyncMock(
                side_effect=RuntimeError(
                    "Simulated failure after scheduler start",
                ),
            )

            await manager._become_leader_and_start()

        shutdown_mock.assert_called_once_with(wait=False)
        assert manager._scheduler is not original_scheduler
        assert manager._scheduler is not None
        assert manager._active_jobs == set()
        assert manager._started is False
        manager._coordination.deactivate.assert_awaited_once()

    async def test_callback_shutdown_failure_uses_disable_and_releases(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test rollback can safely disable and then release leadership."""
        repo = AsyncMock()
        repo.load = AsyncMock(return_value=MagicMock(jobs=[]))
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()

        await manager.initialize()

        original_scheduler = manager._scheduler
        assert original_scheduler is not None

        async def _raise_after_start():
            raise RuntimeError("Simulated failure after scheduler start")

        manager._update_heartbeat = AsyncMock(side_effect=_raise_after_start)

        with patch.object(
            original_scheduler,
            "shutdown",
            side_effect=RuntimeError("Simulated shutdown failure"),
        ):
            await manager._become_leader_and_start()

        assert manager._scheduler is original_scheduler
        assert manager._started is False
        manager._coordination.deactivate.assert_awaited_once()

    async def test_callback_keeps_leadership_if_shutdown_and_disable_fail(
        self,
        temp_jobs_file,
        mock_runner,
        mock_channel_manager,
    ):
        """Test degraded emergency path when scheduler cannot be safely stopped."""
        repo = AsyncMock()
        repo.load = AsyncMock(return_value=MagicMock(jobs=[]))
        manager = CronManager(
            repo=repo,
            runner=mock_runner,
            channel_manager=mock_channel_manager,
            agent_id="test-agent",
            tenant_id="test-tenant",
            coordination_config=CoordinationConfig(enabled=False),
        )
        manager._coordination = AsyncMock()

        await manager.initialize()

        original_scheduler = manager._scheduler
        assert original_scheduler is not None

        manager._update_heartbeat = AsyncMock(
            side_effect=RuntimeError(
                "Simulated failure after scheduler start",
            ),
        )

        with patch.object(
            original_scheduler,
            "shutdown",
            side_effect=RuntimeError("Simulated shutdown failure"),
        ):
            with patch.object(
                original_scheduler,
                "pause",
                side_effect=RuntimeError("Simulated pause failure"),
            ):
                with patch.object(
                    original_scheduler,
                    "remove_all_jobs",
                    side_effect=RuntimeError("Simulated remove failure"),
                ):
                    await manager._become_leader_and_start()

        assert manager._scheduler is original_scheduler
        assert manager._started is True
        manager._coordination.deactivate.assert_not_awaited()
