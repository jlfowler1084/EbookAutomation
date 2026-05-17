"""One-shot migration: extend unexpired tokens from 7-day TTL to 30-day TTL.

Run once after deploying EB-301 (token TTL widening). Idempotent — safe to re-run
because the UPDATE sets `expires_at = created_at + 30*24*3600`, which is a fixed
value for any given row.

Only affects rows where `expires_at > NOW()` — already-expired tokens are left
alone (no resurrection). Existing customers who bought in the 7-day window get
the new 30-day expiry honored.

Usage:
    py -3.12 tools/migrate_token_ttl_eb301.py             # apply against default DB
    py -3.12 tools/migrate_token_ttl_eb301.py --dry-run   # report only, no UPDATE
    py -3.12 tools/migrate_token_ttl_eb301.py --db-path /var/lib/leafbind/web_service.db

Exit codes:
    0 — migration applied (or no-op if nothing to extend)
    1 — DB file missing or schema not initialised
    2 — unexpected SQLite error
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

# Match the new value in web_service/token_store.py — kept as a literal here to
# avoid an import-time dependency on the package layout (the migration must be
# runnable from a standalone deploy that may not have the full venv installed).
NEW_TTL_SECONDS = 30 * 24 * 3600

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s migrate_token_ttl_eb301: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def _resolve_db_path(override: str | None) -> Path:
    if override:
        return Path(override)
    # Late import — only if no override was passed. Lets the script run from a
    # repo checkout without forcing a full venv install on a minimal deploy host.
    try:
        from web_service.config import get_settings
    except ImportError as exc:
        log.error(
            "could not import web_service.config to discover default db_path: %s. "
            "Pass --db-path explicitly.",
            exc,
        )
        sys.exit(1)
    return get_settings().db_path


def migrate(db_path: Path, dry_run: bool) -> int:
    if not db_path.exists():
        log.error("db_path does not exist: %s", db_path)
        return 1

    now = int(time.time())
    new_expires_expr = f"created_at + {NEW_TTL_SECONDS}"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Confirm schema exists before doing anything.
        schema = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tokens'"
        ).fetchone()
        if schema is None:
            log.error("tokens table not found in %s — schema not initialised", db_path)
            return 1

        # Report current state.
        total = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        unexpired = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE expires_at > ?", (now,)
        ).fetchone()[0]
        would_extend = conn.execute(
            f"SELECT COUNT(*) FROM tokens "
            f"WHERE expires_at > ? AND expires_at < {new_expires_expr}",
            (now,),
        ).fetchone()[0]

        log.info("DB: %s", db_path)
        log.info("total rows in tokens table: %d", total)
        log.info("unexpired rows (expires_at > now): %d", unexpired)
        log.info(
            "rows where new TTL is strictly longer than current expires_at "
            "(actually-changing rows): %d",
            would_extend,
        )

        if would_extend == 0:
            log.info("nothing to extend — migration is a no-op on this DB")
            return 0

        if dry_run:
            log.info("--dry-run: skipping UPDATE")
            return 0

        # Apply. Only widen — never shrink. The `expires_at < created_at + NEW_TTL`
        # guard makes the UPDATE strictly monotonic on `expires_at`.
        cursor = conn.execute(
            f"UPDATE tokens "
            f"SET expires_at = {new_expires_expr} "
            f"WHERE expires_at > ? AND expires_at < {new_expires_expr}",
            (now,),
        )
        conn.commit()
        log.info("UPDATE applied — %d rows extended", cursor.rowcount)
        return 0

    except sqlite3.Error as exc:
        log.error("SQLite error: %s", exc)
        conn.rollback()
        return 2
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override the DB path. Defaults to web_service.config.get_settings().db_path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without applying the UPDATE.",
    )
    args = parser.parse_args()
    return migrate(_resolve_db_path(args.db_path), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
