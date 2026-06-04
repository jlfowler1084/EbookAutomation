"""Fail-closed single-file move primitive (EB-373 R4/R7).

Move one file via a same-volume atomic rename, or refuse -- never overwrite, never
traverse a reparse point (the SCRUM-301 junction-traversal data-loss class). The
pure DECISION (`plan_move`) is separated from the SIDE EFFECT (`execute_move`) so
the actuator's dry-run reuses `plan_move` with zero mutation, and the fail-closed
invariants are re-asserted at the destructive moment (TOCTOU defense).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .pathsafe import unique_path
    from .reparse import has_reparse_in_ancestry
else:  # imported with tools/ on sys.path but no package context (mirrors scan.py)
    from book_filer.pathsafe import unique_path
    from book_filer.reparse import has_reparse_in_ancestry


@dataclass(frozen=True)
class MoveDecision:
    action: str          # "move" | "skip"
    src: Path
    dst: Path            # collision-resolved target when action == "move"
    reason: str


@dataclass(frozen=True)
class MoveOutcome:
    moved: bool
    src: Path
    dst: Path
    reason: str


def plan_move(src: Path, dst: Path, *, allow_unique: bool = True) -> MoveDecision:
    """Decide whether `src` may move to `dst`. Pure: performs no filesystem mutation.

    Fail-closed decision matrix: a reparse point anywhere in the src OR dst ancestry,
    a missing/irregular source, or a destination collision (when unique routing is
    disallowed) all yield action="skip" with a reason. A collision with allow_unique
    routes to `unique_path(dst)`; the original is never overwritten.
    """
    src, dst = Path(src), Path(dst)
    if has_reparse_in_ancestry(src):
        return MoveDecision("skip", src, dst, f"reparse point in source ancestry: {src}")
    if has_reparse_in_ancestry(dst):
        return MoveDecision("skip", src, dst, f"reparse point in destination ancestry: {dst}")
    if not src.is_file():
        return MoveDecision("skip", src, dst, f"source missing or not a regular file: {src}")
    if dst.exists():
        if not allow_unique:
            return MoveDecision("skip", src, dst, f"destination exists; unique routing disallowed: {dst}")
        resolved = unique_path(dst)
        return MoveDecision("move", src, resolved, f"destination existed; routed to {resolved.name}")
    return MoveDecision("move", src, dst, "clean move")


def execute_move(decision: MoveDecision) -> MoveOutcome:
    """Realize a `plan_move` decision.

    A skip is a no-op. A move re-asserts the fail-closed invariants right before the
    irreversible step (reparse ancestry, source still present, destination still
    free), creates the destination directories, and performs an atomic same-volume
    rename. Any failure -- a locked/unreadable source, a race that created the
    destination -- returns moved=False. Never raises; never overwrites.
    """
    src, dst = Path(decision.src), Path(decision.dst)
    if decision.action != "move":
        return MoveOutcome(False, src, dst, decision.reason)
    if has_reparse_in_ancestry(src) or has_reparse_in_ancestry(dst):
        return MoveOutcome(False, src, dst, "reparse point in src/dst ancestry at execute time (refused)")
    if not src.is_file():
        return MoveOutcome(False, src, dst, f"source missing/not a file at execute time: {src}")
    if dst.exists():
        return MoveOutcome(False, src, dst, f"destination exists at execute time; refusing to overwrite: {dst}")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)  # atomic same-volume rename
    except OSError as e:
        return MoveOutcome(False, src, dst, f"move failed (locked/unreadable?): {e}")
    return MoveOutcome(True, src, dst, decision.reason)
