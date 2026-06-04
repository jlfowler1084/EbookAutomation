import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.move import MoveDecision, execute_move, plan_move


def _file(p: Path, content: bytes = b"data") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _mk_junction(link: Path, target: Path) -> bool:
    return subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True,
    ).returncode == 0


def _rm_junction(link: Path) -> None:
    if link.exists() or link.is_symlink():
        try:
            os.rmdir(link)  # removes the junction LINK only, never the target (SCRUM-301)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

def test_clean_move_relocates_file_and_creates_dirs(tmp_path):
    src = _file(tmp_path / "src" / "a.epub", b"hello")
    dst = tmp_path / "dst" / "sub" / "a.epub"
    decision = plan_move(src, dst)
    assert decision.action == "move" and decision.dst == dst
    outcome = execute_move(decision)
    assert outcome.moved is True
    assert dst.is_file() and dst.read_bytes() == b"hello"
    assert not src.exists()


# --------------------------------------------------------------------------- #
# Collision handling — never overwrite
# --------------------------------------------------------------------------- #

def test_dest_exists_routes_to_unique_when_allowed(tmp_path):
    src = _file(tmp_path / "src" / "a.epub", b"NEW")
    dst = _file(tmp_path / "dst" / "a.epub", b"ORIGINAL")
    decision = plan_move(src, dst, allow_unique=True)
    assert decision.action == "move" and decision.dst != dst
    outcome = execute_move(decision)
    assert outcome.moved is True
    assert dst.read_bytes() == b"ORIGINAL"          # original never overwritten
    assert decision.dst.read_bytes() == b"NEW"      # moved alongside as "a (2).epub"


def test_dest_exists_skips_when_unique_disallowed(tmp_path):
    src = _file(tmp_path / "src" / "a.epub", b"NEW")
    dst = _file(tmp_path / "dst" / "a.epub", b"ORIGINAL")
    decision = plan_move(src, dst, allow_unique=False)
    assert decision.action == "skip"
    outcome = execute_move(decision)
    assert outcome.moved is False
    assert dst.read_bytes() == b"ORIGINAL" and src.read_bytes() == b"NEW"  # nothing moved


def test_execute_refuses_to_overwrite_dst_created_after_plan(tmp_path):
    src = _file(tmp_path / "src" / "a.epub", b"NEW")
    dst = tmp_path / "dst" / "a.epub"
    decision = plan_move(src, dst)          # planned clean (dst was free)
    assert decision.action == "move"
    _file(dst, b"RACE")                     # dst appears between plan and execute
    outcome = execute_move(decision)
    assert outcome.moved is False
    assert dst.read_bytes() == b"RACE"      # never overwritten
    assert src.read_bytes() == b"NEW"       # src untouched


# --------------------------------------------------------------------------- #
# Missing / irregular source
# --------------------------------------------------------------------------- #

def test_missing_source_skips(tmp_path):
    decision = plan_move(tmp_path / "src" / "ghost.epub", tmp_path / "dst" / "ghost.epub")
    assert decision.action == "skip" and "source" in decision.reason.lower()


# --------------------------------------------------------------------------- #
# Reparse-point / junction safety (Windows) — never traverse, never touch target
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(os.name != "nt", reason="NTFS junctions are Windows-only")
def test_reparse_in_source_ancestry_skips_and_never_touches_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    protected = _file(target / "book.epub", b"PROTECTED")
    link = tmp_path / "link"
    if not _mk_junction(link, target):
        pytest.skip("could not create NTFS junction")
    try:
        src_through_junction = link / "book.epub"   # path traverses the junction
        dst = tmp_path / "dst" / "book.epub"
        decision = plan_move(src_through_junction, dst)
        assert decision.action == "skip" and "reparse" in decision.reason.lower()
        assert protected.read_bytes() == b"PROTECTED" and not dst.exists()
        # Even a forced execute must re-check and refuse (TOCTOU defense).
        forced = execute_move(MoveDecision("move", src_through_junction, dst, "forced"))
        assert forced.moved is False
        assert protected.read_bytes() == b"PROTECTED" and not dst.exists()
    finally:
        _rm_junction(link)


@pytest.mark.skipif(os.name != "nt", reason="NTFS junctions are Windows-only")
def test_reparse_in_destination_ancestry_skips(tmp_path):
    src = _file(tmp_path / "src" / "a.epub", b"data")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "destlink"
    if not _mk_junction(link, target):
        pytest.skip("could not create NTFS junction")
    try:
        dst_through_junction = link / "sub" / "a.epub"   # dst parent traverses the junction
        decision = plan_move(src, dst_through_junction)
        assert decision.action == "skip" and "reparse" in decision.reason.lower()
        assert src.read_bytes() == b"data"               # src untouched
    finally:
        _rm_junction(link)


@pytest.mark.skipif(os.name != "nt", reason="NTFS junctions are Windows-only")
def test_dangling_junction_in_source_path_skips(tmp_path):
    link = tmp_path / "dangling"
    if not _mk_junction(link, tmp_path / "does_not_exist"):
        pytest.skip("could not create NTFS junction")
    try:
        # A dangling junction reports exists()==False yet still carries the reparse bit (EB-360).
        decision = plan_move(link / "a.epub", tmp_path / "dst" / "a.epub")
        assert decision.action == "skip"
    finally:
        _rm_junction(link)


# --------------------------------------------------------------------------- #
# Unit 7 safety contracts — lock the fail-closed branches (EB-353)
# --------------------------------------------------------------------------- #

def test_every_unsafe_condition_skips_contract(tmp_path):
    """Regression lock: each fail-closed branch of plan_move yields action='skip'."""
    assert plan_move(tmp_path / "missing.epub", tmp_path / "d.epub").action == "skip"   # missing src
    a_dir = tmp_path / "adir"
    a_dir.mkdir()
    assert plan_move(a_dir, tmp_path / "d.epub").action == "skip"                        # src is a dir
    src = _file(tmp_path / "s" / "a.epub", b"x")
    _file(tmp_path / "d" / "a.epub", b"y")
    assert plan_move(src, tmp_path / "d" / "a.epub", allow_unique=False).action == "skip"  # dest collision


def test_move_module_relocates_via_atomic_replace_only():
    """Contract: move.py relocates via os.replace (atomic same-volume rename) and is
    delete-free / copy-free -- it never shutil-copies or deletes a library file."""
    src = (Path(__file__).resolve().parents[1] / "tools" / "book_filer" / "move.py").read_text(encoding="utf-8")
    assert "os.replace(" in src
    for forbidden in ("shutil", "os.remove", "os.unlink", ".unlink(", ".rmdir(", "rmtree"):
        assert forbidden not in src, f"move.py must be delete-free; found {forbidden!r}"
