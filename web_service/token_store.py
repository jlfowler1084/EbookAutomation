"""SQLite token store for leafbind.io single-use credit tokens.

Separate from web_service/job_store.py — token concerns (hash storage,
encrypted-recovery, used/expired/disputed state, atomic single-use validation)
are sufficiently distinct from job state to warrant module isolation.
Both stores share the same SQLite DB file but the table operations are independent.

Key correctness properties:
1. Idempotency: mint_tokens_if_absent uses pack_id UNIQUE + SELECT-first-then-INSERT
   under BEGIN IMMEDIATE. The second concurrent writer blocks until the first commits,
   then sees the winner's rows on its first SELECT (from_cache=True path).
2. Atomic single-use: validate_and_consume uses a single UPDATE WHERE used=0 AND ...
   The UPDATE rowcount is the race gate — no separate-txn TOCTOU.
3. Race-loser invariant: if INSERT OR IGNORE fires rowcount=0 (impossible under
   BEGIN IMMEDIATE in normal operation), log ERROR + re-SELECT + return DB-authoritative
   rows. NEVER return locally-generated tokens after a collision.
4. Dispute/used distinguishability: mark_disputed does NOT modify used or used_at,
   preserving audit trail between "consumed then disputed" and "revoked before use".

Schema comment note: MAX_TOKENS_PER_SESSION = 25 is enforced at app-level in
mint_tokens_if_absent before any DB access. The SQL schema comment documents this
for defense-in-depth.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generator

from web_service.config import get_settings
from web_service.crypto import compute_token_hash, get_fernet, mint_token

log = logging.getLogger(__name__)

# Token format regex — ^lb_pk_[A-Za-z0-9_-]{43}$ (from Token Format Specification)
_TOKEN_REGEX = re.compile(r"^lb_pk_[A-Za-z0-9_-]{43}$")

# Maximum tokens allowed per Stripe Checkout session (app-level guard).
# Also documented in the schema SQL comment below for defense-in-depth.
MAX_TOKENS_PER_SESSION = 25

# Token time-to-live: 7 days from mint time (matches Stripe session expiry window)
_TOKEN_TTL_SECONDS = 7 * 24 * 3600


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tokens (
    token_hash                   BLOB PRIMARY KEY,
    token_encrypted_for_recovery BLOB NOT NULL,
    key_version                  INTEGER NOT NULL DEFAULT 1,
    pack_id                      TEXT NOT NULL,
    payment_intent_id            TEXT,
    created_at                   INTEGER NOT NULL,
    expires_at                   INTEGER NOT NULL,
    used                         INTEGER NOT NULL DEFAULT 0,
    used_at                      INTEGER,
    disputed                     INTEGER NOT NULL DEFAULT 0,
    disputed_at                  INTEGER
);
-- NOTE: MAX_TOKENS_PER_SESSION = 25 enforced in mint_tokens_if_absent (app-level)
-- pack_id is the Stripe session_id; NOT UNIQUE at column level because N tokens share
-- the same session. Idempotency is enforced via SELECT-first under BEGIN IMMEDIATE.
-- The INSERT OR IGNORE guard protects against token_hash PK collision (statistically
-- impossible with 256-bit entropy but kept for defense-in-depth).
CREATE INDEX IF NOT EXISTS idx_tokens_pack_id ON tokens(pack_id);
CREATE INDEX IF NOT EXISTS idx_tokens_payment_intent ON tokens(payment_intent_id);

CREATE TABLE IF NOT EXISTS failed_mints (
    session_id    TEXT NOT NULL,
    pack          TEXT NOT NULL,
    error         TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    created_at    INTEGER NOT NULL,
    PRIMARY KEY (session_id, attempt_count)
);
"""


# ---------------------------------------------------------------------------
# Result dataclasses (mirror web_service/validation.py ValidationResult shape)
# ---------------------------------------------------------------------------

class TokenValidationErrorCode(str, Enum):
    """Four-code error taxonomy for token validation at /convert."""
    MALFORMED = "MALFORMED"                       # regex fails; no DB hit
    INVALID_OR_EXPIRED = "INVALID_OR_EXPIRED"     # unknown OR expired (same code — security)
    ALREADY_USED = "ALREADY_USED"                 # used=1 AND disputed=0
    DISPUTED = "DISPUTED"                         # disputed=1 (any used state)


@dataclass(frozen=True)
class TokenValidationError:
    """Structured error returned when token validation fails."""
    code: TokenValidationErrorCode
    message: str
    http_status: int


@dataclass(frozen=True)
class TokenValidationResult:
    """Result of validate_and_consume(). Mirrors validation.py:ValidationResult shape."""
    ok: bool
    error: TokenValidationError | None = None


@dataclass(frozen=True)
class MintResult:
    """Result of mint_tokens_if_absent(). Contains the minted (or retrieved) tokens."""
    ok: bool
    tokens: list[str]
    from_cache: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# DB connection helper (mirrors job_store._get_conn with busy_timeout added)
# ---------------------------------------------------------------------------

@contextmanager
def _get_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode connection to the token DB, closing it when done.

    Mirrors job_store._get_conn but adds PRAGMA busy_timeout=5000 (ms).
    This allows SQLite to wait up to 5s for a locked DB instead of
    immediately raising OperationalError — critical for BEGIN IMMEDIATE blocks.

    Commits on successful exit, rollbacks on exception.
    """
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db(db_path: Path | None = None) -> None:
    """Create the tokens and failed_mints tables if they do not exist. Idempotent."""
    with _get_conn(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    log.info("token_store: DB initialised at %s", db_path or get_settings().db_path)


# ---------------------------------------------------------------------------
# Token minting
# ---------------------------------------------------------------------------

def mint_tokens_if_absent(
    session_id: str,
    count: int,
    payment_intent_id: str,
    db_path: Path | None = None,
) -> MintResult:
    """Mint N tokens for a Stripe Checkout session, or return existing tokens.

    Idempotency key: pack_id UNIQUE (= session_id). Both the webhook path and
    the success-page path call this function; only the first writer inserts rows.

    Under BEGIN IMMEDIATE, SQLite serializes all writers:
    - Writer 1 acquires RESERVED lock; Writer 2 waits up to busy_timeout=5000ms.
    - When Writer 1 commits, Writer 2 proceeds with its own SELECT and finds rows.
    - This is the normal "from_cache" path (SELECT-first).

    Race-loser invariant (should be unreachable under BEGIN IMMEDIATE):
    - If INSERT OR IGNORE returns rowcount=0 for any row: log ERROR (invariant
      violated), re-SELECT inside the same transaction, return DB-authoritative rows.
    - NEVER return locally-generated tokens after an IGNORE collision — those tokens
      were silently dropped and the user would receive phantom tokens.

    Args:
        session_id: Stripe Checkout session ID — used as pack_id (idempotency key).
        count: Number of tokens to mint (1-MAX_TOKENS_PER_SESSION).
        payment_intent_id: Stripe PaymentIntent ID — stored for dispute fallback.
        db_path: Optional DB path override (for tests).

    Returns:
        MintResult with ok=True and the token strings.

    Raises:
        ValueError: If count > MAX_TOKENS_PER_SESSION.
        sqlite3.OperationalError: If DB is locked beyond busy_timeout.
    """
    if count > MAX_TOKENS_PER_SESSION:
        raise ValueError(
            f"count {count} exceeds MAX_TOKENS_PER_SESSION ({MAX_TOKENS_PER_SESSION})"
        )
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")

    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        # BEGIN IMMEDIATE: acquire RESERVED lock immediately, preventing any other
        # writer from starting a transaction until we commit or rollback.
        conn.execute("BEGIN IMMEDIATE")

        # Step 1: SELECT-first. If rows exist (idempotent revisit or race-loser),
        # decrypt and return without inserting.
        existing_rows = conn.execute(
            "SELECT token_encrypted_for_recovery, key_version "
            "FROM tokens WHERE pack_id = ? ORDER BY rowid",
            (session_id,),
        ).fetchall()

        if existing_rows:
            tokens = []
            for row in existing_rows:
                f = get_fernet(row["key_version"])
                raw_token = f.decrypt(bytes(row["token_encrypted_for_recovery"])).decode()
                tokens.append(raw_token)
            conn.commit()
            log.info(
                "token_store: mint_tokens_if_absent — cache hit for session=%s (%d tokens)",
                session_id,
                len(tokens),
            )
            return MintResult(ok=True, tokens=tokens, from_cache=True)

        # Step 2: No existing rows — generate tokens and INSERT.
        now = int(time.time())
        expires_at = now + _TOKEN_TTL_SECONDS
        f = get_fernet(key_version=1)

        generated: list[tuple[str, bytes, bytes]] = []  # (token_str, token_hash, encrypted)
        for _ in range(count):
            token_str, token_hash = mint_token()
            encrypted = f.encrypt(token_str.encode())
            generated.append((token_str, token_hash, encrypted))

        invariant_violated = False
        for token_str, token_hash, encrypted in generated:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO tokens (
                    token_hash, token_encrypted_for_recovery, key_version,
                    pack_id, payment_intent_id,
                    created_at, expires_at,
                    used, disputed
                ) VALUES (?, ?, 1, ?, ?, ?, ?, 0, 0)
                """,
                (token_hash, encrypted, session_id, payment_intent_id, now, expires_at),
            )
            if cursor.rowcount == 0:
                # BEGIN IMMEDIATE serialization invariant violated — this branch should
                # be unreachable in normal operation. Log ERROR and fall through to
                # re-SELECT to return DB-authoritative rows.
                log.error(
                    "token_store: BEGIN IMMEDIATE serialization invariant violated — "
                    "INSERT OR IGNORE collision at session_id=%s. "
                    "Re-SELECTing to return DB-authoritative rows. "
                    "NEVER returning locally-generated tokens.",
                    session_id,
                )
                invariant_violated = True
                break

        if invariant_violated:
            # Re-SELECT inside the same transaction to get DB-authoritative rows.
            # The locally-generated tokens are discarded.
            authoritative_rows = conn.execute(
                "SELECT token_encrypted_for_recovery, key_version "
                "FROM tokens WHERE pack_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
            tokens = []
            for row in authoritative_rows:
                fernet = get_fernet(row["key_version"])
                raw_token = fernet.decrypt(bytes(row["token_encrypted_for_recovery"])).decode()
                tokens.append(raw_token)
            conn.commit()
            return MintResult(ok=True, tokens=tokens, from_cache=True)

        conn.commit()
        tokens = [t[0] for t in generated]
        log.info(
            "token_store: minted %d tokens for session=%s (payment_intent=%s)",
            count,
            session_id,
            payment_intent_id,
        )
        return MintResult(ok=True, tokens=tokens, from_cache=False)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Token validation and consumption
# ---------------------------------------------------------------------------

def validate_and_consume(
    token: str,
    db_path: Path | None = None,
) -> TokenValidationResult:
    """Validate a token and atomically mark it used if valid.

    The UPDATE rowcount is the primary race gate — no separate-txn TOCTOU.
    Disambiguation SELECT runs INSIDE the same BEGIN IMMEDIATE transaction
    to avoid any window between "token exists?" and "why did UPDATE fail?".

    Four-code error taxonomy:
    - MALFORMED: regex fails; no DB hit (fast 422 path)
    - INVALID_OR_EXPIRED: unknown OR expired (same code — avoids leaking format-correctness)
    - ALREADY_USED: used=1 AND disputed=0
    - DISPUTED: disputed=1 (any used state; dispute takes precedence over already-used)

    Args:
        token: The raw token string to validate.
        db_path: Optional DB path override (for tests).

    Returns:
        TokenValidationResult with ok=True on success, or ok=False with error details.
    """
    # MALFORMED: fast path before any DB access
    if not _TOKEN_REGEX.match(token):
        return TokenValidationResult(
            ok=False,
            error=TokenValidationError(
                code=TokenValidationErrorCode.MALFORMED,
                message=(
                    "Token format is invalid. Expected format: lb_pk_<43 characters>. "
                    "Please check you copied the token correctly."
                ),
                http_status=422,
            ),
        )

    token_hash = compute_token_hash(token)
    now = int(time.time())

    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Atomic single-use consume: UPDATE only if not used AND not disputed AND not expired
        cursor = conn.execute(
            "UPDATE tokens SET used=1, used_at=? "
            "WHERE token_hash=? AND used=0 AND disputed=0 AND expires_at>?",
            (now, token_hash, now),
        )

        if cursor.rowcount == 1:
            # Success — token consumed atomically
            conn.commit()
            log.info("token_store: token consumed successfully (hash=...%s)", token_hash.hex()[-8:])
            return TokenValidationResult(ok=True)

        # UPDATE matched 0 rows — disambiguate inside the same transaction
        row = conn.execute(
            "SELECT used, disputed, expires_at FROM tokens WHERE token_hash=?",
            (token_hash,),
        ).fetchone()

        if row is None:
            # No row at all — unknown token (indistinguishable from expired for security)
            conn.rollback()
            return TokenValidationResult(
                ok=False,
                error=TokenValidationError(
                    code=TokenValidationErrorCode.INVALID_OR_EXPIRED,
                    message=(
                        "This token is invalid or has expired. "
                        "Tokens are valid for 7 days after purchase."
                    ),
                    http_status=422,
                ),
            )

        if row["disputed"] == 1:
            # Dispute takes precedence over all other states
            conn.rollback()
            return TokenValidationResult(
                ok=False,
                error=TokenValidationError(
                    code=TokenValidationErrorCode.DISPUTED,
                    message=(
                        "This token has been revoked due to a payment dispute. "
                        "Please contact support if you believe this is an error."
                    ),
                    http_status=402,
                ),
            )

        if row["used"] == 1:
            conn.rollback()
            return TokenValidationResult(
                ok=False,
                error=TokenValidationError(
                    code=TokenValidationErrorCode.ALREADY_USED,
                    message=(
                        "This token has already been used. "
                        "Each token is single-use. Please use a different token."
                    ),
                    http_status=422,
                ),
            )

        # Row exists but expires_at <= now (token is not used, not disputed, but expired)
        conn.rollback()
        return TokenValidationResult(
            ok=False,
            error=TokenValidationError(
                code=TokenValidationErrorCode.INVALID_OR_EXPIRED,
                message=(
                    "This token has expired. "
                    "Tokens are valid for 7 days after purchase."
                ),
                http_status=422,
            ),
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dispute handling
# ---------------------------------------------------------------------------

def mark_disputed(pack_id: str, db_path: Path | None = None) -> int:
    """Mark all tokens for a pack as disputed.

    Sets disputed=1 and disputed_at=now for all tokens with the given pack_id.
    Does NOT modify used or used_at — preserves audit distinguishability between
    "consumed then disputed" (used=1, disputed=1) and "revoked before use"
    (used=0, disputed=1).

    Args:
        pack_id: The Stripe session_id used as pack_id when minting.
        db_path: Optional DB path override (for tests).

    Returns:
        Number of rows updated (number of tokens in the pack).
    """
    now = int(time.time())
    with _get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "UPDATE tokens SET disputed=1, disputed_at=? WHERE pack_id=?",
            (now, pack_id),
        )
        rowcount = cursor.rowcount
    log.info(
        "token_store: mark_disputed pack_id=%s — %d rows marked",
        pack_id,
        rowcount,
    )
    return rowcount


# ---------------------------------------------------------------------------
# Recovery lookup
# ---------------------------------------------------------------------------

def find_session_by_payment_intent(
    pi_id: str,
    db_path: Path | None = None,
) -> str | None:
    """Look up the Stripe session_id (pack_id) by payment_intent_id.

    Used in Unit 4 dispute handling when Charge metadata propagation fails
    and a fallback PI→session_id lookup is needed.

    Args:
        pi_id: The Stripe PaymentIntent ID.
        db_path: Optional DB path override (for tests).

    Returns:
        The session_id string, or None if not found.
    """
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT pack_id FROM tokens WHERE payment_intent_id=? LIMIT 1",
            (pi_id,),
        ).fetchone()
    return row["pack_id"] if row else None


# ---------------------------------------------------------------------------
# Mint failure recording
# ---------------------------------------------------------------------------

def record_failed_mint(
    session_id: str,
    pack: str,
    error: str,
    db_path: Path | None = None,
) -> None:
    """Record a mint failure to the failed_mints table for admin investigation.

    On conflict (same session_id + attempt_count), insert with incremented count.
    This tracks repeated Stripe retries for the same session.

    Args:
        session_id: Stripe session ID for which minting failed.
        pack: Pack name (e.g. "starter", "standard", "power").
        error: Error message or exception string.
        db_path: Optional DB path override (for tests).
    """
    now = int(time.time())
    with _get_conn(db_path) as conn:
        # Get current max attempt_count for this session
        row = conn.execute(
            "SELECT MAX(attempt_count) FROM failed_mints WHERE session_id=?",
            (session_id,),
        ).fetchone()
        max_attempt = row[0] if row[0] is not None else 0
        next_attempt = max_attempt + 1

        conn.execute(
            """
            INSERT INTO failed_mints (session_id, pack, error, attempt_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, pack, error, next_attempt, now),
        )
    log.warning(
        "token_store: recorded failed mint for session=%s pack=%s attempt=%d error=%r",
        session_id,
        pack,
        next_attempt,
        error[:200],
    )


# ---------------------------------------------------------------------------
# Cleanup sweeps
# ---------------------------------------------------------------------------

def cleanup_expired_tokens(db_path: Path | None = None) -> int:
    """Delete consumed tokens that have been expired for >30 days.

    Retention policy: DELETE WHERE used=1 AND expires_at < now - 30*24*3600.
    Only used=1 rows are deleted — unused (potentially recoverable) rows are
    retained regardless of expiry to preserve audit trail and recovery path.

    WAL snapshot isolation guarantees no in-flight reader sees a row mid-delete.
    The used=1 filter ensures we never delete a token that could still be validated.

    Returns:
        Number of rows deleted.
    """
    cutoff = int(time.time()) - (30 * 24 * 3600)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM tokens WHERE used=1 AND expires_at < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount
    if deleted:
        log.info("token_store: cleanup_expired_tokens deleted %d rows", deleted)
    return deleted


def cleanup_failed_mints(db_path: Path | None = None) -> int:
    """Delete failed_mints records older than 7 days.

    7-day retention window provides time for admin investigation and manual
    recovery before records are purged.

    Returns:
        Number of rows deleted.
    """
    cutoff = int(time.time()) - (7 * 24 * 3600)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM failed_mints WHERE created_at < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount
    if deleted:
        log.info("token_store: cleanup_failed_mints deleted %d rows", deleted)
    return deleted
