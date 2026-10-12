"""FastAPI entry point."""

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from alpago.api.v1.router import api_router
from alpago.core.config import settings
from alpago.core.exceptions import DomainError
from alpago.core.logging import log, setup_logging
from alpago.core.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    setup_logging()
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)
    log.info("alpago.start", env=settings.env)
    yield
    log.info("alpago.stop")


app = FastAPI(
    title="Alpago HR Platform API",
    version="0.1.0",
    description="Hiring, approvals, and the full employee lifecycle for Alpago.",
    lifespan=lifespan,
)

# Order matters: security headers outermost, then rate limit, then CORS
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://alpago-web.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(DomainError)
async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://alpago-hr/errors/{exc.code}",
            "title": exc.code.replace("_", " ").title(),
            "status": exc.status_code,
            "detail": str(exc),
            "instance": str(request.url.path),
            **({"extra": exc.detail} if exc.detail else {}),
        },
        media_type="application/problem+json",
    )


@app.get("/healthz", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "alpago-api", "env": settings.env}
