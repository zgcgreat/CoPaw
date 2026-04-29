# -*- coding: utf-8 -*-
"""Tests for tenant-aware MCP stdio process-limit enforcement."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from swe.config.config import Config, MCPClientConfig
from swe.config.context import tenant_context
from swe.config.utils import save_config

_REACT_AGENT_TOOL_EXPORTS = (
    "browser_use",
    "desktop_screenshot",
    "edit_file",
    "execute_shell_command",
    "get_current_time",
    "get_token_usage",
    "glob_search",
    "grep_search",
    "read_file",
    "send_file_to_user",
    "set_user_timezone",
    "view_image",
    "view_video",
    "write_file",
    "create_memory_search_tool",
)


def _write_process_limit_config(
    base_dir: Path,
    tenant_id: str,
    *,
    enabled: bool,
    mcp_stdio: bool = True,
    cpu_time_limit_seconds: int | None = None,
    memory_max_mb: int | None = None,
) -> None:
    tenant_dir = base_dir / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    save_config(
        Config.model_validate(
            {
                "security": {
                    "process_limits": {
                        "enabled": enabled,
                        "shell": True,
                        "mcp_stdio": mcp_stdio,
                        "cpu_time_limit_seconds": cpu_time_limit_seconds,
                        "memory_max_mb": memory_max_mb,
                    },
                },
            },
        ),
        tenant_dir / "config.json",
    )


@pytest.fixture
def tenant_config_root(tmp_path: Path):
    with patch("swe.constant.WORKING_DIR", tmp_path), patch(
        "swe.config.utils.WORKING_DIR",
        tmp_path,
    ):
        yield tmp_path


@contextmanager
def _stub_react_agent_tool_exports():
    import swe.agents.tools as agent_tools

    with ExitStack() as stack:
        for export_name in _REACT_AGENT_TOOL_EXPORTS:
            stack.enter_context(
                patch.object(agent_tools, export_name, object(), create=True),
            )
        yield


def test_stdio_launcher_main_applies_limits_before_exec() -> None:
    from swe.app.mcp.stdio_launcher import main

    with patch(
        "swe.app.mcp.stdio_launcher.resource.setrlimit",
    ) as mock_setrlimit, patch(
        "swe.app.mcp.stdio_launcher.os.execvpe",
    ) as mock_execvpe:
        main(
            [
                "--cpu-time-limit-seconds",
                "2",
                "--memory-max-bytes",
                str(64 * 1024 * 1024),
                "--",
                "node",
                "server.js",
            ],
        )

    mock_execvpe.assert_called_once()
    assert mock_execvpe.call_args.args[0] == "node"
    assert mock_execvpe.call_args.args[1] == ["node", "server.js"]
    assert mock_setrlimit.call_count == 2


@pytest.mark.asyncio
async def test_runner_wraps_stdio_client_launch_with_tenant_launcher(
    tenant_config_root: Path,
) -> None:
    with _stub_react_agent_tool_exports():
        from swe.app.runner.runner import _create_mcp_client_with_headers

        _write_process_limit_config(
            tenant_config_root,
            "tenant-a",
            enabled=True,
            cpu_time_limit_seconds=2,
            memory_max_mb=128,
        )

        captured = {}

        class _FakeStdIOClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        client_config = MCPClientConfig(
            name="demo",
            transport="stdio",
            command="node",
            args=["server.js"],
            env={"DEMO": "1"},
            cwd="/tmp/demo",
        )

        with patch(
            "swe.app.runner.runner.StdIOStatefulClient",
            _FakeStdIOClient,
        ):
            with tenant_context(tenant_id="tenant-a"):
                client = await _create_mcp_client_with_headers(client_config)

    assert captured["command"] == sys.executable
    assert captured["args"][:2] == ["-m", "swe.app.mcp.stdio_launcher"]
    assert captured["args"][-3:] == ["--", "node", "server.js"]
    rebuild_info = getattr(client, "_swe_rebuild_info")
    assert rebuild_info["command"] == "node"
    assert rebuild_info["args"] == ["server.js"]
    assert rebuild_info["launch_command"] == sys.executable


@pytest.mark.asyncio
async def test_runner_leaves_stdio_launch_unwrapped_when_policy_disabled(
    tenant_config_root: Path,
) -> None:
    with _stub_react_agent_tool_exports():
        from swe.app.runner.runner import _create_mcp_client_with_headers

        _write_process_limit_config(
            tenant_config_root,
            "tenant-a",
            enabled=False,
        )

        captured = {}

        class _FakeStdIOClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        client_config = MCPClientConfig(
            name="demo",
            transport="stdio",
            command="node",
            args=["server.js"],
            env={"DEMO": "1"},
            cwd="/tmp/demo",
        )

        with patch(
            "swe.app.runner.runner.StdIOStatefulClient",
            _FakeStdIOClient,
        ):
            with tenant_context(tenant_id="tenant-a"):
                await _create_mcp_client_with_headers(client_config)

    assert captured["command"] == "node"
    assert captured["args"] == ["server.js"]


def test_rebuild_mcp_client_reapplies_tenant_launcher(
    tenant_config_root: Path,
) -> None:
    with _stub_react_agent_tool_exports():
        from swe.agents.react_agent import SWEAgent

        _write_process_limit_config(
            tenant_config_root,
            "tenant-a",
            enabled=True,
            cpu_time_limit_seconds=2,
        )

        captured = {}

        class _FakeStdIOClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        original_client = SimpleNamespace(
            _swe_rebuild_info={
                "name": "demo",
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "env": {"DEMO": "1"},
                "cwd": "/tmp/demo",
            },
        )

        with patch(
            "swe.agents.react_agent.StdIOStatefulClient",
            _FakeStdIOClient,
        ):
            with tenant_context(tenant_id="tenant-a"):
                rebuilt = SWEAgent._rebuild_mcp_client(original_client)

    assert captured["command"] == sys.executable
    assert captured["args"][:2] == ["-m", "swe.app.mcp.stdio_launcher"]
    assert captured["args"][-3:] == ["--", "node", "server.js"]
    assert getattr(rebuilt, "_swe_rebuild_info")["command"] == "node"
