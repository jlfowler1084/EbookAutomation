"""External-mirror backup-proof verification (EB-373 R3 / brainstorm D2).

The actuator performs in-place moves, so a verified external backup IS the safety
net. Before any move, the driver must confirm that a faithful external mirror of the
live corpus exists. A `backup-proof.json` (generated from the mirror) records the
mirror root, the total file count, and a deterministic sample of `(relpath, sha256)`.
`verify_backup_proof` recomputes the count + the same sample against the live corpus
and refuses on any drift.

Fail-closed: count drift, a sampled file missing in the live corpus, a sha256
mismatch, or a malformed/empty proof all return ok=False. Sampling is deterministic
(sorted relpaths, fixed stride) so two builds of the same tree agree byte-for-byte
and only the sampled files are hashed (cheap on a large corpus).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .move import sha256_file
else:  # imported with tools/ on sys.path but no package context (mirrors scan.py)
    from book_filer.move import sha256_file

_DEFAULT_SAMPLE = 64


@dataclass(frozen=True)
class BackupVerification:
    ok: bool
    reason: str


def _relpaths(root: Path) -> list[str]:
    """All files under `root` as sorted posix relpaths (deterministic)."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _sample_relpaths(relpaths: list[str], sample_size: int) -> list[str]:
    """A deterministic, evenly-spread subset of `relpaths` (fixed stride)."""
    if not relpaths:
        return []
    stride = max(1, len(relpaths) // sample_size)
    return relpaths[::stride][:sample_size]


def build_backup_proof(mirror_root: Path, sample_size: int = _DEFAULT_SAMPLE) -> dict:
    """Generate a backup-proof from an external mirror tree.

    Returns {mirror_root, file_count, sample:[{relpath, sha256}, ...]}. Only the
    sampled files are hashed. Deterministic for a fixed tree + sample_size.
    """
    mirror_root = Path(mirror_root)
    relpaths = _relpaths(mirror_root)
    sample = [
        {"relpath": rel, "sha256": sha256_file(mirror_root / rel)}
        for rel in _sample_relpaths(relpaths, sample_size)
    ]
    return {"mirror_root": str(mirror_root), "file_count": len(relpaths), "sample": sample}


def _disjoint(a: Path, b: Path) -> bool:
    """True if neither path is the other nor nested inside it (resolved, case-insensitive)."""
    try:
        ap = tuple(p.lower() for p in a.resolve().parts)
        bp = tuple(p.lower() for p in b.resolve().parts)
    except OSError:
        return False
    n = min(len(ap), len(bp))
    return ap[:n] != bp[:n]


def _verify_tree(root: Path, expected_count: int, sample: list, label: str) -> str | None:
    """None if `root` matches the proof's file_count + every sampled (relpath, sha256); else a
    reason. Used for BOTH the live corpus and the external mirror."""
    count = sum(1 for p in root.rglob("*") if p.is_file())
    if count != expected_count:
        return f"{label} file-count drift: {count} != proof {expected_count}"
    for entry in sample:
        rel = entry.get("relpath") if isinstance(entry, dict) else None
        want = entry.get("sha256") if isinstance(entry, dict) else None
        if not rel or not want:
            return f"{label}: backup proof sample entry malformed (fail closed)"
        f = root / rel
        if not f.is_file():
            return f"sampled file missing in {label}: {rel}"
        if sha256_file(f) != want:
            return f"sha256 mismatch in {label}: {rel}"
    return None


def verify_backup_proof(live_root: Path, proof: dict) -> BackupVerification:
    """Confirm an EXTERNAL mirror of the live corpus exists, still holds the backed-up files,
    and matches the live corpus -- fail closed on any drift.

    The mirror_root recorded in the proof must be present, exist, and be external to (disjoint
    from) live_root, or a proof generated from the live library itself would pass. Then BOTH the
    external mirror tree AND the live corpus must match the proof's file_count + sampled sha256s.
    Checking only live (with the mirror root merely existing) would let an emptied or drifted
    mirror pass while holding no real backup.
    """
    live_root = Path(live_root)
    if not isinstance(proof, dict):
        return BackupVerification(False, "backup proof is not a mapping (fail closed)")

    mirror_root = proof.get("mirror_root")
    if not isinstance(mirror_root, str) or not mirror_root:
        return BackupVerification(False, "backup proof missing mirror_root (cannot prove an external backup)")
    mirror = Path(mirror_root)
    if not mirror.exists():
        return BackupVerification(False, f"backup mirror_root does not exist: {mirror_root}")
    if not _disjoint(mirror, live_root):
        return BackupVerification(
            False, f"backup mirror_root is not external to the live root (inside/equal): {mirror_root}")

    expected_count = proof.get("file_count")
    if not isinstance(expected_count, int):
        return BackupVerification(False, "backup proof missing file_count (fail closed)")

    sample = proof.get("sample")
    if not isinstance(sample, list) or not sample:
        return BackupVerification(False, "backup proof has no sample (fail closed)")

    # The external mirror must STILL contain the backed-up files (root existing is not enough),
    # and the live corpus must match the same proof.
    mirror_fail = _verify_tree(mirror, expected_count, sample, "mirror")
    if mirror_fail:
        return BackupVerification(False, mirror_fail)
    live_fail = _verify_tree(live_root, expected_count, sample, "live")
    if live_fail:
        return BackupVerification(False, live_fail)

    return BackupVerification(
        True, f"verified: live + external mirror both match the proof "
              f"({expected_count} files, {len(sample)} sampled sha256)"
    )
