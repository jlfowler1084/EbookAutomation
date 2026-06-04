import sys
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.fragments import detect_fragment_sets


def test_numbered_suffix_set_is_flagged_for_review():
    paths = [f"Fourth_Step_Guided_Workbook-{i}.pdf" for i in range(1, 8)]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"
    assert set(sets[0].members) == set(paths)


def test_exploded_epub_debris_is_flagged_for_review():
    paths = ["book/ch1.xhtml", "book/ch2.xhtml", "book/content.opf", "book/toc.ncx", "book/style.css"]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"


def test_normal_distinct_books_are_not_fragment_sets():
    paths = ["Author - Title One (2001).epub", "Author - Title Two (2002).epub"]
    assert detect_fragment_sets(paths) == []


def test_never_auto_trashes():
    paths = [f"x-{i}.pdf" for i in range(1, 5)]
    # Policy: fragments are ALWAYS routed to review, never to trash, in the migration.
    assert all(s.disposition == "review" for s in detect_fragment_sets(paths))


def test_windows_paths_in_different_folders_are_not_grouped():
    # Real corpus uses Windows paths. EPUB-debris extensions in DIFFERENT real
    # folders must not be merged into one fragment set (the PurePosixPath bug
    # collapsed every backslash path to parent '.').
    paths = [r"F:\Books\A\ch1.xhtml", r"F:\Books\B\content.opf"]
    assert detect_fragment_sets(paths) == []


def test_windows_exploded_epub_in_one_folder_is_flagged():
    paths = [r"F:\Books\bk\content.opf", r"F:\Books\bk\toc.ncx", r"F:\Books\bk\ch1.xhtml"]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"
    assert set(sets[0].members) == set(paths)


# ---------------------------------------------------------------------------
# EB-359: step-2 numbered-suffix grouping must be folder-aware. A shared stem
# across DIFFERENT real folders must not collapse into one cross-folder set.
# (scan.py mitigates by calling per-folder; direct callers, including the future
# actuator, must be safe at the primitive.)
# ---------------------------------------------------------------------------

def test_numbered_set_must_not_span_multiple_folders():
    # Same stem 'vol', three different real folders; the folder-blind code
    # wrongly groups all three into one cross-folder set. Each folder holds <3
    # numbered files, so the correct result is no fragment set; and NO verdict
    # may ever span more than one parent directory.
    paths = [
        r"F:\Books\A\vol-1.pdf",
        r"F:\Books\B\vol-2.pdf",
        r"F:\Books\C\vol-3.pdf",
    ]
    sets = detect_fragment_sets(paths)
    for s in sets:
        parents = {str(PureWindowsPath(m).parent) for m in s.members}
        assert len(parents) == 1, f"fragment set spans >1 parent: {s.members}"
    assert sets == []


def test_numbered_set_within_one_folder_still_flagged():
    # No regression: >=3 numbered same-stem files in ONE folder are still a set.
    paths = [rf"F:\Books\Series\vol-{i}.pdf" for i in range(1, 4)]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"
    assert set(sets[0].members) == set(paths)


def test_same_stem_split_across_folders_does_not_merge_when_one_folder_qualifies():
    # Folder A has a real 3-part set; folder B has 2 same-stem parts. The B parts
    # must NOT be absorbed into A's set; the set stays within folder A only.
    a = [rf"F:\Books\A\doc-{i}.pdf" for i in range(1, 4)]
    b = [rf"F:\Books\B\doc-{i}.pdf" for i in range(1, 3)]
    sets = detect_fragment_sets(a + b)
    assert len(sets) == 1
    assert set(sets[0].members) == set(a)
