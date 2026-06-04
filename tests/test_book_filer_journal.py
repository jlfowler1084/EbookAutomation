import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.journal import (
    already_applied,
    applied_sources,
    append_record,
    read_records,
)
from book_filer.move import execute_move, plan_move


def _file(p: Path, content: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _rec(seq, src, dst, sha="s", action="copy"):
    return {"seq": seq, "src": str(src), "dst": str(dst),
            "action": action, "sha256": sha, "ts": "20260604-000000"}


def test_append_then_read_roundtrips_in_order(tmp_path):
    jp = tmp_path / "journal.jsonl"
    for i in range(3):
        append_record(jp, _rec(i, f"s{i}", f"d{i}"))
    assert [r["seq"] for r in read_records(jp)] == [0, 1, 2]


def test_read_tolerates_torn_final_line(tmp_path):
    jp = tmp_path / "journal.jsonl"
    append_record(jp, _rec(0, "s0", "d0"))
    append_record(jp, _rec(1, "s1", "d1"))
    with open(jp, "a", encoding="utf-8") as fh:   # crash mid-write: partial, unterminated line
        fh.write('{"seq": 2, "src":')
    assert [r["seq"] for r in read_records(jp)] == [0, 1]   # torn tail dropped, no raise


def test_read_missing_journal_is_empty(tmp_path):
    assert read_records(tmp_path / "nope.jsonl") == []


def test_applied_sources_collects_srcs():
    assert applied_sources([_rec(0, "A", "x"), _rec(1, "B", "y")]) == {"A", "B"}


def test_already_applied_idempotency_key(tmp_path):
    dst = _file(tmp_path / "dst" / "a.epub", b"applied-content")
    sha = hashlib.sha256(b"applied-content").hexdigest()
    src = tmp_path / "src" / "a.epub"   # absent -> already moved
    assert already_applied(src, dst, sha) is True
    # source still present -> not applied
    present = _file(tmp_path / "src2" / "a.epub", b"x")
    assert already_applied(present, dst, sha) is False
    # destination missing -> anomaly, NOT applied (do not silently skip)
    assert already_applied(tmp_path / "g_src", tmp_path / "g_dst", sha) is False
    # destination present but wrong sha -> not applied
    assert already_applied(tmp_path / "x_src", dst, "deadbeef") is False


def test_resume_after_crash_moves_only_remaining_no_double_move(tmp_path):
    jp = tmp_path / "journal.jsonl"
    srcs = [_file(tmp_path / "src" / f"b{i}.epub", f"c{i}".encode()) for i in range(3)]
    dsts = [tmp_path / "dst" / f"b{i}.epub" for i in range(3)]
    shas = [hashlib.sha256(f"c{i}".encode()).hexdigest() for i in range(3)]
    # Apply the first two, journaling each, then "crash" (stop).
    for i in range(2):
        assert execute_move(plan_move(srcs[i], dsts[i])).moved
        append_record(jp, _rec(i, srcs[i], dsts[i], sha=shas[i]))

    # Resume: skip rows already journaled OR idempotently applied; move the rest.
    done = applied_sources(read_records(jp))
    moved_now = []
    for i in range(3):
        if str(srcs[i]) in done or already_applied(srcs[i], dsts[i], shas[i]):
            continue
        if execute_move(plan_move(srcs[i], dsts[i])).moved:
            moved_now.append(i)

    assert moved_now == [2]                       # only the 3rd moved on resume
    assert all(d.is_file() for d in dsts)         # all three now at destination
    assert dsts[0].read_bytes() == b"c0" and dsts[1].read_bytes() == b"c1"  # not corrupted
