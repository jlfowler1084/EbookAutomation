import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.metadata import BookMetadata
from book_filer.identity import planned_calibre_key

_SHA = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


def test_isbn_takes_priority():
    meta = BookMetadata("Title", "Author", 2011, "978-1-4165-9786-5")
    assert planned_calibre_key(meta, _SHA) == "isbn:9781416597865"


def test_falls_back_to_normalized_author_title_year():
    meta = BookMetadata("The Oil Kings", "Cooper, Andrew Scott", 2011, None)
    assert planned_calibre_key(meta, _SHA) == "meta:cooper-andrew-scott|the-oil-kings|2011"


def test_falls_back_to_sha_when_no_usable_metadata():
    meta = BookMetadata(None, None, None, None)
    assert planned_calibre_key(meta, _SHA) == f"sha:{_SHA[:16]}"


def test_is_deterministic():
    meta = BookMetadata("The Oil Kings", "Cooper, Andrew Scott", 2011, None)
    assert planned_calibre_key(meta, _SHA) == planned_calibre_key(meta, _SHA)
