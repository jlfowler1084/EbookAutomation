"""tests/test_scan_bench.py — EB-392 Unit 3 preflight tests.

Hermetic: no network, no real git side effects (subprocess.run for git is
monkeypatched), no dependency on the developer machine's tool layout
(config/settings.json paths.* and shutil.which are monkeypatched). The one
exception is the "real manifest validates against schema" test, which reads
the tracked data/scan_bench/manifest.json but performs no filesystem/network
checks against its source_path entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def test_find_junctions_detects_symlink_directory(tmp_path, monkeypatch):
    fake_link = tmp_path / "sub" / "looks_like_link"
    fake_link.mkdir(parents=True)
    (tmp_path / "other").mkdir()

    def fake_islink(p):
        return os.path.normpath(str(p)) == os.path.normpath(str(fake_link))

    monkeypatch.setattr(scan_bench.os.path, "islink", fake_islink)
    hits = scan_bench.find_junctions(tmp_path)
    assert any(os.path.normpath(str(h)) == os.path.normpath(str(fake_link)) for h in hits)


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


def test_run_compare_report_promote_stubs_exit_3(capsys):
    for name in ("run", "compare", "report", "promote"):
        code = scan_bench.main([name])
        assert code == 3


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
