#!/usr/bin/env python3
"""tools/scan_bench.py — EB-392 Phase 0 scan-bench benchmark harness.

A fixed 13-book corpus (``data/scan_bench/manifest.json``) mirrors the
production PDF-to-KFX conversion path plus local-only VQA so every later
EB-391 phase is measured against the same books the same way. See
``data/scan_bench/README.md`` for the operator runbook and
``docs/plans/2026-09-05-001-feat-eb392-phase0-scan-bench-plan.md`` for the
full design.

This module implements Unit 3 (the ``preflight`` subcommand, which refuses to
start a run whose results could not be trusted) and the shared skeleton Unit 4
extends (``run`` / ``compare`` / ``report`` / ``promote``, stubbed here).

Exit codes (``preflight``, computed by ``compute_exit_code``):
    0 — all checks PASS (INFO entries do not affect this)
    1 — at least one WARN, no FAIL
    2 — at least one FAIL
    3 — infra / argparse error (``ArgumentParser.error()`` is overridden to
        exit 3 rather than argparse's default 2, which this tool reserves for
        "blocking FAIL" — the eb370 convention)

Usage:
    python tools/scan_bench.py preflight --skip-vqa --allow-dirty
    python tools/scan_bench.py preflight --label row0-vqa --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# So ``from llm_providers.local_provider import LocalVisionProvider`` resolves
# regardless of the caller's cwd (mirrors tools/visual_qa.py, tools/batch_qa.py).
sys.path.insert(0, str(SCRIPT_DIR))

logger = logging.getLogger("scan_bench")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# A PDF at or below this size is treated as a download stub, not a real book
# (mirrors the "download stub threshold" language in the plan).
STUB_MIN_BYTES: int = 200_000

# Conservative fallback n_ctx used only when a probe totally fails and no
# result dict is available at all (mirrors local_provider.py's own
# CONSERVATIVE_UNKNOWN_N_CTX so preflight's degraded-path math agrees with
# the provider's).
CONSERVATIVE_UNKNOWN_N_CTX: int = 8192

# A minimal, valid 8x8 solid-white RGB PNG, hardcoded as base64 so the
# tiny-image preflight check never depends on PIL/Pillow being installed.
# NOTE: an 8x8 image was chosen over the more common "smallest possible"
# 1x1 web-placeholder PNG literal after live testing against sb-vision
# (llama.cpp / Qwen3-VL) on 2026-09-06: that famous 1x1 literal (RGBA,
# aggressively hand-optimized IDAT stream) is decoded fine by browsers and
# Python's own zlib/PNG readers but is rejected by the server's image loader
# with HTTP 400 "Failed to load image or audio file" -- a false FAIL that has
# nothing to do with vision support. A plain 8x8 RGB PNG generated with
# zlib.compress(..., 9) (no hand-optimization) round-trips cleanly on the
# same server. Generated once via zlib/struct (see the plan's "no PIL"
# constraint) -- not re-derived at runtime.
_TINY_PNG_B64: str = (
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAD0lEQVR42mP4jwMwDC0J"
    "ALoev0GJ6La7AAAAAElFTkSuQmCC"
)

REQUIRED_RUN_KEYS: tuple[str, ...] = (
    "schema_version", "provider", "vqa", "cloud_policy", "timeouts", "books",
)
REQUIRED_PROVIDER_KEYS: tuple[str, ...] = (
    "base_url", "model", "expected_min_n_ctx", "expected_total_slots",
)
REQUIRED_VQA_KEYS: tuple[str, ...] = (
    "dpi", "max_pages", "batch_size", "fallback_enabled",
)
REQUIRED_BOOK_KEYS: tuple[str, ...] = (
    "id", "track", "title", "source_path", "sha256", "size_bytes", "pages",
    "expected_class", "script", "known_failure", "timeout_overrides",
    "expected_chapters", "toc_source", "interpretation_flags",
)

# Cloud API keys the harness blanks in child environments unless the caller
# opts into --cloud-as-configured (Unit 4). Never logged by value.
CLOUD_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
)

_LOG_LEVEL_FOR_STATUS: dict[str, int] = {
    "PASS": logging.INFO,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "FAIL": logging.ERROR,
}


class ExitCode:
    """Process exit codes shared by every scan_bench subcommand."""

    OK = 0
    WARN = 1
    FAIL = 2
    ERROR = 3


# ---------------------------------------------------------------------------
# Check result type
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """One named preflight check outcome."""

    name: str
    status: str  # "PASS" | "WARN" | "FAIL" | "INFO"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def compute_exit_code(results: list[CheckResult]) -> int:
    """0 if every result is PASS/INFO, 1 if any WARN (no FAIL), 2 if any FAIL.

    Exit 3 (infra/argparse error) is never produced here — it is raised by
    ``_ExitCodeParser.error()`` or by an unhandled exception in ``main()``.
    """
    statuses = {r.status for r in results}
    if "FAIL" in statuses:
        return ExitCode.FAIL
    if "WARN" in statuses:
        return ExitCode.WARN
    return ExitCode.OK


def _overall_status_label(exit_code: int) -> str:
    return {ExitCode.OK: "OK", ExitCode.WARN: "WARN", ExitCode.FAIL: "FAIL"}.get(
        exit_code, "FAIL"
    )


# ---------------------------------------------------------------------------
# Manifest loading / schema validation
# ---------------------------------------------------------------------------

def manifest_path_default() -> Path:
    """Default manifest location: data/scan_bench/manifest.json."""
    return PROJECT_ROOT / "data" / "scan_bench" / "manifest.json"


def load_manifest(path: str | os.PathLike) -> dict:
    """Load and parse the manifest JSON. Raises OSError / json.JSONDecodeError."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest_schema(manifest: dict) -> list[str]:
    """Return a list of schema-violation messages (empty == valid).

    Checks run-wide required keys, the provider/vqa sub-blocks, per-book
    required keys, and book id uniqueness. Never raises — a malformed
    manifest produces violation strings, not an exception.
    """
    errors: list[str] = []

    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]

    for key in REQUIRED_RUN_KEYS:
        if key not in manifest:
            errors.append(f"missing run-wide key: {key!r}")

    provider = manifest.get("provider")
    if provider is None:
        pass  # already reported by the run-wide key check above
    elif not isinstance(provider, dict):
        errors.append("'provider' must be an object")
    else:
        for key in REQUIRED_PROVIDER_KEYS:
            if key not in provider:
                errors.append(f"missing provider.{key}")

    vqa = manifest.get("vqa")
    if vqa is None:
        pass
    elif not isinstance(vqa, dict):
        errors.append("'vqa' must be an object")
    else:
        for key in REQUIRED_VQA_KEYS:
            if key not in vqa:
                errors.append(f"missing vqa.{key}")

    books = manifest.get("books")
    if books is None:
        pass
    elif not isinstance(books, list):
        errors.append("'books' must be a list")
    else:
        seen_ids: set[Any] = set()
        for i, book in enumerate(books):
            if not isinstance(book, dict):
                errors.append(f"books[{i}] is not an object")
                continue
            for key in REQUIRED_BOOK_KEYS:
                if key not in book:
                    errors.append(f"books[{i}] (id={book.get('id', '?')!r}) missing key: {key}")
            bid = book.get("id")
            if bid is not None:
                if bid in seen_ids:
                    errors.append(f"duplicate book id: {bid!r}")
                seen_ids.add(bid)

    return errors


def _write_manifest(path: Path, manifest: dict) -> None:
    """Rewrite the manifest JSON in place: indent=2, ensure_ascii=False, LF only.

    Only mutates values (e.g. a book's ``sha256``) in place before calling
    this — never deletes/re-inserts keys — so key order is preserved (Python
    dicts, and therefore ``json.load``/``json.dump``, are insertion-ordered).
    """
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# sha256 / source-file checks
# ---------------------------------------------------------------------------

def sha256_file(path: str | os.PathLike, chunk_size: int = 1024 * 1024) -> str:
    """Stream a file through sha256 (safe for multi-hundred-MB PDFs)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sources(manifest: dict, write_sha: bool) -> tuple[list[CheckResult], bool]:
    """Per-book source-file checks: exists, is a .pdf, not a stub, sha256.

    Source paths are checked literally (``Path.is_file()``) — never globbed
    or fnmatch'd, per the plan (one benchmark source has ``[``/``]``/a curly
    apostrophe in its filename).

    Returns (per-book CheckResults, whether the manifest dict was mutated by
    ``--write-sha`` and needs to be persisted by the caller).
    """
    results: list[CheckResult] = []
    changed = False
    books = manifest.get("books")
    if not isinstance(books, list):
        return results, changed

    for book in books:
        if not isinstance(book, dict):
            continue
        bid = book.get("id", "?")
        name = f"source_{bid}"
        source_path = book.get("source_path")

        if not source_path or not Path(source_path).is_file():
            results.append(CheckResult(
                name, "FAIL", f"source missing for book {bid}: {source_path!r}",
            ))
            continue

        p = Path(source_path)
        if p.suffix.lower() != ".pdf":
            results.append(CheckResult(
                name, "FAIL", f"{bid}: source is not a .pdf (suffix {p.suffix!r}): {source_path}",
            ))
            continue

        actual_size = p.stat().st_size
        if actual_size <= STUB_MIN_BYTES:
            results.append(CheckResult(
                name, "FAIL",
                f"{bid}: file size {actual_size} bytes <= stub threshold "
                f"{STUB_MIN_BYTES} bytes (likely a download stub): {source_path}",
            ))
            continue

        status = "PASS"
        notes: list[str] = []

        expected_size = book.get("size_bytes")
        if isinstance(expected_size, int) and expected_size != actual_size:
            status = "WARN"
            notes.append(f"size_bytes mismatch (manifest {expected_size}, actual {actual_size})")

        sha = book.get("sha256")
        if not sha:
            if write_sha:
                computed = sha256_file(p)
                book["sha256"] = computed
                changed = True
                notes.append(f"sha256 computed and written: {computed}")
            else:
                status = "WARN" if status != "FAIL" else status
                notes.append("sha unset")
        else:
            computed = sha256_file(p)
            if computed != sha:
                status = "FAIL"
                notes.append(f"sha256 mismatch (manifest {sha}, computed {computed})")

        message = f"{bid}: " + ("; ".join(notes) if notes else "ok")
        results.append(CheckResult(name, status, message))

    return results, changed


# ---------------------------------------------------------------------------
# Endpoint probe / tiny-image check (injectable, network-touching)
# ---------------------------------------------------------------------------

def probe_endpoint(base_url: str, model: str | None) -> dict:
    """Probe the resolved local VQA endpoint via LocalVisionProvider.describe().

    Reuses the exact same provenance path every VQA report/verdict uses
    (EB-390/EB-392 Unit 1/2), so preflight's provider line matches what a run
    would actually record. Never raises: ``describe()`` itself degrades to a
    conservative/unknown result on total probe failure rather than throwing.

    Module-level and side-effect-free on import so tests can monkeypatch this
    name directly (``monkeypatch.setattr(scan_bench, "probe_endpoint", ...)``)
    and never touch the network.
    """
    from llm_providers.local_provider import LocalVisionProvider

    provider = LocalVisionProvider(base_url, model=model)
    return provider.describe(refresh=True)


def tiny_image_check(base_url: str, model: str | None) -> dict:
    """Send one minimal image chat-completion request to the resolved target.

    A text-only backend (e.g. a text LLM gateway with no vision route) can
    still answer ``/v1/models`` successfully but fails on any request
    containing an ``image_url`` content block — this is the ``.env``-override
    trap documented in CLAUDE.md (EB-390); this check is preflight's guard
    against it.

    Never raises; always returns ``{"ok": bool, ...}``. Module-level so tests
    can monkeypatch it and never touch the network.
    """
    try:
        import openai

        client = openai.OpenAI(base_url=base_url, api_key="not-needed")
        data_uri = f"data:image/png;base64,{_TINY_PNG_B64}"
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reply with one word: the color."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
            max_tokens=8,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=30,
        )
        content = response.choices[0].message.content
        return {"ok": True, "content": content}
    except Exception as exc:  # noqa: BLE001 - never fatal, always reported as a check result
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _compute_max_batch_size(base_url: str, model: str | None, n_ctx: int) -> int:
    """LocalVisionProvider.max_batch_size(n_ctx) with an explicit n_ctx never
    probes the network (see local_provider.py) — safe to call unconditionally.
    """
    from llm_providers.local_provider import LocalVisionProvider

    provider = LocalVisionProvider(base_url, model=model)
    return provider.max_batch_size(n_ctx=n_ctx)


def _check_endpoint_probe(base_url: str | None, model: str | None) -> tuple[dict | None, CheckResult]:
    if not base_url:
        return None, CheckResult("endpoint_probe", "FAIL", "manifest provider.base_url is missing")

    try:
        probe = probe_endpoint(base_url, model)
    except Exception as exc:  # noqa: BLE001
        return None, CheckResult(
            "endpoint_probe", "FAIL", f"probe raised {type(exc).__name__}: {exc}",
        )

    probe_ok = bool(probe.get("probe_ok"))
    model_served = probe.get("model_served")
    detail = (
        f"n_ctx={probe.get('n_ctx')} ({probe.get('n_ctx_source')}) "
        f"total_slots={probe.get('total_slots')} model_path={probe.get('model_path')}"
    )
    if not probe_ok or model_served != model:
        return probe, CheckResult(
            "endpoint_probe", "FAIL",
            f"probe_ok={probe_ok} model_served={model_served!r} (manifest model {model!r}); {detail}",
        )
    return probe, CheckResult(
        "endpoint_probe", "PASS", f"model_served={model_served!r}; {detail}",
    )


def _check_endpoint_tiny_image(base_url: str | None, model: str | None) -> CheckResult:
    if not base_url:
        return CheckResult("endpoint_tiny_image", "FAIL", "manifest provider.base_url is missing")

    try:
        result = tiny_image_check(base_url, model)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if result.get("ok"):
        return CheckResult(
            "endpoint_tiny_image", "PASS",
            f"tiny-image request succeeded: {result.get('content')!r}",
        )
    return CheckResult(
        "endpoint_tiny_image", "FAIL",
        f"tiny-image request failed ({result.get('error')}) -- a text-only backend "
        f"that answers /v1/models but has no vision route will fail here",
    )


# ---------------------------------------------------------------------------
# Row-0 regime checks
# ---------------------------------------------------------------------------

def _check_regime(
    *,
    base_url: str | None,
    model: str | None,
    n_ctx: int | None,
    total_slots: int | None,
    expected_min_n_ctx: int | None,
    expected_total_slots: int | None,
    expected_batch_size: int | None,
    strict_regime: bool,
    allow_degraded_batch: bool,
) -> list[CheckResult]:
    """n_ctx / total_slots / max_batch_size vs. the manifest's row-0 gates.

    strict_regime == True (grading AND (row0* label OR --strict)): a
    violation is FAIL, downgraded to WARN by --allow-degraded-batch.
    strict_regime == False (--skip-vqa, or a non-row0 label without
    --strict): a violation is always WARN.
    """
    results: list[CheckResult] = []

    def severity(violated: bool) -> str:
        if not violated:
            return "PASS"
        if strict_regime:
            return "WARN" if allow_degraded_batch else "FAIL"
        return "WARN"

    if isinstance(expected_min_n_ctx, int) and isinstance(n_ctx, int):
        violated = n_ctx < expected_min_n_ctx
        if violated:
            msg = (
                f"n_ctx {n_ctx} < expected_min_n_ctx {expected_min_n_ctx} -- "
                f"see SB-231 (raise sb-vision's served context window)"
            )
        else:
            msg = f"n_ctx {n_ctx} >= expected_min_n_ctx {expected_min_n_ctx}"
        results.append(CheckResult("regime_min_n_ctx", severity(violated), msg))
    else:
        results.append(CheckResult(
            "regime_min_n_ctx", "WARN",
            f"n_ctx ({n_ctx}) or provider.expected_min_n_ctx ({expected_min_n_ctx}) unknown; cannot evaluate",
        ))

    if isinstance(expected_total_slots, int) and isinstance(total_slots, int):
        violated = total_slots != expected_total_slots
        msg = (
            f"total_slots {total_slots} != expected_total_slots {expected_total_slots}" if violated
            else f"total_slots {total_slots} == expected_total_slots {expected_total_slots}"
        )
        results.append(CheckResult("regime_total_slots", severity(violated), msg))
    else:
        results.append(CheckResult(
            "regime_total_slots", "WARN",
            f"total_slots ({total_slots}) or provider.expected_total_slots "
            f"({expected_total_slots}) unknown; cannot evaluate",
        ))

    if isinstance(expected_batch_size, int) and isinstance(n_ctx, int) and base_url:
        try:
            max_batch = _compute_max_batch_size(base_url, model, n_ctx)
        except Exception as exc:  # noqa: BLE001
            results.append(CheckResult(
                "regime_batch_size", "WARN", f"could not compute max_batch_size: {exc}",
            ))
        else:
            violated = max_batch < expected_batch_size
            msg = (
                f"max_batch_size(n_ctx={n_ctx}) = {max_batch} < required vqa.batch_size {expected_batch_size}"
                if violated else
                f"max_batch_size(n_ctx={n_ctx}) = {max_batch} >= required vqa.batch_size {expected_batch_size}"
            )
            results.append(CheckResult("regime_batch_size", severity(violated), msg))
    else:
        results.append(CheckResult(
            "regime_batch_size", "WARN",
            "vqa.batch_size, n_ctx, or provider.base_url unknown; cannot evaluate",
        ))

    return results


# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------

def _check_env_local_llm(manifest_base_url: str | None, manifest_model: str | None) -> CheckResult:
    env_base = os.environ.get("LOCAL_LLM_BASE_URL")
    env_model = os.environ.get("LOCAL_LLM_VISION_MODEL")
    mismatches: list[str] = []
    if env_base and env_base != manifest_base_url:
        mismatches.append(f"LOCAL_LLM_BASE_URL env={env_base!r} manifest={manifest_base_url!r}")
    if env_model and env_model != manifest_model:
        mismatches.append(f"LOCAL_LLM_VISION_MODEL env={env_model!r} manifest={manifest_model!r}")

    if mismatches:
        return CheckResult(
            "env_local_llm", "WARN",
            "; ".join(mismatches) + " -- the harness pins its own child environment",
        )
    return CheckResult("env_local_llm", "PASS", "process env matches manifest (or is unset)")


def _check_env_cloud_keys() -> CheckResult:
    # Never log/print the values themselves — only whether each is present.
    present = [k for k in CLOUD_ENV_KEYS if os.environ.get(k)]
    if present:
        return CheckResult(
            "env_cloud_keys", "INFO",
            f"{', '.join(present)} present in process env -- will be blanked for "
            f"children (cloud_policy off)",
        )
    return CheckResult("env_cloud_keys", "PASS", "no cloud API keys present in process env")


# ---------------------------------------------------------------------------
# Git checks
# ---------------------------------------------------------------------------

def git_head_short(cwd: Path | None = None) -> str:
    """Short HEAD sha for the repo at cwd (default PROJECT_ROOT), or 'unknown'."""
    cwd = cwd or PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    sha = (result.stdout or "").strip()
    return sha or "unknown"


def git_ls_files_tracked(path: str | os.PathLike, cwd: Path | None = None) -> bool:
    """True if ``path`` is tracked in git (``git ls-files --error-unmatch``)."""
    cwd = cwd or PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def git_dirty_pipeline_files(cwd: Path | None = None) -> list[str]:
    """Modified/staged tracked files under tools/, module/, config/settings.json.

    Scoped via a git pathspec (untracked files elsewhere never appear in the
    output at all) *and* filters ``??`` (untracked) lines defensively, so an
    untracked file anywhere -- including under the always-dirty
    data/batch_reports/ tree -- never counts as dirty.
    """
    cwd = cwd or PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "tools/", "module/", "config/settings.json"],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []

    dirty: list[str] = []
    for line in (result.stdout or "").splitlines():
        if not line.strip():
            continue
        status = line[:2]
        if status == "??":
            continue
        dirty.append(line[3:].strip())
    return dirty


# ---------------------------------------------------------------------------
# Junction / symlink guard
# ---------------------------------------------------------------------------

def find_junctions(
    root: str | os.PathLike,
    skip: tuple[str, ...] = (".git", ".worktrees", "node_modules"),
) -> list[Path]:
    """Directories under root that are junctions or symlinks.

    Windows ``rmdir /s`` / PowerShell ``Remove-Item -Recurse`` traverse
    junctions and delete the *target*'s contents -- see the worktree-cleanup
    incident documented in CLAUDE.md. ``followlinks=False`` (os.walk's
    default) means a detected symlinked directory is still listed (so it can
    be flagged) but never descended into.
    """
    root = str(root)
    hits: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for d in dirnames:
            full = os.path.join(dirpath, d)
            is_junction = False
            if hasattr(os.path, "isjunction"):
                try:
                    is_junction = os.path.isjunction(full)
                except OSError:
                    is_junction = False
            try:
                is_link = os.path.islink(full)
            except OSError:
                is_link = False
            if is_junction or is_link:
                hits.append(Path(full))
    return hits


# ---------------------------------------------------------------------------
# Local tool availability
# ---------------------------------------------------------------------------

def load_settings_json() -> dict:
    """Load config/settings.json (pipeline config, not .claude/settings.json)."""
    settings_path = PROJECT_ROOT / "config" / "settings.json"
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("scan_bench: could not load %s: %s", settings_path, exc)
        return {}


def _resolve_config_path(value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def _check_tools() -> list[CheckResult]:
    results: list[CheckResult] = []

    pwsh_path = shutil.which("pwsh")
    if pwsh_path:
        results.append(CheckResult("tool_pwsh", "PASS", f"pwsh found: {pwsh_path}"))
    else:
        results.append(CheckResult("tool_pwsh", "FAIL", "pwsh (PowerShell 7) not found on PATH"))

    settings = load_settings_json()
    paths_cfg = settings.get("paths", {}) if isinstance(settings, dict) else {}
    for key, check_name in (
        ("calibre", "tool_calibre"), ("poppler", "tool_poppler"), ("tesseract", "tool_tesseract"),
    ):
        raw = paths_cfg.get(key)
        if not raw:
            results.append(CheckResult(check_name, "FAIL", f"config/settings.json paths.{key} is not set"))
            continue
        resolved = _resolve_config_path(raw)
        if resolved.exists():
            results.append(CheckResult(check_name, "PASS", f"{key} found: {resolved}"))
        else:
            results.append(CheckResult(
                check_name, "FAIL", f"{key} not found at {resolved} (paths.{key}={raw!r})",
            ))

    return results


# ---------------------------------------------------------------------------
# Determinism verdict check (optional)
# ---------------------------------------------------------------------------

def _check_determinism_verdict(path: Path, provider_cfg: dict) -> CheckResult:
    """Validate a vqa_determinism_check.py JSON verdict against the manifest.

    FAILs when the verdict is non-deterministic / could-not-assess (both
    collapse ``deterministic`` to False -- see vqa_determinism_check.py's
    ``run_determinism_check``/``verdict_to_exit_code``), or when the
    verdict's resolved provider (``provider_resolved`` on a single-run
    report shape, or ``provider_resolved_runs[0]`` on the verdict shape)
    disagrees with the manifest's base_url/model. A verdict with no
    provider_resolved data at all (older schema) cannot be cross-checked and
    is noted, not failed, on that basis alone.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            verdict = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult("determinism_verdict", "FAIL", f"could not load {path}: {exc}")

    if not isinstance(verdict, dict):
        return CheckResult("determinism_verdict", "FAIL", f"{path} does not contain a JSON object")

    reasons: list[str] = []

    if "deterministic" in verdict:
        is_deterministic = bool(verdict.get("deterministic"))
    else:
        is_deterministic = verdict.get("exit_code") == 0
    if not is_deterministic:
        reasons.append(
            "verdict reports non-deterministic (or could-not-assess) grading -- "
            "see docs/solutions/eb361-vqa-grader-determinism-self-check-2026-06-02.md"
        )

    provider_resolved = verdict.get("provider_resolved")
    if not isinstance(provider_resolved, dict):
        runs = verdict.get("provider_resolved_runs")
        if isinstance(runs, list) and runs and isinstance(runs[0], dict):
            provider_resolved = runs[0]
        else:
            provider_resolved = None

    note = ""
    if isinstance(provider_resolved, dict):
        v_base = provider_resolved.get("base_url")
        v_model = provider_resolved.get("model_served")
        m_base = provider_cfg.get("base_url")
        m_model = provider_cfg.get("model")
        if v_base is not None and v_base != m_base:
            reasons.append(
                f"verdict provider_resolved.base_url {v_base!r} != manifest provider.base_url {m_base!r}"
            )
        if v_model is not None and v_model != m_model:
            reasons.append(
                f"verdict provider_resolved.model_served {v_model!r} != manifest provider.model {m_model!r}"
            )
    else:
        note = (
            " (verdict has no provider_resolved data -- cannot confirm target match; "
            "re-run vqa_determinism_check.py after EB-390 lands)"
        )

    if reasons:
        return CheckResult("determinism_verdict", "FAIL", "; ".join(reasons))
    return CheckResult("determinism_verdict", "PASS", f"verdict deterministic{note}")


# ---------------------------------------------------------------------------
# Timeout helpers
# ---------------------------------------------------------------------------

def scaled_convert_timeout(
    size_bytes: int,
    expected_class: str | None,
    timeouts: dict,
    overrides: dict | None = None,
) -> int:
    """Size-scaled conversion timeout, per manifest.timeouts / book overrides.

    ``convert_base_s + convert_per_mb_s * (size_mb - convert_mb_threshold)``
    once size exceeds the threshold; floored at ``convert_scan_floor_s`` for
    ``scan_*``-classed books; ``overrides["convert_s"]`` wins outright.
    """
    overrides = overrides or {}
    if overrides.get("convert_s") is not None:
        return int(overrides["convert_s"])

    base = timeouts.get("convert_base_s", 600)
    per_mb = timeouts.get("convert_per_mb_s", 10)
    threshold_mb = timeouts.get("convert_mb_threshold", 20)
    scan_floor = timeouts.get("convert_scan_floor_s", 1200)

    size_mb = (size_bytes or 0) / (1024 * 1024)
    timeout = base
    if size_mb > threshold_mb:
        timeout = base + per_mb * (size_mb - threshold_mb)

    if isinstance(expected_class, str) and expected_class.startswith("scan_"):
        timeout = max(timeout, scan_floor)

    return int(round(timeout))


def scaled_vqa_timeout(
    output_bytes: int,
    pages: int,
    timeouts: dict,
    overrides: dict | None = None,
) -> int:
    """VQA-stage timeout: ``vqa_base_s + vqa_per_page_s * pages``.

    ``output_bytes`` is accepted (the manifest schema reserves a size-based
    knob for future use) but is not part of the current formula (README);
    ``overrides["vqa_s"]`` wins outright.
    """
    del output_bytes  # reserved, not used by the current formula
    overrides = overrides or {}
    if overrides.get("vqa_s") is not None:
        return int(overrides["vqa_s"])

    base = timeouts.get("vqa_base_s", 900)
    per_page = timeouts.get("vqa_per_page_s", 2)

    return int(round(base + per_page * (pages or 0)))


# ---------------------------------------------------------------------------
# Child environment
# ---------------------------------------------------------------------------

def child_env(
    manifest: dict,
    probed_n_ctx: int,
    cloud_as_configured: bool = False,
    temp_dir: str | os.PathLike | None = None,
) -> dict[str, str]:
    """A copy of os.environ with the harness's provider/cloud/TEMP pins applied.

    Never mutates ``os.environ`` itself. Cloud keys are set to empty strings
    (never deleted) unless ``cloud_as_configured`` — an empty string beats
    ``.env`` under ``load_dotenv(..., override=False)`` and is falsy in both
    Python and PowerShell.
    """
    env = dict(os.environ)
    provider = manifest.get("provider", {}) if isinstance(manifest.get("provider"), dict) else {}
    env["LOCAL_LLM_BASE_URL"] = str(provider.get("base_url", ""))
    env["LOCAL_LLM_VISION_MODEL"] = str(provider.get("model", ""))
    env["LOCAL_LLM_N_CTX"] = str(probed_n_ctx)

    if not cloud_as_configured:
        for key in CLOUD_ENV_KEYS:
            env[key] = ""

    if temp_dir is not None:
        env["TEMP"] = str(temp_dir)
        env["TMP"] = str(temp_dir)

    return env


# ---------------------------------------------------------------------------
# Preflight orchestration
# ---------------------------------------------------------------------------

def run_preflight_checks(
    manifest: dict,
    manifest_path: Path,
    args: argparse.Namespace,
) -> tuple[list[CheckResult], dict[str, Any]]:
    """Run every Unit 3 preflight check and return (results, extra metadata).

    ``extra`` carries data useful for --json output and for a caller
    (Unit 4's ``run``) that wants the resolved n_ctx/provider without
    re-probing: manifest_path, git_head, label, allow_degraded_batch, the
    probed n_ctx/total_slots, and the resolved provider block.
    """
    results: list[CheckResult] = []

    # 1. manifest tracked
    tracked = git_ls_files_tracked(manifest_path)
    if tracked:
        results.append(CheckResult("manifest_tracked", "PASS", f"{manifest_path} is tracked in git"))
    else:
        results.append(CheckResult(
            "manifest_tracked", "FAIL",
            f"{manifest_path} is NOT tracked in git (git ls-files --error-unmatch failed)",
        ))

    # 2. manifest schema
    schema_errors = validate_manifest_schema(manifest)
    if schema_errors:
        results.append(CheckResult("manifest_schema", "FAIL", "; ".join(schema_errors)))
    else:
        n_books = len(manifest.get("books", []))
        results.append(CheckResult("manifest_schema", "PASS", f"schema OK ({n_books} books)"))

    # 3. sources (one CheckResult per book)
    source_results, manifest_changed = check_sources(manifest, write_sha=bool(args.write_sha))
    results.extend(source_results)
    if manifest_changed:
        _write_manifest(manifest_path, manifest)

    # 4. endpoint probe + tiny-image
    provider_cfg = manifest.get("provider", {}) if isinstance(manifest.get("provider"), dict) else {}
    base_url = provider_cfg.get("base_url")
    model = provider_cfg.get("model")

    probe_result, probe_check = _check_endpoint_probe(base_url, model)
    results.append(probe_check)
    results.append(_check_endpoint_tiny_image(base_url, model))

    n_ctx = probe_result.get("n_ctx") if probe_result else CONSERVATIVE_UNKNOWN_N_CTX
    if not isinstance(n_ctx, int):
        n_ctx = CONSERVATIVE_UNKNOWN_N_CTX
    total_slots = probe_result.get("total_slots") if probe_result else None

    # 5. row-0 regime rules
    label = args.label or ""
    will_grade = not bool(args.skip_vqa)
    strict_regime = will_grade and (label.startswith("row0") or bool(args.strict))
    vqa_cfg = manifest.get("vqa", {}) if isinstance(manifest.get("vqa"), dict) else {}
    results.extend(_check_regime(
        base_url=base_url,
        model=model,
        n_ctx=n_ctx,
        total_slots=total_slots,
        expected_min_n_ctx=provider_cfg.get("expected_min_n_ctx"),
        expected_total_slots=provider_cfg.get("expected_total_slots"),
        expected_batch_size=vqa_cfg.get("batch_size"),
        strict_regime=strict_regime,
        allow_degraded_batch=bool(args.allow_degraded_batch),
    ))

    # 6. env
    results.append(_check_env_local_llm(base_url, model))
    results.append(_check_env_cloud_keys())

    # 7. git
    head = git_head_short()
    results.append(CheckResult(
        "git_head", "PASS" if head != "unknown" else "WARN", f"HEAD {head}",
    ))
    dirty = git_dirty_pipeline_files()
    if dirty:
        status = "WARN" if args.allow_dirty else "FAIL"
        results.append(CheckResult(
            "git_dirty", status,
            f"{len(dirty)} modified tracked pipeline file(s): {', '.join(dirty)}",
        ))
    else:
        results.append(CheckResult("git_dirty", "PASS", "tools/, module/, config/settings.json clean"))

    # 8. junctions
    junctions = find_junctions(PROJECT_ROOT)
    if junctions:
        results.append(CheckResult(
            "junctions", "FAIL",
            f"{len(junctions)} junction/symlink director{'y' if len(junctions) == 1 else 'ies'} "
            f"found: {', '.join(str(j) for j in junctions)}",
        ))
    else:
        results.append(CheckResult("junctions", "PASS", "no junction/symlink directories found"))

    # 9. tools
    results.extend(_check_tools())

    # 10. determinism verdict (optional)
    if args.determinism_verdict:
        results.append(_check_determinism_verdict(Path(args.determinism_verdict), provider_cfg))

    extra: dict[str, Any] = {
        "manifest_path": str(manifest_path),
        "git_head": head,
        "label": label,
        "allow_degraded_batch": bool(args.allow_degraded_batch),
        "n_ctx": n_ctx,
        "total_slots": total_slots,
        "resolved_provider": {"base_url": base_url, "model": model},
    }
    return results, extra


def _print_preflight_report(
    results: list[CheckResult],
    exit_code: int,
    extra: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    status_label = _overall_status_label(exit_code)
    summary = f"PREFLIGHT {status_label} ({len(results)} checks)"

    for r in results:
        logger.log(_LOG_LEVEL_FOR_STATUS.get(r.status, logging.INFO), "[%s] %s: %s", r.status, r.name, r.message)

    if args.json:
        payload = {
            "status": status_label,
            "exit_code": exit_code,
            "n_checks": len(results),
            "checks": [asdict(r) for r in results],
            **extra,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for r in results:
            print(f"[{r.status:>4}] {r.name}: {r.message}")
        print(summary)

    logger.info(summary)


def cmd_preflight(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest) if args.manifest else manifest_path_default()
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("preflight: could not load manifest %s: %s", manifest_path, exc)
        return ExitCode.ERROR

    results, extra = run_preflight_checks(manifest, manifest_path, args)
    exit_code = compute_exit_code(results)
    _print_preflight_report(results, exit_code, extra, args)
    return exit_code


# ---------------------------------------------------------------------------
# Unit 4 stubs
# ---------------------------------------------------------------------------

def _make_not_implemented(name: str):
    def _fn(args: argparse.Namespace) -> int:  # noqa: ARG001 - signature parity
        logger.error("scan_bench %s: not implemented in this build (Unit 4)", name)
        return ExitCode.ERROR
    return _fn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class _ExitCodeParser(argparse.ArgumentParser):
    """Override error() to exit 3 (infra/usage) instead of argparse's default 2,
    which scan_bench reserves for "blocking FAIL" (eb370 convention).
    """

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: error: {message}\n")


def build_parser() -> _ExitCodeParser:
    parser = _ExitCodeParser(
        prog="scan_bench",
        description="EB-392 Phase 0 scan-bench harness: preflight, run, compare, report, promote.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_ExitCodeParser)

    pf = subparsers.add_parser("preflight", help="Verify manifest/sources/endpoint/environment before a run.")
    pf.add_argument("--manifest", default=None, help="Path to manifest.json (default: data/scan_bench/manifest.json)")
    pf.add_argument("--label", default=None, help="Run label (row0* triggers strict row-0 regime checks)")
    pf.add_argument("--strict", action="store_true", help="Force row-0 regime checks regardless of label")
    pf.add_argument("--skip-vqa", action="store_true", help="This run will not grade -- relax regime checks to WARN-only")
    pf.add_argument("--allow-degraded-batch", action="store_true", help="Downgrade regime FAILs to WARN (recorded)")
    pf.add_argument("--allow-dirty", action="store_true", help="Downgrade a dirty tools/module/config tree to WARN")
    pf.add_argument("--write-sha", action="store_true", help="Compute+write sha256 for books with unset sha256")
    pf.add_argument("--determinism-verdict", default=None, help="Path to a vqa_determinism_check.py JSON verdict")
    pf.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout")
    pf.set_defaults(func=cmd_preflight)

    for name, help_text in (
        ("run", "Convert + grade all manifest books (Unit 4, not yet implemented)"),
        ("compare", "Diff two runs/baselines (Unit 4, not yet implemented)"),
        ("report", "Render a markdown report for a run/baseline (Unit 4, not yet implemented)"),
        ("promote", "Copy an allowlisted run into data/scan_bench/baselines/ (Unit 4, not yet implemented)"),
    ):
        sp = subparsers.add_parser(name, help=help_text)
        sp.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
        sp.set_defaults(func=_make_not_implemented(name))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 0 if code is None else 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    try:
        return args.func(args)
    except Exception:  # noqa: BLE001 - top-level safety net, never a bare crash
        logger.exception("scan_bench: unexpected error")
        return ExitCode.ERROR


if __name__ == "__main__":
    sys.exit(main())
