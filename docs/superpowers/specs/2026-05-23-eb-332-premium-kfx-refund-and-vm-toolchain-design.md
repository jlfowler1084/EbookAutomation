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
4. **Refund reason/details correctness:** the helper currently logs only
   `child_job_id`, always includes `parent_job_id`, and the clean-fail call site
   passes `reason="child_job_failed"` (`job_queue.py:107`) — all wrong for a
   top-level upload. Use **neutral reasons** that read correctly for both parent
   and child (`dispatch_exception` for the exception path, `pipeline_failed` for
   the clean-fail path — renamed from `child_job_failed`), always include a
   `job_id` key, and include `parent_job_id` only when present.
5. **Tests:** new case mirroring the reconvert refund test — a top-level premium
   `/convert` whose pipeline fails ⇒ token reverse-consumed (reusable),
   `refund_ledger` row written, `premium_refund_applied` emitted. Plus a unit test
   for the consume→create_job failure refund path. Update the
   `_VALID_EVENT_TYPES` whitelist test to cover the new event.

This stream removes the charge-with-no-output harm **even before Wine works**, so
it ships first on its own branch.

## Stream A — Make KFX actually produce on the VM (ops + deploy reproducibility)

**Target:** `claude-dev-01`, service user `joe`, project `/home/joe/EbookAutomation`,
`EnvironmentFile=/etc/web_service.env`, systemd unit `ebookweb`. The deploy
artifacts on master are stale (`User=ebookweb`, `/opt/ebookautomation`,
`/opt/ebookautomation/.env`); **EB-331 (In Progress) owns the path reconciliation.**

### Dependency on EB-331 (load-bearing)

Stream A edits the systemd unit and deploy scripts, which EB-331 is concurrently
rewriting to the real `/home/joe/EbookAutomation` layout. Editing master's stale
files would be throwaway work and would collide with EB-331. **Stream A branches
from (or merges after) EB-331's deploy-path reconciliation**, so all systemd /
installer / README edits target the corrected layout — never the stale master
files. If EB-331's path fix has not landed when Stream A is ready, branch from
EB-331's branch rather than master.

1. **New `deploy/install-kfx-toolchain.sh`** (idempotent, re-runnable, run under
   user `joe`):
   - Install Wine at a **pinned** version (WineHQ repo) compatible with Kindle
     Previewer 3 — record the exact package version.
   - Initialize `~/.wine` prefix for `joe` (`WINEARCH`, headless `wineboot`).
   - Install **Kindle Previewer 3**, pinned: record installer **source URL,
     version, SHA-256 checksum, and local cache path**, plus any EULA /
     manual-download constraint discovered during the spike (Amazon's installer
     may not be directly `wget`-able and may require accepting terms — capture the
     real acquisition method). Driven headlessly via `xvfb-run`.
   - Install + pin the **Calibre KFX Output plugin** (and KFX Input): record the
     plugin artifact **version + SHA-256**, install via
     `calibre-customize --add-plugin <KFXOutput.zip>` as `joe`, and **verify** with
     `calibre-customize --list-plugins | grep -i kfx`. The plugin must be
     (re)installed on rebuild — not assumed present.
   - Configure the KFX Output plugin to locate `kindlepreviewer.exe`
     (plugin preference / `KINDLE_PREVIEWER` path), wrapping KP3 in `xvfb-run`.
2. **Runtime systemd / env constraints (do not skip — this is where it silently
   breaks):** under `ProtectSystem=strict` the filesystem is read-only except the
   `ReadWritePaths`. Wine writes to `~/.wine` and Calibre writes its config/cache
   at conversion time, so the **running service** (not just an interactive shell)
   needs those paths writable and the env set. In the EB-331-corrected unit:
   - Add `ReadWritePaths` for `/home/joe/.wine`, `/home/joe/.config/calibre`,
     `/home/joe/.cache/calibre`, and any KP3 cache dir found during the spike.
   - Provide `HOME`, `WINEPREFIX`, and `KINDLE_PREVIEWER` to the service via
     `Environment=` (or an `ExecStart` wrapper script), so the conversion
     subprocess inherits them.
   - Confirm `PrivateTmp=true` is compatible with `xvfb`/Wine socket usage in
     `/tmp` (isolated tmp is expected to be fine, but verify).
3. **Pre-change safety:** take a Hetzner snapshot (`hcloud` is installed) before
   the spike — this is additive but fragile package work.
4. **Autodeploy split (finding 4):** package installs, KP3 acquisition, and
   snapshots are **bootstrap / rebuild / manual-install only** — they must **not**
   run on the routine ~5-minute EB-331 deploy tick. The routine deploy runs only a
   **cheap KFX verifier** (e.g. `wine --version` + `calibre-customize
   --list-plugins | grep -i kfx` + a presence check on `kindlepreviewer.exe`) that
   **alerts on regression** without installing anything. The heavy installer is
   wired into the bootstrap/rebuild path so a VM rebuild re-runs it.
5. **Docs:** fix `deploy/README.md` to the real layout (coordinated with EB-331).
6. **End-to-end proof (AC):** a real ≥40 MB PDF through
   `https://api.leafbind.io/convert` (`tier=premium`, `kfx`) reaches
   `status=done`, and `/download/{job_id}` returns a non-zero `.kfx`. The
   conversion **must run through the actual `ebookweb.service`** (restart the
   service and convert, or `systemd-run` with the unit's sandbox), not merely an
   interactive `joe` shell — to prove the sandbox/env constraints are satisfied.

**Risk flag:** the Wine + KP3 *headless* step is the one genuinely uncertain
piece. Treat it as a **live spike on the VM**: iterate against the box until a real
KFX builds *through the hardened service*, then freeze the working steps,
versions, and checksums into the install script. **No production-VM access happens
until the user gives an explicit go-ahead for the spike step** (re-confirmed when
we reach it). Stream B needs no VM access.

## Sequencing

Two worktree branches (per worktree policy):

- `fix/EB-332-premium-refund-on-failure` (Stream B) — fully testable locally,
  merges first. No dependency on EB-331 or the VM.
- `fix/EB-332-vm-kfx-toolchain` (Stream A) — deploy scripts + doc fixes.
  **Branches from EB-331's deploy-path reconciliation** (or merges after it), so
  edits target the real `/home/joe/EbookAutomation` layout. The installer +
  systemd changes land after the live spike confirms the steps, versions, and
  checksums.

## Acceptance criteria (from EB-332)

- [ ] `wine` installed on the VM at a **pinned, recorded** version; `~/.wine` prefix exists for `joe`.
- [ ] Kindle Previewer 3 installed under Wine and launchable headless, with **source/version/SHA-256/cache-path** recorded (and EULA/manual-download constraint documented).
- [ ] Calibre KFX Output plugin **(re)installed with pinned version + SHA-256** via `calibre-customize --add-plugin`, verified by `--list-plugins`, and configured with a valid path to `kindlepreviewer.exe`.
- [ ] The `ebookweb.service` unit grants runtime write access to `~/.wine` + Calibre config/cache and sets `HOME`/`WINEPREFIX`/`KINDLE_PREVIEWER`, against the EB-331-corrected layout.
- [ ] A premium KFX conversion of a real ≥40 MB PDF **run through the actual `ebookweb.service`** reaches `status=done`; download returns a non-zero `.kfx` that sideloads on a Kindle.
- [ ] Heavy install runs at bootstrap/rebuild/manual only; routine deploy runs a cheap KFX verifier that alerts on regression (no installs/snapshots on the deploy tick).
- [ ] Setup documented in `deploy/` (real layout) and survives a VM rebuild.
- [ ] Token-on-failure UX implemented (refund/reverse-consume) so a failed premium request never silently charges a credit with no output.

## Out of scope

- KFX output *quality* vs. free tier (EB-321 — cannot be assessed until KFX produces).
- Offloading KFX to the Windows desktop (considered and rejected; not 24/7).
- AZW3 fallback delivery (considered; premium is marketed specifically as KFX).
