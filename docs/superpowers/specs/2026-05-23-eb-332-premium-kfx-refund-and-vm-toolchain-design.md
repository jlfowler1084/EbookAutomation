# EB-332 — Premium KFX: produce it, and stop charging for failed conversions

- **Ticket:** [EB-332](https://jlfowler1084.atlassian.net/browse/EB-332) (Bug, High)
- **Date:** 2026-05-23
- **Status:** Design approved, ready for planning
- **Related:** EB-221 (bootstrap that missed Wine/Previewer), EB-321 (downstream KFX quality), EB-324 (shipped the refund machinery this design reuses)

## Problem

leafbind.io markets **PDF → KFX** as its headline paid feature, but premium KFX
**always fails on the production VM** (`claude-dev-01`): Wine and Kindle Previewer 3
are not installed, so Calibre's KFX Output plugin cannot build the container. No
`.kfx` has ever been produced in production.

Worse than the missing feature: the failure is **silent and billed**. `convert.py`
consumes the single-use premium token atomically *before* the job runs, and the
parent-job failure path does not refund it. A customer selecting KFX today pays a
credit and receives nothing, with no refund.

## Decisions (resolved during brainstorming)

1. **Scope:** both streams, in parallel.
2. **Token-on-failure UX:** refund (reverse-consume) on failure, reusing the
   EB-324 `refund_token()` + `refund_ledger` machinery. Keeps atomic
   consume-before-dispatch (no double-spend race); customer's token becomes
   usable again and an audit row is written.
3. **KFX backend:** install Wine + Kindle Previewer 3 on the VM, so the service
   stays self-contained and 24/7 (rather than offloading to the Windows desktop,
   which is not a 24/7 server).

## Stream B — Refund-on-failure (code, shippable independently)

### Root cause (confirmed in code)

`job_queue.dispatch_job` already invokes `_maybe_refund_failed_child` on **both**
failure branches (`job_queue.py:91` unhandled-exception path, `:107` clean
`result.success == False` path). That helper refunds whenever `job["token_hash"]`
is set — it does **not** require `parent_job_id`. The `jobs.token_hash` column
exists (`job_store.py:35`) and `create_job` already accepts `token_hash_hex`
(`job_store.py:196`).

The **sole** gap: `convert.py` consumes the token but never persists its hash on
the job row, so the guard at `job_queue.py:148` short-circuits for top-level
premium uploads. `reconvert.py:183,194` already does this correctly — Stream B
brings `convert.py` to parity.

### Changes

1. **`web_service/routes/convert.py`** — after a successful `validate_and_consume`,
   compute `token_hash_hex = compute_token_hash(token).hex()` and pass it to
   `create_job(...)`. Fix the now-false docstring (lines 31–33,
   "no refund on conversion failure").
2. **Atomicity hardening (consume→create_job gap):** the token is consumed before
   `input_path.write_bytes` and `create_job`. If either throws, the token is
   burned with no job row to refund against. Wrap the post-consume block so a
   failure there triggers an immediate `refund_token` before re-raising.
3. **Telemetry clarity:** `_maybe_refund_failed_child` unconditionally logs
   `reconvert_refund_applied`, which mislabels a top-level upload. Generalize the
   helper (rename to `_maybe_refund_failed_job`, update docstring) to emit
   `premium_refund_applied` when `parent_job_id` is absent, keeping
   `reconvert_refund_applied` for children. Add `premium_refund_applied` to
   `_VALID_EVENT_TYPES` (`recovery_events_store.py:64`).
4. **Tests:** new case mirroring the reconvert refund test — a top-level premium
   `/convert` whose pipeline fails ⇒ token reverse-consumed (reusable),
   `refund_ledger` row written, `premium_refund_applied` emitted. Plus a unit test
   for the consume→create_job failure refund path.

This stream removes the charge-with-no-output harm **even before Wine works**, so
it ships first on its own branch.

## Stream A — Make KFX actually produce on the VM (ops + deploy reproducibility)

**Target:** `claude-dev-01`, service user `joe`, project `/home/joe/EbookAutomation`.
`deploy/README.md` is stale (documents `/opt/ebookautomation` + `ebookweb` user);
correcting it is part of AC #5.

1. **New `deploy/install-kfx-toolchain.sh`** (idempotent, re-runnable):
   - Install Wine at a pinned version (WineHQ repo) compatible with Kindle
     Previewer 3.
   - Initialize `~/.wine` prefix for `joe` (`WINEARCH`, headless `wineboot`).
   - Install Kindle Previewer 3 under Wine, driven headlessly via `xvfb-run`.
   - Point the Calibre KFX Output plugin at `kindlepreviewer.exe`
     (plugin config / `KINDLE_PREVIEWER` path).
   - Wrap KP3 invocation in `xvfb-run` so the GUI app runs with no real display.
2. **Pre-change safety:** take a Hetzner snapshot (`hcloud` is installed) before
   touching the prod box — this is additive but fragile package work.
3. **Wire into EB-331 autodeploy** so a VM rebuild re-runs the toolchain install
   and does not silently lose KFX again. Fix `deploy/README.md` paths.
4. **End-to-end proof (AC):** a real ≥40 MB PDF through
   `https://api.leafbind.io/convert` (`tier=premium`, `kfx`) reaches
   `status=done`, and `/download/{job_id}` returns a non-zero `.kfx`.

**Risk flag:** the Wine + KP3 *headless* step is the one genuinely uncertain
piece. Treat it as a **live spike on the VM**: iterate the script against the box
until a real KFX builds, then freeze the working steps into the install script.
**No production-VM access happens until the user gives an explicit go-ahead for the
spike step** (re-confirmed when we reach it). Stream B needs no VM access.

## Sequencing

Two worktree branches (per worktree policy):

- `fix/EB-332-premium-refund-on-failure` (Stream B) — fully testable locally,
  merges first.
- `fix/EB-332-vm-kfx-toolchain` (Stream A) — deploy scripts + doc fixes; the
  script lands after the live spike confirms the steps.

## Acceptance criteria (from EB-332)

- [ ] `wine` installed on the VM at a pinned version; `~/.wine` prefix exists for `joe`.
- [ ] Kindle Previewer 3 installed under Wine and launchable headless.
- [ ] Calibre KFX Output plugin configured with a valid path to `kindlepreviewer.exe`.
- [ ] A premium KFX conversion of a real ≥40 MB PDF reaches `status=done`; download returns a non-zero `.kfx` that sideloads on a Kindle.
- [ ] Setup documented in `deploy/` and survives a VM rebuild / autodeploy run.
- [ ] Token-on-failure UX implemented (refund/reverse-consume) so a failed premium request never silently charges a credit with no output.

## Out of scope

- KFX output *quality* vs. free tier (EB-321 — cannot be assessed until KFX produces).
- Offloading KFX to the Windows desktop (considered and rejected; not 24/7).
- AZW3 fallback delivery (considered; premium is marketed specifically as KFX).
