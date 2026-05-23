# EB-332 — Premium KFX Refund-on-Failure + VM Wine Toolchain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop charging customers for failed premium KFX conversions (refund-on-failure), and make the VM actually produce KFX (install Wine + Kindle Previewer headless, reproducibly).

**Architecture:** Two independent streams on two worktree branches. **Stream B** (Python) brings top-level premium `/convert` to parity with `/reconvert` by persisting `token_hash` on the job row, so the *already-wired* `dispatch_job` failure-refund path fires; plus a consume→setup-failure refund and clean per-flow telemetry. **Stream A** (VM ops + deploy) installs Wine + Kindle Previewer 3 headless on `claude-dev-01`, reinstalls/pins the Calibre KFX Output plugin, grants the hardened systemd unit the runtime paths/env it needs, and freezes the working steps into a reproducible installer + a cheap routine-deploy verifier.

**Tech Stack:** Python 3.12, FastAPI, SQLite (WAL), pytest; Bash, Wine (WineHQ), Amazon Kindle Previewer 3, Calibre `ebook-convert`/`calibre-customize`, `xvfb-run`, systemd, Hetzner `hcloud`.

**Spec:** `docs/superpowers/specs/2026-05-23-eb-332-premium-kfx-refund-and-vm-toolchain-design.md`

---

## Parallelization Map

| Stream | Branch | Files touched | Depends on | Merge order |
|---|---|---|---|---|
| B (code) | `fix/EB-332-premium-refund-on-failure` (from `master`) | `web_service/routes/convert.py`, `web_service/job_queue.py`, `web_service/recovery_events_store.py`, `tests/test_web_convert_refund.py` (new), `tests/test_web_recovery_events_store.py` | none | **first** |
| A (VM/deploy) | `fix/EB-332-vm-kfx-toolchain` (from **EB-331's deploy-path branch**, NOT master) | `deploy/install-kfx-toolchain.sh` (new), `deploy/verify-kfx-toolchain.sh` (new), `deploy/web_service.service`, `deploy/README.md` | EB-331 path reconciliation (In Progress) + explicit VM go-ahead | after B + after EB-331 |

No file overlap between streams. Stream B is fully testable locally and merges independently of the VM.

---

# STREAM B — Refund-on-failure (code)

> Create the worktree first via `superpowers:using-git-worktrees`: branch `fix/EB-332-premium-refund-on-failure` from `master`.

## Task B1: Whitelist the `premium_refund_applied` telemetry event

**Files:**
- Modify: `web_service/recovery_events_store.py:64-88` (`_VALID_EVENT_TYPES`)
- Test: `tests/test_web_recovery_events_store.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web_recovery_events_store.py`:

```python
def test_premium_refund_applied_is_accepted(tmp_path):
    """premium_refund_applied is a valid event type (EB-332) and writes a row."""
    import web_service.recovery_events_store as res

    db = tmp_path / "events.db"
    res.init_db(db)
    res.log_event(
        "premium_refund_applied",
        details={"job_id": "j1", "reason": "pipeline_failed", "refunded": True},
        db_path=db,
    )
    assert res.count_events_since("premium_refund_applied", 0, db_path=db) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_web_recovery_events_store.py::test_premium_refund_applied_is_accepted -v`
Expected: FAIL — `count_events_since(...) == 0` (event rejected by whitelist, no row written).

- [ ] **Step 3: Add the event to the whitelist**

In `web_service/recovery_events_store.py`, inside the `_VALID_EVENT_TYPES` frozenset, after the `"reconvert_refund_applied",` line add:

```python
    # EB-332: refund applied to a failed top-level premium /convert job
    # (distinct from reconvert_refund_applied so dashboards can separate
    # first-conversion refunds from re-convert refunds).
    "premium_refund_applied",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest tests/test_web_recovery_events_store.py::test_premium_refund_applied_is_accepted -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web_service/recovery_events_store.py tests/test_web_recovery_events_store.py
git commit -m "feat(EB-332): whitelist premium_refund_applied telemetry event"
```

## Task B2: Generalize the dispatch-failure refund helper for top-level jobs

The helper `_maybe_refund_failed_child` already refunds whenever `job["token_hash"]`
is set (it does NOT require `parent_job_id`). It only needs: (a) a name that
reflects it now serves top-level jobs too, (b) a per-flow event name, and
(c) details/reasons that read correctly for a top-level upload.

**Files:**
- Modify: `web_service/job_queue.py:88-194`
- Test: `tests/test_web_convert_refund.py` (created in B3 — this task is the implementation B3's test drives; commit them together if executing inline)

- [ ] **Step 1: Rename the helper and its two call sites**

In `web_service/job_queue.py`, rename `_maybe_refund_failed_child` →
`_maybe_refund_failed_job`. Update the two call sites:

- Line ~91 (unhandled-exception path) — keep reason `"dispatch_exception"`:
```python
            await _maybe_refund_failed_job(job, reason="dispatch_exception")
```
- Line ~107 (clean `result.success is False` path) — change reason from
  `"child_job_failed"` to the neutral `"pipeline_failed"`:
```python
            await _maybe_refund_failed_job(job, reason="pipeline_failed")
```

- [ ] **Step 2: Rewrite the helper body — per-flow event name + neutral details**

Replace the telemetry block at the end of the helper (the
`recovery_events_store.log_event("reconvert_refund_applied", ...)` call) so the
event type and details depend on whether the job is a re-convert child:

```python
    parent_job_id = job.get("parent_job_id")
    event_type = "reconvert_refund_applied" if parent_job_id else "premium_refund_applied"
    details = {
        "job_id": job["job_id"],
        "reason": reason,
        "refunded": refund.refunded,
        "ledgered": refund.ledgered,
        "refund_id": refund.refund_id,
    }
    if parent_job_id:
        details["parent_job_id"] = parent_job_id
    try:
        recovery_events_store.log_event(event_type, details=details)
    except Exception:
        # Telemetry must never block the dispatcher's return path.
        log.exception("Telemetry log_event failed for refund on job %s", job["job_id"])
```

Also update the helper docstring: it now refunds **any** failed premium job
carrying a `token_hash` (top-level `/convert` or re-convert child); the
`token_hash is None` short-circuit still protects every free-tier failure.

- [ ] **Step 3: Run the existing reconvert refund tests to confirm no regression**

Run: `py -3.12 -m pytest tests/test_web_reconvert.py -v`
Expected: PASS — `TestReconvertRefundOnChildFailure` still refunds children and
still skips free children (child jobs have `parent_job_id`, so they keep emitting
`reconvert_refund_applied`).

- [ ] **Step 4: Commit**

```bash
git add web_service/job_queue.py
git commit -m "refactor(EB-332): generalize dispatch refund helper to top-level premium jobs"
```

## Task B3: Persist token_hash on top-level premium `/convert` + refund the failure path

**Files:**
- Modify: `web_service/routes/convert.py`
- Test: `tests/test_web_convert_refund.py` (Create)

- [ ] **Step 1: Write the failing test (refund on pipeline failure)**

Create `tests/test_web_convert_refund.py`. The fixtures mirror
`tests/test_web_reconvert.py` (capture the real `dispatch_job` at import time so
the route's mock doesn't shadow it):

```python
"""EB-332: a failed top-level premium /convert must refund the consumed token.

Mirrors tests/test_web_reconvert.py's refund integration test, but for the
first-conversion path (no parent_job_id). The fix persists token_hash on the
job row in convert.py so job_queue.dispatch_job's existing failure-refund hook
fires for top-level uploads too.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.job_queue import dispatch_job as _real_dispatch_job  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings():
    from web_service.config import reset_settings
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
    cfg = {"paths": {"calibre": "/usr/bin/ebook-convert", "python": "/usr/bin/python3", "kindle": "output/kindle"}}
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp_path / "data").mkdir()
    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    import importlib
    import web_service.job_store as js
    import web_service.main as main_mod
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)
    importlib.reload(main_mod)

    with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()), \
         patch("web_service.job_queue.init_queue"), \
         patch("web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()):
        with TestClient(main_mod.app) as tc:
            yield tc, settings.db_path, settings


def _premium_kfx_post(tc, db_path, *, session_id, pi_id):
    """Mint a token, POST a premium kfx /convert, return (job_id, token)."""
    import web_service.token_store as ts
    ts.init_db(db_path)
    mint = ts.mint_tokens_if_absent(session_id=session_id, count=1, payment_intent_id=pi_id, db_path=db_path)
    assert mint.ok
    token = mint.tokens[0]
    files = {"file": ("book.pdf", b"%PDF-1.4\n" + b"\x00" * 4000, "application/pdf")}
    resp = tc.post("/convert", files=files, data={"output_format": "kfx", "tier": "premium", "token": token})
    assert resp.status_code == 202, resp.text
    return resp.json()["job_id"], token


@pytest.mark.asyncio
async def test_failed_premium_convert_refunds_token(client, monkeypatch):
    """A top-level premium kfx job that fails in the pipeline refunds the token."""
    import web_service.job_store as js
    from web_service import job_queue, pipeline_runner

    tc, db_path, settings = client
    job_id, _ = _premium_kfx_post(tc, db_path, session_id="cs_eb332_refund", pi_id="pi_eb332_refund")

    # token_hash must be persisted on the top-level job (this is the fix).
    assert js.get_job(job_id)["token_hash"] is not None, "convert.py must persist token_hash"

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT used FROM tokens WHERE pack_id=?", ("cs_eb332_refund",)).fetchone()[0] == 1
    conn.close()

    sem_executor = ThreadPoolExecutor(max_workers=1)
    bill_executor = ThreadPoolExecutor(max_workers=1)
    try:
        monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
        monkeypatch.setattr(job_queue, "_executor", sem_executor)
        monkeypatch.setattr(job_queue, "billing_executor", bill_executor)
        monkeypatch.setattr(
            job_queue, "_run_job",
            lambda job: pipeline_runner.RunResult(success=False, output_path="", output_size=0, error_message="forced kfx failure"),
        )
        await _real_dispatch_job(job_id)
    finally:
        sem_executor.shutdown(wait=False)
        bill_executor.shutdown(wait=False)

    assert js.get_job(job_id)["status"] == "failed"
    conn = sqlite3.connect(str(db_path))
    used_after = conn.execute("SELECT used FROM tokens WHERE pack_id=?", ("cs_eb332_refund",)).fetchone()[0]
    ledger = conn.execute("SELECT refund_reason FROM refund_ledger WHERE failed_job_id=?", (job_id,)).fetchall()
    events = conn.execute("SELECT COUNT(*) FROM recovery_events WHERE event_type='premium_refund_applied'").fetchone()[0]
    conn.close()

    assert used_after == 0, "token must be refunded after a top-level premium failure"
    assert [r[0] for r in ledger] == ["pipeline_failed"], f"expected one pipeline_failed ledger row, got {ledger}"
    assert events == 1, "a premium_refund_applied telemetry event must be emitted (not reconvert_refund_applied)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_web_convert_refund.py::test_failed_premium_convert_refunds_token -v`
Expected: FAIL at `assert js.get_job(job_id)["token_hash"] is not None` — `convert.py` does not yet persist the hash.

- [ ] **Step 3: Implement — compute + persist token_hash and wrap setup in a refunding try**

Edit `web_service/routes/convert.py`:

(a) Add imports near the top (after the existing `web_service` imports):
```python
from web_service import recovery_events_store
from web_service.crypto import compute_token_hash
```

(b) Replace the docstring lines 31-33 ("...consumed atomically before the job is
created — no refund on conversion failure...") with:
```python
    For tier=premium, a valid single-use token is required. The token is
    consumed atomically before the job is created. If job setup or the
    conversion later fails, the token is refunded (reverse-consumed) — see
    _refund_after_setup_failure below and job_queue._maybe_refund_failed_job.
```

(c) Initialise `token_hash_hex` before the premium block and compute it after a
successful consume. Immediately after `circuit_breaker.db_call_succeeded()`:
```python
            token_hash_hex = compute_token_hash(token).hex()
```
and declare it just before `if tier == "premium":`:
```python
    token_hash_hex: str | None = None
```

(d) Generate `job_id` first, then wrap the file-write + `create_job` in a
try/except that refunds on failure and persists the hash. Replace the block from
`job_id = new_job_id()` through the `job_store.create_job(...)` call with:
```python
    job_id = new_job_id()
    temp_dir = settings.temp_dir / f"job_{job_id}"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        input_path = temp_dir / f"input.{result.detected_fmt}"
        input_path.write_bytes(file_bytes)
        job_store.create_job(
            job_id=job_id,
            tier=tier,
            input_fmt=result.detected_fmt,
            output_fmt=output_format,
            temp_dir=str(temp_dir),
            input_path=str(input_path),
            original_filename=file.filename or None,
            token_hash_hex=token_hash_hex,
        )
    except Exception:
        log.exception("Job setup failed after token consume for job %s", job_id)
        if token_hash_hex:
            await _refund_after_setup_failure(token_hash_hex, job_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Could not start conversion; your credit was not used.",
                "code": "JOB_SETUP_FAILED",
            },
        )
```

(e) Add the module-level helper (above the route function):
```python
async def _refund_after_setup_failure(token_hash_hex: str, job_id: str) -> None:
    """Refund a just-consumed premium token when job setup fails before dispatch.

    Best-effort: errors are logged, never propagated — the caller already raises
    a 500 to the client. Mirrors job_queue._maybe_refund_failed_job's shape.
    """
    loop = asyncio.get_event_loop()
    try:
        token_hash_bytes = bytes.fromhex(token_hash_hex)
    except ValueError:
        log.warning("Cannot refund setup failure for %s: token_hash not hex", job_id)
        return
    try:
        refund = await loop.run_in_executor(
            billing_executor,
            token_store.refund_token,
            token_hash_bytes,
            job_id,
            "convert_setup_failed",
        )
    except Exception:
        log.exception("Refund after setup failure raised for %s", job_id)
        return
    try:
        recovery_events_store.log_event(
            "premium_refund_applied",
            details={
                "job_id": job_id,
                "reason": "convert_setup_failed",
                "refunded": refund.refunded,
                "ledgered": refund.ledgered,
                "refund_id": refund.refund_id,
            },
        )
    except Exception:
        log.exception("Telemetry log_event failed for setup-failure refund %s", job_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest tests/test_web_convert_refund.py::test_failed_premium_convert_refunds_token -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web_service/routes/convert.py tests/test_web_convert_refund.py
git commit -m "feat(EB-332): persist token_hash + refund failed top-level premium /convert"
```

## Task B4: Refund when job setup fails after the token is consumed

**Files:**
- Test: `tests/test_web_convert_refund.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_convert_refund.py`:

```python
def test_premium_convert_refunds_when_create_job_fails(client, monkeypatch):
    """If create_job raises after the token is consumed, the token is refunded."""
    import web_service.token_store as ts
    from web_service.routes import convert as convert_module

    tc, db_path, settings = client
    ts.init_db(db_path)
    mint = ts.mint_tokens_if_absent(
        session_id="cs_eb332_setupfail", count=1,
        payment_intent_id="pi_eb332_setupfail", db_path=db_path,
    )
    token = mint.tokens[0]

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated create_job failure")

    monkeypatch.setattr(convert_module.job_store, "create_job", _boom)

    files = {"file": ("book.pdf", b"%PDF-1.4\n" + b"\x00" * 4000, "application/pdf")}
    resp = tc.post("/convert", files=files, data={"output_format": "kfx", "tier": "premium", "token": token})

    assert resp.status_code == 500
    assert resp.json()["detail"]["code"] == "JOB_SETUP_FAILED"

    conn = sqlite3.connect(str(db_path))
    used = conn.execute("SELECT used FROM tokens WHERE pack_id=?", ("cs_eb332_setupfail",)).fetchone()[0]
    ledger = conn.execute("SELECT refund_reason FROM refund_ledger").fetchall()
    conn.close()
    assert used == 0, "token must be refunded when job setup fails after consume"
    assert [r[0] for r in ledger] == ["convert_setup_failed"]
```

- [ ] **Step 2: Run test to verify it passes**

This test should already PASS given Task B3's `_refund_after_setup_failure`. Run:
`py -3.12 -m pytest tests/test_web_convert_refund.py::test_premium_convert_refunds_when_create_job_fails -v`
Expected: PASS. If it FAILS, the refund hook in B3(d)/(e) is wired incorrectly — fix before continuing.

- [ ] **Step 3: Run the full web test suite for regression**

Run: `py -3.12 -m pytest tests/test_web_convert_refund.py tests/test_web_reconvert.py tests/test_web_endpoints.py tests/test_web_recovery_events_store.py tests/test_web_token_store.py -v`
Expected: all PASS. Confirms free-tier `/convert` still creates jobs (no `token_hash`, no refund path) and reconvert refunds are unchanged.

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_convert_refund.py
git commit -m "test(EB-332): cover refund when premium /convert setup fails after consume"
```

## Task B5: Stream B verification + finish

- [ ] **Step 1: Run the manifest + regression checks** (project policy)

Run: `pwsh -File tools/verify-manifest.ps1 -Verbose`
Expected: PASS (no exported function/CLI/critical-file removed).

- [ ] **Step 2: Open the PR** via the `ship` skill / `safe-commit`, targeting `master`. Title: `fix(EB-332): refund failed premium conversions (token never burned for no output)`.

- [ ] **Step 3: After merge**, leave Stream A to its own branch.

---

# STREAM A — VM Wine + Kindle Previewer toolchain (ops + deploy)

> **GATE 1 — EB-331:** Do not start until EB-331's deploy-path reconciliation
> (real layout: `User=joe`, `/home/joe/EbookAutomation`, `.venv`,
> `EnvironmentFile=/etc/web_service.env`) has landed or is available as a branch.
> Branch `fix/EB-332-vm-kfx-toolchain` **from that branch**, not from `master`.
>
> **GATE 2 — VM go-ahead:** Tasks A2–A4 modify the production VM
> (`claude-dev-01`). Do NOT SSH to or change the VM until the user gives an
> explicit go-ahead. Take the Hetzner snapshot (A2 step 1) before any package
> install.

## Task A1: Scaffold the installer + verifier skeletons (no VM access)

**Files:**
- Create: `deploy/install-kfx-toolchain.sh`
- Create: `deploy/verify-kfx-toolchain.sh`

- [ ] **Step 1: Create `deploy/verify-kfx-toolchain.sh`** — the cheap, no-install
  check the routine deploy runs. Exits non-zero (alert) if any KFX prerequisite
  is missing. No apt, no downloads, no snapshots.

```bash
#!/usr/bin/env bash
# verify-kfx-toolchain.sh — cheap KFX readiness probe for the routine deploy tick.
# Installs nothing. Exit 0 = ready, 1 = a prerequisite is missing (alert).
set -euo pipefail

JOE_HOME="/home/joe"
fail=0
note() { echo "[kfx-verify] $*"; }

command -v wine >/dev/null 2>&1 || { note "MISSING: wine not on PATH"; fail=1; }
[ -f "$JOE_HOME/.wine/system.reg" ] || { note "MISSING: wine prefix $JOE_HOME/.wine"; fail=1; }

# KFX Output plugin registered in calibre (run as joe).
if ! sudo -u joe calibre-customize --list-plugins 2>/dev/null | grep -qi 'KFX Output'; then
  note "MISSING: Calibre 'KFX Output' plugin not registered"; fail=1
fi

# Kindle Previewer present (path frozen by the installer; placeholder until A3).
KP_EXE="${KINDLE_PREVIEWER:-$JOE_HOME/.wine/drive_c/Kindle Previewer 3/Kindle Previewer 3.exe}"
[ -f "$KP_EXE" ] || { note "MISSING: Kindle Previewer at $KP_EXE"; fail=1; }

if [ "$fail" -ne 0 ]; then note "KFX toolchain NOT ready"; exit 1; fi
note "KFX toolchain ready"
```

- [ ] **Step 2: Create `deploy/install-kfx-toolchain.sh`** skeleton with the
  privilege split explicit (root for packages, `sudo -u joe` for user-space) and
  pinned-version placeholders that the spike (A2–A3) fills in with real
  versions/checksums:

```bash
#!/usr/bin/env bash
# install-kfx-toolchain.sh — bootstrap/rebuild/manual ONLY. Not for the deploy tick.
# Run as root (handles apt + WineHQ repo); drops to `sudo -u joe` for user-space.
# Idempotent: safe to re-run. Versions/checksums are PINNED below — update only
# after re-validating on the box.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "must run as root"; exit 1; }

JOE_HOME="/home/joe"
WINE_VERSION="__PIN_DURING_SPIKE__"          # e.g. 9.0~focal-1  (A2)
KP3_URL="__PIN_DURING_SPIKE__"               # Amazon installer URL (A3)
KP3_SHA256="__PIN_DURING_SPIKE__"            # checksum of the downloaded installer
KP3_CACHE="$JOE_HOME/.cache/kfx/KindlePreviewerInstaller.exe"
KFX_PLUGIN_URL="__PIN_DURING_SPIKE__"        # KFX Output plugin zip (jhowell/MobileRead)
KFX_PLUGIN_SHA256="__PIN_DURING_SPIKE__"
KFX_PLUGIN_CACHE="$JOE_HOME/.cache/kfx/KFXOutput.zip"

echo "[1/5] Wine (root, pinned $WINE_VERSION) — A2"      # apt + WineHQ repo
echo "[2/5] Wine prefix for joe — A2"                    # sudo -u joe wineboot
echo "[3/5] Kindle Previewer 3 under Wine (headless) — A3"
echo "[4/5] Calibre KFX Output plugin (verify) — A3"
echo "[5/5] Final end-to-end KFX smoke — A4"
echo "Skeleton only — steps land as the spike confirms them."
```

- [ ] **Step 3: Make both executable and commit**

```bash
chmod +x deploy/install-kfx-toolchain.sh deploy/verify-kfx-toolchain.sh
git add deploy/install-kfx-toolchain.sh deploy/verify-kfx-toolchain.sh
git commit -m "feat(EB-332): scaffold KFX toolchain installer + cheap deploy verifier"
```

## Task A2: Live spike — Wine install + prefix (GATE 2 required)

**Files:** fills in `deploy/install-kfx-toolchain.sh` steps [1] and [2].

- [ ] **Step 1: Snapshot the VM first.** On the workstation or VM with `hcloud` configured:
  `hcloud server create-image --type snapshot --description "pre-EB-332-kfx $(date +%F)" <server-id-or-name>`
  Expected: a snapshot ID returned. Record it in the PR description for rollback.

- [ ] **Step 2: Install Wine as root** via the WineHQ apt repo, pinning a version
  known to run Kindle Previewer 3 (KP3 needs a reasonably modern Wine; validate
  on the box). Capture the exact installed version:
  `wine --version`  → record into `WINE_VERSION`.

- [ ] **Step 3: Initialise the prefix for `joe`, headless:**
  `sudo -u joe env WINEARCH=win64 WINEPREFIX=/home/joe/.wine xvfb-run -a wineboot --init`
  Expected: `/home/joe/.wine/system.reg` exists afterwards. (Resolves the original
  `user.reg not found` failure from EB-332.)

- [ ] **Step 4: Freeze steps [1]+[2] into the installer** with the real version,
  then re-run the installer top-to-stop to confirm idempotency. Commit:

```bash
git add deploy/install-kfx-toolchain.sh
git commit -m "feat(EB-332): pin Wine install + joe prefix init in KFX installer (spike-verified)"
```

## Task A3: Live spike — Kindle Previewer 3 + Calibre KFX Output plugin (GATE 2)

**Files:** fills in installer steps [3] and [4].

- [ ] **Step 1: Acquire Kindle Previewer 3.** Download Amazon's installer; record
  the real URL, version, and `sha256sum` into `KP3_URL`/`KP3_SHA256`, cached at
  `KP3_CACHE`. **If Amazon requires interactive EULA/manual download** (likely),
  document that constraint in `deploy/README.md` and have the installer verify the
  cached file's checksum rather than fetch it.

- [ ] **Step 2: Install KP3 under Wine headless:**
  `sudo -u joe env WINEPREFIX=/home/joe/.wine xvfb-run -a wine "$KP3_CACHE" /S`
  (validate the silent-install flag during the spike; fall back to a scripted
  install if `/S` is unsupported). Expected: `Kindle Previewer 3.exe` exists under
  `~/.wine/drive_c/...`; record its path into `KINDLE_PREVIEWER`.

- [ ] **Step 3: (Re)install + verify the Calibre KFX Output plugin as `joe`:**
  download the pinned plugin zip (record `KFX_PLUGIN_URL`/`KFX_PLUGIN_SHA256`),
  then:
  `sudo -u joe calibre-customize --add-plugin "$KFX_PLUGIN_CACHE"`
  `sudo -u joe calibre-customize --list-plugins | grep -i 'KFX Output'`
  Expected: the plugin is listed. Configure it to point at `$KINDLE_PREVIEWER`.

- [ ] **Step 4: Freeze steps [3]+[4] into the installer** (with checksums + the
  resolved KP path) and commit:

```bash
git add deploy/install-kfx-toolchain.sh deploy/README.md
git commit -m "feat(EB-332): pin Kindle Previewer 3 + KFX Output plugin install (spike-verified)"
```

## Task A4: Systemd runtime constraints + end-to-end proof through the service (GATE 2)

**Files:**
- Modify: `deploy/web_service.service` (EB-331-corrected version)
- Modify: `deploy/README.md`
- Finalise: `deploy/install-kfx-toolchain.sh` step [5]

- [ ] **Step 1: Grant the hardened unit the runtime paths + env.** In the
  EB-331-corrected `ebookweb`/`web_service.service` (`User=joe`,
  `WorkingDirectory=/home/joe/EbookAutomation`), under the hardening block, add the
  KFX runtime write paths and environment:

```ini
# EB-332: KFX (Wine + Kindle Previewer) needs these writable at runtime, and
# the env set for the conversion subprocess. ProtectSystem=strict makes the FS
# read-only except ReadWritePaths, so Wine/Calibre would otherwise hit EROFS.
ReadWritePaths=/home/joe/EbookAutomation/data /home/joe/.wine /home/joe/.config/calibre /home/joe/.cache/calibre /tmp
Environment=HOME=/home/joe
Environment=WINEPREFIX=/home/joe/.wine
Environment=KINDLE_PREVIEWER=/home/joe/.wine/drive_c/Kindle Previewer 3/Kindle Previewer 3.exe
```
(Replace the `KINDLE_PREVIEWER` path with the one resolved in A3. Confirm the
real ReadWritePaths data dir matches EB-331's layout.)

- [ ] **Step 2: Reload + restart the service:**
  `sudo systemctl daemon-reload && sudo systemctl restart ebookweb`
  Then `curl -s https://api.leafbind.io/health` → expect `{"status":"ok",...}`.

- [ ] **Step 3: End-to-end proof THROUGH the running service** (this is AC #4).
  Mint a premium dev token (per `leafbind-deploy-topology-and-kfx-gap` memory),
  then drive a real ≥40 MB PDF:
```bash
curl -sS -X POST https://api.leafbind.io/convert \
  -F "tier=premium" -F "output_format=kfx" -F "token=<lb_pk_...>" \
  -F "file=@/path/to/real_40mb.pdf"
# poll until done:
curl -s https://api.leafbind.io/status/<job_id>
# then download and confirm non-zero .kfx:
curl -s -o out.kfx https://api.leafbind.io/download/<job_id> && ls -l out.kfx
```
  Expected: `status=done`, `out.kfx` is non-zero and sideloads on a Kindle. The
  conversion ran under the systemd sandbox — proving step 1's paths/env are
  sufficient (not just an interactive shell).

- [ ] **Step 4: Finalise installer step [5]** to run this smoke conversion (against
  a small fixture PDF) and assert non-zero `.kfx`, and commit:

```bash
git add deploy/web_service.service deploy/install-kfx-toolchain.sh deploy/README.md
git commit -m "feat(EB-332): systemd KFX runtime paths/env + end-to-end smoke through service"
```

## Task A5: Wire into EB-331 bootstrap/rebuild (not the deploy tick)

**Files:**
- Modify: `deploy/README.md` (and EB-331's bootstrap/rebuild script, coordinated with that ticket)

- [ ] **Step 1: Add `install-kfx-toolchain.sh` to the bootstrap/rebuild path** so a
  VM rebuild re-runs it. Add `verify-kfx-toolchain.sh` to the routine deploy as a
  post-restart probe that **alerts but does not install**. Document both in
  `deploy/README.md`, and explicitly state: the installer is manual/bootstrap-only;
  the verifier is the only KFX step on the deploy tick.

- [ ] **Step 2: Commit**

```bash
git add deploy/README.md
git commit -m "docs(EB-332): wire KFX installer into bootstrap, verifier into deploy tick"
```

## Task A6: Stream A finish

- [ ] **Step 1: Run the verifier on the VM** post-install:
  `sudo bash deploy/verify-kfx-toolchain.sh` → expect `KFX toolchain ready`, exit 0.
- [ ] **Step 2: Open the PR** (targets EB-331's branch or `master` once EB-331 merged), recording the snapshot ID + the resolved versions/checksums in the description.

---

## Self-Review

**Spec coverage:**
- Refund-on-failure (reuse EB-324) → B2, B3. ✓
- `premium_refund_applied` event + whitelist test → B1, B2, B3. ✓
- Neutral reasons / `job_id` details → B2. ✓
- consume→create_job hardening → B3(d/e), B4. ✓
- Pin + verify KFX Output plugin on rebuild → A3 step 3, verifier. ✓
- Pin Kindle Previewer (source/version/sha/cache/EULA) → A3 step 1. ✓
- Wine pinned + prefix → A2. ✓
- systemd ReadWritePaths + env, proof through service → A4. ✓
- EB-331 dependency → GATE 1 + Parallelization Map. ✓
- Autodeploy split (installer vs cheap verifier) → A1, A5. ✓
- deploy/README real layout → A3/A4/A5. ✓

**Placeholder scan:** Stream B steps contain full code. Stream A's
`__PIN_DURING_SPIKE__` markers are intentional — they are the spike's outputs, and
each has an explicit task step that resolves it (A2 Wine version, A3 KP3 + plugin
URLs/checksums). No code-step placeholders.

**Type/name consistency:** `_maybe_refund_failed_job` (renamed in B2) is the name
used consistently; `premium_refund_applied` matches across B1/B2/B3; `token_hash_hex`
param matches `job_store.create_job`'s existing signature; `RunResult(success=...,
output_path=..., output_size=..., error_message=...)` matches the reconvert test's usage.
