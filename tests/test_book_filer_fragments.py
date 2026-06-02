import sys
from pathlib import Path

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
