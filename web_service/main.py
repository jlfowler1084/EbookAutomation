"""FastAPI application entry point.

Lifespan: initialises the DB and job queue on startup, cancels the cleanup
sweep on shutdown. CORS is configured from the WEB_SERVICE_ALLOWED_ORIGINS
environment variable (defaults to * for dev; tighten in production).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_service import job_queue, job_store
from web_service.config import get_settings
from web_service.routes import convert, download, status

log = logging.getLogger(__name__)

_sweep_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sweep_task
    settings = get_settings()
    job_store.init_db()
    job_queue.init_queue()
    _sweep_task = asyncio.create_task(job_queue.cleanup_expired_jobs())
    log.info("EbookAutomation web service started")
    yield
    if _sweep_task is not None:
        _sweep_task.cancel()
        try:
            await _sweep_task
        except asyncio.CancelledError:
            pass
    log.info("EbookAutomation web service stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="EbookAutomation Web Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(convert.router)
    application.include_router(status.router)
    application.include_router(download.router)
    return application


app = create_app()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
