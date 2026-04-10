# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from ....config.config import HeartbeatConfig
from .mysql_support import CronStorageScope, MySQLCronStore


class MysqlHeartbeatRepository:
    """Tenant-and-agent scoped MySQL-backed heartbeat config repository."""

    def __init__(
        self,
        store: MySQLCronStore,
        scope: CronStorageScope,
    ):
        self._store = store
        self._scope = scope

    async def has_definition(self) -> bool:
        def _exists(conn) -> bool:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM cron_heartbeat_definitions
                    WHERE tenant_id=%s AND agent_id=%s
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                    ),
                )
                return cur.fetchone() is not None

        return await self._store.run(_exists)

    async def get(self) -> HeartbeatConfig:
        def _get(conn) -> HeartbeatConfig:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT definition_json
                    FROM cron_heartbeat_definitions
                    WHERE tenant_id=%s AND agent_id=%s
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    return HeartbeatConfig()
                return HeartbeatConfig.model_validate(
                    json.loads(row["definition_json"]),
                )

        return await self._store.run(_get)

    async def set(self, config: HeartbeatConfig) -> HeartbeatConfig:
        payload = json.dumps(
            config.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
        )

        def _set(conn) -> HeartbeatConfig:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cron_heartbeat_definitions (
                        tenant_id,
                        agent_id,
                        definition_json
                    ) VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        definition_json=VALUES(definition_json)
                    """,
                    (
                        self._scope.tenant_id,
                        self._scope.agent_id,
                        payload,
                    ),
                )
            return config

        return await self._store.run(_set)
