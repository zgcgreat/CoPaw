# -*- coding: utf-8 -*-
"""Token usage tenant isolation regression tests."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.config.context import tenant_context
from swe.token_usage.manager import TokenUsageManager


def test_token_usage_manager_uses_tenant_workspace_path(tmp_path):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-a"
    tenant_workspace.mkdir()

    with tenant_context(tenant_id="tenant-a", workspace_dir=tenant_workspace):
        scoped_manager = TokenUsageManager.get_instance()
        asyncio.run(
            scoped_manager.record(
                provider_id="openai",
                model_name="gpt-5",
                prompt_tokens=3,
                completion_tokens=4,
                at_date=date(2026, 4, 2),
            ),
        )

    assert scoped_manager._path == tenant_workspace / "token_usage.json"
    assert scoped_manager._path.exists()


def test_token_usage_manager_migrates_legacy_empty_list_file(tmp_path):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-b"
    tenant_workspace.mkdir()
    (tenant_workspace / "token_usage.json").write_text(
        "[]",
        encoding="utf-8",
    )

    with tenant_context(tenant_id="tenant-b", workspace_dir=tenant_workspace):
        scoped_manager = TokenUsageManager.get_instance()
        asyncio.run(
            scoped_manager.record(
                provider_id="openai",
                model_name="gpt-5",
                prompt_tokens=5,
                completion_tokens=7,
                at_date=date(2026, 4, 8),
            ),
        )

    stored = (tenant_workspace / "token_usage.json").read_text(
        encoding="utf-8",
    )
    assert '"2026-04-08"' in stored
