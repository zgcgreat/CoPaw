# -*- coding: utf-8 -*-
"""Tests for TenantModelManager configuration management."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from swe.tenant_models.exceptions import TenantModelNotFoundError
from swe.tenant_models.manager import TenantModelManager
from swe.tenant_models.models import (
    ModelSlot,
    RoutingConfig,
    TenantModelConfig,
    TenantProviderConfig,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the manager cache before and after each test."""
    TenantModelManager.invalidate_cache()
    yield
    TenantModelManager.invalidate_cache()


@pytest.fixture
def sample_config():
    """Create a sample TenantModelConfig for testing."""
    return TenantModelConfig(
        version="1.0",
        providers=[
            TenantProviderConfig(
                id="openai-main",
                type="openai",
                api_key="test-key",
                models=["gpt-4"],
                enabled=True,
            ),
        ],
        routing=RoutingConfig(
            mode="cloud_first",
            slots={
                "cloud": ModelSlot(provider_id="openai-main", model="gpt-4"),
                "local": ModelSlot(provider_id="ollama-local", model="llama2"),
            },
        ),
    )


@pytest.fixture
def default_config():
    """Create a default TenantModelConfig for fallback testing."""
    return TenantModelConfig(
        version="1.0",
        providers=[
            TenantProviderConfig(
                id="default-provider",
                type="openai",
                api_key="default-key",
                models=["gpt-3.5-turbo"],
                enabled=True,
            ),
        ],
        routing=RoutingConfig(
            mode="cloud_first",
            slots={
                "cloud": ModelSlot(
                    provider_id="default-provider",
                    model="gpt-3.5-turbo",
                ),
            },
        ),
    )


class TestTenantModelManagerGetConfigPath:
    """Tests for get_config_path method."""

    def test_get_config_path_returns_correct_path(self, tmp_path):
        """Test that get_config_path returns the expected file path."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"
            expected_path = tmp_path / tenant_id / "tenant_models.json"

            result = manager.get_config_path(tenant_id)

            assert result == expected_path

    def test_get_config_path_with_different_tenants(self, tmp_path):
        """Test that different tenant IDs produce different paths."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()

            path1 = manager.get_config_path("tenant1")
            path2 = manager.get_config_path("tenant2")

            assert path1 != path2
            assert "tenant1" in str(path1)
            assert "tenant2" in str(path2)


class TestTenantModelManagerExists:
    """Tests for exists method."""

    def test_exists_returns_true_for_existing_config(
        self,
        tmp_path,
        sample_config,
    ):
        """Test exists returns True when config file exists."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            # Create config file
            config_path = manager.get_config_path(tenant_id)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(sample_config.model_dump_json())

            assert manager.exists(tenant_id) is True

    def test_exists_returns_false_for_missing_config(self, tmp_path):
        """Test exists returns False when config file doesn't exist."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "nonexistent-tenant"

            assert manager.exists(tenant_id) is False


class TestTenantModelManagerSave:
    """Tests for save method."""

    def test_save_creates_directory_if_not_exists(
        self,
        tmp_path,
        sample_config,
    ):
        """Test save creates the tenant directory if it doesn't exist."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            config_path = manager.get_config_path(tenant_id)
            assert not config_path.parent.exists()

            manager.save(tenant_id, sample_config)

            assert config_path.parent.exists()
            assert config_path.exists()

    def test_save_writes_valid_json(self, tmp_path, sample_config):
        """Test save writes valid JSON that can be loaded."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            manager.save(tenant_id, sample_config)

            config_path = manager.get_config_path(tenant_id)
            with open(config_path) as f:
                data = json.load(f)

            assert data["version"] == "1.0"
            assert len(data["providers"]) == 1
            assert data["providers"][0]["id"] == "openai-main"

    def test_save_overwrites_existing_config(self, tmp_path, sample_config):
        """Test save overwrites an existing config file."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            # Save initial config
            manager.save(tenant_id, sample_config)

            # Modify and save again
            sample_config.providers[0].api_key = "new-key"
            manager.save(tenant_id, sample_config)

            # Verify the file was updated
            loaded = manager.load(tenant_id)
            assert loaded.providers[0].api_key == "new-key"


class TestTenantModelManagerLoad:
    """Tests for load method."""

    def test_load_existing_config(self, tmp_path, sample_config):
        """Test load returns the config for an existing tenant."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            manager.save(tenant_id, sample_config)
            loaded_config = manager.load(tenant_id)

            assert loaded_config.version == sample_config.version
            assert (
                loaded_config.providers[0].id == sample_config.providers[0].id
            )

    def test_load_caches_config(self, tmp_path, sample_config):
        """Test load caches the loaded config."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            manager.save(tenant_id, sample_config)

            # Load twice - second load should use cache
            config1 = manager.load(tenant_id)
            config2 = manager.load(tenant_id)

            # Should be the same object (cached)
            assert config1 is config2

    def test_load_fallback_to_default(self, tmp_path, default_config):
        """Test load falls back to 'default' tenant if requested tenant doesn't exist."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()

            # Save default config
            manager.save("default", default_config)

            # Load nonexistent tenant - should fall back to default
            loaded = manager.load("nonexistent-tenant")

            assert loaded.providers[0].id == "default-provider"

    def test_load_raises_error_if_no_default(self, tmp_path):
        """Test load raises TenantModelNotFoundError if neither tenant nor default exists."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()

            with pytest.raises(TenantModelNotFoundError) as exc_info:
                manager.load("nonexistent-tenant")

            assert exc_info.value.tenant_id == "nonexistent-tenant"

    def test_load_with_cache_invalidation(self, tmp_path, sample_config):
        """Test that cache invalidation forces a reload from disk."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            # Save and load
            manager.save(tenant_id, sample_config)
            config1 = manager.load(tenant_id)

            # Modify file directly on disk
            config_path = manager.get_config_path(tenant_id)
            modified_config = sample_config.model_copy()
            modified_config.providers[0].api_key = "modified-key"
            config_path.write_text(modified_config.model_dump_json())

            # Invalidate cache and reload
            manager.invalidate_cache(tenant_id)
            config2 = manager.load(tenant_id)

            # Should be different objects
            assert config1 is not config2
            assert config2.providers[0].api_key == "modified-key"


class TestTenantModelManagerInvalidateCache:
    """Tests for invalidate_cache method."""

    def test_invalidate_cache_for_specific_tenant(
        self,
        tmp_path,
        sample_config,
    ):
        """Test invalidating cache for a specific tenant."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()

            manager.save("tenant1", sample_config)
            manager.save("tenant2", sample_config)

            # Load both to cache them
            config1 = manager.load("tenant1")
            config2 = manager.load("tenant2")

            # Invalidate only tenant1
            manager.invalidate_cache("tenant1")

            # tenant1 should be reloaded from disk
            config1_new = manager.load("tenant1")
            # tenant2 should still be cached
            config2_new = manager.load("tenant2")

            assert config1 is not config1_new
            assert config2 is config2_new

    def test_invalidate_cache_for_all_tenants(self, tmp_path, sample_config):
        """Test invalidating cache for all tenants when tenant_id is None."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()

            manager.save("tenant1", sample_config)
            manager.save("tenant2", sample_config)

            # Load both to cache them
            config1 = manager.load("tenant1")
            config2 = manager.load("tenant2")

            # Invalidate all caches
            manager.invalidate_cache()

            # Both should be reloaded from disk
            config1_new = manager.load("tenant1")
            config2_new = manager.load("tenant2")

            assert config1 is not config1_new
            assert config2 is not config2_new

    def test_invalidate_cache_for_nonexistent_tenant(self):
        """Test invalidating cache for a tenant that was never loaded."""
        manager = TenantModelManager()
        # Should not raise an error
        manager.invalidate_cache("nonexistent-tenant")


class TestTenantModelManagerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_load_with_invalid_json(self, tmp_path):
        """Test load handles corrupt JSON file gracefully."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant"

            # Create an invalid JSON file
            config_path = manager.get_config_path(tenant_id)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("not valid json")

            with pytest.raises(
                Exception,
            ):  # Could be JSON decode error or validation error
                manager.load(tenant_id)

    def test_save_with_special_characters_in_tenant_id(
        self,
        tmp_path,
        sample_config,
    ):
        """Test save handles tenant IDs with special characters."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager = TenantModelManager()
            tenant_id = "test-tenant_123"

            manager.save(tenant_id, sample_config)

            assert manager.exists(tenant_id)
            loaded = manager.load(tenant_id)
            assert loaded.providers[0].id == sample_config.providers[0].id

    def test_multiple_managers_share_cache(self, tmp_path, sample_config):
        """Test that cache is shared across manager instances (class-level cache)."""
        with patch("swe.tenant_models.manager.SECRET_DIR", tmp_path):
            manager1 = TenantModelManager()
            manager2 = TenantModelManager()
            tenant_id = "test-tenant"

            # Save with first manager
            manager1.save(tenant_id, sample_config)

            # Load with first manager (will cache)
            config1 = manager1.load(tenant_id)

            # Load with second manager (should use cache)
            config2 = manager2.load(tenant_id)

            # Should be the same cached object
            assert config1 is config2
