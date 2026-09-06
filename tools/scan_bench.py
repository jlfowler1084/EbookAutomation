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
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
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

# Data directories covered by the CLAUDE.md junction hazard: a junction from a
# worktree into one of these lets a recursive worktree delete wipe the *target*
# (the SCRUM-301/303 incident). Tool directories are deliberately NOT in scope:
# the main tree ships tools/poppler as a legitimate junction to the WinGet
# Poppler install, and flagging it would fail preflight exactly where captures
# must run (the main working tree).
DATA_HAZARD_DIRS: tuple[str, ...] = (
    "archive", "output", "inbox", "processing", "data", "test-corpus", "logs",
)


def _is_reparse_dir(path: str) -> bool:
    """True when *path* is a directory junction or symlink (never raises)."""
    is_junction = False
    if hasattr(os.path, "isjunction"):
        try:
            is_junction = os.path.isjunction(path)
        except OSError:
            is_junction = False
    try:
        is_link = os.path.islink(path)
    except OSError:
        is_link = False
    return is_junction or is_link


def find_junctions(
    root: str | os.PathLike,
    skip: tuple[str, ...] = (".git", ".worktrees", "node_modules"),
    scope_dirs: tuple[str, ...] = DATA_HAZARD_DIRS,
) -> list[Path]:
    """Junction/symlink directories inside the data-hazard subtrees of root.

    Windows ``rmdir /s`` / PowerShell ``Remove-Item -Recurse`` traverse
    junctions and delete the *target*'s contents -- see the worktree-cleanup
    incident documented in CLAUDE.md. Only ``scope_dirs`` (the data
    directories that hazard is about) are inspected: each scope dir itself is
    checked (``archive`` being a junction is the classic failure), then its
    subtree is walked with ``followlinks=False`` so a detected reparse
    directory is listed but never descended into. Directories outside the
    scope (``tools/poppler`` and the like) are never reported.
    """
    root = str(root)
    hits: list[Path] = []
    for name in scope_dirs:
        top = os.path.join(root, name)
        if not os.path.isdir(top):
            continue
        if _is_reparse_dir(top):
            hits.append(Path(top))
            continue
        for dirpath, dirnames, _filenames in os.walk(top, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for d in dirnames:
                full = os.path.join(dirpath, d)
                if _is_reparse_dir(full):
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
# Unit 4: production call-site mirror (contract)
# ---------------------------------------------------------------------------
#
# The harness never calls Invoke-EbookPipeline or Invoke-ConvergeLoop -- it
# mirrors the PDF branch's Convert-ToKindle call exactly enough to exercise
# the same extraction/OCR code paths, with the run's own -OutputDir and no
# archiving/TTS/email. The contract test (tests/test_scan_bench.py) parses
# module/EbookAutomation.psm1 for that call site and asserts (1) every name
# in MIRROR_SWITCHES is one of its parameter names and OCR_GATE_CLASSES
# matches the psm1 -UseOCR gate expression verbatim, and (2) the call site's
# full parameter list equals CONVERT_TOKINDLE_CALL_PARAMS -- so a Phase 2
# change to that call site (e.g. a new parameter) fails the test and forces a
# harness review rather than silently drifting from production.

# Switches the harness mirror actually passes to Convert-ToKindle. A subset
# of CONVERT_TOKINDLE_CALL_PARAMS by construction -- every other call-site
# parameter is left at the pipeline's own default (unbound in the mirror).
MIRROR_SWITCHES: tuple[str, ...] = (
    "InputFile", "OutputDir", "UseHtmlExtraction", "NoCache", "UseOCR",
)

# classify_source.py verdicts that make Invoke-EbookPipeline's PDF branch
# auto-enable -UseOCR (module/EbookAutomation.psm1, the
# "$pipelineClassification.classification -in @(...)" gate immediately
# preceding the Convert-ToKindle call). The mirror replicates this gate
# exactly; OCR_GATE_CLASSES is compared against the psm1 text verbatim by
# the contract test.
OCR_GATE_CLASSES: frozenset[str] = frozenset({
    "scan_with_text", "scan_no_text", "image_only",
})

# The Invoke-EbookPipeline PDF branch's Convert-ToKindle call site, pinned in
# call order (module/EbookAutomation.psm1, ~L3951-3973). A changed call site
# (added/removed/reordered parameter) is a Phase-2-relevant event the harness
# needs to see -- the contract test snapshots this exact tuple.
CONVERT_TOKINDLE_CALL_PARAMS: tuple[str, ...] = (
    "InputFile", "OutputDir", "UseHtmlExtraction", "UseClaudeChapters",
    "UseOCR", "ForceColumns", "ValidateVisual", "NoCache", "UseVision",
    "VisionCostLimit", "UseGemini", "GeminiRemediate", "GeminiCostLimit",
    "ProduceEpub", "ApplyAIFixes", "Profile", "NoFootnotes", "NoIndex",
    "NoBibliography", "NoHyperlinks", "NoFrontMatter", "NoBackMatter",
    "NoImages", "NoBlockQuotes",
)

# Marks the start of the call site: "Convert-ToKindle -InputFile" (the
# argument name may differ, e.g. $workCopy vs. a future rename -- only the
# parameter *names* that follow are the contract, not the bound variables).
_CONVERT_TOKINDLE_CALL_START_RE = re.compile(
    r"^.*Convert-ToKindle\s+-InputFile\b.*-OutputDir\b.*`[ \t]*$", re.MULTILINE,
)
_CALL_PARAM_RE = re.compile(r"-([A-Za-z][A-Za-z0-9]*)\b")
_OCR_GATE_RE = re.compile(
    r"classification\s*-in\s*@\(([^)]*)\)",
)


def extract_convert_tokindle_call(psm1_text: str) -> str:
    """The literal ``Convert-ToKindle -InputFile ...`` call-site text block.

    module/EbookAutomation.psm1 writes this call as one PowerShell statement
    split across backtick-continued lines (`` `\n``). Starting from the line
    containing ``Convert-ToKindle -InputFile``, every line ending in a
    backtick (ignoring trailing whitespace) continues the statement; the
    first line that does NOT end in a backtick is the last line of the call
    and is included, then scanning stops -- a plain line-based re-assembly
    of the statement rather than a single regex trying to model PowerShell's
    continuation syntax.

    Raises ValueError if the call site cannot be found (a signal the psm1
    file changed shape enough that this contract test itself needs review).
    """
    start_match = _CONVERT_TOKINDLE_CALL_START_RE.search(psm1_text)
    if not start_match:
        raise ValueError(
            "Convert-ToKindle -InputFile call site not found in psm1 text "
            "-- module/EbookAutomation.psm1 shape changed; update the "
            "contract test/extraction logic, not just the pinned parameter list."
        )

    # Walk forward from the start of that line so the first captured line is
    # the whole "Convert-ToKindle -InputFile ... `" line, not just the tail
    # from the regex match point.
    line_start = psm1_text.rfind("\n", 0, start_match.start()) + 1
    remainder = psm1_text[line_start:]

    lines: list[str] = []
    for line in remainder.splitlines():
        lines.append(line)
        if not line.rstrip().endswith("`"):
            break
    return "\n".join(lines)


def extract_convert_tokindle_call_params(psm1_text: str) -> list[str]:
    """Parameter names (in call order) at the Convert-ToKindle call site.

    ``-InputFile $workCopy -OutputDir $kindleDir`` -> ["InputFile",
    "OutputDir", ...]. A bare ``-Param`` (no colon-bound value, e.g.
    ``-VisionCostLimit $VisionCostLimit``) and a ``-Param:$value`` switch
    form are both matched identically -- only the parameter *name* matters
    for this contract, not the binding style.
    """
    call = extract_convert_tokindle_call(psm1_text)
    # Strip the command name itself first -- "Convert-ToKindle" would
    # otherwise be mis-parsed by _CALL_PARAM_RE as a "-ToKindle" parameter.
    _, _, args_text = call.partition("Convert-ToKindle")
    return _CALL_PARAM_RE.findall(args_text)


def extract_ocr_gate_classes(psm1_text: str) -> set[str]:
    """The classification strings inside the psm1's ``-in @(...)`` OCR gate
    that immediately precedes the Convert-ToKindle call (the
    ``$pipelineClassification.classification -in @('scan_with_text', ...)``
    expression). Returns an empty set if no such gate is found in the text
    preceding the call site (a signal, not a silent pass, for the contract
    test to fail on).
    """
    call = extract_convert_tokindle_call(psm1_text)
    call_start = psm1_text.index(call)
    preceding = psm1_text[:call_start]
    # The gate immediately precedes the call in the file; take the *last*
    # match before the call site rather than the first anywhere in the file.
    matches = list(_OCR_GATE_RE.finditer(preceding))
    if not matches:
        return set()
    literal_list = matches[-1].group(1)
    return set(re.findall(r"'([^']*)'", literal_list))


def build_convert_command(
    module_psd1: str | os.PathLike,
    pdf_path: str | os.PathLike,
    out_dir: str | os.PathLike,
    use_ocr: bool,
) -> list[str]:
    """The pwsh argv for one Convert-ToKindle mirror invocation.

    Every parameter name used here must be in MIRROR_SWITCHES (and therefore
    in CONVERT_TOKINDLE_CALL_PARAMS) -- see the contract test.
    """
    ps_cmd = (
        f'Import-Module "{module_psd1}" -Force; '
        f'Convert-ToKindle -InputFile "{pdf_path}" -OutputDir "{out_dir}" '
        f'-UseHtmlExtraction -NoCache'
    )
    if use_ocr:
        ps_cmd += " -UseOCR"
    return ["pwsh", "-NoProfile", "-Command", ps_cmd]


def build_classify_command(pdf_path: str | os.PathLike) -> list[str]:
    """``py -3.12 tools/classify_source.py --input <pdf>`` (verified invocation
    shape; classify_source.py is otherwise unrelated to the pwsh/Convert-ToKindle
    mirror and is run with the Windows py-launcher, not sys.executable).
    """
    script = SCRIPT_DIR / "classify_source.py"
    return ["py", "-3.12", str(script), "--input", str(pdf_path)]


def build_vqa_command(
    python_exe: str,
    output_path: str | os.PathLike,
    vqa_cfg: dict,
    n_ctx: int,
    out_dir: str | os.PathLike,
) -> list[str]:
    """``<python> tools/visual_qa.py --input <output> --provider local
    --fallback-enabled false --dpi <dpi> --max-pages <max_pages> --batch-size
    <batch_size> --n-ctx <n_ctx> --output-dir <out_dir> --verbose``.

    Explicit --dpi/--max-pages defeat visual_qa.py's large-file DPI/page
    clamp (EB-347); --fallback-enabled is passed the literal lowercase
    string ``false`` (its argparse type is ``lambda x: x.lower() != "false"``).
    """
    script = SCRIPT_DIR / "visual_qa.py"
    return [
        python_exe, str(script),
        "--input", str(output_path),
        "--provider", "local",
        "--fallback-enabled", "false",
        "--dpi", str(vqa_cfg.get("dpi", 150)),
        "--max-pages", str(vqa_cfg.get("max_pages", 20)),
        "--batch-size", str(vqa_cfg.get("batch_size", 8)),
        "--n-ctx", str(n_ctx),
        "--output-dir", str(out_dir),
        "--verbose",
    ]


def build_determinism_gate_command(
    python_exe: str,
    gate_subject_output: str | os.PathLike,
    vqa_cfg: dict,
    n_ctx: int,
    out_dir: str | os.PathLike,
) -> list[str]:
    """``<python> tools/vqa_determinism_check.py --input <subject> --provider
    local --dpi <dpi> --max-pages <max_pages> --batch-size <batch_size>
    --n-ctx <n_ctx> --runs 2 --tolerance 0 --json --out-dir <out_dir>``.

    Identical VQA flags to ``build_vqa_command`` (minus --fallback-enabled,
    which vqa_determinism_check.py's build_vqa_runner hardcodes to False
    itself) so the gate's run 1 is a faithful stand-in for a normal graded
    row on the same book.
    """
    script = SCRIPT_DIR / "vqa_determinism_check.py"
    return [
        python_exe, str(script),
        "--input", str(gate_subject_output),
        "--provider", "local",
        "--dpi", str(vqa_cfg.get("dpi", 150)),
        "--max-pages", str(vqa_cfg.get("max_pages", 20)),
        "--batch-size", str(vqa_cfg.get("batch_size", 8)),
        "--n-ctx", str(n_ctx),
        "--runs", "2",
        "--tolerance", "0",
        "--json",
        "--out-dir", str(out_dir),
    ]


# ---------------------------------------------------------------------------
# Unit 4: process execution with Windows-safe tree kill
# ---------------------------------------------------------------------------

@dataclass
class ProcResult:
    """Outcome of one ``run_with_tree_kill`` invocation.

    ``returncode`` is ``None`` when ``timed_out`` is True -- the process was
    killed rather than allowed to exit, so it never produced a real exit code.
    """

    returncode: int | None
    stdout: str
    stderr: str
    elapsed: float
    timed_out: bool


def _kill_process_tree(pid: int) -> None:
    """Kill ``pid`` and every descendant while ``pid`` is still alive.

    Module-level and separately monkeypatchable (tests assert it is called,
    with the still-live root PID, before ``Popen.kill()``) per the plan's
    Key Technical Decisions: ``subprocess.run(timeout=...)`` on Windows kills
    only the direct child and then blocks in ``communicate()`` until every
    grandchild holding the inherited pipe handles exits, so a timeout there
    never leaves a live root PID to tree-kill. ``psutil`` (children,
    recursive) is used when importable; ``taskkill /F /T /PID`` otherwise --
    no new hard dependency (plan: "No new Python dependencies").
    """
    try:
        import psutil
    except ImportError:
        psutil = None  # type: ignore[assignment]

    if psutil is not None:
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        try:
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        return

    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, text=True, timeout=15,
        )
    except OSError as exc:
        logger.warning("taskkill /T /PID %s failed: %s", pid, exc)


def run_with_tree_kill(
    cmd: list[str],
    timeout: int,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike | None = None,
    log_path: str | os.PathLike | None = None,
) -> ProcResult:
    """``Popen`` + ``communicate(timeout=...)``, tree-killing the child on expiry.

    Deliberately not ``subprocess.run(timeout=...)`` -- see ``_kill_process_tree``
    and the plan's Key Technical Decisions. On ``TimeoutExpired`` the tree is
    killed *before* ``proc.kill()`` (root still alive at that point), then the
    pipes are drained via a second ``communicate()`` so the child's already-
    buffered stdout/stderr is not lost.
    """
    t0 = time.monotonic()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(cwd) if cwd else None,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc.pid)
        try:
            proc.kill()
        except OSError:
            pass
        stdout, stderr = proc.communicate()
    elapsed = time.monotonic() - t0

    if log_path is not None:
        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("=== CMD ===\n")
                f.write(" ".join(str(c) for c in cmd))
                f.write("\n=== STDOUT ===\n")
                f.write(stdout or "")
                f.write("\n=== STDERR ===\n")
                f.write(stderr or "")
                if timed_out:
                    f.write(f"\n=== TIMED OUT after {timeout}s ===\n")
        except OSError as exc:
            logger.warning("could not write log %s: %s", log_path, exc)

    return ProcResult(
        returncode=None if timed_out else proc.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        elapsed=elapsed,
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# Unit 4: source resolution (sha256 relocation)
# ---------------------------------------------------------------------------

def resolve_source_path(
    book: dict, search_root: str | os.PathLike | None,
) -> tuple[Path | None, str]:
    """(resolved_path_or_None, path_resolved_via).

    ``path_resolved_via`` is ``"literal"`` (the manifest's ``source_path``
    exists as-is), ``"sha256_search"`` (a same-size file with matching
    sha256 was found under ``search_root``), or ``"not_found"``. Never globs
    or ``fnmatch``s -- ``Path.is_file()`` and a plain ``os.walk`` with exact
    size/sha256 comparisons only (one benchmark source has ``[``/``]`` in its
    filename). Matching is never done by title.
    """
    literal = Path(str(book.get("source_path", "")))
    if book.get("source_path") and literal.is_file():
        return literal, "literal"

    target_sha = book.get("sha256")
    if not search_root or not target_sha:
        return None, "not_found"

    root = Path(search_root)
    if not root.is_dir():
        return None, "not_found"

    target_size = book.get("size_bytes")
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.lower().endswith(".pdf"):
                continue
            candidate = Path(dirpath) / name
            try:
                if isinstance(target_size, int) and candidate.stat().st_size != target_size:
                    continue
                if sha256_file(candidate) == target_sha:
                    return candidate, "sha256_search"
            except OSError:
                continue

    return None, "not_found"


# ---------------------------------------------------------------------------
# Unit 4: classify_source.py (injectable, subprocess-touching)
# ---------------------------------------------------------------------------

def classify_source(
    pdf_path: str | os.PathLike, env: dict[str, str], timeout: int = 60,
) -> tuple[str, dict | None]:
    """Run ``classify_source.py --input <pdf>``. Returns (verdict, raw_json).

    Never raises: any failure (non-zero exit, timeout, unparseable stdout)
    yields verdict ``"unknown"`` and ``None`` -- the plan's "classify failure
    -> verdict unknown, conversion still attempted, -UseOCR absent". Module-
    level so tests can monkeypatch this name directly and never spawn ``py``.
    """
    cmd = build_classify_command(pdf_path)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("classify_source.py failed to run for %s: %s", pdf_path, exc)
        return "unknown", None

    if result.returncode != 0:
        logger.warning(
            "classify_source.py exited %s for %s", result.returncode, pdf_path,
        )
        return "unknown", None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("classify_source.py produced unparseable JSON for %s", pdf_path)
        return "unknown", None

    return data.get("classification", "unknown"), data


# ---------------------------------------------------------------------------
# Unit 4: conversion output parsing
# ---------------------------------------------------------------------------

# Case-insensitive: matches both "done -> X.kfx" and the Enhanced-Typesetting
# fallback "done -> X.azw3".
_OUTPUT_PATH_RE = re.compile(r"done -> (.+\.(?:kfx|azw3))", re.IGNORECASE)


def parse_conversion_output(stdout: str, stderr: str) -> tuple[str | None, str | None]:
    """(<output_path>, <output_format>) parsed from a Convert-ToKindle
    ``Kindle: done -> <path>`` log line in stdout or stderr, or (None, None).
    ``output_format`` is the matched extension, lowercased, without the dot.
    """
    m = _OUTPUT_PATH_RE.search(stdout or "") or _OUTPUT_PATH_RE.search(stderr or "")
    if not m:
        return None, None
    path = m.group(1).strip()
    fmt = Path(path).suffix.lstrip(".").lower()
    return path, fmt


# ---------------------------------------------------------------------------
# Unit 4: cloud-usage markers in a convert log (cost_zero_verified, half 2 of 2)
# ---------------------------------------------------------------------------

# Markers that unconditionally mean a cloud call was made -- see
# tools/extract_tts_text.py / module/EbookAutomation.psm1 (grepped 2026-09-06).
_CLOUD_MARKER_LITERALS: tuple[str, ...] = (
    "AI Quality Pass: using model=",
    "attempting Gemini fallback",
    "sending text to Claude",
)


def extraction_cloud_markers(log_text: str) -> list[str]:
    """Cloud-usage marker strings found in a persisted convert log.

    A "non-skipped AI Rejoin:" line (any line containing "AI Rejoin:" that
    does not contain the literal skipped-form text "skipped (no API key)")
    counts as a marker too -- see the plan's Key Technical Decisions. Never
    raises; an empty/None log yields an empty list.
    """
    log_text = log_text or ""
    hits: list[str] = []
    for marker in _CLOUD_MARKER_LITERALS:
        if marker in log_text:
            hits.append(marker)
    for line in log_text.splitlines():
        if "AI Rejoin:" in line and "skipped (no API key)" not in line:
            hits.append(line.strip())
    return hits


# ---------------------------------------------------------------------------
# Unit 4: conversion (HTML-derived) metrics
# ---------------------------------------------------------------------------

def intermediate_html_path(output_path: str | os.PathLike) -> Path:
    """``<output>.parent/.intermediates/<output.stem>_kindle.html`` -- the
    join pattern build_batch_provenance.py's ``_book_record`` uses. Convert-
    ToKindle names its output from parsed Title/Author metadata, never the
    source stem, so this must be derived from the conversion's own reported
    output path, never guessed from the source filename.
    """
    out = Path(output_path)
    return out.parent / ".intermediates" / f"{out.stem}_kindle.html"


_PAGE_ANCHOR_RE = re.compile(r'<a\s+id="page_(\d+)"')


def compute_conversion_metrics(
    html_path: str | os.PathLike,
    source_pdf_path: str | os.PathLike | None,
    *,
    script: str = "latin",
    pages: int | None = None,
    expected_chapters: int | None = None,
) -> dict:
    """R4 conversion-side metrics from the intermediate HTML (+ source PDF
    bookmarks when available). Never raises -- a missing/unreadable HTML file
    yields ``{"metrics_error": ...}`` so a book whose conversion failed before
    producing HTML still gets a row, never a crashed run.

    Imports ``tools/test_pipeline.py::extract_baseline_from_html``,
    ``tools/chapter_alignment.py::verify_chapter_alignment``, and
    ``tools/extract_tts_text.py::score_text_layer_quality`` lazily (deferred
    heavy imports, mirroring vqa_determinism_check.build_vqa_runner) so
    importing scan_bench itself stays cheap for preflight/CLI-parsing tests.
    """
    html_path = Path(html_path)
    if not html_path.is_file():
        return {"metrics_error": f"intermediate HTML not found: {html_path}"}

    try:
        html_text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"metrics_error": f"could not read intermediate HTML: {exc}"}

    sys.path.insert(0, str(SCRIPT_DIR))
    from test_pipeline import extract_baseline_from_html  # noqa: PLC0415

    baseline = extract_baseline_from_html(html_text)
    body_text = re.sub(r"<[^>]+>", " ", html_text)
    word_count = len(body_text.split())
    page_anchors = len(_PAGE_ANCHOR_RE.findall(html_text))

    metrics: dict[str, Any] = {
        "h1_count": baseline.get("h1_count", 0),
        "h2_count": baseline.get("h2_count", 0),
        "h3_count": baseline.get("h3_count", 0),
        "chapter_count": baseline.get("h1_count", 0) + baseline.get("h2_count", 0),
        "linked_footnotes": baseline.get("linked_footnotes", 0),
        "unlinked_footnotes": baseline.get("unlinked_footnotes", 0),
        "ligature_splits": baseline.get("ligature_splits_remaining", 0),
        "double_spaces": baseline.get("double_spaces", 0),
        "standalone_page_numbers": baseline.get("standalone_page_numbers", 0),
        "word_count": word_count,
        "page_anchors": page_anchors,
        "page_anchor_ratio": (page_anchors / pages) if pages else None,
    }

    if word_count > 100:
        try:
            from extract_tts_text import score_text_layer_quality  # noqa: PLC0415
            quality = score_text_layer_quality(body_text, multi_sample=True)
            metrics["text_layer_score"] = quality.get("score")
            metrics["text_layer_recommendation"] = quality.get("recommendation")
        except Exception as exc:  # noqa: BLE001 - a scorer failure is not fatal
            metrics["text_layer_score"] = None
            metrics["text_layer_score_error"] = f"{type(exc).__name__}: {exc}"
    else:
        metrics["text_layer_score"] = None

    metrics["not_comparable_text_quality"] = (script == "non-latin")

    metrics["bookmark_count"] = 0
    metrics["alignment_score"] = None
    if source_pdf_path is not None:
        try:
            from chapter_alignment import verify_chapter_alignment  # noqa: PLC0415
            alignment = verify_chapter_alignment(source_pdf_path, html_path)
        except Exception as exc:  # noqa: BLE001
            alignment = {"error": f"{type(exc).__name__}: {exc}", "alignment_score": None}
        metrics["bookmark_count"] = alignment.get("total_bookmarks") or 0
        metrics["alignment_score"] = alignment.get("alignment_score")
        metrics["alignment_summary"] = alignment.get("summary")

    if expected_chapters is not None:
        metrics["chapter_delta"] = metrics["chapter_count"] - expected_chapters

    return metrics


# ---------------------------------------------------------------------------
# Unit 4: VQA-report metrics and exit-2 classification
# ---------------------------------------------------------------------------

# EB-340/EB-353 canary convention: an issue whose category or description
# falls in this family is a "garble finding".
_GARBLE_KEYWORDS: tuple[str, ...] = ("garbl", "ocr", "illegible", "extraction failure")

# page_type values excluded from the degenerate-grader stddev (scrum-290).
_COVER_PAGE_TYPES: frozenset[str] = frozenset({"cover", "front_matter"})

# visual_qa.py exit-2 stderr-tail classification (plan Key Technical Decisions).
_RENDER_FAILURE_MARKERS: tuple[str, ...] = (
    "calibre conversion failed", "did not produce expected pdf",
    "could not determine page count", "no pages were rendered",
)
_PROVIDER_DOWN_MARKERS: tuple[str, ...] = ("unreachable after", "connection", "connect")


def classify_vqa_exit2(stderr_text: str) -> str:
    """``vqa_render_failed`` / ``vqa_provider_down`` / ``vqa_api_failure`` from
    the stderr tail of a ``visual_qa.py`` exit-2 (exception) run.
    """
    lower = (stderr_text or "").lower()
    if any(marker in lower for marker in _RENDER_FAILURE_MARKERS):
        return "vqa_render_failed"
    if any(marker in lower for marker in _PROVIDER_DOWN_MARKERS):
        return "vqa_provider_down"
    return "vqa_api_failure"


def is_garble_issue(issue: dict) -> bool:
    text = f"{issue.get('category', '')} {issue.get('description', '')}".lower()
    return any(kw in text for kw in _GARBLE_KEYWORDS)


def count_garble_findings(report: dict) -> int:
    count = 0
    for page in report.get("pages", []) or []:
        for issue in page.get("issues", []) or []:
            if is_garble_issue(issue):
                count += 1
    return count


def non_cover_page_scores(report: dict) -> list[float]:
    scores: list[float] = []
    for page in report.get("pages", []) or []:
        page_type = (page.get("page_type") or "").lower()
        if page_type in _COVER_PAGE_TYPES:
            continue
        score = page.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    return scores


def compute_page_stddev(scores: list[float]) -> float | None:
    if len(scores) < 2:
        return None
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    return variance ** 0.5


def compute_cost_zero_verified(
    vqa_report: dict, extraction_markers: list[str],
) -> bool:
    """fallback off (no ``fallback_*`` keys in ``token_usage``) AND no cloud
    markers in the convert log. The harness always passes
    ``--fallback-enabled false``; the report's own token_usage is the
    independent proof (SCRUM-282/EB-361 "prove it from two sources").
    """
    token_usage = vqa_report.get("token_usage", {}) or {}
    no_fallback_tokens = not any(str(k).startswith("fallback_") for k in token_usage)
    return no_fallback_tokens and not extraction_markers


def compute_vqa_row_metrics(vqa_report: dict, extraction_markers: list[str]) -> dict:
    """R4 VQA-side per-book metrics from a ``_visual_qa_report.json`` dict."""
    scores = non_cover_page_scores(vqa_report)
    stddev = compute_page_stddev(scores)
    garble = count_garble_findings(vqa_report)
    provider_resolved = vqa_report.get("provider_resolved")
    token_usage = vqa_report.get("token_usage", {}) or {}

    return {
        "overall_score": vqa_report.get("overall_score"),
        "overall_pass": vqa_report.get("overall_pass"),
        "evaluation_status": vqa_report.get("evaluation_status"),
        "coverage_status": vqa_report.get("coverage_status"),
        "coverage_reason": vqa_report.get("coverage_reason"),
        "pages_requested": vqa_report.get("pages_requested"),
        "pages_sampled": vqa_report.get("pages_sampled"),
        "pages_evaluated": vqa_report.get("pages_evaluated"),
        "sampled_pages": [
            p.get("page_number") for p in vqa_report.get("pages", []) or []
        ],
        "category_scores": vqa_report.get("category_scores", {}),
        "non_cover_page_stddev": stddev,
        "degenerate_grader": len(scores) >= 3 and stddev is not None and stddev < 2,
        "garble_findings": garble,
        "token_usage": token_usage,
        "provider_resolved": provider_resolved,
        "batch_size_effective": (provider_resolved or {}).get("batch_size_effective"),
        "fallback_enabled": False,
        "cost_zero_verified": compute_cost_zero_verified(vqa_report, extraction_markers),
    }


# ---------------------------------------------------------------------------
# Unit 4: run directories, ids, and run-summary I/O
# ---------------------------------------------------------------------------

def runs_root_default() -> Path:
    return PROJECT_ROOT / "data" / "scan_bench" / "runs"


def make_run_id(label: str | None, git_sha: str, now: datetime | None = None) -> str:
    """``<yyyymmdd-HHMMSS>-<sha7>[-label]``."""
    now = now or datetime.now()
    run_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{git_sha}"
    if label:
        run_id += f"-{label}"
    return run_id


@dataclass
class RunPaths:
    """Everything one ``run --run-id`` produces, laid out under ``runs_root``.

    ``data/scan_bench/runs/**`` is gitignored (Key Technical Decisions) --
    only ``promote``'s allowlist copy ever reaches ``data/scan_bench/baselines/``.
    """

    run_dir: Path
    kfx_dir: Path
    vqa_dir: Path
    logs_dir: Path
    determinism_dir: Path
    determinism_pre: Path
    determinism_post: Path
    tmp_dir: Path
    run_meta_path: Path
    run_summary_path: Path
    manifest_snapshot_path: Path
    report_path: Path

    @classmethod
    def for_run(cls, runs_root: str | os.PathLike, run_id: str) -> "RunPaths":
        run_dir = Path(runs_root) / run_id
        determinism_dir = run_dir / "determinism"
        return cls(
            run_dir=run_dir,
            kfx_dir=run_dir / "kfx",
            vqa_dir=run_dir / "vqa",
            logs_dir=run_dir / "logs",
            determinism_dir=determinism_dir,
            determinism_pre=determinism_dir / "pre",
            determinism_post=determinism_dir / "post",
            tmp_dir=run_dir / "tmp",
            run_meta_path=run_dir / "run-meta.json",
            run_summary_path=run_dir / "run-summary.json",
            manifest_snapshot_path=run_dir / "manifest.snapshot.json",
            report_path=run_dir / "report.md",
        )

    def ensure(self) -> None:
        for d in (
            self.run_dir, self.kfx_dir, self.vqa_dir, self.logs_dir,
            self.determinism_pre, self.determinism_post, self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def _read_json(path: str | os.PathLike) -> dict | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: str | os.PathLike, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def load_run_summary(path: str | os.PathLike) -> dict:
    """``run-summary.json``: a dict keyed by book id. ``{}`` if absent/corrupt."""
    return _read_json(path) or {}


def write_run_summary(path: str | os.PathLike, summary: dict) -> None:
    """Rewritten after every book (plan: a killed run resumes cleanly)."""
    _write_json(path, summary)


def _resolve_module_psd1() -> Path:
    candidate = PROJECT_ROOT / "module" / "EbookAutomation.psd1"
    if candidate.is_file():
        return candidate
    return PROJECT_ROOT / "EbookAutomation.psd1"


def _pwsh_version() -> str:
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return (result.stdout or "").strip() or "unknown"


def _tail(text: str | None, limit: int = 4000) -> str:
    return (text or "")[-limit:]


def build_run_meta(
    manifest: dict, manifest_path: Path, git_sha: str, probe: dict,
    args: argparse.Namespace,
) -> dict:
    """Everything a run records once, up front (plan: "Recorded once in
    run-meta.json"). ``gate_subject`` / ``gate_exit_code`` / ``gate_verdict`` /
    ``post_run_canary`` are filled in by ``cmd_run`` once Stage 2 runs.
    """
    vqa_cfg = manifest.get("vqa", {}) if isinstance(manifest.get("vqa"), dict) else {}
    provider_cfg = manifest.get("provider", {}) if isinstance(manifest.get("provider"), dict) else {}
    n_ctx = probe.get("n_ctx") if isinstance(probe.get("n_ctx"), int) else CONSERVATIVE_UNKNOWN_N_CTX

    return {
        "ticket": "EB-392",
        "created": datetime.now().isoformat(),
        "label": args.label,
        "git_head": git_sha,
        "git_dirty_pipeline_files": git_dirty_pipeline_files(),
        "python_version": sys.version,
        "pwsh_version": _pwsh_version(),
        "manifest_path": str(manifest_path),
        "cloud_policy": "as-configured" if getattr(args, "cloud_as_configured", False) else "off",
        "vqa_config": vqa_cfg,
        "classifier_escalation_config": manifest.get("classifier_escalation", {}),
        "ocr_escalation_config": manifest.get("ocr_escalation", {}),
        "converge_loop_config": manifest.get("converge_loop", {}),
        "provider_manifest": provider_cfg,
        "resolved_provider": {
            "base_url": provider_cfg.get("base_url"),
            "model_requested": provider_cfg.get("model"),
            "model_served": probe.get("model_served"),
            "n_ctx": probe.get("n_ctx"),
            "n_ctx_source": probe.get("n_ctx_source"),
            "total_slots": probe.get("total_slots"),
            "model_path": probe.get("model_path"),
            "probe_ok": probe.get("probe_ok"),
        },
        "entry_point": "convert-tokindle-mirror",
        "entry_point_switches": list(MIRROR_SWITCHES),
        "ocr_gate_classes": sorted(OCR_GATE_CLASSES),
        "command_templates": {
            "classify": " ".join(build_classify_command("<pdf>")),
            "convert_no_ocr": " ".join(
                build_convert_command("<module.psd1>", "<pdf>", "<run>/kfx/<id>", False)
            ),
            "convert_with_ocr": " ".join(
                build_convert_command("<module.psd1>", "<pdf>", "<run>/kfx/<id>", True)
            ),
            "vqa": " ".join(
                build_vqa_command(sys.executable, "<output>", vqa_cfg, n_ctx, "<run>/vqa/<id>")
            ),
            "determinism_gate": " ".join(
                build_determinism_gate_command(
                    sys.executable, "<gate_subject>", vqa_cfg, n_ctx, "<run>/determinism/pre",
                )
            ),
        },
        "pinned_batch_size": vqa_cfg.get("batch_size"),
        "gate_subject": None,
        "gate_exit_code": None,
        "gate_verdict": None,
        "post_run_canary": None,
    }


# ---------------------------------------------------------------------------
# Unit 4: per-book row lifecycle
# ---------------------------------------------------------------------------

# Stage-1 (conversion) terminal outcomes.
_CONVERT_TERMINAL: frozenset[str] = frozenset({
    "converted", "converted_empty", "convert_failed", "convert_crashed", "source_missing",
})
# Stage-2 (VQA) terminal outcomes -- a book that reached one of these is done.
_VQA_TERMINAL: frozenset[str] = frozenset({
    "evaluated", "evaluated_partial", "vqa_skipped_by_flag", "vqa_skipped_empty",
})
# Statuses counted as an outright failure for the run-level guardrail.
_FAILURE_STATUSES: frozenset[str] = frozenset({
    "source_missing", "convert_failed", "convert_crashed", "convert_timeout",
    "vqa_provider_down", "vqa_render_failed", "vqa_api_failure", "vqa_no_report", "vqa_timeout",
})


def _default_row(book: dict) -> dict:
    return {
        "id": book.get("id"),
        "track": book.get("track"),
        "title": book.get("title"),
        "entry_point": "convert-tokindle-mirror",
        "status": "pending",
        "classify_verdict": None,
        "use_ocr": None,
        "path_resolved_via": None,
        "source_path_used": None,
        "convert_status": None,
        "convert_sec": None,
        "convert_cmd": None,
        "output_path": None,
        "output_format": None,
        "output_bytes": None,
        "size_ratio": None,
        "extraction_cloud_markers": [],
        "cost_nonzero": False,
        "metrics": None,
        "metrics_done": False,
        "vqa_status": None,
        "vqa_sec": None,
        "vqa": None,
        "vqa_trusted": None,
        "provider_drift": None,
        "error": None,
    }


def _stage1_needs_processing(row: dict | None) -> bool:
    if row is None:
        return True
    cs = row.get("convert_status")
    if cs is None:
        return True
    if cs == "convert_timeout":
        return True
    return cs not in _CONVERT_TERMINAL


def _stage2_needs_processing(row: dict | None, vqa_only_resume: bool = False) -> bool:
    if row is None:
        return False
    if row.get("convert_status") not in ("converted", "converted_empty"):
        return False
    vs = row.get("vqa_status")
    if vs is None:
        return True
    if vs.endswith("_timeout") or vs.endswith("_provider_down"):
        return True
    if vs == "vqa_skipped_untrusted_grader":
        return True
    if vqa_only_resume and vs == "vqa_skipped_by_flag":
        return True
    return vs not in _VQA_TERMINAL


def process_stage1_book(
    book: dict,
    row: dict,
    *,
    manifest: dict,
    paths: RunPaths,
    env: dict[str, str],
    module_psd1: Path,
    search_root: str | None,
    convert_timeout_cap: int | None,
) -> None:
    """Mutates ``row`` in place through the Stage 1 lifecycle for one book:
    resolve source -> classify -> Convert-ToKindle mirror -> parse output ->
    conversion metrics. Never raises -- every failure mode becomes a row
    status, never a crashed run.
    """
    bid = book["id"]
    timeouts_cfg = manifest.get("timeouts", {}) if isinstance(manifest.get("timeouts"), dict) else {}

    resolved_path, via = resolve_source_path(book, search_root)
    row["path_resolved_via"] = via
    if resolved_path is None:
        row["status"] = row["convert_status"] = "source_missing"
        row["error"] = (
            f"source not found: literal path missing and sha256 search under "
            f"{search_root!r} found no match for book {bid}"
        )
        return
    row["source_path_used"] = str(resolved_path)

    verdict, _raw = classify_source(resolved_path, env)
    row["classify_verdict"] = verdict
    use_ocr = verdict in OCR_GATE_CLASSES
    row["use_ocr"] = use_ocr

    out_dir = paths.kfx_dir / bid
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_convert_command(module_psd1, resolved_path, out_dir, use_ocr)
    row["convert_cmd"] = cmd

    try:
        source_size = resolved_path.stat().st_size
    except OSError:
        source_size = book.get("size_bytes") or 0
    timeout = scaled_convert_timeout(
        source_size, book.get("expected_class"), timeouts_cfg, book.get("timeout_overrides"),
    )
    if convert_timeout_cap:
        timeout = min(timeout, convert_timeout_cap)

    log_path = paths.logs_dir / f"{bid}.convert.log"
    try:
        result = run_with_tree_kill(cmd, timeout=timeout, env=env, log_path=log_path)
    except Exception as exc:  # noqa: BLE001 - a Popen-level exception, not a row crash
        row["status"] = row["convert_status"] = "convert_crashed"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return

    row["convert_sec"] = round(result.elapsed, 2)

    if result.timed_out:
        row["status"] = row["convert_status"] = "convert_timeout"
        row["error"] = f"conversion timed out after {timeout}s"
        return

    log_text = (result.stdout or "") + "\n" + (result.stderr or "")
    markers = extraction_cloud_markers(log_text)
    row["extraction_cloud_markers"] = markers
    row["cost_nonzero"] = bool(markers)

    if result.returncode != 0:
        row["status"] = row["convert_status"] = "convert_failed"
        row["error"] = _tail(log_text)
        return

    output_path, output_format = parse_conversion_output(result.stdout, result.stderr)
    if output_path is None:
        row["status"] = row["convert_status"] = "convert_failed"
        row["error"] = "conversion exited 0 but no 'Kindle: done -> ...' line was found"
        return

    row["output_path"] = output_path
    row["output_format"] = output_format
    try:
        size = os.path.getsize(output_path)
    except OSError:
        size = 0
    row["output_bytes"] = size
    src_size = book.get("size_bytes") or 0
    row["size_ratio"] = (size / src_size) if src_size else None
    row["status"] = row["convert_status"] = "converted" if size > 0 else "converted_empty"

    html_path = intermediate_html_path(output_path)
    metrics = compute_conversion_metrics(
        html_path, resolved_path, script=book.get("script", "latin"),
        pages=book.get("pages"), expected_chapters=book.get("expected_chapters"),
    )
    row["metrics"] = metrics
    row["metrics_done"] = "metrics_error" not in metrics


_DRIFT_FIELDS: tuple[str, ...] = ("model_served", "n_ctx", "total_slots", "model_path")


def detect_provider_drift(baseline_provider: dict, probe: dict) -> str | None:
    """``None`` if no drift, ``"probe_failed"`` if the re-probe itself failed,
    else a human-readable diff of the drifted field(s).
    """
    if not probe.get("probe_ok"):
        return "probe_failed"
    diffs = [
        f"{f}: {baseline_provider.get(f)!r} -> {probe.get(f)!r}"
        for f in _DRIFT_FIELDS if baseline_provider.get(f) != probe.get(f)
    ]
    return "; ".join(diffs) if diffs else None


def process_stage2_book(
    book: dict,
    row: dict,
    *,
    manifest: dict,
    paths: RunPaths,
    env: dict[str, str],
    python_exe: str,
    run_meta: dict,
    vqa_stage_timeout_cap: int | None,
    reused_report: dict | None = None,
) -> None:
    """Mutates ``row`` in place through the Stage 2 (VQA) lifecycle for one
    already-converted book: pre-probe drift check -> visual_qa.py -> outcome
    classification -> VQA metrics.
    """
    bid = book["id"]
    if row.get("convert_status") not in ("converted", "converted_empty"):
        return

    if row.get("convert_status") == "converted_empty":
        row["status"] = row["vqa_status"] = "vqa_skipped_empty"
        return

    if reused_report is not None:
        row["vqa"] = compute_vqa_row_metrics(reused_report, row.get("extraction_cloud_markers", []))
        coverage = reused_report.get("coverage_status")
        row["status"] = row["vqa_status"] = "evaluated_partial" if coverage == "partial" else "evaluated"
        row["vqa_trusted"] = True
        row["provider_drift"] = None
        return

    timeouts_cfg = manifest.get("timeouts", {}) if isinstance(manifest.get("timeouts"), dict) else {}
    vqa_cfg = manifest.get("vqa", {}) if isinstance(manifest.get("vqa"), dict) else {}
    provider_cfg = manifest.get("provider", {}) if isinstance(manifest.get("provider"), dict) else {}

    try:
        probe = probe_endpoint(provider_cfg.get("base_url"), provider_cfg.get("model"))
    except Exception as exc:  # noqa: BLE001
        row["status"] = row["vqa_status"] = "vqa_provider_down"
        row["error"] = f"pre-book re-probe raised {type(exc).__name__}: {exc}"
        return

    drift_reason = detect_provider_drift(run_meta.get("resolved_provider", {}), probe)
    if drift_reason == "probe_failed":
        row["status"] = row["vqa_status"] = "vqa_provider_down"
        row["error"] = "pre-book re-probe failed (probe_ok False) -- VQA not launched"
        return
    if drift_reason:
        row["provider_drift"] = drift_reason
        row["vqa_trusted"] = False

    n_ctx = probe.get("n_ctx") if isinstance(probe.get("n_ctx"), int) else CONSERVATIVE_UNKNOWN_N_CTX
    out_dir = paths.vqa_dir / bid
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_vqa_command(python_exe, row["output_path"], vqa_cfg, n_ctx, out_dir)

    timeout = scaled_vqa_timeout(
        row.get("output_bytes") or 0, book.get("pages") or 0, timeouts_cfg, book.get("timeout_overrides"),
    )
    if vqa_stage_timeout_cap:
        timeout = min(timeout, vqa_stage_timeout_cap)

    log_path = paths.logs_dir / f"{bid}.vqa.log"
    try:
        result = run_with_tree_kill(cmd, timeout=timeout, env=env, log_path=log_path)
    except Exception as exc:  # noqa: BLE001
        row["status"] = row["vqa_status"] = "vqa_api_failure"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return

    row["vqa_sec"] = round(result.elapsed, 2)

    if result.timed_out:
        row["status"] = row["vqa_status"] = "vqa_timeout"
        row["error"] = f"VQA timed out after {timeout}s"
        return

    if result.returncode == 2:
        row["status"] = row["vqa_status"] = classify_vqa_exit2(result.stderr)
        row["error"] = _tail(result.stderr)
        return

    report_path = out_dir / f"{Path(str(row['output_path'])).stem}_visual_qa_report.json"
    if not report_path.is_file():
        row["status"] = row["vqa_status"] = "vqa_no_report"
        row["error"] = _tail(result.stderr) or "visual_qa.py exited without writing a report"
        return

    report = _read_json(report_path)
    if report is None:
        row["status"] = row["vqa_status"] = "vqa_no_report"
        row["error"] = f"could not parse report JSON at {report_path}"
        return

    row["vqa"] = compute_vqa_row_metrics(report, row.get("extraction_cloud_markers", []))
    row["status"] = row["vqa_status"] = (
        "evaluated_partial" if report.get("coverage_status") == "partial" else "evaluated"
    )
    if row.get("vqa_trusted") is not False:
        row["vqa_trusted"] = True


# ---------------------------------------------------------------------------
# Unit 4: Stage 2 determinism gate
# ---------------------------------------------------------------------------

def select_gate_subject(books: list[dict], summary: dict) -> dict | None:
    """B1's converted output if available, else the first converted book of
    any track in manifest order (recorded via ``fallback``).
    """
    b1_row = summary.get("B1")
    if b1_row and b1_row.get("convert_status") == "converted":
        return {"id": "B1", "output_path": b1_row["output_path"], "fallback": False}
    for book in books:
        row = summary.get(book.get("id"))
        if row and row.get("convert_status") == "converted":
            return {
                "id": book["id"], "output_path": row["output_path"],
                "fallback": book.get("id") != "B1",
            }
    return None


def run_determinism_gate(
    gate_subject_output: str,
    manifest: dict,
    n_ctx: int,
    out_dir: Path,
    python_exe: str,
    env: dict[str, str],
    timeout: int,
    log_path: Path,
) -> tuple[int, dict | None, dict | None]:
    """Runs ``vqa_determinism_check.py`` against the gate subject.

    Returns ``(exit_code, verdict_json_or_None, run1_report_or_None)``.
    ``run1_report`` is loaded from ``<out_dir>/run1/<stem>_visual_qa_report.json``
    (``vqa_determinism_check.build_vqa_runner``'s own per-run output layout)
    so it can be reused as the gate subject's graded VQA row without a second
    ``visual_qa.py`` invocation. A timeout or a Popen-level exception is
    treated as exit 2 (provider-down-equivalent) -- the gate is not trusted
    either way.
    """
    vqa_cfg = manifest.get("vqa", {}) if isinstance(manifest.get("vqa"), dict) else {}
    cmd = build_determinism_gate_command(python_exe, gate_subject_output, vqa_cfg, n_ctx, out_dir)
    try:
        result = run_with_tree_kill(cmd, timeout=timeout, env=env, log_path=log_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("determinism gate raised %s: %s", type(exc).__name__, exc)
        return ExitCode.FAIL, None, None

    if result.timed_out:
        logger.error("determinism gate timed out after %ss", timeout)
        return ExitCode.FAIL, None, None

    verdict = None
    try:
        verdict = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("determinism gate produced unparseable JSON on stdout")

    exit_code = result.returncode if result.returncode is not None else ExitCode.FAIL

    run1_report = None
    run1_path = Path(out_dir) / "run1" / f"{Path(gate_subject_output).stem}_visual_qa_report.json"
    run1_report = _read_json(run1_path)

    return exit_code, verdict, run1_report


# ---------------------------------------------------------------------------
# Unit 4: dry-run preview
# ---------------------------------------------------------------------------

def _mask_child_env_for_display(env: dict[str, str], cloud_as_configured: bool) -> dict[str, str]:
    keys = ("LOCAL_LLM_BASE_URL", "LOCAL_LLM_VISION_MODEL", "LOCAL_LLM_N_CTX",
            *CLOUD_ENV_KEYS, "TEMP", "TMP")
    masked: dict[str, str] = {}
    for key in keys:
        if key not in env:
            continue
        if key in CLOUD_ENV_KEYS and not cloud_as_configured:
            masked[key] = "<blanked>"
        else:
            masked[key] = env[key]
    return masked


def _print_dry_run(
    books: list[dict],
    module_psd1: Path,
    env: dict[str, str],
    args: argparse.Namespace,
    run_id: str,
    runs_root: Path,
) -> None:
    """Preview mode: prints one planned Convert-ToKindle mirror command per
    manifest book plus a blanked-key env summary -- no subprocess, no probe
    beyond the one already done by the caller, no directories created.

    The OCR gate preview uses each book's manifest ``expected_class``
    snapshot (never a live ``classify_source.py`` call, which
    ``--dry-run`` must not spawn) -- see ``compute_conversion_metrics``'s
    docstring / the README for why ``expected_class`` is a snapshot, not a
    live re-check, elsewhere in the harness.
    """
    print(f"scan_bench run --dry-run: run_id={run_id!r} runs_root={runs_root}")
    print(f"scan_bench run --dry-run: {len(books)} planned conversion command(s):")
    print("env (harness-managed subset, cloud keys blanked unless --cloud-as-configured):")
    print(json.dumps(
        _mask_child_env_for_display(env, bool(args.cloud_as_configured)),
        indent=2, ensure_ascii=False,
    ))
    for book in books:
        use_ocr = book.get("expected_class") in OCR_GATE_CLASSES
        out_dir = runs_root / run_id / "kfx" / book["id"]
        cmd = build_convert_command(module_psd1, book.get("source_path"), out_dir, use_ocr)
        print(f"[{book['id']}] " + " ".join(str(c) for c in cmd))


# ---------------------------------------------------------------------------
# Unit 4: run orchestration
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:  # noqa: C901 - orchestration, kept linear on purpose
    manifest_path = Path(args.manifest) if args.manifest else manifest_path_default()
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("run: could not load manifest %s: %s", manifest_path, exc)
        return ExitCode.ERROR

    schema_errors = validate_manifest_schema(manifest)
    if schema_errors:
        logger.error("run: manifest schema invalid: %s", "; ".join(schema_errors))
        return ExitCode.ERROR

    if (args.resume or args.retry) and not args.run_id:
        logger.error("run: --resume/--retry require an explicit --run-id naming the run to resume")
        return ExitCode.ERROR

    git_sha = git_head_short()
    run_id = args.run_id or make_run_id(args.label, git_sha)
    runs_root = Path(args.runs_root) if args.runs_root else runs_root_default()
    paths = RunPaths.for_run(runs_root, run_id)

    run_exists = paths.run_dir.is_dir()
    if run_exists and not (args.resume or args.retry):
        logger.error(
            "run: run dir already exists: %s -- pass --resume or --retry, or "
            "choose a different --run-id/--label", paths.run_dir,
        )
        return ExitCode.ERROR
    if not run_exists and (args.resume or args.retry):
        logger.error("run: --resume/--retry given but run dir does not exist: %s", paths.run_dir)
        return ExitCode.ERROR
    if args.vqa_only and not run_exists and not args.dry_run:
        logger.error(
            "run: --vqa-only requires an existing run (pass --run-id of a "
            "previous run, typically with --resume)",
        )
        return ExitCode.ERROR

    if not args.dry_run:
        paths.ensure()

    provider_cfg = manifest.get("provider", {}) if isinstance(manifest.get("provider"), dict) else {}
    base_url = provider_cfg.get("base_url")
    model = provider_cfg.get("model")
    try:
        probe = probe_endpoint(base_url, model) if base_url else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("run: initial provider probe failed: %s", exc)
        probe = {}
    n_ctx = probe.get("n_ctx") if isinstance(probe.get("n_ctx"), int) else CONSERVATIVE_UNKNOWN_N_CTX

    temp_dir = paths.tmp_dir if not args.dry_run else None
    env = child_env(
        manifest, n_ctx, cloud_as_configured=bool(args.cloud_as_configured), temp_dir=temp_dir,
    )
    python_exe = sys.executable
    module_psd1 = _resolve_module_psd1()

    only_ids = {x.strip() for x in args.only.split(",")} if args.only else None
    retry_target = args.retry
    books = manifest.get("books", []) if isinstance(manifest.get("books"), list) else []
    selected_books = [
        b for b in books
        if (not only_ids or b.get("id") in only_ids)
        and (not retry_target or b.get("id") == retry_target)
    ]

    if args.dry_run:
        _print_dry_run(selected_books, module_psd1, env, args, run_id, runs_root)
        return ExitCode.OK

    if run_exists:
        run_meta = _read_json(paths.run_meta_path) or build_run_meta(manifest, manifest_path, git_sha, probe, args)
        summary = load_run_summary(paths.run_summary_path)
    else:
        run_meta = build_run_meta(manifest, manifest_path, git_sha, probe, args)
        summary = {}
        _write_json(paths.run_meta_path, run_meta)
        _write_json(paths.manifest_snapshot_path, manifest)

    timeouts_cfg = manifest.get("timeouts", {}) if isinstance(manifest.get("timeouts"), dict) else {}
    vqa_cfg = manifest.get("vqa", {}) if isinstance(manifest.get("vqa"), dict) else {}

    # === Stage 1 ===
    if not args.vqa_only:
        for book in selected_books:
            bid = book["id"]
            existing = summary.get(bid)
            force = bool(retry_target) and bid == retry_target
            if existing is not None and not force:
                if not args.resume or not _stage1_needs_processing(existing):
                    continue
            row = _default_row(book) if (existing is None or force) else existing
            process_stage1_book(
                book, row, manifest=manifest, paths=paths, env=env,
                module_psd1=module_psd1, search_root=args.search_root,
                convert_timeout_cap=args.convert_timeout,
            )
            summary[bid] = row
            write_run_summary(paths.run_summary_path, summary)

    if args.skip_vqa:
        for book in selected_books:
            row = summary.get(book["id"])
            if row and row.get("vqa_status") is None and row.get("convert_status") in (
                "converted", "converted_empty",
            ):
                row["status"] = row["vqa_status"] = "vqa_skipped_by_flag"
        write_run_summary(paths.run_summary_path, summary)
        return _finalize_run(paths, summary, run_meta, manifest, books)

    # === Stage 2: determinism gate ===
    gate_subject = run_meta.get("gate_subject")
    if not gate_subject:
        subject = select_gate_subject(books, summary)
        if subject is None:
            # Nothing converted non-empty anywhere -- there is no book a
            # determinism gate could even run against, so nothing can be
            # graded. This is not fatal on its own: a 0-byte conversion is a
            # per-book outcome independent of any gate, so still resolve
            # converted_empty -> vqa_skipped_empty; convert_failed/timeout/
            # source_missing rows are already terminal from Stage 1 and are
            # left untouched. The run-level guardrail (100% failure) still
            # applies via _finalize_run's own status check.
            logger.warning(
                "run: no converted (non-empty) book is available as a determinism-gate "
                "subject -- VQA cannot run for any row this run",
            )
            for book in selected_books:
                row = summary.get(book["id"])
                if row and row.get("convert_status") == "converted_empty" and row.get("vqa_status") is None:
                    row["status"] = row["vqa_status"] = "vqa_skipped_empty"
            run_meta["gate_subject"] = None
            write_run_summary(paths.run_summary_path, summary)
            _write_json(paths.run_meta_path, run_meta)
            return _finalize_run(paths, summary, run_meta, manifest, books)
        gate_subject = subject
        run_meta["gate_subject"] = gate_subject
        _write_json(paths.run_meta_path, run_meta)

    gate_timeout = args.vqa_stage_timeout or (
        scaled_vqa_timeout(0, max((b.get("pages") or 0) for b in books) if books else 0, timeouts_cfg) * 3
    )
    gate_exit, gate_verdict, gate_run1_report = run_determinism_gate(
        gate_subject["output_path"], manifest, n_ctx, paths.determinism_pre,
        python_exe, env, gate_timeout, paths.logs_dir / "determinism_gate.log",
    )
    run_meta["gate_exit_code"] = gate_exit
    run_meta["gate_verdict"] = gate_verdict
    _write_json(paths.run_meta_path, run_meta)

    grade_untrusted = bool(args.grade_untrusted)
    vqa_trusted_overall = True

    if gate_exit == ExitCode.WARN and not grade_untrusted:
        logger.error(
            "VQA grader is NON-DETERMINISTIC for this run's gate subject (%s) -- "
            "grading is skipped for every row. Quiesce the node (serve with "
            "--parallel 1 / a single slot) and re-run with --resume once fixed, "
            "or pass --grade-untrusted to grade anyway (vqa_trusted: false). See "
            "docs/solutions/eb361-vqa-grader-determinism-self-check-2026-06-02.md.",
            gate_subject["id"],
        )
        for book in selected_books:
            row = summary.get(book["id"])
            if row and row.get("convert_status") in ("converted", "converted_empty"):
                row["status"] = row["vqa_status"] = "vqa_skipped_untrusted_grader"
                row["vqa_trusted"] = False
        write_run_summary(paths.run_summary_path, summary)
        return _finalize_run(paths, summary, run_meta, manifest, books, force_exit=ExitCode.WARN)

    if gate_exit == ExitCode.FAIL:
        logger.error("run: determinism gate could not reach the provider (exit 2) -- VQA skipped for every row")
        for book in selected_books:
            row = summary.get(book["id"])
            if row and row.get("convert_status") in ("converted", "converted_empty"):
                row["status"] = row["vqa_status"] = "vqa_skipped_provider_down"
        write_run_summary(paths.run_summary_path, summary)
        return _finalize_run(paths, summary, run_meta, manifest, books)

    if gate_exit == ExitCode.WARN and grade_untrusted:
        vqa_trusted_overall = False

    # === Stage 2: per book ===
    for book in selected_books:
        bid = book["id"]
        row = summary.get(bid)
        if row is None:
            continue
        force = bool(retry_target) and bid == retry_target
        if not force:
            if not args.resume and row.get("vqa_status") is not None:
                continue
            if args.resume and not _stage2_needs_processing(row, vqa_only_resume=bool(args.vqa_only)):
                continue
        elif row.get("convert_status") not in ("converted", "converted_empty"):
            continue

        reused_report = gate_run1_report if bid == gate_subject["id"] else None
        process_stage2_book(
            book, row, manifest=manifest, paths=paths, env=env, python_exe=python_exe,
            run_meta=run_meta, vqa_stage_timeout_cap=args.vqa_stage_timeout,
            reused_report=reused_report,
        )
        if not vqa_trusted_overall:
            row["vqa_trusted"] = False
        summary[bid] = row
        write_run_summary(paths.run_summary_path, summary)

    # === Post-run canary ===
    try:
        post_probe = probe_endpoint(base_url, model) if base_url else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("run: post-run re-probe failed: %s", exc)
        post_probe = {}
    canary_drift = detect_provider_drift(run_meta.get("resolved_provider", {}), post_probe)

    canary_report = None
    try:
        canary_cmd = build_vqa_command(
            python_exe, gate_subject["output_path"], vqa_cfg, n_ctx, paths.determinism_post,
        )
        canary_result = run_with_tree_kill(
            canary_cmd, timeout=gate_timeout, env=env,
            log_path=paths.logs_dir / "post_canary.vqa.log",
        )
        canary_report_path = (
            paths.determinism_post / f"{Path(str(gate_subject['output_path'])).stem}_visual_qa_report.json"
        )
        if not canary_result.timed_out and canary_result.returncode in (0, 1):
            canary_report = _read_json(canary_report_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("run: post-run canary VQA run failed: %s", exc)

    canary_ok, canary_reason = True, None
    if canary_drift:
        canary_ok, canary_reason = False, f"post-run probe drift: {canary_drift}"
    elif canary_report is not None and gate_run1_report is not None:
        if canary_report.get("overall_score") != gate_run1_report.get("overall_score"):
            canary_ok = False
            canary_reason = (
                f"post-run canary overall_score {canary_report.get('overall_score')} != "
                f"gate run1 overall_score {gate_run1_report.get('overall_score')}"
            )

    run_meta["post_run_canary"] = {
        "ok": canary_ok, "reason": canary_reason, "probe": post_probe,
        "report_overall_score": canary_report.get("overall_score") if canary_report else None,
    }
    if not canary_ok:
        for row in summary.values():
            row["vqa_trusted"] = False
    _write_json(paths.run_meta_path, run_meta)
    write_run_summary(paths.run_summary_path, summary)

    return _finalize_run(paths, summary, run_meta, manifest, books)


def _finalize_run(
    paths: RunPaths, summary: dict, run_meta: dict, manifest: dict,
    books: list[dict], force_exit: int | None = None,
) -> int:
    """Writes ``report.md`` and computes the run's process exit code.

    0 all rows terminal-success, 1 some rows failed/partial/skipped
    (expected for row 0), 2 guardrail failure (100% failure in a stage, or a
    forced WARN/FAIL from the caller e.g. an untrusted-grader run).
    """
    try:
        paths.report_path.write_text(
            render_report_markdown(manifest, summary, run_meta), encoding="utf-8", newline="\n",
        )
    except OSError as exc:
        logger.warning("run: could not write %s: %s", paths.report_path, exc)

    if force_exit is not None:
        return force_exit

    statuses = [row.get("status") for row in summary.values() if row]
    if books and statuses and all(s in _FAILURE_STATUSES for s in statuses):
        return ExitCode.FAIL

    canary_row = summary.get("B1")
    canary_warn = False
    if canary_row and canary_row.get("vqa"):
        score = canary_row["vqa"].get("overall_score")
        garble = canary_row["vqa"].get("garble_findings") or 0
        if (isinstance(score, (int, float)) and score < 85) or garble > 0:
            canary_warn = True

    fully_ok = {"evaluated", "evaluated_partial", "vqa_skipped_by_flag"}
    all_success = bool(statuses) and all(s in fully_ok for s in statuses)
    if all_success and not canary_warn:
        return ExitCode.OK
    return ExitCode.WARN


# ---------------------------------------------------------------------------
# Unit 4: compare
# ---------------------------------------------------------------------------

def baselines_root_default() -> Path:
    return PROJECT_ROOT / "data" / "scan_bench" / "baselines"


def resolve_run_or_baseline_dir(
    name_or_path: str, runs_root: Path, baselines_root: Path,
) -> Path | None:
    """A literal path (if it looks like a run/baseline dir), else ``<runs_root>/
    <name>``, else ``<baselines_root>/<name>``. ``compare``/``report`` accept
    either a run id or a promoted baseline label interchangeably (both
    directory shapes carry ``run-summary.json`` -- promote's allowlist
    guarantees that).
    """
    p = Path(name_or_path)
    if p.is_dir() and (p / "run-summary.json").is_file():
        return p
    candidate = runs_root / name_or_path
    if candidate.is_dir():
        return candidate
    candidate = baselines_root / name_or_path
    if candidate.is_dir():
        return candidate
    return None


def load_run_bundle(dir_path: Path) -> tuple[dict, dict]:
    summary = load_run_summary(dir_path / "run-summary.json")
    meta = _read_json(dir_path / "run-meta.json") or {}
    return summary, meta


def _get_path(d: dict | None, path: tuple[str, ...]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


# (display name, dotted path within a row) for every numeric R4 metric.
_NUMERIC_METRIC_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("convert_sec", ("convert_sec",)),
    ("vqa_sec", ("vqa_sec",)),
    ("output_bytes", ("output_bytes",)),
    ("size_ratio", ("size_ratio",)),
    ("word_count", ("metrics", "word_count")),
    ("chapter_count", ("metrics", "chapter_count")),
    ("bookmark_count", ("metrics", "bookmark_count")),
    ("alignment_score", ("metrics", "alignment_score")),
    ("text_layer_score", ("metrics", "text_layer_score")),
    ("ligature_splits", ("metrics", "ligature_splits")),
    ("double_spaces", ("metrics", "double_spaces")),
    ("linked_footnotes", ("metrics", "linked_footnotes")),
    ("unlinked_footnotes", ("metrics", "unlinked_footnotes")),
    ("page_anchors", ("metrics", "page_anchors")),
    ("page_anchor_ratio", ("metrics", "page_anchor_ratio")),
    ("overall_score", ("vqa", "overall_score")),
    ("garble_findings", ("vqa", "garble_findings")),
    ("non_cover_page_stddev", ("vqa", "non_cover_page_stddev")),
)

_PROVIDER_PARITY_FIELDS: tuple[str, ...] = ("model_served", "n_ctx", "total_slots", "model_path")


def compare_row(
    book_id: str,
    row_a: dict | None,
    row_b: dict | None,
    *,
    allow_batch_mismatch: bool,
    label_a: str,
    label_b: str,
) -> dict:
    """One book's classification (``ok`` | ``not_comparable`` | ``untrusted``
    | ``unreliable`` | ``missing_on_a`` | ``missing_on_b``) plus per-metric
    deltas. VQA-side deltas are blocked (``"blocked": True``, ``delta: None``)
    when the classification is ``not_comparable``/``untrusted`` -- a score
    delta under a different server regime, or with an unreliable grader on
    either side, is not a number worth reporting; conversion-side metrics
    (independent of the VQA server) are still compared.
    """
    if row_a is None or row_b is None:
        return {
            "id": book_id,
            "classification": "missing_on_a" if row_a is None else "missing_on_b",
            "not_comparable_reasons": [],
            "flags": [],
            "status_a": row_a.get("status") if row_a else None,
            "status_b": row_b.get("status") if row_b else None,
            "deltas": {},
        }

    flags: list[str] = []
    classification = "ok"

    if row_a.get("vqa_trusted") is False or row_b.get("vqa_trusted") is False:
        classification = "untrusted"

    provider_a = (row_a.get("vqa") or {}).get("provider_resolved") or {}
    provider_b = (row_b.get("vqa") or {}).get("provider_resolved") or {}
    not_comparable_reasons = [
        f"{f}: {provider_a.get(f)!r} != {provider_b.get(f)!r}"
        for f in _PROVIDER_PARITY_FIELDS
        if provider_a.get(f) is not None and provider_b.get(f) is not None
        and provider_a.get(f) != provider_b.get(f)
    ]

    batch_a = provider_a.get("batch_size_effective")
    batch_b = provider_b.get("batch_size_effective")
    is_row0_pair = label_a.startswith("row0") and label_b.startswith("row0")
    if batch_a is not None and batch_b is not None and batch_a != batch_b:
        if allow_batch_mismatch and not is_row0_pair:
            flags.append("batch_mismatch")
        else:
            not_comparable_reasons.append(f"batch_size_effective: {batch_a!r} != {batch_b!r}")

    if not_comparable_reasons and classification == "ok":
        classification = "not_comparable"

    pages_a = (row_a.get("vqa") or {}).get("sampled_pages")
    pages_b = (row_b.get("vqa") or {}).get("sampled_pages")
    if pages_a is not None and pages_b is not None and list(pages_a) != list(pages_b):
        flags.append("unreliable")
        if classification == "ok":
            classification = "unreliable"

    if (row_a.get("vqa") or {}).get("degenerate_grader") or (row_b.get("vqa") or {}).get("degenerate_grader"):
        flags.append("degenerate_grader")

    vqa_blocked = classification in ("not_comparable", "untrusted")
    deltas: dict[str, dict] = {}
    for name, path in _NUMERIC_METRIC_PATHS:
        va, vb = _get_path(row_a, path), _get_path(row_b, path)
        if path[0] == "vqa" and vqa_blocked:
            deltas[name] = {"a": va, "b": vb, "delta": None, "blocked": True}
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            deltas[name] = {"a": va, "b": vb, "delta": round(vb - va, 4)}
        else:
            deltas[name] = {"a": va, "b": vb, "delta": None}

    return {
        "id": book_id,
        "classification": classification,
        "not_comparable_reasons": not_comparable_reasons,
        "flags": flags,
        "status_a": row_a.get("status"),
        "status_b": row_b.get("status"),
        "deltas": deltas,
    }


def compare_runs(dir_a: Path, dir_b: Path, *, allow_batch_mismatch: bool = False) -> dict:
    summary_a, meta_a = load_run_bundle(dir_a)
    summary_b, meta_b = load_run_bundle(dir_b)
    label_a = meta_a.get("label") or dir_a.name
    label_b = meta_b.get("label") or dir_b.name

    all_ids = list(dict.fromkeys([*summary_a.keys(), *summary_b.keys()]))
    rows = [
        compare_row(
            bid, summary_a.get(bid), summary_b.get(bid),
            allow_batch_mismatch=allow_batch_mismatch, label_a=label_a, label_b=label_b,
        )
        for bid in all_ids
    ]
    return {
        "a": str(dir_a), "b": str(dir_b), "label_a": label_a, "label_b": label_b,
        "allow_batch_mismatch": allow_batch_mismatch, "rows": rows,
    }


def render_compare_markdown(result: dict) -> str:
    lines = [f"# scan_bench compare: {result['label_a']} vs {result['label_b']}", ""]
    lines.append("| id | classification | flags | overall_score Δ | chapter_count Δ | word_count Δ |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    def _fmt(row: dict, name: str) -> str:
        entry = row.get("deltas", {}).get(name, {})
        delta = entry.get("delta")
        return "-" if delta is None else f"{delta:+g}"

    for row in result["rows"]:
        lines.append(
            f"| {row['id']} | {row['classification']} | "
            f"{', '.join(row.get('flags', [])) or '-'} | "
            f"{_fmt(row, 'overall_score')} | {_fmt(row, 'chapter_count')} | {_fmt(row, 'word_count')} |"
        )
    return "\n".join(lines)


def cmd_compare(args: argparse.Namespace) -> int:
    runs_root = runs_root_default()
    baselines_root = baselines_root_default()
    dir_a = resolve_run_or_baseline_dir(args.a, runs_root, baselines_root)
    dir_b = resolve_run_or_baseline_dir(args.b, runs_root, baselines_root)
    if dir_a is None:
        logger.error("compare: could not resolve %r to a run/baseline dir", args.a)
        return ExitCode.ERROR
    if dir_b is None:
        logger.error("compare: could not resolve %r to a run/baseline dir", args.b)
        return ExitCode.ERROR

    result = compare_runs(dir_a, dir_b, allow_batch_mismatch=bool(args.allow_batch_mismatch))
    if args.md:
        print(render_compare_markdown(result))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return ExitCode.OK


# ---------------------------------------------------------------------------
# Unit 4: report
# ---------------------------------------------------------------------------

def render_report_markdown(manifest: dict, summary: dict, run_meta: dict) -> str:
    """Row table in manifest order + a "Measurement artifacts (NOT findings)"
    section (gate verdicts, n_ctx/total_slots/model_path, cloud policy,
    drift/partial-coverage rows) -- never presented as a finding, per the
    README's interpretation guardrails.
    """
    books = manifest.get("books", []) if isinstance(manifest.get("books"), list) else []
    label = run_meta.get("label") or run_meta.get("git_head") or ""
    lines = [f"# scan_bench report -- {label}", ""]
    lines.append(
        "| id | track | status | verdict | format | score | coverage | chapters | bookmarks | "
        "alignment | words | quality | footnotes L/U | ligatures | dbl-sp | anchor ratio | "
        "garble | convert s | vqa s |"
    )
    lines.append("|" + " --- |" * 18)

    for book in books:
        bid = book.get("id")
        row = summary.get(bid) or {}
        metrics = row.get("metrics") or {}
        vqa = row.get("vqa") or {}
        lines.append(
            f"| {bid} | {book.get('track', '')} | {row.get('status', '-')} | "
            f"{row.get('classify_verdict', '-')} | {row.get('output_format', '-')} | "
            f"{vqa.get('overall_score', '-')} | {vqa.get('coverage_status', '-')} | "
            f"{metrics.get('chapter_count', '-')} | {metrics.get('bookmark_count', '-')} | "
            f"{metrics.get('alignment_score', '-')} | {metrics.get('word_count', '-')} | "
            f"{metrics.get('text_layer_score', '-')} | "
            f"{metrics.get('linked_footnotes', '-')}/{metrics.get('unlinked_footnotes', '-')} | "
            f"{metrics.get('ligature_splits', '-')} | {metrics.get('double_spaces', '-')} | "
            f"{metrics.get('page_anchor_ratio', '-')} | {vqa.get('garble_findings', '-')} | "
            f"{row.get('convert_sec', '-')} | {row.get('vqa_sec', '-')} |"
        )

    lines += ["", "## Measurement artifacts (NOT findings)", ""]
    resolved = run_meta.get("resolved_provider", {}) or {}
    lines.append(f"- n_ctx: {resolved.get('n_ctx')} (source: {resolved.get('n_ctx_source')})")
    lines.append(f"- total_slots: {resolved.get('total_slots')}")
    lines.append(f"- model_path: {resolved.get('model_path')}")
    lines.append(f"- model_served: {resolved.get('model_served')}")
    lines.append(f"- pinned batch size: {run_meta.get('pinned_batch_size')}")
    lines.append(f"- cloud_policy: {run_meta.get('cloud_policy')}")
    lines.append(f"- gate subject: {run_meta.get('gate_subject')}")
    lines.append(f"- gate exit code: {run_meta.get('gate_exit_code')}")
    gate_verdict = run_meta.get("gate_verdict") or {}
    lines.append(f"- gate deterministic: {gate_verdict.get('deterministic')}")
    post_canary = run_meta.get("post_run_canary") or {}
    lines.append(f"- post-run canary ok: {post_canary.get('ok')} ({post_canary.get('reason') or 'n/a'})")

    drift_rows = sorted(bid for bid, row in summary.items() if row.get("provider_drift"))
    lines.append(f"- provider_drift rows: {', '.join(drift_rows) or 'none'}")
    partial_rows = sorted(bid for bid, row in summary.items() if row.get("vqa_status") == "evaluated_partial")
    lines.append(f"- partial-coverage rows: {', '.join(partial_rows) or 'none'}")
    trust_false = sorted(bid for bid, row in summary.items() if row.get("vqa_trusted") is False)
    lines.append(f"- vqa_trusted False rows: {', '.join(trust_false) or 'none'}")

    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    runs_root = runs_root_default()
    baselines_root = baselines_root_default()
    run_dir = resolve_run_or_baseline_dir(args.run_or_label, runs_root, baselines_root)
    if run_dir is None:
        logger.error("report: could not resolve %r to a run/baseline dir", args.run_or_label)
        return ExitCode.ERROR

    summary = load_run_summary(run_dir / "run-summary.json")
    run_meta = _read_json(run_dir / "run-meta.json") or {}
    manifest = _read_json(run_dir / "manifest.snapshot.json")
    if manifest is None:
        try:
            manifest = load_manifest(manifest_path_default())
        except (OSError, json.JSONDecodeError):
            manifest = {"books": []}

    markdown = render_report_markdown(manifest, summary, run_meta)
    try:
        (run_dir / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
    except OSError as exc:
        logger.warning("report: could not write %s: %s", run_dir / "report.md", exc)
    print(markdown)
    return ExitCode.OK


# ---------------------------------------------------------------------------
# Unit 4: promote
# ---------------------------------------------------------------------------

# Top-level files copied verbatim, when present.
_PROMOTE_ALLOWLIST_TOP: tuple[str, ...] = (
    "run-meta.json", "run-summary.json", "report.md", "manifest.snapshot.json",
)


def _iter_promote_files(run_dir: Path):
    """Yields ``(relative_path, absolute_path)`` for exactly the promote
    allowlist -- no ``.kfx``, no ``.intermediates/*.html``, no rendered PNGs.
    """
    for name in _PROMOTE_ALLOWLIST_TOP:
        p = run_dir / name
        if p.is_file():
            yield Path(name), p

    vqa_dir = run_dir / "vqa"
    if vqa_dir.is_dir():
        for report in sorted(vqa_dir.glob("*/*_visual_qa_report.json")):
            yield report.relative_to(run_dir), report

    determinism_dir = run_dir / "determinism"
    if determinism_dir.is_dir():
        for f in sorted(determinism_dir.glob("**/*.json")):
            yield f.relative_to(run_dir), f


_NON_TERMINAL_ROW_STATUSES: frozenset[str | None] = frozenset({None, "pending", "converting"})


def validate_promotion(summary: dict, cloud_as_configured: bool) -> list[str]:
    """Row-0 promotion rules (plan Approach, Unit 4): returns validation-
    failure reasons; an empty list means the run may be promoted.
    """
    reasons: list[str] = []

    for bid, row in summary.items():
        if row.get("status") in _NON_TERMINAL_ROW_STATUSES:
            reasons.append(f"{bid}: row is not terminal (status={row.get('status')!r})")

    graded = {bid: row for bid, row in summary.items() if row.get("vqa") is not None}
    if graded:
        if not cloud_as_configured:
            for bid, row in graded.items():
                if not row["vqa"].get("cost_zero_verified"):
                    reasons.append(f"{bid}: cost_zero_verified is not True")

        signatures = {
            (
                (row["vqa"].get("provider_resolved") or {}).get("n_ctx"),
                (row["vqa"].get("provider_resolved") or {}).get("total_slots"),
                (row["vqa"].get("provider_resolved") or {}).get("model_served"),
                (row["vqa"].get("provider_resolved") or {}).get("model_path"),
            )
            for row in graded.values()
        }
        if len(signatures) > 1:
            reasons.append(f"graded rows do not share an identical provider_resolved: {sorted(signatures)}")

        if any(row.get("vqa_trusted") is False for row in graded.values()):
            reasons.append("at least one graded row has vqa_trusted False")

        b1 = summary.get("B1")
        if b1 and b1.get("vqa") is not None:
            score = b1["vqa"].get("overall_score")
            garble = b1["vqa"].get("garble_findings") or 0
            if not (isinstance(score, (int, float)) and score >= 85):
                reasons.append(f"B1 canary overall_score {score!r} < 85")
            if garble:
                reasons.append(f"B1 canary has {garble} garble finding(s) (must be zero)")

    return reasons


def cmd_promote(args: argparse.Namespace) -> int:
    runs_root = Path(args.runs_root) if args.runs_root else runs_root_default()
    run_dir = runs_root / args.run_id
    if not run_dir.is_dir():
        logger.error("promote: run dir does not exist: %s", run_dir)
        return ExitCode.ERROR

    dest_root = Path(args.dest) if args.dest else PROJECT_ROOT
    dest_dir = dest_root / "data" / "scan_bench" / "baselines" / args.label
    if dest_dir.is_dir() and not args.force:
        logger.error("promote: label %r already exists at %s -- pass --force to overwrite", args.label, dest_dir)
        return ExitCode.ERROR

    summary = load_run_summary(run_dir / "run-summary.json")
    run_meta = _read_json(run_dir / "run-meta.json") or {}
    cloud_as_configured = run_meta.get("cloud_policy") == "as-configured"

    reasons = validate_promotion(summary, cloud_as_configured)
    if reasons:
        logger.error("promote: refused (%d validation failure(s)):", len(reasons))
        for reason in reasons:
            logger.error("  - %s", reason)
        return ExitCode.FAIL

    copied = 0
    for rel, abs_path in _iter_promote_files(run_dir):
        target = dest_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(abs_path, target)
        copied += 1

    logger.info("promote: copied %d file(s) into %s", copied, dest_dir)
    print(json.dumps({"label": args.label, "dest": str(dest_dir), "files_copied": copied}, indent=2))
    return ExitCode.OK


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

    rn = subparsers.add_parser("run", help="Convert + grade manifest books (two-stage, resumable).")
    rn.add_argument("--manifest", default=None, help="Path to manifest.json (default: data/scan_bench/manifest.json)")
    rn.add_argument("--run-id", default=None, help="Run id (default: <yyyymmdd-HHMMSS>-<sha7>[-label]); required with --resume/--retry")
    rn.add_argument("--label", default=None, help="Run label (row0* selects the row-0 canary/validation bar at promote time)")
    rn.add_argument("--only", default=None, help="Comma-separated book ids to restrict this run to (e.g. A1,B1)")
    rn.add_argument("--resume", action="store_true", help="Re-attempt non-terminal/timeout/provider-down rows in an existing run")
    rn.add_argument("--retry", default=None, help="Force a clean re-attempt of exactly one book id (requires --run-id)")
    rn.add_argument("--dry-run", action="store_true", help="Print planned commands + env summary; no subprocess, no directories created")
    rn.add_argument("--skip-vqa", action="store_true", help="Stop after Stage 1 (conversion only); rows become vqa_skipped_by_flag")
    rn.add_argument("--vqa-only", action="store_true", help="Skip Stage 1; grade already-converted rows of an existing run")
    rn.add_argument("--cloud-as-configured", action="store_true", help="Inherit cloud API keys instead of blanking them (row0-cloud)")
    rn.add_argument("--grade-untrusted", action="store_true", help="Grade anyway when the determinism gate fails (vqa_trusted: false)")
    rn.add_argument("--convert-timeout", type=int, default=None, help="Caps the size-scaled per-book conversion timeout (seconds)")
    rn.add_argument("--vqa-stage-timeout", type=int, default=None, help="Caps the size-scaled per-book VQA timeout and the determinism-gate timeout (seconds)")
    rn.add_argument("--runs-root", default=None, help="Root dir for run output (default: data/scan_bench/runs)")
    rn.add_argument("--search-root", default=None, help="Root dir to sha256-search for a book whose literal source_path is missing")
    rn.set_defaults(func=cmd_run)

    cp = subparsers.add_parser("compare", help="Diff two runs/baselines (numeric deltas + parity/trust checks).")
    cp.add_argument("a", help="Run id or baseline label (or a literal run/baseline dir path)")
    cp.add_argument("b", help="Run id or baseline label (or a literal run/baseline dir path)")
    cp.add_argument("--md", action="store_true", help="Render a markdown table instead of JSON")
    cp.add_argument("--allow-batch-mismatch", action="store_true", help="Downgrade a batch_size_effective mismatch to a flag (never for two row0* labels)")
    cp.set_defaults(func=cmd_compare)

    rp = subparsers.add_parser("report", help="Render/print report.md for a run or promoted baseline.")
    rp.add_argument("run_or_label", help="Run id or baseline label (or a literal run/baseline dir path)")
    rp.set_defaults(func=cmd_report)

    pr = subparsers.add_parser("promote", help="Copy an allowlisted run into data/scan_bench/baselines/<label>/.")
    pr.add_argument("--run-id", required=True, help="Run id under --runs-root to promote")
    pr.add_argument("--label", required=True, help="Destination baseline label")
    pr.add_argument("--dest", default=None, help="Destination repo root (default: this checkout) -- point at a worktree for the data PR")
    pr.add_argument("--runs-root", default=None, help="Root dir the run lives under (default: data/scan_bench/runs)")
    pr.add_argument("--force", action="store_true", help="Overwrite an existing baseline label")
    pr.set_defaults(func=cmd_promote)

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
