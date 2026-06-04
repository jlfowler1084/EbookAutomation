import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.actuate import (
    DEFAULT_OPERATIONAL,
    apply_manifest,
    finalize_run,
    route_target,
    undo_apply,
)
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
    journal_records = [json.loads(ln) for ln in
                       (run_dir / "journal.jsonl").read_text(encoding="utf-8").strip().splitlines()]
    assert sum(1 for r in journal_records if r.get("state") == "intent") == 4   # WAL: intent...
    assert sum(1 for r in journal_records if r.get("state") == "commit") == 4   # ...then commit per move
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


def test_dry_run_refuses_run_dir_inside_library_and_stays_inert(tmp_path):
    """R9: a run-dir inside the library would write artifacts into F:\\Books -- refuse before
    creating anything, so dry-run truly mutates nothing."""
    lib, rows = _build_library(tmp_path)
    before = _snapshot(lib)
    inside = lib / "_Migration_Manifests" / "run"   # a run-dir INSIDE the library
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, inside, mode="dry-run", stamp="S")
    assert result.ok is False and "run-dir" in result.refused_reason.lower()
    assert _snapshot(lib) == before        # nothing written into the library
    assert not inside.exists()             # run_dir not even created


def test_apply_refuses_run_dir_inside_library(tmp_path):
    lib, rows = _build_library(tmp_path)
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, lib / "run", mode="apply", stamp="S")
    assert result.ok is False and "run-dir" in result.refused_reason.lower()


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
        rec = {"seq": i, "src": str(src), "dst": str(dst),
               "action": rows[i].action, "sha256": rows[i].sha256, "ts": "S"}
        append_record(journal, {**rec, "state": "intent"})
        os.replace(src, dst)
        append_record(journal, {**rec, "state": "commit"})

    # Resume: journal is non-empty, so the backup gate is skipped and the first two are
    # idempotently skipped; only dupe (trash) and weird (quarantine) move now.
    result = apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                            lib, run_dir, mode="apply", stamp="S")
    assert result.ok and result.moved_count == 2
    assert (lib / "_Trash_Pending" / "_Inbox" / "dupe.epub").is_file()
    assert (lib / "_Quarantine" / "_Inbox" / "weird.epub").is_file()
    # The two pre-moved files are intact and were not double-moved.
    assert (lib / "01 History" / "A - Good.epub").read_bytes() == b"good-content"


def test_crash_after_move_before_commit_resume_then_undo_restores_all(tmp_path, monkeypatch):
    """P1 regression: a move can be durable BEFORE its journal record is. If the process
    crashes in that window, resume must recognize the applied move and undo must still
    restore it -- the journal can never be behind the filesystem."""
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    before_snap = _snapshot(lib)
    before_content = _content_multiset(lib)

    import book_filer.actuate as actuate_mod
    real_append = actuate_mod.append_record
    target_src = str(Path(rows[1].original_path))
    state = {"crashed": False}

    def flaky_append(path, record):
        # Fail the COMMIT of row 1 -- its os.replace has already happened, so row 1 is
        # applied-but-uncommitted. (On a single-record model this is just row 1's record.)
        if record.get("src") == target_src and record.get("state", "commit") == "commit":
            state["crashed"] = True
            raise OSError("simulated crash committing row 1's move")
        return real_append(path, record)

    monkeypatch.setattr(actuate_mod, "append_record", flaky_append)
    with pytest.raises(OSError):
        apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib), lib, run_dir,
                       mode="apply", stamp="S")
    assert state["crashed"]
    monkeypatch.undo()  # crash is over; resume with a healthy journal writer

    assert apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib), lib, run_dir,
                          mode="apply", stamp="S").ok

    undo = undo_apply(run_dir, lib, stamp="S")
    assert undo.ok, [f"{o.seq}:{o.reason}" for o in undo.outcomes]
    assert _snapshot(lib) == before_snap          # EVERY file restored, incl. the uncommitted one
    assert _content_multiset(lib) == before_content


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


# --------------------------------------------------------------------------- #
# Undo + finalize (R5/R8)
# --------------------------------------------------------------------------- #

def test_undo_restores_exact_original_layout(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    before = _snapshot(lib)
    assert apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                          lib, run_dir, mode="apply", stamp="S").moved_count == 4
    assert _snapshot(lib) != before                 # layout changed by the apply
    undo = undo_apply(run_dir, lib, stamp="S")
    assert undo.ok and undo.restored_count == 4
    assert _snapshot(lib) == before                 # byte-for-byte original layout restored
    assert (lib / "_Inbox" / "good.epub").read_bytes() == b"good-content"


def test_undo_reports_incomplete_when_a_dst_was_removed(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                   lib, run_dir, mode="apply", stamp="S")
    (lib / "_Quarantine" / "_Inbox" / "weird.epub").unlink()  # independently removed before undo
    undo = undo_apply(run_dir, lib, stamp="S")
    assert undo.ok is False and undo.restored_count == 3      # the other three restored; reported
    assert (run_dir / "undo-report.md").exists()


def test_finalize_purges_journal_without_deleting_files(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                   lib, run_dir, mode="apply", stamp="S")
    trashed = lib / "_Trash_Pending" / "_Inbox" / "dupe.epub"
    assert trashed.is_file()
    fin = finalize_run(run_dir, stamp="S")
    assert fin.ok and fin.finalized_count == 4
    assert not (run_dir / "journal.jsonl").exists()        # active journal purged (undo window closed)
    assert (run_dir / "journal.finalized.jsonl").exists()  # archived for audit
    assert trashed.is_file()                               # R8: no library file deleted
    assert undo_apply(run_dir, lib, stamp="S").restored_count == 0  # nothing to undo after finalize


def test_apply_undo_reapply_undo_roundtrips(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    before = _snapshot(lib)
    for _ in range(2):
        apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib),
                       lib, run_dir, mode="apply", stamp="S")
        assert _snapshot(lib) != before
        assert undo_apply(run_dir, lib, stamp="S").ok
        assert _snapshot(lib) == before
        (run_dir / "journal.jsonl").unlink(missing_ok=True)  # fresh run for the next cycle


# --------------------------------------------------------------------------- #
# Unit 7 — staged-rollout integration + safety-contract regressions
# --------------------------------------------------------------------------- #

def _content_multiset(root: Path) -> list:
    return sorted(hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in root.rglob("*") if p.is_file())


def test_full_staged_rollout_dry_run_apply_undo_reapply_finalize(tmp_path):
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    verdict = _signed_verdict(rows)
    before = _snapshot(lib)

    # 1. dry-run is inert.
    dry = apply_manifest(rows, verdict, build_backup_proof(lib), lib, run_dir, mode="dry-run", stamp="S")
    assert dry.ok and _snapshot(lib) == before and not (run_dir / "journal.jsonl").exists()

    # 2. apply realizes the multi-folder target layout.
    applied = apply_manifest(rows, verdict, build_backup_proof(lib), lib, run_dir, mode="apply", stamp="S")
    assert applied.ok and applied.moved_count == 4 and _snapshot(lib) != before

    # 3. undo restores exactly.
    assert undo_apply(run_dir, lib, stamp="S").ok and _snapshot(lib) == before

    # 4. re-apply (fresh) then finalize closes the undo window.
    (run_dir / "journal.jsonl").unlink(missing_ok=True)
    reapplied = apply_manifest(rows, verdict, build_backup_proof(lib), lib, run_dir, mode="apply", stamp="S")
    assert reapplied.ok and reapplied.moved_count == 4
    fin = finalize_run(run_dir, stamp="S")
    assert fin.ok and not (run_dir / "journal.jsonl").exists()


def test_no_hard_delete_content_multiset_conserved(tmp_path):
    """R8: in-place moves relocate bytes; the set of file contents is invariant across
    apply and undo -- nothing is ever deleted or corrupted."""
    lib, rows = _build_library(tmp_path)
    run_dir = tmp_path / "run"
    before = _content_multiset(lib)
    apply_manifest(rows, _signed_verdict(rows), build_backup_proof(lib), lib, run_dir, mode="apply", stamp="S")
    assert _content_multiset(lib) == before    # same bytes, relocated -- nothing deleted
    undo_apply(run_dir, lib, stamp="S")
    assert _content_multiset(lib) == before    # undo conserves content too


def test_determinism_drift_after_signing_is_refused_with_no_moves(tmp_path):
    """EB-353: the apply re-derives the manifest digest; a row edited after signing no
    longer matches the signed verdict -> refuse, zero moves."""
    lib, rows = _build_library(tmp_path)
    verdict = _signed_verdict(rows)                       # bound to rows as signed
    tampered = list(rows)
    tampered[0] = _row(original_path=rows[0].original_path,
                       destination_path=rows[0].destination_path,
                       action="copy", section="99 Tampered After Signing",
                       sha256=rows[0].sha256)
    before = _snapshot(lib)
    result = apply_manifest(tampered, verdict, build_backup_proof(lib), lib, tmp_path / "run",
                            mode="apply", stamp="S")
    assert result.ok is False and "binding" in result.refused_reason.lower()
    assert _snapshot(lib) == before


def test_actuator_source_has_no_recursive_or_library_delete():
    """R8 source contract: move.py (the only module that touches library-file paths) is
    delete-free; actuate.py uses no recursive delete and unlinks only its own lock artifact."""
    tools = Path(__file__).resolve().parents[1] / "tools" / "book_filer"
    move_src = (tools / "move.py").read_text(encoding="utf-8")
    actuate_src = (tools / "actuate.py").read_text(encoding="utf-8")
    for forbidden in ("os.remove", "os.unlink", "shutil", ".unlink(", ".rmdir(", "rmtree"):
        assert forbidden not in move_src, f"move.py must be delete-free; found {forbidden!r}"
    for forbidden in ("shutil.rmtree", "os.removedirs", "rmtree"):
        assert forbidden not in actuate_src, f"actuate.py must not recursively delete; found {forbidden!r}"
    unlink_lines = [ln for ln in actuate_src.splitlines() if ".unlink(" in ln]
    assert unlink_lines, "expected the lock-file unlink to be present"
    assert all("lock_path" in ln for ln in unlink_lines), \
        f"actuate.py may only unlink its lock file; found: {unlink_lines}"
