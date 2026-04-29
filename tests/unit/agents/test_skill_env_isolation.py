# -*- coding: utf-8 -*-
"""Skill env override isolation regression tests."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.agents import skills_manager
from swe.constant import EnvVarLoader


def test_apply_skill_config_env_overrides_scopes_values_without_mutating_process_env(
    monkeypatch,
    tmp_path,
):
    workspace_dir = tmp_path / "tenant-a"
    workspace_dir.mkdir()

    monkeypatch.setattr(
        skills_manager,
        "reconcile_workspace_manifest",
        lambda workspace_dir: {
            "skills": {
                "demo": {
                    "config": {"API_KEY": "tenant-secret"},
                    "requirements": {"require_envs": ["API_KEY"]},
                },
            },
        },
    )
    monkeypatch.setattr(
        skills_manager,
        "resolve_effective_skills",
        lambda workspace_dir, channel_name: ["demo"],
    )
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("SWE_SKILL_CONFIG_DEMO", raising=False)

    with skills_manager.apply_skill_config_env_overrides(
        workspace_dir,
        "console",
    ):
        assert os.environ.get("API_KEY") is None
        assert os.environ.get("SWE_SKILL_CONFIG_DEMO") is None
        assert EnvVarLoader.get_str("API_KEY") == "tenant-secret"
        assert (
            EnvVarLoader.get_str("SWE_SKILL_CONFIG_DEMO")
            == '{"API_KEY": "tenant-secret"}'
        )

    assert os.environ.get("API_KEY") is None
    assert os.environ.get("SWE_SKILL_CONFIG_DEMO") is None
    assert EnvVarLoader.get_str("API_KEY") == ""
    assert EnvVarLoader.get_str("SWE_SKILL_CONFIG_DEMO") == ""
