# -*- coding: utf-8 -*-
"""Tests for LLM workload context binding."""

from swe.config.llm_workload import (
    LLM_WORKLOAD_CHAT,
    LLM_WORKLOAD_CRON,
    bind_llm_workload,
    get_current_llm_workload,
)


def test_llm_workload_defaults_to_chat() -> None:
    assert get_current_llm_workload() == LLM_WORKLOAD_CHAT


def test_llm_workload_binds_and_resets() -> None:
    with bind_llm_workload(LLM_WORKLOAD_CRON):
        assert get_current_llm_workload() == LLM_WORKLOAD_CRON

    assert get_current_llm_workload() == LLM_WORKLOAD_CHAT


def test_nested_llm_workload_binding_restores_previous_value() -> None:
    with bind_llm_workload(LLM_WORKLOAD_CRON):
        with bind_llm_workload(LLM_WORKLOAD_CHAT):
            assert get_current_llm_workload() == LLM_WORKLOAD_CHAT
        assert get_current_llm_workload() == LLM_WORKLOAD_CRON

    assert get_current_llm_workload() == LLM_WORKLOAD_CHAT
