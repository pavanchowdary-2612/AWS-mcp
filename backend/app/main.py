"""
FastAPI application entry point.

Lifespan:
  - On startup: verify Redis connection, warm up OIDC discovery cache.
  - On shutdown: close Redis connection pool.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.cache.redis_client import get_redis
from app.auth.oidc import _fetch_discovery
from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting AWS Chatbot backend (model: %s)", settings.groq_model)

    # Warm up Redis
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection OK at %s", settings.redis_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis not reachable at startup: %s", exc)

    # Warm up OIDC discovery (caches the document module-level)
    try:
        _fetch_discovery()
        logger.info(
            "OIDC discovery loaded from %s", settings.identity_center_issuer_url
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OIDC discovery warm-up failed (will retry on first request): %s", exc)

    yield

    # Cleanup
    from app.cache.redis_client import _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        logger.info("Redis connection pool closed.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Enterprise AWS AI Chatbot",
        description="Natural-language interface to AWS resources via MCP and IAM Identity Center.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS — only allow the configured frontend origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/health", tags=["ops"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
