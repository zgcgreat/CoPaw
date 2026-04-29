# -*- coding: utf-8 -*-
"""Tenant-local skill pool regression tests."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import swe.config as swe_config
from swe.agents import skills_hub
from swe.agents.skills_manager import (
    SkillPoolService,
    _build_signature,
    get_skill_pool_dir,
    get_workspace_skills_dir,
    import_builtin_skills,
    list_workspaces,
    list_builtin_import_candidates,
    reconcile_pool_manifest,
    update_single_builtin,
)
from swe.app.routers import agents as agents_router


def _write_skill(skill_dir: Path, description: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            f"---\nname: {skill_dir.name}\n"
            f"description: {description}\n---\n"
        ),
        encoding="utf-8",
    )


def test_skill_pool_service_upload_uses_tenant_pool(tmp_path: Path) -> None:
    tenant_a_dir = tmp_path / "tenant-a"
    tenant_b_dir = tmp_path / "tenant-b"
    workspace_dir = tenant_a_dir / "workspaces" / "alpha"
    _write_skill(
        get_workspace_skills_dir(workspace_dir) / "shared",
        "workspace tenant-a copy",
    )

    result = SkillPoolService(working_dir=tenant_a_dir).upload_from_workspace(
        workspace_dir=workspace_dir,
        skill_name="shared",
    )

    assert result == {"success": True, "name": "shared"}
    assert (tenant_a_dir / "skill_pool" / "shared" / "SKILL.md").read_text(
        encoding="utf-8",
    ).find("workspace tenant-a copy") != -1
    assert not (tenant_b_dir / "skill_pool" / "shared").exists()


def test_skill_pool_service_create_save_delete_are_tenant_scoped(
    tmp_path: Path,
) -> None:
    tenant_a_dir = tmp_path / "tenant-a"
    tenant_b_dir = tmp_path / "tenant-b"
    service_a = SkillPoolService(working_dir=tenant_a_dir)
    service_b = SkillPoolService(working_dir=tenant_b_dir)

    created_a = service_a.create_skill(
        name="shared",
        content="---\nname: shared\ndescription: tenant-a\n---\n",
    )
    created_b = service_b.create_skill(
        name="shared",
        content="---\nname: shared\ndescription: tenant-b\n---\n",
    )
    saved = service_a.save_pool_skill(
        skill_name="shared",
        content="---\nname: shared\ndescription: tenant-a updated\n---\n",
    )
    deleted = service_a.delete_skill("shared")

    assert created_a == "shared"
    assert created_b == "shared"
    assert saved == {"success": True, "mode": "edit", "name": "shared"}
    assert deleted is True
    assert not (tenant_a_dir / "skill_pool" / "shared").exists()
    assert (tenant_b_dir / "skill_pool" / "shared").exists()


def test_skill_pool_service_download_reads_tenant_local_pool(
    tmp_path: Path,
) -> None:
    tenant_a_dir = tmp_path / "tenant-a"
    tenant_b_dir = tmp_path / "tenant-b"
    workspace_dir = tenant_a_dir / "workspaces" / "target"

    _write_skill(
        get_skill_pool_dir(working_dir=tenant_a_dir) / "shared",
        "tenant-a pool copy",
    )
    _write_skill(
        get_skill_pool_dir(working_dir=tenant_b_dir) / "shared",
        "tenant-b pool copy",
    )
    reconcile_pool_manifest(working_dir=tenant_a_dir)
    reconcile_pool_manifest(working_dir=tenant_b_dir)

    result = SkillPoolService(
        working_dir=tenant_a_dir,
    ).download_to_workspace(
        skill_name="shared",
        workspace_dir=workspace_dir,
    )

    assert result["success"] is True
    skill_text = (workspace_dir / "skills" / "shared" / "SKILL.md").read_text(
        encoding="utf-8",
    )
    assert "tenant-a pool copy" in skill_text
    assert "tenant-b pool copy" not in skill_text


def test_list_builtin_import_candidates_reads_tenant_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tenant_dir = tmp_path / "tenant-a"
    _write_skill(
        get_skill_pool_dir(working_dir=tenant_dir) / "guidance",
        "tenant builtin copy",
    )
    reconcile_pool_manifest(working_dir=tenant_dir)

    manifest_path = tenant_dir / "skill_pool" / "skill.json"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest = manifest.replace(
        '"source": "customized"',
        '"source": "builtin"',
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    monkeypatch.setattr(
        "swe.agents.skills_manager._get_builtin_signatures",
        lambda: {"guidance": ""},
    )
    monkeypatch.setattr(
        "swe.agents.skills_manager._read_frontmatter_safe",
        lambda *args, **kwargs: {"description": "Builtin guidance"},
    )

    result = list_builtin_import_candidates(working_dir=tenant_dir)

    assert result[0]["name"] == "guidance"
    assert result[0]["current_source"] == "builtin"


def test_import_and_update_builtin_skills_are_tenant_scoped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tenant_a_dir = tmp_path / "tenant-a"
    tenant_b_dir = tmp_path / "tenant-b"
    builtin_root = tmp_path / "builtin-skills"
    builtin_skill_dir = builtin_root / "guidance"
    _write_skill(builtin_skill_dir, "builtin guidance v1")

    monkeypatch.setattr(
        "swe.agents.skills_manager.get_builtin_skills_dir",
        lambda: builtin_root,
    )
    monkeypatch.setattr(
        "swe.agents.skills_manager._get_builtin_signatures",
        lambda: {"guidance": _build_signature(builtin_skill_dir)},
    )

    imported = import_builtin_skills(
        ["guidance"],
        working_dir=tenant_a_dir,
    )

    _write_skill(
        get_skill_pool_dir(working_dir=tenant_a_dir) / "guidance",
        "tenant-a outdated guidance",
    )
    reconcile_pool_manifest(working_dir=tenant_a_dir)
    _write_skill(
        get_skill_pool_dir(working_dir=tenant_b_dir) / "guidance",
        "tenant-b custom guidance",
    )
    reconcile_pool_manifest(working_dir=tenant_b_dir)

    manifest_path = tenant_a_dir / "skill_pool" / "skill.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest_text.replace(
            '"source": "customized"',
            '"source": "builtin"',
        ),
        encoding="utf-8",
    )

    updated = update_single_builtin("guidance", working_dir=tenant_a_dir)

    assert imported["imported"] == ["guidance"]
    assert updated["source"] == "builtin"
    assert "builtin guidance v1" in (
        tenant_a_dir / "skill_pool" / "guidance" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "tenant-b custom guidance" in (
        tenant_b_dir / "skill_pool" / "guidance" / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_import_pool_skill_from_hub_passes_tenant_working_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, Path] = {}

    monkeypatch.setattr(skills_hub, "_is_http_url", lambda value: True)
    monkeypatch.setattr(
        skills_hub,
        "_resolve_bundle_from_url",
        lambda bundle_url, version: (b"zip", bundle_url),
    )
    monkeypatch.setattr(
        skills_hub,
        "_normalize_bundle",
        lambda data: (
            "hub-skill",
            "---\nname: hub-skill\ndescription: Imported\n---\n",
            None,
            None,
            None,
        ),
    )

    class FakePoolService:
        def __init__(self, working_dir: Path | None = None):
            observed["working_dir"] = working_dir

        def create_skill(self, **kwargs):
            return kwargs["name"]

    monkeypatch.setattr(skills_hub, "SkillPoolService", FakePoolService)

    result = skills_hub.import_pool_skill_from_hub(
        bundle_url="https://example.com/skill.zip",
        working_dir=tmp_path / "tenant-a",
    )

    assert result.name == "hub-skill"
    assert observed["working_dir"] == tmp_path / "tenant-a"


def test_initialize_agent_workspace_seeds_from_tenant_pool(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tenant_dir = tmp_path / "tenant-a"
    other_tenant_dir = tmp_path / "tenant-b"
    workspace_dir = tenant_dir / "workspaces" / "agent-1"

    _write_skill(
        get_skill_pool_dir(working_dir=tenant_dir) / "guidance",
        "tenant-a pool guidance",
    )
    _write_skill(
        get_skill_pool_dir(working_dir=other_tenant_dir) / "guidance",
        "tenant-b pool guidance",
    )

    monkeypatch.setattr(
        agents_router,
        "_ensure_default_heartbeat_md",
        lambda *args, **kwargs: None,
    )

    agents_router._initialize_agent_workspace(
        workspace_dir,
        SimpleNamespace(language="en"),
        skill_names=["guidance"],
        working_dir=tenant_dir,
    )

    skill_text = (
        workspace_dir / "skills" / "guidance" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "tenant-a pool guidance" in skill_text
    assert "tenant-b pool guidance" not in skill_text


def test_initialize_agent_workspace_prefers_agent_language(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "agent-ru"

    monkeypatch.setattr(
        swe_config,
        "load_config",
        lambda: (_ for _ in ()).throw(
            AssertionError("should not read global config"),
        ),
    )

    agents_router._initialize_agent_workspace(
        workspace_dir,
        SimpleNamespace(language="ru"),
    )

    assert "Встроенный" not in (workspace_dir / "AGENTS.md").read_text(
        encoding="utf-8",
    )
    assert "Шаблон рабочей области" in (workspace_dir / "AGENTS.md").read_text(
        encoding="utf-8",
    )


def test_list_workspaces_reads_agent_names_from_tenant_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tenant_config_path = tmp_path / "tenant-a" / "config.json"
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "shared"
    observed: dict[str, Path | None] = {}

    monkeypatch.setattr(
        "swe.config.utils.get_tenant_config_path",
        lambda tenant_id=None: tenant_config_path,
    )
    monkeypatch.setattr(
        "swe.config.utils.load_config",
        lambda path: SimpleNamespace(
            agents=SimpleNamespace(
                profiles={
                    "shared": SimpleNamespace(
                        workspace_dir=str(workspace_dir),
                    ),
                },
            ),
        ),
    )
    monkeypatch.setattr(
        "swe.config.config.load_agent_config",
        lambda agent_id, config_path=None, tenant_id=None: (
            observed.update({"config_path": config_path})
            or SimpleNamespace(name="Tenant Shared")
        ),
    )

    result = list_workspaces(tenant_id="tenant-a")

    assert observed["config_path"] == tenant_config_path
    assert result == [
        {
            "agent_id": "shared",
            "agent_name": "Tenant Shared",
            "workspace_dir": str(workspace_dir),
        },
    ]
