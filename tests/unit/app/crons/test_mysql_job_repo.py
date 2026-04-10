from __future__ import annotations

from typing import Any

import pytest

from swe.app.crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
    JobRuntimeSpec,
    ScheduleSpec,
)
from swe.app.crons.repo.mysql_support import CronStorageScope
from swe.config.config import HeartbeatConfig


def _job(job_id: str, *, tenant_id: str = "tenant-a") -> CronJobSpec:
    return CronJobSpec(
        id=job_id,
        name=f"job-{job_id}",
        enabled=True,
        tenant_id=tenant_id,
        schedule=ScheduleSpec(cron="*/5 * * * *"),
        task_type="agent",
        request=CronJobRequest(
            input=[{"role": "user", "content": [{"type": "text", "text": "run"}]}],
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


class _FakeCursor:
    def __init__(self, state: dict[str, Any]):
        self._state = state
        self._rows: list[dict[str, str]] = []
        self._row: dict[str, str] | None = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> int:
        sql = " ".join(query.split()).lower()
        params = params or ()
        jobs = self._state["jobs"]
        heartbeats = self._state["heartbeats"]
        self._rows = []
        self._row = None
        self.rowcount = 0

        if (
            "select definition_json from cron_job_definitions" in sql
            and "job_id=%s" in sql
        ):
            key = (params[0], params[1], params[2])
            payload = jobs.get(key)
            self._row = {"definition_json": payload} if payload else None
            self.rowcount = 1 if payload else 0
            return self.rowcount

        if "select definition_json from cron_job_definitions" in sql:
            tenant_id, agent_id = params
            rows = []
            for key, payload in jobs.items():
                if key[:2] == (tenant_id, agent_id):
                    rows.append({"job_id": key[2], "definition_json": payload})
            rows.sort(key=lambda row: row["job_id"])
            self._rows = [
                {"definition_json": row["definition_json"]}
                for row in rows
            ]
            self.rowcount = len(self._rows)
            return self.rowcount

        if "insert into cron_job_definitions" in sql:
            key = (params[0], params[1], params[2])
            jobs[key] = params[3]
            self.rowcount = 1
            return 1

        if (
            "delete from cron_job_definitions" in sql
            and "job_id=%s" in sql
        ):
            key = (params[0], params[1], params[2])
            existed = key in jobs
            jobs.pop(key, None)
            self.rowcount = 1 if existed else 0
            return self.rowcount

        if "delete from cron_job_definitions" in sql:
            tenant_id, agent_id = params
            keys = [
                key
                for key in jobs
                if key[:2] == (tenant_id, agent_id)
            ]
            for key in keys:
                del jobs[key]
            self.rowcount = len(keys)
            return self.rowcount

        if "select definition_json from cron_heartbeat_definitions" in sql:
            key = (params[0], params[1])
            payload = heartbeats.get(key)
            self._row = {"definition_json": payload} if payload else None
            self.rowcount = 1 if payload else 0
            return self.rowcount

        if "select 1 from cron_heartbeat_definitions" in sql:
            key = (params[0], params[1])
            exists = key in heartbeats
            self._row = {"exists": 1} if exists else None
            self.rowcount = 1 if exists else 0
            return self.rowcount

        if "insert into cron_heartbeat_definitions" in sql:
            heartbeats[(params[0], params[1])] = params[2]
            self.rowcount = 1
            return 1

        raise AssertionError(f"Unsupported SQL in test double: {query}")

    def fetchall(self) -> list[dict[str, str]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, str] | None:
        return self._row


class _FakeConnection:
    def __init__(self, state: dict[str, Any]):
        self._state = state

    def cursor(self):
        return _FakeCursor(self._state)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStore:
    def __init__(self):
        self.state = {"jobs": {}, "heartbeats": {}}

    async def run(self, fn):
        return fn(_FakeConnection(self.state))


@pytest.mark.asyncio
async def test_mysql_job_repo_is_scoped_and_cross_instance_consistent():
    from swe.app.crons.repo.mysql_job_repo import MysqlJobRepository

    store = _FakeStore()
    repo_a1 = MysqlJobRepository(
        store,
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-1"),
    )
    repo_a1_peer = MysqlJobRepository(
        store,
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-1"),
    )
    repo_a2 = MysqlJobRepository(
        store,
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-2"),
    )

    await repo_a1.upsert_job(_job("job-1"))
    await repo_a1_peer.upsert_job(_job("job-2"))
    await repo_a2.upsert_job(_job("job-3"))

    assert [job.id for job in await repo_a1.list_jobs()] == [
        "job-1",
        "job-2",
    ]
    assert (await repo_a1_peer.get_job("job-2")).id == "job-2"
    assert [job.id for job in await repo_a2.list_jobs()] == ["job-3"]


@pytest.mark.asyncio
async def test_mysql_job_repo_save_replaces_only_current_scope():
    from swe.app.crons.models import JobsFile
    from swe.app.crons.repo.mysql_job_repo import MysqlJobRepository

    store = _FakeStore()
    repo_a1 = MysqlJobRepository(
        store,
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-1"),
    )
    repo_b1 = MysqlJobRepository(
        store,
        CronStorageScope(tenant_id="tenant-b", agent_id="agent-1"),
    )

    await repo_a1.upsert_job(_job("stale"))
    await repo_b1.upsert_job(_job("other", tenant_id="tenant-b"))

    await repo_a1.save(
        JobsFile.model_validate(
            {"jobs": [_job("fresh").model_dump(mode="json")]},
        ),
    )

    assert [job.id for job in await repo_a1.list_jobs()] == ["fresh"]
    assert [job.id for job in await repo_b1.list_jobs()] == ["other"]


@pytest.mark.asyncio
async def test_mysql_job_repo_delete_returns_false_for_missing_rows():
    from swe.app.crons.repo.mysql_job_repo import MysqlJobRepository

    repo = MysqlJobRepository(
        _FakeStore(),
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-1"),
    )

    assert await repo.delete_job("missing") is False


@pytest.mark.asyncio
async def test_mysql_heartbeat_repo_round_trips_default_and_saved_config():
    from swe.app.crons.repo.mysql_heartbeat_repo import MysqlHeartbeatRepository

    repo = MysqlHeartbeatRepository(
        _FakeStore(),
        CronStorageScope(tenant_id="tenant-a", agent_id="agent-1"),
    )

    assert await repo.has_definition() is False
    assert await repo.get() == HeartbeatConfig()

    saved = await repo.set(
        HeartbeatConfig(enabled=True, every="15m", target="last"),
    )

    assert saved == HeartbeatConfig(
        enabled=True,
        every="15m",
        target="last",
    )
    assert await repo.has_definition() is True
    assert await repo.get() == saved
