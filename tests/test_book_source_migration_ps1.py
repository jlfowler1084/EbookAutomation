from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "Invoke-BookSourceMigration.ps1"


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise AssertionError("PowerShell is required for Invoke-BookSourceMigration.ps1 tests")
    return shell


def _run_script(*args: str) -> subprocess.CompletedProcess:
    cmd = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _rows(report_run: Path) -> list[dict]:
    manifest = report_run / "migration-manifest.jsonl"
    return [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def test_dry_run_is_inert_and_skips_existing_hash(tmp_path: Path):
    target = tmp_path / "Books"
    migration = target / "_Inbox" / "Migration"
    report = tmp_path / "reports"
    copy_source = tmp_path / "copy-source"
    move_source = tmp_path / "move-source"

    target.mkdir(parents=True)
    copy_source.mkdir()
    move_source.mkdir()

    (copy_source / "new-book.epub").write_bytes(b"new epub")
    duplicate_bytes = b"already present"
    (move_source / "already.pdf").write_bytes(duplicate_bytes)
    (target / "01 History").mkdir()
    (target / "01 History" / "already.pdf").write_bytes(duplicate_bytes)

    result = _run_script(
        "-NoDefaultSources",
        "-AdditionalCopySource",
        str(copy_source),
        "-AdditionalMoveSource",
        str(move_source),
        "-TargetRoot",
        str(target),
        "-MigrationRoot",
        str(migration),
        "-ReportRoot",
        str(report),
        "-Stamp",
        "DRYRUN",
    )

    assert result.returncode == 0, result.stderr
    assert (copy_source / "new-book.epub").exists()
    assert (move_source / "already.pdf").exists()
    assert not (migration / "DRYRUN").exists(), "dry-run must not create the staging tree"

    rows = _rows(report / "DRYRUN")
    by_name = {Path(row["source_path"]).name: row for row in rows}
    assert by_name["new-book.epub"]["planned_action"] == "stage-copy"
    assert by_name["new-book.epub"]["executed"] is False
    assert by_name["already.pdf"]["planned_action"] == "skip-existing-hash"
    assert by_name["already.pdf"]["source_removed"] is False


def test_apply_copies_calibre_like_source_and_removes_download_like_source_after_stage(
    tmp_path: Path,
):
    target = tmp_path / "Books"
    migration = target / "_Inbox" / "Migration"
    report = tmp_path / "reports"
    copy_source = tmp_path / "calibre-source"
    move_source = tmp_path / "downloads-source"

    target.mkdir(parents=True)
    copy_source.mkdir()
    move_source.mkdir()

    copy_file = copy_source / "keep.epub"
    move_file = move_source / "move.pdf"
    copy_file.write_bytes(b"copy source stays")
    move_file.write_bytes(b"move source removed after verified copy")

    result = _run_script(
        "-Apply",
        "-NoDefaultSources",
        "-NoExistingHashScan",
        "-AdditionalCopySource",
        str(copy_source),
        "-AdditionalMoveSource",
        str(move_source),
        "-TargetRoot",
        str(target),
        "-MigrationRoot",
        str(migration),
        "-ReportRoot",
        str(report),
        "-Stamp",
        "APPLY",
    )

    assert result.returncode == 0, result.stderr
    assert copy_file.exists(), "copy policy must leave the source in place"
    assert not move_file.exists(), "move policy removes source only after staging"

    rows = _rows(report / "APPLY")
    by_name = {Path(row["source_path"]).name: row for row in rows}
    assert by_name["keep.epub"]["planned_action"] == "stage-copy"
    assert by_name["keep.epub"]["executed"] is True
    assert by_name["keep.epub"]["source_removed"] is False
    assert Path(by_name["keep.epub"]["destination_path"]).read_bytes() == b"copy source stays"

    assert by_name["move.pdf"]["planned_action"] == "stage-move"
    assert by_name["move.pdf"]["executed"] is True
    assert by_name["move.pdf"]["source_removed"] is True
    assert Path(by_name["move.pdf"]["destination_path"]).read_bytes() == b"move source removed after verified copy"
