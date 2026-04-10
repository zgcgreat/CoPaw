# -*- coding: utf-8 -*-
"""Tenant-aware error push regression tests for CronManager."""
import asyncio
import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"


@pytest.fixture
def cron_context():
    original_modules = {
        name: sys.modules.get(name)
        for name in [
            "swe.app.crons.repo.base",
            "swe.app.crons.executor",
            "swe.app.crons.heartbeat",
            "swe.config",
            "swe.config.context",
            "swe.app.tenant_context",
            "swe.app.console_push_store",
            "swe.app.channels.schema",
            "swe.app.crons.models",
            "swe.app.crons.coordination",
            "swe.app.crons.manager_test",
        ]
    }

    repo_module = types.ModuleType("swe.app.crons.repo.base")
    repo_module.BaseJobRepository = object
    sys.modules["swe.app.crons.repo.base"] = repo_module

    executor_module = types.ModuleType("swe.app.crons.executor")
    executor_module.CronExecutor = lambda runner, channel_manager: object()
    sys.modules["swe.app.crons.executor"] = executor_module

    heartbeat_module = types.ModuleType("swe.app.crons.heartbeat")
    heartbeat_module.is_cron_expression = lambda every: False
    heartbeat_module.parse_heartbeat_cron = (
        lambda every: ("*", "*", "*", "*", "*")
    )
    heartbeat_module.parse_heartbeat_every = lambda every: 60

    async def _run_heartbeat_once(**kwargs):
        return None

    heartbeat_module.run_heartbeat_once = _run_heartbeat_once
    sys.modules["swe.app.crons.heartbeat"] = heartbeat_module

    config_module = types.ModuleType("swe.config")
    config_module.get_heartbeat_config = (
        lambda agent_id=None: types.SimpleNamespace(
            enabled=False,
            every="60s",
        )
    )
    sys.modules["swe.config"] = config_module

    tenant_context_module = types.ModuleType("swe.app.tenant_context")

    @contextmanager
    def _bind_tenant_context(*args, **kwargs):
        yield

    tenant_context_module.bind_tenant_context = _bind_tenant_context
    sys.modules["swe.app.tenant_context"] = tenant_context_module

    push_calls = []
    push_module = types.ModuleType("swe.app.console_push_store")

    async def _append(session_id, text, *, sticky=False, tenant_id=None):
        push_calls.append(
            {
                "session_id": session_id,
                "text": text,
                "sticky": sticky,
                "tenant_id": tenant_id,
            },
        )

    push_module.append = _append
    sys.modules["swe.app.console_push_store"] = push_module

    coordination_module = types.ModuleType("swe.app.crons.coordination")
    coordination_module.CoordinationConfig = object
    coordination_module.CronCoordination = object

    @contextmanager
    def _execution_lock_context(*args, **kwargs):
        yield True

    coordination_module.execution_lock_context = _execution_lock_context
    sys.modules["swe.app.crons.coordination"] = coordination_module

    channels_schema_module = types.ModuleType("swe.app.channels.schema")
    channels_schema_module.DEFAULT_CHANNEL = "console"
    sys.modules["swe.app.channels.schema"] = channels_schema_module

    models_spec = importlib.util.spec_from_file_location(
        "swe.app.crons.models",
        SRC_ROOT / "swe" / "app" / "crons" / "models.py",
    )
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules["swe.app.crons.models"] = models_module
    assert models_spec is not None and models_spec.loader is not None
    models_spec.loader.exec_module(models_module)

    manager_spec = importlib.util.spec_from_file_location(
        "swe.app.crons.manager_test",
        SRC_ROOT / "swe" / "app" / "crons" / "manager.py",
    )
    manager_module = importlib.util.module_from_spec(manager_spec)
    sys.modules["swe.app.crons.manager_test"] = manager_module
    assert manager_spec is not None and manager_spec.loader is not None
    manager_spec.loader.exec_module(manager_module)

    try:
        yield {
            "CronManager": manager_module.CronManager,
            "CronJobSpec": models_module.CronJobSpec,
            "ScheduleSpec": models_module.ScheduleSpec,
            "DispatchSpec": models_module.DispatchSpec,
            "DispatchTarget": models_module.DispatchTarget,
            "JobRuntimeSpec": models_module.JobRuntimeSpec,
            "CronJobRequest": models_module.CronJobRequest,
            "push_calls": push_calls,
        }
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class _Task:
    def cancelled(self):
        return False

    def exception(self):
        return RuntimeError("boom")

    def get_name(self):
        return "cron-run-job-1"


def test_task_done_cb_pushes_error_to_tenant_scoped_store(cron_context):
    manager = cron_context["CronManager"](
        repo=object(),
        runner=object(),
        channel_manager=object(),
    )
    job = cron_context["CronJobSpec"](
        id="job-1",
        name="tenant cron",
        tenant_id="tenant-a",
        schedule=cron_context["ScheduleSpec"](cron="* * * * *"),
        task_type="agent",
        request=cron_context["CronJobRequest"](
            input=[{"content": [{"type": "text", "text": "ping"}]}],
        ),
        dispatch=cron_context["DispatchSpec"](
            channel="console",
            target=cron_context["DispatchTarget"](
                user_id="user-a",
                session_id="session-a",
            ),
            meta={},
        ),
        runtime=cron_context["JobRuntimeSpec"](),
    )

    manager._task_done_cb(_Task(), job)
    asyncio.run(asyncio.sleep(0))

    assert cron_context["push_calls"] == [
        {
            "session_id": "session-a",
            "text": "❌ Cron job [tenant cron] failed: boom",
            "sticky": False,
            "tenant_id": "tenant-a",
        },
    ]
