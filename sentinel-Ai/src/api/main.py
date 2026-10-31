"""
FastAPI AI Engine — Layer 3 internal service.

This service is NEVER exposed to users directly.
It accepts internal HTTP requests from Spring Boot only.
Service auth: shared secret (X-Service-Token); optional mTLS at the proxy.
Per-user rate limits and user_id audit/tenant scoping on /v1/*.
No user JWT/RBAC, persistence, or session management here.

Startup sequence:
1. Lifespan context runs _build_compiled_graph() once.
2. Graph is cached via lru_cache in dependencies.py.
3. Routers are registered — each injects the cached graph via Depends().
"""

from __future__ import annotations
import sys

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api.dependencies import _build_compiled_graph
from src.api.routers import chat, documents, knowledge
from src.api.schemas.responses import ErrorApiResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
    }
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — graph built once here, never per request
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup: build and cache the compiled LangGraph.
    Shutdown: nothing to teardown — graph is stateless between requests.
    """
    logger.info("Sentinel AI Engine starting up.")
    try:
        _build_compiled_graph()
        logger.info("Sentinel AI Engine ready to accept requests.")
    except Exception:
        logger.exception("FATAL: failed to build compiled LangGraph at startup.")
        sys.exit(1)
    yield
    logger.info("Sentinel AI Engine shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sentinel AI Engine",
    description=(
        "Internal AI service. Accepts requests from Spring Boot only. "
        "Requires X-Service-Token on /v1/*. "
        "Never expose this service directly to users or the public internet."
    ),
    version="1.0.0",
    docs_url="/internal/docs",
    redoc_url="/internal/redoc",
    openapi_url="/internal/openapi.json",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Global exception handler — never leak stack traces to Spring Boot
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorApiResponse(
            request_id="unknown",
            error_code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(knowledge.router)


# ---------------------------------------------------------------------------
# Health check — for Spring Boot to verify the AI engine is alive
# ---------------------------------------------------------------------------
@app.get("/internal/health", tags=["internal"])
async def health_check() -> JSONResponse:
    import time
    import os
    checks: dict[str, str] = {}

    # Check 1 — LLM config present
    api_key = os.getenv("GOOGLE_API_KEY", "")
    checks["llm"] = "ok" if api_key.strip() else "misconfigured"

    # Check 2 — ChromaDB reachable
    try:
        from src.api.dependencies import _build_compiled_graph
        _build_compiled_graph()
        checks["graph"] = "ok"
    except Exception:
        checks["graph"] = "error"

    # Check 3 — Model name
    checks["model"] = os.getenv("LLM_MODEL", "unknown")

    overall = "ok" if all(v == "ok" for v in checks.values() if v != checks["model"]) else "degraded"

    return JSONResponse(
        status_code=status.HTTP_200_OK if overall == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": overall,
            "service": "sentinel-ai-engine",
            "checks": checks,
        },
    )