"""EB-369: pre-flight pattern-DB lock must not hang.

The pre-flight historical-data lookup (pattern_db.get_recommended_strategy)
is purely a read and is documented as non-blocking. But it went through
get_db(), which runs schema+migrate+index DDL on every connect — so a read
took write locks and could block (indefinitely, in the wild) behind a stale
writer. The fix routes the read path through a read-only, no-DDL connection
(get_db_readonly): a WAL reader never needs the write lock, so it cannot be
blocked by a writer.

These tests pin:
  - get_db_readonly exists, is read-only, and returns None when the DB is absent
  - get_recommended_strategy does not create the DB and does not block under a
    concurrent writer (the regression for the hang)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = TESTS_DIR.parent
TOOLS_DIR = WORKTREE_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import pattern_db  # noqa: E402


def test_get_db_readonly_returns_none_when_missing(tmp_path):
    """A read-only open of a not-yet-created DB returns None (caller → no data)."""
    missing = tmp_path / "data" / "nope.db"
    assert pattern_db.get_db_readonly(str(missing)) is None


def test_get_db_readonly_is_read_only(tmp_path):
    """The read-only connection must reject writes."""
    db = str(tmp_path / "data" / "ebook_patterns.db")
    pattern_db.get_db(db).close()  # create it
    conn = pattern_db.get_db_readonly(db)
    assert conn is not None
    import sqlite3
    try:
        with conn:
            try:
                conn.execute("CREATE TABLE _should_fail (x)")
                assert False, "read-only connection allowed a write"
            except sqlite3.OperationalError as e:
                assert "readonly" in str(e).lower() or "read-only" in str(e).lower()
    finally:
        conn.close()


def test_get_db_busy_timeout_set(tmp_path):
    """get_db connections carry an explicit bounded busy_timeout."""
    db = str(tmp_path / "data" / "ebook_patterns.db")
    conn = pattern_db.get_db(db)
    try:
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert bt == pattern_db._BUSY_TIMEOUT_MS
    finally:
        conn.close()


def test_recommended_strategy_missing_db_returns_default_without_creating(tmp_path):
    """On a missing DB, the lookup returns the default and does NOT create the file."""
    db = tmp_path / "data" / "ebook_patterns.db"
    res = pattern_db.get_recommended_strategy(filename="x.pdf", db_path=str(db))
    assert res["source"] == "default"
    assert not db.exists(), "read path must not create the DB as a side effect"


def test_recommended_strategy_nonblocking_under_writer(tmp_path):
    """Regression: the read path returns promptly while a writer holds the lock.

    Before the fix the lookup went through get_db (write DDL on connect) and
    blocked ~5s+ behind the writer. After the fix it uses a read-only WAL
    connection and returns near-instantly.
    """
    db = str(tmp_path / "data" / "ebook_patterns.db")
    conn = pattern_db.get_db(db)
    conn.execute("INSERT INTO books(filename, format) VALUES ('seed.pdf','pdf')")
    conn.commit()
    conn.close()

    holder_py = tmp_path / "holder.py"
    holder_py.write_text(textwrap.dedent(f'''
        import sqlite3, time
        c = sqlite3.connect(r"{db}", timeout=30)
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT INTO books(filename, format) VALUES ('lock.pdf','pdf')")
        print("LOCKED", flush=True)
        time.sleep(15)
    '''))
    proc = subprocess.Popen([sys.executable, str(holder_py)],
                            stdout=subprocess.PIPE, text=True)
    try:
        # wait until the holder confirms it holds the write lock
        assert proc.stdout.readline().strip() == "LOCKED"
        t0 = time.time()
        res = pattern_db.get_recommended_strategy(
            source_file_path="seed.pdf", format="pdf", db_path=db)
        elapsed = time.time() - t0
        assert elapsed < 2.0, f"read path blocked {elapsed:.1f}s under a writer (EB-369 hang)"
        assert isinstance(res, dict) and "source" in res
    finally:
        proc.kill()
        proc.wait()
