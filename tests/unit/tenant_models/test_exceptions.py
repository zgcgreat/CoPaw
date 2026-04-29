# -*- coding: utf-8 -*-
"""Tests for tenant_models exception classes."""


def test_tenant_model_error_base_class():
    """Test TenantModelError base class."""
    from swe.tenant_models.exceptions import TenantModelError

    error = TenantModelError("Base error message")
    assert isinstance(error, RuntimeError)
    assert str(error) == "Base error message"


def test_tenant_model_not_found_error():
    """Test TenantModelNotFoundError with tenant_id attribute."""
    from swe.tenant_models.exceptions import TenantModelNotFoundError

    error = TenantModelNotFoundError("tenant1")
    assert str(error) == "Tenant model config not found for tenant: tenant1"
    assert error.tenant_id == "tenant1"


def test_tenant_model_provider_error():
    """Test TenantModelProviderError with provider_id attribute."""
    from swe.tenant_models.exceptions import TenantModelProviderError

    error = TenantModelProviderError("provider1", "API key missing")
    assert "provider1" in str(error)
    assert "API key missing" in str(error)
    assert error.provider_id == "provider1"


def test_tenant_model_validation_error():
    """Test TenantModelValidationError for config validation failures."""
    from swe.tenant_models.exceptions import (
        TenantModelError,
        TenantModelValidationError,
    )

    error = TenantModelValidationError(
        "Invalid configuration: missing required field",
    )
    assert isinstance(error, TenantModelError)
    assert "Invalid configuration" in str(error)
