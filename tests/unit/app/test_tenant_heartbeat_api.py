from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.config.config import HeartbeatConfig


class _WorkspaceMiddleware:
    def __init__(self, app, workspace):
        self.app = app
        self.workspace = workspace

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["workspace"] = self.workspace
            scope["state"]["tenant_id"] = "tenant-a"
        await self.app(scope, receive, send)


class _CronManager:
    def __init__(self):
        self.config = HeartbeatConfig(
            enabled=True,
            every="30m",
            target="main",
        )
        self.saved = []

    async def get_heartbeat_config(self):
        return self.config

    async def update_heartbeat_config(self, config):
        self.config = config
        self.saved.append(config)
        return config


def _build_client():
    channels_schema = types.ModuleType("swe.app.channels.schema")
    channels_schema.ChannelType = str
    channels_schema.DEFAULT_CHANNEL = "console"
    sys.modules["swe.app.channels.schema"] = channels_schema

    from swe.app.routers.config import router

    workspace = SimpleNamespace(
        cron_manager=_CronManager(),
        config=SimpleNamespace(
            heartbeat=HeartbeatConfig(
                enabled=False,
                every="6h",
                target="main",
            ),
        ),
    )
    app = FastAPI()
    app.add_middleware(_WorkspaceMiddleware, workspace=workspace)
    app.include_router(router)
    return TestClient(app), workspace


def test_get_heartbeat_reads_durable_config_from_cron_manager():
    client, _workspace = _build_client()

    response = client.get("/config/heartbeat")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "every": "30m",
        "target": "main",
        "activeHours": None,
    }


def test_put_heartbeat_updates_durable_repo_not_agent_json():
    client, workspace = _build_client()

    response = client.put(
        "/config/heartbeat",
        json={
            "enabled": True,
            "every": "15m",
            "target": "last",
            "activeHours": {"start": "09:00", "end": "18:00"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "every": "15m",
        "target": "last",
        "activeHours": {"start": "09:00", "end": "18:00"},
    }
    assert workspace.cron_manager.saved == [
        HeartbeatConfig(
            enabled=True,
            every="15m",
            target="last",
            activeHours={"start": "09:00", "end": "18:00"},
        ),
    ]
    assert workspace.config.heartbeat == HeartbeatConfig(
        enabled=False,
        every="6h",
        target="main",
    )
