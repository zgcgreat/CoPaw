# -*- coding: utf-8 -*-
"""FastAPI 依赖注入."""
from typing import Annotated
from fastapi import Depends, Request
from ..database.connection import DatabaseConnection


def get_db(request: Request) -> DatabaseConnection:
    """从 app.state 获取数据库连接."""
    return request.app.state.db


DbDep = Annotated[DatabaseConnection, Depends(get_db)]
