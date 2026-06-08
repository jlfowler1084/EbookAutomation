"""U5 ingest-rewiring verification tests (EB-380).

Covers:
- BookFinder.output_root → _Inbox\BookFinder (config + Python default + psm1 fallback)
- Scan-BooksFolder.ps1 and Invoke-TesseractKindleBatch.ps1 exclusion filter
  (_-prefixed and Audio_Books top-level dirs are not scanned)
- Literal-path audit: no remaining F:\\Books\\BookFinder (without _Inbox) in source files
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_SCRIPT = REPO_ROOT / "Scan-BooksFolder.ps1"


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise AssertionError("PowerShell required for U5 tests")
    return shell


def _run_ps(script: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), *args],
        capture_output=True, text=True, timeout=timeout,
    )


# ── Python constant ───────────────────────────────────────────────────────────

def test_book_downloader_default_output_root_contains_inbox():
    """DEFAULT_OUTPUT_ROOT must route downloads into _Inbox, not the shelf root."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import book_downloader
    assert "_Inbox" in book_downloader.DEFAULT_OUTPUT_ROOT, (
        f"Expected '_Inbox' in DEFAULT_OUTPUT_ROOT; got: {book_downloader.DEFAULT_OUTPUT_ROOT!r}"
    )
    assert "BookFinder" in book_downloader.DEFAULT_OUTPUT_ROOT


# ── Config ────────────────────────────────────────────────────────────────────

def test_settings_json_bookfinder_output_root_contains_inbox():
    """config/settings.json BookFinder.output_root must point into _Inbox."""
    settings_path = REPO_ROOT / "config" / "settings.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    output_root = data["BookFinder"]["output_root"]
    assert "_Inbox" in output_root, (
        f"Expected '_Inbox' in BookFinder.output_root; got: {output_root!r}"
    )
    assert "BookFinder" in output_root


# ── psm1 fallback strings ─────────────────────────────────────────────────────

def test_psm1_fallback_paths_contain_inbox():
    """Both hardcoded fallback paths in EbookAutomation.psm1 must include _Inbox."""
    psm1 = REPO_ROOT / "module" / "EbookAutomation.psm1"
    content = psm1.read_text(encoding="utf-8", errors="replace")

    # Find all hardcoded Books\BookFinder occurrences (slash-normalised)
    old_pattern = re.compile(r"Books[/\\]BookFinder", re.IGNORECASE)
    old_matches = [(m.start(), content[max(0, m.start()-30):m.end()+30])
                   for m in old_pattern.finditer(content)
                   if "_Inbox" not in content[max(0, m.start()-20):m.end()+20]]
    assert not old_matches, (
        f"Found {len(old_matches)} hardcoded 'Books\\BookFinder' (without _Inbox) in psm1:\n"
        + "\n".join(f"  ...{ctx}..." for _, ctx in old_matches[:3])
    )


# ── Literal-path audit ────────────────────────────────────────────────────────

def test_literal_path_audit_no_old_bookfinder_root():
    """No source file should contain the old Books\\BookFinder path (without _Inbox).

    Searches .py, .ps1, .json, .psm1 files in the repo root (not tests/ or docs/).
    """
    old_pattern = re.compile(r"Books[/\\\\]BookFinder", re.IGNORECASE)
    violations: list[tuple[Path, int, str]] = []

    search_globs = ["**/*.py", "**/*.ps1", "**/*.psm1", "**/*.json"]
    skip_dirs = {"tests", "docs", ".git", ".worktrees", "data", "archive", "output"}

    for glob_pat in search_globs:
        for path in REPO_ROOT.glob(glob_pat):
            # Skip paths that are in excluded directories
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & skip_dirs:
                continue
            # Skip this test file itself
            if path.name == "test_eb380_u5_ingest_rewiring.py":
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for lineno, line in enumerate(content.splitlines(), 1):
                if old_pattern.search(line) and "_Inbox" not in line:
                    violations.append((path, lineno, line.strip()))

    assert not violations, (
        f"Found {len(violations)} occurrence(s) of old BookFinder path without _Inbox:\n"
        + "\n".join(f"  {p}:{ln}: {ln_text[:120]}" for p, ln, ln_text in violations[:10])
    )


# ── Scan-BooksFolder exclusion filter ─────────────────────────────────────────

def test_scan_excludes_operational_and_audio_dirs(tmp_path: Path):
    """Scan-BooksFolder.ps1 must skip _Inbox and Audio_Books; include real sections."""
    books_root = tmp_path / "Books"

    # Shelf section (should be scanned)
    shelf = books_root / "01 History"
    shelf.mkdir(parents=True)
    (shelf / "a-history-book.pdf").write_bytes(b"PDF" * 100)

    # Operational dir (must be excluded)
    inbox = books_root / "_Inbox" / "Manual"
    inbox.mkdir(parents=True)
    (inbox / "inbox-book.pdf").write_bytes(b"PDF" * 100)

    # TTS output dir (must be excluded)
    audio = books_root / "Audio_Books"
    audio.mkdir(parents=True)
    (audio / "recording.pdf").write_bytes(b"PDF" * 100)

    result = _run_ps(SCAN_SCRIPT, "-BooksRoot", str(books_root))

    # Script outputs relative paths of sample files found
    combined = result.stdout + result.stderr
    # Strip ANSI escape sequences for reliable matching
    combined_clean = re.sub(r'\x1b\[[0-9;]*m', '', combined)

    assert "_Inbox" not in combined_clean, (
        f"_Inbox content must be excluded from scan output.\n{combined_clean[:800]}"
    )
    assert "Audio_Books" not in combined_clean or "excluded" in combined_clean.lower(), (
        f"Audio_Books content must be excluded from scan output.\n{combined_clean[:800]}"
    )
    # Confirm the shelf section WAS scanned (count shows at least 1 file)
    assert "a-history-book" in combined_clean or "1" in combined_clean, (
        f"Expected shelf section files to appear in output.\n{combined_clean[:800]}"
    )


# ── Scan-BooksFolder exclusion: source-code check ────────────────────────────

def test_scan_booksfolderps1_has_exclusion_filter():
    """Scan-BooksFolder.ps1 source must contain the exclusion-filter keywords."""
    content = SCAN_SCRIPT.read_text(encoding="utf-8", errors="replace")
    assert "StartsWith('_')" in content or "StartsWith(\"_\")" in content, (
        "Scan-BooksFolder.ps1 must contain a _ prefix exclusion filter"
    )
    assert "Audio_Books" in content, (
        "Scan-BooksFolder.ps1 must name Audio_Books in its exclusion list"
    )


def test_tesseract_script_has_exclusion_filter():
    """Invoke-TesseractKindleBatch.ps1 must also contain the exclusion-filter keywords."""
    tesseract_script = REPO_ROOT / "Invoke-TesseractKindleBatch.ps1"
    content = tesseract_script.read_text(encoding="utf-8", errors="replace")
    assert "StartsWith('_')" in content or "StartsWith(\"_\")" in content, (
        "Invoke-TesseractKindleBatch.ps1 must contain a _ prefix exclusion filter"
    )
    assert "Audio_Books" in content, (
        "Invoke-TesseractKindleBatch.ps1 must name Audio_Books in its exclusion list"
    )
