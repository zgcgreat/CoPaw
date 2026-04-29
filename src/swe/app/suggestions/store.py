# -*- coding: utf-8 -*-
"""建议存储模块 - 存储生成后的猜你想问建议供前端轮询获取.

基于 session_id 存储，前端在主响应完成后轮询获取建议。
建议有过期时间，自动清理。
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

# Per-session suggestion storage: session_id -> list of suggestions
_session_suggestions: Dict[str, List[Dict[str, Any]]] = {}
_lock = asyncio.Lock()
_MAX_AGE_SECONDS = 60  # 建议有效期60秒
_MAX_SUGGESTIONS_PER_SESSION = 10  # 每个session最多存储的建议数

# Q&A 内容存储：chat_id -> {user_message_hash: QAContentEntry}
_qa_content_store: Dict[str, Dict[str, Any]] = {}
_QA_MAX_AGE_SECONDS = 120  # Q&A 内容有效期120秒


@dataclass
class QAContentEntry:
    """Q&A 内容条目."""

    user_message: str  # 提取后的用户问题
    user_message_hash: str  # 用户问题的 hash
    assistant_response: str  # 提取后的助手回答
    ts: float  # 存储时间戳
    tenant_id: str  # 租户 ID


async def store_suggestions(
    session_id: str,
    suggestions: List[str],
    tenant_id: Optional[str] = None,
) -> None:
    """存储建议列表到 session_id 对应的存储中.

    Args:
        session_id: Session identifier.
        suggestions: 建议问题列表.
        tenant_id: Tenant identifier for isolation.
    """
    if not session_id or not suggestions:
        return

    async with _lock:
        # 每次只保留最新的一个 suggestions entry（覆盖而不是累积）
        # 因为 suggestions 是针对最新一条回答的，不需要历史累积
        suggestion_entry = {
            "id": str(uuid.uuid4()),
            "suggestions": suggestions,
            "ts": time.time(),
            "session_id": session_id,
            "tenant_id": tenant_id or "default",
        }

        _session_suggestions[session_id] = [suggestion_entry]


async def take_suggestions(
    session_id: str,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """获取并移除 session_id 对应的所有建议.

    Args:
        session_id: Session identifier.
        tenant_id: Tenant identifier for isolation.

    Returns:
        建议列表，每个建议包含 id 和 suggestions 字段。
    """
    if not session_id:
        return []

    async with _lock:
        suggestions = _session_suggestions.get(session_id, [])
        _prune_expired(suggestions)

        # 移除该 session 的建议
        if session_id in _session_suggestions:
            del _session_suggestions[session_id]

        return _strip_ts(suggestions)


async def peek_suggestions(
    session_id: str,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查看但不移除 session_id 对应的建议（用于检查是否有建议）.

    Args:
        session_id: Session identifier.
        tenant_id: Tenant identifier for isolation.

    Returns:
        建议列表（不移除）。
    """
    if not session_id:
        return []

    async with _lock:
        suggestions = _session_suggestions.get(session_id, [])
        _prune_expired(suggestions)
        return _strip_ts(suggestions)


def _prune_expired(
    suggestions: List[Dict[str, Any]],
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> List[Dict[str, Any]]:
    """清理过期建议（就地清理）."""
    cutoff = time.time() - max_age_seconds
    return [s for s in suggestions if s.get("ts", 0) >= cutoff]


def _strip_ts(suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """移除内部时间戳字段."""
    return [
        {
            "id": s["id"],
            "suggestions": s["suggestions"],
        }
        for s in suggestions
    ]


def get_stats() -> Dict[str, Any]:
    """获取存储统计信息."""
    return {
        "session_count": len(_session_suggestions),
        "sessions": {
            session_id: len(suggestions)
            for session_id, suggestions in _session_suggestions.items()
        },
    }
