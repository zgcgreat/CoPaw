# -*- coding: utf-8 -*-
"""Tenant injection regression tests for cron APIs."""
import importlib.util
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(SRC_ROOT))

if "swe.app.crons" not in sys.modules:
    pkg = types.ModuleType("swe.app.crons")
    pkg.__path__ = [str(SRC_ROOT / "swe" / "app" / "crons")]
    sys.modules["swe.app.crons"] = pkg

channels_schema_module = types.ModuleType("swe.app.channels.schema")
channels_schema_module.DEFAULT_CHANNEL = "console"
sys.modules["swe.app.channels.schema"] = channels_schema_module

models_spec = importlib.util.spec_from_file_location(
    "swe.app.crons.models",
    SRC_ROOT / "swe" / "app" / "crons" / "models.py",
)
assert models_spec is not None and models_spec.loader is not None
models_module = importlib.util.module_from_spec(models_spec)
sys.modules["swe.app.crons.models"] = models_module
models_spec.loader.exec_module(models_module)

manager_module = types.ModuleType("swe.app.crons.manager")
manager_module.CronManager = object
sys.modules["swe.app.crons.manager"] = manager_module

api_spec = importlib.util.spec_from_file_location(
    "swe.app.crons.api",
    SRC_ROOT / "swe" / "app" / "crons" / "api.py",
)
assert api_spec is not None and api_spec.loader is not None
api_module = importlib.util.module_from_spec(api_spec)
sys.modules["swe.app.crons.api"] = api_module
api_spec.loader.exec_module(api_module)


class _TenantStateMiddleware:
    def __init__(self, app, tenant_id: str):
        self.app = app
        self.tenant_id = tenant_id

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["tenant_id"] = self.tenant_id
        await self.app(scope, receive, send)


class _Manager:
    def __init__(self):
        self.created = []

    async def create_or_replace_job(self, spec):
        self.created.append(spec)

    async def list_jobs(self):
        return []

    async def get_job(self, job_id):
        return None

    def get_state(self, job_id):
        return types.SimpleNamespace(model_dump=lambda mode=None: {})


CronJobSpec = models_module.CronJobSpec
ScheduleSpec = models_module.ScheduleSpec
DispatchSpec = models_module.DispatchSpec
DispatchTarget = models_module.DispatchTarget
JobRuntimeSpec = models_module.JobRuntimeSpec
CronJobRequest = models_module.CronJobRequest


def _job_spec(job_id: str = ""):
    return {
        "id": job_id,
        "name": "tenant cron",
        "enabled": True,
        "tenant_id": None,
        "schedule": ScheduleSpec(cron="* * * * *").model_dump(mode="json"),
        "task_type": "agent",
        "request": CronJobRequest(
            input=[{"content": [{"type": "text", "text": "ping"}]}],
        ).model_dump(mode="json"),
        "dispatch": DispatchSpec(
            channel="console",
            target=DispatchTarget(user_id="user-a", session_id="session-a"),
            meta={},
        ).model_dump(mode="json"),
        "runtime": JobRuntimeSpec().model_dump(mode="json"),
        "meta": {},
    }


def _build_client(manager: _Manager) -> TestClient:
    app = FastAPI()
    app.add_middleware(_TenantStateMiddleware, tenant_id="tenant-a")
    app.include_router(api_module.router)

    async def _get_mgr():
        return manager

    app.dependency_overrides[api_module.get_cron_manager] = _get_mgr
    return TestClient(app)


def test_create_job_injects_request_tenant_id():
    manager = _Manager()
    client = _build_client(manager)

    response = client.post("/cron/jobs", json=_job_spec())

    assert response.status_code == 200
    assert manager.created[0].tenant_id == "tenant-a"


def test_replace_job_overrides_payload_tenant_with_request_tenant():
    manager = _Manager()
    client = _build_client(manager)

    response = client.put(
        "/cron/jobs/job-1",
        json={**_job_spec("job-1"), "tenant_id": "other-tenant"},
    )

    assert response.status_code == 200
    assert manager.created[0].tenant_id == "tenant-a"
