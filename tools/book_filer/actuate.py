"""Apply driver + CLI for the book_filer actuator (EB-373 Unit 5).

Executes a signed-GREEN manifest as in-place moves behind the full gate stack:
single-run lock -> manifest<->verdict binding (R2, which re-derives the determinism
projection per EB-353) -> external backup proof (R3, fresh apply only) -> idempotent
resume filter (R6) -> per-row fail-closed move (R4/R7) with a durable journal (R5).

dry-run (default, R1/R9) plans every row and writes a journal-preview but mutates
nothing. trash routes to _Trash_Pending; nothing is ever deleted (R8). The live
library root is an EXPLICIT argument -- the actuator never defaults to the real
F:\\Books corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .backup import verify_backup_proof
    from .calibration import verify_binding
    from .journal import already_applied, append_record, applied_sources, read_records
    from .manifest import ManifestRow
    from .move import execute_move, plan_move
else:  # run directly as a script: add tools/ to sys.path so `book_filer` resolves (mirrors scan.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from book_filer.backup import verify_backup_proof
    from book_filer.calibration import verify_binding
    from book_filer.journal import already_applied, append_record, applied_sources, read_records
    from book_filer.manifest import ManifestRow
    from book_filer.move import execute_move, plan_move

EXIT_OK = 0
EXIT_BAD_ENV = 1     # PYTHONHASHSEED != 0
EXIT_REFUSED = 2     # a gate refused (binding / backup); no moves
EXIT_BAD_ARGS = 3    # inputs could not be loaded
EXIT_ERROR = 4       # unexpected

# Operational-folder routing by action (names mirror config/settings.json `library`).
DEFAULT_OPERATIONAL = {
    "review": "_Needs_Review",
    "trash": "_Trash_Pending",        # dedup-trash routes here (brainstorm D3), never _Duplicates_Pending
    "quarantine": "_Quarantine",
}
_SHELVE_ACTIONS = ("copy", "hardlink")


@dataclass(frozen=True)
class RowResult:
    seq: int
    src: str
    dst: str
    action: str
    moved: bool
    reason: str


@dataclass
class ApplyResult:
    ok: bool                       # the run completed; a gate refusal sets ok=False
    refused_reason: str | None
    mode: str
    results: list[RowResult]
    journal_path: Path | None
    report_path: Path | None

    @property
    def moved_count(self) -> int:
        return sum(1 for r in self.results if r.moved)


def _original_relpath(original_path: str, library_root: Path) -> Path:
    """The original's path relative to the library root, preserved under operational
    folders. Falls back to the leaf name if the original is outside the library root."""
    p = Path(original_path)
    try:
        return p.relative_to(library_root)
    except ValueError:
        return Path(p.name)


def route_target(row: ManifestRow, library_root: Path, operational: dict) -> Path | None:
    """The on-disk target for a row, or None when the actuator must skip it (an
    unhandled action, or a shelve row with no computed destination)."""
    if row.action in _SHELVE_ACTIONS:
        return Path(row.destination_path) if row.destination_path else None
    folder = operational.get(row.action)
    if folder is None:
        return None  # merge-format / non_library / unknown -> skip + log (fail closed)
    return Path(library_root) / folder / _original_relpath(row.original_path, library_root)


def _write_report(run_dir: Path, mode: str, results: list[RowResult],
                  refused_reason: str | None = None) -> Path:
    lines = [f"# book_filer apply report ({mode})", ""]
    if refused_reason:
        lines += [f"**REFUSED:** {refused_reason}", "", "No rows were processed."]
    else:
        moved = sum(1 for r in results if r.moved)
        verb = "planned" if mode == "dry-run" else "moved"
        lines += [f"{len(results)} row(s): {moved} {verb}, {len(results) - moved} skipped.", "",
                  "| seq | action | moved | src -> dst | reason |",
                  "|---|---|---|---|---|"]
        for r in results:
            lines.append(f"| {r.seq} | {r.action} | {r.moved} | `{r.src}` -> `{r.dst}` | {r.reason} |")
    path = run_dir / "apply-report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_journal_preview(run_dir: Path, results: list[RowResult]) -> Path:
    """dry-run only: what the journal WOULD record, mutating nothing (R9)."""
    preview = [{"seq": r.seq, "src": r.src, "dst": r.dst, "action": r.action, "would_move": r.moved}
               for r in results]
    path = run_dir / "journal-preview.json"
    path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    return path


def apply_manifest(rows, verdict, backup_proof, library_root, run_dir, *,
                   mode: str = "dry-run", operational: dict | None = None,
                   stamp: str = "unstamped", lock: bool = True) -> ApplyResult:
    """Apply (or dry-run) a manifest behind the full gate stack. See module docstring."""
    library_root = Path(library_root)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    operational = operational or DEFAULT_OPERATIONAL
    journal_path = run_dir / "journal.jsonl"
    lock_path = run_dir / "apply.lock"

    if lock:
        try:  # atomic O_EXCL acquire -- refuse rather than clobber a concurrent run
            with open(lock_path, "x", encoding="utf-8") as fh:
                fh.write(f"{mode} {stamp}\n")
        except FileExistsError:
            return ApplyResult(False, f"another run holds the lock: {lock_path}",
                               mode, [], None, None)
    try:
        return _run(rows, verdict, backup_proof, library_root, run_dir,
                    journal_path, mode, operational, stamp)
    finally:
        if lock:
            try:
                lock_path.unlink()
            except OSError:
                pass


def _run(rows, verdict, backup_proof, library_root, run_dir, journal_path,
         mode, operational, stamp) -> ApplyResult:
    def refuse(reason: str) -> ApplyResult:
        report = _write_report(run_dir, mode, [], refused_reason=reason)
        return ApplyResult(False, reason, mode, [], None, report)

    journal_records = read_records(journal_path)
    is_resume = mode == "apply" and bool(journal_records)

    binding = verify_binding(rows, verdict)
    if not binding.ok:
        return refuse(f"manifest binding refused (R2): {binding.reason}")

    # Backup gate (R3): a FRESH apply only. dry-run mutates nothing; a resume already
    # verified the backup when the run began, and the corpus is now mid-migration so it
    # can no longer match the pristine-state proof.
    if mode == "apply" and not is_resume:
        bproof = verify_backup_proof(library_root, backup_proof)
        if not bproof.ok:
            return refuse(f"backup proof refused (R3): {bproof.reason}")

    done = applied_sources(journal_records) if mode == "apply" else set()
    results: list[RowResult] = []
    for seq, row in enumerate(rows):
        src = Path(row.original_path)
        target = route_target(row, library_root, operational)
        if target is None:
            results.append(RowResult(seq, str(src), "", row.action, False,
                                     "unhandled action or missing destination -- skipped"))
            continue
        if mode == "apply" and (str(src) in done or already_applied(src, target, row.sha256)):
            results.append(RowResult(seq, str(src), str(target), row.action, False,
                                     "already applied (resume skip)"))
            continue
        decision = plan_move(src, target, allow_unique=True)
        if mode == "dry-run":
            results.append(RowResult(seq, str(src), str(decision.dst), row.action,
                                     decision.action == "move",
                                     f"dry-run {decision.action}: {decision.reason}"))
            continue
        outcome = execute_move(decision)
        if outcome.moved:
            append_record(journal_path, {
                "seq": seq, "src": str(outcome.src), "dst": str(outcome.dst),
                "action": row.action, "sha256": row.sha256, "ts": stamp,
            })
        results.append(RowResult(seq, str(outcome.src), str(outcome.dst), row.action,
                                 outcome.moved, outcome.reason))

    report = _write_report(run_dir, mode, results)
    if mode == "dry-run":
        _write_journal_preview(run_dir, results)
    return ApplyResult(True, None, mode, results,
                       journal_path if mode == "apply" else None, report)


# --------------------------------------------------------------------------- #
# Undo (R5) + finalize (R8)
# --------------------------------------------------------------------------- #

_HASH_CHUNK = 1 << 20


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb", buffering=_HASH_CHUNK) as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class UndoRecordOutcome:
    seq: object
    src: str          # the original location being restored TO
    dst: str          # the current location being moved FROM
    restored: bool
    reason: str


@dataclass
class UndoResult:
    ok: bool                         # every journaled move restored AND sha-verified
    restored_count: int
    outcomes: list[UndoRecordOutcome]
    report_path: Path | None


@dataclass
class FinalizeResult:
    ok: bool
    finalized_count: int
    audit_path: Path | None
    reason: str


def _write_undo_report(run_dir: Path, outcomes: list[UndoRecordOutcome], ok: bool) -> Path:
    restored = sum(1 for o in outcomes if o.restored)
    lines = ["# book_filer undo report", "",
             f"{'COMPLETE' if ok else 'INCOMPLETE'}: {restored}/{len(outcomes)} records restored.", "",
             "| seq | restored | dst -> src | reason |", "|---|---|---|---|"]
    for o in outcomes:
        lines.append(f"| {o.seq} | {o.restored} | `{o.dst}` -> `{o.src}` | {o.reason} |")
    path = run_dir / "undo-report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def undo_apply(run_dir, library_root, *, lock: bool = True, stamp: str = "unstamped") -> UndoResult:
    """Reverse-replay the journal (last move first), restoring each file to its EXACT
    original path through the same fail-closed move primitive, and verify the restore by
    re-hashing against the journal's recorded sha256. A record whose current location was
    independently moved/removed is skipped + reported (fail-closed, no guessing); the run
    is then reported INCOMPLETE. Never deletes anything. `library_root` is accepted for
    signature symmetry with apply; reparse safety comes from the move primitive itself.
    """
    run_dir = Path(run_dir)
    journal_path = run_dir / "journal.jsonl"
    lock_path = run_dir / "apply.lock"
    records = read_records(journal_path)

    if lock:
        try:
            with open(lock_path, "x", encoding="utf-8") as fh:
                fh.write(f"undo {stamp}\n")
        except FileExistsError:
            return UndoResult(False, 0, [], None)
    try:
        outcomes: list[UndoRecordOutcome] = []
        for rec in reversed(records):  # reverse-replay: last move undone first
            seq = rec.get("seq")
            cur = Path(rec["dst"])     # where the file is now
            orig = Path(rec["src"])    # where it must return
            sha = rec.get("sha256", "")
            if already_applied(cur, orig, sha):  # idempotent: already restored
                outcomes.append(UndoRecordOutcome(seq, str(orig), str(cur), True, "already restored"))
                continue
            outcome = execute_move(plan_move(cur, orig, allow_unique=False))
            if not outcome.moved:
                outcomes.append(UndoRecordOutcome(seq, str(orig), str(cur), False, outcome.reason))
            elif sha and _sha256_file(orig) != sha:
                outcomes.append(UndoRecordOutcome(seq, str(orig), str(cur), False, "restored but sha mismatch"))
            else:
                outcomes.append(UndoRecordOutcome(seq, str(orig), str(cur), True, "restored"))
        ok = bool(outcomes) and all(o.restored for o in outcomes) or not records
        report = _write_undo_report(run_dir, outcomes, ok) if outcomes else None
        return UndoResult(ok, sum(1 for o in outcomes if o.restored), outcomes, report)
    finally:
        if lock:
            try:
                lock_path.unlink()
            except OSError:
                pass


def finalize_run(run_dir, *, stamp: str = "unstamped") -> FinalizeResult:
    """End the undo window: archive the active journal (so undo finds nothing) and write a
    closing audit record. Deletes NO library files -- _Trash_Pending retention is separate (R8)."""
    run_dir = Path(run_dir)
    journal_path = run_dir / "journal.jsonl"
    if not journal_path.exists():
        return FinalizeResult(False, 0, None, "no active journal to finalize")
    records = read_records(journal_path)
    archived = run_dir / "journal.finalized.jsonl"
    os.replace(journal_path, archived)  # purge the active journal; keep an audit copy
    audit = {"finalized": len(records), "stamp": stamp, "archived_journal": archived.name}
    audit_path = run_dir / "finalize-audit.json"
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return FinalizeResult(True, len(records), audit_path, "undo window closed; journal archived")


def _load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("PYTHONHASHSEED") != "0":
        print("ERROR: PYTHONHASHSEED must be '0' for a deterministic apply (mirror of scan.py).",
              file=sys.stderr)
        return EXIT_BAD_ENV

    parser = argparse.ArgumentParser(
        description="EB-373 book_filer actuator -- apply/undo/finalize a signed-GREEN manifest "
                    "as in-place moves.")
    parser.add_argument("--manifest", type=Path, help="plan-<stamp>.json (apply/dry-run)")
    parser.add_argument("--verdict", type=Path, help="signed calibration verdict JSON (apply/dry-run)")
    parser.add_argument("--backup-proof", type=Path, help="external-mirror backup-proof JSON (apply)")
    parser.add_argument("--library-root", required=True, type=Path,
                        help="Live corpus root (e.g. F:\\Books). Explicit by design -- the actuator "
                             "never defaults to the real library.")
    parser.add_argument("--run-dir", required=True, type=Path, help="Run artifacts (journal, report).")
    parser.add_argument("--mode", choices=["dry-run", "apply", "undo", "finalize"], default="dry-run")
    parser.add_argument("--stamp", default="unstamped")
    parser.add_argument("--no-lock", action="store_true", help="Disable the single-run lock (tests).")
    args = parser.parse_args(argv)

    if args.mode == "finalize":
        fin = finalize_run(args.run_dir, stamp=args.stamp)
        if not fin.ok:
            print(f"REFUSED: {fin.reason}", file=sys.stderr)
            return EXIT_REFUSED
        print(f"finalize complete: {fin.finalized_count} moves; {fin.reason}.", file=sys.stderr)
        return EXIT_OK

    if args.mode == "undo":
        undo = undo_apply(args.run_dir, args.library_root, stamp=args.stamp, lock=not args.no_lock)
        verb = "COMPLETE" if undo.ok else "INCOMPLETE"
        print(f"undo {verb}: {undo.restored_count} restored. Report: {undo.report_path}", file=sys.stderr)
        return EXIT_OK if undo.ok else EXIT_REFUSED

    # apply / dry-run
    missing = [name for name, val in (("--manifest", args.manifest), ("--verdict", args.verdict),
                                      ("--backup-proof", args.backup_proof)) if val is None]
    if missing:
        print(f"ERROR: {args.mode} requires {', '.join(missing)}", file=sys.stderr)
        return EXIT_BAD_ARGS
    try:
        rows = [ManifestRow(**d) for d in _load_json(args.manifest)]
        verdict = _load_json(args.verdict)
        backup_proof = _load_json(args.backup_proof)
    except (OSError, ValueError, TypeError) as e:
        print(f"ERROR: cannot load inputs: {e}", file=sys.stderr)
        return EXIT_BAD_ARGS

    result = apply_manifest(rows, verdict, backup_proof, args.library_root, args.run_dir,
                            mode=args.mode, stamp=args.stamp, lock=not args.no_lock)
    if not result.ok:
        print(f"REFUSED: {result.refused_reason}", file=sys.stderr)
        return EXIT_REFUSED
    verb = "planned" if args.mode == "dry-run" else "moved"
    print(f"{args.mode} complete: {result.moved_count} {verb}, "
          f"{len(result.results) - result.moved_count} skipped. Report: {result.report_path}",
          file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
