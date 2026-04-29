# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field

from ...config.utils import get_tenant_secrets_dir
from ...utils.tools import (
    get_auth_token,
    get_user_info,
)

logger = logging.getLogger(__name__)

CRON_AUTH_FILE_NAME = "cron_auth.json"
DEFAULT_USER_INFO_TTL = timedelta(days=7)
DEFAULT_AUTH_TOKEN_TTL = timedelta(hours=2)
USER_INFO_REFRESH_MARGIN = timedelta(days=5)
AUTH_TOKEN_REUSE_MIN_REMAINING = timedelta(minutes=30)
ACCESS_TOKEN_COOKIE_NAME = "com.cmb.dw.rtl.sso.token"


class CronAuthState(BaseModel):
    user_info: dict[str, Any] = Field(default_factory=dict)
    user_info_expires_at: datetime | None = None
    user_info_refreshed_at: datetime | None = None
    auth_token: str | None = None
    auth_token_expires_at: datetime | None = None
    cookie_header: str | None = None
    last_prefetch_at: datetime | None = None
    last_error: str | None = None


@dataclass
class CronUserInfoEnsureResult:
    state: CronAuthState
    reused: bool


@dataclass
class ResolvedAuthToken:
    token: str | None
    expires_at: datetime | None
    reused: bool
    cookie_header: str | None = None


@dataclass
class CronAuthSnapshot:
    configured: bool
    user_info_expires_at: datetime | None
    auth_token_expires_at: datetime | None
    has_auth_token: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _prepare_secret_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)


def _iter_cookie_pairs(cookie_header: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in cookie_header.split(";"):
        item = part.strip()
        if not item:
            continue
        name, sep, value = item.partition("=")
        if not sep:
            continue
        pairs.append((name.strip(), value.strip()))
    return pairs


def extract_access_token_from_cookie(cookie_header: str) -> str:
    for name, value in _iter_cookie_pairs(cookie_header):
        if name == ACCESS_TOKEN_COOKIE_NAME and value:
            return value
    raise ValueError(
        f"cron auth cookie missing {ACCESS_TOKEN_COOKIE_NAME}",
    )


def merge_auth_token_into_cookie(
    cookie_header: str | None,
    auth_token: str,
) -> str:
    if not cookie_header:
        return f"{ACCESS_TOKEN_COOKIE_NAME}={auth_token}"

    merged_parts: list[str] = []
    replaced = False
    for name, value in _iter_cookie_pairs(cookie_header):
        if name == ACCESS_TOKEN_COOKIE_NAME:
            merged_parts.append(f"{ACCESS_TOKEN_COOKIE_NAME}={auth_token}")
            replaced = True
            continue
        merged_parts.append(f"{name}={value}")

    if not replaced:
        merged_parts.append(f"{ACCESS_TOKEN_COOKIE_NAME}={auth_token}")
    return "; ".join(merged_parts)


def get_cron_auth_file_path(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> Path:
    _ = workspace_dir
    return get_tenant_secrets_dir(tenant_id) / CRON_AUTH_FILE_NAME


def load_cron_auth_state(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> CronAuthState:
    path = get_cron_auth_file_path(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    logger.info("load_cron_auth_state workspace_dir")
    print(path)
    if not path.is_file():
        return CronAuthState()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return CronAuthState.model_validate(data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning(
            "Failed to load cron auth state from %s: %s",
            path,
            exc,
        )
        return CronAuthState(last_error=f"load_failed: {exc}")


def save_cron_auth_state(
    state: CronAuthState,
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> Path:
    path = get_cron_auth_file_path(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    _prepare_secret_parent(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            state.model_dump(mode="json", exclude_none=True),
            fh,
            ensure_ascii=False,
            indent=2,
        )
    _chmod_best_effort(path, 0o600)
    return path


def _parse_expire_time(raw: Any, default_ttl: timedelta) -> datetime:
    now = utc_now()
    if isinstance(raw, datetime):
        return ensure_utc(raw) or (now + default_ttl)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            return ensure_utc(datetime.fromisoformat(raw)) or (
                now + default_ttl
            )
        except ValueError:
            pass
    return now + default_ttl


def _normalize_user_info_payload(
    payload: Any,
) -> tuple[dict[str, Any], datetime]:
    if isinstance(payload, Mapping):
        data = dict(payload)
        exp = _parse_expire_time(data.get("exp"), DEFAULT_USER_INFO_TTL)
        user_info = data.get("userInfo", data)
        if isinstance(user_info, Mapping):
            return dict(user_info), exp
        return {"value": user_info}, exp
    return {"value": payload}, utc_now() + DEFAULT_USER_INFO_TTL


def _raise_if_user_info_expired(state: CronAuthState) -> None:
    if not state.user_info:
        return
    expires_at = ensure_utc(state.user_info_expires_at)
    print("user_info expires_at", expires_at)
    now = utc_now()
    if expires_at is not None and expires_at <= now:
        raise ValueError("cron auth user_info is expired")


def save_user_info_from_access_token(
    access_token: str,
    *,
    cookie_header: str | None = None,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> CronAuthState:
    payload = get_user_info(access_token)
    user_info, expires_at = _normalize_user_info_payload(payload)
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    state.user_info = user_info
    state.user_info_expires_at = expires_at
    state.user_info_refreshed_at = utc_now()
    state.auth_token = None
    state.auth_token_expires_at = None
    if cookie_header is not None:
        state.cookie_header = cookie_header
    state.last_error = None
    save_cron_auth_state(
        state,
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    return state


def ensure_user_info_from_access_token(
    access_token: str,
    *,
    cookie_header: str | None = None,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
    min_remaining: timedelta = USER_INFO_REFRESH_MARGIN,
) -> CronUserInfoEnsureResult:
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    expires_at = ensure_utc(state.user_info_expires_at)
    now = utc_now()
    if (
        state.user_info
        and expires_at is not None
        and expires_at - now > min_remaining
    ):
        if cookie_header is not None:
            state.cookie_header = cookie_header
            save_cron_auth_state(
                state,
                tenant_id=tenant_id,
                workspace_dir=workspace_dir,
            )
        return CronUserInfoEnsureResult(
            state=state,
            reused=True,
        )
    return CronUserInfoEnsureResult(
        state=save_user_info_from_access_token(
            access_token,
            cookie_header=cookie_header,
            tenant_id=tenant_id,
            workspace_dir=workspace_dir,
        ),
        reused=False,
    )


def require_valid_user_info(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> CronAuthState:
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    if not state.user_info:
        raise ValueError("cron auth user_info is not configured")

    _raise_if_user_info_expired(state)
    return state


def refresh_user_info_if_needed(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
    min_remaining: timedelta = USER_INFO_REFRESH_MARGIN,
) -> CronAuthState:
    return require_valid_user_info(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )


def _is_auth_token_reusable(
    state: CronAuthState,
    *,
    min_remaining: timedelta = AUTH_TOKEN_REUSE_MIN_REMAINING,
) -> bool:
    expires_at = ensure_utc(state.auth_token_expires_at)
    if not state.auth_token or expires_at is None:
        return False
    return expires_at - utc_now() > min_remaining


def issue_auth_token(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> ResolvedAuthToken:
    state = require_valid_user_info(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    if not state.user_info:
        raise ValueError("cron auth user_info is not configured")

    auth_token = get_auth_token(state.user_info)
    expires_at = utc_now() + DEFAULT_AUTH_TOKEN_TTL
    state.auth_token = auth_token
    state.auth_token_expires_at = expires_at
    state.last_error = None
    save_cron_auth_state(
        state,
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    return ResolvedAuthToken(
        token=auth_token,
        expires_at=expires_at,
        reused=False,
        cookie_header=merge_auth_token_into_cookie(
            state.cookie_header,
            auth_token,
        ),
    )


def prefetch_auth_token(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> ResolvedAuthToken:
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    if _is_auth_token_reusable(state, min_remaining=timedelta(0)):
        state.last_prefetch_at = utc_now()
        state.last_error = None
        save_cron_auth_state(
            state,
            tenant_id=tenant_id,
            workspace_dir=workspace_dir,
        )
        return ResolvedAuthToken(
            token=state.auth_token,
            expires_at=(
                ensure_utc(state.auth_token_expires_at)
                or (utc_now() + DEFAULT_AUTH_TOKEN_TTL)
            ),
            reused=True,
            cookie_header=merge_auth_token_into_cookie(
                state.cookie_header,
                state.auth_token or "",
            ),
        )

    resolved = issue_auth_token(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    state.last_prefetch_at = utc_now()
    state.last_error = None
    save_cron_auth_state(
        state,
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    return resolved


def resolve_auth_token_for_execution(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> ResolvedAuthToken:
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    _raise_if_user_info_expired(state)

    if not state.user_info:
        return ResolvedAuthToken(
            token=None,
            expires_at=None,
            reused=False,
            cookie_header=None,
        )

    if _is_auth_token_reusable(state):
        return ResolvedAuthToken(
            token=state.auth_token,
            expires_at=(
                ensure_utc(state.auth_token_expires_at)
                or (utc_now() + DEFAULT_AUTH_TOKEN_TTL)
            ),
            reused=True,
            cookie_header=merge_auth_token_into_cookie(
                state.cookie_header,
                state.auth_token or "",
            ),
        )
    return issue_auth_token(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )


def get_auth_snapshot(
    *,
    tenant_id: str | None = None,
    workspace_dir: str | Path | None = None,
) -> CronAuthSnapshot:
    state = load_cron_auth_state(
        tenant_id=tenant_id,
        workspace_dir=workspace_dir,
    )
    return CronAuthSnapshot(
        configured=bool(state.user_info),
        user_info_expires_at=ensure_utc(state.user_info_expires_at),
        auth_token_expires_at=ensure_utc(
            state.auth_token_expires_at,
        ),
        has_auth_token=bool(state.auth_token),
    )
