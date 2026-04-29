# -*- coding: utf-8 -*-
"""Tenant env lookup regression tests."""
from swe.config.utils import get_tenant_env


def test_get_tenant_env_reads_from_tenant_secret_file(tmp_path, monkeypatch):
    tenant_secret = tmp_path / "tenant-a" / ".secret"
    tenant_secret.mkdir(parents=True)
    (tenant_secret / "envs.json").write_text(
        '{"API_KEY": "tenant-value"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "swe.config.utils.get_tenant_secrets_dir",
        lambda tenant_id=None: tenant_secret,
    )

    assert get_tenant_env("API_KEY", tenant_id="tenant-a") == "tenant-value"
