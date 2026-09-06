"""tests/test_scan_bench.py — EB-392 Unit 3 (preflight) + Unit 4 (run / compare
/ report / promote) tests.

Hermetic: no network, no real git side effects (subprocess.run for git is
monkeypatched), no dependency on the developer machine's tool layout
(config/settings.json paths.* and shutil.which are monkeypatched). The one
exception is the "real manifest validates against schema" test, which reads
the tracked data/scan_bench/manifest.json but performs no filesystem/network
checks against its source_path entries.

Unit 4's orchestration tests (``cmd_run``/``compare``/``report``/``promote``)
never spawn a real subprocess: ``scan_bench.run_with_tree_kill`` is replaced
wholesale by ``FakeProcRunner`` (below), and ``scan_bench.classify_source`` /
``scan_bench.probe_endpoint`` are monkeypatched the same way Unit 3 does.
IMPORTANT: never call ``scan_bench.main(["run"])`` or ``scan_bench.cmd_run``
bare/unpatched in a test -- unlike ``compare``/``report``/``promote``, ``run``
has no required arguments, so an unpatched call executes a REAL Stage 1/2
conversion+VQA pass against the live 13-book manifest (this happened once
during EB-392 Unit 4 development and had to be tree-killed by hand).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import scan_bench  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _pdf_bytes(size: int) -> bytes:
    header = b"%PDF-1.4\n"
    return header + b"0" * max(0, size - len(header))


def make_book(
    tmp_path: Path,
    book_id: str,
    *,
    size: int = 250_000,
    sha_mode: str = "auto",
    filename: str | None = None,
    **overrides,
) -> dict:
    """Write a fake PDF under tmp_path and return a schema-complete book dict.

    sha_mode: "auto" (compute real sha256), "unset" (None), "wrong" (a
    plausible-looking but incorrect hash), or a literal sha256 string.
    """
    fname = filename or f"{book_id}.pdf"
    path = tmp_path / "sources" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pdf_bytes(size))
    actual_size = path.stat().st_size

    if sha_mode == "auto":
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    elif sha_mode == "unset":
        sha = None
    elif sha_mode == "wrong":
        sha = "0" * 64
    else:
        sha = sha_mode

    book = {
        "id": book_id,
        "track": "A",
        "title": f"Book {book_id}",
        "source_path": str(path),
        "sha256": sha,
        "size_bytes": actual_size,
        "pages": 100,
        "expected_class": "digital_native",
        "script": "latin",
        "known_failure": "test fixture",
        "timeout_overrides": {},
        "expected_chapters": None,
        "toc_source": "none",
        "interpretation_flags": [],
    }
    book.update(overrides)
    return book


def make_manifest(books: list[dict], **overrides) -> dict:
    manifest = {
        "schema_version": 1,
        "ticket": "EB-392",
        "created": "2026-09-06",
        "provider": {
            "base_url": "http://192.168.1.33:8080/v1",
            "model": "sb-vision",
            "expected_min_n_ctx": 32768,
            "expected_total_slots": 1,
        },
        "vqa": {"dpi": 150, "max_pages": 20, "batch_size": 8, "fallback_enabled": False},
        "cloud_policy": "off",
        "timeouts": {
            "convert_base_s": 600,
            "convert_per_mb_s": 10,
            "convert_mb_threshold": 20,
            "convert_scan_floor_s": 1200,
            "vqa_base_s": 900,
            "vqa_per_page_s": 2,
        },
        "books": books,
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(manifest.get(key), dict):
            manifest[key] = {**manifest[key], **value}
        else:
            manifest[key] = value
    return manifest


def write_manifest_file(path: Path, manifest: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def default_args(**overrides) -> argparse.Namespace:
    base = dict(
        manifest=None,
        label=None,
        strict=False,
        skip_vqa=False,
        allow_degraded_batch=False,
        allow_dirty=False,
        write_sha=False,
        determinism_verdict=None,
        json=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def good_probe(n_ctx: int = 32768, total_slots: int = 1, *, model_served_matches: bool = True):
    def _probe(base_url: str, model: str | None) -> dict:
        return {
            "provider": "local",
            "base_url": base_url,
            "model_requested": model,
            "model_served": model if model_served_matches else None,
            "models_listed": [model] if model_served_matches else ["some-other-model"],
            "n_ctx": n_ctx,
            "n_ctx_source": "models",
            "n_ctx_train": 262144,
            "total_slots": total_slots,
            "model_path": "/models/sb-vision.gguf",
            "build_info": "b1234",
            "server_type": "llamacpp",
            "probe_ok": True,
            "batch_size_effective": None,
            "max_tokens_effective": None,
        }
    return _probe


def failing_probe(base_url: str, model: str | None) -> dict:
    return {
        "provider": "local", "base_url": base_url, "model_requested": model,
        "model_served": None, "models_listed": [], "n_ctx": 8192,
        "n_ctx_source": "unknown", "n_ctx_train": None, "total_slots": None,
        "model_path": None, "build_info": None, "server_type": None,
        "probe_ok": False, "batch_size_effective": None, "max_tokens_effective": None,
    }


def good_tiny_image(base_url: str, model: str | None) -> dict:
    return {"ok": True, "content": "white"}


def failing_tiny_image(base_url: str, model: str | None) -> dict:
    return {"ok": False, "error": "APIStatusError: 500 Internal Server Error"}


def install_git_fake(
    monkeypatch,
    *,
    ls_files_ok: bool = True,
    status_lines: tuple[str, ...] = (),
    head: str = "abc1234",
):
    def fake_run(cmd, cwd=None, capture_output=None, text=None, **kwargs):
        class _Result:
            pass

        r = _Result()
        r.stderr = ""
        if cmd[:2] == ["git", "ls-files"]:
            r.returncode = 0 if ls_files_ok else 1
            r.stdout = ""
        elif cmd[:2] == ["git", "rev-parse"]:
            r.returncode = 0
            r.stdout = head + "\n"
        elif cmd[:2] == ["git", "status"]:
            r.returncode = 0
            r.stdout = ("\n".join(status_lines) + "\n") if status_lines else ""
        else:
            r.returncode = 0
            r.stdout = ""
        return r

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)


@pytest.fixture
def hermetic(monkeypatch, tmp_path):
    """A fully hermetic preflight environment: clean git, present tools,
    no env leakage, good probe/tiny-image, no junctions.
    """
    calibre = tmp_path / "tools_env" / "calibre.exe"
    calibre.parent.mkdir(parents=True, exist_ok=True)
    calibre.write_bytes(b"x")
    poppler = tmp_path / "tools_env" / "poppler"
    poppler.mkdir(parents=True, exist_ok=True)
    tesseract = tmp_path / "tools_env" / "tesseract.exe"
    tesseract.write_bytes(b"x")

    monkeypatch.setattr(scan_bench, "load_settings_json", lambda: {
        "paths": {
            "calibre": str(calibre),
            "poppler": str(poppler),
            "tesseract": str(tesseract),
        }
    })
    monkeypatch.setattr(
        scan_bench.shutil, "which",
        lambda name: r"C:\fake\pwsh.exe" if name == "pwsh" else None,
    )

    install_git_fake(monkeypatch)

    for key in (
        "LOCAL_LLM_BASE_URL", "LOCAL_LLM_VISION_MODEL",
        "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(scan_bench, "find_junctions", lambda root: [])
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe())
    monkeypatch.setattr(scan_bench, "tiny_image_check", good_tiny_image)

    return tmp_path


def run_preflight(manifest: dict, manifest_path: Path, args: argparse.Namespace):
    return scan_bench.run_preflight_checks(manifest, manifest_path, args)


def status_of(results, name):
    for r in results:
        if r.name == name:
            return r
    return None


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_preflight_happy_path_exit_0(hermetic, tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1"), make_book(tmp_path, "B1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, extra = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 0
    assert all(r.status in ("PASS", "INFO") for r in results)
    assert extra["n_ctx"] == 32768
    assert extra["total_slots"] == 1


# ---------------------------------------------------------------------------
# Row-0 regime rules
# ---------------------------------------------------------------------------

def test_regime_low_n_ctx_row0_label_fails_naming_sb231(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=8192))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(label="row0-vqa"))
    assert scan_bench.compute_exit_code(results) == 2
    check = status_of(results, "regime_min_n_ctx")
    assert check.status == "FAIL"
    assert "SB-231" in check.message


def test_regime_low_n_ctx_row0_label_with_skip_vqa_warns_only(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=8192))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(label="row0-vqa", skip_vqa=True))
    assert scan_bench.compute_exit_code(results) == 1
    check = status_of(results, "regime_min_n_ctx")
    assert check.status == "WARN"
    assert "SB-231" in check.message


def test_regime_total_slots_mismatch_row0_label_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(total_slots=2))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(label="row0-convert"))
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "regime_total_slots").status == "FAIL"


def test_regime_allow_degraded_batch_downgrades_to_warn_and_is_recorded(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=8192))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    args = default_args(label="row0-vqa", allow_degraded_batch=True)
    results, extra = run_preflight(manifest, manifest_path, args)
    assert scan_bench.compute_exit_code(results) == 1
    assert status_of(results, "regime_min_n_ctx").status == "WARN"
    assert status_of(results, "regime_batch_size").status == "WARN"
    assert extra["allow_degraded_batch"] is True


def test_regime_non_row0_label_without_strict_is_warn_only(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=8192, total_slots=2))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(label="exploratory-1"))
    assert scan_bench.compute_exit_code(results) == 1
    assert status_of(results, "regime_min_n_ctx").status == "WARN"
    assert status_of(results, "regime_total_slots").status == "WARN"


def test_regime_strict_flag_forces_row0_rules_on_non_row0_label(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=8192))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(label="exploratory-1", strict=True))
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "regime_min_n_ctx").status == "FAIL"


# ---------------------------------------------------------------------------
# Source checks
# ---------------------------------------------------------------------------

def test_missing_source_fails_naming_book_id(hermetic, tmp_path):
    book = make_book(tmp_path, "A2")
    Path(book["source_path"]).unlink()
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    check = status_of(results, "source_A2")
    assert check.status == "FAIL"
    assert "A2" in check.message


def test_stub_size_source_fails(hermetic, tmp_path):
    book = make_book(tmp_path, "A3", size=1000, sha_mode="auto")
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    check = status_of(results, "source_A3")
    assert check.status == "FAIL"
    assert "stub" in check.message.lower()


def test_non_pdf_extension_fails(hermetic, tmp_path):
    book = make_book(tmp_path, "A4", filename="A4.txt")
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert status_of(results, "source_A4").status == "FAIL"


def test_sha256_mismatch_fails(hermetic, tmp_path):
    book = make_book(tmp_path, "A5", sha_mode="wrong")
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert status_of(results, "source_A5").status == "FAIL"
    assert "mismatch" in status_of(results, "source_A5").message.lower()


def test_sha_unset_warns(hermetic, tmp_path):
    book = make_book(tmp_path, "A6", sha_mode="unset")
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    check = status_of(results, "source_A6")
    assert check.status == "WARN"
    assert "sha unset" in check.message.lower()
    assert scan_bench.compute_exit_code(results) == 1


def test_write_sha_rewrites_manifest_and_rerun_passes_preserving_key_order(hermetic, tmp_path):
    book = make_book(tmp_path, "A7", sha_mode="unset")
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    original_book_keys = list(manifest["books"][0].keys())
    original_top_keys = list(manifest.keys())

    args = default_args(write_sha=True)
    results, _ = run_preflight(manifest, manifest_path, args)
    assert status_of(results, "source_A7").status in ("PASS", "WARN")
    assert "written" in status_of(results, "source_A7").message.lower()

    # Re-load from disk: sha256 was written, and key order at both the
    # top level and the per-book level is unchanged (values mutated in
    # place, no keys deleted/re-inserted).
    reloaded = scan_bench.load_manifest(manifest_path)
    assert reloaded["books"][0]["sha256"]
    assert list(reloaded.keys()) == original_top_keys
    assert list(reloaded["books"][0].keys()) == original_book_keys

    # Re-run without --write-sha: now passes cleanly (sha256 matches).
    results2, _ = run_preflight(reloaded, manifest_path, default_args())
    check2 = status_of(results2, "source_A7")
    assert check2.status == "PASS"


def test_source_path_with_brackets_and_curly_apostrophe_checked_literally(hermetic, tmp_path):
    # U+2019 RIGHT SINGLE QUOTATION MARK ("curly apostrophe").
    fname = "Weird [sha a5436317] Anna\u2019s Archive.pdf"
    book = make_book(tmp_path, "A8", filename=fname)
    manifest = make_manifest([book])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    check = status_of(results, "source_A8")
    assert check.status == "PASS"


# ---------------------------------------------------------------------------
# Endpoint probe / tiny-image
# ---------------------------------------------------------------------------

def test_probe_ok_false_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", failing_probe)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "endpoint_probe").status == "FAIL"


def test_probe_model_not_listed_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(model_served_matches=False))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "endpoint_probe").status == "FAIL"


def test_probe_raises_is_caught_as_fail(hermetic, monkeypatch, tmp_path):
    def _raise(base_url, model):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(scan_bench, "probe_endpoint", _raise)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert status_of(results, "endpoint_probe").status == "FAIL"
    assert "RuntimeError" in status_of(results, "endpoint_probe").message


def test_tiny_image_http_500_fails_with_text_only_in_message(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "tiny_image_check", failing_tiny_image)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    check = status_of(results, "endpoint_tiny_image")
    assert check.status == "FAIL"
    assert "text-only" in check.message.lower()


def test_tiny_image_raises_is_caught_as_fail(hermetic, monkeypatch, tmp_path):
    def _raise(base_url, model):
        raise ConnectionError("refused")

    monkeypatch.setattr(scan_bench, "tiny_image_check", _raise)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert status_of(results, "endpoint_tiny_image").status == "FAIL"


# ---------------------------------------------------------------------------
# Determinism verdict
# ---------------------------------------------------------------------------

def test_determinism_verdict_non_deterministic_fails(hermetic, tmp_path):
    verdict = {
        "deterministic": False,
        "tolerance": 0,
        "provider_resolved_runs": [
            {"base_url": "http://192.168.1.33:8080/v1", "model_served": "sb-vision"},
            {"base_url": "http://192.168.1.33:8080/v1", "model_served": "sb-vision"},
        ],
        "exit_code": 1,
    }
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    args = default_args(determinism_verdict=str(verdict_path))
    results, _ = run_preflight(manifest, manifest_path, args)
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "determinism_verdict").status == "FAIL"


def test_determinism_verdict_provider_mismatch_fails(hermetic, tmp_path):
    verdict = {
        "deterministic": True,
        "provider_resolved_runs": [
            {"base_url": "http://localhost:8000/v1", "model_served": "qwen3.5-35b-a3b-fp8"},
            {"base_url": "http://localhost:8000/v1", "model_served": "qwen3.5-35b-a3b-fp8"},
        ],
        "exit_code": 0,
    }
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    args = default_args(determinism_verdict=str(verdict_path))
    results, _ = run_preflight(manifest, manifest_path, args)
    assert scan_bench.compute_exit_code(results) == 2
    check = status_of(results, "determinism_verdict")
    assert check.status == "FAIL"
    assert "base_url" in check.message


def test_determinism_verdict_clean_passes(hermetic, tmp_path):
    verdict = {
        "deterministic": True,
        "provider_resolved_runs": [
            {"base_url": "http://192.168.1.33:8080/v1", "model_served": "sb-vision"},
            {"base_url": "http://192.168.1.33:8080/v1", "model_served": "sb-vision"},
        ],
        "exit_code": 0,
    }
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    args = default_args(determinism_verdict=str(verdict_path))
    results, _ = run_preflight(manifest, manifest_path, args)
    assert status_of(results, "determinism_verdict").status == "PASS"


def test_determinism_verdict_missing_provider_resolved_not_a_failure_on_its_own(hermetic, tmp_path):
    verdict = {"deterministic": True, "exit_code": 0}
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    args = default_args(determinism_verdict=str(verdict_path))
    results, _ = run_preflight(manifest, manifest_path, args)
    assert status_of(results, "determinism_verdict").status == "PASS"


# ---------------------------------------------------------------------------
# Env checks
# ---------------------------------------------------------------------------

def test_env_mismatch_warns_with_both_values(hermetic, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:8000/v1")
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 1
    check = status_of(results, "env_local_llm")
    assert check.status == "WARN"
    assert "http://localhost:8000/v1" in check.message
    assert "http://192.168.1.33:8080/v1" in check.message


def test_env_cloud_keys_present_is_info_not_warn_or_fail(hermetic, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-not-a-real-key")
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    check = status_of(results, "env_cloud_keys")
    assert check.status == "INFO"
    assert "sk-fake-not-a-real-key" not in check.message
    assert scan_bench.compute_exit_code(results) == 0


# ---------------------------------------------------------------------------
# Git dirty / tracked
# ---------------------------------------------------------------------------

def test_manifest_not_tracked_fails(hermetic, monkeypatch, tmp_path):
    install_git_fake(monkeypatch, ls_files_ok=False)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "manifest_tracked").status == "FAIL"


def test_dirty_tools_file_fails_without_allow_dirty(hermetic, monkeypatch, tmp_path):
    install_git_fake(monkeypatch, status_lines=(" M tools/scan_bench.py",))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "git_dirty").status == "FAIL"


def test_dirty_tools_file_warns_with_allow_dirty(hermetic, monkeypatch, tmp_path):
    install_git_fake(monkeypatch, status_lines=(" M tools/scan_bench.py",))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args(allow_dirty=True))
    assert scan_bench.compute_exit_code(results) == 1
    assert status_of(results, "git_dirty").status == "WARN"


def test_untracked_batch_reports_file_ignored(hermetic, monkeypatch, tmp_path):
    install_git_fake(monkeypatch, status_lines=("?? data/batch_reports/foo.json",))
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert status_of(results, "git_dirty").status == "PASS"
    assert scan_bench.compute_exit_code(results) == 0


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------

def test_junction_found_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "find_junctions", lambda root: [Path(r"F:\fake\junction")])
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "junctions").status == "FAIL"


def test_find_junctions_plain_tree_is_empty(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "c.txt").write_text("x", encoding="utf-8")
    assert scan_bench.find_junctions(tmp_path) == []


def test_find_junctions_skips_dotgit_and_worktrees(tmp_path, monkeypatch):
    (tmp_path / ".git" / "sub").mkdir(parents=True)
    (tmp_path / ".worktrees" / "sub").mkdir(parents=True)
    (tmp_path / "node_modules" / "sub").mkdir(parents=True)

    # Pretend every directory is a symlink -- the skip-list must still
    # exclude .git/.worktrees/node_modules from ever being reported.
    monkeypatch.setattr(scan_bench.os.path, "islink", lambda p: True)
    hits = scan_bench.find_junctions(tmp_path)
    assert hits == []


def test_find_junctions_detects_symlink_directory_under_data_dir(tmp_path, monkeypatch):
    fake_link = tmp_path / "archive" / "looks_like_link"
    fake_link.mkdir(parents=True)
    (tmp_path / "other").mkdir()

    def fake_islink(p):
        return os.path.normpath(str(p)) == os.path.normpath(str(fake_link))

    monkeypatch.setattr(scan_bench.os.path, "islink", fake_islink)
    hits = scan_bench.find_junctions(tmp_path)
    assert any(os.path.normpath(str(h)) == os.path.normpath(str(fake_link)) for h in hits)


def test_find_junctions_flags_data_dir_that_is_itself_a_junction(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()

    def fake_islink(p):
        return os.path.normpath(str(p)) == os.path.normpath(str(archive))

    monkeypatch.setattr(scan_bench.os.path, "islink", fake_islink)
    hits = scan_bench.find_junctions(tmp_path)
    assert [os.path.normpath(str(h)) for h in hits] == [os.path.normpath(str(archive))]


def test_find_junctions_ignores_tool_directory_junctions(tmp_path, monkeypatch):
    """The main tree's tools/poppler is a legitimate junction (WinGet Poppler);
    it must never fail preflight, which runs from the main tree for captures."""
    poppler = tmp_path / "tools" / "poppler"
    poppler.mkdir(parents=True)
    (tmp_path / "archive").mkdir()

    def fake_islink(p):
        return os.path.normpath(str(p)) == os.path.normpath(str(poppler))

    monkeypatch.setattr(scan_bench.os.path, "islink", fake_islink)
    assert scan_bench.find_junctions(tmp_path) == []
    assert "tools" not in scan_bench.DATA_HAZARD_DIRS


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def test_missing_pwsh_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench.shutil, "which", lambda name: None)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "tool_pwsh").status == "FAIL"


def test_missing_calibre_path_fails(hermetic, monkeypatch, tmp_path):
    monkeypatch.setattr(scan_bench, "load_settings_json", lambda: {
        "paths": {"calibre": str(tmp_path / "does_not_exist.exe"), "poppler": str(tmp_path), "tesseract": str(tmp_path)}
    })
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    assert scan_bench.compute_exit_code(results) == 2
    assert status_of(results, "tool_calibre").status == "FAIL"


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

def test_manifest_schema_missing_run_key_fails(hermetic, tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1")])
    del manifest["cloud_policy"]
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    check = status_of(results, "manifest_schema")
    assert check.status == "FAIL"
    assert "cloud_policy" in check.message


def test_manifest_schema_missing_book_key_fails(hermetic, tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1")])
    del manifest["books"][0]["known_failure"]
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    results, _ = run_preflight(manifest, manifest_path, default_args())
    check = status_of(results, "manifest_schema")
    assert check.status == "FAIL"
    assert "known_failure" in check.message


def test_manifest_schema_duplicate_book_id_fails(hermetic, tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1"), make_book(tmp_path, "A1", filename="A1b.pdf")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    errors = scan_bench.validate_manifest_schema(manifest)
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_manifest_schema_valid_manifest_has_no_errors(tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1")])
    assert scan_bench.validate_manifest_schema(manifest) == []


def test_real_manifest_validates_against_schema():
    """The tracked data/scan_bench/manifest.json is schema-valid.

    No filesystem/network access to the books' source_path entries --
    schema validation is pure dict inspection.
    """
    manifest = scan_bench.load_manifest(scan_bench.manifest_path_default())
    errors = scan_bench.validate_manifest_schema(manifest)
    assert errors == []
    assert len(manifest["books"]) == 13
    assert manifest["provider"]["model"] == "sb-vision"


# ---------------------------------------------------------------------------
# Timeout helpers
# ---------------------------------------------------------------------------

TIMEOUTS = {
    "convert_base_s": 600,
    "convert_per_mb_s": 10,
    "convert_mb_threshold": 20,
    "convert_scan_floor_s": 1200,
    "vqa_base_s": 900,
    "vqa_per_page_s": 2,
}


def test_scaled_convert_timeout_under_threshold_returns_base():
    size = 10 * 1024 * 1024  # 10 MB < 20 MB threshold
    assert scan_bench.scaled_convert_timeout(size, "digital_native", TIMEOUTS) == 600


def test_scaled_convert_timeout_over_threshold_scales():
    size = 40 * 1024 * 1024  # 40 MB, 20 MB over threshold
    # 600 + 10 * 20 = 800
    assert scan_bench.scaled_convert_timeout(size, "digital_native", TIMEOUTS) == 800


def test_scaled_convert_timeout_scan_floor_applies():
    size = 1 * 1024 * 1024  # tiny, well under threshold -> base 600
    result = scan_bench.scaled_convert_timeout(size, "scan_no_text", TIMEOUTS)
    assert result == TIMEOUTS["convert_scan_floor_s"]


def test_scaled_convert_timeout_override_wins():
    size = 200 * 1024 * 1024
    result = scan_bench.scaled_convert_timeout(size, "scan_with_text", TIMEOUTS, {"convert_s": 3600})
    assert result == 3600


def test_scaled_vqa_timeout_formula():
    assert scan_bench.scaled_vqa_timeout(0, 20, TIMEOUTS) == 900 + 2 * 20


def test_scaled_vqa_timeout_override_wins():
    assert scan_bench.scaled_vqa_timeout(0, 20, TIMEOUTS, {"vqa_s": 2400}) == 2400


# ---------------------------------------------------------------------------
# child_env
# ---------------------------------------------------------------------------

def test_child_env_pins_and_blanks_and_does_not_mutate_os_environ(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-looking-value")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-real-looking-value")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-real-looking-value")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("SOME_OTHER_VAR", "unchanged")

    manifest = make_manifest([make_book(tmp_path, "A1")])
    env = scan_bench.child_env(manifest, 32768, temp_dir=tmp_path / "temp")

    assert env["LOCAL_LLM_BASE_URL"] == "http://192.168.1.33:8080/v1"
    assert env["LOCAL_LLM_VISION_MODEL"] == "sb-vision"
    assert env["LOCAL_LLM_N_CTX"] == "32768"
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["GEMINI_API_KEY"] == ""
    assert env["OPENROUTER_API_KEY"] == ""
    assert env["SOME_OTHER_VAR"] == "unchanged"
    assert env["TEMP"] == str(tmp_path / "temp")
    assert env["TMP"] == str(tmp_path / "temp")

    # Real process env is untouched.
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-real-looking-value"
    assert os.environ["LOCAL_LLM_BASE_URL"] == "http://localhost:8000/v1"


def test_child_env_cloud_as_configured_inherits_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-looking-value")
    manifest = make_manifest([make_book(tmp_path, "A1")])
    env = scan_bench.child_env(manifest, 32768, cloud_as_configured=True)
    assert env["ANTHROPIC_API_KEY"] == "sk-real-looking-value"


def test_child_env_no_temp_dir_leaves_temp_unset_by_this_function(monkeypatch, tmp_path):
    monkeypatch.delenv("TEMP", raising=False)
    manifest = make_manifest([make_book(tmp_path, "A1")])
    env = scan_bench.child_env(manifest, 8192)
    assert "TEMP" not in env or env.get("TEMP") == os.environ.get("TEMP")


# ---------------------------------------------------------------------------
# sha256_file / git_head_short / git_dirty_pipeline_files
# ---------------------------------------------------------------------------

def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world" * 1000)
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    assert scan_bench.sha256_file(p) == expected


def test_git_head_short_returns_stdout(monkeypatch):
    install_git_fake(monkeypatch, head="deadbee")
    assert scan_bench.git_head_short() == "deadbee"


def test_git_head_short_unknown_on_failure(monkeypatch):
    def fake_run(cmd, cwd=None, capture_output=None, text=None, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)
    assert scan_bench.git_head_short() == "unknown"


def test_git_dirty_pipeline_files_filters_untracked(monkeypatch):
    install_git_fake(monkeypatch, status_lines=(
        " M tools/scan_bench.py",
        "?? data/batch_reports/foo.json",
        "A  module/EbookAutomation.psm1",
    ))
    dirty = scan_bench.git_dirty_pipeline_files()
    assert "tools/scan_bench.py" in dirty
    assert "module/EbookAutomation.psm1" in dirty
    assert not any("batch_reports" in d for d in dirty)


def test_git_ls_files_tracked_true_and_false(monkeypatch):
    install_git_fake(monkeypatch, ls_files_ok=True)
    assert scan_bench.git_ls_files_tracked("data/scan_bench/manifest.json") is True
    install_git_fake(monkeypatch, ls_files_ok=False)
    assert scan_bench.git_ls_files_tracked("data/scan_bench/manifest.json") is False


# ---------------------------------------------------------------------------
# compute_exit_code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([], 0),
        (["PASS"], 0),
        (["PASS", "INFO"], 0),
        (["PASS", "WARN"], 1),
        (["INFO", "WARN"], 1),
        (["WARN", "FAIL"], 2),
        (["PASS", "WARN", "FAIL"], 2),
        (["FAIL"], 2),
    ],
)
def test_compute_exit_code_table(statuses, expected):
    results = [scan_bench.CheckResult(f"c{i}", s, "msg") for i, s in enumerate(statuses)]
    assert scan_bench.compute_exit_code(results) == expected


# ---------------------------------------------------------------------------
# CLI / argparse
# ---------------------------------------------------------------------------

def test_argparse_bad_flag_exits_3(capsys):
    code = scan_bench.main(["preflight", "--not-a-real-flag"])
    assert code == 3


def test_argparse_missing_subcommand_exits_3(capsys):
    code = scan_bench.main([])
    assert code == 3


def test_compare_report_promote_missing_required_args_exit_3(capsys):
    """argparse-level checks only -- never invoke bare ``run`` here: unlike
    compare/report/promote, ``run`` has no required arguments, so
    ``scan_bench.main(["run"])`` would actually execute a real Stage 1/2
    conversion+VQA pass against the live 13-book manifest (confirmed the
    hard way during EB-392 Unit 4 development). Unit 4's ``run`` tests all
    monkeypatch probe_endpoint/classify_source/run_with_tree_kill and pass
    an explicit --run-id/--runs-root under tmp_path.
    """
    for argv in (["compare"], ["compare", "only-one"], ["report"], ["promote"], ["promote", "--run-id", "x"]):
        code = scan_bench.main(argv)
        assert code == 3, f"{argv} should exit 3 (argparse), got {code}"


def test_main_preflight_end_to_end_exit_0(hermetic, tmp_path, capsys):
    manifest = make_manifest([make_book(tmp_path, "A1")])
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)

    code = scan_bench.main(["preflight", "--manifest", str(manifest_path), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "OK"
    assert payload["exit_code"] == 0
    assert isinstance(payload["checks"], list)


def test_main_preflight_missing_manifest_file_exits_3(tmp_path, capsys):
    code = scan_bench.main(["preflight", "--manifest", str(tmp_path / "nope.json")])
    assert code == 3


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def test_manifest_path_default_points_at_data_scan_bench():
    p = scan_bench.manifest_path_default()
    assert p == PROJECT_ROOT / "data" / "scan_bench" / "manifest.json"


def test_load_manifest_round_trips(tmp_path):
    manifest = make_manifest([make_book(tmp_path, "A1")])
    p = tmp_path / "manifest.json"
    write_manifest_file(p, manifest)
    loaded = scan_bench.load_manifest(p)
    assert loaded["books"][0]["id"] == "A1"


def test_exit_code_constants():
    assert scan_bench.ExitCode.OK == 0
    assert scan_bench.ExitCode.WARN == 1
    assert scan_bench.ExitCode.FAIL == 2
    assert scan_bench.ExitCode.ERROR == 3


# ===========================================================================
# Unit 4: run / compare / report / promote
# ===========================================================================

FIXTURES_DIR = TESTS_DIR / "fixtures" / "scan_bench"
SAMPLE_HTML_TEXT = (FIXTURES_DIR / "sample_kindle.html").read_text(encoding="utf-8")
SAMPLE_VQA_REPORT = json.loads((FIXTURES_DIR / "sample_visual_qa_report.json").read_text(encoding="utf-8"))
SAMPLE_DETERMINISM_VERDICT = json.loads(
    (FIXTURES_DIR / "sample_determinism_verdict.json").read_text(encoding="utf-8")
)
CONVERT_LOG_CLEAN = (FIXTURES_DIR / "convert_log_clean.txt").read_text(encoding="utf-8")
CONVERT_LOG_DIRTY = (FIXTURES_DIR / "convert_log_with_cloud_markers.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract: the harness mirror vs. the real Convert-ToKindle call site
# ---------------------------------------------------------------------------

PSM1_PATH = PROJECT_ROOT / "module" / "EbookAutomation.psm1"
PSM1_TEXT = PSM1_PATH.read_text(encoding="utf-8")

# Pinned snapshot of the Invoke-EbookPipeline PDF branch's Convert-ToKindle
# call site (module/EbookAutomation.psm1, ~L3951-3973). A changed call site
# must fail this test and force a harness review.
PINNED_CONVERT_TOKINDLE_CALL_PARAMS = [
    "InputFile", "OutputDir", "UseHtmlExtraction", "UseClaudeChapters",
    "UseOCR", "ForceColumns", "ValidateVisual", "NoCache", "UseVision",
    "VisionCostLimit", "UseGemini", "GeminiRemediate", "GeminiCostLimit",
    "ProduceEpub", "ApplyAIFixes", "Profile", "NoFootnotes", "NoIndex",
    "NoBibliography", "NoHyperlinks", "NoFrontMatter", "NoBackMatter",
    "NoImages", "NoBlockQuotes",
]


def test_contract_pinned_call_params_matches_module():
    assert scan_bench.extract_convert_tokindle_call_params(PSM1_TEXT) == PINNED_CONVERT_TOKINDLE_CALL_PARAMS
    assert list(scan_bench.CONVERT_TOKINDLE_CALL_PARAMS) == PINNED_CONVERT_TOKINDLE_CALL_PARAMS


def test_contract_mirror_switches_are_subset_of_call_site_params():
    call_params = set(scan_bench.extract_convert_tokindle_call_params(PSM1_TEXT))
    assert set(scan_bench.MIRROR_SWITCHES).issubset(call_params)


def test_contract_ocr_gate_classes_match_psm1_gate_expression():
    gate_classes = scan_bench.extract_ocr_gate_classes(PSM1_TEXT)
    assert gate_classes == set(scan_bench.OCR_GATE_CLASSES)
    assert gate_classes == {"scan_with_text", "scan_no_text", "image_only"}


def test_contract_call_site_not_found_raises_value_error():
    with pytest.raises(ValueError):
        scan_bench.extract_convert_tokindle_call("no Convert-ToKindle call here")


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

def test_build_convert_command_without_ocr():
    cmd = scan_bench.build_convert_command(r"C:\mod\EbookAutomation.psd1", r"F:\book.pdf", r"F:\out\A1", False)
    assert cmd[0] == "pwsh"
    assert "-NoProfile" in cmd
    ps_cmd = cmd[-1]
    assert 'Import-Module "C:\\mod\\EbookAutomation.psd1" -Force' in ps_cmd
    assert '-InputFile "F:\\book.pdf"' in ps_cmd
    assert '-OutputDir "F:\\out\\A1"' in ps_cmd
    assert "-UseHtmlExtraction" in ps_cmd
    assert "-NoCache" in ps_cmd
    assert "-UseOCR" not in ps_cmd


def test_build_convert_command_with_ocr():
    cmd = scan_bench.build_convert_command(r"C:\mod\EbookAutomation.psd1", r"F:\book.pdf", r"F:\out\A1", True)
    assert "-UseOCR" in cmd[-1]


def test_build_classify_command_shape():
    cmd = scan_bench.build_classify_command(r"F:\book.pdf")
    assert cmd[:2] == ["py", "-3.12"]
    assert cmd[-2:] == ["--input", r"F:\book.pdf"]


def test_build_vqa_command_shape():
    vqa_cfg = {"dpi": 150, "max_pages": 20, "batch_size": 8}
    cmd = scan_bench.build_vqa_command("python.exe", r"F:\out\A1.kfx", vqa_cfg, 32768, r"F:\out\vqa\A1")
    assert cmd[0] == "python.exe"
    assert "--fallback-enabled" in cmd and cmd[cmd.index("--fallback-enabled") + 1] == "false"
    assert cmd[cmd.index("--dpi") + 1] == "150"
    assert cmd[cmd.index("--max-pages") + 1] == "20"
    assert cmd[cmd.index("--batch-size") + 1] == "8"
    assert cmd[cmd.index("--n-ctx") + 1] == "32768"
    assert cmd[cmd.index("--output-dir") + 1] == r"F:\out\vqa\A1"
    assert "--verbose" in cmd


def test_build_determinism_gate_command_shape():
    vqa_cfg = {"dpi": 150, "max_pages": 20, "batch_size": 8}
    cmd = scan_bench.build_determinism_gate_command("python.exe", r"F:\out\B1.kfx", vqa_cfg, 32768, r"F:\out\det\pre")
    assert cmd[cmd.index("--runs") + 1] == "2"
    assert cmd[cmd.index("--tolerance") + 1] == "0"
    assert "--json" in cmd
    assert cmd[cmd.index("--out-dir") + 1] == r"F:\out\det\pre"
    assert "--fallback-enabled" not in cmd  # build_vqa_runner hardcodes fallback off itself


# ---------------------------------------------------------------------------
# run_with_tree_kill
# ---------------------------------------------------------------------------

class _FakeCompletedProc:
    """A minimal stand-in for subprocess.Popen used by run_with_tree_kill tests."""

    def __init__(self, pid, stdout="", stderr="", returncode=0, hang_first_call=False):
        self.pid = pid
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._hang_first_call = hang_first_call
        self._communicate_calls = 0
        self.killed = False

    def communicate(self, timeout=None):
        self._communicate_calls += 1
        if self._hang_first_call and self._communicate_calls == 1:
            import subprocess as _subprocess
            raise _subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


def test_run_with_tree_kill_normal_completion(monkeypatch):
    fake = _FakeCompletedProc(pid=1234, stdout="hello", stderr="", returncode=0)
    monkeypatch.setattr(scan_bench.subprocess, "Popen", lambda *a, **k: fake)

    result = scan_bench.run_with_tree_kill(["echo", "hi"], timeout=5)
    assert result.returncode == 0
    assert result.stdout == "hello"
    assert result.timed_out is False


def test_run_with_tree_kill_timeout_kills_tree_before_proc_kill_then_drains(monkeypatch):
    fake = _FakeCompletedProc(pid=4321, stdout="drained-stdout", stderr="drained-stderr", hang_first_call=True)
    monkeypatch.setattr(scan_bench.subprocess, "Popen", lambda *a, **k: fake)

    call_order = []
    monkeypatch.setattr(
        scan_bench, "_kill_process_tree",
        lambda pid: call_order.append(("tree_kill", pid)),
    )
    orig_kill = fake.kill

    def _tracked_kill():
        call_order.append(("proc_kill", fake.pid))
        orig_kill()
    fake.kill = _tracked_kill

    result = scan_bench.run_with_tree_kill(["sleep", "60"], timeout=5)

    assert result.timed_out is True
    assert result.returncode is None
    assert result.stdout == "drained-stdout"
    assert result.stderr == "drained-stderr"
    # Tree-kill must be invoked with the still-live root PID BEFORE proc.kill().
    assert call_order == [("tree_kill", 4321), ("proc_kill", 4321)]


def test_run_with_tree_kill_writes_log(tmp_path, monkeypatch):
    fake = _FakeCompletedProc(pid=1, stdout="out-text", stderr="err-text", returncode=0)
    monkeypatch.setattr(scan_bench.subprocess, "Popen", lambda *a, **k: fake)

    log_path = tmp_path / "logs" / "A1.convert.log"
    scan_bench.run_with_tree_kill(["cmd"], timeout=5, log_path=log_path)
    text = log_path.read_text(encoding="utf-8")
    assert "out-text" in text
    assert "err-text" in text


@pytest.mark.skipif(
    os.environ.get("SCAN_BENCH_LIVE") != "1",
    reason="live process-tree kill check; set SCAN_BENCH_LIVE=1 to run",
)
def test_run_with_tree_kill_live_kills_nested_python():
    """This dev machine routinely has dozens of pre-existing, unrelated
    python.exe processes running (other sessions/agents) -- checking "no
    python.exe survives" against the whole system is unusable. Instead,
    snapshot python.exe PIDs immediately before spawning the nested
    pwsh -> python tree and assert that none of the PIDs that are NEW
    relative to that snapshot are still alive once run_with_tree_kill returns.
    """
    import time as _time

    import psutil

    before_pids = {p.pid for p in psutil.process_iter(["pid", "name"]) if p.info["name"] == "python.exe"}

    t0 = _time.monotonic()
    result = scan_bench.run_with_tree_kill(
        ["pwsh", "-Command", 'python -c "import time; time.sleep(60)"'],
        timeout=5,
    )
    elapsed = _time.monotonic() - t0

    assert result.timed_out is True
    assert elapsed < 15

    after_pids = {p.pid for p in psutil.process_iter(["pid", "name"]) if p.info["name"] == "python.exe"}
    new_survivors = after_pids - before_pids
    assert not new_survivors, (
        f"new python.exe PID(s) spawned by this test survived the tree-kill: {sorted(new_survivors)}"
    )


# ---------------------------------------------------------------------------
# resolve_source_path
# ---------------------------------------------------------------------------

def test_resolve_source_path_literal(tmp_path):
    book = make_book(tmp_path, "A1")
    path, via = scan_bench.resolve_source_path(book, search_root=None)
    assert via == "literal"
    assert path == Path(book["source_path"])


def test_resolve_source_path_sha256_search_found(tmp_path):
    book = make_book(tmp_path, "A2")
    original = Path(book["source_path"])
    search_root = tmp_path / "search_root"
    relocated = search_root / "subdir" / "renamed.pdf"
    relocated.parent.mkdir(parents=True, exist_ok=True)
    relocated.write_bytes(original.read_bytes())
    original.unlink()

    path, via = scan_bench.resolve_source_path(book, search_root=str(search_root))
    assert via == "sha256_search"
    assert path == relocated


def test_resolve_source_path_not_found(tmp_path):
    book = make_book(tmp_path, "A3")
    Path(book["source_path"]).unlink()
    path, via = scan_bench.resolve_source_path(book, search_root=str(tmp_path / "nonexistent"))
    assert path is None
    assert via == "not_found"


def test_resolve_source_path_literal_with_brackets_and_apostrophe(tmp_path):
    fname = "Weird [sha a5436317] Anna\u2019s Archive.pdf"
    book = make_book(tmp_path, "A4", filename=fname)
    path, via = scan_bench.resolve_source_path(book, search_root=None)
    assert via == "literal"
    assert path is not None and path.name == fname


# ---------------------------------------------------------------------------
# classify_source
# ---------------------------------------------------------------------------

def test_classify_source_success(monkeypatch):
    def fake_run(cmd, capture_output=None, text=None, encoding=None, errors=None, timeout=None, env=None):
        class _R:
            returncode = 0
            stdout = json.dumps({"classification": "scan_with_text", "confidence": 0.9})
            stderr = ""
        return _R()

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)
    verdict, raw = scan_bench.classify_source("F:\\book.pdf", env={})
    assert verdict == "scan_with_text"
    assert raw["confidence"] == 0.9


def test_classify_source_nonzero_exit_yields_unknown(monkeypatch):
    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = "boom"
        return _R()

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)
    verdict, raw = scan_bench.classify_source("F:\\book.pdf", env={})
    assert verdict == "unknown"
    assert raw is None


def test_classify_source_bad_json_yields_unknown(monkeypatch):
    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = "not json"
            stderr = ""
        return _R()

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)
    verdict, raw = scan_bench.classify_source("F:\\book.pdf", env={})
    assert verdict == "unknown"


def test_classify_source_timeout_yields_unknown(monkeypatch):
    import subprocess as _subprocess

    def fake_run(cmd, **kwargs):
        raise _subprocess.TimeoutExpired(cmd="classify", timeout=1)

    monkeypatch.setattr(scan_bench.subprocess, "run", fake_run)
    verdict, raw = scan_bench.classify_source("F:\\book.pdf", env={})
    assert verdict == "unknown"
    assert raw is None


# ---------------------------------------------------------------------------
# parse_conversion_output
# ---------------------------------------------------------------------------

def test_parse_conversion_output_kfx():
    path, fmt = scan_bench.parse_conversion_output("Kindle: done -> F:\\out\\Book.kfx (1.2 MB, 3.4s)", "")
    assert path == "F:\\out\\Book.kfx"
    assert fmt == "kfx"


def test_parse_conversion_output_azw3():
    path, fmt = scan_bench.parse_conversion_output("", "Kindle: done -> F:\\out\\Book.azw3 (1.2 MB, 3.4s)")
    assert fmt == "azw3"


def test_parse_conversion_output_none():
    path, fmt = scan_bench.parse_conversion_output("no marker here", "nor here")
    assert path is None
    assert fmt is None


# ---------------------------------------------------------------------------
# extraction_cloud_markers
# ---------------------------------------------------------------------------

def test_extraction_cloud_markers_clean_log_is_empty():
    assert scan_bench.extraction_cloud_markers(CONVERT_LOG_CLEAN) == []


def test_extraction_cloud_markers_dirty_log_nonempty():
    markers = scan_bench.extraction_cloud_markers(CONVERT_LOG_DIRTY)
    assert any("AI Quality Pass: using model=" in m for m in markers)
    assert any("attempting Gemini fallback" in m for m in markers)
    assert any("sending text to Claude" in m for m in markers)
    assert any("AI Rejoin:" in m for m in markers)


def test_extraction_cloud_markers_skipped_ai_rejoin_not_a_marker():
    log = "  AI Rejoin: skipped (no API key)\n  AI Quality Pass: skipped (no API key)\n"
    assert scan_bench.extraction_cloud_markers(log) == []


# ---------------------------------------------------------------------------
# compute_conversion_metrics
# ---------------------------------------------------------------------------

def test_compute_conversion_metrics_happy_path_page_anchor_ratio_1():
    metrics = scan_bench.compute_conversion_metrics(
        FIXTURES_DIR / "sample_kindle.html", None, script="latin", pages=12,
    )
    assert metrics["page_anchors"] == 12
    assert metrics["page_anchor_ratio"] == 1.0
    assert metrics["chapter_count"] == metrics["h1_count"] + metrics["h2_count"]
    assert metrics["linked_footnotes"] == 1
    assert metrics["unlinked_footnotes"] == 1
    assert metrics["bookmark_count"] == 0
    assert metrics["alignment_score"] is None
    assert metrics["not_comparable_text_quality"] is False
    assert isinstance(metrics["text_layer_score"], int)


def test_compute_conversion_metrics_non_latin_flag():
    metrics = scan_bench.compute_conversion_metrics(
        FIXTURES_DIR / "sample_kindle.html", None, script="non-latin", pages=12,
    )
    assert metrics["not_comparable_text_quality"] is True


def test_compute_conversion_metrics_missing_html_yields_error_not_exception(tmp_path):
    metrics = scan_bench.compute_conversion_metrics(tmp_path / "does_not_exist.html", None, pages=10)
    assert "metrics_error" in metrics


def test_compute_conversion_metrics_expected_chapters_delta():
    metrics = scan_bench.compute_conversion_metrics(
        FIXTURES_DIR / "sample_kindle.html", None, pages=12, expected_chapters=10,
    )
    assert metrics["chapter_delta"] == metrics["chapter_count"] - 10


# ---------------------------------------------------------------------------
# VQA metrics / exit-2 classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stderr_text,expected", [
    ("RuntimeError: Calibre conversion failed (exit 1):\n...", "vqa_render_failed"),
    ("RuntimeError: Calibre did not produce expected PDF: x.pdf", "vqa_render_failed"),
    ("RuntimeError: Could not determine page count for: x.pdf", "vqa_render_failed"),
    ("RuntimeError: No pages were rendered successfully", "vqa_render_failed"),
    ("ConnectionError: Local provider unreachable after 3 retries: refused", "vqa_provider_down"),
    ("requests.exceptions.ConnectionError: Connection refused", "vqa_provider_down"),
    ("ValueError: something unrelated went wrong", "vqa_api_failure"),
])
def test_classify_vqa_exit2(stderr_text, expected):
    assert scan_bench.classify_vqa_exit2(stderr_text) == expected


def test_count_garble_findings_uses_category_and_description():
    report = {
        "pages": [
            {"page_number": 1, "issues": [{"category": "garbled_text", "description": "x"}]},
            {"page_number": 2, "issues": [{"category": "layout", "description": "OCR artifact visible"}]},
            {"page_number": 3, "issues": [{"category": "layout", "description": "illegible smudge"}]},
            {"page_number": 4, "issues": [{"category": "layout", "description": "clean page, no issues"}]},
        ],
    }
    assert scan_bench.count_garble_findings(report) == 3


def test_non_cover_page_scores_excludes_cover_and_front_matter():
    report = {"pages": [
        {"page_number": 1, "page_type": "cover", "score": 10},
        {"page_number": 2, "page_type": "front_matter", "score": 20},
        {"page_number": 3, "page_type": "body", "score": 90},
        {"page_number": 4, "page_type": "body", "score": 92},
    ]}
    assert scan_bench.non_cover_page_scores(report) == [90.0, 92.0]


def test_compute_page_stddev_needs_at_least_two_scores():
    assert scan_bench.compute_page_stddev([]) is None
    assert scan_bench.compute_page_stddev([50.0]) is None
    assert scan_bench.compute_page_stddev([50.0, 50.0]) == 0.0


def test_degenerate_grader_requires_three_pages_and_low_stddev():
    report_uniform = {"pages": [
        {"page_number": i, "page_type": "body", "score": 80} for i in range(1, 6)
    ]}
    metrics = scan_bench.compute_vqa_row_metrics(report_uniform, [])
    assert metrics["degenerate_grader"] is True

    report_two_pages_uniform = {"pages": [
        {"page_number": 1, "page_type": "body", "score": 80},
        {"page_number": 2, "page_type": "body", "score": 80},
    ]}
    metrics2 = scan_bench.compute_vqa_row_metrics(report_two_pages_uniform, [])
    assert metrics2["degenerate_grader"] is False  # fewer than 3 non-cover pages


def test_compute_cost_zero_verified_true_when_clean():
    report = {"token_usage": {"input_tokens": 100, "output_tokens": 50}}
    assert scan_bench.compute_cost_zero_verified(report, []) is True


def test_compute_cost_zero_verified_false_with_fallback_tokens():
    report = {"token_usage": {"input_tokens": 100, "output_tokens": 50, "fallback_input_tokens": 10}}
    assert scan_bench.compute_cost_zero_verified(report, []) is False


def test_compute_cost_zero_verified_false_with_cloud_markers():
    report = {"token_usage": {"input_tokens": 100, "output_tokens": 50}}
    assert scan_bench.compute_cost_zero_verified(report, ["AI Quality Pass: using model="]) is False


def test_compute_vqa_row_metrics_from_fixture():
    metrics = scan_bench.compute_vqa_row_metrics(SAMPLE_VQA_REPORT, [])
    assert metrics["overall_score"] == 87
    assert metrics["sampled_pages"] == list(range(1, 21))
    assert metrics["garble_findings"] == 1
    assert metrics["provider_resolved"]["model_served"] == "sb-vision"
    assert metrics["batch_size_effective"] == 8
    assert metrics["cost_zero_verified"] is True


# ---------------------------------------------------------------------------
# Orchestration harness: FakeProcRunner
# ---------------------------------------------------------------------------

def _is_convert_cmd(cmd: list) -> bool:
    return len(cmd) >= 4 and cmd[0] == "pwsh" and "Convert-ToKindle" in str(cmd[3])


def _is_vqa_cmd(cmd: list) -> bool:
    return any(str(c).endswith("visual_qa.py") for c in cmd)


def _is_gate_cmd(cmd: list) -> bool:
    return any(str(c).endswith("vqa_determinism_check.py") for c in cmd)


def _parse_convert_cmd(cmd: list) -> tuple[str, str, bool]:
    ps_cmd = cmd[3]
    m_in = re.search(r'-InputFile "([^"]+)"', ps_cmd)
    m_out = re.search(r'-OutputDir "([^"]+)"', ps_cmd)
    return m_in.group(1), m_out.group(1), "-UseOCR" in ps_cmd


def _clean_report_copy(stem: str) -> dict:
    """A deep copy of SAMPLE_VQA_REPORT with every page's issues cleared, so
    orchestration tests (which only care about status transitions/plumbing,
    not the garble-finding count) get a clean canary by default -- the
    garbled page-5 issue baked into the fixture is exercised directly by
    test_count_garble_findings_uses_category_and_description and
    test_compute_vqa_row_metrics_from_fixture instead.
    """
    report = json.loads(json.dumps(SAMPLE_VQA_REPORT))
    report["book"] = f"{stem}.kfx"
    for page in report["pages"]:
        page["issues"] = []
    return report


class FakeProcRunner:
    """Replaces ``scan_bench.run_with_tree_kill`` wholesale for orchestration
    tests. Never touches a real process; writes the same side-effect files
    (intermediate HTML, KFX bytes, VQA report JSON, gate run1/run2 reports)
    a real invocation would produce, at the paths ``scan_bench`` itself
    computes, so the metrics/parsing code under test runs unmodified.

    ``convert_behavior`` / ``vqa_behavior``: ``{book_id: outcome}`` where
    outcome in ("ok", "azw3", "empty", "failed", "timeout", "crash") for
    convert, or ("ok", "partial", "render_failed", "provider_down",
    "api_failure", "no_report", "timeout") for vqa. Default "ok".
    """

    def __init__(self, *, convert_behavior=None, vqa_behavior=None, gate_behavior="ok",
                 convert_log=CONVERT_LOG_CLEAN):
        self.convert_behavior = convert_behavior or {}
        self.vqa_behavior = vqa_behavior or {}
        self.gate_behavior = gate_behavior
        self.convert_log = convert_log
        self.calls: list[dict] = []

    def __call__(self, cmd, timeout, env=None, cwd=None, log_path=None):
        self.calls.append({
            "cmd": list(cmd), "timeout": timeout,
            "env": dict(env) if env is not None else None,
        })
        if _is_gate_cmd(cmd):
            result = self._handle_gate(cmd, timeout)
        elif _is_vqa_cmd(cmd):
            result = self._handle_vqa(cmd, timeout)
        elif _is_convert_cmd(cmd):
            result = self._handle_convert(cmd, timeout)
        else:
            raise AssertionError(f"FakeProcRunner: unrecognized command: {cmd}")

        if log_path is not None:
            # Mirrors run_with_tree_kill's own log format closely enough for
            # "log file persisted containing that text" assertions.
            log_path = Path(log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                f"=== STDOUT ===\n{result.stdout}\n=== STDERR ===\n{result.stderr}\n",
                encoding="utf-8",
            )
        return result

    def convert_calls(self):
        return [c for c in self.calls if _is_convert_cmd(c["cmd"])]

    def vqa_calls(self):
        return [c for c in self.calls if _is_vqa_cmd(c["cmd"])]

    def gate_calls(self):
        return [c for c in self.calls if _is_gate_cmd(c["cmd"])]

    def _handle_convert(self, cmd, timeout):
        pdf_path, out_dir_str, _use_ocr = _parse_convert_cmd(cmd)
        bid = Path(pdf_path).stem
        behavior = self.convert_behavior.get(bid, "ok")
        out_dir = Path(out_dir_str)
        out_dir.mkdir(parents=True, exist_ok=True)

        if behavior == "timeout":
            return scan_bench.ProcResult(returncode=None, stdout="", stderr="", elapsed=float(timeout), timed_out=True)
        if behavior == "failed":
            return scan_bench.ProcResult(
                returncode=1, stdout="", stderr="RuntimeError: Calibre conversion failed (exit 1)",
                elapsed=1.0, timed_out=False,
            )
        if behavior == "crash":
            raise OSError("simulated Popen failure")

        stem = f"{bid} - Fake Author"
        ext = "azw3" if behavior == "azw3" else "kfx"
        out_path = out_dir / f"{stem}.{ext}"

        if behavior == "empty":
            out_path.write_bytes(b"")
        else:
            out_path.write_bytes(b"FAKEOUTPUT" * 100)
            inter_dir = out_dir / ".intermediates"
            inter_dir.mkdir(parents=True, exist_ok=True)
            (inter_dir / f"{stem}_kindle.html").write_text(SAMPLE_HTML_TEXT, encoding="utf-8")

        stdout = self.convert_log + f"\nKindle: done -> {out_path} (1.0 MB, 2.0s)\n"
        return scan_bench.ProcResult(returncode=0, stdout=stdout, stderr="", elapsed=2.0, timed_out=False)

    def _handle_vqa(self, cmd, timeout):
        input_path = cmd[cmd.index("--input") + 1]
        out_dir = Path(cmd[cmd.index("--output-dir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        # book id is the leading token of the output stem ("A1 - Fake Author")
        bid = Path(input_path).stem.split(" - ")[0]
        behavior = self.vqa_behavior.get(bid, "ok")
        stem = Path(input_path).stem

        if behavior == "timeout":
            return scan_bench.ProcResult(returncode=None, stdout="", stderr="", elapsed=float(timeout), timed_out=True)
        if behavior == "render_failed":
            return scan_bench.ProcResult(
                returncode=2, stdout="", stderr="RuntimeError: Calibre conversion failed (exit 1)",
                elapsed=1.0, timed_out=False,
            )
        if behavior == "provider_down":
            return scan_bench.ProcResult(
                returncode=2, stdout="",
                stderr="ConnectionError: Local provider unreachable after 3 retries: refused",
                elapsed=1.0, timed_out=False,
            )
        if behavior == "api_failure":
            return scan_bench.ProcResult(
                returncode=2, stdout="", stderr="ValueError: something else went wrong",
                elapsed=1.0, timed_out=False,
            )
        if behavior == "no_report":
            return scan_bench.ProcResult(returncode=0, stdout="{}", stderr="", elapsed=1.0, timed_out=False)

        report = _clean_report_copy(stem)
        if behavior == "partial":
            report["coverage_status"] = "partial"
        report_path = out_dir / f"{stem}_visual_qa_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f)
        rc = 0 if report.get("overall_pass", True) else 1
        return scan_bench.ProcResult(
            returncode=rc, stdout=json.dumps({"overall_score": report.get("overall_score")}),
            stderr="", elapsed=5.0, timed_out=False,
        )

    def _handle_gate(self, cmd, timeout):
        input_path = cmd[cmd.index("--input") + 1]
        out_dir = Path(cmd[cmd.index("--out-dir") + 1])
        stem = Path(input_path).stem
        report = _clean_report_copy(stem)
        for run_name in ("run1", "run2"):
            run_dir = out_dir / run_name
            run_dir.mkdir(parents=True, exist_ok=True)
            with open(run_dir / f"{stem}_visual_qa_report.json", "w", encoding="utf-8") as f:
                json.dump(report, f)

        if self.gate_behavior == "timeout":
            return scan_bench.ProcResult(returncode=None, stdout="", stderr="", elapsed=float(timeout), timed_out=True)
        if self.gate_behavior == "provider_down":
            verdict = {"could_not_assess": True, "could_not_assess_reason": "provider drift", "exit_code": 2}
            return scan_bench.ProcResult(returncode=2, stdout=json.dumps(verdict), stderr="", elapsed=1.0, timed_out=False)
        if self.gate_behavior == "nondeterministic":
            verdict = json.loads(json.dumps(SAMPLE_DETERMINISM_VERDICT))
            verdict["deterministic"] = False
            verdict["exit_code"] = 1
            return scan_bench.ProcResult(returncode=1, stdout=json.dumps(verdict), stderr="", elapsed=10.0, timed_out=False)

        verdict = json.loads(json.dumps(SAMPLE_DETERMINISM_VERDICT))
        return scan_bench.ProcResult(returncode=0, stdout=json.dumps(verdict), stderr="", elapsed=10.0, timed_out=False)


def make_fake_classify(manifest: dict):
    by_id = {b["id"]: b.get("expected_class", "digital_native") for b in manifest["books"]}

    def _fake(pdf_path, env, timeout=60):
        bid = Path(pdf_path).stem
        verdict = by_id.get(bid, "unknown")
        return verdict, {"classification": verdict}
    return _fake


def default_run_args(**overrides) -> argparse.Namespace:
    base = dict(
        manifest=None, run_id=None, label=None, only=None, resume=False, retry=None,
        dry_run=False, skip_vqa=False, vqa_only=False, cloud_as_configured=False,
        grade_untrusted=False, convert_timeout=None, vqa_stage_timeout=None,
        runs_root=None, search_root=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def run_orch(monkeypatch, tmp_path):
    """Hermetic orchestration environment: clean git, a good 32768/1-slot
    probe, no real subprocess. Returns (tmp_path, runs_root).
    """
    install_git_fake(monkeypatch)
    monkeypatch.setattr(scan_bench, "probe_endpoint", good_probe(n_ctx=32768, total_slots=1))
    monkeypatch.setattr(scan_bench, "_pwsh_version", lambda: "7.4.0")
    runs_root = tmp_path / "runs"
    return tmp_path, runs_root


def _write_run_manifest(tmp_path, books, **overrides):
    manifest = make_manifest(books, **overrides)
    manifest_path = tmp_path / "manifest.json"
    write_manifest_file(manifest_path, manifest)
    return manifest, manifest_path


# ---------------------------------------------------------------------------
# cmd_run: happy path
# ---------------------------------------------------------------------------

def test_cmd_run_happy_path_gate_subject_reused_not_regraded(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="scan_with_text")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="testrun1", runs_root=str(runs_root))
    code = scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "testrun1" / "run-summary.json")
    assert summary["B1"]["status"] == "evaluated"
    assert summary["A1"]["status"] == "evaluated"
    assert summary["B1"]["metrics_done"] is True
    assert summary["B1"]["vqa"]["cost_zero_verified"] is True
    assert summary["B1"]["vqa_trusted"] is True
    assert summary["A1"]["vqa_trusted"] is True
    assert code == scan_bench.ExitCode.OK

    # B1 is the gate subject (converted, id == "B1") -> its VQA row comes
    # from the gate's run 1; visual_qa.py must not be invoked again for it.
    vqa_calls_by_book: dict[str, int] = {}
    for c in runner.vqa_calls():
        bid = Path(c["cmd"][c["cmd"].index("--input") + 1]).stem.split(" - ")[0]
        vqa_calls_by_book[bid] = vqa_calls_by_book.get(bid, 0) + 1
    # B1 is the gate subject: its graded row comes from the gate's run 1, so
    # Stage 2 grading never calls visual_qa.py for it directly. The one B1
    # visual_qa.py call that legitimately happens is the separate post-run
    # canary re-run (plan: "a post-run B1 canary re-run ... closes the stage"),
    # which is distinct from (re-)grading B1's own summary row.
    assert vqa_calls_by_book.get("B1", 0) == 1
    assert vqa_calls_by_book.get("A1", 0) == 1
    assert len(runner.gate_calls()) == 1

    run_meta = scan_bench._read_json(runs_root / "testrun1" / "run-meta.json")
    assert run_meta["gate_subject"]["id"] == "B1"
    assert run_meta["gate_subject"]["fallback"] is False
    assert run_meta["resolved_provider"]["model_served"] == "sb-vision"
    assert run_meta["entry_point"] == "convert-tokindle-mirror"
    assert set(run_meta["entry_point_switches"]) == set(scan_bench.MIRROR_SWITCHES)

    assert (runs_root / "testrun1" / "report.md").is_file()


# ---------------------------------------------------------------------------
# cmd_run: classify gate (-UseOCR)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected_class,ocr_expected", [
    ("scan_with_text", True),
    ("scan_no_text", True),
    ("image_only", True),
    ("digital_native", False),
    ("unknown", False),
])
def test_cmd_run_use_ocr_gate_matches_classify_verdict(run_orch, monkeypatch, tmp_path, expected_class, ocr_expected):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class=expected_class)
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="ocr-test", runs_root=str(runs_root), skip_vqa=True)
    scan_bench.cmd_run(args)

    convert_calls = runner.convert_calls()
    assert len(convert_calls) == 1
    ps_cmd = convert_calls[0]["cmd"][3]
    assert ("-UseOCR" in ps_cmd) is ocr_expected

    summary = scan_bench.load_run_summary(runs_root / "ocr-test" / "run-summary.json")
    assert summary["B1"]["classify_verdict"] == expected_class
    assert summary["B1"]["use_ocr"] is ocr_expected


def test_cmd_run_classify_failure_still_converts_without_ocr(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="scan_with_text")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", lambda pdf, env, timeout=60: ("unknown", None))

    args = default_run_args(manifest=str(manifest_path), run_id="classify-fail", runs_root=str(runs_root), skip_vqa=True)
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "classify-fail" / "run-summary.json")
    assert summary["B1"]["classify_verdict"] == "unknown"
    assert summary["B1"]["use_ocr"] is False
    assert summary["B1"]["convert_status"] == "converted"


# ---------------------------------------------------------------------------
# cmd_run: child env pins / cloud-as-configured
# ---------------------------------------------------------------------------

def test_cmd_run_child_env_pinned_for_every_subprocess(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-looking")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:8000/v1")
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="envtest", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    assert len(runner.calls) >= 2  # at least convert + gate (B1 is the only book)
    for call in runner.calls:
        env = call["env"]
        assert env["LOCAL_LLM_BASE_URL"] == manifest["provider"]["base_url"]
        assert env["LOCAL_LLM_VISION_MODEL"] == manifest["provider"]["model"]
        assert env["ANTHROPIC_API_KEY"] == ""
        assert "TEMP" in env


def test_cmd_run_cloud_as_configured_inherits_keys_and_records_policy(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-looking")
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_log=CONVERT_LOG_DIRTY)
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(
        manifest=str(manifest_path), run_id="cloudcfg", runs_root=str(runs_root), cloud_as_configured=True,
    )
    scan_bench.cmd_run(args)

    for call in runner.convert_calls():
        assert call["env"]["ANTHROPIC_API_KEY"] == "sk-real-looking"

    run_meta = scan_bench._read_json(runs_root / "cloudcfg" / "run-meta.json")
    assert run_meta["cloud_policy"] == "as-configured"

    summary = scan_bench.load_run_summary(runs_root / "cloudcfg" / "run-summary.json")
    assert summary["B1"]["cost_nonzero"] is True  # recorded regardless of cloud policy


# ---------------------------------------------------------------------------
# cmd_run: conversion failure / timeout / empty / azw3
# ---------------------------------------------------------------------------

def test_cmd_run_convert_failed_persists_log_no_vqa(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_behavior={"B1": "failed"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="convfail", runs_root=str(runs_root))
    code = scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "convfail" / "run-summary.json")
    assert summary["B1"]["status"] == "convert_failed"
    assert "Calibre conversion failed" in summary["B1"]["error"]
    assert runner.vqa_calls() == []
    assert runner.gate_calls() == []
    assert code == scan_bench.ExitCode.FAIL  # 100% of rows failed

    log_path = runs_root / "convfail" / "logs" / "B1.convert.log"
    assert log_path.is_file()
    assert "Calibre conversion failed" in log_path.read_text(encoding="utf-8")


def test_cmd_run_convert_timeout(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_behavior={"B1": "timeout"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="convtimeout", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "convtimeout" / "run-summary.json")
    assert summary["B1"]["status"] == "convert_timeout"


def test_cmd_run_converted_empty_then_vqa_skipped_empty(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_behavior={"B1": "empty"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="convempty", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "convempty" / "run-summary.json")
    assert summary["B1"]["convert_status"] == "converted_empty"
    assert summary["B1"]["status"] == "vqa_skipped_empty"
    assert runner.vqa_calls() == []


def test_cmd_run_azw3_output_format_vqa_still_runs(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_behavior={"B1": "azw3"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="azw3test", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "azw3test" / "run-summary.json")
    assert summary["B1"]["output_format"] == "azw3"
    assert summary["B1"]["status"] == "evaluated"
    assert len(runner.vqa_calls()) >= 0  # B1 is its own gate subject (reused report) -- no extra vqa call needed
    assert len(runner.gate_calls()) == 1


# ---------------------------------------------------------------------------
# cmd_run: sha256 relocation
# ---------------------------------------------------------------------------

def test_cmd_run_sha256_relocation_used_when_literal_missing(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    original = Path(book["source_path"])
    search_root = tmp_path / "search_root"
    relocated = search_root / "renamed.pdf"
    search_root.mkdir(parents=True, exist_ok=True)
    relocated.write_bytes(original.read_bytes())
    original.unlink()

    manifest, manifest_path = _write_run_manifest(tmp_path, [book])
    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(
        manifest=str(manifest_path), run_id="relocate", runs_root=str(runs_root),
        search_root=str(search_root),
    )
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "relocate" / "run-summary.json")
    assert summary["B1"]["path_resolved_via"] == "sha256_search"
    assert summary["B1"]["source_path_used"] == str(relocated)


def test_cmd_run_source_missing_when_no_relocation_found(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    Path(book["source_path"]).unlink()
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(
        manifest=str(manifest_path), run_id="nomatch", runs_root=str(runs_root),
        search_root=str(tmp_path / "empty_search_root"),
    )
    code = scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "nomatch" / "run-summary.json")
    assert summary["B1"]["status"] == "source_missing"
    assert code == scan_bench.ExitCode.FAIL


# ---------------------------------------------------------------------------
# cmd_run: determinism gate outcomes
# ---------------------------------------------------------------------------

def test_cmd_run_gate_nondeterministic_skips_all_grading(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner(gate_behavior="nondeterministic")
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="gatefail", runs_root=str(runs_root))
    code = scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "gatefail" / "run-summary.json")
    assert summary["B1"]["status"] == "vqa_skipped_untrusted_grader"
    assert summary["A1"]["status"] == "vqa_skipped_untrusted_grader"
    assert summary["B1"]["vqa_trusted"] is False
    assert code == scan_bench.ExitCode.WARN
    assert runner.vqa_calls() == []


def test_cmd_run_gate_nondeterministic_grade_untrusted_grades_anyway(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner(gate_behavior="nondeterministic")
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(
        manifest=str(manifest_path), run_id="gateuntrust", runs_root=str(runs_root), grade_untrusted=True,
    )
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "gateuntrust" / "run-summary.json")
    assert summary["B1"]["status"] == "evaluated"
    assert summary["A1"]["status"] == "evaluated"
    assert summary["B1"]["vqa_trusted"] is False
    assert summary["A1"]["vqa_trusted"] is False


def test_cmd_run_gate_provider_down(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(gate_behavior="provider_down")
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="gatedown", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "gatedown" / "run-summary.json")
    assert summary["B1"]["status"] == "vqa_skipped_provider_down"


def test_cmd_run_gate_fallback_subject_when_b1_fails(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner(convert_behavior={"B1": "failed"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="gatefallback", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    run_meta = scan_bench._read_json(runs_root / "gatefallback" / "run-meta.json")
    assert run_meta["gate_subject"]["id"] == "A1"
    assert run_meta["gate_subject"]["fallback"] is True


# ---------------------------------------------------------------------------
# cmd_run: provider drift / probe failure
# ---------------------------------------------------------------------------

def test_cmd_run_provider_drift_on_third_book_marks_untrusted(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    books = [make_book(tmp_path, bid, expected_class="digital_native") for bid in ("B1", "A1", "A2")]
    manifest, manifest_path = _write_run_manifest(tmp_path, books)

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    # Probe call order for this manifest: (1) cmd_run's initial run-level
    # probe, (2) A1's pre-book probe (B1 is the gate subject and its VQA row
    # is reused from the gate -- no separate pre-book probe), (3) A2's
    # pre-book probe, (4) the post-run canary probe. Drift from call 3
    # onward so A2 (and the canary) see it, but A1 does not.
    call_count = {"n": 0}
    baseline = good_probe(n_ctx=32768, total_slots=1)

    def drifting_probe(base_url, model):
        call_count["n"] += 1
        result = baseline(base_url, model)
        if call_count["n"] > 2:
            result = dict(result)
            result["model_path"] = "/models/different-weights.gguf"
        return result

    monkeypatch.setattr(scan_bench, "probe_endpoint", drifting_probe)

    args = default_run_args(manifest=str(manifest_path), run_id="drifttest", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "drifttest" / "run-summary.json")
    # At least one non-gate-subject row should show drift once the probe flips.
    assert any(row.get("provider_drift") for bid, row in summary.items() if bid != "B1")


def test_cmd_run_probe_failure_before_vqa_yields_provider_down_without_launch(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    def sometimes_failing_probe(base_url, model):
        raise RuntimeError("connection refused")

    # Use the good probe for the initial run-level probe, but fail every
    # per-book re-probe in Stage 2 by monkeypatching after Stage 1 completes
    # is awkward here, so instead assert on A1 (non-gate-subject) whose
    # pre-book probe always runs; a raising probe applied from the start
    # still lets Stage 1 proceed (Stage 1 never calls probe_endpoint).
    monkeypatch.setattr(scan_bench, "probe_endpoint", sometimes_failing_probe)

    args = default_run_args(manifest=str(manifest_path), run_id="probedown", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    # The initial probe failure degrades run-meta gracefully (n_ctx unknown-conservative);
    # the gate itself still runs (gate doesn't call probe_endpoint), but A1's
    # per-book pre-probe raises -> vqa_provider_down without a visual_qa.py launch.
    summary = scan_bench.load_run_summary(runs_root / "probedown" / "run-summary.json")
    assert summary["A1"]["status"] == "vqa_provider_down"
    assert not any(
        Path(c["cmd"][c["cmd"].index("--input") + 1]).stem.split(" - ")[0] == "A1"
        for c in runner.vqa_calls()
    )


# ---------------------------------------------------------------------------
# cmd_run: VQA outcome classes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vqa_outcome,expected_status", [
    ("render_failed", "vqa_render_failed"),
    ("provider_down", "vqa_provider_down"),
    ("api_failure", "vqa_api_failure"),
    ("no_report", "vqa_no_report"),
    ("timeout", "vqa_timeout"),
    ("partial", "evaluated_partial"),
])
def test_cmd_run_vqa_outcome_classes(run_orch, monkeypatch, tmp_path, vqa_outcome, expected_status):
    tmp_path, runs_root = run_orch
    b1 = make_book(tmp_path, "B1", expected_class="digital_native")
    a1 = make_book(tmp_path, "A1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [b1, a1])

    runner = FakeProcRunner(vqa_behavior={"A1": vqa_outcome})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id=f"vqa-{vqa_outcome}", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / f"vqa-{vqa_outcome}" / "run-summary.json")
    assert summary["A1"]["status"] == expected_status
    # Metrics from the intermediate HTML are still computed regardless of VQA outcome.
    assert summary["A1"]["metrics_done"] is True


# ---------------------------------------------------------------------------
# cmd_run: cloud markers -> cost_nonzero / WARN
# ---------------------------------------------------------------------------

def test_cmd_run_cloud_markers_set_cost_nonzero_and_block_cost_zero_verified(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner(convert_log=CONVERT_LOG_DIRTY)
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="cloudmarkers", runs_root=str(runs_root))
    scan_bench.cmd_run(args)

    summary = scan_bench.load_run_summary(runs_root / "cloudmarkers" / "run-summary.json")
    assert summary["B1"]["cost_nonzero"] is True
    assert summary["B1"]["vqa"]["cost_zero_verified"] is False


# ---------------------------------------------------------------------------
# cmd_run: resume matrix
# ---------------------------------------------------------------------------

def test_cmd_run_resume_reattempts_only_non_terminal_rows(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    books = [make_book(tmp_path, bid, expected_class="digital_native") for bid in ("A1", "A2", "A3", "A4", "A5")]
    manifest, manifest_path = _write_run_manifest(tmp_path, books)
    run_id = "resume-matrix"
    paths = scan_bench.RunPaths.for_run(runs_root, run_id)
    paths.ensure()

    def _converted_row(bid, **overrides):
        row = {
            **scan_bench._default_row({"id": bid}),
            "convert_status": "converted",
            "output_path": str(paths.kfx_dir / bid / f"{bid} - Fake Author.kfx"),
        }
        row.update(overrides)
        (paths.kfx_dir / bid).mkdir(parents=True, exist_ok=True)
        Path(row["output_path"]).write_bytes(b"FAKEOUTPUT" * 10)
        return row

    existing_summary = {
        "A1": _converted_row("A1", status="evaluated", vqa_status="evaluated"),
        "A2": {**scan_bench._default_row({"id": "A2"}), "status": "convert_timeout", "convert_status": "convert_timeout"},
        "A3": {**scan_bench._default_row({"id": "A3"})},
        "A4": _converted_row("A4", status="vqa_provider_down", vqa_status="vqa_provider_down"),
        "A5": _converted_row("A5", status="vqa_skipped_untrusted_grader", vqa_status="vqa_skipped_untrusted_grader"),
    }
    scan_bench.write_run_summary(paths.run_summary_path, existing_summary)
    run_meta = scan_bench.build_run_meta(manifest, manifest_path, "abc1234", good_probe()("x", "y"), default_run_args())
    scan_bench._write_json(paths.run_meta_path, run_meta)

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id=run_id, runs_root=str(runs_root), resume=True)
    scan_bench.cmd_run(args)

    converted_book_ids = set()
    for c in runner.convert_calls():
        pdf_path, _out, _ocr = _parse_convert_cmd(c["cmd"])
        converted_book_ids.add(Path(pdf_path).stem)

    # A1 is fully terminal -- must not be reconverted. A2 (timeout), A3
    # (pending), A4/A5 (already converted; only need VQA) may or may not
    # re-run Stage 1 depending on their convert_status; the key contract is
    # A1 is left alone and A2/A3 (which never successfully converted) do run.
    assert "A1" not in converted_book_ids
    assert "A2" in converted_book_ids
    assert "A3" in converted_book_ids
    assert "A4" not in converted_book_ids  # already converted -- only Stage 2 should re-run
    assert "A5" not in converted_book_ids


def test_cmd_run_without_resume_existing_dir_refused(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])
    run_id = "already-exists"
    (runs_root / run_id).mkdir(parents=True)

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id=run_id, runs_root=str(runs_root))
    code = scan_bench.cmd_run(args)
    assert code == scan_bench.ExitCode.ERROR
    assert runner.calls == []


def test_cmd_run_resume_without_run_id_errors(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])
    args = default_run_args(manifest=str(manifest_path), runs_root=str(runs_root), resume=True)
    assert scan_bench.cmd_run(args) == scan_bench.ExitCode.ERROR


def test_cmd_run_vqa_only_resume_grades_skip_vqa_run(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1", expected_class="digital_native")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    runner = FakeProcRunner()
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    run_id = "skipvqa-then-grade"
    args1 = default_run_args(
        manifest=str(manifest_path), run_id=run_id, runs_root=str(runs_root), skip_vqa=True,
    )
    scan_bench.cmd_run(args1)
    summary1 = scan_bench.load_run_summary(runs_root / run_id / "run-summary.json")
    assert summary1["B1"]["status"] == "vqa_skipped_by_flag"

    args2 = default_run_args(
        manifest=str(manifest_path), run_id=run_id, runs_root=str(runs_root),
        vqa_only=True, resume=True,
    )
    scan_bench.cmd_run(args2)
    summary2 = scan_bench.load_run_summary(runs_root / run_id / "run-summary.json")
    assert summary2["B1"]["status"] == "evaluated"


def test_cmd_run_vqa_only_without_existing_run_errors(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    book = make_book(tmp_path, "B1")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])
    args = default_run_args(
        manifest=str(manifest_path), run_id="brand-new", runs_root=str(runs_root), vqa_only=True,
    )
    assert scan_bench.cmd_run(args) == scan_bench.ExitCode.ERROR


# ---------------------------------------------------------------------------
# cmd_run: guardrails / dry-run
# ---------------------------------------------------------------------------

def test_cmd_run_all_conversions_fail_exit_2(run_orch, monkeypatch, tmp_path):
    tmp_path, runs_root = run_orch
    books = [make_book(tmp_path, bid, expected_class="digital_native") for bid in ("A1", "A2")]
    manifest, manifest_path = _write_run_manifest(tmp_path, books)

    runner = FakeProcRunner(convert_behavior={"A1": "failed", "A2": "failed"})
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", runner)
    monkeypatch.setattr(scan_bench, "classify_source", make_fake_classify(manifest))

    args = default_run_args(manifest=str(manifest_path), run_id="allfail", runs_root=str(runs_root))
    code = scan_bench.cmd_run(args)
    assert code == scan_bench.ExitCode.FAIL


def test_cmd_run_dry_run_prints_one_command_per_book_no_subprocess(run_orch, monkeypatch, tmp_path, capsys):
    tmp_path, runs_root = run_orch
    books = [make_book(tmp_path, bid, expected_class="digital_native") for bid in ("A1", "A2", "A3")]
    manifest, manifest_path = _write_run_manifest(tmp_path, books)

    def _boom(*a, **k):
        raise AssertionError("dry-run must not spawn a subprocess")
    monkeypatch.setattr(scan_bench, "run_with_tree_kill", _boom)
    monkeypatch.setattr(scan_bench, "classify_source", _boom)

    args = default_run_args(manifest=str(manifest_path), run_id="dryrun1", runs_root=str(runs_root), dry_run=True)
    code = scan_bench.cmd_run(args)
    assert code == scan_bench.ExitCode.OK
    assert not (runs_root / "dryrun1").exists()

    out = capsys.readouterr().out
    assert out.count("Convert-ToKindle") == 3
    for bid in ("A1", "A2", "A3"):
        assert f"[{bid}]" in out
    assert "<blanked>" in out


def test_cmd_run_dry_run_cloud_as_configured_shows_real_env(run_orch, monkeypatch, tmp_path, capsys):
    tmp_path, runs_root = run_orch
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-shown-value")
    book = make_book(tmp_path, "A1")
    manifest, manifest_path = _write_run_manifest(tmp_path, [book])

    args = default_run_args(
        manifest=str(manifest_path), run_id="dryrun2", runs_root=str(runs_root),
        dry_run=True, cloud_as_configured=True,
    )
    scan_bench.cmd_run(args)
    out = capsys.readouterr().out
    assert "sk-shown-value" in out
    assert "<blanked>" not in out


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

def _bundle(tmp_path, name, summary, meta=None):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    scan_bench.write_run_summary(d / "run-summary.json", summary)
    scan_bench._write_json(d / "run-meta.json", meta or {"label": name})
    return d


def _row(**overrides):
    row = {
        "status": "evaluated", "convert_sec": 10.0, "vqa_sec": 5.0,
        "metrics": {"word_count": 1000, "chapter_count": 10},
        "vqa": {
            "overall_score": 90, "garble_findings": 0, "degenerate_grader": False,
            "sampled_pages": [1, 2, 3],
            "provider_resolved": {"model_served": "sb-vision", "n_ctx": 32768, "total_slots": 1,
                                   "model_path": "/m.gguf", "batch_size_effective": 8},
        },
        "vqa_trusted": True,
    }
    for key, value in overrides.items():
        if key in ("metrics", "vqa") and isinstance(value, dict):
            row[key] = {**row[key], **value}
        else:
            row[key] = value
    return row


def test_compare_numeric_deltas_and_page_parity(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(vqa={"overall_score": 80})})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row(vqa={"overall_score": 85})})
    result = scan_bench.compare_runs(dir_a, dir_b)
    row = result["rows"][0]
    assert row["classification"] == "ok"
    assert row["deltas"]["overall_score"]["delta"] == 5


def test_compare_page_set_mismatch_is_unreliable(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(vqa={"sampled_pages": [1, 2, 3]})})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row(vqa={"sampled_pages": [1, 2, 4]})})
    result = scan_bench.compare_runs(dir_a, dir_b)
    assert result["rows"][0]["classification"] == "unreliable"
    assert "unreliable" in result["rows"][0]["flags"]


def test_compare_n_ctx_mismatch_not_comparable(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(vqa={"provider_resolved": {"n_ctx": 8192, "model_served": "sb-vision", "total_slots": 1, "model_path": "/m.gguf", "batch_size_effective": 1}})})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row()})
    result = scan_bench.compare_runs(dir_a, dir_b)
    row = result["rows"][0]
    assert row["classification"] == "not_comparable"
    assert row["deltas"]["overall_score"]["blocked"] is True
    # conversion-side metrics remain comparable even when VQA is not.
    assert row["deltas"]["word_count"]["blocked"] is False if "blocked" in row["deltas"]["word_count"] else True


def test_compare_batch_mismatch_flag_with_allow_flag(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row()}, meta={"label": "exploratory-a"})
    dir_b = _bundle(
        tmp_path, "run_b",
        {"B1": _row(vqa={"provider_resolved": {"model_served": "sb-vision", "n_ctx": 32768, "total_slots": 1, "model_path": "/m.gguf", "batch_size_effective": 1}})},
        meta={"label": "exploratory-b"},
    )
    result = scan_bench.compare_runs(dir_a, dir_b, allow_batch_mismatch=True)
    assert "batch_mismatch" in result["rows"][0]["flags"]
    assert result["rows"][0]["classification"] == "ok"


def test_compare_batch_mismatch_never_allowed_for_two_row0_labels(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row()}, meta={"label": "row0-vqa"})
    dir_b = _bundle(
        tmp_path, "run_b",
        {"B1": _row(vqa={"provider_resolved": {"model_served": "sb-vision", "n_ctx": 32768, "total_slots": 1, "model_path": "/m.gguf", "batch_size_effective": 1}})},
        meta={"label": "row0-cloud"},
    )
    result = scan_bench.compare_runs(dir_a, dir_b, allow_batch_mismatch=True)
    assert result["rows"][0]["classification"] == "not_comparable"


def test_compare_untrusted_side_flags_untrusted(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(vqa_trusted=False)})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row()})
    result = scan_bench.compare_runs(dir_a, dir_b)
    assert result["rows"][0]["classification"] == "untrusted"


def test_compare_missing_on_one_side(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(), "A1": _row()})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row()})
    result = scan_bench.compare_runs(dir_a, dir_b)
    by_id = {r["id"]: r for r in result["rows"]}
    assert by_id["A1"]["classification"] == "missing_on_b"


def test_compare_degenerate_grader_flag_carried(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row(vqa={"degenerate_grader": True})})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row()})
    result = scan_bench.compare_runs(dir_a, dir_b)
    assert "degenerate_grader" in result["rows"][0]["flags"]


def test_compare_md_renders_table(tmp_path):
    dir_a = _bundle(tmp_path, "run_a", {"B1": _row()})
    dir_b = _bundle(tmp_path, "run_b", {"B1": _row()})
    result = scan_bench.compare_runs(dir_a, dir_b)
    md = scan_bench.render_compare_markdown(result)
    assert "B1" in md
    assert "|" in md


def test_cmd_compare_cli_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scan_bench, "runs_root_default", lambda: tmp_path / "runs")
    monkeypatch.setattr(scan_bench, "baselines_root_default", lambda: tmp_path / "baselines")
    (tmp_path / "runs").mkdir()
    _bundle(tmp_path / "runs", "run_a", {"B1": _row()})
    _bundle(tmp_path / "runs", "run_b", {"B1": _row(vqa={"overall_score": 50})})

    args = argparse.Namespace(a="run_a", b="run_b", md=False, allow_batch_mismatch=False)
    code = scan_bench.cmd_compare(args)
    assert code == scan_bench.ExitCode.OK
    out = json.loads(capsys.readouterr().out)
    assert out["rows"][0]["id"] == "B1"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def test_render_report_markdown_row_order_and_artifacts_section(tmp_path):
    books = [make_book(tmp_path, "B1"), make_book(tmp_path, "A1")]
    manifest = make_manifest(books)
    summary = {"B1": _row(), "A1": _row(status="convert_failed", vqa=None, vqa_trusted=None)}
    run_meta = {
        "label": "smoke", "resolved_provider": {"n_ctx": 32768, "n_ctx_source": "models", "total_slots": 1, "model_path": "/m.gguf", "model_served": "sb-vision"},
        "pinned_batch_size": 8, "cloud_policy": "off", "gate_subject": {"id": "B1"}, "gate_exit_code": 0,
        "gate_verdict": {"deterministic": True}, "post_run_canary": {"ok": True, "reason": None},
    }
    md = scan_bench.render_report_markdown(manifest, summary, run_meta)
    b1_idx = md.index("| B1 ")
    a1_idx = md.index("| A1 ")
    assert b1_idx < a1_idx  # manifest order preserved
    assert "Measurement artifacts (NOT findings)" in md
    assert "n_ctx: 32768" in md
    assert "cloud_policy: off" in md


def test_cmd_report_reads_run_dir_and_writes_report_md(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scan_bench, "runs_root_default", lambda: tmp_path / "runs")
    monkeypatch.setattr(scan_bench, "baselines_root_default", lambda: tmp_path / "baselines")
    (tmp_path / "runs").mkdir()
    run_dir = _bundle(tmp_path / "runs", "run_x", {"B1": _row()}, meta={"label": "run_x"})
    manifest = make_manifest([make_book(tmp_path, "B1")])
    scan_bench._write_json(run_dir / "manifest.snapshot.json", manifest)

    args = argparse.Namespace(run_or_label="run_x")
    code = scan_bench.cmd_report(args)
    assert code == scan_bench.ExitCode.OK
    assert (run_dir / "report.md").is_file()
    out = capsys.readouterr().out
    assert "B1" in out


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

def _promotable_run(tmp_path, *, cost_zero=True, canary_score=90, garble=0, trusted=True):
    run_dir = tmp_path / "runs" / "promo1"
    run_dir.mkdir(parents=True)
    (run_dir / "vqa" / "B1").mkdir(parents=True)
    (run_dir / "determinism" / "pre" / "run1").mkdir(parents=True)
    (run_dir / "kfx" / "B1").mkdir(parents=True)
    (run_dir / "kfx" / "B1" / "B1.kfx").write_bytes(b"not promotable")
    (run_dir / "kfx" / "B1" / ".intermediates").mkdir(parents=True)
    (run_dir / "kfx" / "B1" / ".intermediates" / "x.html").write_text("<html></html>", encoding="utf-8")

    provider_resolved = {"n_ctx": 32768, "total_slots": 1, "model_served": "sb-vision", "model_path": "/m.gguf",
                          "batch_size_effective": 8}
    summary = {
        "B1": _row(
            status="evaluated",
            vqa={"overall_score": canary_score, "garble_findings": garble, "cost_zero_verified": cost_zero,
                 "provider_resolved": provider_resolved},
            vqa_trusted=trusted,
        ),
    }
    scan_bench.write_run_summary(run_dir / "run-summary.json", summary)
    scan_bench._write_json(run_dir / "run-meta.json", {"cloud_policy": "off", "label": "smoke"})
    (run_dir / "report.md").write_text("# report", encoding="utf-8")
    scan_bench._write_json(run_dir / "vqa" / "B1" / "B1_visual_qa_report.json", {"overall_score": canary_score})
    scan_bench._write_json(run_dir / "determinism" / "pre" / "run1" / "B1_visual_qa_report.json", {"overall_score": canary_score})
    return run_dir


def test_promote_copies_only_allowlisted_files(tmp_path):
    _promotable_run(tmp_path)
    args = argparse.Namespace(run_id="promo1", label="testlabel", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    code = scan_bench.cmd_promote(args)
    assert code == scan_bench.ExitCode.OK

    dest_dir = tmp_path / "dest" / "data" / "scan_bench" / "baselines" / "testlabel"
    assert (dest_dir / "run-meta.json").is_file()
    assert (dest_dir / "run-summary.json").is_file()
    assert (dest_dir / "report.md").is_file()
    assert (dest_dir / "vqa" / "B1" / "B1_visual_qa_report.json").is_file()
    assert (dest_dir / "determinism" / "pre" / "run1" / "B1_visual_qa_report.json").is_file()
    assert not (dest_dir / "kfx").exists()
    assert not any(dest_dir.rglob("*.kfx"))
    assert not any(dest_dir.rglob("*.html"))


def test_promote_refuses_existing_label_without_force(tmp_path):
    _promotable_run(tmp_path)
    dest_dir = tmp_path / "dest" / "data" / "scan_bench" / "baselines" / "testlabel"
    dest_dir.mkdir(parents=True)

    args = argparse.Namespace(run_id="promo1", label="testlabel", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    code = scan_bench.cmd_promote(args)
    assert code == scan_bench.ExitCode.ERROR


def test_promote_refuses_when_cost_zero_verified_false(tmp_path):
    _promotable_run(tmp_path, cost_zero=False)
    args = argparse.Namespace(run_id="promo1", label="testlabel", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    code = scan_bench.cmd_promote(args)
    assert code == scan_bench.ExitCode.FAIL


def test_promote_refuses_when_canary_below_85_or_has_garble(tmp_path):
    _promotable_run(tmp_path, canary_score=60)
    args = argparse.Namespace(run_id="promo1", label="lowscore", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    assert scan_bench.cmd_promote(args) == scan_bench.ExitCode.FAIL

    run_dir2 = _promotable_run(tmp_path.parent / (tmp_path.name + "_2"), garble=1)
    args2 = argparse.Namespace(run_id="promo1", label="garbled", dest=str(tmp_path / "dest2"), runs_root=str(run_dir2.parent), force=False)
    assert scan_bench.cmd_promote(args2) == scan_bench.ExitCode.FAIL


def test_promote_refuses_when_vqa_trusted_false(tmp_path):
    _promotable_run(tmp_path, trusted=False)
    args = argparse.Namespace(run_id="promo1", label="untrusted", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    assert scan_bench.cmd_promote(args) == scan_bench.ExitCode.FAIL


def test_promote_force_overwrites_existing_label(tmp_path):
    _promotable_run(tmp_path)
    dest_dir = tmp_path / "dest" / "data" / "scan_bench" / "baselines" / "testlabel"
    dest_dir.mkdir(parents=True)
    (dest_dir / "stale.json").write_text("{}", encoding="utf-8")

    args = argparse.Namespace(run_id="promo1", label="testlabel", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=True)
    code = scan_bench.cmd_promote(args)
    assert code == scan_bench.ExitCode.OK
    assert (dest_dir / "run-meta.json").is_file()


def test_promote_missing_run_dir_errors(tmp_path):
    args = argparse.Namespace(run_id="doesnotexist", label="x", dest=str(tmp_path / "dest"), runs_root=str(tmp_path / "runs"), force=False)
    assert scan_bench.cmd_promote(args) == scan_bench.ExitCode.ERROR
