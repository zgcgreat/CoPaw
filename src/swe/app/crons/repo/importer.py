# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from ....config.config import HeartbeatConfig


@dataclass(frozen=True)
class CronImportResult:
    jobs_imported: int
    heartbeat_imported: bool


class CronStorageImporter:
    """One-time importer from legacy workspace files into MySQL storage."""

    def __init__(self, *, primary_repo, heartbeat_repo, legacy_repo):
        self._primary_repo = primary_repo
        self._heartbeat_repo = heartbeat_repo
        self._legacy_repo = legacy_repo

    async def import_if_needed(
        self,
        *,
        legacy_heartbeat: HeartbeatConfig | None = None,
    ) -> CronImportResult:
        jobs_imported = 0

        if not await self._primary_repo.list_jobs():
            for job in await self._legacy_repo.list_jobs():
                await self._primary_repo.upsert_job(job)
                jobs_imported += 1

        heartbeat_imported = False
        if (
            legacy_heartbeat is not None
            and not await self._heartbeat_repo.has_definition()
        ):
            await self._heartbeat_repo.set(legacy_heartbeat)
            heartbeat_imported = True

        return CronImportResult(
            jobs_imported=jobs_imported,
            heartbeat_imported=heartbeat_imported,
        )
