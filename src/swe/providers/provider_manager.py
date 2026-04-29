# -*- coding: utf-8 -*-
"""A Manager class to handle all providers, including built-in and custom ones.
It provides a unified interface to manage providers, such as listing available
providers, adding/removing custom providers, and fetching provider details."""

import asyncio
import json
import logging
import os
import shutil
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover (Windows)
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover (Unix)
    msvcrt = None
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

from agentscope.model import ChatModelBase

from swe.providers.provider import (
    ModelInfo,
    Provider,
    ProviderInfo,
)
from swe.providers.models import ModelSlotConfig
from swe.providers.openai_provider import OpenAIProvider
from swe.providers.anthropic_provider import AnthropicProvider

# from swe.providers.gemini_provider import GeminiProvider
from swe.providers.ollama_provider import OllamaProvider
from swe.constant import SECRET_DIR


logger = logging.getLogger(__name__)

if fcntl is None and msvcrt is None:  # pragma: no cover
    raise ImportError(
        "No file locking module available (need fcntl or msvcrt)",
    )


def _try_lock_file(file_obj) -> None:
    """Acquire a non-blocking exclusive lock for the lock file."""
    if fcntl is not None:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return

    if msvcrt is None:  # pragma: no cover
        raise RuntimeError("No supported file locking backend available")

    file_obj.seek(0)
    file_obj.write("0")
    file_obj.flush()
    file_obj.seek(0)
    msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)


def _unlock_file(file_obj) -> None:
    """Release the lock acquired by _try_lock_file."""
    if fcntl is not None:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
        return

    if msvcrt is None:  # pragma: no cover
        raise RuntimeError("No supported file locking backend available")

    file_obj.seek(0)
    msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)


# -------------------------------------------------------
# Built-in provider definitions and their default models.
# -------------------------------------------------------


class ActiveModelsInfo(BaseModel):
    active_llm: ModelSlotConfig | None


class ProviderManager:
    """A manager class to handle all providers,
    including built-in and custom ones."""

    _instance = None
    _instances: dict[str, "ProviderManager"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, tenant_id: str = "default") -> None:
        """Initialize provider manager for a specific tenant.

        Args:
            tenant_id: The tenant ID for isolated storage. Defaults to "default".
        """
        # Initialize provider manager, load providers from registry and store
        # any necessary state (e.g., cached models).
        self.tenant_id = tenant_id
        self.builtin_providers: Dict[str, Provider] = {}
        self.custom_providers: Dict[str, Provider] = {}
        self.active_model: ModelSlotConfig | None = None
        self._file_mtimes: dict[str, float] = {}
        self.root_path = self._get_tenant_root_path(tenant_id)
        self.builtin_path = self.root_path / "builtin"
        self.custom_path = self.root_path / "custom"
        self._prepare_disk_storage()
        self._init_builtins()
        try:
            self._migrate_legacy_providers()
        except Exception as e:
            logger.warning("Failed to migrate legacy providers: %s", e)
        self._init_from_storage()
        self._apply_default_annotations()
        self._record_mtimes()

    @staticmethod
    def _get_tenant_root_path(tenant_id: str) -> Path:
        """Get the root path for a tenant's provider configuration.

        Args:
            tenant_id: The tenant ID.

        Returns:
            Path to the tenant's provider configuration directory.
        """
        return SECRET_DIR / tenant_id / "providers"

    @staticmethod
    def _do_initialize_provider_storage(
        tenant_id: str,
        tenant_providers_dir: Path,
    ) -> None:
        """Initialize provider storage for a tenant.

        Copies from the appropriate default_{source} template if available.
        If the source-specific template doesn't exist, automatically creates
        it from the default tenant, then copies to the tenant directory.

        When tenant_id is "default" and source_id is set, the dynamic
        template creation may create the target directory directly (since
        template dir == target dir), so no additional copy is needed.

        Args:
            tenant_id: The effective tenant ID.
            tenant_providers_dir: Target directory for provider storage.
        """
        from ..config.context import get_current_source_id

        source_id = get_current_source_id()
        source_dir = None
        template_name = "default"

        # Try source-specific template first
        if source_id:
            candidate = SECRET_DIR / f"default_{source_id}" / "providers"
            if candidate.exists() and any(candidate.iterdir()):
                source_dir = candidate
                template_name = f"default_{source_id}"
            else:
                # Dynamic creation: create source template from default
                ProviderManager._ensure_source_template_providers(
                    SECRET_DIR,
                    source_id,
                )
                # Re-check after creation
                if candidate.exists() and any(candidate.iterdir()):
                    source_dir = candidate
                    template_name = f"default_{source_id}"

        # After dynamic creation, target might already exist
        # (when effective_tenant_id matches template_name, e.g., default + ruice)
        if tenant_providers_dir.exists():
            logger.info(
                "Provider config for tenant %s already exists, skipping copy",
                tenant_id,
            )
            return

        # Fall back to generic default
        if source_dir is None:
            default_dir = SECRET_DIR / "default" / "providers"
            if default_dir.exists() and any(default_dir.iterdir()):
                source_dir = default_dir

        if source_dir is not None:
            logger.info(
                "Initializing provider config for tenant %s from %s",
                tenant_id,
                template_name,
            )
            shutil.copytree(source_dir, tenant_providers_dir)
            logger.info("Provider config initialized for tenant %s", tenant_id)
        else:
            logger.info(
                "Creating empty provider config structure for tenant %s",
                tenant_id,
            )
            tenant_providers_dir.mkdir(parents=True, exist_ok=True)
            (tenant_providers_dir / "builtin").mkdir(exist_ok=True)
            (tenant_providers_dir / "custom").mkdir(exist_ok=True)

    @staticmethod
    def _ensure_source_template_providers(
        secret_dir: Path,
        source_id: str,
    ) -> None:
        """Ensure source-specific providers template exists.

        Creates default_{source_id}/providers from default/providers
        if the source template doesn't exist.

        Args:
            secret_dir: Base secret directory (e.g., ~/.swe.secret).
            source_id: Source identifier (e.g., "ruice").
        """
        default_providers = secret_dir / "default" / "providers"
        target_providers = secret_dir / f"default_{source_id}" / "providers"

        if not default_providers.exists():
            return

        target_parent = target_providers.parent
        try:
            if not target_parent.exists():
                # Copy entire default directory to create default_{source_id}
                shutil.copytree(
                    secret_dir / "default",
                    target_parent,
                )
                logger.info(
                    "Created source template providers directory: %s",
                    target_parent,
                )
            elif not target_providers.exists():
                shutil.copytree(default_providers, target_providers)
                logger.info(
                    "Created source template providers: %s",
                    target_providers,
                )
        except OSError:
            # Handle race condition - created by concurrent request
            if not target_providers.exists():
                raise
            logger.debug(
                "Source template providers %s created by concurrent request",
                target_providers,
            )

    @staticmethod
    def ensure_tenant_provider_storage(tenant_id: str | None) -> None:
        """Ensure tenant provider storage exists, initializing if needed.

        This method is idempotent and concurrency-safe. It initializes tenant
        provider storage by copying from the default tenant's configuration
        when it doesn't exist. If the default tenant has no configuration,
        an empty directory structure is created.

        When tenant_id is "default" and source_id is set in context, the
        effective storage directory becomes default_{source_id}.

        Args:
            tenant_id: The tenant ID to ensure storage for. If None, uses "default".

        Raises:
            TimeoutError: If unable to acquire initialization lock within timeout.
            OSError: If initialization fails due to filesystem issues.

        Note:
            This method is called automatically at provider feature boundaries
            (provider APIs, local model APIs, runtime model creation). It is safe
            to call multiple times - subsequent calls are no-ops if storage exists.
        """
        from ..config.context import (
            get_current_source_id,
            resolve_effective_tenant_id,
        )

        tenant_id = tenant_id or "default"
        source_id = get_current_source_id()
        effective_tenant_id = resolve_effective_tenant_id(tenant_id, source_id)
        tenant_providers_dir = SECRET_DIR / effective_tenant_id / "providers"

        # Fast path: already exists
        if tenant_providers_dir.exists():
            return

        lock_file = tenant_providers_dir.parent / ".provider_init.lock"
        try:
            tenant_providers_dir.parent.mkdir(parents=True, exist_ok=True)
            ProviderManager._initialize_with_lock(
                lock_file,
                effective_tenant_id,
                tenant_providers_dir,
            )
        except Exception as e:
            logger.error(
                "Failed to initialize provider config for tenant %s: %s",
                effective_tenant_id,
                e,
            )
            raise

    @staticmethod
    def _initialize_with_lock(
        lock_file: Path,
        tenant_id: str,
        tenant_providers_dir: Path,
    ) -> None:
        """Initialize provider storage with file locking.

        Args:
            lock_file: Path to lock file.
            tenant_id: The tenant ID.
            tenant_providers_dir: Target directory for provider storage.
        """
        max_wait_seconds = 30.0
        deadline = time.monotonic() + max_wait_seconds

        with open(lock_file, "w", encoding="utf-8") as f:
            # Acquire lock
            ProviderManager._wait_for_lock(
                f,
                deadline,
                tenant_id,
                tenant_providers_dir,
            )

            # Double-check after acquiring lock
            if tenant_providers_dir.exists():
                return

            # Initialize storage
            ProviderManager._do_initialize_provider_storage(
                tenant_id,
                tenant_providers_dir,
            )

            # Release lock
            ProviderManager._release_lock(f)

    @staticmethod
    def _wait_for_lock(
        f,
        deadline: float,
        tenant_id: str,
        tenant_providers_dir: Path,
    ) -> None:
        """Wait for file lock with timeout.

        Args:
            f: File handle.
            deadline: Timeout deadline (monotonic time).
            tenant_id: Tenant ID for logging.
            tenant_providers_dir: Provider directory to check during wait.
        """
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                elif msvcrt is not None:  # pragma: no cover (Windows)
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except (IOError, OSError) as exc:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Timeout waiting for provider initialization lock for tenant {tenant_id}",
                    ) from exc
                logger.debug(
                    "Waiting for concurrent provider initialization for tenant %s",
                    tenant_id,
                )
                time.sleep(0.05)
                if tenant_providers_dir.exists():
                    return

    @staticmethod
    def _release_lock(f) -> None:
        """Release file lock.

        Args:
            f: File handle.
        """
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover (Windows)
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    @staticmethod
    def get_instance(tenant_id: str | None = None) -> "ProviderManager":
        """Get a ProviderManager instance for a specific tenant.

        This method implements a multi-instance singleton pattern where
        each tenant has its own isolated ProviderManager instance.

        When tenant_id is "default" and source_id is set in context, the
        singleton key becomes default_{source_id} for source isolation.

        Args:
            tenant_id: The tenant ID. If None, uses "default" tenant.

        Returns:
            ProviderManager instance for the specified tenant.
        """
        from ..config.context import (
            get_current_source_id,
            resolve_effective_tenant_id,
        )

        tenant_id = tenant_id or "default"
        source_id = get_current_source_id()
        effective_tenant_id = resolve_effective_tenant_id(tenant_id, source_id)

        # Fast path: check if instance exists without lock
        if effective_tenant_id in ProviderManager._instances:
            return ProviderManager._instances[effective_tenant_id]

        # Slow path: create instance with lock
        with ProviderManager._instances_lock:
            # Double-check after acquiring lock
            if effective_tenant_id not in ProviderManager._instances:
                ProviderManager._instances[
                    effective_tenant_id
                ] = ProviderManager(
                    effective_tenant_id,
                )
            return ProviderManager._instances[effective_tenant_id]

    @staticmethod
    def get_active_chat_model() -> ChatModelBase:
        """Get the currently active provider/model configuration.

        .. deprecated::
            This method is deprecated in multi-tenant environments.
            Use TenantModelContext.get_config() for tenant-isolated model selection.
        """
        import warnings

        warnings.warn(
            "get_active_chat_model() accesses global active model which is not "
            "isolated per tenant. In multi-tenant environments, use "
            "TenantModelContext.get_config() for proper tenant isolation.",
            DeprecationWarning,
            stacklevel=2,
        )
        manager = ProviderManager.get_instance()
        model = manager.get_active_model()
        if model is None or model.provider_id == "" or model.model == "":
            raise ValueError("No active model configured.")
        provider = manager.get_provider(model.provider_id)
        if provider is None:
            raise ValueError(
                f"Active provider '{model.provider_id}' not found.",
            )
        return provider.get_chat_model_instance(model.model)

    def _prepare_disk_storage(self):
        """Prepare directory structure"""
        for path in [self.root_path, self.builtin_path, self.custom_path]:
            path.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(path, 0o700)  # Restrict permissions for security
            except Exception:
                pass

    def _init_builtins(self):
        # Deep copy builtin providers to ensure per-tenant isolation
        pass

    def _add_builtin(self, provider: Provider):
        self.builtin_providers[provider.id] = provider

    def _record_mtimes(self):
        """Snapshot modification times of all provider config files."""
        mtimes: dict[str, float] = {}
        for provider_id in self.builtin_providers:
            path = self.builtin_path / f"{provider_id}.json"
            if path.exists():
                mtimes[str(path)] = path.stat().st_mtime
        for path in self.custom_path.glob("*.json"):
            mtimes[str(path)] = path.stat().st_mtime
        active_path = self.root_path / "active_model.json"
        if active_path.exists():
            mtimes[str(active_path)] = active_path.stat().st_mtime
        self._file_mtimes = mtimes

    def _update_mtime(self, path: Path):
        """Update cached mtime for a single file after writing."""
        if path.exists():
            self._file_mtimes[str(path)] = path.stat().st_mtime
        else:
            self._file_mtimes.pop(str(path), None)

    def _refresh_if_stale(self):
        """Reload providers whose files changed on disk since last snapshot."""
        changed_builtin = self._detect_changed_builtins()
        (
            changed_custom,
            new_custom,
            removed_custom,
        ) = self._detect_custom_changes()
        active_changed = self._detect_active_model_change()

        if not any(
            [
                changed_builtin,
                changed_custom,
                new_custom,
                removed_custom,
                active_changed,
            ],
        ):
            return

        self._apply_builtin_refresh(changed_builtin)
        self._apply_custom_refresh(changed_custom, new_custom, removed_custom)
        if active_changed:
            self._apply_active_model_refresh()
        self._record_mtimes()

    def _detect_changed_builtins(self) -> list[str]:
        """Detect builtin providers whose files have changed."""
        changed: list[str] = []
        for provider_id in self.builtin_providers:
            path = self.builtin_path / f"{provider_id}.json"
            if self._file_has_changed(path):
                changed.append(provider_id)
        return changed

    def _detect_custom_changes(
        self,
    ) -> tuple[list[Path], list[Path], list[str]]:
        """Detect custom provider changes, additions, and removals."""
        changed: list[Path] = []
        new: list[Path] = []
        current: set[str] = set()

        for path in self.custom_path.glob("*.json"):
            path_str = str(path)
            current.add(path_str)
            try:
                mtime = path.stat().st_mtime
                if path_str not in self._file_mtimes:
                    new.append(path)
                elif self._file_mtimes[path_str] != mtime:
                    changed.append(path)
            except OSError:
                pass

        removed = self._detect_removed_custom(current)
        return changed, new, removed

    def _detect_removed_custom(self, current_paths: set[str]) -> list[str]:
        """Detect custom provider files that were removed."""
        removed: list[str] = []
        custom_prefix = str(self.custom_path)
        for path_str in list(self._file_mtimes):
            if (
                path_str.startswith(custom_prefix)
                and path_str not in current_paths
            ):
                removed.append(path_str)
        return removed

    def _detect_active_model_change(self) -> bool:
        """Check if active model file has changed."""
        active_path = self.root_path / "active_model.json"
        return self._file_has_changed(active_path)

    def _file_has_changed(self, path: Path) -> bool:
        """Check if a file has changed since last snapshot."""
        try:
            if path.exists():
                mtime = path.stat().st_mtime
                return self._file_mtimes.get(str(path)) != mtime
        except OSError:
            pass
        return False

    def _apply_builtin_refresh(self, provider_ids: list[str]) -> None:
        """Apply changes for modified builtin providers."""
        for provider_id in provider_ids:
            provider = self.load_provider(provider_id, is_builtin=True)
            if provider:
                builtin = self.builtin_providers[provider_id]
                if not builtin.freeze_url:
                    builtin.base_url = provider.base_url
                builtin.api_key = provider.api_key
                builtin.extra_models = provider.extra_models
                builtin.generate_kwargs.update(provider.generate_kwargs)

    def _apply_custom_refresh(
        self,
        changed: list[Path],
        new: list[Path],
        removed: list[str],
    ) -> None:
        """Apply changes for custom providers."""
        for path in changed + new:
            provider = self.load_provider(path.stem, is_builtin=False)
            if provider:
                self.custom_providers[provider.id] = provider

        for path_str in removed:
            provider_id = Path(path_str).stem
            self.custom_providers.pop(provider_id, None)

    def _apply_active_model_refresh(self) -> None:
        """Apply changes for active model."""
        active_model = self.load_active_model()
        if active_model:
            self.active_model = active_model

    async def list_provider_info(self) -> List[ProviderInfo]:
        self._refresh_if_stale()
        tasks = [
            provider.get_info() for provider in self.builtin_providers.values()
        ]
        tasks += [
            provider.get_info() for provider in self.custom_providers.values()
        ]
        provider_infos = await asyncio.gather(*tasks)
        return list(provider_infos)

    def get_provider(self, provider_id: str) -> Provider | None:
        # Return a provider instance by its ID. This will be used to create
        # chat model instances for the agent.
        if provider_id in self.builtin_providers:
            return self.builtin_providers[provider_id]
        if provider_id in self.custom_providers:
            return self.custom_providers[provider_id]
        return None

    async def get_provider_info(self, provider_id: str) -> ProviderInfo | None:
        provider = self.get_provider(provider_id)
        return await provider.get_info() if provider else None

    def get_active_model(self) -> ModelSlotConfig | None:
        # Return the currently active provider/model configuration.
        return self.active_model

    def update_provider(self, provider_id: str, config: Dict) -> bool:
        # Update the configuration of a provider (e.g., base URL, API key).
        # This will be called when the user edits a provider's settings in the
        # UI. It should update the in-memory provider instance and persist the
        # changes to providers.json.
        provider = self.get_provider(provider_id)
        if not provider:
            return False
        provider.update_config(config)
        self._save_provider(
            provider,
            is_builtin=provider_id in self.builtin_providers,
        )
        return True

    async def fetch_provider_models(
        self,
        provider_id: str,
    ) -> List[ModelInfo]:
        """Fetch the list of available models from a provider and update."""
        provider = self.get_provider(provider_id)
        if not provider:
            return []
        try:
            models = await provider.fetch_models()
            provider.extra_models = models
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )
            return models
        except Exception as e:
            logger.warning(
                "Failed to fetch models for provider '%s': %s",
                provider_id,
                e,
            )
            return []

    def _resolve_custom_provider_id(self, provider_id: str) -> str:
        """Resolve provider ID conflicts for a custom provider."""
        base_id = provider_id
        if base_id in self.builtin_providers:
            base_id = f"{base_id}-custom"

        resolved_id = base_id
        while (
            resolved_id in self.builtin_providers
            or resolved_id in self.custom_providers
        ):
            resolved_id = f"{resolved_id}-new"

        return resolved_id

    async def add_custom_provider(self, provider_data: ProviderInfo):
        # Add a new custom provider with the given data. This will update the
        # providers.json file and make the new provider available in the UI.
        provider_payload = provider_data.model_dump()
        provider_payload["id"] = self._resolve_custom_provider_id(
            provider_data.id,
        )
        provider_payload["is_custom"] = True
        provider = self._provider_from_data(
            provider_payload,
        )  # Validate provider data
        # For custom providers, we assume they don't support connection check
        # without model config, to avoid false negatives in the UI.
        provider.support_connection_check = False
        self.custom_providers[provider.id] = provider
        self._save_provider(provider, is_builtin=False)
        return await provider.get_info()

    def remove_custom_provider(self, provider_id: str) -> bool:
        # Remove a custom provider by its ID. This will update the
        # providers.json file and remove the provider from the UI.
        if provider_id in self.custom_providers:
            del self.custom_providers[provider_id]
            provider_path = self.custom_path / f"{provider_id}.json"
            if provider_path.exists():
                os.remove(provider_path)
            self._file_mtimes.pop(str(provider_path), None)
            return True
        return False

    async def activate_model(self, provider_id: str, model_id: str):
        # Set the active provider and model for the agent. This will update
        # providers.json and determine which provider/model is used when the
        # agent creates chat model instances.
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found.")
        if not provider.has_model(model_id):
            raise ValueError(
                f"Model '{model_id}' not found in provider '{provider_id}'.",
            )
        self.active_model = ModelSlotConfig(
            provider_id=provider_id,
            model=model_id,
        )
        self.save_active_model(self.active_model)

        self.maybe_probe_multimodal(provider_id, model_id)

    def maybe_probe_multimodal(self, provider_id: str, model_id: str) -> None:
        """Schedule multimodal probing for a model if capability is unknown."""
        provider = self.get_provider(provider_id)
        # Auto-probe multimodal if not yet probed
        for model in provider.models + provider.extra_models:
            if model.id == model_id and model.supports_multimodal is None:
                asyncio.create_task(
                    self._auto_probe_multimodal(provider_id, model_id),
                )
                break

    async def _auto_probe_multimodal(
        self,
        provider_id: str,
        model_id: str,
    ) -> None:
        """Background probe that doesn't block model activation."""
        try:
            result = await self.probe_model_multimodal(provider_id, model_id)
            logger.info(
                "Auto-probe for %s/%s: image=%s, video=%s",
                provider_id,
                model_id,
                result.get("supports_image"),
                result.get("supports_video"),
            )
        except Exception as e:
            logger.warning("Auto-probe multimodal failed: %s", e)

    async def add_model_to_provider(
        self,
        provider_id: str,
        model_info: ModelInfo,
    ) -> ProviderInfo:
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found.")
        await provider.add_model(model_info)
        self._save_provider(
            provider,
            is_builtin=provider_id in self.builtin_providers,
        )
        return await provider.get_info()

    async def delete_model_from_provider(
        self,
        provider_id: str,
        model_id: str,
    ) -> ProviderInfo:
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found.")
        await provider.delete_model(model_id=model_id)
        self._save_provider(
            provider,
            is_builtin=provider_id in self.builtin_providers,
        )
        return await provider.get_info()

    async def probe_model_multimodal(
        self,
        provider_id: str,
        model_id: str,
    ) -> dict:
        """Probe a model's multimodal capabilities and persist the result."""
        provider = self.get_provider(provider_id)
        if not provider:
            return {"error": f"Provider '{provider_id}' not found"}

        result = await provider.probe_model_multimodal(model_id)

        # Update the model's capability flags
        for model in provider.models + provider.extra_models:
            if model.id == model_id:
                model.supports_image = result.supports_image
                model.supports_video = result.supports_video
                model.supports_multimodal = result.supports_multimodal
                model.probe_source = "probed"
                break

        # Compare probe result against expected baseline
        from .capability_baseline import (
            ExpectedCapabilityRegistry,
            compare_probe_result,
        )

        registry = ExpectedCapabilityRegistry()
        expected = registry.get_expected(provider_id, model_id)
        if expected:
            discrepancies = compare_probe_result(
                expected,
                result.supports_image,
                result.supports_video,
            )
            for d in discrepancies:
                logger.warning(
                    "Probe discrepancy: %s/%s %s expected=%s actual=%s (%s)",
                    d.provider_id,
                    d.model_id,
                    d.field,
                    d.expected,
                    d.actual,
                    d.discrepancy_type,
                )

        # Persist to disk
        self._save_provider(
            provider,
            is_builtin=provider_id in self.builtin_providers,
        )
        return {
            "supports_image": result.supports_image,
            "supports_video": result.supports_video,
            "supports_multimodal": result.supports_multimodal,
            "image_message": result.image_message,
            "video_message": result.video_message,
        }

    def _save_provider(
        self,
        provider: Provider,
        is_builtin: bool = False,
        skip_if_exists: bool = False,
    ):
        """Save a provider configuration to disk."""
        provider_dir = self.builtin_path if is_builtin else self.custom_path
        provider_path = provider_dir / f"{provider.id}.json"
        if skip_if_exists and provider_path.exists():
            return
        with open(provider_path, "w", encoding="utf-8") as f:
            json.dump(provider.model_dump(), f, ensure_ascii=False, indent=2)
        try:
            os.chmod(provider_path, 0o600)
        except OSError:
            pass
        self._update_mtime(provider_path)

    def overwrite_provider_payload(self, payload: Dict) -> Provider:
        """Replace a tenant provider with the supplied payload.

        The payload should come from an existing Provider instance's
        ``model_dump()`` so secrets and model metadata are preserved. The write
        path updates both in-memory state and on-disk storage in the same shape
        that ProviderManager already uses for normal persistence.
        """
        provider = self._provider_from_data(payload)
        is_builtin = not provider.is_custom

        if is_builtin:
            self.custom_providers.pop(provider.id, None)
            custom_path = self.custom_path / f"{provider.id}.json"
            if custom_path.exists():
                custom_path.unlink()
            self.builtin_providers[provider.id] = provider
        else:
            self.builtin_providers.pop(provider.id, None)
            builtin_path = self.builtin_path / f"{provider.id}.json"
            if builtin_path.exists():
                builtin_path.unlink()
            self.custom_providers[provider.id] = provider

        self._save_provider(provider, is_builtin=is_builtin)
        return provider

    def load_provider(
        self,
        provider_id: str,
        is_builtin: bool = False,
    ) -> Provider | None:
        """Load a provider configuration from disk."""
        provider_dir = self.builtin_path if is_builtin else self.custom_path
        provider_path = provider_dir / f"{provider_id}.json"
        if not provider_path.exists():
            return None
        try:
            with open(provider_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._provider_from_data(data)
        except Exception as e:
            logger.warning(
                "Failed to load provider '%s' from %s: %s",
                provider_id,
                provider_path,
                e,
            )
            return None

    def _provider_from_data(self, data: Dict) -> Provider:
        """Deserialize provider data to a concrete provider type."""
        provider_id = str(data.get("id", ""))
        chat_model = str(data.get("chat_model", ""))

        if provider_id == "anthropic" or chat_model == "AnthropicChatModel":
            return AnthropicProvider.model_validate(data)
        # if provider_id == "gemini" or chat_model == "GeminiChatModel":
        #     return GeminiProvider.model_validate(data)
        if provider_id == "ollama":
            return OllamaProvider.model_validate(data)
        return OpenAIProvider.model_validate(data)

    def save_active_model(self, active_model: ModelSlotConfig):
        """Save the active provider/model configuration to disk."""
        active_path = self.root_path / "active_model.json"
        with open(active_path, "w", encoding="utf-8") as f:
            json.dump(
                active_model.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
            )
        try:
            os.chmod(active_path, 0o600)
        except OSError:
            pass
        self._update_mtime(active_path)

    def load_active_model(self) -> ModelSlotConfig | None:
        """Load the active provider/model configuration from disk.

        If active_model.json doesn't exist but legacy tenant_models.json does,
        recovers the active slot from the legacy config and migrates it.
        """
        active_path = self.root_path / "active_model.json"

        # Try to load from new location first
        if active_path.exists():
            try:
                with open(active_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ModelSlotConfig.model_validate(data)
            except Exception:
                return None

        # Recovery: migrate from legacy tenant_models.json if it exists
        legacy_config = self._recover_from_legacy_tenant_models()
        if legacy_config:
            logger.info(
                "Recovered active model from legacy tenant_models.json "
                "for tenant %s: %s/%s",
                self.tenant_id,
                legacy_config.provider_id,
                legacy_config.model,
            )
            # Save to new location for future reads
            self.save_active_model(legacy_config)
            return legacy_config

        return None

    def _recover_from_legacy_tenant_models(self) -> ModelSlotConfig | None:
        """Recover active model from legacy tenant_models.json.

        This provides one-time migration for tenants that have tenant_models.json
        but don't yet have providers/active_model.json.

        Returns:
            ModelSlotConfig if recovery succeeded, None otherwise.
        """
        try:
            from swe.tenant_models.manager import TenantModelManager

            # Check if legacy config exists for this tenant
            legacy_path = TenantModelManager.get_config_path(self.tenant_id)
            if not legacy_path.exists():
                # Try default tenant as fallback
                if self.tenant_id != "default":
                    legacy_path = TenantModelManager.get_config_path("default")
                    if not legacy_path.exists():
                        return None
                else:
                    return None

            # Load and extract active slot from legacy config
            legacy_config = TenantModelManager.load(self.tenant_id)
            if not legacy_config:
                return None

            active_slot = legacy_config.get_active_slot()
            if active_slot and active_slot.provider_id and active_slot.model:
                return ModelSlotConfig(
                    provider_id=active_slot.provider_id,
                    model=active_slot.model,
                )
        except Exception as e:
            logger.debug(
                "Failed to recover from legacy tenant_models.json "
                "for tenant %s: %s",
                self.tenant_id,
                e,
            )
        return None

    def _migrate_legacy_providers(self):
        """Migrate from legacy providers.json format to the new structure."""
        legacy_path = SECRET_DIR / "providers.json"
        if not legacy_path.exists() or not legacy_path.is_file():
            return

        with open(legacy_path, "r", encoding="utf-8") as f:
            legacy_data = json.load(f)

        self._migrate_builtin_providers(legacy_data.get("providers", {}))
        self._migrate_custom_providers(legacy_data.get("custom_providers", {}))
        self._migrate_active_model_config(legacy_data.get("active_llm", {}))

        try:
            os.remove(legacy_path)
        except Exception:
            logger.warning(
                "Failed to remove legacy providers.json after migration.",
            )

    def _migrate_builtin_providers(self, builtin_providers: dict) -> None:
        """Migrate built-in providers from legacy format."""
        for provider_id, config in builtin_providers.items():
            provider = self.get_provider(provider_id)
            if not provider:
                logger.warning(
                    "Legacy provider '%s' not found in registry, skipping.",
                    provider_id,
                )
                continue
            self._apply_builtin_provider_config(provider, config)
            self._save_provider(provider, is_builtin=True)

    def _apply_builtin_provider_config(
        self,
        provider: Provider,
        config: dict,
    ) -> None:
        """Apply legacy config to a built-in provider."""
        if "api_key" in config:
            provider.api_key = config["api_key"]
        if "extra_models" in config:
            provider.extra_models = [
                ModelInfo.model_validate(model)
                for model in config["extra_models"]
            ]
        if not provider.freeze_url and "base_url" in config:
            provider.base_url = config["base_url"]

    def _migrate_custom_providers(self, custom_providers: dict) -> None:
        """Migrate custom providers from legacy format."""
        for provider_id, data in custom_providers.items():
            custom_provider = OpenAIProvider(
                id=provider_id,
                name=data.get("name", provider_id),
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key", ""),
                is_custom=True,
            )
            if "models" in data:
                custom_provider.extra_models = [
                    ModelInfo.model_validate(model) for model in data["models"]
                ]
            if "chat_model" in data:
                custom_provider.chat_model = data["chat_model"]
            self._save_provider(custom_provider, is_builtin=False)

    def _migrate_active_model_config(self, active_model: dict) -> None:
        """Migrate active model from legacy format."""
        if not active_model:
            return
        try:
            self.active_model = ModelSlotConfig.model_validate(active_model)
            self.save_active_model(self.active_model)
        except Exception:
            logger.warning("Failed to migrate active model, using default.")

    def _init_from_storage(self):
        """Initialize all providers and active model from disk storage."""
        # Load built-in providers
        for builtin in self.builtin_providers.values():
            provider = self.load_provider(builtin.id, is_builtin=True)
            if provider:
                # inherit user-configured base_url only when freeze_url=False
                if not builtin.freeze_url:
                    builtin.base_url = provider.base_url
                builtin.api_key = provider.api_key
                builtin.extra_models = provider.extra_models
                builtin.generate_kwargs.update(provider.generate_kwargs)
        # Load custom providers
        for provider_file in self.custom_path.glob("*.json"):
            provider = self.load_provider(provider_file.stem, is_builtin=False)
            if provider:
                self.custom_providers[provider.id] = provider
        # Load active model config
        active_model = self.load_active_model()
        if active_model:
            self.active_model = active_model

    def _apply_default_annotations(self):
        """Apply doc-based default annotations for unprobed models.

        Models that already carry static annotations (supports_image /
        supports_video set at definition time) only need the derived
        supports_multimodal flag computed.  Models with no annotations
        at all fall back to the ExpectedCapabilityRegistry.
        """
        from .capability_baseline import ExpectedCapabilityRegistry

        registry = ExpectedCapabilityRegistry()
        for provider in self.builtin_providers.values():
            for model in provider.models:
                # Already fully annotated (e.g. by a prior probe) → skip
                if model.supports_multimodal is not None:
                    continue

                # Static annotations present → compute derived flag only
                if (
                    model.supports_image is not None
                    or model.supports_video is not None
                ):
                    model.supports_multimodal = bool(
                        model.supports_image or model.supports_video,
                    )
                    continue

                # No annotations at all → fall back to registry
                expected = registry.get_expected(provider.id, model.id)
                if expected:
                    model.supports_image = expected.expected_image
                    model.supports_video = expected.expected_video
                    model.supports_multimodal = bool(
                        expected.expected_image or expected.expected_video,
                    )
                    model.probe_source = "documentation"
