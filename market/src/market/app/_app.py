# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..__version__ import __version__
from ..config.constant import DOCS_ENABLED, CORS_ORIGINS
from ..database.config import get_database_config
from ..database.connection import DatabaseConnection
from .routers import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    logger.info("Market service starting up...")
    logger.info(f"Environment: {os.environ.get('MARKET_ENV', 'prd')}")

    db_config = get_database_config()
    db = DatabaseConnection(db_config)
    if db_config.host:
        try:
            await db.connect()
            if not db.is_connected:
                raise RuntimeError(
                    "Database connection failed after connect(). Check DB config.",
                )
            logger.info("Database connection established: %s", db_config.host)
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Failed to initialize database connection: %s", e)
            raise RuntimeError(
                "Database connection is required. Check database configuration.",
            ) from e
    else:
        logger.info("Database connection disabled (no host configured)")
    fastapi_app.state.db = db

    marketplace_root = Path(
        os.environ.get(
            "MARKET_MARKETPLACE_ROOT",
            str(Path.home() / ".swe.marketplace"),
        ),
    )
    swe_root = Path(
        os.environ.get("MARKET_SWE_ROOT", str(Path.home() / ".swe")),
    )
    from ..marketplace.service import MarketplaceService

    fastapi_app.state.marketplace = MarketplaceService(
        db=db,
        marketplace_root=marketplace_root,
        swe_root=swe_root,
    )

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
