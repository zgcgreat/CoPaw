# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,unused-argument,protected-access,wrong-import-position
"""Tests for the Kimi built-in providers."""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

fcntl_stub = types.ModuleType("fcntl")
fcntl_stub.flock = lambda *args, **kwargs: None
fcntl_stub.LOCK_EX = 1
fcntl_stub.LOCK_NB = 2
fcntl_stub.LOCK_UN = 8
sys.modules.setdefault("fcntl", fcntl_stub)

import swe.providers.provider_manager as provider_manager_module
from swe.providers.capability_baseline import ExpectedCapabilityRegistry
from swe.providers.openai_provider import OpenAIProvider
from swe.providers.provider import ModelInfo
from swe.providers.provider_manager import ProviderManager


KIMI_MODEL_IDS = [
    "kimi-k2.5",
    "kimi-k2-0905-preview",
    "kimi-k2-0711-preview",
    "kimi-k2-turbo-preview",
    "kimi-k2-thinking",
    "kimi-k2-thinking-turbo",
]


def _kimi_models() -> list[ModelInfo]:
    """Build Kimi model infos from the current capability baseline."""
    registry = ExpectedCapabilityRegistry()
    capabilities = registry.get_all_for_provider("kimi-cn")
    capability_by_model = {cap.model_id: cap for cap in capabilities}

    return [
        ModelInfo(
            id=model_id,
            name=model_id,
            supports_image=capability_by_model[model_id].expected_image,
            supports_video=capability_by_model[model_id].expected_video,
            probe_source="documentation",
        )
        for model_id in KIMI_MODEL_IDS
    ]


def _make_kimi_provider(provider_id: str) -> OpenAIProvider:
    if provider_id == "kimi-cn":
        return OpenAIProvider(
            id="kimi-cn",
            name="Kimi (China)",
            base_url="https://api.moonshot.cn/v1",
            chat_model="KimiChatModel",
            models=_kimi_models(),
            freeze_url=True,
        )
    return OpenAIProvider(
        id="kimi-intl",
        name="Kimi (International)",
        base_url="https://api.moonshot.ai/v1",
        chat_model="KimiChatModel",
        models=_kimi_models(),
        freeze_url=True,
    )


def test_kimi_providers_are_openai_compatible() -> None:
    """Kimi providers should be OpenAIProvider instances."""
    PROVIDER_KIMI_CN = _make_kimi_provider("kimi-cn")
    PROVIDER_KIMI_INTL = _make_kimi_provider("kimi-intl")

    assert isinstance(PROVIDER_KIMI_CN, OpenAIProvider)
    assert isinstance(PROVIDER_KIMI_INTL, OpenAIProvider)


def test_kimi_provider_configs() -> None:
    """Verify Kimi provider configuration defaults."""
    PROVIDER_KIMI_CN = _make_kimi_provider("kimi-cn")
    PROVIDER_KIMI_INTL = _make_kimi_provider("kimi-intl")

    assert PROVIDER_KIMI_CN.id == "kimi-cn"
    assert PROVIDER_KIMI_CN.name == "Kimi (China)"
    assert PROVIDER_KIMI_CN.base_url == "https://api.moonshot.cn/v1"
    assert PROVIDER_KIMI_CN.chat_model == "KimiChatModel"
    assert PROVIDER_KIMI_CN.freeze_url is True

    assert PROVIDER_KIMI_INTL.id == "kimi-intl"
    assert PROVIDER_KIMI_INTL.name == "Kimi (International)"
    assert PROVIDER_KIMI_INTL.base_url == "https://api.moonshot.ai/v1"
    assert PROVIDER_KIMI_INTL.chat_model == "KimiChatModel"
    assert PROVIDER_KIMI_INTL.freeze_url is True


def test_kimi_models_list() -> None:
    """Verify Kimi model definitions."""
    model_ids = [m.id for m in _kimi_models()]

    assert model_ids == KIMI_MODEL_IDS


@pytest.fixture
def isolated_secret_dir(monkeypatch, tmp_path):
    secret_dir = tmp_path / ".swe.secret"
    monkeypatch.setattr(provider_manager_module, "SECRET_DIR", secret_dir)
    return secret_dir


def test_kimi_payloads_can_be_managed_by_provider_manager(
    isolated_secret_dir,
) -> None:
    """Kimi provider payloads should be usable by ProviderManager."""
    manager = ProviderManager()
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-cn").model_dump(),
    )
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-intl").model_dump(),
    )

    provider_cn = manager.get_provider("kimi-cn")
    assert provider_cn is not None
    assert isinstance(provider_cn, OpenAIProvider)
    assert provider_cn.base_url == "https://api.moonshot.cn/v1"

    provider_intl = manager.get_provider("kimi-intl")
    assert provider_intl is not None
    assert isinstance(provider_intl, OpenAIProvider)
    assert provider_intl.base_url == "https://api.moonshot.ai/v1"


async def test_kimi_check_connection_success(monkeypatch) -> None:
    """Kimi check_connection should delegate to OpenAI client."""
    provider = OpenAIProvider(
        id="kimi-cn",
        name="Kimi (China)",
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
    )

    class FakeModels:
        async def list(self, timeout=None):
            return SimpleNamespace(data=[])

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, msg = await provider.check_connection(timeout=2)

    assert ok is True
    assert msg == ""


def test_kimi_has_expected_models(isolated_secret_dir) -> None:
    """Provider manager Kimi providers should include all built-in models."""
    manager = ProviderManager()
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-cn").model_dump(),
    )
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-intl").model_dump(),
    )
    provider_cn = manager.get_provider("kimi-cn")
    provider_intl = manager.get_provider("kimi-intl")

    assert provider_cn is not None
    assert provider_intl is not None

    for model_id in [
        "kimi-k2.5",
        "kimi-k2-0905-preview",
        "kimi-k2-0711-preview",
        "kimi-k2-turbo-preview",
        "kimi-k2-thinking",
        "kimi-k2-thinking-turbo",
    ]:
        assert provider_cn.has_model(model_id)
        assert provider_intl.has_model(model_id)


async def test_kimi_activate_models(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    """Should be able to activate both Kimi providers."""
    manager = ProviderManager()
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-cn").model_dump(),
    )
    manager.overwrite_provider_payload(
        _make_kimi_provider("kimi-intl").model_dump(),
    )

    await manager.activate_model("kimi-cn", "kimi-k2.5")
    assert manager.active_model is not None
    assert manager.active_model.provider_id == "kimi-cn"
    assert manager.active_model.model == "kimi-k2.5"

    await manager.activate_model("kimi-intl", "kimi-k2-thinking")
    assert manager.active_model is not None
    assert manager.active_model.provider_id == "kimi-intl"
    assert manager.active_model.model == "kimi-k2-thinking"
