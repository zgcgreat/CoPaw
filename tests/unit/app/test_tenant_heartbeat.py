# -*- coding: utf-8 -*-
"""Tenant-bound heartbeat path tests."""
import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
_HEARTBEAT_FILE = SRC_ROOT / "swe" / "app" / "crons" / "heartbeat.py"

_ORIGINAL_MODULES = {
    name: sys.modules.get(name)
    for name in [
        "swe.app",
        "swe.app.crons",
        "swe.agents.utils.file_handling",
        "swe.config",
        "swe.constant",
        "swe.app.crons.models",
        "swe.app.crons.heartbeat",
    ]
}

if "swe.app" not in sys.modules:
    app_pkg = types.ModuleType("swe.app")
    app_pkg.__path__ = [str(SRC_ROOT / "swe" / "app")]
    sys.modules["swe.app"] = app_pkg

if "swe.app.crons" not in sys.modules:
    crons_pkg = types.ModuleType("swe.app.crons")
    crons_pkg.__path__ = [str(SRC_ROOT / "swe" / "app" / "crons")]
    sys.modules["swe.app.crons"] = crons_pkg

file_handling = types.ModuleType("swe.agents.utils.file_handling")
file_handling.read_text_file_with_encoding_fallback = lambda path: ""
sys.modules["swe.agents.utils.file_handling"] = file_handling

config_module = types.ModuleType("swe.config")
config_module.get_heartbeat_config = (
    lambda agent_id=None: types.SimpleNamespace(
        active_hours=None,
        target="main",
    )
)
config_module.get_heartbeat_query_path = lambda: Path("/global/HEARTBEAT.md")
config_module.load_config = lambda: types.SimpleNamespace(
    user_timezone="UTC",
    last_dispatch=None,
)
sys.modules["swe.config"] = config_module

constant_module = types.ModuleType("swe.constant")
constant_module.HEARTBEAT_FILE = "HEARTBEAT.md"
constant_module.HEARTBEAT_TARGET_LAST = "last"
sys.modules["swe.constant"] = constant_module

models_module = types.ModuleType("swe.app.crons.models")
models_module._crontab_dow_to_name = lambda value: value
sys.modules["swe.app.crons.models"] = models_module

heartbeat_spec = importlib.util.spec_from_file_location(
    "swe.app.crons.heartbeat",
    _HEARTBEAT_FILE,
)
assert heartbeat_spec is not None and heartbeat_spec.loader is not None
heartbeat_module = importlib.util.module_from_spec(heartbeat_spec)
sys.modules["swe.app.crons.heartbeat"] = heartbeat_module
heartbeat_spec.loader.exec_module(heartbeat_module)

for _name, _module in _ORIGINAL_MODULES.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


def test_run_heartbeat_uses_workspace_dir_when_provided(tmp_path):
    workspace_dir = tmp_path / "tenant-a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "HEARTBEAT.md").write_text("ping", encoding="utf-8")

    path = heartbeat_module.resolve_heartbeat_path(workspace_dir=workspace_dir)

    assert path == workspace_dir / "HEARTBEAT.md"


def test_tenant_b_heartbeat_does_not_read_tenant_a_file(tmp_path):
    tenant_a = tmp_path / "tenant-a"
    tenant_b = tmp_path / "tenant-b"
    tenant_a.mkdir(parents=True)
    tenant_b.mkdir(parents=True)
    (tenant_a / "HEARTBEAT.md").write_text("tenant-a", encoding="utf-8")
    (tenant_b / "HEARTBEAT.md").write_text("tenant-b", encoding="utf-8")

    assert (
        heartbeat_module.resolve_heartbeat_path(
            workspace_dir=tenant_b,
        )
        == tenant_b / "HEARTBEAT.md"
    )
