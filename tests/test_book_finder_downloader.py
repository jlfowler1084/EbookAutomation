"""Regression tests for EB-356 BookFinder search/download defects.

Anchors the five verified blockers fixed under EB-356. Four are exercised here
(the fifth, the PowerShell ``-List`` parameter-set binding, is a pure-PS concern
covered by ``tests/Invoke-EbookBookDownload.ParamSet.Tests.ps1``).

    Defect 1  book_finder: ``title`` is a POSITIONAL arg, not ``--title``.
    Defect 3  book_downloader.mark_complete / get_stats need sqlite3.Row.
    Defect 4  book_downloader.get_pending session filter (WHERE before ORDER BY).
    Defect 5  book_downloader.run honors an explicit ``books=`` selection
              instead of always re-pulling the whole pending queue (--ids path).

Run with:
    py -3.12 -m pytest tests/test_book_finder_downloader.py -v

Every downloader test pins ``output_root`` to the pytest ``tmp_path`` fixture, so
no test reads or writes the real F:\\Books library.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import book_downloader  # noqa: E402
import book_finder  # noqa: E402


# ---------------------------------------------------------------------------
# Defect 1 — book_finder declares `title` positional (not `--title`)
# ---------------------------------------------------------------------------

def test_search_title_is_positional():
    """The PS call site must pass the title positionally; this pins that contract."""
    parser = book_finder.build_parser()
    ns = parser.parse_args(["search", "Atomic Habits", "--author", "James Clear"])
    assert ns.title == "Atomic Habits"
    assert ns.author == "James Clear"


def test_search_rejects_title_flag():
    """`--title` is the original bug (psm1 used to pass it) — argparse must reject it."""
    parser = book_finder.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--title", "Atomic Habits"])


# ---------------------------------------------------------------------------
# Multi-source args — contract the psm1 wrapper must satisfy (review Finding 3)
# ---------------------------------------------------------------------------

def test_sources_single_flag_takes_all_values():
    """`-s libgen anna` (nargs="+") must yield BOTH sources — the form the
    wrapper now emits."""
    parser = book_finder.build_parser()
    ns = parser.parse_args(["search", "A Title", "-s", "libgen", "anna"])
    assert ns.sources == ["libgen", "anna"]


def test_sources_repeated_flag_keeps_only_last():
    """Documents WHY the wrapper must not repeat the flag: `-s libgen -s anna`
    collapses to anna-only, silently dropping libgen."""
    parser = book_finder.build_parser()
    ns = parser.parse_args(["search", "A Title", "-s", "libgen", "-s", "anna"])
    assert ns.sources == ["anna"]


# ---------------------------------------------------------------------------
# Defect 3 — mark_complete + get_stats require conn.row_factory = sqlite3.Row
# ---------------------------------------------------------------------------

def test_mark_complete_writes_history(tmp_path):
    """Pre-fix this raised TypeError on book["title"] against a tuple row."""
    db = book_downloader.DownloadDB(tmp_path / "state.db")
    book_id = db.add_book("My Title", "My Author", "epub", md5="abc123")

    # Must not raise; must record both the completion and a history row.
    db.mark_complete(book_id, str(tmp_path / "out.epub"), file_size="123 bytes")

    stats = db.get_stats()
    assert stats["complete"] == 1
    assert stats["downloaded_total"] == 1


def test_get_stats_uses_named_access(tmp_path):
    """get_stats reads row["c"] — needs row_factory, else TypeError on a tuple."""
    db = book_downloader.DownloadDB(tmp_path / "state.db")
    db.add_book("Pending One", "Author", "epub")
    db.add_book("Pending Two", "Author", "pdf")

    stats = db.get_stats()  # would TypeError pre-fix
    assert stats["pending"] == 2
    assert stats["complete"] == 0
    assert stats["failed"] == 0


# ---------------------------------------------------------------------------
# Defect 4 — get_pending builds the WHERE clause BEFORE ORDER BY
# ---------------------------------------------------------------------------

def test_get_pending_filters_by_session(tmp_path):
    """Pre-fix the session filter sat after ORDER BY and returned every session."""
    db = book_downloader.DownloadDB(tmp_path / "state.db")
    s1 = db.start_session("root1")
    s2 = db.start_session("root2")
    db.add_book("Book A", "Author A", "epub", session_id=s1)
    db.add_book("Book B", "Author B", "epub", session_id=s2)

    s1_titles = {b["title"] for b in db.get_pending(session_id=s1)}
    assert s1_titles == {"Book A"}  # NOT {"Book A", "Book B"}


def test_get_pending_no_filter_returns_all(tmp_path):
    """Sanity: without a session_id the filter is absent and all pending return."""
    db = book_downloader.DownloadDB(tmp_path / "state.db")
    db.add_book("Book A", "Author A", "epub", session_id=db.start_session("r1"))
    db.add_book("Book B", "Author B", "epub", session_id=db.start_session("r2"))

    assert {b["title"] for b in db.get_pending()} == {"Book A", "Book B"}


# ---------------------------------------------------------------------------
# Defect 5 — run() honors an explicit books= selection (--ids path)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# load_books_from_json — single-result object (PowerShell ConvertTo-Json collapse)
# ---------------------------------------------------------------------------

def test_load_books_from_json_single_object(tmp_path):
    """A one-result search serializes as a bare object, not a 1-element array.
    Must be read as a single book, not "no books"."""
    import json
    p = tmp_path / "one.json"
    p.write_text(json.dumps(
        {"title": "Solo", "author": "A", "format": "epub",
         "download_url": "http://example/s.epub"}), encoding="utf-8")
    books = book_downloader.load_books_from_json(str(p))
    assert len(books) == 1
    assert books[0]["title"] == "Solo"


def test_load_books_from_json_array(tmp_path):
    """The multi-result path (a JSON array) is unchanged."""
    import json
    p = tmp_path / "many.json"
    p.write_text(json.dumps(
        [{"title": "One", "download_url": "u1"},
         {"title": "Two", "download_url": "u2"}]), encoding="utf-8")
    books = book_downloader.load_books_from_json(str(p))
    assert [b["title"] for b in books] == ["One", "Two"]


def test_load_books_from_json_container_dict(tmp_path):
    """A {"results": [...]} container is still honored (not mistaken for a book)."""
    import json
    p = tmp_path / "wrapped.json"
    p.write_text(json.dumps({"results": [{"title": "Wrapped", "download_url": "u"}]}),
                 encoding="utf-8")
    books = book_downloader.load_books_from_json(str(p))
    assert [b["title"] for b in books] == ["Wrapped"]


def _fake_book(book_id: int) -> dict:
    return {
        "id": book_id, "title": f"Book {book_id}", "author": "A",
        "format": "epub", "download_url": "http://example/x", "md5": "",
        "max_retries": 1, "retry_count": 0, "local_path": "",
    }


def test_run_uses_explicit_books_without_repulling_queue(tmp_path, monkeypatch):
    """run(books=...) must download exactly those and NOT call get_pending."""
    dl = book_downloader.BookDownloader(output_root=str(tmp_path))
    monkeypatch.setattr(book_downloader.time, "sleep", lambda *_: None)

    pending_calls = {"n": 0}
    real_get_pending = dl.db.get_pending
    monkeypatch.setattr(
        dl.db, "get_pending",
        lambda *a, **k: (pending_calls.__setitem__("n", pending_calls["n"] + 1)
                         or real_get_pending(*a, **k)),
    )

    processed: list[int] = []
    monkeypatch.setattr(
        dl, "download_book",
        lambda book: (processed.append(book["id"]) or True),
    )

    result = dl.run(books=[_fake_book(999)])

    assert pending_calls["n"] == 0          # the queue was NOT re-pulled
    assert processed == [999]               # only the explicit selection ran
    assert result["completed"] == 1
    assert result["failed"] == 0


def test_run_falls_back_to_pending_when_no_books(tmp_path, monkeypatch):
    """When books= is omitted, run() still pulls the pending queue (no regression)."""
    dl = book_downloader.BookDownloader(output_root=str(tmp_path))
    monkeypatch.setattr(book_downloader.time, "sleep", lambda *_: None)
    monkeypatch.setattr(dl, "download_book", lambda book: True)

    pending_calls = {"n": 0}
    real_get_pending = dl.db.get_pending
    monkeypatch.setattr(
        dl.db, "get_pending",
        lambda *a, **k: (pending_calls.__setitem__("n", pending_calls["n"] + 1)
                         or real_get_pending(*a, **k)),
    )
    dl.db.add_book("Queued", "A", "epub")

    dl.run()  # books=None
    assert pending_calls["n"] == 1
