# -*- coding: utf-8 -*-
"""Unit tests for tenant-scoped bootstrap helper functions."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import swe.app.migration as migration_module
import swe.constant as constant_module
from swe.agents.skills_manager import ensure_skill_pool_initialized
from swe.app.migration import (
    ensure_default_agent_exists,
    ensure_qa_agent_exists,
)
from swe.config.config import (
    Config,
    AgentsConfig,
    AgentProfileRef,
    load_agent_config,
)
from swe.config.utils import save_config
from swe.constant import BUILTIN_QA_AGENT_ID


def test_ensure_default_agent_exists_uses_tenant_working_dir(
    tmp_path,
    monkeypatch,
):
    tenant_dir = tmp_path / "tenant-alpha"
    global_dir = tmp_path / "global-default"
    monkeypatch.setattr(migration_module, "WORKING_DIR", global_dir)

    ensure_default_agent_exists(working_dir=tenant_dir)

    config_path = tenant_dir / "config.json"
    default_workspace = tenant_dir / "workspaces" / "default"

    assert config_path.exists()
    assert default_workspace.exists()
    assert (default_workspace / "chats.json").exists()
    assert (default_workspace / "jobs.json").exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = config_data.get("agents", {}).get("profiles", {})
    default_profile = profiles.get("default") or {}
    assert default_profile.get("workspace_dir") == str(default_workspace)

    assert not (global_dir / "config.json").exists()
    assert not (global_dir / "workspaces").exists()


def test_ensure_qa_agent_exists_uses_tenant_working_dir(tmp_path, monkeypatch):
    tenant_dir = tmp_path / "tenant-bravo"
    global_dir = tmp_path / "global-default"
    monkeypatch.setattr(migration_module, "WORKING_DIR", global_dir)

    ensure_qa_agent_exists(working_dir=tenant_dir)

    config_path = tenant_dir / "config.json"
    qa_workspace = tenant_dir / "workspaces" / BUILTIN_QA_AGENT_ID

    assert config_path.exists()
    assert qa_workspace.exists()
    assert (qa_workspace / "chats.json").exists()
    assert (qa_workspace / "jobs.json").exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = config_data.get("agents", {}).get("profiles", {})
    qa_profile = profiles.get(BUILTIN_QA_AGENT_ID) or {}
    assert qa_profile.get("workspace_dir") == str(qa_workspace)

    assert not (global_dir / "config.json").exists()
    assert not (global_dir / "workspaces").exists()


def test_ensure_qa_agent_exists_uses_tenant_language_templates(
    tmp_path,
    monkeypatch,
):
    tenant_dir = tmp_path / "tenant-echo"
    observed = {}
    original_agent_profile_config = migration_module.AgentProfileConfig
    save_config(
        Config(
            agents=AgentsConfig(
                language="ru",
                profiles={},
            ),
        ),
        tenant_dir / "config.json",
    )
    monkeypatch.setattr(
        migration_module,
        "AgentProfileConfig",
        lambda *args, **kwargs: (
            observed.update({"language": kwargs.get("language")})
            or original_agent_profile_config(*args, **kwargs)
        ),
    )

    ensure_qa_agent_exists(working_dir=tenant_dir)

    assert observed["language"] == "ru"


def test_ensure_skill_pool_initialized_uses_tenant_working_dir(
    tmp_path,
    monkeypatch,
):
    tenant_dir = tmp_path / "tenant-charlie"
    global_dir = tmp_path / "global-default"
    monkeypatch.setattr(constant_module, "WORKING_DIR", global_dir)

    created = ensure_skill_pool_initialized(working_dir=tenant_dir)

    assert (tenant_dir / "skill_pool").is_dir()
    assert created in (True, False)
    assert not (global_dir / "skill_pool").exists()


def test_load_agent_config_creates_agent_json_under_tenant_config_path(
    tmp_path,
):
    tenant_dir = tmp_path / "tenant-delta"
    workspace_dir = tenant_dir / "workspaces" / "default"

    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(workspace_dir),
                    ),
                },
                language="en",
            ),
        ),
        tenant_dir / "config.json",
    )

    agent_config = load_agent_config(
        "default",
        config_path=tenant_dir / "config.json",
    )

    assert agent_config.workspace_dir == str(workspace_dir)
    assert (workspace_dir / "agent.json").exists()
    assert not (tmp_path / "config.json").exists()
