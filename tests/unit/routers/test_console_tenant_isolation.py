# -*- coding: utf-8 -*-
"""Tenant isolation tests for console push message API."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
_CONSOLE_FILE = SRC_ROOT / "swe" / "app" / "routers" / "console.py"


@pytest.fixture
def client_and_calls():
    original_modules = {
        name: sys.modules.get(name)
        for name in [
            "swe.app.console_push_store",
            "swe.app.agent_context",
            "agentscope_runtime",
            "agentscope_runtime.engine",
            "agentscope_runtime.engine.schemas",
            "agentscope_runtime.engine.schemas.agent_schemas",
            "swe.app.routers.console_test",
        ]
    }
    take_calls = []

    console_push_store = types.ModuleType("swe.app.console_push_store")

    async def _noop_get_recent(*args, **kwargs):
        return []

    async def _take(session_id, tenant_id=None):
        take_calls.append(
            {
                "session_id": session_id,
                "tenant_id": tenant_id,
            },
        )
        return [
            {
                "id": "msg-1",
                "text": f"{tenant_id}:{session_id}",
                "sticky": False,
            },
        ]

    console_push_store.get_recent = _noop_get_recent
    console_push_store.take = _take
    sys.modules["swe.app.console_push_store"] = console_push_store

    agent_context = types.ModuleType("swe.app.agent_context")
    agent_context.get_agent_for_request = lambda request: None
    sys.modules["swe.app.agent_context"] = agent_context

    agentscope_runtime = types.ModuleType("agentscope_runtime")
    engine = types.ModuleType("agentscope_runtime.engine")
    schemas = types.ModuleType("agentscope_runtime.engine.schemas")
    agent_schemas = types.ModuleType(
        "agentscope_runtime.engine.schemas.agent_schemas",
    )
    agent_schemas.AgentRequest = dict
    sys.modules["agentscope_runtime"] = agentscope_runtime
    sys.modules["agentscope_runtime.engine"] = engine
    sys.modules["agentscope_runtime.engine.schemas"] = schemas
    sys.modules[
        "agentscope_runtime.engine.schemas.agent_schemas"
    ] = agent_schemas

    spec = importlib.util.spec_from_file_location(
        "swe.app.routers.console_test",
        _CONSOLE_FILE,
    )
    console_router = importlib.util.module_from_spec(spec)
    sys.modules["swe.app.routers.console_test"] = console_router
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(console_router)

    app = FastAPI()

    @app.middleware("http")
    async def add_tenant_state(request, call_next):
        request.state.tenant_id = request.headers.get("X-Tenant-Id")
        return await call_next(request)

    app.include_router(console_router.router, prefix="/api")

    try:
        yield TestClient(app), take_calls
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_push_messages_api_requires_session_id(client_and_calls):
    client, _take_calls = client_and_calls

    response = client.get(
        "/api/console/push-messages",
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "session_id is required"


def test_push_messages_api_reads_only_requested_tenant_session(
    client_and_calls,
):
    client, take_calls = client_and_calls
    take_calls.clear()

    response = client.get(
        "/api/console/push-messages",
        params={"session_id": "session-a"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "messages": [
            {
                "id": "msg-1",
                "text": "tenant-a:session-a",
                "sticky": False,
            },
        ],
    }
    assert take_calls == [
        {
            "session_id": "session-a",
            "tenant_id": "tenant-a",
        },
    ]
