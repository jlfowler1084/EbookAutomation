"""pytest suite for scripts/Invoke-BookFileGuarded.ps1 (EB-380 U3/U4).

All tests drive the wrapper via subprocess.run([pwsh, -File, SCRIPT, ...]) so
the entry-point guard and the full PowerShell runtime are exercised.  Parsing
queue JSONL uses encoding='utf-8-sig' in case PowerShell writes a BOM.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "Invoke-BookFileGuarded.ps1"


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise AssertionError("PowerShell is required for Invoke-BookFileGuarded tests")
    return shell


def _run_script(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run Invoke-BookFileGuarded.ps1 via pwsh -File (child process)."""
    cmd = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _make_settings(tmp_path: Path, library_root: Path) -> Path:
    """Write a minimal settings.json pointing at tmp_path directories."""
    settings: dict = {
        "library": {
            "library_root": str(library_root),
            "calibre_library": str(tmp_path / "Calibre"),
            "audio_root": str(library_root / "Audio_Books"),
            "documents_root": str(tmp_path / "Documents"),
            "materialize_mode": "copy",
            "trash_retention_days": 30,
            "operational_folders": ["_Inbox", "_Needs_Review", "_Trash_Pending"],
            "scan_exclude": ["Audio_Books"],
            "max_path_length": 240,
        }
    }
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    return settings_path


def _rows(queue_path: Path) -> list[dict]:
    """Parse JSONL queue; utf-8-sig handles BOM if PowerShell wrote it."""
    return [
        json.loads(line)
        for line in queue_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _write_book(path: Path, content: bytes = b"FAKEPDF" * 400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_child_process_happy_path(tmp_path: Path):
    """MANDATORY: child-process via pwsh -File proves the entry guard fires.

    An in-process dot-source-and-call test would pass even if the entry guard
    silently no-ops.  Only a child-process invocation exercises the real guard.
    """
    library_root = tmp_path / "Books"
    inbox_manual = library_root / "_Inbox" / "Manual"
    inbox_manual.mkdir(parents=True)
    _write_book(inbox_manual / "history-of-rome.pdf")

    run_dir = tmp_path / "run"
    settings_path = _make_settings(tmp_path, library_root)

    result = _run_script(
        "-LibraryRoot", str(library_root),
        "-RunDir",      str(run_dir),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
    )

    assert result.returncode == 0, (
        f"Exit {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )

    # Verify the queue artifact — not just exit code
    queue_path = run_dir / "inbox-proposals.jsonl"
    assert queue_path.exists(), "Queue artifact must be written after a successful sweep"

    rows = _rows(queue_path)
    assert len(rows) >= 1, (
        "Expected at least one proposal row for history-of-rome.pdf"
    )


def test_library_root_mismatch_refused(tmp_path: Path):
    """Wrapper must refuse (non-zero exit) when -LibraryRoot != canonical config."""
    library_root = tmp_path / "Books"
    wrong_root   = tmp_path / "WrongBooks"
    wrong_root.mkdir(parents=True)
    settings_path = _make_settings(tmp_path, library_root)

    result = _run_script(
        "-LibraryRoot", str(wrong_root),
        "-RunDir",      str(tmp_path / "run"),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
    )

    assert result.returncode != 0, (
        "Mismatch between -LibraryRoot and config canonical value must produce non-zero exit"
    )
    combined = result.stdout + result.stderr
    assert "mismatch" in combined.lower() or "error" in combined.lower(), (
        f"Expected an error/mismatch message in output:\n{combined[:600]}"
    )


def test_empty_inbox_writes_artifact(tmp_path: Path):
    """Queue artifact must exist even when _Inbox is empty (heartbeat/idempotency)."""
    library_root = tmp_path / "Books"
    (library_root / "_Inbox").mkdir(parents=True)

    run_dir = tmp_path / "run"
    settings_path = _make_settings(tmp_path, library_root)

    result = _run_script(
        "-LibraryRoot", str(library_root),
        "-RunDir",      str(run_dir),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
    )

    assert result.returncode == 0, (
        f"Empty inbox must exit 0\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert (run_dir / "inbox-proposals.jsonl").exists(), (
        "Queue artifact must be written even for a zero-file sweep"
    )


def test_discord_sender_missing_is_best_effort(tmp_path: Path):
    """Missing Discord sender must not fail the run — sweep is best-effort."""
    library_root = tmp_path / "Books"
    (library_root / "_Inbox").mkdir(parents=True)

    run_dir = tmp_path / "run"
    settings_path = _make_settings(tmp_path, library_root)
    absent_sender = tmp_path / "no_sender_here.ps1"  # intentionally absent

    result = _run_script(
        "-LibraryRoot",  str(library_root),
        "-RunDir",       str(run_dir),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
        "-DiscordSender", str(absent_sender),
    )

    assert result.returncode == 0, (
        f"Missing Discord sender must not fail the run\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert (run_dir / "inbox-proposals.jsonl").exists(), (
        "Queue artifact must still be written despite missing Discord sender"
    )


def test_no_webhook_url_in_output(tmp_path: Path):
    """Leak guard: webhook URL/token from sender must not surface in wrapper output.

    Creates a fake sender that echoes a fake URL to stdout; the PS wrapper must
    swallow the sender's output (*> $null) so the URL never reaches the caller.
    """
    library_root = tmp_path / "Books"
    (library_root / "_Inbox").mkdir(parents=True)

    run_dir = tmp_path / "run"
    settings_path = _make_settings(tmp_path, library_root)

    # Fake sender that writes a fake webhook URL to stdout
    fake_token = "FAKE_TOKEN_abc123_secret"
    fake_url   = f"https://discord.com/api/webhooks/999999/{fake_token}"
    fake_sender = tmp_path / "fake_sender.ps1"
    fake_sender.write_text(
        f"param([string]$ProjectName, [string]$EventType, [string]$Summary)\n"
        f"Write-Host 'SENDER_CALLED'\n"
        f"Write-Host 'leaked_url={fake_url}'\n",
        encoding="utf-8",
    )

    result = _run_script(
        "-LibraryRoot",  str(library_root),
        "-RunDir",       str(run_dir),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
        "-DiscordSender", str(fake_sender),
    )

    # Capture ALL output (stdout + stderr) — the test uses capture_output=True
    combined = result.stdout + result.stderr
    assert fake_token not in combined, (
        f"Webhook token must not appear in wrapper output.\n"
        f"Found in combined output:\n{combined[:800]}"
    )
    assert fake_url not in combined, (
        f"Webhook URL must not appear in wrapper output.\n"
        f"Found in combined output:\n{combined[:800]}"
    )


def test_heartbeat_on_quiet_run(tmp_path: Path):
    """Zero-file inbox must emit a heartbeat so silence != cron dead."""
    library_root = tmp_path / "Books"
    (library_root / "_Inbox").mkdir(parents=True)

    run_dir = tmp_path / "run"
    settings_path = _make_settings(tmp_path, library_root)
    absent_sender = tmp_path / "no_sender.ps1"  # absent → digest goes to stdout

    result = _run_script(
        "-LibraryRoot",  str(library_root),
        "-RunDir",       str(run_dir),
        "-SettingsPath", str(settings_path),
        "-SettleSeconds", "0",
        "-DiscordSender", str(absent_sender),
    )

    assert result.returncode == 0, result.stderr

    combined = result.stdout + result.stderr
    assert (
        "0 new files" in combined
        or "0 files" in combined
        or "healthy" in combined
        or "swept 0" in combined
    ), (
        f"Expected heartbeat indicator in quiet-run output.\n"
        f"Got: {combined[:600]}"
    )
