# -*- coding: utf-8 -*-
"""用户信息查询接口路由。

用于用户登录后获取更多用户信息，转发到外部API。
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...constant import USER_INFO_API_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-info", tags=["user-info"])


class UserInfoQueryRequest(BaseModel):
    """用户信息查询请求参数。"""

    keyWord: str  # 用户ID
    compareType: str = "EQ"  # 比较类型，默认EQ


class UserInfoQueryResponse(BaseModel):
    """用户信息查询响应（动态字段）。"""

    # 使用动态字段，实际返回由外部API决定
    data: dict


@router.post(
    "/query",
    response_model=UserInfoQueryResponse,
    summary="查询用户信息",
    description="用户登录后获取更多用户信息，转发到外部API",
)
async def query_user_info(
    request: Request,
    body: UserInfoQueryRequest,
) -> UserInfoQueryResponse:
    """查询用户信息。

    Args:
        request: FastAPI请求对象
        body: 查询参数，包含keyWord（用户ID）和compareType

    Returns:
        用户信息数据

    Raises:
        HTTPException: 如果API地址未配置或请求失败
    """
    # 检查API地址是否配置
    if not USER_INFO_API_URL:
        logger.warning("USER_INFO_API_URL not configured")
        raise HTTPException(
            status_code=503,
            detail="User info API not configured",
        )

    # 构建请求
    url = USER_INFO_API_URL.rstrip("/") + "/user/query"
    headers = {
        "Content-Type": "application/json",
    }

    # 从请求中获取认证信息并传递
    auth_header = request.headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = auth_header

    # 调用外部API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "keyWord": body.keyWord,
                    "compareType": body.compareType,
                },
                headers=headers,
            )

        if not response.is_success:
            error_detail = response.text
            logger.error(
                f"User info API failed: {response.status_code} - {error_detail}",
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"User info API error: {error_detail}",
            )

        data = response.json()
        return UserInfoQueryResponse(data=data)

    except httpx.TimeoutException as exc:
        logger.error(f"User info API timeout: {exc}")
        raise HTTPException(
            status_code=504,
            detail="User info API timeout",
        ) from exc
    except httpx.RequestError as exc:
        logger.error(f"User info API request error: {exc}")
        raise HTTPException(
            status_code=502,
            detail="User info API connection error",
        ) from exc


__all__ = ["router"]
