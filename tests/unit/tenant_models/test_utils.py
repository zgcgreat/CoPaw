# -*- coding: utf-8 -*-
"""Tests for tenant model utility functions."""

import os
from unittest.mock import patch

import pytest

from swe.tenant_models.utils import resolve_env_vars


class TestResolveEnvVars:
    """Test cases for resolve_env_vars function."""

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        assert resolve_env_vars(None) is None

    def test_no_env_vars_returns_unchanged(self):
        """Test that strings without env vars are returned unchanged."""
        assert resolve_env_vars("simple string") == "simple string"
        assert resolve_env_vars("") == ""
        # These strings don't match the ${ENV:VAR} pattern
        assert resolve_env_vars("${ENV_VAR}") == "${ENV_VAR}"
        assert resolve_env_vars("no env vars here") == "no env vars here"

    def test_single_env_var_present(self):
        """Test resolution of a single existing environment variable."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = resolve_env_vars("${ENV:TEST_VAR}")
            assert result == "test_value"

    def test_single_env_var_missing(self):
        """Test that missing environment variables are replaced with empty string."""
        with patch.dict(os.environ, {}, clear=True):
            # Make sure MISSING_VAR doesn't exist
            os.environ.pop("MISSING_VAR", None)
            result = resolve_env_vars("${ENV:MISSING_VAR}")
            assert result == ""

    def test_env_var_in_middle_of_string(self):
        """Test environment variable in the middle of a string."""
        with patch.dict(os.environ, {"API_KEY": "secret123"}):
            result = resolve_env_vars("prefix_${ENV:API_KEY}_suffix")
            assert result == "prefix_secret123_suffix"

    def test_multiple_env_vars(self):
        """Test multiple environment variables in a string."""
        with patch.dict(os.environ, {"VAR1": "value1", "VAR2": "value2"}):
            result = resolve_env_vars("${ENV:VAR1}_${ENV:VAR2}")
            assert result == "value1_value2"

    def test_multiple_env_vars_mixed_presence(self):
        """Test multiple env vars where some exist and some don't."""
        with patch.dict(os.environ, {"EXISTS": "yes"}, clear=True):
            os.environ.pop("NOT_EXISTS", None)
            result = resolve_env_vars("${ENV:EXISTS}_${ENV:NOT_EXISTS}")
            assert result == "yes_"

    def test_env_var_at_start(self):
        """Test environment variable at the start of a string."""
        with patch.dict(os.environ, {"HOST": "localhost"}):
            result = resolve_env_vars("${ENV:HOST}:8080")
            assert result == "localhost:8080"

    def test_env_var_at_end(self):
        """Test environment variable at the end of a string."""
        with patch.dict(os.environ, {"PORT": "8080"}):
            result = resolve_env_vars("http://localhost:${ENV:PORT}")
            assert result == "http://localhost:8080"

    def test_empty_env_var_name(self):
        """Test handling of empty environment variable name."""
        result = resolve_env_vars("${ENV:}")
        assert result == ""

    def test_malformed_env_var_syntax(self):
        """Test handling of malformed env var syntax."""
        # These should not be recognized as env vars
        assert resolve_env_vars("${ENV_VAR}") == "${ENV_VAR}"
        assert resolve_env_vars("${ENV:VAR") == "${ENV:VAR"
        assert resolve_env_vars("$ENV:VAR}") == "$ENV:VAR}"
        assert resolve_env_vars("${env:VAR}") == "${env:VAR}"

    def test_complex_url_with_env_vars(self):
        """Test complex URL construction with environment variables."""
        with patch.dict(
            os.environ,
            {"API_HOST": "api.example.com", "API_KEY": "abc123"},
        ):
            result = resolve_env_vars(
                "https://${ENV:API_HOST}/v1?key=${ENV:API_KEY}",
            )
            assert result == "https://api.example.com/v1?key=abc123"

    def test_consecutive_env_vars(self):
        """Test consecutive environment variables without separators."""
        with patch.dict(os.environ, {"A": "1", "B": "2", "C": "3"}):
            result = resolve_env_vars("${ENV:A}${ENV:B}${ENV:C}")
            assert result == "123"
