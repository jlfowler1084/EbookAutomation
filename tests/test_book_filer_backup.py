import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.backup import build_backup_proof, verify_backup_proof


def _make_tree(root: Path, files: dict[str, bytes]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


def _corpus(n: int = 10) -> dict[str, bytes]:
    return {f"sub{i % 3}/book{i}.epub": f"content-{i}".encode() for i in range(n)}


def test_verify_passes_for_identical_mirror(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(live, files)
    _make_tree(mirror, files)
    proof = build_backup_proof(mirror)
    assert verify_backup_proof(live, proof).ok is True


def test_build_proof_is_deterministic_and_samples_a_subset(tmp_path):
    mirror = tmp_path / "mirror"
    _make_tree(mirror, _corpus(200))
    p1 = build_backup_proof(mirror, sample_size=20)
    p2 = build_backup_proof(mirror, sample_size=20)
    assert p1["sample"] == p2["sample"]          # deterministic across two calls
    assert len(p1["sample"]) == 20               # a sampled subset, not all 200
    assert p1["file_count"] == 200               # but the count covers the whole corpus


def test_verify_fails_on_count_drift(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(mirror, files)
    _make_tree(live, files)
    (live / "extra.epub").write_bytes(b"x")      # live has one more file than the proof
    r = verify_backup_proof(live, build_backup_proof(mirror))
    assert r.ok is False and "count" in r.reason.lower()


def test_verify_fails_on_missing_sampled_file_and_names_it(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(mirror, files)
    _make_tree(live, files)
    proof = build_backup_proof(mirror)
    sampled_rel = proof["sample"][0]["relpath"]
    (live / sampled_rel).unlink()                # remove a sampled file...
    (live / "replacement.epub").write_bytes(b"z")  # ...but keep the count equal
    r = verify_backup_proof(live, proof)
    assert r.ok is False and sampled_rel in r.reason


def test_verify_fails_on_sha_mismatch_and_names_it(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(mirror, files)
    _make_tree(live, files)
    proof = build_backup_proof(mirror)
    sampled_rel = proof["sample"][0]["relpath"]
    (live / sampled_rel).write_bytes(b"TAMPERED")  # same file count, different content
    r = verify_backup_proof(live, proof)
    assert r.ok is False and sampled_rel in r.reason


def test_verify_fails_closed_on_empty_or_malformed_proof(tmp_path):
    live = tmp_path / "live"
    _make_tree(live, _corpus(10))
    assert verify_backup_proof(live, {"file_count": 10, "sample": []}).ok is False
    assert verify_backup_proof(live, "not-a-dict").ok is False


def test_verify_fails_when_mirror_root_is_the_live_root(tmp_path):
    """P3: a proof generated from the live library itself (mirror_root == live) proves no
    external backup exists -- refuse."""
    lib = tmp_path / "Books"
    _make_tree(lib, _corpus(10))
    proof = build_backup_proof(lib)            # mirror_root == lib (the reported bug)
    r = verify_backup_proof(lib, proof)
    assert r.ok is False and "external" in r.reason.lower()


def test_verify_fails_when_mirror_root_missing_or_nonexistent(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    _make_tree(live, _corpus(10))
    _make_tree(mirror, _corpus(10))
    proof = build_backup_proof(mirror)
    proof["mirror_root"] = str(tmp_path / "ghost")   # points at a nonexistent path
    assert verify_backup_proof(live, proof).ok is False
    del proof["mirror_root"]
    assert verify_backup_proof(live, proof).ok is False


def test_verify_passes_for_external_mirror(tmp_path):
    """A proof from a genuinely separate (disjoint) mirror tree still verifies."""
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(live, files)
    _make_tree(mirror, files)
    assert verify_backup_proof(live, build_backup_proof(mirror)).ok is True


def test_verify_fails_when_mirror_contents_are_gone(tmp_path):
    """The mirror ROOT existing is not enough: if its contents are wiped the backup is empty
    and must be refused, even though the live corpus still matches the proof."""
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(live, files)
    _make_tree(mirror, files)
    proof = build_backup_proof(mirror)
    for child in list(mirror.iterdir()):          # wipe contents, keep the (empty) root dir
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    r = verify_backup_proof(live, proof)
    assert r.ok is False and "mirror" in r.reason.lower()


def test_verify_fails_when_a_sampled_mirror_file_is_mutated(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(live, files)
    _make_tree(mirror, files)
    proof = build_backup_proof(mirror)
    sampled_rel = proof["sample"][0]["relpath"]
    (mirror / sampled_rel).write_bytes(b"MIRROR-TAMPERED")   # same count, different content
    r = verify_backup_proof(live, proof)
    assert r.ok is False and sampled_rel in r.reason


def test_verify_fails_when_a_sampled_mirror_file_is_missing(tmp_path):
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    files = _corpus(10)
    _make_tree(live, files)
    _make_tree(mirror, files)
    proof = build_backup_proof(mirror)
    sampled_rel = proof["sample"][0]["relpath"]
    (mirror / sampled_rel).unlink()
    (mirror / "replacement.epub").write_bytes(b"z")          # keep the mirror count equal
    r = verify_backup_proof(live, proof)
    assert r.ok is False and sampled_rel in r.reason
