"""
app.main
~~~~~~~~~
FastAPI application factory for Omni_CortexX.

Wires together:
• CORS middleware
• structured logging
• request-ID middleware
• API routes (REST + WebSocket)
• exception handlers
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_diagnosis import router as diagnosis_router
from app.api.websocket import router as ws_router
from app.core.config import get_settings
from app.core.exceptions import OmniCortexError
from app.core.logging import (
    generate_request_id,
    get_logger,
    request_id_ctx,
    setup_logging,
)

logger = get_logger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        json_output=settings.app_env == "production",
    )
    logger.info(
        "app_startup",
        env=settings.app_env,
        debug=settings.app_debug,
        featherless_keys=len(settings.featherless_api_keys),
        budget_per_key=settings.featherless_budget_per_key,
        total_budget=len(settings.featherless_api_keys) * settings.featherless_budget_per_key,
        triage_models=len(settings.triage_models),
    )
    yield
    logger.info("app_shutdown")


# ── App factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Omni_CortexX",
        description="Medical Diagnostic Multi-Agent Debate System",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
    )

    # ── CORS ─────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request-ID Middleware ────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or generate_request_id()
        request_id_ctx.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    # ── Exception Handlers ──────────────────────────────────────
    @app.exception_handler(OmniCortexError)
    async def omni_error_handler(request: Request, exc: OmniCortexError):
        logger.error(
            "api_error",
            error=str(exc),
            error_type=type(exc).__name__,
            details=exc.details,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": type(exc).__name__,
                "detail": str(exc),
                "request_id": request_id_ctx.get(),
            },
        )

    # ── Routes ──────────────────────────────────────────────────
    app.include_router(diagnosis_router)
    app.include_router(ws_router)

    return app


# ── Module-level app instance for uvicorn ────────────────────────────
app = create_app()
