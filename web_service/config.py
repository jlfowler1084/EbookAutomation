"""Web service configuration — loads config/settings.json and environment variables.

All tool paths come from config/settings.json (matching the existing pipeline pattern).
Secrets (Stripe, Anthropic API key) come exclusively from environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require_env(name: str) -> str:
    """Return env var value or raise ConfigurationError naming the variable."""
    value = os.environ.get(name)
    if not value:
        raise ConfigurationError(
            f"Required environment variable '{name}' is not set. "
            f"Add it to /etc/web_service.env or export it before starting the server."
        )
    return value


@dataclass(frozen=True)
class Settings:
    project_root: Path
    calibre_path: Path
    python_path: Path
    pipeline_script: Path
    db_path: Path
    temp_dir: Path
    output_dir: Path
    max_file_size_free: int       # bytes — 20 MB
    max_file_size_premium: int    # bytes — 100 MB
    max_concurrent_jobs: int
    job_ttl_free: int             # seconds — 1 hour
    job_ttl_premium: int          # seconds — 24 hours
    allowed_origins: list[str] = field(default_factory=list)


def load_settings() -> Settings:
    """Load Settings from config/settings.json and environment variables."""
    settings_path = _PROJECT_ROOT / "config" / "settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(
            f"Pipeline config not found: {settings_path}. "
            "Ensure config/settings.json exists at the project root."
        )

    with open(settings_path, encoding="utf-8") as f:
        cfg = json.load(f)

    paths = cfg.get("paths", {})

    # Strip .exe suffix on non-Windows — matches EB-221/EB-224 fix pattern
    calibre_raw = paths.get("calibre", "ebook-convert")
    if sys.platform != "win32" and str(calibre_raw).endswith(".exe"):
        calibre_raw = str(calibre_raw)[:-4]
    calibre_path = Path(calibre_raw)

    python_path = Path(paths.get("python", sys.executable))

    pipeline_script = _PROJECT_ROOT / "tools" / "pdf_to_balabolka.py"

    db_path = _PROJECT_ROOT / "data" / "web_service.db"

    temp_dir = Path(tempfile.gettempdir()) / "web_service_jobs"

    # Resolve output dir — relative paths are anchored to project root
    output_dir_raw = paths.get("kindle", "output/kindle")
    output_dir_path = Path(output_dir_raw)
    output_dir = (
        output_dir_path if output_dir_path.is_absolute()
        else _PROJECT_ROOT / output_dir_path
    )

    allowed_origins_raw = os.environ.get("WEB_SERVICE_ALLOWED_ORIGINS", "")
    allowed_origins = (
        [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
        if allowed_origins_raw
        else ["*"]
    )

    return Settings(
        project_root=_PROJECT_ROOT,
        calibre_path=calibre_path,
        python_path=python_path,
        pipeline_script=pipeline_script,
        db_path=db_path,
        temp_dir=temp_dir,
        output_dir=output_dir,
        max_file_size_free=20 * 1024 * 1024,
        max_file_size_premium=100 * 1024 * 1024,
        max_concurrent_jobs=int(os.environ.get("WEB_MAX_CONCURRENT_JOBS", "3")),
        job_ttl_free=int(os.environ.get("WEB_JOB_TTL_FREE", "3600")),
        job_ttl_premium=int(os.environ.get("WEB_JOB_TTL_PREMIUM", "86400")),
        allowed_origins=allowed_origins,
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings singleton, loading on first call."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Clear the settings cache — used in tests to reload from a temp config."""
    global _settings
    _settings = None
