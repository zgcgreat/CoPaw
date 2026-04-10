# -*- coding: utf-8 -*-
"""Regression tests for workspace runner registration."""

import subprocess
import sys


def test_tenant_initializer_import_does_not_load_workspace_runtime():
    """Importing tenant_initializer should not eagerly load workspace.py."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib, sys; "
                "importlib.import_module('swe.app.workspace.tenant_initializer'); "
                "raise SystemExit("
                "0 if 'swe.app.workspace.workspace' not in sys.modules else 1"
                ")"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_runner_lazy_export_resolves_class():
    """AgentRunner package export should resolve to the concrete class."""
    from swe.app.runner import AgentRunner

    assert AgentRunner is not None
    assert AgentRunner.__name__ == "AgentRunner"


def test_workspace_registers_concrete_runner_service(tmp_path):
    """Workspace should register a concrete runner service class."""
    from swe.app.workspace import Workspace

    workspace = Workspace(
        agent_id="test123",
        workspace_dir=str(tmp_path / "test_agent"),
    )

    descriptor = workspace._service_manager.descriptors["runner"]  # pylint: disable=protected-access

    assert descriptor.service_class is not None


def test_workspace_uses_namespaced_task_tracker(tmp_path):
    """Workspace should namespace shared run coordination by tenant/agent."""
    from swe.app.workspace import Workspace

    workspace = Workspace(
        agent_id="agent-a",
        workspace_dir=str(tmp_path / "agent-a"),
        tenant_id="tenant-a",
    )

    assert workspace.task_tracker._coordinator.namespace == "tenant-a:agent-a"  # pylint: disable=protected-access


def test_workspace_stop_closes_task_tracker(tmp_path):
    """Workspace stop should close the shared task tracker coordinator."""
    from swe.app.workspace import Workspace

    workspace = Workspace(
        agent_id="agent-a",
        workspace_dir=str(tmp_path / "agent-a"),
        tenant_id="tenant-a",
    )

    calls = []

    async def _fake_stop_all(*, final):
        calls.append(("stop_all", final))

    async def _fake_aclose():
        calls.append(("aclose", None))

    workspace._started = True  # pylint: disable=protected-access
    workspace._service_manager.stop_all = _fake_stop_all  # pylint: disable=protected-access
    workspace.task_tracker.aclose = _fake_aclose

    import asyncio

    asyncio.run(workspace.stop())

    assert calls == [
        ("stop_all", True),
        ("aclose", None),
    ]
