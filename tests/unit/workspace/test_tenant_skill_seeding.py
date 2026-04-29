# -*- coding: utf-8 -*-
"""Tests for tenant-aware skill pool helpers and skill seeding.

Tests skill pool reconciliation with explicit working_dir parameter
and skill seeding from default tenant during full initialization.
"""
import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent.parent / "src"),
)

# pylint: disable=wrong-import-position
from swe.app.workspace.tenant_initializer import (  # noqa: E402
    TenantInitializer,
)
from swe.agents.skills_manager import (  # noqa: E402
    get_skill_pool_dir,
    get_pool_skill_manifest_path,
    get_workspace_skills_dir,
    get_workspace_skill_manifest_path,
    reconcile_pool_manifest,
    read_skill_pool_manifest,
    _write_json_atomic,
)


class TestTenantAwarePoolHelpers:
    """Tests for tenant-aware skill pool manifest helpers."""

    def test_reconcile_pool_manifest_uses_explicit_working_dir(self, tmp_path):
        """reconcile_pool_manifest targets the specified working_dir."""
        # Create tenant directories
        tenant_a = tmp_path / "tenant-a"
        tenant_b = tmp_path / "tenant-b"

        # Create skill pool directories with different skills
        pool_a = get_skill_pool_dir(working_dir=tenant_a)
        pool_b = get_skill_pool_dir(working_dir=tenant_b)

        pool_a.mkdir(parents=True, exist_ok=True)
        pool_b.mkdir(parents=True, exist_ok=True)

        # Create different skills in each pool
        skill_a_dir = pool_a / "skill-a"
        skill_a_dir.mkdir()
        (skill_a_dir / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: Skill A\n---\n",
            encoding="utf-8",
        )

        skill_b_dir = pool_b / "skill-b"
        skill_b_dir.mkdir()
        (skill_b_dir / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: Skill B\n---\n",
            encoding="utf-8",
        )

        # Reconcile each pool separately
        manifest_a = reconcile_pool_manifest(working_dir=tenant_a)
        manifest_b = reconcile_pool_manifest(working_dir=tenant_b)

        # Verify each manifest contains only its own skills
        assert "skill-a" in manifest_a.get("skills", {})
        assert "skill-b" not in manifest_a.get("skills", {})

        assert "skill-b" in manifest_b.get("skills", {})
        assert "skill-a" not in manifest_b.get("skills", {})

    def test_read_skill_pool_manifest_with_working_dir(self, tmp_path):
        """read_skill_pool_manifest targets the specified working_dir."""
        tenant_a = tmp_path / "tenant-a"
        tenant_b = tmp_path / "tenant-b"

        # Create manifests with different content
        manifest_a_path = get_pool_skill_manifest_path(working_dir=tenant_a)
        manifest_b_path = get_pool_skill_manifest_path(working_dir=tenant_b)

        manifest_a_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_b_path.parent.mkdir(parents=True, exist_ok=True)

        _write_json_atomic(
            manifest_a_path,
            {"skills": {"custom-skill": {"name": "custom-skill"}}},
        )
        _write_json_atomic(
            manifest_b_path,
            {"skills": {"other-skill": {"name": "other-skill"}}},
        )

        # Read without reconcile
        result_a = read_skill_pool_manifest(
            reconcile=False,
            working_dir=tenant_a,
        )
        result_b = read_skill_pool_manifest(
            reconcile=False,
            working_dir=tenant_b,
        )

        assert "custom-skill" in result_a.get("skills", {})
        assert "other-skill" in result_b.get("skills", {})


class TestSkillPoolSeeding:
    """Tests for skill pool seeding from default tenant."""

    def test_seed_skill_pool_from_default_copies_skills(self, tmp_path):
        """Seeding copies skills from default tenant to new tenant."""
        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create default tenant skill pool with custom skills
        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: Test Skill\n---\n",
            encoding="utf-8",
        )

        # Create manifest for default pool
        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {
                "skills": {
                    "test-skill": {
                        "name": "test-skill",
                        "source": "customized",
                    },
                },
            },
        )

        # Create new tenant and seed from default
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_skill_pool_from_default()

        assert result["seeded"] is True
        assert result["source"] == "default"
        assert "test-skill" in result["skills"]

        # Verify skill was copied
        target_pool = get_skill_pool_dir(working_dir=new_init.tenant_dir)
        assert (target_pool / "test-skill" / "SKILL.md").exists()

    def test_seed_skill_pool_skips_when_pool_exists(self, tmp_path):
        """Seeding is skipped when tenant already has skill pool state."""
        from swe.agents.skills_manager import (
            get_pool_skill_manifest_path,
            _write_json_atomic,
        )

        # Setup default tenant
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "default-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-skill\ndescription: Default Skill\n---\n",
            encoding="utf-8",
        )

        # Create new tenant with existing skill pool (with manifest)
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        new_pool = get_skill_pool_dir(working_dir=new_init.tenant_dir)
        new_pool.mkdir(parents=True, exist_ok=True)

        existing_skill = new_pool / "existing-skill"
        existing_skill.mkdir()
        (existing_skill / "SKILL.md").write_text(
            "---\nname: existing-skill\ndescription: Existing\n---\n",
            encoding="utf-8",
        )

        # Create manifest to indicate "complete" pool state
        manifest_path = get_pool_skill_manifest_path(
            working_dir=new_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {"skills": {"existing-skill": {"name": "existing-skill"}}},
        )

        # Try to seed - should be skipped
        result = new_init.seed_skill_pool_from_default()

        assert result["seeded"] is False
        assert result["source"] is None

        # Verify existing skill is preserved
        assert (new_pool / "existing-skill").exists()
        assert not (new_pool / "default-skill").exists()

    def test_seed_skill_pool_falls_back_to_builtin(self, tmp_path):
        """Falls back to builtin initialization when default has no pool."""
        # Create default tenant without skill pool
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create new tenant
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_skill_pool_from_default()

        assert result["seeded"] is True
        assert result["source"] == "builtin"
        # Should have builtin skills
        assert len(result["skills"]) > 0

    def test_seed_skill_pool_without_source_manifest(self, tmp_path):
        """Seeding works when source has skill directories but no manifest."""
        # Setup default tenant with skills but NO manifest
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create default tenant skill pool with skills on disk only
        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "manifestless-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: manifestless-skill\ndescription: No Manifest\n---\n",
            encoding="utf-8",
        )

        # Verify NO manifest exists
        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        assert not manifest_path.exists()

        # Create new tenant and seed from default
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_skill_pool_from_default()

        # Should still seed from disk content
        assert result["seeded"] is True
        assert result["source"] == "default"
        assert "manifestless-skill" in result["skills"]

        # Verify skill was copied and manifest was created
        target_pool = get_skill_pool_dir(working_dir=new_init.tenant_dir)
        assert (target_pool / "manifestless-skill" / "SKILL.md").exists()
        target_manifest = get_pool_skill_manifest_path(
            working_dir=new_init.tenant_dir,
        )
        assert target_manifest.exists()

    def test_seed_skill_pool_preserves_config(self, tmp_path):
        """Pool seeding preserves config field from source manifest."""
        # Setup default tenant with skills and config
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "config-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: config-skill\ndescription: Config Skill\n---\n",
            encoding="utf-8",
        )

        # Create manifest with config
        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {
                "skills": {
                    "config-skill": {
                        "name": "config-skill",
                        "config": {"api_key": "secret123", "timeout": 30},
                    },
                },
            },
        )

        # Create new tenant and seed from default
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_skill_pool_from_default()

        assert result["seeded"] is True
        assert "config-skill" in result["skills"]

        # Verify config was preserved in target manifest
        target_manifest = get_pool_skill_manifest_path(
            working_dir=new_init.tenant_dir,
        )
        manifest_data = json.loads(target_manifest.read_text(encoding="utf-8"))
        skill_entry = manifest_data.get("skills", {}).get("config-skill", {})

        assert skill_entry.get("config") == {
            "api_key": "secret123",
            "timeout": 30,
        }


class TestDefaultWorkspaceSkillSeeding:
    """Tests for default workspace skill seeding from default tenant."""

    def test_seed_workspace_skills_from_default(self, tmp_path):
        """Seeding copies workspace skills from default tenant."""
        # Setup default tenant with workspace skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_workspace = default_init.tenant_dir / "workspaces" / "default"
        default_skills = get_workspace_skills_dir(default_workspace)
        default_skills.mkdir(parents=True, exist_ok=True)

        skill_dir = default_skills / "workspace-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: workspace-skill\ndescription: WS Skill\n---\n",
            encoding="utf-8",
        )

        # Create manifest with user-state fields
        manifest_path = get_workspace_skill_manifest_path(default_workspace)
        _write_json_atomic(
            manifest_path,
            {
                "skills": {
                    "workspace-skill": {
                        "enabled": True,
                        "channels": ["console", "discord"],
                        "config": {"api_key": "secret"},
                        "source": "customized",
                    },
                },
            },
        )

        # Create new tenant and seed workspace skills
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_default_workspace_skills_from_default()

        assert result["seeded"] is True
        assert "workspace-skill" in result["skills"]

        # Verify skill was copied
        new_workspace = new_init.tenant_dir / "workspaces" / "default"
        new_skills = get_workspace_skills_dir(new_workspace)
        assert (new_skills / "workspace-skill" / "SKILL.md").exists()

        # Verify user-state fields were preserved
        new_manifest = get_workspace_skill_manifest_path(new_workspace)
        manifest_data = json.loads(new_manifest.read_text(encoding="utf-8"))
        skill_entry = manifest_data.get("skills", {}).get(
            "workspace-skill",
            {},
        )

        assert skill_entry.get("enabled") is True
        assert skill_entry.get("channels") == ["console", "discord"]
        assert skill_entry.get("config") == {"api_key": "secret"}
        assert skill_entry.get("source") == "customized"

    def test_seed_workspace_skills_skips_when_skills_exist(self, tmp_path):
        """Seeding is skipped when workspace already has skills."""
        from swe.agents.skills_manager import (
            get_workspace_skill_manifest_path,
            _write_json_atomic,
        )

        # Setup default tenant
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_workspace = default_init.tenant_dir / "workspaces" / "default"
        default_skills = get_workspace_skills_dir(default_workspace)
        default_skills.mkdir(parents=True, exist_ok=True)

        skill_dir = default_skills / "default-ws-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-ws-skill\ndescription: Default\n---\n",
            encoding="utf-8",
        )

        # Create new tenant with existing workspace skills (with manifest)
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        new_workspace = new_init.tenant_dir / "workspaces" / "default"
        new_skills = get_workspace_skills_dir(new_workspace)
        new_skills.mkdir(parents=True, exist_ok=True)

        existing_skill = new_skills / "existing-skill"
        existing_skill.mkdir()
        (existing_skill / "SKILL.md").write_text(
            "---\nname: existing-skill\ndescription: Existing\n---\n",
            encoding="utf-8",
        )

        # Create manifest to indicate "complete" workspace skill state
        manifest_path = get_workspace_skill_manifest_path(new_workspace)
        _write_json_atomic(
            manifest_path,
            {"skills": {"existing-skill": {"name": "existing-skill"}}},
        )

        # Try to seed - should be skipped
        result = new_init.seed_default_workspace_skills_from_default()

        assert result["seeded"] is False
        assert not result["skills"]

        # Verify existing skill is preserved
        assert (new_skills / "existing-skill").exists()
        assert not (new_skills / "default-ws-skill").exists()

    def test_seed_workspace_skills_skips_when_source_empty(self, tmp_path):
        """Seeding is skipped when default workspace has no skills."""
        # Setup default tenant without workspace skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create new tenant
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_default_workspace_skills_from_default()

        assert result["seeded"] is False
        assert not result["skills"]

    def test_seed_workspace_without_source_manifest(self, tmp_path):
        """Workspace seeding works when source has skills but no manifest."""
        # Setup default tenant with workspace skills but NO manifest
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_workspace = default_init.tenant_dir / "workspaces" / "default"
        default_skills = get_workspace_skills_dir(default_workspace)
        default_skills.mkdir(parents=True, exist_ok=True)

        skill_dir = default_skills / "manifestless-ws-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: manifestless-ws-skill\ndescription: No Manifest\n---\n",
            encoding="utf-8",
        )

        # Verify NO manifest exists
        manifest_path = get_workspace_skill_manifest_path(default_workspace)
        assert not manifest_path.exists()

        # Create new tenant and seed workspace skills
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.ensure_directory_structure()

        result = new_init.seed_default_workspace_skills_from_default()

        # Should still seed from disk content
        assert result["seeded"] is True
        assert "manifestless-ws-skill" in result["skills"]

        # Verify skill was copied and manifest was created
        new_workspace = new_init.tenant_dir / "workspaces" / "default"
        new_skills = get_workspace_skills_dir(new_workspace)
        assert (new_skills / "manifestless-ws-skill" / "SKILL.md").exists()
        new_manifest = get_workspace_skill_manifest_path(new_workspace)
        assert new_manifest.exists()


class TestFullInitialization:
    """Tests for full tenant initialization with skill seeding."""

    def test_initialize_full_seeds_from_default(self, tmp_path):
        """Full initialization seeds skills from default tenant."""
        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create default pool skill
        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        pool_skill = default_pool / "pool-skill"
        pool_skill.mkdir()
        (pool_skill / "SKILL.md").write_text(
            "---\nname: pool-skill\ndescription: Pool Skill\n---\n",
            encoding="utf-8",
        )

        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {"skills": {"pool-skill": {"name": "pool-skill"}}},
        )

        # Create default workspace skill
        default_workspace = default_init.tenant_dir / "workspaces" / "default"
        default_skills = get_workspace_skills_dir(default_workspace)
        default_skills.mkdir(parents=True, exist_ok=True)

        ws_skill = default_skills / "ws-skill"
        ws_skill.mkdir()
        (ws_skill / "SKILL.md").write_text(
            "---\nname: ws-skill\ndescription: WS Skill\n---\n",
            encoding="utf-8",
        )

        ws_manifest_path = get_workspace_skill_manifest_path(default_workspace)
        _write_json_atomic(
            ws_manifest_path,
            {"skills": {"ws-skill": {"enabled": True, "channels": ["all"]}}},
        )

        # Initialize new tenant
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result = new_init.initialize_full()

        assert result["minimal"] is True
        assert result["pool_seed"]["seeded"] is True
        assert result["pool_seed"]["source"] == "default"
        assert "pool-skill" in result["pool_seed"]["skills"]
        assert result["workspace_seed"]["seeded"] is True
        assert "ws-skill" in result["workspace_seed"]["skills"]
        assert result["qa_agent"] is True

        # Verify skills exist in new tenant
        new_pool = get_skill_pool_dir(working_dir=new_init.tenant_dir)
        assert (new_pool / "pool-skill" / "SKILL.md").exists()

        new_workspace = new_init.tenant_dir / "workspaces" / "default"
        new_skills = get_workspace_skills_dir(new_workspace)
        assert (new_skills / "ws-skill" / "SKILL.md").exists()

    def test_initialize_minimal_does_not_seed_skills(self, tmp_path):
        """Minimal initialization does not copy or initialize skills."""
        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "default-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-skill\ndescription: Default\n---\n",
            encoding="utf-8",
        )

        # Initialize new tenant with minimal
        new_init = TenantInitializer(tmp_path, "new-tenant")
        new_init.initialize_minimal()

        # Verify no skills were copied
        new_pool = get_skill_pool_dir(working_dir=new_init.tenant_dir)
        assert not new_pool.exists() or not any(new_pool.iterdir())

        # Verify no workspace skills
        new_workspace = new_init.tenant_dir / "workspaces" / "default"
        new_skills = get_workspace_skills_dir(new_workspace)
        assert not new_skills.exists() or not any(new_skills.iterdir())

    def test_runtime_bootstrap_does_not_create_qa_agent(self, tmp_path):
        """Runtime bootstrap (ensure_seeded_bootstrap) does NOT create QA agent."""
        from swe.constant import BUILTIN_QA_AGENT_ID

        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "default-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-skill\ndescription: Default\n---\n",
            encoding="utf-8",
        )

        # Run runtime bootstrap
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result = new_init.ensure_seeded_bootstrap()

        # Skills should be seeded
        assert result["pool_seed"]["seeded"] is True

        # QA agent should NOT be created in runtime bootstrap
        assert not (
            new_init.tenant_dir / "workspaces" / BUILTIN_QA_AGENT_ID
        ).exists()

    def test_full_initialization_creates_qa_agent(self, tmp_path):
        """Full initialization (CLI) DOES create QA agent."""
        from swe.constant import BUILTIN_QA_AGENT_ID

        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "default-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-skill\ndescription: Default\n---\n",
            encoding="utf-8",
        )

        # Run full initialization
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result = new_init.initialize_full()

        # Skills should be seeded
        assert result["pool_seed"]["seeded"] is True

        # QA agent SHOULD be created in full initialization
        assert result["qa_agent"] is True
        assert (
            new_init.tenant_dir / "workspaces" / BUILTIN_QA_AGENT_ID
        ).exists()
