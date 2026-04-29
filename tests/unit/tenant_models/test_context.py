# -*- coding: utf-8 -*-
"""Tests for tenant model context management."""

from contextvars import Token

import pytest

from swe.config.context import TenantContextError
from swe.tenant_models.context import TenantModelContext
from swe.tenant_models.models import (
    ModelSlot,
    RoutingConfig,
    TenantModelConfig,
    TenantProviderConfig,
)


@pytest.fixture
def sample_config() -> TenantModelConfig:
    """Create a sample TenantModelConfig for testing."""
    return TenantModelConfig(
        version="1.0",
        providers=[
            TenantProviderConfig(
                id="openai-main",
                type="openai",
                api_key="${ENV:OPENAI_API_KEY}",
                models=["gpt-4", "gpt-3.5-turbo"],
                enabled=True,
            ),
            TenantProviderConfig(
                id="anthropic-main",
                type="anthropic",
                api_key="${ENV:ANTHROPIC_API_KEY}",
                models=["claude-3-opus", "claude-3-sonnet"],
                enabled=True,
            ),
        ],
        routing=RoutingConfig(
            mode="cloud_first",
            slots={
                "local": ModelSlot(
                    provider_id="openai-main",
                    model="gpt-3.5-turbo",
                ),
                "cloud": ModelSlot(
                    provider_id="anthropic-main",
                    model="claude-3-opus",
                ),
            },
        ),
    )


@pytest.fixture
def another_config() -> TenantModelConfig:
    """Create another TenantModelConfig for testing nested contexts."""
    return TenantModelConfig(
        version="1.0",
        providers=[
            TenantProviderConfig(
                id="ollama-local",
                type="ollama",
                base_url="http://localhost:11434",
                models=["llama2", "codellama"],
                enabled=True,
            ),
        ],
        routing=RoutingConfig(
            mode="local_first",
            slots={
                "local": ModelSlot(provider_id="ollama-local", model="llama2"),
                "cloud": ModelSlot(
                    provider_id="ollama-local",
                    model="codellama",
                ),
            },
        ),
    )


class TestTenantModelContext:
    """Test suite for TenantModelContext."""

    def test_get_config_returns_none_when_not_set(self) -> None:
        """Test that get_config returns None when no config is set."""
        # Ensure context is clean
        result = TenantModelContext.get_config()
        assert result is None

    def test_set_and_get_config(
        self,
        sample_config: TenantModelConfig,
    ) -> None:
        """Test setting and getting config."""
        token = TenantModelContext.set_config(sample_config)
        try:
            result = TenantModelContext.get_config()
            assert result is not None
            assert result == sample_config
            assert result.version == "1.0"
            assert len(result.providers) == 2
            assert result.routing.mode == "cloud_first"
        finally:
            TenantModelContext.reset_config(token)

    def test_get_config_strict_raises_when_not_set(self) -> None:
        """Test that get_config_strict raises TenantContextError when config is not set."""
        with pytest.raises(TenantContextError) as exc_info:
            TenantModelContext.get_config_strict()

        assert "TenantModelConfig is not set in context" in str(exc_info.value)

    def test_get_config_strict_returns_config_when_set(
        self,
        sample_config: TenantModelConfig,
    ) -> None:
        """Test that get_config_strict returns config when set."""
        token = TenantModelContext.set_config(sample_config)
        try:
            result = TenantModelContext.get_config_strict()
            assert result == sample_config
        finally:
            TenantModelContext.reset_config(token)

    def test_reset_config_restores_previous_state(
        self,
        sample_config: TenantModelConfig,
    ) -> None:
        """Test that reset_config restores previous state."""
        # Set initial config
        token = TenantModelContext.set_config(sample_config)

        # Verify it's set
        result = TenantModelContext.get_config()
        assert result == sample_config

        # Reset should restore to None (previous state)
        TenantModelContext.reset_config(token)
        result = TenantModelContext.get_config()
        assert result is None

    def test_nested_contexts(
        self,
        sample_config: TenantModelConfig,
        another_config: TenantModelConfig,
    ) -> None:
        """Test that nested contexts work correctly with token-based reset."""
        # Initially, config should be None
        assert TenantModelContext.get_config() is None

        # Set first config
        token1 = TenantModelContext.set_config(sample_config)
        assert TenantModelContext.get_config() == sample_config

        # Set second config (nested)
        token2 = TenantModelContext.set_config(another_config)
        assert TenantModelContext.get_config() == another_config

        # Reset second config
        TenantModelContext.reset_config(token2)
        assert TenantModelContext.get_config() == sample_config

        # Reset first config
        TenantModelContext.reset_config(token1)
        assert TenantModelContext.get_config() is None

    def test_multiple_nested_contexts(
        self,
        sample_config: TenantModelConfig,
        another_config: TenantModelConfig,
    ) -> None:
        """Test multiple levels of nesting."""
        token1 = TenantModelContext.set_config(sample_config)
        assert TenantModelContext.get_config() == sample_config

        token2 = TenantModelContext.set_config(another_config)
        assert TenantModelContext.get_config() == another_config

        token3 = TenantModelContext.set_config(sample_config)
        assert TenantModelContext.get_config() == sample_config

        # Reset in reverse order
        TenantModelContext.reset_config(token3)
        assert TenantModelContext.get_config() == another_config

        TenantModelContext.reset_config(token2)
        assert TenantModelContext.get_config() == sample_config

        TenantModelContext.reset_config(token1)
        assert TenantModelContext.get_config() is None

    def test_set_config_returns_token(
        self,
        sample_config: TenantModelConfig,
    ) -> None:
        """Test that set_config returns a Token object."""
        token = TenantModelContext.set_config(sample_config)
        assert token is not None
        assert isinstance(token, Token)
        TenantModelContext.reset_config(token)

    def test_config_isolation_across_contexts(
        self,
        sample_config: TenantModelConfig,
    ) -> None:
        """Test that config changes in one context don't affect parent context."""
        token1 = TenantModelContext.set_config(sample_config)
        try:
            # Modify the config in nested context
            token2 = TenantModelContext.set_config(
                TenantModelConfig(
                    version="2.0",
                    providers=[],
                    routing=RoutingConfig(
                        mode="local_first",
                        slots={},
                    ),
                ),
            )

            # Should see new config
            result = TenantModelContext.get_config()
            assert result is not None
            assert result.version == "2.0"

            # Reset to parent context
            TenantModelContext.reset_config(token2)

            # Should see original config
            result = TenantModelContext.get_config()
            assert result == sample_config
            assert result.version == "1.0"
        finally:
            TenantModelContext.reset_config(token1)
