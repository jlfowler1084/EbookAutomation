import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.dedup import FileInfo, plan_dedup


def test_format_twins_are_all_kept_as_merge_format():
    files = [
        FileInfo("a.epub", "h1", "epub", 100, True, "cooper|oilkings|2011"),
        FileInfo("a.pdf", "h2", "pdf", 200, True, "cooper|oilkings|2011"),
    ]
    decisions = {d.path: d.action for group in plan_dedup(files) for d in group.members}
    # Different formats of the same work are both kept (one canonical 'keep', the other 'merge-format').
    assert set(decisions.values()) == {"keep", "merge-format"}


def test_exact_same_format_dup_collapses_to_best():
    files = [
        FileInfo("Book (1).epub", "h", "epub", 100, False, "w"),
        FileInfo("Book.epub", "h", "epub", 100, True, "w"),  # has metadata -> keeper
    ]
    [group] = plan_dedup(files)
    keep = [m for m in group.members if m.action == "keep"]
    trash = [m for m in group.members if m.action == "trash"]
    assert [m.path for m in keep] == ["Book.epub"]
    assert [m.path for m in trash] == ["Book (1).epub"]


def test_distinct_works_are_not_grouped():
    files = [
        FileInfo("x.epub", "h1", "epub", 1, True, "work-a"),
        FileInfo("y.epub", "h2", "epub", 1, True, "work-b"),
    ]
    assert len(plan_dedup(files)) == 2


def test_keeper_tiebreak_is_deterministic():
    files = [
        FileInfo("Book.epub", "h", "epub", 100, False, "w"),
        FileInfo("Book copy.epub", "h", "epub", 100, False, "w"),
    ]
    a = [m.action for g in plan_dedup(files) for m in g.members]
    b = [m.action for g in plan_dedup(files) for m in g.members]
    assert a == b  # stable ordering, no randomness


def test_nonidentical_same_format_collision_is_never_trashed():
    # Two same-format files sharing a work_key but with DIFFERENT sha256 are NOT
    # exact duplicates (different content). "Keep best of EXACT dups" must not
    # trash them; the non-canonical one is routed to review.
    files = [
        FileInfo("ed1.epub", "hash-A", "epub", 100, True, "w"),
        FileInfo("ed2.epub", "hash-B", "epub", 100, True, "w"),
    ]
    [group] = plan_dedup(files)
    actions = {m.path: m.action for m in group.members}
    assert "trash" not in actions.values()
    assert actions == {"ed1.epub": "keep", "ed2.epub": "review"}


def test_exact_sha_dup_still_collapses_alongside_a_distinct_copy():
    # Within a format: byte-identical extras (same sha256) trash; a distinct-content
    # copy (different sha256) survives as review.
    files = [
        FileInfo("a.epub", "h1", "epub", 100, True, "w"),
        FileInfo("a-copy.epub", "h1", "epub", 100, True, "w"),  # exact dup of a.epub
        FileInfo("b.epub", "h2", "epub", 100, True, "w"),       # distinct content
    ]
    [group] = plan_dedup(files)
    actions = {m.path: m.action for m in group.members}
    assert actions["a-copy.epub"] == "trash"          # byte-identical -> safe to trash
    assert actions["b.epub"] == "review"              # distinct content -> never trashed
    assert actions["a.epub"] == "keep"
