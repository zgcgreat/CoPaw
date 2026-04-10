# -*- coding: utf-8 -*-
"""MySQL support utilities for durable cron storage."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse

import pymysql

from ....constant import EnvVarLoader


@dataclass(frozen=True)
class CronStorageScope:
    tenant_id: str
    agent_id: str


@dataclass(frozen=True)
class CronMySQLSettings:
    host: str
    port: int
    user: str
    password: str
    database: str

    @classmethod
    def from_env(cls) -> "CronMySQLSettings":
        dsn = EnvVarLoader.get_str("SWE_CRON_MYSQL_DSN", "").strip()
        if not dsn:
            raise RuntimeError("SWE_CRON_MYSQL_DSN is required for cron storage")

        parsed = urlparse(dsn)
        return cls(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            database=(parsed.path or "/").lstrip("/"),
        )


class MySQLCronStore:
    """Thin async wrapper around synchronous PyMySQL connections."""

    def __init__(self, settings: CronMySQLSettings):
        self._settings = settings

    def _connect(self):
        return pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            user=self._settings.user,
            password=self._settings.password,
            database=self._settings.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _run_sync(self, fn):
        with self._connect() as conn:
            result = fn(conn)
            conn.commit()
            return result

    async def run(self, fn):
        return await asyncio.to_thread(self._run_sync, fn)

    async def ensure_schema(self) -> None:
        def _create(conn):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cron_job_definitions (
                        tenant_id VARCHAR(191) NOT NULL,
                        agent_id VARCHAR(191) NOT NULL,
                        job_id VARCHAR(191) NOT NULL,
                        definition_json LONGTEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (tenant_id, agent_id, job_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cron_heartbeat_definitions (
                        tenant_id VARCHAR(191) NOT NULL,
                        agent_id VARCHAR(191) NOT NULL,
                        definition_json LONGTEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (tenant_id, agent_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

        await self.run(_create)
