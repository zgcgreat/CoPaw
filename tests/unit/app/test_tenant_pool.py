# -*- coding: utf-8 -*-
"""Unit tests for TenantWorkspacePool.

Tests lazy creation, cache hits, concurrent creation safety, and stop-all cleanup.
"""
# pylint: disable=wrong-import-position,protected-access,unused-import
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest  # noqa: E402,F401

from swe.app.workspace.tenant_pool import (  # noqa: E402
    TenantWorkspacePool,
    TenantWorkspaceEntry,
)
from swe.config.config import (  # noqa: E402
    Config,
    AgentsConfig,
    AgentProfileRef,
)
from swe.config.utils import save_config  # noqa: E402


@pytest.fixture(name="mock_working_dir")
def _mock_working_dir(tmp_path, monkeypatch):
    """Mock WORKING_DIR to use tmp_path for isolation."""
    from swe import constant

    monkeypatch.setattr(constant, "WORKING_DIR", tmp_path / "swe")
    return tmp_path / "swe"


class TestTenantWorkspacePoolBasics:
    """Basic functionality tests."""

    def test_initialization_creates_base_dir(self, tmp_path):
        """Pool initialization creates base directory if needed."""
        base_dir = tmp_path / "tenants"
        assert not base_dir.exists()

        TenantWorkspacePool(base_dir)

        assert base_dir.exists()
        assert base_dir.is_dir()

    def test_initialization_with_existing_dir(self, tmp_path):
        """Pool initialization works with existing directory."""
        base_dir = tmp_path / "tenants"
        base_dir.mkdir()

        pool = TenantWorkspacePool(base_dir)

        assert pool._base_working_dir == base_dir

    def test_len_empty_pool(self, tmp_path):
        """Empty pool has length 0."""
        pool = TenantWorkspacePool(tmp_path / "tenants")
        assert len(pool) == 0

    def test_contains_empty_pool(self, tmp_path):
        """Empty pool doesn't contain any tenant."""
        pool = TenantWorkspacePool(tmp_path / "tenants")
        assert "tenant-1" not in pool


class TestTenantWorkspaceCreation:
    """Tests for workspace creation."""

    async def test_get_or_create_creates_workspace(
        self,
        mock_working_dir,
    ):
        """get_or_create creates a new workspace."""
        pool = TenantWorkspacePool(mock_working_dir)

        workspace = await pool.get_or_create("tenant-1")

        assert workspace is not None
        assert workspace.agent_id == "default"

    async def test_get_or_create_uses_default_agent_id(
        self,
        mock_working_dir,
    ):
        """get_or_create uses default agent_id."""
        pool = TenantWorkspacePool(mock_working_dir)

        workspace = await pool.get_or_create("tenant-1")

        assert workspace.agent_id == "default"

    async def test_get_or_create_creates_tenant_dir(self, tmp_path):
        """get_or_create creates tenant workspace directory."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")

        tenant_dir = pool._get_tenant_workspace_dir("tenant-1")
        assert tenant_dir.exists()
        assert tenant_dir.is_dir()

    async def test_get_or_create_returns_existing_workspace(self, tmp_path):
        """get_or_create returns existing workspace on second call."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        workspace1 = await pool.get_or_create("tenant-1")
        workspace2 = await pool.get_or_create("tenant-1")

        assert workspace1 is workspace2  # Same instance

    async def test_get_or_create_increases_pool_size(self, tmp_path):
        """get_or_create increases pool size."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        assert len(pool) == 0

        await pool.get_or_create("tenant-1")
        assert len(pool) == 1

        await pool.get_or_create("tenant-2")
        assert len(pool) == 2

        # Same tenant doesn't increase size
        await pool.get_or_create("tenant-1")
        assert len(pool) == 2


class TestTenantWorkspaceGet:
    """Tests for get method."""

    async def test_get_returns_none_when_not_exists(self, tmp_path):
        """get returns None when workspace doesn't exist."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        result = await pool.get("tenant-1")

        assert result is None

    async def test_get_returns_existing_workspace(self, tmp_path):
        """get returns workspace if it exists."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        created = await pool.get_or_create("tenant-1")
        retrieved = await pool.get("tenant-1")

        assert retrieved is created

    async def test_get_does_not_create_workspace(self, tmp_path):
        """get does not create workspace if not exists."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        result = await pool.get("tenant-1")

        assert result is None
        assert len(pool) == 0


class TestTenantWorkspaceRemove:
    """Tests for remove method."""

    async def test_remove_returns_none_when_not_exists(self, tmp_path):
        """remove returns None when workspace doesn't exist."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        result = await pool.remove("tenant-1")

        assert result is None

    async def test_remove_returns_workspace(self, tmp_path):
        """remove returns workspace when it exists."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        created = await pool.get_or_create("tenant-1")
        removed = await pool.remove("tenant-1")

        assert removed is created

    async def test_removes_from_pool(self, tmp_path):
        """remove removes workspace from pool."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")
        assert "tenant-1" in pool

        await pool.remove("tenant-1")
        assert "tenant-1" not in pool


class TestTenantWorkspaceStop:
    """Tests for stop method."""

    async def test_stop_returns_false_when_not_exists(self, tmp_path):
        """stop returns False when workspace doesn't exist."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        result = await pool.stop("tenant-1")

        assert result is False

    async def test_stop_removes_from_pool(self, tmp_path):
        """stop removes workspace from pool."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")
        await pool.stop("tenant-1")

        assert "tenant-1" not in pool


class TestTenantWorkspaceStopAll:
    """Tests for stop_all method."""

    async def test_stop_all_empty_pool(self, tmp_path):
        """stop_all handles empty pool."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.stop_all()

        assert len(pool) == 0

    async def test_stop_all_removes_all_workspaces(self, tmp_path):
        """stop_all removes all workspaces from pool."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")
        await pool.get_or_create("tenant-2")
        await pool.get_or_create("tenant-3")

        assert len(pool) == 3

        await pool.stop_all()

        assert len(pool) == 0


class TestTenantWorkspaceAccessTracking:
    """Tests for access tracking."""

    async def test_mark_access_updates_timestamp(self, tmp_path):
        """mark_access updates last_accessed_at."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")

        await pool.mark_access("tenant-1")

        # Entry was updated (we can't easily test the exact timestamp)
        result = await pool.mark_access("tenant-1")
        assert result is True

    async def test_mark_access_returns_false_when_not_exists(self, tmp_path):
        """mark_access returns False when workspace doesn't exist."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        result = await pool.mark_access("tenant-1")

        assert result is False

    async def test_get_or_create_tracks_access(self, tmp_path):
        """get_or_create tracks access count."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")
        await pool.get_or_create("tenant-1")  # Second access
        await pool.get_or_create("tenant-1")  # Third access

        # Access should have been tracked (via get_or_create -> mark_access)
        stats = await pool.get_stats()
        assert stats["tenants"]["tenant-1"]["access_count"] >= 1


class TestTenantWorkspaceStats:
    """Tests for get_stats method."""

    async def test_get_stats_empty_pool(self, tmp_path):
        """get_stats returns empty info for empty pool."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        stats = await pool.get_stats()

        assert stats["tenant_count"] == 0
        assert stats["tenants"] == {}

    async def test_get_stats_with_tenants(self, tmp_path):
        """get_stats returns info for all tenants."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        await pool.get_or_create("tenant-1")
        await pool.get_or_create("tenant-2")

        stats = await pool.get_stats()

        assert stats["tenant_count"] == 2
        assert "tenant-1" in stats["tenants"]
        assert "tenant-2" in stats["tenants"]
        assert "created_at" in stats["tenants"]["tenant-1"]
        assert "last_accessed_at" in stats["tenants"]["tenant-1"]
        assert "access_count" in stats["tenants"]["tenant-1"]


class TestTenantWorkspaceConcurrency:
    """Tests for concurrent access safety."""

    def test_concurrent_get_or_create_same_tenant(self, tmp_path):
        """Concurrent get_or_create for same tenant returns same workspace."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        async def run_test():
            async def get_workspace():
                return await pool.get_or_create("tenant-1")

            return await asyncio.gather(*[get_workspace() for _ in range(10)])

        workspaces = asyncio.run(run_test())

        first = workspaces[0]
        for ws in workspaces[1:]:
            assert ws is first

    def test_concurrent_get_or_create_different_tenants(self, tmp_path):
        """Concurrent get_or_create for different tenants works correctly."""
        pool = TenantWorkspacePool(tmp_path / "tenants")

        async def run_test():
            async def get_workspace(tenant_id):
                return await pool.get_or_create(tenant_id)

            return await asyncio.gather(
                *[get_workspace(f"tenant-{i}") for i in range(5)],
            )

        workspaces = asyncio.run(run_test())

        assert len(set(id(ws) for ws in workspaces)) == 5
        assert len(pool) == 5


class TestTenantBootstrapConcurrency:
    """Tests for concurrent first-access bootstrap with skill seeding."""

    def test_concurrent_ensure_bootstrap_seeds_once(self, tmp_path):
        """Concurrent ensure_bootstrap seeds skills once per tenant."""
        from swe.agents.skills_manager import (
            get_skill_pool_dir,
            get_pool_skill_manifest_path,
            _write_json_atomic,
        )

        # Setup default tenant with skills
        default_pool = get_skill_pool_dir(working_dir=tmp_path / "default")
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "concurrent-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: concurrent-skill\ndescription: Concurrent\n---\n",
            encoding="utf-8",
        )

        manifest_path = get_pool_skill_manifest_path(
            working_dir=tmp_path / "default",
        )
        _write_json_atomic(
            manifest_path,
            {"skills": {"concurrent-skill": {"name": "concurrent-skill"}}},
        )

        pool = TenantWorkspacePool(tmp_path)

        async def run_test():
            async def bootstrap_tenant():
                await pool.ensure_bootstrap("concurrent-tenant")
                return True

            # Concurrent bootstraps for same tenant
            results = await asyncio.gather(
                *[bootstrap_tenant() for _ in range(10)],
            )
            return results

        results = asyncio.run(run_test())

        # All should succeed
        assert all(results)

        # Tenant should be in pool
        assert "concurrent-tenant" in pool

        # Verify skills were seeded (only once)
        from swe.agents.skills_manager import get_skill_pool_dir

        tenant_pool = get_skill_pool_dir(
            working_dir=tmp_path / "concurrent-tenant",
        )
        assert (tenant_pool / "concurrent-skill" / "SKILL.md").exists()

    def test_concurrent_ensure_bootstrap_different_tenants(self, tmp_path):
        """Concurrent ensure_bootstrap for different tenants works correctly."""
        from swe.agents.skills_manager import (
            get_skill_pool_dir,
            get_pool_skill_manifest_path,
            _write_json_atomic,
        )

        # Setup default tenant with skills
        default_pool = get_skill_pool_dir(working_dir=tmp_path / "default")
        default_pool.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            skill_dir = default_pool / f"shared-skill-{i}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: shared-skill-{i}\ndescription: Shared\n---\n",
                encoding="utf-8",
            )

        manifest_path = get_pool_skill_manifest_path(
            working_dir=tmp_path / "default",
        )
        _write_json_atomic(
            manifest_path,
            {
                "skills": {
                    "shared-skill-0": {"name": "shared-skill-0"},
                    "shared-skill-1": {"name": "shared-skill-1"},
                    "shared-skill-2": {"name": "shared-skill-2"},
                },
            },
        )

        pool = TenantWorkspacePool(tmp_path)

        async def run_test():
            async def bootstrap_tenant(tenant_id):
                await pool.ensure_bootstrap(tenant_id)
                return tenant_id

            # Concurrent bootstraps for different tenants
            tenant_ids = [f"tenant-{i}" for i in range(5)]
            results = await asyncio.gather(
                *[bootstrap_tenant(tid) for tid in tenant_ids],
            )
            return results

        results = asyncio.run(run_test())

        # All tenants should be bootstrapped
        assert len(results) == 5
        assert len(pool) == 5

        # Each tenant should have the skills seeded
        for tenant_id in results:
            tenant_pool = get_skill_pool_dir(working_dir=tmp_path / tenant_id)
            assert (tenant_pool / "shared-skill-0" / "SKILL.md").exists()

    def test_ensure_bootstrap_repairs_cached_tenant_scaffold(self, tmp_path):
        """ensure_bootstrap self-heals missing files for cached tenants."""
        default_tenant = tmp_path / "default"
        default_workspace = default_tenant / "workspaces" / "default"
        default_workspace.mkdir(parents=True)

        save_config(
            Config(
                agents=AgentsConfig(
                    active_agent="default",
                    profiles={
                        "default": AgentProfileRef(
                            id="default",
                            workspace_dir=str(default_workspace),
                        ),
                    },
                    language="zh",
                ),
            ),
            default_tenant / "config.json",
        )

        (default_workspace / "AGENTS.md").write_text(
            "# agents\n",
            encoding="utf-8",
        )
        (default_workspace / "BOOTSTRAP.md").write_text(
            "# bootstrap\n",
            encoding="utf-8",
        )
        (default_workspace / "HEARTBEAT.md").write_text(
            "# heartbeat\n",
            encoding="utf-8",
        )
        (default_workspace / "MEMORY.md").write_text(
            "# memory\n",
            encoding="utf-8",
        )
        (default_workspace / "PROFILE.md").write_text(
            "# profile\n",
            encoding="utf-8",
        )
        (default_workspace / "SOUL.md").write_text(
            "# soul\n",
            encoding="utf-8",
        )

        pool = TenantWorkspacePool(tmp_path)

        async def run_test():
            await pool.ensure_bootstrap("tenant-heal")

            workspace = tmp_path / "tenant-heal" / "workspaces" / "default"
            (tmp_path / "tenant-heal" / "config.json").unlink()
            (workspace / "AGENTS.md").unlink()
            (workspace / "agent.json").unlink()
            (workspace / "token_usage.json").unlink()

            await pool.ensure_bootstrap("tenant-heal")

            return workspace

        workspace = asyncio.run(run_test())

        assert (tmp_path / "tenant-heal" / "config.json").exists()
        assert (workspace / "AGENTS.md").exists()
        assert (workspace / "agent.json").exists()
        assert (workspace / "token_usage.json").exists()

        token_usage = json.loads(
            (workspace / "token_usage.json").read_text(encoding="utf-8"),
        )
        assert token_usage == {}

    def test_ensure_bootstrap_does_not_recreate_deleted_bootstrap_md(
        self,
        tmp_path,
    ):
        """Deleting BOOTSTRAP.md should not trigger cached-tenant self-heal."""
        default_tenant = tmp_path / "default"
        default_workspace = default_tenant / "workspaces" / "default"
        default_workspace.mkdir(parents=True)

        save_config(
            Config(
                agents=AgentsConfig(
                    active_agent="default",
                    profiles={
                        "default": AgentProfileRef(
                            id="default",
                            workspace_dir=str(default_workspace),
                        ),
                    },
                ),
            ),
            default_tenant / "config.json",
        )

        for filename in (
            "AGENTS.md",
            "BOOTSTRAP.md",
            "HEARTBEAT.md",
            "MEMORY.md",
            "PROFILE.md",
            "SOUL.md",
        ):
            (default_workspace / filename).write_text(
                "# template\n",
                encoding="utf-8",
            )

        pool = TenantWorkspacePool(tmp_path)

        async def run_test():
            await pool.ensure_bootstrap("tenant-keep")
            bootstrap_path = (
                tmp_path
                / "tenant-keep"
                / "workspaces"
                / "default"
                / "BOOTSTRAP.md"
            )
            bootstrap_path.unlink()

            await pool.ensure_bootstrap("tenant-keep")
            return bootstrap_path

        bootstrap_path = asyncio.run(run_test())

        assert not bootstrap_path.exists()


class TestTenantWorkspaceDirectoryLayout:
    """Tests for tenant workspace directory layout."""

    def test_tenant_workspace_dir_under_base(self, tmp_path):
        """Tenant workspace dir is under base working dir."""
        base_dir = tmp_path / "tenants"
        pool = TenantWorkspacePool(base_dir)

        tenant_dir = pool._get_tenant_workspace_dir("tenant-1")

        # Compare with resolved base path since pool resolves it
        assert tenant_dir.parent == pool._base_working_dir
        assert tenant_dir.name == "tenant-1"

    def test_different_tenants_different_dirs(self, tmp_path):
        """Different tenants get different directories."""
        base_dir = tmp_path / "tenants"
        pool = TenantWorkspacePool(base_dir)

        dir1 = pool._get_tenant_workspace_dir("tenant-1")
        dir2 = pool._get_tenant_workspace_dir("tenant-2")

        assert dir1 != dir2
        assert dir1.parent == dir2.parent

    def test_tenant_dir_with_special_chars(self, tmp_path):
        """Tenant IDs with special characters work correctly."""
        base_dir = tmp_path / "tenants"
        pool = TenantWorkspacePool(base_dir)

        # Test various tenant ID formats
        tenant_ids = [
            "tenant-1",
            "tenant_1",
            "tenant.1",
            "Tenant1",
            "123-abc",
            "a" * 50,
        ]

        for tenant_id in tenant_ids:
            dir_path = pool._get_tenant_workspace_dir(tenant_id)
            assert dir_path.name == tenant_id
            assert dir_path.parent == base_dir


class TestTenantWorkspaceEntry:
    """Tests for TenantWorkspaceEntry dataclass."""

    def test_entry_creation(self):
        """TenantWorkspaceEntry can be created."""

        # Create a mock workspace
        class MockWorkspace:
            pass

        entry = TenantWorkspaceEntry(
            tenant_id="tenant-1",
            workspace=MockWorkspace(),
        )

        assert entry.tenant_id == "tenant-1"
        assert entry.access_count == 0
        assert entry.created_at > 0
        assert entry.last_accessed_at > 0
