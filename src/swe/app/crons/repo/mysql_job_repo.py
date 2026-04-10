# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from .base import BaseJobRepository
from .mysql_support import CronStorageScope, MySQLCronStore
from ..models import CronJobSpec, JobsFile


class MysqlJobRepository(BaseJobRepository):
    """Tenant-and-agent scoped MySQL-backed cron job repository."""

    def __init__(
        self,
        store: MySQLCronStore,
        scope: CronStorageScope,
    ):
        self._store = store
        self._scope = scope

    async def load(self) -> JobsFile:
        return JobsFile(version=1, jobs=await self.list_jobs())

    async def save(self, jobs_file: JobsFile) -> None:
        payloads = [
            (
                self._scope.tenant_id,
                self._scope.agent_id,
                job.id,
                json.dumps(
                    job.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            for job in jobs_file.jobs
        ]

        def _save(conn) -> None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM cron_job_definitions
                    WHERE tenant_id=%s AND agent_id=%s
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                    ),
                )
                for row in payloads:
                    cur.execute(
                        """
                        INSERT INTO cron_job_definitions (
                            tenant_id,
                            agent_id,
                            job_id,
                            definition_json
                        ) VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            definition_json=VALUES(definition_json)
                        """,
                        row,
                    )

        await self._store.run(_save)

    async def list_jobs(self) -> list[CronJobSpec]:
        def _list(conn) -> list[CronJobSpec]:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT definition_json
                    FROM cron_job_definitions
                    WHERE tenant_id=%s AND agent_id=%s
                    ORDER BY job_id
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                    ),
                )
                return [
                    CronJobSpec.model_validate_json(row["definition_json"])
                    for row in cur.fetchall()
                ]

        return await self._store.run(_list)

    async def get_job(self, job_id: str) -> CronJobSpec | None:
        def _get(conn) -> CronJobSpec | None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT definition_json
                    FROM cron_job_definitions
                    WHERE tenant_id=%s AND agent_id=%s AND job_id=%s
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                        job_id,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return CronJobSpec.model_validate_json(row["definition_json"])

        return await self._store.run(_get)

    async def upsert_job(self, spec: CronJobSpec) -> None:
        payload = json.dumps(
            spec.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )

        def _upsert(conn) -> None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cron_job_definitions (
                        tenant_id,
                        agent_id,
                        job_id,
                        definition_json
                    ) VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        definition_json=VALUES(definition_json)
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                        spec.id,
                        payload,
                    ),
                )

        await self._store.run(_upsert)

    async def delete_job(self, job_id: str) -> bool:
        def _delete(conn) -> bool:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM cron_job_definitions
                    WHERE tenant_id=%s AND agent_id=%s AND job_id=%s
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                        job_id,
                    ),
                )
                return cur.rowcount > 0

        return await self._store.run(_delete)
