from __future__ import annotations

import pytest

from swe.app.crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
    JobRuntimeSpec,
    ScheduleSpec,
)
from swe.config.config import HeartbeatConfig


def test_mysql_settings_parse_dsn(monkeypatch):
    monkeypatch.setenv(
        "SWE_CRON_MYSQL_DSN",
        "mysql://cron_user:cron_pass@127.0.0.1:3306/swe_cron",
    )

    from swe.app.crons.repo.mysql_support import CronMySQLSettings

    settings = CronMySQLSettings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.port == 3306
    assert settings.user == "cron_user"
    assert settings.password == "cron_pass"
    assert settings.database == "swe_cron"


def test_mysql_settings_require_dsn(monkeypatch):
    monkeypatch.delenv("SWE_CRON_MYSQL_DSN", raising=False)

    from swe.app.crons.repo.mysql_support import CronMySQLSettings

    with pytest.raises(RuntimeError, match="SWE_CRON_MYSQL_DSN"):
        CronMySQLSettings.from_env()


def _job(job_id: str, *, name: str = "cron job") -> CronJobSpec:
    return CronJobSpec(
        id=job_id,
        name=name,
        enabled=True,
        tenant_id="tenant-a",
        schedule=ScheduleSpec(cron="*/5 * * * *"),
        task_type="agent",
        request=CronJobRequest(
            input=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        ),
        dispatch=DispatchSpec(
            channel="console",
            target=DispatchTarget(
                user_id="user-a",
                session_id="session-a",
            ),
        ),
        runtime=JobRuntimeSpec(),
    )


class _InMemoryJobRepo:
    def __init__(self, jobs: list[CronJobSpec] | None = None):
        self.jobs = list(jobs or [])

    async def list_jobs(self) -> list[CronJobSpec]:
        return [job.model_copy(deep=True) for job in self.jobs]

    async def upsert_job(self, spec: CronJobSpec) -> None:
        for index, existing in enumerate(self.jobs):
            if existing.id == spec.id:
                self.jobs[index] = spec
                return
        self.jobs.append(spec)


class _InMemoryHeartbeatRepo:
    def __init__(self, config: HeartbeatConfig | None = None):
        self.config = config.model_copy(deep=True) if config else None

    async def has_definition(self) -> bool:
        return self.config is not None

    async def get(self) -> HeartbeatConfig:
        return (
            self.config.model_copy(deep=True)
            if self.config is not None
            else HeartbeatConfig()
        )

    async def set(self, config: HeartbeatConfig) -> HeartbeatConfig:
        self.config = config.model_copy(deep=True)
        return self.config.model_copy(deep=True)


@pytest.mark.asyncio
async def test_importer_backfills_legacy_jobs_and_heartbeat_when_primary_empty():
    from swe.app.crons.repo.importer import CronStorageImporter

    primary_repo = _InMemoryJobRepo()
    legacy_repo = _InMemoryJobRepo([_job("job-1"), _job("job-2")])
    heartbeat_repo = _InMemoryHeartbeatRepo()
    importer = CronStorageImporter(
        primary_repo=primary_repo,
        heartbeat_repo=heartbeat_repo,
        legacy_repo=legacy_repo,
    )

    imported = await importer.import_if_needed(
        legacy_heartbeat=HeartbeatConfig(
            enabled=True,
            every="15m",
            target="last",
        ),
    )

    assert imported.jobs_imported == 2
    assert imported.heartbeat_imported is True
    assert [job.id for job in await primary_repo.list_jobs()] == [
        "job-1",
        "job-2",
    ]
    assert await heartbeat_repo.get() == HeartbeatConfig(
        enabled=True,
        every="15m",
        target="last",
    )


@pytest.mark.asyncio
async def test_importer_backfills_missing_legacy_jobs_when_primary_non_empty():
    from swe.app.crons.repo.importer import CronStorageImporter

    primary_repo = _InMemoryJobRepo([_job("current")])
    legacy_repo = _InMemoryJobRepo([_job("current"), _job("legacy")])
    heartbeat_repo = _InMemoryHeartbeatRepo(
        HeartbeatConfig(enabled=True, every="30m", target="main"),
    )
    importer = CronStorageImporter(
        primary_repo=primary_repo,
        heartbeat_repo=heartbeat_repo,
        legacy_repo=legacy_repo,
    )

    imported = await importer.import_if_needed(
        legacy_heartbeat=HeartbeatConfig(
            enabled=True,
            every="5m",
            target="last",
        ),
    )

    assert imported.jobs_imported == 1
    assert imported.heartbeat_imported is False
    assert [job.id for job in await primary_repo.list_jobs()] == [
        "current",
        "legacy",
    ]
    assert await heartbeat_repo.get() == HeartbeatConfig(
        enabled=True,
        every="30m",
        target="main",
    )
