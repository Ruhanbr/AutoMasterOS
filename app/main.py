import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AutoMasterException, to_http_exception
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

# ── Trace ID propagado pelo contexto da requisição ────────────────────────────
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("AutoMaster iniciando", version="1.0.0", env=settings.APP_ENV)
    yield
    logger.info("AutoMaster encerrando")


def create_application() -> FastAPI:
    app = FastAPI(
        title="AutoMaster API",
        description=(
            "SaaS para oficinas agrícolas com emissão de NF-e totalmente automática.\n\n"
            "**Header obrigatório:** `X-Tenant-ID: <uuid>` em todos os endpoints (exceto /tenants e /health)."
        ),
        version="1.0.0",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Observability: trace_id em todo log da requisição ─────────────────────
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        tid = str(uuid.uuid4())
        _trace_id_var.set(tid)
        start = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=tid,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        structlog.get_logger().info(
            "request_complete",
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        response.headers["X-Trace-ID"] = tid
        return response

    @app.exception_handler(AutoMasterException)
    async def automaster_exception_handler(
        request: Request, exc: AutoMasterException
    ) -> JSONResponse:
        http_exc = to_http_exception(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    # ─── Routers ──────────────────────────────────────────────────────────────
    from app.routers.auth import router as auth_router
    from app.routers.clients import router as clients_router
    from app.routers.invoices import router as invoices_router
    from app.routers.machines import router as machines_router
    from app.routers.service_orders import router as service_orders_router
    from app.routers.tenants import router as tenants_router
    from app.routers.users import router as users_router

    prefix = settings.API_V1_PREFIX
    app.include_router(auth_router, prefix=prefix)
    app.include_router(tenants_router, prefix=prefix)
    app.include_router(clients_router, prefix=prefix)
    app.include_router(machines_router, prefix=prefix)
    app.include_router(service_orders_router, prefix=prefix)
    app.include_router(invoices_router, prefix=prefix)
    app.include_router(users_router, prefix=prefix)

    from app.modules.financial.router import router as financial_router
    from app.modules.orchestration.router import router as orchestration_router
    from app.modules.reports.router import router as reports_router
    from app.modules.stock.router import router as stock_router
    from app.routers.public import router as public_router

    app.include_router(stock_router, prefix=prefix)
    app.include_router(financial_router, prefix=prefix)
    app.include_router(orchestration_router, prefix=prefix)
    app.include_router(reports_router, prefix=prefix)
    # Router público — sem autenticação (portal do cliente)
    app.include_router(public_router, prefix=prefix)

    # ── Health / Readiness ────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}

    @app.get("/ready", tags=["health"])
    async def readiness_check() -> dict:
        from app.core.database import get_db_session
        from app.core.redis_client import cache

        checks: dict[str, str] = {}

        try:
            gen = get_db_session()
            session = await gen.__anext__()
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["database"] = "ok"
            try:
                await gen.aclose()
            except Exception:
                pass
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        checks["redis"] = "ok" if await cache.ping() else "error"

        all_ok = all(v == "ok" for v in checks.values())
        status_code = 200 if all_ok else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if all_ok else "degraded", "checks": checks},
        )

    return app


app = create_application()
