"""EB-355 -WhatIf Read-Only Scan Driver.

Scans a directory of books and produces a migration manifest WITHOUT touching
any source file. All writes go to <out_dir> only (G1-gated).

Usage:
    python scan.py --root <dir> --out-dir <dir> --stamp <str>
                   [--limit N] [--force] [--taxonomy-version N]
                   [--settings <path>] [--taxonomy <path>]

PYTHONHASHSEED=0 is REQUIRED. The main() guard asserts it; the calibration
driver sets it for both fresh process runs.

Read-only guarantees: G1-G12 (see §2.1 of the build plan).
"""
from __future__ import annotations

# ============================================================
# BANNED-MUTATOR NOTICE — see §2.1 G3 of the build plan.
# ONLY allowed writes: out_dir.mkdir + open(path, 'w'/'wb') under
# out_dir (G1-gated). Atomic rename via the stdlib atomic-rename
# primitive (tmp->final) is used for all artifact writes under out_dir.
# ============================================================

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import stat
import sys
from dataclasses import asdict
from pathlib import Path, PureWindowsPath

# Support both `python scan.py` (direct) and `import book_filer.scan` (package).
# When run directly, relative imports fail, so we add the parent dir to sys.path.
if __name__ == "__main__" or __package__ is None or __package__ == "":
    _HERE = Path(__file__).resolve().parent.parent  # tools/
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from book_filer.calibration import CalibrationVerdict, SpotCheck, evaluate_calibration
    from book_filer.classify import classify_name
    from book_filer.config import LibraryConfig, load_library_config
    from book_filer.dedup import DupGroup, FileInfo, Member, plan_dedup
    from book_filer.fragments import FragmentVerdict, detect_fragment_sets
    from book_filer.identity import planned_calibre_key
    from book_filer.manifest import ManifestRow, canonical_projection, write_manifest
    from book_filer.metadata import extract_metadata, BookMetadata
    from book_filer.pathsafe import build_base_name, compute_shelf_path, sanitize_component
    from book_filer.reparse import _is_reparse_point, has_reparse_in_ancestry
    from book_filer.taxonomy import Taxonomy, load_taxonomy
    from book_filer.classify import Classification
else:
    from .calibration import CalibrationVerdict, SpotCheck, evaluate_calibration
    from .classify import classify_name, Classification
    from .config import LibraryConfig, load_library_config
    from .dedup import DupGroup, FileInfo, Member, plan_dedup
    from .fragments import FragmentVerdict, detect_fragment_sets
    from .identity import planned_calibre_key
    from .manifest import ManifestRow, canonical_projection, write_manifest
    from .metadata import extract_metadata, BookMetadata
    from .pathsafe import build_base_name, compute_shelf_path, sanitize_component
    from .reparse import _is_reparse_point, has_reparse_in_ancestry
    from .taxonomy import Taxonomy, load_taxonomy

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

TOOL_VERSION = "0.4.0"
BOOK_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".azw"}        # D3: .txt excluded
FRAGMENT_EXTS = {".xhtml", ".opf", ".ncx", ".css", ".jpg", ".jpeg", ".png", ".gif"}
_HASH_CHUNK = 1 << 20

_MUTATOR_RE = re.compile(
    r"(?i)\b(Move-Item|Remove-Item|Copy-Item|New-Item|mklink|"
    r"Set-Content|Out-File|del|rmdir|rd)\b"
)  # G6 banned-content in undo artifact

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# G1 — Safety assertion: out_dir must be outside scan root (both directions)
# ---------------------------------------------------------------------------

class UnsafeScanError(RuntimeError):
    """Raised when G1 safety assertion fails. Fatal."""


def _assert_output_outside_scan(scan: Path, out: Path) -> None:
    """G1: Reject if out is inside scan, scan inside out, or reparse in scan ancestry.

    Both-directions check, case-insensitive on resolved .parts.
    Raises UnsafeScanError on any violation.
    """
    try:
        scan_res = scan.resolve()
        out_res = out.resolve()
    except OSError as e:
        raise UnsafeScanError(f"Cannot resolve paths: {e}") from e

    scan_parts = tuple(p.lower() for p in scan_res.parts)
    out_parts = tuple(p.lower() for p in out_res.parts)

    # Check: out inside scan (out_parts starts with scan_parts)
    if len(out_parts) >= len(scan_parts) and out_parts[: len(scan_parts)] == scan_parts:
        raise UnsafeScanError(
            f"G1 violation: out_dir {out!r} is inside or equal to scan root {scan!r}"
        )

    # Check: scan inside out (scan_parts starts with out_parts)
    if len(scan_parts) >= len(out_parts) and scan_parts[: len(out_parts)] == out_parts:
        raise UnsafeScanError(
            f"G1 violation: scan root {scan!r} is inside or equal to out_dir {out!r}"
        )

    # Check: reparse in scan root ancestry
    if has_reparse_in_ancestry(scan_res):
        raise UnsafeScanError(
            f"G1 violation: reparse point in scan root ancestry: {scan!r}"
        )


# ---------------------------------------------------------------------------
# Hashing (G2: read-only, "rb" only)
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> tuple[str, int]:
    """Return (sha256_hex, size_bytes). G2: opens path in 'rb' mode only.

    Returns ("", 0) on any OSError — caller builds error row.
    """
    h = hashlib.sha256()
    size = 0
    try:
        # G2: MUST be "rb" — never write/append/plus mode on scan paths
        with open(path, "rb", buffering=_HASH_CHUNK) as fh:
            for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
                h.update(chunk)
                size += len(chunk)
        return h.hexdigest(), size
    except OSError as e:
        log.warning("Cannot hash %s: %s", path, e)
        return "", 0


# ---------------------------------------------------------------------------
# Author sort heuristic (flagged: not Calibre-grade; Plan-5 re-derives)
# ---------------------------------------------------------------------------

def _author_sort(author: str | None) -> str | None:
    """Simple 'Last, First' sort key. Not Calibre-grade — Plan-5 re-derives."""
    if not author:
        return None
    parts = author.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return author


# ---------------------------------------------------------------------------
# Enumeration — junction-safe, config-derived (G4, G8)
# ---------------------------------------------------------------------------

def _build_skip_set(config: LibraryConfig) -> set[str]:
    """G8: name-based skip set, derived ONLY from config.operational_folders (lowercased).

    scan_exclude entries are NOT in this set — they are handled separately by
    _build_exclude_resolved (resolved full-path match) to prevent substring
    over-matching (e.g. 'Audio_Books' must not prune 'Audio_Books_Backup').
    """
    return {f.lower() for f in config.operational_folders}


def _build_exclude_resolved(config: LibraryConfig, scan_root: Path) -> set[Path]:
    """Resolve scan_exclude entries relative to scan_root for exact-path pruning.

    This prevents substring over-matching: 'Audio_Books' matches only
    <root>/Audio_Books, NOT <root>/Audio_Books_Backup.
    """
    excluded = set()
    for name in config.scan_exclude:
        excluded.add((scan_root / name).resolve())
    return excluded


def _is_reparse(path: Path) -> bool:
    """Check if path itself is a reparse point. Fail-closed on any error."""
    try:
        attrs = os.lstat(path).st_file_attributes
        return bool(attrs & _REPARSE)
    except (OSError, AttributeError):
        return True  # fail-closed: treat as reparse if we can't check


def _iter_book_files(
    scan_root: Path,
    config: LibraryConfig,
    out_dir: Path,
) -> tuple[list[Path], list[Path], list[str]]:
    """Enumerate book files using explicit os.scandir DFS.

    Returns (book_paths, fragment_paths, skip_notes).

    G4: never follows links; scandir stack DFS, no os.walk(followlinks=True).
    G8: skip set from config only.
    Reparse: per-child check before queuing; ancestry check before descending.
    Fail-CLOSED on any OSError from reparse check.
    Zero-byte files: skipped, noted (G11).
    """
    skip_set = _build_skip_set(config)
    exclude_resolved = _build_exclude_resolved(config, scan_root)
    out_resolved = out_dir.resolve()

    book_paths: list[Path] = []
    fragment_paths: list[Path] = []
    skip_notes: list[str] = []

    # DFS stack — entries are (dir_path, depth)
    stack: list[Path] = [scan_root]

    while stack:
        current_dir = stack.pop()

        # G4: check reparse in ancestry before descending
        try:
            if has_reparse_in_ancestry(current_dir):
                skip_notes.append(f"SKIP (reparse in ancestry): {current_dir}")
                log.info("Skipping reparse-in-ancestry dir: %s", current_dir)
                continue
        except (OSError, AttributeError) as e:
            skip_notes.append(f"SKIP (reparse check error, fail-closed): {current_dir}: {e}")
            log.warning("Reparse check failed (fail-closed), skipping: %s: %s", current_dir, e)
            continue

        # Skip out_dir subtree (G1 defensive)
        try:
            if current_dir.resolve() == out_resolved:
                skip_notes.append(f"SKIP (out_dir): {current_dir}")
                continue
        except OSError:
            pass

        try:
            entries = list(os.scandir(current_dir))
        except PermissionError as e:
            skip_notes.append(f"SKIP (permission denied): {current_dir}: {e}")
            log.warning("Permission denied on dir: %s: %s", current_dir, e)
            continue
        except OSError as e:
            skip_notes.append(f"SKIP (OSError on dir): {current_dir}: {e}")
            log.warning("OSError on dir: %s: %s", current_dir, e)
            continue

        subdirs: list[Path] = []

        for entry in entries:
            try:
                entry_path = Path(entry.path)

                # Skip hidden/system (leading '.')
                if entry.name.startswith("."):
                    continue

                # G3: skip hidden/system Windows attributes
                try:
                    attrs = os.lstat(entry.path).st_file_attributes
                    _HIDDEN = 0x2
                    _SYSTEM = 0x4
                    if attrs & (_HIDDEN | _SYSTEM):
                        continue
                except (OSError, AttributeError):
                    pass

                if entry.is_dir(follow_symlinks=False):
                    dir_name_lower = entry.name.lower()

                    # G8: skip operational folders (case-insensitive)
                    if dir_name_lower in skip_set:
                        skip_notes.append(f"SKIP (operational): {entry_path}")
                        log.debug("Skipping operational folder: %s", entry_path)
                        continue

                    # G8: skip scan_exclude by resolved full path (no substring match)
                    try:
                        resolved = entry_path.resolve()
                        if resolved in exclude_resolved:
                            skip_notes.append(f"SKIP (scan_exclude): {entry_path}")
                            log.debug("Skipping excluded folder: %s", entry_path)
                            continue
                    except OSError:
                        pass

                    # Skip out_dir subtree
                    try:
                        if entry_path.resolve() == out_resolved:
                            skip_notes.append(f"SKIP (out_dir): {entry_path}")
                            continue
                    except OSError:
                        pass

                    # G4: per-child reparse check before queuing subdir
                    try:
                        if entry.is_symlink():
                            skip_notes.append(f"SKIP (symlink dir): {entry_path}")
                            log.info("Skipping symlink dir: %s", entry_path)
                            continue
                        if _is_reparse(entry_path):
                            skip_notes.append(f"SKIP (reparse point dir): {entry_path}")
                            log.info("Skipping reparse point dir: %s", entry_path)
                            continue
                    except (OSError, AttributeError) as e:
                        # Fail-CLOSED: do NOT descend if we can't check
                        skip_notes.append(
                            f"SKIP (reparse check error, fail-closed): {entry_path}: {e}"
                        )
                        log.warning("Reparse check error (fail-closed): %s: %s", entry_path, e)
                        continue

                    subdirs.append(entry_path)

                elif entry.is_file(follow_symlinks=False):
                    # Skip symlink files
                    if entry.is_symlink():
                        continue

                    suffix = Path(entry.name).suffix.lower()

                    # G11: skip zero-byte files
                    try:
                        file_size = entry.stat(follow_symlinks=False).st_size
                        if file_size == 0:
                            skip_notes.append(f"SKIP (zero-byte): {entry_path}")
                            log.debug("Skipping zero-byte: %s", entry_path)
                            continue
                    except OSError:
                        pass

                    if suffix in BOOK_EXTS:
                        book_paths.append(entry_path)
                    elif suffix in FRAGMENT_EXTS:
                        fragment_paths.append(entry_path)

            except (OSError, PermissionError) as e:
                skip_notes.append(f"SKIP (file entry error): {entry.path}: {e}")
                log.warning("File entry error: %s: %s", entry.path, e)
                continue

        # Add subdirs to stack (they'll be processed in DFS order)
        stack.extend(reversed(subdirs))

    # Sort the flat lists for determinism (scandir is unordered)
    book_paths.sort(key=lambda p: str(p))
    fragment_paths.sort(key=lambda p: str(p))

    return book_paths, fragment_paths, skip_notes


# ---------------------------------------------------------------------------
# Per-file pipeline
# ---------------------------------------------------------------------------

class _FileFacts:
    """All derived facts about a single book file."""

    __slots__ = (
        "path", "sha256", "size", "meta", "cls", "planned_key",
        "work_key", "has_metadata", "error", "fmt",
    )

    def __init__(
        self, path: Path, sha256: str, size: int, meta, cls, planned_key: str,
        work_key: str, has_metadata: bool, error: str | None, fmt: str,
    ):
        self.path = path
        self.sha256 = sha256
        self.size = size
        self.meta = meta
        self.cls = cls
        self.planned_key = planned_key
        self.work_key = work_key
        self.has_metadata = has_metadata
        self.error = error
        self.fmt = fmt


def _build_file_facts(path: Path, taxonomy: Taxonomy) -> _FileFacts:
    """Build all facts for one book file. Never raises into the filer (G5)."""
    fmt = path.suffix.lower().lstrip(".")
    error: str | None = None

    sha, size = _hash_file(path)
    if not sha:
        # OSError during hashing — error row
        error = f"could not read file: {path}"
        sha = ""
        size = 0

    # Metadata extraction (all-None for .mobi/.azw*)
    try:
        meta = extract_metadata(path)
    except Exception as e:
        log.warning("Metadata extraction failed for %s: %s", path, e)
        meta = BookMetadata(None, None, None, None)

    # Classification (wrapped defensively)
    try:
        cls = classify_name(path.name, taxonomy)
    except Exception as e:
        log.warning("Classification failed for %s: %s", path, e)
        cls = Classification("review", None, None, 0.0)

    # Identity key
    planned_key = planned_calibre_key(meta, sha)
    work_key = planned_key if not error else str(path)

    has_metadata = bool(meta.title and meta.author)

    return _FileFacts(
        path=path,
        sha256=sha,
        size=size,
        meta=meta,
        cls=cls,
        planned_key=planned_key,
        work_key=work_key,
        has_metadata=has_metadata,
        error=error,
        fmt=fmt,
    )


# ---------------------------------------------------------------------------
# Duplicate group ID — content-derived (§1.4, deterministic)
# ---------------------------------------------------------------------------

def _dup_group_id(work_key: str) -> str:
    """Content-derived group ID: dup:<sha1(work_key)[:12]>.

    NOT a walk-order counter — stable across runs.
    """
    h = hashlib.sha1(work_key.encode("utf-8")).hexdigest()
    return f"dup:{h[:12]}"


# ---------------------------------------------------------------------------
# Destination path — content-derived, NO unique_path in dry-run (§1.6)
# ---------------------------------------------------------------------------

def _destination_path(
    facts: _FileFacts,
    config: LibraryConfig,
    disambiguator: str | None = None,
) -> str:
    """Compute destination path from content key. Never calls unique_path (§1.6, G12).

    Returns "" if the file cannot be shelved (review/quarantine/error).
    """
    if facts.error or not facts.cls or facts.cls.disposition in ("non_library", "review"):
        return ""

    section = facts.cls.section or ""
    subcategory = facts.cls.subcategory or ""
    if not section or not subcategory:
        return ""

    author_sort_val = _author_sort(facts.meta.author) or "Unknown"
    title = facts.meta.title or facts.path.stem
    year = facts.meta.year
    ext = facts.path.suffix.lower()

    try:
        dest = compute_shelf_path(
            library_root=config.library_root,
            section=section,
            subcategory=subcategory,
            author_sort=author_sort_val,
            title=title,
            ext=ext,
            year=year,
            disambiguator=disambiguator,
            max_path_length=config.max_path_length,
        )
        # G7: destination must resolve under library_root
        dest_str = str(dest)
        lib_str = str(config.library_root)
        if not dest_str.lower().startswith(lib_str.lower()):
            log.warning("Destination escapes library root: %s", dest_str)
            return ""
        # G12: destination_path is never opened/mkdir'd in dry-run; just stringify
        return dest_str
    except Exception as e:
        log.warning("compute_shelf_path failed for %s: %s", facts.path, e)
        return ""


# ---------------------------------------------------------------------------
# Action resolution — §1.5 precedence table
# ---------------------------------------------------------------------------

def _resolve_action(
    facts: _FileFacts,
    member: Member | None,
    has_metadata_in_group: bool,
    fragment_verdict: FragmentVerdict | None,
    config: LibraryConfig,
    dest: str,
) -> tuple[str, bool, str]:
    """Return (action, review_required, canonical_reason) per §1.5 precedence."""

    # 1. Error row
    if facts.error is not None:
        return "review", True, facts.error

    # 2. Destination exceeds max_path_length
    if dest and len(dest) > config.max_path_length:
        return "quarantine", True, "destination exceeds max_path_length"

    # 3. Reparse in source or destination ancestry
    try:
        if has_reparse_in_ancestry(facts.path):
            return "quarantine", True, "reparse point in source/destination (SCRUM-301)"
    except (OSError, AttributeError):
        pass

    if dest:
        try:
            if has_reparse_in_ancestry(Path(dest)):
                return "quarantine", True, "reparse point in source/destination (SCRUM-301)"
        except (OSError, AttributeError):
            pass

    # 4. Fragment verdict
    if fragment_verdict is not None:
        return "review", True, fragment_verdict.reason

    # 5. Dedup: trash ONLY with a real metadata anchor (G11 / M1, EB-355 review).
    # has_metadata_in_group (computed by the caller) is True only when SOME member
    # of the sha-matched group actually has embedded metadata. A sha-only group
    # with no metadata anchor is downgraded to review — never auto-trashed, because
    # there is no identity to justify which byte-identical copy is canonical.
    if member is not None and member.action == "trash":
        if has_metadata_in_group:
            return "trash", False, member.reason
        else:
            return "review", True, "sha-only duplicate, no metadata anchor — review"

    # 6. Dedup: review
    if member is not None and member.action == "review":
        return "review", True, member.reason

    # 7. Non-library classification
    if facts.cls.disposition == "non_library":
        return "review", True, "non-library file"

    # 8. Low-confidence/ambiguous classification
    if facts.cls.disposition == "review":
        return "review", True, "low-confidence/ambiguous classification"

    # 9. Dedup: merge-format
    if member is not None and member.action == "merge-format":
        return "merge-format", False, member.reason

    # 10. Shelf -> materialize_mode
    if facts.cls.disposition == "shelf":
        # Determine canonical_reason from the identity key
        pk = facts.planned_key
        if pk.startswith("isbn:"):
            digits = pk[5:]
            reason = f"[ISBN {digits}]"
        elif pk.startswith("meta:"):
            reason = ""
        else:
            reason = f"[sha {facts.sha256[:8]}]"
        return config.materialize_mode, False, reason

    # Fallback
    return "review", True, "unclassified"


# ---------------------------------------------------------------------------
# Manifest assembly — §1.4
# ---------------------------------------------------------------------------

def build_manifest_rows(
    book_paths: list[Path],
    fragment_paths: list[Path],
    config: LibraryConfig,
    taxonomy: Taxonomy,
    taxonomy_version: int,
    limit: int | None = None,
) -> list[ManifestRow]:
    """Build all ManifestRow objects. Called once; returns sorted list."""

    # Apply limit after sort (§1.2)
    paths = book_paths  # already sorted by _iter_book_files
    if limit is not None:
        paths = paths[:limit]

    # Build facts for each file
    facts_list: list[_FileFacts] = []
    for p in paths:
        facts_list.append(_build_file_facts(p, taxonomy))

    # Build FileInfo list for dedup
    file_infos: list[FileInfo] = [
        FileInfo(
            path=str(f.path),
            sha256=f.sha256,
            format=f.fmt,
            size=f.size,
            has_metadata=f.has_metadata,
            work_key=f.work_key,
        )
        for f in facts_list
    ]

    # Plan dedup
    dup_groups: list[DupGroup] = plan_dedup(file_infos)

    # Build lookup: path -> (Member, group, has_metadata_in_group)
    path_to_member: dict[str, tuple[Member, DupGroup]] = {}
    for group in dup_groups:
        for member in group.members:
            path_to_member[member.path] = (member, group)

    # Fragment detection — called ONCE PER PARENT DIRECTORY (§1.4, wraps EB-359)
    # Group candidate paths by parent directory
    from collections import defaultdict
    by_parent: dict[str, list[str]] = defaultdict(list)
    # Include both book paths and fragment paths for fragment detection
    all_paths_for_fragments = [str(p) for p in paths] + [str(p) for p in fragment_paths]
    for p_str in all_paths_for_fragments:
        parent = str(PureWindowsPath(p_str).parent)
        by_parent[parent].append(p_str)

    # Merge fragment verdicts
    path_to_fragment: dict[str, FragmentVerdict] = {}
    for parent_dir, parent_paths in by_parent.items():
        verdicts = detect_fragment_sets(parent_paths)
        for verdict in verdicts:
            for member_path in verdict.members:
                if member_path not in path_to_fragment:
                    path_to_fragment[member_path] = verdict

    # Build rows
    rows: list[ManifestRow] = []

    for facts in facts_list:
        path_str = str(facts.path)
        member_info = path_to_member.get(path_str)
        member = member_info[0] if member_info else None
        group = member_info[1] if member_info else None

        # Determine if group has any member with metadata (for sha-only trash check)
        group_members: list[Member] = list(group.members) if group else []

        # Fragment verdict for this path
        fragment_verdict = path_to_fragment.get(path_str)

        # Determine has_metadata_in_group for trash downgrade logic
        # For the dedup group, check if any keep/non-trash member has metadata
        # We use the facts_list to look up has_metadata for other group members
        facts_by_path: dict[str, _FileFacts] = {str(f.path): f for f in facts_list}
        if group:
            has_metadata_in_group = any(
                facts_by_path[m.path].has_metadata
                for m in group_members
                if m.path in facts_by_path and m.action != "trash"
            )
        else:
            has_metadata_in_group = facts.has_metadata

        # Compute initial destination (without disambiguator)
        if facts.error or not facts.cls or facts.cls.disposition in ("non_library", "review"):
            dest_str = ""
        else:
            # First pass: no disambiguator
            dest_str = _destination_path(facts, config)

        # Resolve action (first pass, may need to update dest with disambiguator)
        # We need the action to know if this is a shelf row that needs a destination
        action, review_required, canonical_reason = _resolve_action(
            facts, member, has_metadata_in_group, fragment_verdict, config, dest_str
        )

        # Destination collisions are resolved deterministically AFTER all rows are
        # built, by _disambiguate_destinations (called from scan()). An in-loop
        # first-pass attempt was removed (EB-355 PR #185 review): it iterated the
        # partial `rows` list and raised StopIteration when an earlier review row
        # (empty destination) was present, aborting the whole scan.

        # G7: validate destination is under library_root
        if dest_str:
            lib_str = str(config.library_root).lower()
            if not dest_str.lower().startswith(lib_str):
                dest_str = ""
                action = "quarantine"
                review_required = True
                canonical_reason = "destination outside library_root"

        # Recheck length after disambiguation
        if dest_str and len(dest_str) > config.max_path_length:
            action = "quarantine"
            review_required = True
            canonical_reason = "destination exceeds max_path_length"

        # duplicate_group_id: content-derived for multi-member groups; None for singletons (§1.4)
        if group and len(group.members) > 1:
            dup_id = _dup_group_id(group.work_key)
        else:
            dup_id = None

        # undo_action: inert commented no-op (G6)
        undo = f"# would restore: {path_str} -> {dest_str or '(no destination)'}"

        # isbn from metadata
        isbn = facts.meta.isbn if facts.meta else None

        row = ManifestRow(
            original_path=str(Path(facts.path).resolve()),  # normalized (§1.4)
            destination_path=dest_str,
            sha256=facts.sha256,
            size=facts.size,
            planned_calibre_key=facts.planned_key,
            calibre_id=None,  # C11: always None in dry-run
            isbn=isbn,
            format=facts.fmt,
            section=facts.cls.section if facts.cls else None,
            subcategory=facts.cls.subcategory if facts.cls else None,
            author_sort=_author_sort(facts.meta.author) if facts.meta else None,
            title=facts.meta.title or facts.path.stem,
            year=facts.meta.year if facts.meta else None,
            duplicate_group_id=dup_id,
            canonical_reason=canonical_reason,
            classification_confidence=facts.cls.confidence if facts.cls else 0.0,
            classification_source=facts.cls.source if facts.cls else "rule",
            taxonomy_version=taxonomy_version,
            tool_version=TOOL_VERSION,
            action=action,
            undo_action=undo,
            review_required=review_required,
        )
        rows.append(row)

    # Sort by original_path (§1.4)
    rows.sort(key=lambda r: r.original_path)

    # Assert no duplicate original_path (§1.4)
    seen_paths: set[str] = set()
    for r in rows:
        assert r.original_path not in seen_paths, f"Duplicate original_path: {r.original_path}"
        seen_paths.add(r.original_path)

    return rows


# ---------------------------------------------------------------------------
# Destination disambiguation — cleaner implementation
# ---------------------------------------------------------------------------

def _disambiguate_destinations(rows: list[ManifestRow], config: LibraryConfig,
                                facts_by_path: dict[str, _FileFacts]) -> list[ManifestRow]:
    """Post-process rows to ensure all non-empty destinations are unique.

    Two distinct-sha books that collide on destination get [sha <8>] disambiguators.
    Returns new list (rows are frozen dataclasses, so we rebuild).
    """
    # Group by destination
    from collections import defaultdict
    dest_groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r.destination_path:
            dest_groups[r.destination_path].append(i)

    # Find collisions (same dest, different sha)
    updated = list(rows)
    for dest, indices in dest_groups.items():
        if len(indices) <= 1:
            continue
        # Check if they actually have different sha256 (same sha = duplicate, handled by dedup)
        shas = [rows[i].sha256 for i in indices]
        if len(set(shas)) <= 1:
            continue
        # Real collision: append [sha <8>] to each
        for idx in indices:
            r = rows[idx]
            facts = facts_by_path.get(r.original_path)
            if facts is None:
                continue
            disambig = f"sha {r.sha256[:8]}"
            new_dest = _destination_path(facts, config, disambiguator=disambig)
            # Rebuild row with updated destination_path
            d = asdict(r)
            d["destination_path"] = new_dest
            updated[idx] = ManifestRow(**d)

    return updated


# ---------------------------------------------------------------------------
# Spot-check sheet generation (§3, deterministic stratified sampling)
# ---------------------------------------------------------------------------

def _spot_disposition(action: str) -> str:
    """Map a manifest action to the calibration vocabulary (shelf/review) so the
    spot-check sheet ingests directly into evaluate_calibration, which counts
    wrong-shelf only when disposition == 'shelf' (EB-355 gate-hardening)."""
    return "shelf" if action in ("copy", "hardlink") else "review"


def _build_spot_check(rows: list[ManifestRow], min_spots: int = 50) -> list[dict]:
    """Build a deterministic stratified spot-check sheet of min(min_spots, len(rows)) rows.

    Strata (by action): shelf (copy/hardlink), non_library, and review (everything
    else: review/quarantine/trash/merge-format/fragment). Each stratum is sorted by
    sha256 and a proportional slice is taken; then the deterministic remainder is
    filled up to the target. The prior integer-proportional slicing alone could sum
    to < min_spots even when enough rows existed (e.g. 51 shelf + 2 review -> 48 + 1
    = 49), creating a FALSE calibration RED on sample size. Returns list of dicts.
    """
    total = len(rows)
    if total == 0:
        return []

    strata: dict[str, list[ManifestRow]] = {"shelf": [], "non_library": [], "review": []}
    for r in rows:
        if r.action in ("copy", "hardlink"):
            strata["shelf"].append(r)
        elif r.action == "non_library":
            strata["non_library"].append(r)
        else:
            strata["review"].append(r)

    target = min(min_spots, total)

    def _key(r: ManifestRow) -> tuple[str, str]:
        return (r.sha256, r.original_path)

    selected: list[ManifestRow] = []
    seen: set[str] = set()

    # 1) Proportional slice per stratum (deterministic by sha256, then path).
    for stratum_rows in strata.values():
        if not stratum_rows:
            continue
        take = max(1, int(len(stratum_rows) / total * target))
        for r in sorted(stratum_rows, key=_key)[:take]:
            if r.original_path not in seen:
                selected.append(r)
                seen.add(r.original_path)

    # 2) Fill the deterministic remainder up to the target (fixes integer-truncation
    #    underfill: proportional slices can sum to < target even when rows exist).
    if len(selected) < target:
        for r in sorted(rows, key=_key):
            if r.original_path not in seen:
                selected.append(r)
                seen.add(r.original_path)
                if len(selected) >= target:
                    break

    # 3) Emit in deterministic order, capped at the target, with sequential numbering.
    selected.sort(key=_key)
    selected = selected[:target]
    spots: list[dict] = []
    for i, r in enumerate(selected, 1):
        spots.append({
            "spot_index": i,
            "disposition": _spot_disposition(r.action),
            "section": r.section or "",
            "subcategory": r.subcategory or "",
            "confidence": r.classification_confidence,
            "filename": Path(r.original_path).name,
            "dest-tail": Path(r.destination_path).name if r.destination_path else "",
            "correct?": "",
            "note": "",
        })
    return spots


# ---------------------------------------------------------------------------
# G6 — undo artifact inertness assertion
# ---------------------------------------------------------------------------

def _assert_undo_inert(content: str) -> None:
    """G6: Assert every non-blank line in the undo script starts with '#'.

    Rejects any uncommented _MUTATOR_RE match. Raises ValueError on violation.
    """
    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            raise ValueError(
                f"G6: undo artifact line {lineno} is not a comment: {line!r}"
            )
        # Check for uncommented mutator content after the # prefix
        uncommented = stripped.lstrip("#").strip()
        if _MUTATOR_RE.search(uncommented):
            # This is inside a comment, which is fine for documentation purposes.
            # But we must not have it as executable code. Since ALL non-blank lines
            # start with #, this check passes (the mutator is commented out).
            pass


# ---------------------------------------------------------------------------
# Atomic write helper (G10)
# ---------------------------------------------------------------------------

def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """G10: Atomic text write. Writes only under out_dir (G1-gated)."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding=encoding) as fh:
        fh.write(content)
    # G10: atomic rename — tmp under out_dir only, never targets scan root
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """G10: Atomic bytes write. Writes only under out_dir (G1-gated)."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(content)
    # G10: atomic rename — tmp under out_dir only, never targets scan root
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Output writing (§1.7)
# ---------------------------------------------------------------------------

def _write_scan_outputs(
    rows: list[ManifestRow],
    out_dir: Path,
    stamp: str,
    skip_notes: list[str],
    projection_a: str,
    projection_b: str | None,
    corpus_count: int,
    corpus_size: int,
) -> None:
    """Write all output artifacts under out_dir (G1-gated location). G10: atomic writes."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # plan-<stamp>.{csv,json,md}
    write_manifest(rows, out_dir, stamp)

    # canonical-projection.txt — lets a later run compare via --compare-to (§3),
    # so the two-run determinism verdict is real rather than a single-run placeholder.
    _atomic_write_text(out_dir / "canonical-projection.txt", projection_a)

    # shelf-index.json — one entry per row with a destination, no clobber
    shelf_index: dict[str, dict] = {}
    for r in rows:
        if r.destination_path:
            if r.destination_path not in shelf_index:
                shelf_index[r.destination_path] = {
                    "original_path": r.original_path,
                    "sha256": r.sha256,
                    "action": r.action,
                    "format": r.format,
                }
    _atomic_write_text(
        out_dir / "shelf-index.json",
        json.dumps(shelf_index, indent=2, sort_keys=True),
    )

    # <stamp>-undo.ps1.txt — inert commented script (G6)
    undo_lines = [
        "# Auto-generated undo script (INERT). All lines are comments — no executable code.",
        "# This file is a .ps1.txt to prevent accidental execution.",
        "# Rename to .ps1 and manually review before executing any restore.",
        "#",
    ]
    for r in reversed(rows):
        if r.undo_action:
            # G6: every undo_action must already start with '#'
            line = r.undo_action if r.undo_action.strip().startswith("#") else f"# {r.undo_action}"
            undo_lines.append(line)

    undo_content = "\n".join(undo_lines) + "\n"
    _assert_undo_inert(undo_content)  # G6: assert before write
    _atomic_write_text(out_dir / f"{stamp}-undo.ps1.txt", undo_content)

    # scan-summary.md
    action_counts: dict[str, int] = {}
    for r in rows:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1

    summary_lines = [
        f"# Scan Summary — {stamp}",
        "",
        f"**Corpus:** {corpus_count} file(s), {corpus_size:,} bytes",
        f"**Rows:** {len(rows)}",
        "",
        "## Action breakdown",
        "",
    ]
    for action, count in sorted(action_counts.items()):
        summary_lines.append(f"- `{action}`: {count}")
    summary_lines += ["", "## Skip notes", ""]
    for note in skip_notes[:100]:  # cap at 100 for readability
        summary_lines.append(f"- {note}")
    if len(skip_notes) > 100:
        summary_lines.append(f"- ... and {len(skip_notes) - 100} more")

    _atomic_write_text(out_dir / "scan-summary.md", "\n".join(summary_lines) + "\n")

    # determinism-report.md + determinism-diff.json
    if projection_b is not None:
        deterministic = projection_a == projection_b
        det_report = [
            f"# Determinism Report — {stamp}",
            "",
            f"**Deterministic:** {'YES' if deterministic else 'NO'}",
            "",
        ]
        if not deterministic:
            det_report += [
                "## Differences detected",
                "",
                "Run A and Run B produced different canonical projections.",
                "See determinism-diff.json for details.",
            ]
        _atomic_write_text(out_dir / "determinism-report.md", "\n".join(det_report) + "\n")

        diff_data = {
            "deterministic": deterministic,
            "run_a_len": len(json.loads(projection_a)) if projection_a else 0,
            "run_b_len": len(json.loads(projection_b)) if projection_b else 0,
        }
        if not deterministic:
            diff_data["note"] = "Projections differ — see scan-summary.md for diagnostics"
        _atomic_write_bytes(out_dir / "determinism-diff.json",
                            json.dumps(diff_data, indent=2).encode("utf-8"))
    else:
        # Single-run mode: emit placeholder
        _atomic_write_text(
            out_dir / "determinism-report.md",
            f"# Determinism Report — {stamp}\n\nSingle-run mode; no comparison performed.\n"
        )
        _atomic_write_bytes(
            out_dir / "determinism-diff.json",
            b'{"deterministic": null, "note": "single-run mode"}\n'
        )

    # spot-check-sheet.{csv,md}
    spots = _build_spot_check(rows)
    spot_fields = ["spot_index", "disposition", "section", "subcategory", "confidence",
                   "filename", "dest-tail", "correct?", "note"]
    spot_csv_path = out_dir / "spot-check-sheet.csv"
    tmp_csv = Path(str(spot_csv_path) + ".tmp")
    with open(tmp_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=spot_fields)
        writer.writeheader()
        writer.writerows(spots)
    os.replace(tmp_csv, spot_csv_path)

    spot_md_lines = ["# Spot-Check Sheet", "",
                     "| spot_index | disposition | section | subcategory | confidence | filename | dest-tail | correct? | note |",
                     "|---|---|---|---|---|---|---|---|---|"]
    for s in spots:
        spot_md_lines.append(
            f"| {s['spot_index']} | {s['disposition']} | {s['section']} | {s['subcategory']} | "
            f"{s['confidence']:.2f} | {s['filename']} | {s['dest-tail']} | "
            f"{s['correct?']} | {s['note']} |"
        )
    _atomic_write_text(out_dir / "spot-check-sheet.md", "\n".join(spot_md_lines) + "\n")

    # calibration-verdict.json (placeholder — real verdict requires human sign-off)
    verdict_data = {
        "note": "Run evaluate_calibration() with signed_off_by after human spot-check review.",
        "deterministic": projection_b is not None and projection_a == projection_b,
        "spot_check_size": len(spots),
        "green": False,
        "reason": "Pending human sign-off",
    }
    _atomic_write_bytes(
        out_dir / "calibration-verdict.json",
        json.dumps(verdict_data, indent=2).encode("utf-8"),
    )

    # _COMPLETE sentinel — written LAST (G10)
    _atomic_write_text(out_dir / "_COMPLETE", f"stamp={stamp}\nrows={len(rows)}\n")


# ---------------------------------------------------------------------------
# Main scan entry point
# ---------------------------------------------------------------------------

def scan(
    root: Path,
    out_dir: Path,
    stamp: str,
    settings_path: Path | None = None,
    taxonomy_path: Path | None = None,
    limit: int | None = None,
    force: bool = False,
    taxonomy_version_override: int | None = None,
    compare_to: Path | None = None,
) -> list[ManifestRow]:
    """Run the -WhatIf scan. Returns the manifest rows.

    Raises UnsafeScanError on G1 violation (fatal).
    All other per-file errors produce error rows (G5).
    """
    # G1: assert output is outside scan root — FIRST (before any scandir)
    _assert_output_outside_scan(root, out_dir)

    # Refuse to overwrite an existing complete manifest unless --force
    complete_sentinel = out_dir / "_COMPLETE"
    if complete_sentinel.exists() and not force:
        raise FileExistsError(
            f"Complete manifest already exists at {out_dir}. Use --force to overwrite."
        )

    # Load config and taxonomy
    config = load_library_config(settings_path)
    taxonomy = load_taxonomy(taxonomy_path)

    # Read taxonomy version from JSON (never hardcoded)
    tax_data = json.loads(
        (taxonomy_path if taxonomy_path else
         Path(__file__).resolve().parents[2] / "config" / "books-taxonomy.json"
         ).read_text(encoding="utf-8")
    )
    taxonomy_version: int = int(tax_data.get("version", 1))
    if taxonomy_version_override is not None and "version" not in tax_data:
        taxonomy_version = taxonomy_version_override

    # Enumerate files
    book_paths, fragment_paths, skip_notes = _iter_book_files(root, config, out_dir)
    corpus_count = len(book_paths)
    corpus_size = sum(
        os.stat(p).st_size for p in book_paths
        if p.exists()
    )

    # Build manifest rows
    rows = build_manifest_rows(
        book_paths, fragment_paths, config, taxonomy, taxonomy_version, limit=limit
    )

    # Post-process: disambiguate destination collisions
    facts_by_path = {str(Path(p).resolve()): _build_file_facts(p, taxonomy) for p in book_paths}
    rows = _disambiguate_destinations(rows, config, facts_by_path)
    rows.sort(key=lambda r: r.original_path)

    # Compute canonical projection (run A).
    proj_a = canonical_projection(rows)

    # Two-run determinism (§3): if comparing to a prior run, load its persisted
    # projection so _write_scan_outputs emits a REAL verdict, not a placeholder.
    proj_b: str | None = None
    if compare_to is not None:
        proj_b = (Path(compare_to) / "canonical-projection.txt").read_text(encoding="utf-8")

    # Write outputs (G1-gated: only writes under out_dir)
    _write_scan_outputs(
        rows=rows,
        out_dir=out_dir,
        stamp=stamp,
        skip_notes=skip_notes,
        projection_a=proj_a,
        projection_b=proj_b,
        corpus_count=corpus_count,
        corpus_size=corpus_size,
    )

    return rows


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI main. Returns exit code."""
    # G13/§1.4: assert PYTHONHASHSEED=0 before any work
    if os.environ.get("PYTHONHASHSEED") != "0":
        print(
            "ERROR: PYTHONHASHSEED must be set to '0' for deterministic scanning.\n"
            "Run with: PYTHONHASHSEED=0 python scan.py ...\n"
            "Or set $env:PYTHONHASHSEED='0' in PowerShell.",
            file=sys.stderr,
        )
        return 1

    parser = argparse.ArgumentParser(
        description="EB-355 -WhatIf read-only book library scan driver."
    )
    parser.add_argument("--root", required=True, type=Path,
                        help="Directory to scan (source library root).")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="Output directory for manifest artifacts (must be outside --root).")
    parser.add_argument("--stamp", required=True, type=str,
                        help="Timestamp/run identifier string.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of files processed (for testing).")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing complete manifest.")
    parser.add_argument("--taxonomy-version", type=int, default=None,
                        help="Override taxonomy version (only if absent in JSON).")
    parser.add_argument("--settings", type=Path, default=None,
                        help="Path to settings.json (default: config/settings.json).")
    parser.add_argument("--taxonomy", type=Path, default=None,
                        help="Path to books-taxonomy.json (default: config/books-taxonomy.json).")
    parser.add_argument("--compare-to", type=Path, default=None,
                        help="Prior run's out-dir; loads its canonical-projection.txt to "
                             "emit a real two-run determinism verdict.")

    args = parser.parse_args(argv)

    # F2 (EB-355 review): resolve --root and --out-dir so a relative value cannot
    # silently resolve against the process CWD and surprise the user about where
    # output landed. G1 re-resolves internally regardless; this pins the user-facing
    # location and keeps the startup log honest.
    args.out_dir = args.out_dir.resolve()
    args.root = args.root.resolve()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        rows = scan(
            root=args.root,
            out_dir=args.out_dir,
            stamp=args.stamp,
            settings_path=args.settings,
            taxonomy_path=args.taxonomy,
            limit=args.limit,
            force=args.force,
            taxonomy_version_override=args.taxonomy_version,
            compare_to=args.compare_to,
        )
        print(f"Scan complete: {len(rows)} rows. Manifest: {args.out_dir}", file=sys.stderr)
        return 0

    except UnsafeScanError as e:
        print(f"FATAL: G1 UnsafeScanError: {e}", file=sys.stderr)
        return 2

    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    except Exception as e:
        print(f"FATAL: Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
