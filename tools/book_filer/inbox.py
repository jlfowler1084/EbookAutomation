"""Inbox-scoped propose-only driver for the steady-state auto-filer (EB-380 U2).

Walks _Inbox, classifies each eligible book file, deduplicates against the live
shelf oracle, and writes a tiered proposal queue (inbox-proposals.jsonl) under
the run-dir.  MOVES NOTHING — Phase-1 propose-only; auto-move is T3 (new ADR).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .config import LibraryConfig
from .reparse import has_reparse_in_ancestry
from .scan import BOOK_EXTS, _build_file_facts, _destination_path, _hash_file
from .taxonomy import Taxonomy

log = logging.getLogger(__name__)

# ── Public constants ──────────────────────────────────────────────────────────

QUEUE_FILENAME = "inbox-proposals.jsonl"
LOCK_FILENAME = "inbox-sweep.lock"

# By-products of the conversion pipeline — not eligible for shelving.
DERIVATIVE_EXTS: frozenset[str] = frozenset({
    ".kfx", ".mp3", ".m4a", ".m4b", ".aax", ".wav",
})

# In-flight download markers — skip until settled.
IN_FLIGHT_EXTS: frozenset[str] = frozenset({
    ".crdownload", ".part", ".tmp", ".!qb",
})

# Confidence thresholds for tier routing.  Calibrated in U6; injectable for testing.
_DEFAULT_THRESHOLDS: dict[str, float] = {"low": 0.3, "high": 0.6}

# Tiers that are safe to short-circuit when (path, size, mtime) unchanged.
_STABLE_TIERS: frozenset[str] = frozenset({
    "proposed", "ambiguous", "no_match", "duplicate",
    "review_oracle_missing", "derivative_parked",
})

# Sentinel for _shelf_oracle: tells sweep_inbox to build the oracle live.
_LIVE = object()


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class SweepResult:
    skipped_lock: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    queue_written: bool = False
    summary: str = ""


# ── G7 precondition ───────────────────────────────────────────────────────────

def _assert_root_match(config: LibraryConfig, library_root_arg: Path) -> None:
    """Fail-closed: config.library_root must equal the --library-root CLI arg.

    _destination_path's G7 guard reads config.library_root (scan.py:491), not
    the CLI arg, so a drift silently scopes containment to the wrong root.
    """
    canon = os.path.normcase(os.path.abspath(str(config.library_root)))
    arg = os.path.normcase(os.path.abspath(str(library_root_arg)))
    if canon != arg:
        raise ValueError(
            f"library_root mismatch — config.library_root is {config.library_root!r} "
            f"but --library-root arg resolved to {Path(library_root_arg)!r}. "
            "Pass the canonical path from config/settings.json."
        )


# ── Eligibility ───────────────────────────────────────────────────────────────

def _iter_inbox_paths(inbox: Path, settle_seconds: int, now: float) -> Iterator[Path]:
    """Walk _Inbox recursively; yield eligible files.

    Skips: in-flight extensions, zero-byte files, files younger than
    settle_seconds.  Never follows reparse points (followlinks=False).
    """
    if not inbox.is_dir():
        return
    for dirpath, _dirs, filenames in os.walk(str(inbox), followlinks=False):
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in IN_FLIGHT_EXTS:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size == 0:
                continue
            if settle_seconds > 0 and (now - st.st_mtime) < settle_seconds:
                continue
            yield p


# ── Queue I/O ─────────────────────────────────────────────────────────────────

def _load_queue(queue_path: Path) -> dict[str, dict]:
    """Return existing rows keyed by sha.  Returns {} when queue does not exist."""
    if not queue_path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            rows[row["sha"]] = row
        except Exception as exc:
            log.warning("Ignoring malformed queue line: %s", exc)
    return rows


def _save_queue(queue_path: Path, rows_by_sha: dict[str, dict]) -> None:
    """Write rows as sha-sorted JSONL (deterministic at PYTHONHASHSEED=0)."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(rows_by_sha[k], ensure_ascii=False, sort_keys=True)
        for k in sorted(rows_by_sha)
    ]
    queue_path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )


# ── G7 secondary containment ──────────────────────────────────────────────────

def _is_inside_library(proposed_path: str, config: LibraryConfig) -> bool:
    """Return True only when proposed_path resolves under config.library_root."""
    if not proposed_path:
        return False
    lib = os.path.normcase(os.path.abspath(str(config.library_root)))
    dest = os.path.normcase(os.path.abspath(proposed_path))
    return dest.startswith(lib)


# ── Row builder ───────────────────────────────────────────────────────────────

def _source_subfolder(path: Path, config: LibraryConfig) -> str:
    """Return the immediate _Inbox child dir name (e.g. 'BookFinder'), or ''."""
    inbox = config.library_root / "_Inbox"
    try:
        rel = path.relative_to(inbox)
        return rel.parts[0] if len(rel.parts) > 1 else ""
    except ValueError:
        return ""


def _make_row(
    *,
    sha: str,
    path: Path,
    size: int,
    mtime: float,
    tier: str,
    proposed_path: str,
    confidence: float,
    reason: str | None,
    source_subfolder: str,
    dedup_verdict: str,
    taxonomy_version: int,
    swept_at: str,
) -> dict:
    return {
        "sha": sha,
        "path": str(path),
        "size": size,
        "mtime": mtime,
        "tier": tier,
        "proposed_path": proposed_path,
        "confidence": confidence,
        "reason": reason,
        "source_subfolder": source_subfolder,
        "dedup_verdict": dedup_verdict,
        "taxonomy_version": taxonomy_version,
        "swept_at": swept_at,
    }


def _compute_row(
    path: Path,
    config: LibraryConfig,
    taxonomy: Taxonomy,
    oracle: frozenset[str] | None,
    thresholds: dict[str, float],
    swept_at: str,
) -> dict:
    """Build one proposal row for an eligible inbox file.

    Tier routing (monotonic — default to the lower tier on doubt):
      reparse ancestry → quarantine_reparse
      derivative ext   → derivative_parked
      oracle is None   → review_oracle_missing  (fail-closed)
      work_key in oracle → duplicate
      shelf + dest OK  → proposed
      review + section + conf≥LOW → ambiguous
      otherwise        → no_match
    """
    subfolder = _source_subfolder(path, config)

    # Reparse check — before hashing (SCRUM-301 junction-traversal defense)
    if has_reparse_in_ancestry(path):
        return _make_row(
            sha=f"reparse:{path}",
            path=path, size=0, mtime=0.0,
            tier="quarantine_reparse",
            proposed_path="",
            confidence=0.0,
            reason="reparse point in source ancestry",
            source_subfolder=subfolder,
            dedup_verdict="skipped",
            taxonomy_version=taxonomy.version,
            swept_at=swept_at,
        )

    # Derivative detection — before hashing
    if path.suffix.lower() in DERIVATIVE_EXTS:
        sha, size = _hash_file(path)
        sha = sha or f"deriv:{path}"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return _make_row(
            sha=sha, path=path, size=size, mtime=mtime,
            tier="derivative_parked",
            proposed_path="",
            confidence=0.0,
            reason=f"derivative extension: {path.suffix.lower()}",
            source_subfolder=subfolder,
            dedup_verdict="skipped",
            taxonomy_version=taxonomy.version,
            swept_at=swept_at,
        )

    # Full facts: hash + metadata + classify
    facts = _build_file_facts(path, taxonomy)
    sha = facts.sha256 or f"err:{path}"
    try:
        st = path.stat()
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        size, mtime = facts.size, 0.0

    # Oracle dedup — fail-closed when oracle is None
    if oracle is None:
        return _make_row(
            sha=sha, path=path, size=size, mtime=mtime,
            tier="review_oracle_missing",
            proposed_path="",
            confidence=facts.cls.confidence if facts.cls else 0.0,
            reason="shelf oracle unavailable — cannot dedup",
            source_subfolder=subfolder,
            dedup_verdict="oracle_missing",
            taxonomy_version=taxonomy.version,
            swept_at=swept_at,
        )

    dedup_verdict = (
        "duplicate" if facts.work_key and facts.work_key in oracle else "clean"
    )
    if dedup_verdict == "duplicate":
        return _make_row(
            sha=sha, path=path, size=size, mtime=mtime,
            tier="duplicate",
            proposed_path="",
            confidence=facts.cls.confidence if facts.cls else 0.0,
            reason=f"already shelved (key={facts.work_key!r})",
            source_subfolder=subfolder,
            dedup_verdict=dedup_verdict,
            taxonomy_version=taxonomy.version,
            swept_at=swept_at,
        )

    # Tier from classification
    cls = facts.cls
    if not cls or facts.error:
        tier, proposed_path = "no_match", ""
        confidence, reason = 0.0, (facts.error or "classification error")
    elif cls.disposition == "shelf":
        dest = _destination_path(facts, config)
        if dest and _is_inside_library(dest, config):
            tier, proposed_path = "proposed", dest
        else:
            tier, proposed_path = "no_match", ""
        confidence, reason = cls.confidence, cls.reason
    elif cls.disposition == "review":
        low = thresholds.get("low", _DEFAULT_THRESHOLDS["low"])
        tier = "ambiguous" if (cls.section and cls.confidence >= low) else "no_match"
        proposed_path = ""
        confidence, reason = cls.confidence, cls.reason
    else:  # non_library
        tier, proposed_path = "no_match", ""
        confidence, reason = cls.confidence, cls.reason

    return _make_row(
        sha=sha, path=path, size=size, mtime=mtime,
        tier=tier, proposed_path=proposed_path,
        confidence=confidence, reason=reason,
        source_subfolder=subfolder,
        dedup_verdict=dedup_verdict,
        taxonomy_version=taxonomy.version,
        swept_at=swept_at,
    )


# ── Live shelf oracle ─────────────────────────────────────────────────────────

def _build_shelf_oracle(config: LibraryConfig) -> frozenset[str] | None:
    """Walk the live shelf; return a frozenset of planned_calibre_key values.

    Returns None on any error — the caller routes all files to
    review_oracle_missing rather than proposing without dedup (fail-closed).
    shelf-index.json has no live producer (EB-380 research), so this always
    builds the key-set fresh from the shelved sections each sweep.
    """
    from .identity import planned_calibre_key
    from .metadata import BookMetadata, extract_metadata

    keys: set[str] = set()
    skip = {f.lower() for f in config.operational_folders}
    skip.update(e.lower() for e in config.scan_exclude)

    try:
        library_root = config.library_root
        if not library_root.is_dir():
            return frozenset()  # new/empty library is not an oracle error
        for entry in library_root.iterdir():
            if entry.name.lower() in skip or entry.name.startswith("_"):
                continue
            if not entry.is_dir():
                continue
            for dirpath, _, filenames in os.walk(str(entry), followlinks=False):
                for fname in filenames:
                    p = Path(dirpath) / fname
                    if p.suffix.lower() not in BOOK_EXTS:
                        continue
                    sha, _ = _hash_file(p)
                    if not sha:
                        continue
                    try:
                        meta = extract_metadata(p)
                    except Exception:
                        meta = BookMetadata(None, None, None, None)
                    keys.add(planned_calibre_key(meta, sha))
    except Exception as exc:
        log.error("_build_shelf_oracle failed: %s", exc)
        return None

    return frozenset(keys)


# ── Entry point ───────────────────────────────────────────────────────────────

def sweep_inbox(
    config: LibraryConfig,
    run_dir: Path,
    taxonomy: Taxonomy,
    *,
    library_root_arg: Path,
    settle_seconds: int = 30,
    tier_thresholds: dict[str, float] | None = None,
    _shelf_oracle=_LIVE,
) -> SweepResult:
    """Sweep _Inbox and emit a tiered proposal queue.  MOVES NOTHING.

    Parameters
    ----------
    config :
        Loaded library config.  config.library_root must equal library_root_arg.
    run_dir :
        Directory for lock + queue.  Must resolve OUTSIDE F:\\Books.
    taxonomy :
        Loaded taxonomy for classification.
    library_root_arg :
        The --library-root CLI argument.  Must equal config.library_root (G7).
    settle_seconds :
        Minimum file age in seconds before a file is eligible.
    tier_thresholds :
        Confidence thresholds: ``"low"`` and ``"high"``.  None → module defaults.
    _shelf_oracle :
        Injection point.  ``_LIVE`` (default) = build from shelf; ``frozenset`` =
        use as-is; ``None`` = oracle unavailable → all files → review_oracle_missing.

    Returns
    -------
    SweepResult
        ``skipped_lock=True`` when the lock was held by another sweep or confirm.
    """
    # AUTO-MOVE IS T3 — do NOT add confirm invocation without a new ADR
    _assert_root_match(config, library_root_arg)

    thresholds = tier_thresholds or _DEFAULT_THRESHOLDS
    lock_path = run_dir / LOCK_FILENAME
    queue_path = run_dir / QUEUE_FILENAME

    # O_EXCL lock — mutually exclusive with any concurrent sweep or confirm
    try:
        with open(lock_path, "x", encoding="utf-8") as fh:
            fh.write("sweep")
    except FileExistsError:
        log.warning("sweep_inbox: lock held at %s — skipping", lock_path)
        return SweepResult(skipped_lock=True)

    try:
        return _sweep_locked(
            config=config,
            taxonomy=taxonomy,
            queue_path=queue_path,
            settle_seconds=settle_seconds,
            thresholds=thresholds,
            shelf_oracle=_shelf_oracle,
        )
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def _sweep_locked(
    *,
    config: LibraryConfig,
    taxonomy: Taxonomy,
    queue_path: Path,
    settle_seconds: int,
    thresholds: dict[str, float],
    shelf_oracle,
) -> SweepResult:
    """Inner sweep body (runs with lock held)."""
    swept_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    now = time.time()

    # Resolve oracle
    oracle: frozenset[str] | None
    if shelf_oracle is _LIVE:
        oracle = _build_shelf_oracle(config)
    else:
        oracle = shelf_oracle  # frozenset | None

    rows_by_sha: dict[str, dict] = _load_queue(queue_path)

    # Path → sha for short-circuit (live rows only)
    path_to_sha: dict[str, str] = {
        row["path"]: row["sha"]
        for row in rows_by_sha.values()
        if row.get("tier") not in ("stale", "superseded")
    }

    inbox = config.library_root / "_Inbox"
    live_paths: set[str] = set()
    live_shas: set[str] = set()
    counts: dict[str, int] = {}

    for path in _iter_inbox_paths(inbox, settle_seconds, now):
        path_str = str(path)
        live_paths.add(path_str)

        # Short-circuit: skip re-hash when (path, size, mtime) unchanged
        existing_sha = path_to_sha.get(path_str)
        if existing_sha and existing_sha in rows_by_sha:
            existing_row = rows_by_sha[existing_sha]
            if existing_row.get("tier") in _STABLE_TIERS:
                try:
                    st = path.stat()
                    unchanged = (
                        existing_row.get("size") == st.st_size
                        and existing_row.get("mtime", 0.0) == st.st_mtime
                    )
                    if unchanged:
                        live_shas.add(existing_sha)
                        counts[existing_row["tier"]] = counts.get(existing_row["tier"], 0) + 1
                        continue
                except OSError:
                    pass

        row = _compute_row(path, config, taxonomy, oracle, thresholds, swept_at)
        sha = row["sha"]

        # Supersede old row for this path if sha changed
        if existing_sha and existing_sha != sha and existing_sha in rows_by_sha:
            old = dict(rows_by_sha[existing_sha])
            old["tier"] = "superseded"
            old["swept_at"] = swept_at
            rows_by_sha[existing_sha] = old

        rows_by_sha[sha] = row
        live_shas.add(sha)
        counts[row["tier"]] = counts.get(row["tier"], 0) + 1

    # Tombstone rows whose source file has vanished
    for sha, row in list(rows_by_sha.items()):
        if row.get("tier") in ("stale", "superseded"):
            continue
        if sha in live_shas:
            continue
        path_str = row.get("path", "")
        if not path_str or path_str in live_paths:
            continue
        updated = dict(row)
        updated["tier"] = "stale"
        updated["swept_at"] = swept_at
        rows_by_sha[sha] = updated
        counts["stale"] = counts.get("stale", 0) + 1

    _save_queue(queue_path, rows_by_sha)

    total = sum(counts.values())
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return SweepResult(
        skipped_lock=False,
        counts=counts,
        queue_written=True,
        summary=f"swept {total} file(s): {summary}" if total else "swept 0 files",
    )
