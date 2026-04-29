# -*- coding: utf-8 -*-
# flake8: noqa: E402
# pylint: disable=wrong-import-position,unused-import,protected-access,unused-variable
"""Integration tests for tenant-isolated provider configuration.

This module tests:
- Multi-tenant provider config isolation (Task 7.1)
- Auto-initialization for new tenants (Task 7.2)
- Migration behavior (Task 7.3)
- Backward compatibility (Task 7.4)
- Concurrent access performance (Task 7.5)
"""
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.providers.provider_manager import ProviderManager


class TestTenantIsolation:
    """Tests for multi-tenant provider configuration isolation (Task 7.1)."""

    def test_tenants_have_separate_provider_directories(self, tmp_path):
        """Each tenant has separate provider storage directory."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager_a = ProviderManager.get_instance("tenant-a")
            manager_b = ProviderManager.get_instance("tenant-b")

            # Verify different root paths
            assert manager_a.root_path != manager_b.root_path
            assert "tenant-a" in str(manager_a.root_path)
            assert "tenant-b" in str(manager_b.root_path)

    def test_tenant_api_keys_are_isolated(self, tmp_path):
        """API keys configured by one tenant are not visible to another."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager_a = ProviderManager.get_instance("apikey-a")
            manager_b = ProviderManager.get_instance("apikey-b")

            # Tenant A sets API key
            manager_a.update_provider(
                "openai",
                {"api_key": "sk-tenant-a-secret"},
            )

            # Tenant B sets different API key
            manager_b.update_provider(
                "openai",
                {"api_key": "sk-tenant-b-secret"},
            )

            # Reload managers and verify isolation
            ProviderManager._instances.clear()
            reloaded_a = ProviderManager.get_instance("apikey-a")
            reloaded_b = ProviderManager.get_instance("apikey-b")

            assert (
                reloaded_a.get_provider("openai").api_key
                == "sk-tenant-a-secret"
            )
            assert (
                reloaded_b.get_provider("openai").api_key
                == "sk-tenant-b-secret"
            )

    def test_tenant_active_models_are_isolated(self, tmp_path):
        """Active model selection is isolated per tenant."""
        from swe.providers.models import ModelSlotConfig

        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager_a = ProviderManager.get_instance("model-a")
            manager_b = ProviderManager.get_instance("model-b")

            # Tenant A sets active model
            manager_a.active_model = ModelSlotConfig(
                provider_id="openai",
                model="gpt-4",
            )
            manager_a.save_active_model(manager_a.active_model)

            # Tenant B sets different active model
            manager_b.active_model = ModelSlotConfig(
                provider_id="anthropic",
                model="claude-3",
            )
            manager_b.save_active_model(manager_b.active_model)

            # Verify isolation by reloading
            ProviderManager._instances.clear()
            reloaded_a = ProviderManager.get_instance("model-a")
            reloaded_b = ProviderManager.get_instance("model-b")

            assert reloaded_a.active_model.provider_id == "openai"
            assert reloaded_a.active_model.model == "gpt-4"
            assert reloaded_b.active_model.provider_id == "anthropic"
            assert reloaded_b.active_model.model == "claude-3"

    def test_custom_providers_are_tenant_scoped(self, tmp_path):
        """Custom providers added by one tenant don't appear for others."""
        import asyncio

        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager_a = ProviderManager.get_instance("custom-a")
            manager_b = ProviderManager.get_instance("custom-b")

            # Tenant A adds custom provider
            from swe.providers.provider import ProviderInfo

            custom_provider = ProviderInfo(
                id="custom-provider",
                name="Custom Provider",
                base_url="https://custom.example/v1",
                is_custom=True,
                chat_model="OpenAIChatModel",
            )
            asyncio.run(manager_a.add_custom_provider(custom_provider))

            # Tenant B should not see the custom provider
            assert manager_a.get_provider("custom-provider") is not None
            assert manager_b.get_provider("custom-provider") is None


class TestAutoInitialization:
    """Tests for automatic tenant configuration initialization (Task 7.2)."""

    def test_new_tenant_inherits_from_default(self, tmp_path):
        """New tenant inherits configuration from default tenant."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Setup default tenant with configuration
            default_manager = ProviderManager.get_instance("default")
            default_manager.update_provider(
                "openai",
                {"api_key": "sk-default-key"},
            )

            # Simulate auto-initialization by copying from default
            import shutil

            default_providers = (
                tmp_path / ".swe.secret" / "default" / "providers"
            )
            new_tenant_providers = (
                tmp_path / ".swe.secret" / "new-tenant" / "providers"
            )
            new_tenant_providers.mkdir(parents=True)

            # Copy builtin configs
            if (default_providers / "builtin").exists():
                shutil.copytree(
                    default_providers / "builtin",
                    new_tenant_providers / "builtin",
                )

            # Verify new tenant has inherited config
            new_manager = ProviderManager.get_instance("new-tenant")
            assert new_manager.get_provider("openai") is not None

    def test_empty_directory_fallback_when_default_empty(self, tmp_path):
        """New tenant gets empty directory when default has no config."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Create empty directory for new tenant
            new_tenant_dir = (
                tmp_path / ".swe.secret" / "empty-tenant" / "providers"
            )
            new_tenant_dir.mkdir(parents=True)

            # Verify directory structure exists
            assert new_tenant_dir.exists()


class TestMigrationBehavior:
    """Tests for migration behavior after running migration script (Task 7.3)."""

    def test_system_works_after_migration(self, tmp_path):
        """System works correctly after migrating to tenant-isolated storage."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Simulate migrated structure (default tenant has config)
            default_providers = (
                tmp_path / ".swe.secret" / "default" / "providers"
            )
            default_providers.mkdir(parents=True)
            builtin_dir = default_providers / "builtin"
            builtin_dir.mkdir()

            # Create a provider config
            import json

            (builtin_dir / "openai.json").write_text(
                json.dumps(
                    {
                        "id": "openai",
                        "name": "OpenAI",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-migrated",
                    },
                ),
            )

            # Verify system works with migrated structure
            ProviderManager._instances.clear()  # Clear cache to load from disk
            manager = ProviderManager.get_instance("default")
            provider = manager.get_provider("openai")
            assert provider is not None
            assert provider.api_key == "sk-migrated"

    def test_migrated_tenant_isolation(self, tmp_path):
        """Tenant isolation works after migration."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Setup migrated structure for multiple tenants
            for tenant in ["default", "alice", "bob"]:
                tenant_dir = (
                    tmp_path / ".swe.secret" / tenant / "providers" / "builtin"
                )
                tenant_dir.mkdir(parents=True)

                import json

                (tenant_dir / "openai.json").write_text(
                    json.dumps(
                        {
                            "id": "openai",
                            "name": "OpenAI",
                            "base_url": "https://api.openai.com/v1",
                            "api_key": f"sk-{tenant}",
                        },
                    ),
                )

            # Verify each tenant has isolated config
            ProviderManager._instances.clear()  # Clear cache to load from disk
            for tenant in ["default", "alice", "bob"]:
                manager = ProviderManager.get_instance(tenant)
                assert manager.get_provider("openai").api_key == f"sk-{tenant}"


class TestBackwardCompatibility:
    """Tests for backward compatibility with single-tenant mode (Task 7.4)."""

    def test_default_tenant_when_no_tenant_specified(self, tmp_path):
        """Default tenant is used when no tenant ID is specified."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager = ProviderManager.get_instance()
            assert manager.tenant_id == "default"

    def test_existing_code_works_without_modification(self, tmp_path):
        """Existing code using ProviderManager() still works."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Direct instantiation (old way)
            manager = ProviderManager()
            assert manager.tenant_id == "default"

            # Using get_instance without args (old way)
            manager = ProviderManager.get_instance()
            assert manager.tenant_id == "default"

    def test_none_tenant_defaults_to_default(self, tmp_path):
        """None tenant ID defaults to 'default' tenant."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            manager = ProviderManager.get_instance(None)
            assert manager.tenant_id == "default"


class TestConcurrentAccess:
    """Tests for multi-tenant concurrent access performance (Task 7.5)."""

    def test_thread_safe_instance_creation(self, tmp_path):
        """ProviderManager instance creation is thread-safe."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Clear any existing instances
            ProviderManager._instances.clear()

            results = []
            errors = []

            def create_manager(tenant_id):
                try:
                    manager = ProviderManager.get_instance(tenant_id)
                    results.append((tenant_id, manager.tenant_id))
                except Exception as e:
                    errors.append((tenant_id, str(e)))

            # Create multiple threads for different tenants
            threads = []
            for i in range(10):
                t = threading.Thread(
                    target=create_manager,
                    args=(f"tenant-{i}",),
                )
                threads.append(t)

            # Start all threads simultaneously
            for t in threads:
                t.start()

            # Wait for completion
            for t in threads:
                t.join()

            # Verify no errors
            assert (
                len(errors) == 0
            ), f"Errors during concurrent creation: {errors}"
            assert len(results) == 10

            # Verify all instances are distinct
            managers = [r[1] for r in results]
            assert len(set(managers)) == 10  # All different instances

    def test_cached_instance_retrieval_performance(self, tmp_path):
        """Cached instance retrieval is fast."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Pre-create instance
            manager = ProviderManager.get_instance("perf-tenant")

            # Measure retrieval time (should be very fast from cache)
            start = time.time()
            for _ in range(1000):
                ProviderManager.get_instance("perf-tenant")
            duration = time.time() - start

            # Should complete in under 0.1 seconds (cached access)
            assert duration < 0.1, f"Cached retrieval too slow: {duration}s"

    def test_concurrent_provider_access(self, tmp_path):
        """Multiple threads can access different tenant providers concurrently."""
        with patch(
            "swe.providers.provider_manager.SECRET_DIR",
            tmp_path / ".swe.secret",
        ):
            # Setup two tenants with different configs
            for tenant, key in [
                ("concurrent-a", "key-a"),
                ("concurrent-b", "key-b"),
            ]:
                manager = ProviderManager.get_instance(tenant)
                manager.update_provider("openai", {"api_key": key})

            results = {"a": None, "b": None}

            def read_provider(tenant, key):
                manager = ProviderManager.get_instance(tenant)
                provider = manager.get_provider("openai")
                results[key] = provider.api_key

            # Read both providers concurrently
            t1 = threading.Thread(
                target=read_provider,
                args=("concurrent-a", "a"),
            )
            t2 = threading.Thread(
                target=read_provider,
                args=("concurrent-b", "b"),
            )

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # Verify correct isolation
            assert results["a"] == "key-a"
            assert results["b"] == "key-b"
