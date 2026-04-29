# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..__version__ import __version__
from ..config.constant import (
    DOCS_ENABLED,
    CORS_ORIGINS,
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_ACCESS,
    DB_NAME,
    DB_MIN_CONN,
    DB_MAX_CONN,
)
from ..database.connection import DatabaseConfig, DatabaseConnection
from .routers import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    logger.info("Market service starting up...")
    logger.info(f"Environment: {os.environ.get('MARKET_ENV', 'prd')}")

    db_config = DatabaseConfig(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_ACCESS,
        database=DB_NAME,
        min_connections=DB_MIN_CONN,
        max_connections=DB_MAX_CONN,
    )
    db = DatabaseConnection(db_config)
    if DB_HOST:
        try:
            await db.connect()
        except Exception as e:
            logger.warning("DB connection failed (non-fatal): %s", e)
    fastapi_app.state.db = db

    yield

    await db.close()
    logger.info("Market service shutting down...")


app = FastAPI(
    title="Market",
    description="应用市场服务",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

if CORS_ORIGINS:
    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api")
