"""Tests for book_filer.inbox — propose-only inbox driver (EB-380 U2).

Test-first: the behavioral contracts encoded here DRIVE the implementation.
Key invariants locked here:
  - Phase-1 tiers only (proposed/ambiguous/no_match/derivative_parked/duplicate/
    quarantine_reparse/review_oracle_missing/superseded/stale)
  - Zero file moves (source-grep + filesystem assertion)
  - sha-keyed upsert (idempotent, supersede, stale lifecycle)
  - Fail-closed on lock contention and missing oracle
  - G7 containment: no proposed_path outside library_root
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from book_filer.classify import Classification
from book_filer.config import LibraryConfig
from book_filer.taxonomy import Taxonomy
import book_filer.reparse as reparse_mod
import book_filer.inbox as inbox_mod
from book_filer.inbox import LOCK_FILENAME, QUEUE_FILENAME, SweepResult, sweep_inbox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path) -> LibraryConfig:
    return LibraryConfig(
        library_root=tmp_path / "Books",
        calibre_library=tmp_path / "Calibre",
        audio_root=tmp_path / "Books" / "Audio_Books",
        documents_root=tmp_path / "Documents",
        materialize_mode="copy",
        trash_retention_days=30,
        operational_folders=("_Inbox", "_Needs_Review", "_Quarantine", "_Trash_Pending"),
        scan_exclude=("Audio_Books",),
        max_path_length=240,
    )


def _run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mk_taxonomy() -> Taxonomy:
    """Minimal taxonomy: 'history' → History/General; 'military' → History/Military."""
    return Taxonomy(
        confidence_threshold=0.3,
        non_library_keywords=("resume", "cv"),
        sections={"History": ("General", "Military")},
        version=42,
        format_keywords=frozenset(),
        boilerplate_keywords=frozenset(),
        _index={
            "history": {("History", "General")},
            "military": {("History", "Military")},
        },
    )


def _write_book(path: Path, content: bytes = b"FAKEPDF" * 400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _read_queue(run_dir: Path) -> list[dict]:
    q = run_dir / QUEUE_FILENAME
    if not q.exists():
        return []
    rows = []
    for line in q.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _shelf_cls(section: str = "History", subcategory: str = "General", confidence: float = 0.9) -> Classification:
    return Classification("shelf", section, subcategory, confidence)


def _review_section_cls(section: str = "History", confidence: float = 0.2) -> Classification:
    return Classification("review", section, None, confidence)


def _review_no_section_cls(confidence: float = 0.1) -> Classification:
    return Classification("review", None, None, confidence)


def _run_sweep(
    cfg: LibraryConfig,
    run_dir: Path,
    *,
    cls: Classification | None = None,
    monkeypatch=None,
    settle_seconds: int = 0,
    oracle: frozenset | None = frozenset(),
) -> SweepResult:
    """Run sweep_inbox; optionally monkeypatch classify_name to return cls."""
    if cls is not None and monkeypatch is not None:
        monkeypatch.setattr("book_filer.scan.classify_name", lambda *a, **kw: cls)
    return sweep_inbox(
        cfg,
        run_dir,
        _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=settle_seconds,
        _shelf_oracle=oracle,
    )


# ---------------------------------------------------------------------------
# Happy paths: tier routing
# ---------------------------------------------------------------------------

def test_proposed_clean_pdf(tmp_path, monkeypatch):
    """Shelf-classified PDF with high confidence → 'proposed'; _Inbox unchanged."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    book = _write_book(cfg.library_root / "_Inbox" / "Manual" / "history-book.pdf")

    result = _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)

    rows = _read_queue(run_dir)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}: {rows}"
    row = rows[0]
    assert row["tier"] == "proposed"
    assert row["sha"] != ""
    assert row["proposed_path"] != ""
    assert row["taxonomy_version"] == 42
    # _Inbox unchanged — nothing moved
    assert book.exists(), "sweep must not move or delete source files"


def test_ambiguous_low_confidence(tmp_path, monkeypatch):
    """review disposition with a section + low confidence → 'ambiguous'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "uncertain-book.pdf")

    _run_sweep(cfg, run_dir, cls=_review_section_cls(confidence=0.4), monkeypatch=monkeypatch)

    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "ambiguous"
    assert rows[0]["proposed_path"] == ""  # no destination for ambiguous


def test_no_match_no_section(tmp_path, monkeypatch):
    """review disposition with no section → 'no_match'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "mystery.pdf")

    _run_sweep(cfg, run_dir, cls=_review_no_section_cls(), monkeypatch=monkeypatch)

    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "no_match"
    assert rows[0]["proposed_path"] == ""


def test_derivative_parked_kfx(tmp_path):
    """A .kfx file → 'derivative_parked' without classification."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Conversions" / "some-book.kfx")

    sweep_inbox(
        cfg,
        run_dir,
        _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )

    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "derivative_parked"
    assert rows[0]["proposed_path"] == ""


def test_source_subfolder_recorded(tmp_path, monkeypatch):
    """source_subfolder is captured from the _Inbox subdirectory name."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "BookFinder" / "book.pdf")

    _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)

    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["source_subfolder"] == "BookFinder"


# ---------------------------------------------------------------------------
# Eligibility filtering
# ---------------------------------------------------------------------------

def test_skips_in_flight_extensions(tmp_path):
    """In-flight extensions (.crdownload, .part, .tmp, .!qb) produce no queue rows."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    inbox = cfg.library_root / "_Inbox" / "Manual"
    for ext in (".crdownload", ".part", ".tmp", ".!qb"):
        _write_book(inbox / f"book{ext}")

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )
    assert _read_queue(run_dir) == []


def test_skips_zero_byte_file(tmp_path):
    """Zero-byte files are skipped — not eligible for classification."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    inbox = cfg.library_root / "_Inbox" / "Manual"
    inbox.mkdir(parents=True)
    (inbox / "empty.pdf").write_bytes(b"")

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )
    assert _read_queue(run_dir) == []


def test_skips_within_settle_window(tmp_path):
    """Files younger than settle_seconds are skipped (still downloading)."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "new-book.pdf")

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=9999,  # all files are "too new"
        _shelf_oracle=frozenset(),
    )
    assert _read_queue(run_dir) == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotent_unchanged_inbox(tmp_path, monkeypatch):
    """Re-run on unchanged _Inbox → identical queue; no duplicate rows."""
    os.environ["PYTHONHASHSEED"] = "0"  # pin for determinism-sensitive test
    try:
        cfg = _cfg(tmp_path)
        run_dir = _run_dir(tmp_path)
        _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")

        _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
        rows_first = _read_queue(run_dir)
        _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
        rows_second = _read_queue(run_dir)

        # Same number of live rows (not counting any stale/superseded)
        live_first = [r for r in rows_first if r["tier"] not in ("stale", "superseded")]
        live_second = [r for r in rows_second if r["tier"] not in ("stale", "superseded")]
        assert len(live_first) == 1
        assert len(live_second) == 1
        assert live_first[0]["sha"] == live_second[0]["sha"]
        assert live_first[0]["tier"] == live_second[0]["tier"]
    finally:
        os.environ.pop("PYTHONHASHSEED", None)


# ---------------------------------------------------------------------------
# Lifecycle: supersede
# ---------------------------------------------------------------------------

def test_supersede_on_sha_change(tmp_path, monkeypatch):
    """Content change → new sha → new row; old row tombstoned 'superseded'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    book = _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf", b"VER1" * 500)

    _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
    rows_v1 = _read_queue(run_dir)
    assert len(rows_v1) == 1
    sha_v1 = rows_v1[0]["sha"]

    # Overwrite with different content (different size avoids short-circuit edge case)
    book.write_bytes(b"VER2VERSION2" * 250)
    _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
    rows_v2 = _read_queue(run_dir)

    by_sha = {r["sha"]: r for r in rows_v2}
    assert by_sha[sha_v1]["tier"] == "superseded", "old sha must be tombstoned"
    new_rows = [r for r in rows_v2 if r["sha"] != sha_v1]
    assert len(new_rows) == 1
    assert new_rows[0]["tier"] == "proposed"


# ---------------------------------------------------------------------------
# Lifecycle: stale
# ---------------------------------------------------------------------------

def test_stale_on_vanished_source(tmp_path, monkeypatch):
    """Deleting a queued file → next sweep tombstones its row 'stale'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    book = _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")

    _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
    assert len(_read_queue(run_dir)) == 1

    book.unlink()
    _run_sweep(cfg, run_dir, cls=_shelf_cls(), monkeypatch=monkeypatch)
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "stale"


# ---------------------------------------------------------------------------
# Error path: reparse in source ancestry
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="reparse points are Windows-only")
def test_reparse_ancestry_routes_to_quarantine(tmp_path, monkeypatch):
    """File under a reparse ancestry → 'quarantine_reparse'; never classified."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    inbox = cfg.library_root / "_Inbox" / "Manual"
    book = _write_book(inbox / "book.pdf")

    monkeypatch.setattr(
        "book_filer.inbox.has_reparse_in_ancestry",
        lambda p: Path(p).is_relative_to(inbox),
    )

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "quarantine_reparse"
    # Source file still there — never moved
    assert book.exists()


# ---------------------------------------------------------------------------
# Error path: lock contention
# ---------------------------------------------------------------------------

def test_lock_held_exits_with_skipped_lock(tmp_path):
    """Lock already held → skipped_lock=True; queue not created by this run."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")

    # Simulate a concurrent sweep by pre-creating the lock file
    (run_dir / LOCK_FILENAME).write_text("held-by-other-sweep", encoding="utf-8")

    result = sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )

    assert result.skipped_lock is True
    # Queue must not exist (this run wrote nothing)
    assert not (run_dir / QUEUE_FILENAME).exists()


# ---------------------------------------------------------------------------
# Dedup: live shelf oracle
# ---------------------------------------------------------------------------

def test_duplicate_flagged_by_oracle(tmp_path, monkeypatch):
    """File whose planned_calibre_key is in the shelf oracle → tier 'duplicate'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    book = _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")

    # Compute the oracle key the driver will derive (no embedded metadata → sha key)
    sha256 = hashlib.sha256(book.read_bytes()).hexdigest()
    oracle_key = f"sha:{sha256[:16]}"

    monkeypatch.setattr("book_filer.scan.classify_name", lambda *a, **kw: _shelf_cls())

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset([oracle_key]),
    )
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "duplicate"


def test_missing_oracle_fails_closed(tmp_path, monkeypatch):
    """_shelf_oracle=None (unavailable) → all files get 'review_oracle_missing'."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")
    monkeypatch.setattr("book_filer.scan.classify_name", lambda *a, **kw: _shelf_cls())

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=None,  # explicitly unavailable → fail-closed
    )
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "review_oracle_missing"


def test_clean_file_not_in_oracle(tmp_path, monkeypatch):
    """File NOT in oracle → proceeds to normal tier (proposed)."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")
    monkeypatch.setattr("book_filer.scan.classify_name", lambda *a, **kw: _shelf_cls())

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(["sha:deadbeef12345678"]),  # unrelated key
    )
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    assert rows[0]["tier"] == "proposed"


# ---------------------------------------------------------------------------
# G7: containment guard on proposed_path
# ---------------------------------------------------------------------------

def test_g7_containment_no_outside_path_emitted(tmp_path, monkeypatch):
    """Driver refuses to emit a proposed_path outside library_root (secondary containment)."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_book(cfg.library_root / "_Inbox" / "Manual" / "history.pdf")
    monkeypatch.setattr("book_filer.scan.classify_name", lambda *a, **kw: _shelf_cls())

    # Bypass _destination_path's own G7 guard — return a path outside library_root.
    # Patch inbox.py's imported name (not scan.py) because from-import caches the reference.
    outside = str(tmp_path / "Escaped" / "somewhere.pdf")
    monkeypatch.setattr("book_filer.inbox._destination_path", lambda *a, **kw: outside)

    sweep_inbox(
        cfg, run_dir, _mk_taxonomy(),
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozenset(),
    )
    rows = _read_queue(run_dir)
    assert len(rows) == 1
    proposed = rows[0].get("proposed_path", "")
    # Either empty or safely inside library_root
    if proposed:
        lib_root = str(cfg.library_root).lower()
        assert proposed.lower().startswith(lib_root), (
            f"proposed_path escapes library_root: {proposed!r}"
        )


# ---------------------------------------------------------------------------
# library_root_arg mismatch (G7 precondition)
# ---------------------------------------------------------------------------

def test_library_root_arg_mismatch_raises(tmp_path):
    """Mismatched library_root_arg vs config.library_root → ValueError (fail-closed)."""
    cfg = _cfg(tmp_path)
    run_dir = _run_dir(tmp_path)

    with pytest.raises(ValueError, match=r"library.root"):
        sweep_inbox(
            cfg, run_dir, _mk_taxonomy(),
            library_root_arg=tmp_path / "WrongRoot",
            settle_seconds=0,
            _shelf_oracle=frozenset(),
        )


# ---------------------------------------------------------------------------
# Source-grep: moves-nothing invariant
# ---------------------------------------------------------------------------

def test_inbox_source_grep_no_move_primitives():
    """inbox.py must contain no file-move/delete primitives in the sweep path.

    Structural lock on the propose-only guarantee (mirrors the move.py test pattern).
    """
    src_path = Path(__file__).resolve().parents[1] / "tools" / "book_filer" / "inbox.py"
    src = src_path.read_text(encoding="utf-8")
    for forbidden in (
        "os.replace(",
        "os.rename(",
        "os.remove(",
        "shutil.move(",
        "shutil.copy(",
        ".rmdir(",
        "rmtree(",
        "execute_move(",
    ):
        assert forbidden not in src, (
            f"inbox.py must be move-free; found {forbidden!r} — "
            "auto-move is T3 (new ADR required)"
        )
