import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.actuate import DEFAULT_OPERATIONAL, apply_manifest, route_target
from book_filer.backup import build_backup_proof
from book_filer.journal import append_record
from book_filer.manifest import ManifestRow, manifest_digest


def _row(**kw) -> ManifestRow:
    base = dict(
        original_path=r"F:\Books\_Inbox\x.epub", destination_path="",
        sha256="abc123", size=10, planned_calibre_key="isbn:9780", calibre_id=None, isbn="9780",
        format="epub", section=None, subcategory=None,
        author_sort="A, B", title="T", year=2000, duplicate_group_id=None, canonical_reason=None,
        classification_confidence=0.9, classification_source="rule", taxonomy_version=1,
        tool_version="0.4.0", action="review", undo_action="", review_required=True,
    )
    base.update(kw)
    return ManifestRow(**base)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _signed_verdict(rows, **overrides) -> dict:
    v = {
        "green": True,
        "manifest_digest": manifest_digest(rows),
        "gates": {"auto_shelf_floor": {"pass": True}, "trash_safety": {"pass": True}},
    }
    v.update(overrides)
    return v


def _build_library(tmp_path):
    """A synthetic F:\\Books-like root with 4 source files + a 4-row manifest
    (one per action: copy / review / trash / quarantine)."""
    lib = tmp_path / "Books"
    contents = {
        "_Inbox/good.epub": b"good-content",
        "_Inbox/maybe.epub": b"maybe-content",
        "_Inbox/dupe.epub": b"dupe-content",
        "_Inbox/weird.epub": b"weird-content",
    }
    for rel, c in contents.items():
        p = lib / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(c)
    rows = [
        _row(original_path=str(lib / "_Inbox" / "good.epub"),
             destination_path=str(lib / "01 History" / "A - Good.epub"),
             action="copy", section="01 History", review_required=False, sha256=_sha(b"good-content")),
        _row(original_path=str(lib / "_Inbox" / "maybe.epub"),
             action="review", sha256=_sha(b"maybe-content")),
        _row(original_path=str(lib / "_Inbox" / "dupe.epub"),
             action="trash", review_required=False, sha256=_sha(b"dupe-content")),
        _row(original_path=str(lib / "_Inbox" / "weird.epub"),
             action="quarantine", sha256=_sha(b"weird-content")),
    ]
    return lib, rows


def _snapshot(root: Path) -> dict:
    return {str(p): p.stat().st_size for p in sorted(root.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #

def test_route_target_maps_each_action(tmp_path):
    lib = tmp_path / "Books"
    shelve = _row(original_path=str(lib / "_Inbox" / "a.epub"),
                  destination_path=str(lib / "01 History" / "a.epub"), action="copy")
    assert route_target(shelve, lib, DEFAULT_OPERATIONAL) == lib / "01 History" / "a.epub"
    review = _row(original_path=str(lib / "_Inbox" / "b.epub"), action="review")
    assert route_target(review, lib, DEFAULT_OPERATIONAL) == lib / "_Needs_Review" / "_Inbox" / "b.epub"
    trash = _row(original_path=str(lib / "_Inbox" / "c.epub"), action="trash")
    assert route_target(trash, lib, DEFAULT_OPERATIONAL) == lib / "_Trash_Pending" / "_Inbox" / "c.epub"
    quar = _row(original_path=str(lib / "_Inbox" / "d.epub"), action="quarantine")
    assert route_target(quar, lib, DEFAULT_OPERATIONAL) == lib / "_Quarantine" / "_Inbox" / "d.epub"
    # unhandled action -> None (skip + log)
    assert route_target(_row(action="merge-format"), lib, DEFAULT_OPERATIONAL) is None


# --------------------------------------------------------------------------- #
# Apply (R1/R4/R8) — realizes the target layout
# --------------------------------------------------------------------------- #

def test_apply_realizes_target_layout(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, run_dir, mode="apply", stamp="S")
    assert result.ok and result.moved_count == 4
    assert (lib / "01 History" / "A - Good.epub").read_bytes() == b"good-content"
    assert (lib / "_Needs_Review" / "_Inbox" / "maybe.epub").read_bytes() == b"maybe-content"
    assert (lib / "_Trash_Pending" / "_Inbox" / "dupe.epub").read_bytes() == b"dupe-content"
    assert (lib / "_Quarantine" / "_Inbox" / "weird.epub").read_bytes() == b"weird-content"
    assert not (lib / "_Inbox" / "good.epub").exists()   # source gone
    journal_lines = (run_dir / "journal.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(journal_lines) == 4
    assert (run_dir / "apply-report.md").exists()


def test_trash_routes_to_trash_pending_and_is_not_deleted(tmp_path):
    lib, rows = _build_library(tmp_path)
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, tmp_path / "run", mode="apply", stamp="S")
    assert result.ok
    trashed = lib / "_Trash_Pending" / "_Inbox" / "dupe.epub"
    assert trashed.is_file() and trashed.read_bytes() == b"dupe-content"  # moved, never deleted (R8)


# --------------------------------------------------------------------------- #
# dry-run (R1/R9) — inert + journal preview
# --------------------------------------------------------------------------- #

def test_dry_run_mutates_nothing_and_writes_preview(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    before = _snapshot(lib)
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, run_dir, mode="dry-run", stamp="S")
    assert result.ok
    assert _snapshot(lib) == before                       # R9: nothing mutated
    assert not (run_dir / "journal.jsonl").exists()       # no real journal in dry-run
    preview = json.loads((run_dir / "journal-preview.json").read_text(encoding="utf-8"))
    assert len(preview) == 4


# --------------------------------------------------------------------------- #
# Gates (R2/R3) — refuse, no moves
# --------------------------------------------------------------------------- #

def test_refuses_on_binding_mismatch_with_no_moves(tmp_path):
    lib, rows = _build_library(tmp_path)
    wrong_verdict = _signed_verdict([_row(original_path="OTHER", section="ZZ")])  # bound to other rows
    before = _snapshot(lib)
    result = apply_manifest(rows, wrong_verdict, build_backup_proof(lib),
                            lib, tmp_path / "run", mode="apply", stamp="S")
    assert result.ok is False and "binding" in result.refused_reason.lower()
    assert _snapshot(lib) == before


def test_refuses_on_backup_proof_failure_with_no_moves(tmp_path):
    lib, rows = _build_library(tmp_path)
    proof = build_backup_proof(lib)
    proof["file_count"] = 999  # tampered -> count drift
    before = _snapshot(lib)
    result = apply_manifest(rows, _signed_verdict(rows), proof,
                            lib, tmp_path / "run", mode="apply", stamp="S")
    assert result.ok is False and "backup" in result.refused_reason.lower()
    assert _snapshot(lib) == before


# --------------------------------------------------------------------------- #
# Resume (R6) — interrupt after 2, re-run completes the remaining 2
# --------------------------------------------------------------------------- #

def test_resume_completes_only_remaining_rows(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    journal = run_dir / "journal.jsonl"
    # Simulate an apply interrupted after the first two rows: move them by hand and
    # record them in the journal, exactly as a crashed real apply would have left things.
    moved = [
        (lib / "_Inbox" / "good.epub", lib / "01 History" / "A - Good.epub"),
        (lib / "_Inbox" / "maybe.epub", lib / "_Needs_Review" / "_Inbox" / "maybe.epub"),
    ]
    for i, (src, dst) in enumerate(moved):
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        append_record(journal, {"seq": i, "src": str(src), "dst": str(dst),
                                "action": rows[i].action, "sha256": rows[i].sha256, "ts": "S"})

    # Resume: journal is non-empty, so the backup gate is skipped and the first two are
    # idempotently skipped; only dupe (trash) and weird (quarantine) move now.
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, run_dir, mode="apply", stamp="S")
    assert result.ok and result.moved_count == 2
    assert (lib / "_Trash_Pending" / "_Inbox" / "dupe.epub").is_file()
    assert (lib / "_Quarantine" / "_Inbox" / "weird.epub").is_file()
    # The two pre-moved files are intact and were not double-moved.
    assert (lib / "01 History" / "A - Good.epub").read_bytes() == b"good-content"


# --------------------------------------------------------------------------- #
# CLI (subprocess) — PYTHONHASHSEED guard + dry-run smoke
# --------------------------------------------------------------------------- #

def _write_inputs(tmp_path, lib, rows):
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps([asdict(r) for r in rows]), encoding="utf-8")
    vpath = tmp_path / "verdict.json"
    vpath.write_text(json.dumps(_signed_verdict(rows)), encoding="utf-8")
    ppath = tmp_path / "proof.json"
    ppath.write_text(json.dumps(build_backup_proof(lib)), encoding="utf-8")
    return mpath, vpath, ppath


def _run_apply_cli(mpath, vpath, ppath, lib, run_dir, mode="dry-run", hashseed="0"):
    actuate = Path(__file__).resolve().parents[1] / "tools" / "book_filer" / "actuate.py"
    cmd = [sys.executable, str(actuate), "--manifest", str(mpath), "--verdict", str(vpath),
           "--backup-proof", str(ppath), "--library-root", str(lib),
           "--run-dir", str(run_dir), "--mode", mode]
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hashseed
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_cli_refuses_without_hashseed(tmp_path):
    lib, rows = _build_library(tmp_path)
    mpath, vpath, ppath = _write_inputs(tmp_path, lib, rows)
    r = _run_apply_cli(mpath, vpath, ppath, lib, tmp_path / "run", mode="dry-run", hashseed="1")
    assert r.returncode == 1 and "PYTHONHASHSEED" in r.stderr


def test_cli_dry_run_smoke_is_inert(tmp_path):
    lib, rows = _build_library(tmp_path)
    mpath, vpath, ppath = _write_inputs(tmp_path, lib, rows)
    before = _snapshot(lib)
    r = _run_apply_cli(mpath, vpath, ppath, lib, tmp_path / "run", mode="dry-run")
    assert r.returncode == 0, r.stderr
    assert _snapshot(lib) == before
    assert (tmp_path / "run" / "journal-preview.json").exists()
