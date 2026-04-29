# -*- coding: utf-8 -*-
"""管理员市场 API."""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from ...marketplace.schemas import (
    DistributeRequest,
    DistributeResponse,
    MarketSkillResponse,
    PublishSkillRequest,
)

router = APIRouter()


def _require_manager(x_manager: Optional[str]) -> None:
    if x_manager != "true":
        raise HTTPException(status_code=403, detail="Manager access required")


def _require_source_id(x_source_id: Optional[str]) -> str:
    if not x_source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )
    return x_source_id


@router.post(
    "/marketplace/skills",
    response_model=MarketSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_skill(
    req: PublishSkillRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """上架技能（管理员）."""
    source_id = _require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    item = await svc.publish_skill(source_id, req)
    return MarketSkillResponse(
        item_id=item.item_id,
        name=item.name,
        description=item.description,
        version=item.version,
        creator_id=item.creator_id,
        creator_name=item.creator_name,
        category_id=item.category_id,
        bbk_ids=item.bbk_ids,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete(
    "/marketplace/skills/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unpublish_skill(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """下架技能（管理员）."""
    source_id = _require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    ok = await svc.unpublish_skill(
        source_id,
        item_id,
        operator_id=x_user_id or "",
        operator_name=x_user_name or "",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.post(
    "/marketplace/skills/{item_id}/distribute",
    response_model=DistributeResponse,
)
async def distribute_skill(
    item_id: str,
    req: DistributeRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """分发技能（管理员）."""
    source_id = _require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    try:
        result = await svc.distribute_skill(
            source_id,
            item_id,
            operator_id=x_user_id or "",
            operator_name=x_user_name or "",
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
