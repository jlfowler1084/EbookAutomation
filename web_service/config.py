"""Web service configuration — loads config/settings.json and environment variables.

All tool paths come from config/settings.json (matching the existing pipeline pattern).
Secrets (Stripe, Anthropic API key) come exclusively from environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


def _resolve_calibre_path(paths: dict) -> Path:
    """Resolve the Calibre ebook-convert path with cross-platform fallback.

    Discovered during EB-245 integration testing: a Windows-default
    `settings.json` (paths.calibre = `C:\\Program Files\\Calibre2\\ebook-convert.exe`)
    deployed to a Linux VM resolves to a non-existent path. The previous code
    trusted the configured value and only stripped the `.exe` suffix, which left
    `subprocess.run` trying to execute a path that doesn't exist.

    Resolution order:
        1. Use `paths.calibre` from settings.json if the file exists on disk
        2. Strip `.exe` on non-Windows and retry the existence check
        3. Fall back to `shutil.which("ebook-convert")` (Linux/macOS apt/brew installs)
        4. Last resort: return the configured value unchanged (subprocess.run will
           raise a clear FileNotFoundError, which is better than silent misbehavior)

    Same pattern as `tools/extract_tts_text.py:2995` — keep them in sync.
    """
    raw = str(paths.get("calibre", "ebook-convert"))
    if sys.platform != "win32" and raw.endswith(".exe"):
        raw = raw[:-4]
    if Path(raw).is_file():
        return Path(raw)
    fallback = shutil.which("ebook-convert")
    if fallback:
        return Path(fallback)
    return Path(raw)


def _resolve_python_path(paths: dict) -> Path:
    """Resolve the Python interpreter path with cross-platform fallback.

    Same EB-245 discovery as `_resolve_calibre_path`: a Windows-default
    `settings.json` (`paths.python = C:\\Users\\...\\python.exe`) deployed to a
    Linux VM resolved to a non-existent path, breaking the premium-tier
    subprocess invocation.

    Falls back to `sys.executable` (the currently-running interpreter) when the
    configured path doesn't exist. `sys.executable` is always valid because the
    web service is running through it.
    """
    raw = paths.get("python", sys.executable)
    if Path(raw).is_file():
        return Path(raw)
    return Path(sys.executable)

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
    # Stripe billing secrets — all required at startup (fail-closed via _require_env)
    stripe_price_power: str
    stripe_price_standard: str
    stripe_price_starter: str
    stripe_publishable_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    # Stripe API version pin (EB-227) — defaults to 2026-04-22.dahlia. Must match
    # the version configured on the Stripe webhook endpoint in Workbench.
    stripe_api_version: str
    # Token HMAC secret — required for token generation and validation
    token_hmac_secret: str
    allowed_origins: list[str] = field(default_factory=list)
    # EB-245: cost cap for input-side Gemini OCR remediation on premium tier.
    # Caps `--gemini-cost-limit` passed to extract_tts_text.py. $1.00 is generous —
    # typical --gemini-remediate run only re-extracts a handful of flagged pages
    # at ~$0.002/page, so most premium conversions stay well under this ceiling.
    premium_gemini_cost_limit_usd: float = 1.0
    # EB-245 Phase 4: output-side visual QA pass via tools/visual_qa.py.
    # Default OFF for first production rollout — flip via PREMIUM_VQA_ENABLED=true
    # once Gemini-only economics are observed in real traffic.
    premium_vqa_enabled: bool = False
    # Per-conversion VQA cost cap. visual_qa.py samples 8 pages by default at
    # ~$0.05-$0.10 per OpenRouter call, so $0.50 is generous headroom.
    premium_vqa_cost_limit_usd: float = 0.5


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

    # Cross-platform path resolution with shutil.which / sys.executable fallback.
    # The shared settings.json holds Windows defaults; on Linux VMs those paths
    # don't exist, so the helpers fall through to live system lookups. See the
    # docstrings on _resolve_calibre_path and _resolve_python_path for the
    # EB-245 discovery that motivated this.
    calibre_path = _resolve_calibre_path(paths)
    python_path = _resolve_python_path(paths)

    pipeline_script = _PROJECT_ROOT / "tools" / "extract_tts_text.py"

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
        stripe_price_power=_require_env("STRIPE_PRICE_POWER"),
        stripe_price_standard=_require_env("STRIPE_PRICE_STANDARD"),
        stripe_price_starter=_require_env("STRIPE_PRICE_STARTER"),
        stripe_publishable_key=_require_env("STRIPE_PUBLISHABLE_KEY"),
        stripe_secret_key=_require_env("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=_require_env("STRIPE_WEBHOOK_SECRET"),
        stripe_api_version=os.environ.get("STRIPE_API_VERSION", "2026-04-22.dahlia"),
        token_hmac_secret=_require_env("TOKEN_HMAC_SECRET"),
        allowed_origins=allowed_origins,
        premium_gemini_cost_limit_usd=float(
            os.environ.get("PREMIUM_GEMINI_COST_LIMIT_USD", "1.0")
        ),
        premium_vqa_enabled=os.environ.get("PREMIUM_VQA_ENABLED", "false").lower() == "true",
        premium_vqa_cost_limit_usd=float(
            os.environ.get("PREMIUM_VQA_COST_LIMIT_USD", "0.5")
        ),
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
