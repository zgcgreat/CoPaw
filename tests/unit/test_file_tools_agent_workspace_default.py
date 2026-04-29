# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from swe.agents.tools.file_io import append_file, read_file, write_file
from swe.config.context import tenant_context


@pytest.mark.asyncio
async def test_read_file_defaults_to_workspace_dir(tmp_path: Path):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "note.txt").write_text("workspace content")
    (tenant_dir / "note.txt").write_text("tenant-root content")

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await read_file("note.txt")

    assert "workspace content" in result.content[0].get("text", "")


@pytest.mark.asyncio
async def test_write_and_append_file_default_to_workspace_dir(tmp_path: Path):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            await write_file("note.txt", "hello")
            await append_file("note.txt", " world")

    # file_io uses UTF-8 BOM for .txt for Windows compatibility.
    assert (workspace_dir / "note.txt").read_text().lstrip(
        "\ufeff",
    ) == "hello world"
