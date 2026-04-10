# -*- coding: utf-8 -*-
"""Lazy runner package exports."""
from __future__ import annotations


__all__ = [
    # Core classes
    "AgentRunner",
    "ChatManager",
    # API
    "router",
    # Models
    "ChatSpec",
    "ChatHistory",
    "ChatsFile",
    "ChatRunContext",
    "ChatRunRecord",
    # Chat Repository
    "BaseChatRepository",
    "BaseChatRunRepository",
    "JsonChatRepository",
    "MysqlChatRepository",
    "MysqlChatRunRepository",
]


def __getattr__(name: str):
    if name == "AgentRunner":
        from .runner import AgentRunner as _AgentRunner

        return _AgentRunner
    if name == "router":
        from .api import router as _router

        return _router
    if name == "ChatManager":
        from .manager import ChatManager as _ChatManager

        return _ChatManager
    if name in {"ChatSpec", "ChatHistory", "ChatsFile"}:
        from .models import (
            ChatHistory as _ChatHistory,
            ChatsFile as _ChatsFile,
            ChatSpec as _ChatSpec,
        )

        exports = {
            "ChatSpec": _ChatSpec,
            "ChatHistory": _ChatHistory,
            "ChatsFile": _ChatsFile,
        }
        return exports[name]
    if name in {"ChatRunContext", "ChatRunRecord"}:
        from .run_models import (
            ChatRunContext as _ChatRunContext,
            ChatRunRecord as _ChatRunRecord,
        )

        exports = {
            "ChatRunContext": _ChatRunContext,
            "ChatRunRecord": _ChatRunRecord,
        }
        return exports[name]
    if name in {
        "BaseChatRepository",
        "BaseChatRunRepository",
        "JsonChatRepository",
        "MysqlChatRepository",
        "MysqlChatRunRepository",
    }:
        from .repo import (
            BaseChatRepository as _BaseChatRepository,
            BaseChatRunRepository as _BaseChatRunRepository,
            JsonChatRepository as _JsonChatRepository,
            MysqlChatRepository as _MysqlChatRepository,
            MysqlChatRunRepository as _MysqlChatRunRepository,
        )

        exports = {
            "BaseChatRepository": _BaseChatRepository,
            "BaseChatRunRepository": _BaseChatRunRepository,
            "JsonChatRepository": _JsonChatRepository,
            "MysqlChatRepository": _MysqlChatRepository,
            "MysqlChatRunRepository": _MysqlChatRunRepository,
        }
        return exports[name]
    raise AttributeError(name)
