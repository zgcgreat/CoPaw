# -*- coding: utf-8 -*-
"""猜你想问功能模块 - 异步生成用户可能想问的后续问题."""

from .service import generate_suggestions, SuggestionService, extract_key_content
from .store import (
    store_suggestions,
    take_suggestions,
    peek_suggestions,
    store_qa_content,
    get_qa_content,
)

__all__ = [
    "generate_suggestions",
    "SuggestionService",
    "extract_key_content",
    "store_suggestions",
    "take_suggestions",
    "peek_suggestions",
]
