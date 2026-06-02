"""Duplicate planning (spec §6.4). Merge formats; collapse exact same-format dups to the best copy.

No filesystem access — operates on FileInfo records the caller has gathered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_REDOWNLOAD_RE = re.compile(r"\((\d+)\)|copy", re.IGNORECASE)


@dataclass(frozen=True)
class FileInfo:
    path: str
    sha256: str
    format: str        # "epub", "pdf", ...
    size: int
    has_metadata: bool
    work_key: str      # normalized author|title|year (from identity)


@dataclass(frozen=True)
class Member:
    path: str
    action: str        # "keep" | "merge-format" | "trash"
    reason: str


@dataclass(frozen=True)
class DupGroup:
    work_key: str
    members: tuple[Member, ...]


def _keeper_sort_key(f: FileInfo):
    # Prefer: has metadata, then larger, then a "clean" (non-redownload) name, then path (stable).
    return (not f.has_metadata, -f.size, bool(_REDOWNLOAD_RE.search(f.path)), f.path)


def plan_dedup(files: list[FileInfo]) -> list[DupGroup]:
    by_work: dict[str, list[FileInfo]] = {}
    for f in files:
        by_work.setdefault(f.work_key, []).append(f)

    groups: list[DupGroup] = []
    for work_key, work_files in by_work.items():
        members: list[Member] = []
        # Within a work, split by format. One canonical per work; same-format extras collapse.
        by_format: dict[str, list[FileInfo]] = {}
        for f in work_files:
            by_format.setdefault(f.format, []).append(f)

        # The overall canonical format-representative is the best file across all formats.
        overall_keeper = sorted(work_files, key=_keeper_sort_key)[0]

        for fmt, fmt_files in by_format.items():
            # Exact duplicates share a sha256. Only byte-identical extras may be
            # trashed; files that share a work_key but differ in content are NOT
            # exact dups and are routed to review, never auto-trashed.
            by_sha: dict[str, list[FileInfo]] = {}
            for f in fmt_files:
                by_sha.setdefault(f.sha256, []).append(f)

            sha_reps: list[FileInfo] = []
            for dups in by_sha.values():
                ranked = sorted(dups, key=_keeper_sort_key)
                sha_reps.append(ranked[0])
                for extra in ranked[1:]:
                    members.append(Member(extra.path, "trash",
                                          f"exact duplicate (sha256 match) of {ranked[0].path}"))

            # Defensive: sha_reps is non-empty by construction (every format has
            # >=1 file), but guard the index so a future filter inside this loop
            # can't introduce an IndexError.
            if not sha_reps:
                continue
            # Best distinct-content representative of this format.
            fmt_rep = sorted(sha_reps, key=_keeper_sort_key)[0]
            for rep in sha_reps:
                if rep.path == overall_keeper.path:
                    members.append(Member(rep.path, "keep", "canonical copy"))
                elif rep.path == fmt_rep.path and fmt != overall_keeper.format:
                    members.append(Member(rep.path, "merge-format",
                                          f"alternate format ({fmt}) of the same work"))
                else:
                    members.append(Member(rep.path, "review",
                                          f"distinct same-work {fmt} copy (different content); "
                                          "needs human review"))
        groups.append(DupGroup(work_key, tuple(sorted(members, key=lambda m: m.path))))
    return sorted(groups, key=lambda g: g.work_key)
