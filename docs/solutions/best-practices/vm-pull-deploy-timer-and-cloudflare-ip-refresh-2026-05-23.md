---
ticket: EB-331
date: 2026-05-23
author: Joe Fowler
tags: [systemd, timer, pull-deploy, deploy, discord, cloudflare, nginx, vm, bash, infra, leafbind]
module: deploy
problem_type: deploy-automation-pattern
related:
  - EB-324 (the gap this closes — VM 45 commits behind at Send-to-Kindle go-live)
  - PR #153 / fix/EB-331-deploy-path-reconciliation (the deploy primitive this wraps; merge first, then rebase EB-331)
  - docs/plans/2026-05-22-002-feat-eb331-vm-autodeploy-plan.md
  - docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md
  - best-practices/vercel-production-branch-misconfiguration-2026-05-15.md ("deploy succeeded ≠ deploy shipped")
  - best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md (verify THROUGH the CF proxy, fail-closed)
  - best-practices/verify-tool-dependent-hypotheses-before-shipping-diagnosis-2026-05-15.md (health = active probe, not a non-crashing process)
---

# VM pull-deploy via systemd timer + best-effort Discord + monthly Cloudflare-IP refresh

## Problem

There was no auto-deploy from `master` to the production `ebookweb` VM. Merges
accumulated undeployed until someone ran `deploy.sh` by hand. At the EB-324
Send-to-Kindle go-live the VM was **45 commits behind** — the backend was merged
but never deployed, the go-live flag was flipped against code not on the box, and
the route 404'd. Critically, "no news" looked identical to "all healthy."

The pattern below codifies the manual deploy into an unattended, self-healing,
self-reporting loop. It's reusable for any single-VM, git-checkout-on-the-box
service where you want master→prod within minutes without putting CI credentials
on GitHub.

## The pattern (what was built)

Pull model, not push — all credentials stay on the VM:

```
ebookweb-autodeploy.timer (OnBootSec=2min, OnUnitActiveSec=5min)
  └─> autodeploy.sh  (flock'd, root)  — wraps, never reimplements, deploy.sh
        fetch origin/master; HEAD == origin/master ? exit silently
        : preflights (on master, clean tree, HEAD ancestor of origin)
          → deploy.sh (ff-pull → pip → restart → ~45s health poll → auto-rollback)
            ok   → 🟩 + through-CF /health probe (annotation only)
            fail → 🔴 (deduped) + last ~15 lines  [deploy.sh already rolled back]
heartbeat.timer (daily)   → liveness / N-behind  (dead-timer canary)
cf-refresh.timer (monthly)→ rewrite nginx CF allowlist, verify THROUGH Cloudflare
```

Installed idempotently by `deploy/install-autodeploy.sh`; enabled behind a
human branch-protection gate. Full how-it-works + rollout runbook lives in
`deploy/README.md` → "Automated Deploy (EB-331)".

## Reusable lessons (the non-obvious parts)

These are the things that cost time or would have shipped a latent bug. They
generalize beyond this repo.

### 1. A dedupe re-nag window must be timestamped from the last POST, not the last event

The alert dedupe stored `<class> <epoch>` and re-nagged after 3h. The first
implementation re-stamped the timestamp on **every** failing tick (including
suppressed ones). Effect: a failure recurring every 5 min slid the window
forward by one tick each time, `delta` never reached 3h, and **the re-nag never
fired** — it alerted once and went permanently silent. The exact "silent dead
timer" failure mode the ticket exists to prevent.

Fix: only re-stamp when you actually post. A green suite hid it because the
dedupe test asserted *within-window suppression* but never asserted the re-nag
*fires* after the window. **A dedupe test is only half-written until it proves
recovery, not just suppression.** (Regression: `test_autodeploy.sh::T8b`,
verified to fail against the pre-fix logic before locking in.)

### 2. On Windows, `core.filemode=false` silently strips the +x bit — store it in git

The deploy scripts are `ExecStart=` / direct-exec targets (`autodeploy.sh` execs
`deploy.sh`; systemd execs `autodeploy.sh`). New `.sh` files committed from this
Windows repo landed `100644`. A VM `git pull` then checks them out
non-executable → systemd fails with `Command ... is not executable`.

- A manual `chmod +x` on the VM does **not** survive — the next autodeploy
  `git pull` restores the index mode (644).
- `git commit <pathspec>` re-stats the working file under `core.filemode=false`
  and discards an index mode change; `git update-index --chmod=+x` + `git commit`
  *without* a pathspec (or `--amend` from the index) is what makes 100755 stick.
- Pin systemd unit files to LF in `.gitattributes` (`*.service`/`*.timer text
  eol=lf`) — a stray CRLF puts `\r` in `ExecStart=` and yields the same
  "not executable" failure on Linux.

Verify with `git ls-files -s deploy/*.sh` (expect `100755` for exec'd scripts,
`100644` for sourced libs).

### 3. A sourced bash helper must be source-safe and never propagate failure

`discord-notify.sh` is `source`d by the deploy wrapper. It deliberately has **no**
`set -euo pipefail` at file scope (that would mutate the *caller's* shell options).
Best-effort is enforced per-call: every fallible command is guarded
(`if ! cmd; then return 0`), the JSON is built with `jq -n --arg` (never string
interpolation, so quotes/newlines in a failure dump stay valid), and an unset
webhook / Discord outage logs to journald and returns 0. Discord being down must
never block a deploy.

### 4. Through-CF probe is annotation, local health is the rollback gate

`deploy.sh` polls `127.0.0.1:8001/health` as the rollback decision. `autodeploy.sh`
*additionally* probes `https://api.leafbind.io/health` through Cloudflare (with a
`?cb=` cold-bust) to report *verified* state — but a failed through-CF probe
**downgrades the success line to ⚠️ and does not roll back**. Rolling back on a
transient CF/network blip would be a false negative. (Consistent with the
"verify THROUGH the proxy" lesson, but scoped so the proxy can't trigger a
rollback.)

### 5. Branch protection without required status checks

The repo's app-test workflows are `paths:`-filtered, so a deploy-only PR never
triggers them. Adding them as *required* checks would deadlock such PRs on a
forever-pending check. The right gate for a solo maintainer making master
auto-executing: **require a PR + block direct push, no required status checks.**

### 6. Test the wrapper, freeze the dependency — and don't trust plan wording about flags

The plan's Unit 6 verification said to use `refresh-cloudflare-ips.sh --dry-run`.
That script has **no** `--dry-run` — it would read `--dry-run` as the config path
(exit 2), and even passing a real path rewrites in place and reloads prod nginx
(its header advertised this as a "dry run" — a latent foot-gun, since corrected).
Resolution: keep the shipped EB-324 script frozen, **stub its 0/1/2/3 exits** to
test the new wrapper's Discord mapping, and fix only the misleading header. When a
plan references a tool flag, confirm the flag exists before building on it.

### 7. Tooling honesty / hermetic tests

- `systemd-analyze verify` exits non-zero under WSL purely because the VM-only
  `ExecStart` path (`/home/joe/...`) doesn't exist locally — **not** a unit-file
  defect. Structural validity (sections, directive names) is the local signal;
  definitive verify is on the VM.
- An implementer reported `EXIT:0` that was a hardcoded `echo`, not `$?`. Re-run
  verification commands yourself; treat self-reported pass/fail as a claim, not
  evidence.
- A test that writes into the repo root instead of a `mktemp` dir leaves a stray
  file (here a `:`-named file — git-bash maps the illegal `:` to U+F03A). Caught
  by the staged-file integrity check. Tests must use temp dirs for all writes; a
  `git add -A` should be sanity-checked before commit. (Bonus: a `replace_all`
  edit over-matched the trailing half of `>> file`, turning it into `>: > file` —
  prefer anchored single-edits over `replace_all` on short, common substrings.)

## How to reuse this

1. Wrap the existing deploy primitive; never reimplement rollback in the tick wrapper.
2. Make every VM-specific path an env var with a default (the wrapper, installer,
   and helper all do this) so the logic is testable against `mktemp` + stubbed
   `systemctl`/`nginx`/`curl` with no VM and no root.
3. Commit exec scripts `100755`, pin units to LF, and have the installer
   `chmod +x` defensively.
4. Gate the installer on the live nginx CF target (exists + sentinels + in
   `nginx -T`) and make the gate atomic — all timers enable together or none do;
   a partial "install failed but some automation is live" state is worse than a
   hard stop + idempotent re-run.
5. Ship a daily heartbeat as the dead-timer canary, and a dedupe window measured
   from the last alert sent.

## References

- Plan: `docs/plans/2026-05-22-002-feat-eb331-vm-autodeploy-plan.md`
- Design spec: `docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md`
- Runbook: `deploy/README.md` → "Automated Deploy (EB-331)"
- Scripts: `deploy/{autodeploy,discord-notify,cf-refresh-wrapped,install-autodeploy}.sh`, `deploy/ebookweb-*.{service,timer}`, `deploy/refresh-cloudflare-ips.{service,timer}`
- Tests: `tests/deploy/test_{autodeploy,discord_notify,cf_refresh,install_autodeploy}.sh`
- EB-331 ticket: https://jlfowler1084.atlassian.net/browse/EB-331
