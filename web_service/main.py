"""FastAPI application entry point.

Lifespan: initialises the DB and job queue on startup, cancels the cleanup
sweep on shutdown. CORS is configured from the WEB_SERVICE_ALLOWED_ORIGINS
environment variable (defaults to * for dev; tighten in production).

Startup checks (Unit 1):
  - NTP sync: logs ERROR if not synchronized but continues (refusing boot is worse).
    Result surfaced in /health as ntp_synced.
  - Env mismatch: warns if STRIPE_PUBLISHABLE_KEY / STRIPE_SECRET_KEY prefixes
    don't match (test vs live mode mismatch).
  - Middleware safety: warns if non-allowlisted middleware is present (forward-looking
    guard for Unit 4 webhook handler which requires raw body access).
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_service import job_queue, job_store
from web_service.config import get_settings
from web_service.routes import convert, download, status

log = logging.getLogger(__name__)

_sweep_task: asyncio.Task | None = None

# Module-level NTP state — set during lifespan startup, read by /health
_ntp_synced: bool = True

# Middleware classes that are allowlisted for raw-body safety (Unit 4 guard)
_MIDDLEWARE_ALLOWLIST = {"CORSMiddleware"}


def _check_ntp_sync() -> bool:
    """Return True if system NTP is synchronized; False otherwise.

    Tries the systemd timesync sentinel file first (fast, no subprocess).
    Falls back to timedatectl for distros without the sentinel.
    Treats any error as "unknown — assume synced" to avoid false alarms on
    non-systemd hosts (macOS, Windows dev machines).
    """
    sentinel = Path("/run/systemd/timesync/synchronized")
    try:
        if sentinel.exists():
            return True
        # File absent — may mean not synced, or may mean non-systemd host.
        # Fall through to timedatectl.
        result = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip().lower() == "yes"
    except FileNotFoundError:
        # timedatectl not available (Windows dev, macOS) — assume synced
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("NTP check failed with unexpected error: %s", exc)
        return True


def _check_stripe_env_mismatch() -> None:
    """Warn if Stripe key prefixes suggest a test/live environment mismatch."""
    pub_key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    sec_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not pub_key or not sec_key:
        return  # Missing keys handled by _require_env at Settings load time

    pub_prefix = pub_key[:7]
    sec_prefix = sec_key[:7]

    pub_live = pub_key.startswith("pk_live_")
    sec_live = sec_key.startswith("sk_live_")
    pub_test = pub_key.startswith("pk_test_")
    sec_test = sec_key.startswith("sk_test_")

    if (pub_live and sec_live) or (pub_test and sec_test):
        return  # Keys match — no warning needed

    log.warning(
        "Stripe key environment mismatch detected: "
        "STRIPE_PUBLISHABLE_KEY prefix=%r, STRIPE_SECRET_KEY prefix=%r. "
        "Ensure both keys are from the same Stripe mode (test or live).",
        pub_prefix,
        sec_prefix,
    )


def _check_middleware_safety(application: FastAPI) -> None:
    """Warn if non-allowlisted middleware is present.

    Forward-looking guard for Unit 4's webhook handler, which depends on
    raw body access via request.stream(). Any middleware that consumes the
    request body (e.g. body-logging middleware) will break webhook signature
    validation. Surface the warning now so it's caught before Unit 4 ships.
    """
    for middleware_entry in application.user_middleware:
        cls = middleware_entry.cls
        cls_name = getattr(cls, "__name__", str(cls))
        if cls_name not in _MIDDLEWARE_ALLOWLIST:
            log.warning(
                "Non-allowlisted middleware detected: %r. "
                "If this middleware consumes request.stream(), it will break "
                "the /stripe/webhook raw-body signature validation (Unit 4). "
                "Review before shipping the webhook handler.",
                cls_name,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sweep_task, _ntp_synced
    settings = get_settings()

    # --- Startup check 1: NTP synchronization ---
    _ntp_synced = _check_ntp_sync()
    if not _ntp_synced:
        log.error(
            "NTP is not synchronized. Stripe webhook timestamp validation "
            "uses wall-clock time; clock drift > 300s causes webhook rejection. "
            "Run: timedatectl set-ntp true  (or equivalent). "
            "Service will continue starting — this is a WARNING, not a fatal error."
        )

    # --- Startup check 2: Stripe env mismatch ---
    _check_stripe_env_mismatch()

    # --- Startup check 3: Middleware safety ---
    _check_middleware_safety(app)

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
    return {"status": "ok", "ntp_synced": _ntp_synced}
