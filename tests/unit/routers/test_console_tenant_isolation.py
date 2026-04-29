# -*- coding: utf-8 -*-
"""Tenant isolation tests for console push message API."""
import importlib.util
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
_CONSOLE_FILE = SRC_ROOT / "swe" / "app" / "routers" / "console.py"


console_push_store = types.ModuleType("swe.app.console_push_store")


async def _noop_get_recent(*args, **kwargs):
    return []


async def _noop_take(*args, **kwargs):
    return []


console_push_store.get_recent = _noop_get_recent
console_push_store.take = _noop_take
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
sys.modules["agentscope_runtime.engine.schemas.agent_schemas"] = agent_schemas

spec = importlib.util.spec_from_file_location(
    "swe.app.routers.console",
    _CONSOLE_FILE,
)
assert spec is not None and spec.loader is not None
console_router = importlib.util.module_from_spec(spec)
sys.modules["swe.app.routers.console"] = console_router
spec.loader.exec_module(console_router)


app = FastAPI()


@app.middleware("http")
async def add_tenant_state(request, call_next):
    request.state.tenant_id = request.headers.get("X-Tenant-Id")
    return await call_next(request)


app.include_router(console_router.router, prefix="/api")
client = TestClient(app)


def test_push_messages_api_requires_session_id():
    response = client.get(
        "/api/console/push-messages",
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "session_id is required"
