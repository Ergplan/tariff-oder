"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .adapters import build_adapters
from .config import Settings, get_settings
from .db import dispose_db, init_db
from .errors import AppError
from .routers import health, jobs, profiles, registry, sources
from .schemas import ErrorResponse, Me
from .telemetry import actor_var, configure_logging, request_id_var

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.deployment_profile.value, settings.log_format, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings)
        log.info(
            "api started",
            extra={
                "profile": settings.deployment_profile.value,
                "adapters": app.state.adapters.describe(),
                "version": __version__,
            },
        )
        yield
        dispose_db()

    app = FastAPI(
        title="Tariff Order Intelligence API",
        version=__version__,
        description=(
            "Data service: sources, inventory, jobs, registry.  "
            "Candidates and facts arrive in later milestones as separate resources."
        ),
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    # Settings and adapters are built eagerly rather than in the lifespan handler, so that
    # anything holding the app object sees the same adapters whether or not lifespan has run.
    app.state.settings = settings
    app.state.adapters = build_adapters(settings)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        actor_token = actor_var.set(None)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            response = JSONResponse(status_code=500, content=AppError("internal_error").to_payload(rid))
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-Id"] = rid
        if request.url.path not in ("/healthz", "/readyz"):
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        request_id_var.reset(token)
        actor_var.reset(actor_token)
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        rid = request_id_var.get()
        if exc.spec.severity in ("error", "critical"):
            log.error("app error", extra={"error_type": exc.error_type, "detail": exc.detail})
        return JSONResponse(status_code=exc.spec.http_status, content=exc.to_payload(rid))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        payload = AppError(
            "validation_failed",
            detail="; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()),
        ).to_payload(request_id_var.get())
        return JSONResponse(status_code=422, content=payload)

    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(jobs.router)
    app.include_router(registry.router)
    app.include_router(profiles.router)

    from fastapi import Depends

    from .auth import current_principal

    @app.get("/me", response_model=Me, tags=["identity"])
    def me(principal=Depends(current_principal)) -> Me:
        return Me(email=principal.email, role=principal.role, provider=principal.provider)

    return app


app = create_app() if __name__ == "tariff_api.main_autoload" else None  # placeholder; use factory
