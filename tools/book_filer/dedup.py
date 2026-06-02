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
            fmt_keeper = sorted(fmt_files, key=_keeper_sort_key)[0]
            for f in fmt_files:
                if f.path == fmt_keeper.path:
                    if f.path == overall_keeper.path:
                        members.append(Member(f.path, "keep", "canonical copy"))
                    else:
                        members.append(Member(f.path, "merge-format",
                                              f"alternate format ({fmt}) of the same work"))
                else:
                    members.append(Member(f.path, "trash",
                                          f"redundant {fmt} copy; keeper={fmt_keeper.path}"))
        groups.append(DupGroup(work_key, tuple(sorted(members, key=lambda m: m.path))))
    return sorted(groups, key=lambda g: g.work_key)
