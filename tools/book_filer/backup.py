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

import hashlib
from dataclasses import dataclass
from pathlib import Path

_HASH_CHUNK = 1 << 20  # 1 MiB, matches scan._hash_file
_DEFAULT_SAMPLE = 64


@dataclass(frozen=True)
class BackupVerification:
    ok: bool
    reason: str


def _sha256_file(path: Path) -> str:
    """sha256 hex of a file, read-only in 'rb' chunks (mirrors scan._hash_file)."""
    h = hashlib.sha256()
    with open(path, "rb", buffering=_HASH_CHUNK) as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


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
        {"relpath": rel, "sha256": _sha256_file(mirror_root / rel)}
        for rel in _sample_relpaths(relpaths, sample_size)
    ]
    return {"mirror_root": str(mirror_root), "file_count": len(relpaths), "sample": sample}


def verify_backup_proof(live_root: Path, proof: dict) -> BackupVerification:
    """Confirm the live corpus matches a backup proof. Fail closed on any drift."""
    live_root = Path(live_root)
    if not isinstance(proof, dict):
        return BackupVerification(False, "backup proof is not a mapping (fail closed)")

    expected_count = proof.get("file_count")
    if not isinstance(expected_count, int):
        return BackupVerification(False, "backup proof missing file_count (fail closed)")

    sample = proof.get("sample")
    if not isinstance(sample, list) or not sample:
        return BackupVerification(False, "backup proof has no sample (fail closed)")

    live_count = sum(1 for p in live_root.rglob("*") if p.is_file())
    if live_count != expected_count:
        return BackupVerification(
            False, f"file-count drift: live {live_count} != proof {expected_count}"
        )

    for entry in sample:
        rel = entry.get("relpath") if isinstance(entry, dict) else None
        want = entry.get("sha256") if isinstance(entry, dict) else None
        if not rel or not want:
            return BackupVerification(False, "backup proof sample entry malformed (fail closed)")
        f = live_root / rel
        if not f.is_file():
            return BackupVerification(False, f"sampled file missing in live corpus: {rel}")
        if _sha256_file(f) != want:
            return BackupVerification(False, f"sha256 mismatch for sampled file: {rel}")

    return BackupVerification(
        True, f"verified: {live_count} files, {len(sample)} sampled sha256 match the mirror"
    )
