# -*- coding: utf-8 -*-
"""Featured case models (simplified - no case_id)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CaseStep(BaseModel):
    """Case step."""

    title: str
    content: str


class CaseDetail(BaseModel):
    """Case detail with iframe and steps."""

    iframe_url: str = ""
    iframe_title: str = ""
    steps: List[CaseStep] = []


class FeaturedCase(BaseModel):
    """Featured case with dimension info."""

    model_config = ConfigDict(use_enum_values=True)

    id: Optional[int] = None
    source_id: str = Field(..., min_length=1, max_length=64)
    bbk_id: Optional[str] = Field(None, max_length=64)
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeaturedCaseCreate(BaseModel):
    """Create featured case request.

    Note: source_id is NOT a form field - it comes from X-Source-Id header.
    Note: sort_order is auto-generated (max + 1 for current dimension).
    """

    bbk_id: Optional[str] = Field(None, max_length=64)
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None


class FeaturedCaseUpdate(BaseModel):
    """Update featured case request."""

    bbk_id: Optional[str] = Field(None, max_length=64)
    label: Optional[str] = Field(None, min_length=1, max_length=512)
    value: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FeaturedCaseListResponse(BaseModel):
    """Featured case list response."""

    cases: List[FeaturedCase]
    total: int
