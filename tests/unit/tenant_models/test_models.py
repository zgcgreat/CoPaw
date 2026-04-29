# -*- coding: utf-8 -*-
"""Unit tests for tenant model configuration data models."""

import pytest
from pydantic import ValidationError


class TestTenantProviderConfig:
    """Test cases for TenantProviderConfig."""

    def test_create_minimal_provider_config(self):
        """Test creating a minimal provider configuration."""
        from swe.tenant_models.models import TenantProviderConfig

        config = TenantProviderConfig(
            id="openai-main",
            type="openai",
            models=["gpt-4", "gpt-3.5-turbo"],
        )

        assert config.id == "openai-main"
        assert config.type == "openai"
        assert config.models == ["gpt-4", "gpt-3.5-turbo"]
        assert config.enabled is True
        assert config.api_key is None
        assert config.base_url is None
        assert config.extra == {}

    def test_create_full_provider_config(self):
        """Test creating a provider with all fields."""
        from swe.tenant_models.models import TenantProviderConfig

        config = TenantProviderConfig(
            id="anthropic-main",
            type="anthropic",
            api_key="${ENV:ANTHROPIC_API_KEY}",
            base_url="https://api.anthropic.com",
            models=["claude-3-opus", "claude-3-sonnet"],
            enabled=False,
            extra={"timeout": 30, "max_retries": 3},
        )

        assert config.id == "anthropic-main"
        assert config.type == "anthropic"
        assert config.api_key == "${ENV:ANTHROPIC_API_KEY}"
        assert config.base_url == "https://api.anthropic.com"
        assert config.models == ["claude-3-opus", "claude-3-sonnet"]
        assert config.enabled is False
        assert config.extra == {"timeout": 30, "max_retries": 3}

    def test_provider_type_must_be_valid(self):
        """Test that provider type must be one of the allowed values."""
        from swe.tenant_models.models import TenantProviderConfig

        with pytest.raises(ValidationError) as exc_info:
            TenantProviderConfig(
                id="invalid-provider",
                type="invalid_type",  # type: ignore
                models=["model-1"],
            )

        assert "literal_error" in str(exc_info.value).lower()

    def test_provider_models_can_be_empty(self):
        """Test that models list can be empty."""
        from swe.tenant_models.models import TenantProviderConfig

        # Empty models list should be allowed
        config = TenantProviderConfig(
            id="empty-models",
            type="openai",
            models=[],
        )
        assert config.models == []


class TestModelSlot:
    """Test cases for ModelSlot."""

    def test_create_model_slot(self):
        """Test creating a model slot."""
        from swe.tenant_models.models import ModelSlot

        slot = ModelSlot(
            provider_id="openai-main",
            model="gpt-4",
        )

        assert slot.provider_id == "openai-main"
        assert slot.model == "gpt-4"


class TestRoutingConfig:
    """Test cases for RoutingConfig."""

    def test_create_routing_config(self):
        """Test creating a routing configuration."""
        from swe.tenant_models.models import ModelSlot, RoutingConfig

        routing = RoutingConfig(
            mode="local_first",
            slots={
                "local": ModelSlot(provider_id="ollama-local", model="llama2"),
                "cloud": ModelSlot(provider_id="openai-main", model="gpt-4"),
            },
        )

        assert routing.mode == "local_first"
        assert routing.slots["local"].provider_id == "ollama-local"
        assert routing.slots["cloud"].provider_id == "openai-main"

    def test_routing_mode_must_be_valid(self):
        """Test that routing mode must be one of the allowed values."""
        from swe.tenant_models.models import RoutingConfig

        with pytest.raises(ValidationError) as exc_info:
            RoutingConfig(
                mode="invalid_mode",  # type: ignore
                slots={},
            )

        assert "literal_error" in str(exc_info.value).lower()


class TestTenantModelConfig:
    """Test cases for TenantModelConfig."""

    def test_create_tenant_model_config(self):
        """Test creating a complete tenant model configuration."""
        from swe.tenant_models.models import (
            ModelSlot,
            RoutingConfig,
            TenantModelConfig,
            TenantProviderConfig,
        )

        config = TenantModelConfig(
            providers=[
                TenantProviderConfig(
                    id="ollama-local",
                    type="ollama",
                    models=["llama2", "codellama"],
                ),
                TenantProviderConfig(
                    id="openai-cloud",
                    type="openai",
                    api_key="${ENV:OPENAI_API_KEY}",
                    models=["gpt-4", "gpt-3.5-turbo"],
                ),
            ],
            routing=RoutingConfig(
                mode="local_first",
                slots={
                    "local": ModelSlot(
                        provider_id="ollama-local",
                        model="llama2",
                    ),
                    "cloud": ModelSlot(
                        provider_id="openai-cloud",
                        model="gpt-4",
                    ),
                },
            ),
        )

        assert config.version == "1.0"
        assert len(config.providers) == 2
        assert config.routing.mode == "local_first"

    def test_get_active_slot(self):
        """Test getting the active slot from routing configuration."""
        from swe.tenant_models.models import (
            ModelSlot,
            RoutingConfig,
            TenantModelConfig,
            TenantProviderConfig,
        )

        config = TenantModelConfig(
            providers=[
                TenantProviderConfig(
                    id="provider-1",
                    type="openai",
                    models=["gpt-4"],
                ),
                TenantProviderConfig(
                    id="provider-2",
                    type="anthropic",
                    models=["claude-3-opus"],
                ),
            ],
            routing=RoutingConfig(
                mode="local_first",
                slots={
                    "local": ModelSlot(
                        provider_id="provider-1",
                        model="gpt-4",
                    ),
                    "cloud": ModelSlot(
                        provider_id="provider-2",
                        model="claude-3-opus",
                    ),
                },
            ),
        )

        active_slot = config.get_active_slot()
        assert active_slot.provider_id == "provider-1"
        assert active_slot.model == "gpt-4"

    def test_get_other_slot(self):
        """Test getting the other (fallback) slot from routing configuration."""
        from swe.tenant_models.models import (
            ModelSlot,
            RoutingConfig,
            TenantModelConfig,
            TenantProviderConfig,
        )

        config = TenantModelConfig(
            providers=[
                TenantProviderConfig(
                    id="provider-1",
                    type="openai",
                    models=["gpt-4"],
                ),
                TenantProviderConfig(
                    id="provider-2",
                    type="anthropic",
                    models=["claude-3-opus"],
                ),
            ],
            routing=RoutingConfig(
                mode="local_first",
                slots={
                    "local": ModelSlot(
                        provider_id="provider-1",
                        model="gpt-4",
                    ),
                    "cloud": ModelSlot(
                        provider_id="provider-2",
                        model="claude-3-opus",
                    ),
                },
            ),
        )

        other_slot = config.get_other_slot()
        assert other_slot.provider_id == "provider-2"
        assert other_slot.model == "claude-3-opus"

    def test_custom_version(self):
        """Test creating a config with a custom version."""
        from swe.tenant_models.models import (
            RoutingConfig,
            TenantModelConfig,
            TenantProviderConfig,
        )

        config = TenantModelConfig(
            version="2.0",
            providers=[
                TenantProviderConfig(
                    id="test-provider",
                    type="openai",
                    models=["gpt-4"],
                ),
            ],
            routing=RoutingConfig(
                mode="cloud_first",
                slots={},
            ),
        )

        assert config.version == "2.0"

    def test_serialization(self):
        """Test that config can be serialized to dict/JSON."""
        from swe.tenant_models.models import (
            ModelSlot,
            RoutingConfig,
            TenantModelConfig,
            TenantProviderConfig,
        )

        config = TenantModelConfig(
            providers=[
                TenantProviderConfig(
                    id="openai-main",
                    type="openai",
                    api_key="${ENV:OPENAI_API_KEY}",
                    models=["gpt-4"],
                ),
            ],
            routing=RoutingConfig(
                mode="local_first",
                slots={
                    "active": ModelSlot(
                        provider_id="openai-main",
                        model="gpt-4",
                    ),
                },
            ),
        )

        # Test model_dump (Pydantic v2)
        config_dict = config.model_dump()
        assert "version" in config_dict
        assert "providers" in config_dict
        assert "routing" in config_dict

        # Test model_dump_json
        config_json = config.model_dump_json()
        assert isinstance(config_json, str)
        assert "openai-main" in config_json

    def test_deserialization(self):
        """Test that config can be deserialized from dict."""
        from swe.tenant_models.models import TenantModelConfig

        config_dict = {
            "version": "1.0",
            "providers": [
                {
                    "id": "openai-main",
                    "type": "openai",
                    "api_key": "${ENV:OPENAI_API_KEY}",
                    "models": ["gpt-4"],
                    "enabled": True,
                    "extra": {},
                },
            ],
            "routing": {
                "mode": "local_first",
                "slots": {
                    "local": {
                        "provider_id": "openai-main",
                        "model": "gpt-4",
                    },
                },
            },
        }

        config = TenantModelConfig(**config_dict)
        assert config.version == "1.0"
        assert config.providers[0].id == "openai-main"
        assert config.routing.mode == "local_first"
        assert config.routing.slots["local"].model == "gpt-4"
