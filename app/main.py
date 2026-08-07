import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.comments import router as comments_router
from app.api.v1.fields import router as fields_router
from app.api.v1.projects import router as projects_router
from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Never let a DB hiccup prevent the server from binding a port:
        # Render's health check requires the process to accept traffic, so
        # start cleanly and leave schema errors to the health/log path.
        try:
            await bootstrap_schema()
        except Exception:  # keep serving even if DB is down
            logger.exception("startup schema bootstrap failed")
    yield


async def bootstrap_schema() -> None:
    """Create tables + HNSW index idempotently on startup (zero-touch deploy)."""
    from sqlalchemy import text

    from app.core.database import engine
    from app.models import Base

    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:  # noqa: BLE001 - some hosts restrict extension creation
            logger.warning("could not CREATE EXTENSION vector (continuing)")
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migrations: CREATE TABLE won't alter existing tables.
        for ddl in (
            (
                "ALTER TABLE comment_records "
                "ADD COLUMN IF NOT EXISTS parent_comment_id VARCHAR(64)"
            ),
            (
                "ALTER TABLE jobs "
                "ADD COLUMN IF NOT EXISTS fetched_count INTEGER DEFAULT 0"
            ),
            (
                "ALTER TABLE jobs "
                "ADD COLUMN IF NOT EXISTS analyzed_count INTEGER DEFAULT 0"
            ),
        ):
            try:
                await conn.execute(text(ddl))
            except Exception:  # noqa: BLE001 - best-effort migration
                logger.warning("schema migration skipped: %s", ddl)
    logger.info("database schema ready")


app = FastAPI(title="CreatorOS Comment Analyzer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(comments_router)
app.include_router(fields_router)
app.include_router(projects_router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "request validation failed",
                "detail": _safe_validation_errors(exc.errors()),
            }
        },
    )


def _safe_validation_errors(errors: list) -> list[dict]:
    safe: list[dict] = []
    for err in errors:
        item = {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        ctx = err.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                k: (str(v) if not isinstance(v, (str, int, float, bool)) else v)
                for k, v in ctx.items()
            }
        safe.append(item)
    return safe


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "internal server error",
            }
        },
    )


@app.get("/health")
async def health():
    from redis.asyncio import Redis
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.database import engine

    checks: dict = {"status": "ok", "database": "unknown", "redis": "unknown"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
        checks["status"] = "degraded"
    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=5)
        await client.ping()
        await client.aclose()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"
        checks["status"] = "degraded"
    return checks
