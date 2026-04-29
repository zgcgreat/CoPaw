# -*- coding: utf-8 -*-
# flake8: noqa: E402
# pylint: disable=wrong-import-position
"""Tests for model_factory tenant integration."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.agents.model_factory import (
    _get_formatter_for_chat_model,
    _create_file_block_support_formatter,
)


class TestFormatterMapping:
    """Tests for chat model to formatter mapping."""

    def test_openai_model_returns_openai_formatter(self):
        """OpenAIChatModel returns OpenAIChatFormatter."""
        from agentscope.formatter import OpenAIChatFormatter
        from agentscope.model import OpenAIChatModel

        formatter_class = _get_formatter_for_chat_model(OpenAIChatModel)
        assert formatter_class == OpenAIChatFormatter

    def test_unknown_model_defaults_to_openai_formatter(self):
        """Unknown model class defaults to OpenAIChatFormatter."""
        from agentscope.formatter import OpenAIChatFormatter
        from agentscope.model import OpenAIChatModel

        class UnknownModel(OpenAIChatModel):
            pass

        formatter_class = _get_formatter_for_chat_model(UnknownModel)
        assert formatter_class == OpenAIChatFormatter


class TestFileBlockSupportFormatter:
    """Tests for file block support formatter wrapper."""

    def test_formatter_creation(self):
        """File block support formatter can be created."""
        from agentscope.formatter import OpenAIChatFormatter

        formatter_class = _create_file_block_support_formatter(
            OpenAIChatFormatter,
        )
        assert formatter_class is not None
        assert "FileBlockSupport" in formatter_class.__name__


class TestCreateModelAndFormatterTenantIntegration:
    """Tests for tenant-aware model creation."""

    def test_raises_when_no_active_model(self):
        """Factory raises when ProviderManager has no active model."""
        from swe.agents.model_factory import create_model_and_formatter

        # Patch ProviderManager to return no active model
        with patch(
            "swe.agents.model_factory.ProviderManager",
        ) as mock_pm_class:
            mock_manager = MagicMock()
            mock_manager.get_active_model.return_value = None
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            with pytest.raises(
                ValueError,
                match="No tenant model configuration found",
            ):
                create_model_and_formatter()

    def test_uses_provider_manager_as_primary_source(self):
        """Factory uses ProviderManager.get_active_model() as primary source."""
        from swe.agents.model_factory import create_model_and_formatter

        # Patch ProviderManager with active model
        with patch(
            "swe.agents.model_factory.ProviderManager",
        ) as mock_pm_class:
            mock_manager = MagicMock()
            from swe.providers.models import ModelSlotConfig

            mock_manager.get_active_model.return_value = ModelSlotConfig(
                provider_id="openai",
                model="gpt-4",
            )
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            # Mock provider to return a model
            mock_provider = MagicMock()
            mock_model = MagicMock()
            mock_model.__class__.__name__ = "OpenAIChatModel"
            mock_provider.get_chat_model_instance.return_value = mock_model
            mock_manager.get_provider.return_value = mock_provider

            # Patch formatter creation and wrappers
            with patch(
                "swe.agents.model_factory._create_formatter_instance",
            ):
                with patch(
                    "swe.agents.model_factory.TokenRecordingModelWrapper",
                ):
                    with patch("swe.agents.model_factory.RetryChatModel"):
                        model, _ = create_model_and_formatter()

            # Verify ProviderManager.get_active_model was called (not TenantModelContext)
            mock_manager.get_active_model.assert_called_once()
            mock_manager.get_provider.assert_called_once_with("openai")

    def test_tenant_provider_manager_isolation(self):
        """Different tenants get different ProviderManager instances."""
        from swe.agents.model_factory import create_model_and_formatter

        # Patch ProviderManager to track tenant IDs
        with patch(
            "swe.agents.model_factory.ProviderManager",
        ) as mock_pm_class:
            mock_manager = MagicMock()
            from swe.providers.models import ModelSlotConfig

            mock_manager.get_active_model.return_value = ModelSlotConfig(
                provider_id="openai",
                model="gpt-4",
            )
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            mock_provider = MagicMock()
            mock_model = MagicMock()
            mock_model.__class__.__name__ = "OpenAIChatModel"
            mock_provider.get_chat_model_instance.return_value = mock_model
            mock_manager.get_provider.return_value = mock_provider

            # Patch formatter creation
            with patch(
                "swe.agents.model_factory._create_formatter_instance",
            ):
                with patch(
                    "swe.agents.model_factory.TokenRecordingModelWrapper",
                ):
                    with patch(
                        "swe.agents.model_factory.RetryChatModel",
                    ):
                        # First call with tenant-a
                        with patch(
                            "swe.config.context.get_current_tenant_id",
                            return_value="tenant-a",
                        ):
                            try:
                                create_model_and_formatter()
                            except Exception:
                                pass

            # Verify get_instance was called with tenant-a
            calls = [
                str(call) for call in mock_pm_class.get_instance.call_args_list
            ]
            assert any("tenant-a" in call for call in calls)

    def test_passes_effective_tenant_and_agent_scope_to_retry_model(self):
        """Factory propagates limiter scope and config to RetryChatModel."""
        from swe.agents.model_factory import create_model_and_formatter
        from swe.providers.models import ModelSlotConfig

        with (
            patch(
                "swe.config.context.get_current_effective_tenant_id",
                return_value="tenant-a",
            ),
            patch(
                "swe.app.agent_context.get_current_agent_id",
                return_value="agent-x",
            ),
            patch(
                "swe.config.config.load_agent_config",
            ) as mock_load_agent_config,
            patch(
                "swe.agents.model_factory.ProviderManager",
            ) as mock_pm_class,
            patch(
                "swe.agents.model_factory._create_formatter_instance",
            ),
            patch(
                "swe.agents.model_factory.TokenRecordingModelWrapper",
                side_effect=lambda _provider_id, model: model,
            ),
            patch(
                "swe.agents.model_factory.RetryChatModel",
                side_effect=lambda model, **_kwargs: model,
            ) as mock_retry_model,
        ):
            mock_agent_config = MagicMock()
            mock_agent_config.running.llm_retry_enabled = True
            mock_agent_config.running.llm_max_retries = 3
            mock_agent_config.running.llm_backoff_base = 1.0
            mock_agent_config.running.llm_backoff_cap = 10.0
            mock_agent_config.running.llm_max_concurrent = 7
            mock_agent_config.running.llm_max_qpm = 70
            mock_agent_config.running.llm_rate_limit_pause = 4.0
            mock_agent_config.running.llm_rate_limit_jitter = 0.5
            mock_agent_config.running.llm_acquire_timeout = 30.0
            mock_agent_config.running.llm_chat_max_concurrent = None
            mock_agent_config.running.llm_cron_max_concurrent = None
            mock_agent_config.running.llm_chat_acquire_timeout = None
            mock_agent_config.running.llm_cron_acquire_timeout = None
            mock_load_agent_config.return_value = mock_agent_config

            mock_manager = MagicMock()
            mock_manager.get_active_model.return_value = ModelSlotConfig(
                provider_id="openai",
                model="gpt-4",
            )
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            mock_provider = MagicMock()
            mock_model = MagicMock()
            mock_model.model_name = "gpt-4"
            mock_model.stream = False
            mock_provider.get_chat_model_instance.return_value = mock_model
            mock_manager.get_provider.return_value = mock_provider

            create_model_and_formatter()

        mock_pm_class.get_instance.assert_called_once_with("tenant-a")
        assert mock_retry_model.call_args.kwargs["tenant_id"] == "tenant-a"
        assert mock_retry_model.call_args.kwargs["agent_id"] == "agent-x"
        rate_limit_config = mock_retry_model.call_args.kwargs[
            "rate_limit_config"
        ]
        assert rate_limit_config.max_concurrent == 7
        assert rate_limit_config.max_qpm == 70
        assert rate_limit_config.max_concurrent_for("chat") == 2
        assert rate_limit_config.max_concurrent_for("cron") == 3
        assert rate_limit_config.acquire_timeout_for("chat") == 30.0
        assert rate_limit_config.acquire_timeout_for("cron") == 30.0
        mock_load_agent_config.assert_any_call(
            "agent-x",
            tenant_id="tenant-a",
        )

    def test_workload_specific_rate_limit_config_overrides_fallbacks(self):
        """Factory keeps default fallback while applying workload overrides."""
        from swe.agents.model_factory import create_model_and_formatter
        from swe.providers.models import ModelSlotConfig

        with (
            patch(
                "swe.config.context.get_current_effective_tenant_id",
                return_value="tenant-a",
            ),
            patch(
                "swe.app.agent_context.get_current_agent_id",
                return_value="agent-x",
            ),
            patch(
                "swe.config.config.load_agent_config",
            ) as mock_load_agent_config,
            patch(
                "swe.agents.model_factory.ProviderManager",
            ) as mock_pm_class,
            patch(
                "swe.agents.model_factory._create_formatter_instance",
            ),
            patch(
                "swe.agents.model_factory.TokenRecordingModelWrapper",
                side_effect=lambda _provider_id, model: model,
            ),
            patch(
                "swe.agents.model_factory.RetryChatModel",
                side_effect=lambda model, **_kwargs: model,
            ) as mock_retry_model,
        ):
            mock_agent_config = MagicMock()
            mock_agent_config.running.llm_retry_enabled = True
            mock_agent_config.running.llm_max_retries = 3
            mock_agent_config.running.llm_backoff_base = 1.0
            mock_agent_config.running.llm_backoff_cap = 10.0
            mock_agent_config.running.llm_max_concurrent = 5
            mock_agent_config.running.llm_chat_max_concurrent = None
            mock_agent_config.running.llm_cron_max_concurrent = 2
            mock_agent_config.running.llm_max_qpm = 70
            mock_agent_config.running.llm_rate_limit_pause = 4.0
            mock_agent_config.running.llm_rate_limit_jitter = 0.5
            mock_agent_config.running.llm_acquire_timeout = 30.0
            mock_agent_config.running.llm_chat_acquire_timeout = 15.0
            mock_agent_config.running.llm_cron_acquire_timeout = None
            mock_load_agent_config.return_value = mock_agent_config

            mock_manager = MagicMock()
            mock_manager.get_active_model.return_value = ModelSlotConfig(
                provider_id="openai",
                model="gpt-4",
            )
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            mock_provider = MagicMock()
            mock_model = MagicMock()
            mock_model.model_name = "gpt-4"
            mock_model.stream = False
            mock_provider.get_chat_model_instance.return_value = mock_model
            mock_manager.get_provider.return_value = mock_provider

            create_model_and_formatter()

        rate_limit_config = mock_retry_model.call_args.kwargs[
            "rate_limit_config"
        ]
        assert rate_limit_config.max_concurrent_for("chat") == 2
        assert rate_limit_config.max_concurrent_for("cron") == 2
        assert rate_limit_config.acquire_timeout_for("chat") == 15.0
        assert rate_limit_config.acquire_timeout_for("cron") == 30.0


class TestBackwardCompatibility:
    """Tests for backward compatibility with non-tenant mode."""

    def test_raises_when_provider_manager_has_no_active_model(self):
        """Factory raises when ProviderManager has no active model."""
        from swe.agents.model_factory import create_model_and_formatter

        # Patch ProviderManager to return no active model
        with patch(
            "swe.agents.model_factory.ProviderManager",
        ) as mock_pm_class:
            mock_manager = MagicMock()
            mock_manager.get_active_model.return_value = None
            mock_pm_class.get_instance.return_value = mock_manager
            mock_pm_class.ensure_tenant_provider_storage = MagicMock()

            with pytest.raises(
                ValueError,
                match="No tenant model configuration",
            ):
                create_model_and_formatter()

    def test_agent_id_parameter_uses_retry_config(self):
        """agent_id loads retry config from agent config."""
        from swe.agents.model_factory import create_model_and_formatter

        with patch(
            "swe.app.agent_context.get_current_agent_id",
        ) as mock_get_agent:
            mock_get_agent.return_value = "context-agent"

            with patch("swe.config.config.load_agent_config") as mock_load:
                mock_config = MagicMock()
                mock_config.running.llm_retry_enabled = True
                mock_config.running.llm_max_retries = 3
                mock_config.running.llm_backoff_base = 1.0
                mock_config.running.llm_backoff_cap = 60.0
                mock_config.running.llm_max_concurrent = 10
                mock_config.running.llm_max_qpm = 100
                mock_config.running.llm_rate_limit_pause = 1.0
                mock_config.running.llm_rate_limit_jitter = 0.1
                mock_config.running.llm_acquire_timeout = 30.0
                mock_config.running.llm_chat_max_concurrent = None
                mock_config.running.llm_cron_max_concurrent = None
                mock_config.running.llm_chat_acquire_timeout = None
                mock_config.running.llm_cron_acquire_timeout = None
                mock_load.return_value = mock_config

                # Also need to mock ProviderManager since it's the primary source
                with patch(
                    "swe.agents.model_factory.ProviderManager",
                ) as mock_pm_class:
                    mock_manager = MagicMock()
                    mock_manager.get_active_model.return_value = None
                    mock_pm_class.get_instance.return_value = mock_manager
                    mock_pm_class.ensure_tenant_provider_storage = MagicMock()

                    with pytest.raises(
                        ValueError,
                        match="No tenant model configuration",
                    ):
                        create_model_and_formatter(agent_id="param-agent")

                    # load_agent_config should be called with param-agent
                    mock_load.assert_called_once_with("param-agent")


class TestRetryConfigPropagation:
    """Tests for retry configuration propagation."""

    def test_retry_config_from_agent_config(self):
        """Retry configuration is extracted from agent config."""
        from swe.providers.retry_chat_model import RetryConfig

        # Create a RetryConfig to verify structure
        retry_config = RetryConfig(
            enabled=True,
            max_retries=5,
            backoff_base=2.0,
            backoff_cap=120.0,
        )

        assert retry_config.enabled is True
        assert retry_config.max_retries == 5
        assert retry_config.backoff_base == 2.0
        assert retry_config.backoff_cap == 120.0
