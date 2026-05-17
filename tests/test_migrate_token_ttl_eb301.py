"""Tests for tools/migrate_token_ttl_eb301.py.

Covers the EB-301 deploy-time migration that extends unexpired 7-day-TTL tokens
to the new 30-day window.

Required behavior:
- Unexpired 7-day token is extended to created_at + 30 days
- Already-extended (30-day) token is left alone (idempotent)
- Already-expired token is NOT resurrected
- --dry-run does not modify the DB
- Missing DB path returns exit code 1
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from web_service.token_store import init_db, mint_tokens_if_absent

_MIGRATE_SCRIPT = (
    Path(__file__).resolve().parent.parent / "tools" / "migrate_token_ttl_eb301.py"
)


def _run(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_MIGRATE_SCRIPT), "--db-path", str(db_path), *args],
        capture_output=True,
        text=True,
    )


def _set_expiry(db_path: Path, pack_id: str, created_at: int, expires_at: int) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE tokens SET created_at=?, expires_at=? WHERE pack_id=?",
        (created_at, expires_at, pack_id),
    )
    conn.commit()
    conn.close()


def _read_expiry(db_path: Path, pack_id: str) -> tuple[int, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT created_at, expires_at FROM tokens WHERE pack_id=? LIMIT 1",
        (pack_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    return row["created_at"], row["expires_at"]


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "migrate.db"
    init_db(db_path)
    return db_path


class TestMigrateTokenTTL:
    def test_extends_unexpired_7day_token_to_30_days(self, db):
        mint_tokens_if_absent("cs_legacy_7d", 1, "pi_7d", db_path=db)
        now = int(time.time())
        # Simulate the old contract: created 1 day ago, expires 6 days from now (7-day TTL).
        created = now - 24 * 3600
        old_expires = created + 7 * 24 * 3600
        _set_expiry(db, "cs_legacy_7d", created, old_expires)

        result = _run(db_path=db)
        assert result.returncode == 0, result.stderr

        new_created, new_expires = _read_expiry(db, "cs_legacy_7d")
        assert new_created == created
        assert new_expires == created + 30 * 24 * 3600

    def test_does_not_resurrect_already_expired_token(self, db):
        mint_tokens_if_absent("cs_expired", 1, "pi_expired", db_path=db)
        now = int(time.time())
        # Created 10 days ago, expired 3 days ago (under old 7-day TTL).
        created = now - 10 * 24 * 3600
        expired_at = now - 3 * 24 * 3600
        _set_expiry(db, "cs_expired", created, expired_at)

        result = _run(db_path=db)
        assert result.returncode == 0, result.stderr

        _, new_expires = _read_expiry(db, "cs_expired")
        assert new_expires == expired_at, "expired token must not be resurrected"

    def test_idempotent_second_run_no_op(self, db):
        mint_tokens_if_absent("cs_idem", 1, "pi_idem", db_path=db)
        now = int(time.time())
        created = now - 24 * 3600
        old_expires = created + 7 * 24 * 3600
        _set_expiry(db, "cs_idem", created, old_expires)

        first = _run(db_path=db)
        assert first.returncode == 0
        _, expires_after_first = _read_expiry(db, "cs_idem")
        assert expires_after_first == created + 30 * 24 * 3600

        # Re-run — must not shrink, must not extend further.
        second = _run(db_path=db)
        assert second.returncode == 0
        _, expires_after_second = _read_expiry(db, "cs_idem")
        assert expires_after_second == expires_after_first

    def test_does_not_shrink_already_30day_token(self, db):
        mint_tokens_if_absent("cs_new", 1, "pi_new", db_path=db)
        # mint_tokens_if_absent now defaults to 30-day TTL — read & confirm.
        created_before, expires_before = _read_expiry(db, "cs_new")
        assert expires_before == created_before + 30 * 24 * 3600

        result = _run(db_path=db)
        assert result.returncode == 0

        created_after, expires_after = _read_expiry(db, "cs_new")
        assert created_after == created_before
        assert expires_after == expires_before

    def test_dry_run_does_not_modify(self, db):
        mint_tokens_if_absent("cs_dry", 1, "pi_dry", db_path=db)
        now = int(time.time())
        created = now - 24 * 3600
        old_expires = created + 7 * 24 * 3600
        _set_expiry(db, "cs_dry", created, old_expires)

        result = _run("--dry-run", db_path=db)
        assert result.returncode == 0
        # Reporting goes to stderr; the script logs the planned change there.
        assert "1" in result.stderr or "actually-changing" in result.stderr

        _, expires_after = _read_expiry(db, "cs_dry")
        assert expires_after == old_expires, "--dry-run must not write"

    def test_missing_db_returns_exit_code_1(self, tmp_path):
        missing = tmp_path / "does_not_exist.db"
        result = _run(db_path=missing)
        assert result.returncode == 1
