"""Append-only JSONL move journal + idempotent-resume helpers (EB-373 R5/R6).

Every committed move is durably recorded -- one fsync'd JSON line written BEFORE the
next move begins -- so a crash mid-run leaves a consistent, resumable state and the
journal is at worst one torn line ahead of reality. `read_records` therefore tolerates
a torn FINAL line (crash mid-write) but treats an unparseable earlier line as genuine
corruption. Resume skips rows already recorded in the journal OR idempotently applied
(source gone, destination present with the expected sha256), so a re-run never
double-moves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

if __package__:
    from .move import sha256_file
else:  # imported with tools/ on sys.path but no package context (mirrors scan.py)
    from book_filer.move import sha256_file


class JournalCorruptError(RuntimeError):
    """A non-final journal line failed to parse -- real corruption, not a torn tail."""


def append_record(path: Path, record: dict) -> None:
    """Append one record as a JSON line and fsync before returning, so the move that
    follows is always preceded by a durable record (crash-safe ordering, R5)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_records(path: Path) -> list[dict]:
    """Parse journal records. Tolerates a torn final line (crash mid-write); raises
    JournalCorruptError if an EARLIER line is unparseable (genuine corruption)."""
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break  # torn final line -- tolerated (R6)
            raise JournalCorruptError(f"journal corrupt at line {i + 1}: {line!r}")
    return records


def applied_sources(records: list[dict]) -> set[str]:
    """The set of source paths already recorded as moved (legacy single-record filter)."""
    return {r["src"] for r in records if isinstance(r, dict) and "src" in r}


def intents_by_seq(records: list[dict]) -> dict:
    """Latest write-ahead `intent` record per seq. A re-attempt overwrites an earlier intent,
    so the last one carries the resolved (possibly unique_path) destination."""
    out: dict = {}
    for r in records:
        if isinstance(r, dict) and r.get("state") == "intent" and "seq" in r:
            out[r["seq"]] = r
    return out


def committed_seqs(records: list[dict]) -> set:
    """Seqs with a durable `commit` record (the move definitely completed)."""
    return {r["seq"] for r in records if isinstance(r, dict) and r.get("state") == "commit" and "seq" in r}


def already_applied(src: Path, dst: Path, sha256: str) -> bool:
    """Idempotency key: True iff the source is gone AND the destination exists with the
    expected sha256. A source-gone-but-dest-missing row is an anomaly, NOT 'applied'
    (returns False so resume does not silently skip it)."""
    src, dst = Path(src), Path(dst)
    if src.exists():
        return False
    if not dst.is_file():
        return False
    return sha256_file(dst) == sha256
