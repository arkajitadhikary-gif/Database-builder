import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db import models  # noqa: F401 - registers all ORM models
from app.db.session import check_database, check_database_schema, engine
from app.services.embeddings import check_embedding_provider
from app.services.pdf import ocr_available
from app.workers.ingestion import resume_incomplete_batches


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.reference_root.mkdir(parents=True, exist_ok=True)
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    database_ok, _ = await check_database()
    if database_ok:
        app.state.recovery_task = asyncio.create_task(_recover_guarded())
    yield
    recovery_task = getattr(app.state, "recovery_task", None)
    if recovery_task is not None:
        recovery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recovery_task
    await engine.dispose()


settings = get_settings()
logger = logging.getLogger("judicore")


async def _recover_guarded() -> None:
    try:
        await resume_incomplete_batches()
    except Exception:
        logger.exception("durable ingestion recovery failed")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://localhost:1420", "http://127.0.0.1:1420"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def localhost_session_guard(request: Request, call_next):
    configured_token = settings.session_token
    if configured_token and request.url.path != "/api/v1/health/live":
        supplied = request.headers.get("authorization", "")
        if supplied != f"Bearer {configured_token}":
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)


@app.get("/api/v1/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "READY", "service": "backend"}


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, object]:
    database_ok, database_detail = await check_database()
    schema_ok, schema_detail = (
        await check_database_schema() if database_ok else (False, "database unavailable")
    )
    embedding_ok, embedding_detail = await asyncio.to_thread(check_embedding_provider)
    ocr_ok, ocr_detail = ocr_available()
    checks: dict[str, dict[str, str]] = {
        "backend": {"status": "READY", "detail": "FastAPI process is running"},
        "postgresql": {
            "status": "READY" if database_ok else "ERROR",
            "detail": database_detail,
        },
        "schema": {
            "status": "READY" if schema_ok else "NOT CONFIGURED",
            "detail": schema_detail,
        },
        "ocr": {
            "status": "READY" if settings.ocr_enabled and ocr_ok else "NOT CONFIGURED",
            "detail": ocr_detail if settings.ocr_enabled else "OCR is disabled by configuration",
        },
        "embedding": {
            "status": "READY" if embedding_ok else "NOT CONFIGURED",
            "detail": embedding_detail,
        },
        "storage": {
            "status": "READY" if settings.reference_root.exists() else "ERROR",
            "detail": str(settings.reference_root.resolve()),
        },
    }
    if not database_ok:
        overall = "ERROR"
    elif not schema_ok or checks["storage"]["status"] != "READY" or not embedding_ok:
        overall = "WARNING"
    else:
        overall = "READY"
    return {"status": overall, "checks": checks}


app.include_router(api_router, prefix="/api/v1")
