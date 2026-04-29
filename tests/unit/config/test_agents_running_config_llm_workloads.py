# -*- coding: utf-8 -*-
"""Tests for workload-specific LLM runtime config fields."""

import pytest
from pydantic import ValidationError

from swe.config.config import AgentsRunningConfig


def test_workload_specific_llm_config_fields_use_defaults() -> None:
    config = AgentsRunningConfig()

    assert config.llm_chat_max_concurrent == 2
    assert config.llm_cron_max_concurrent == 3
    assert config.llm_chat_acquire_timeout is None
    assert config.llm_cron_acquire_timeout is None


def test_workload_specific_llm_config_coerces_none_to_defaults() -> None:
    config = AgentsRunningConfig(
        llm_chat_max_concurrent=None,
        llm_cron_max_concurrent=None,
    )

    assert config.llm_chat_max_concurrent == 2
    assert config.llm_cron_max_concurrent == 3


def test_workload_specific_llm_config_fields_accept_overrides() -> None:
    config = AgentsRunningConfig(
        llm_rate_limit_pause=5.0,
        llm_rate_limit_jitter=1.0,
        llm_chat_max_concurrent=4,
        llm_cron_max_concurrent=2,
        llm_chat_acquire_timeout=20.0,
        llm_cron_acquire_timeout=120.0,
    )

    assert config.llm_chat_max_concurrent == 4
    assert config.llm_cron_max_concurrent == 2
    assert config.llm_chat_acquire_timeout == 20.0
    assert config.llm_cron_acquire_timeout == 120.0


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("llm_acquire_timeout", 25.0),
        ("llm_chat_acquire_timeout", 25.0),
        ("llm_cron_acquire_timeout", 25.0),
    ],
)
def test_llm_acquire_timeout_must_exceed_pause_plus_jitter(
    field_name: str,
    field_value: float,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        AgentsRunningConfig(
            llm_rate_limit_pause=20.0,
            llm_rate_limit_jitter=5.0,
            **{field_name: field_value},
        )

    assert (
        f"{field_name} must be greater than llm_rate_limit_pause + "
        "llm_rate_limit_jitter"
    ) in str(exc_info.value)
