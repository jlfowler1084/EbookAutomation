---
ticket: EB-331
title: VM deploy automation — pull-model auto-deploy for the ebookweb backend
status: design-approved
date: 2026-05-22
author: Joe Fowler (brainstormed with Claude)
related:
  - EB-330 (go-live ops checklist — Done; source of the 45-commit-drift incident)
  - EB-324 (Send-to-Kindle go-live — the drift was caught here)
  - EB-7 (epic: Cloud Infrastructure & Deployment)
  - PR #153 (fix/EB-331-deploy-path-reconciliation — corrects deploy.sh; this design wraps it)
  - EB-319 (containerization spike — explicitly out of scope)
---

# EB-331 — VM auto-deploy (pull model)

## Problem

There is no auto-deploy from `master` to the production Hetzner VM. Merges accumulate
undeployed until someone runs the deploy by hand. At the EB-324 Send-to-Kindle go-live
(2026-05-22) the VM was found **45 commits behind** (`f93d2bc` vs `origin/master cc81461`):
the entire Send-to-Kindle backend had been merged but never deployed, and the go-live flag
was flipped against code that wasn't on the box (route returned a generic 404). Caught and
fixed by a manual `git pull --ff-only` + restart.

"No news" currently looks identical to "all healthy" — there is no signal that deploys are
flowing or that the box is current.

## Goal

Codify the manual deploy sequence into an unattended, self-healing, self-reporting loop on
the VM, so a merge to `master` reaches production within minutes and any failure is visible.

## Decisions (locked during brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Trigger model | **Pull** (VM systemd timer) | All credentials stay on the box; nothing inbound; GitHub untouched; codifies today's manual sequence. |
| Interval | **5 min** (`OnUnitActiveSec=5min` + `OnBootSec=2min`) | Merge-to-prod ≤ ~5 min; ~288 lightweight checks/day. First-run after boot guaranteed by `OnBootSec`. |
| Alerting | **Discord** (ClaudeInfra Ops), alert-on-trouble + daily heartbeat + one line per real deploy | A silent pull-timer is dangerous — a dead timer looks like "nothing to deploy". Heartbeat catches a dead timer within a day. |
| Reuse vs reimplement | **Wrap `deploy/deploy.sh`** (PR #153) | `deploy.sh` already does pull→pip→restart→health→rollback. EB-331 owns the *trigger* and *visibility* only. |

## Scope

**In:** the `ebookweb` FastAPI backend on the VM (pull timer, alerting, drift visibility,
plus deploying `refresh-cloudflare-ips.sh` with a monthly timer).

**Out:** frontend/Vercel deploy (already auto-deploys), push/CI deploy model, the deploy
path reconciliation itself (PR #153), containerization (EB-319).

## VM ground truth (verified 2026-05-22, per `leafbind-vm-ops-facts` memory)

- Access: Tailscale node `claude-dev-01` (`100.68.98.58`), `ssh root@` with key auth. Public origin `5.161.228.1`.
- App dir `/home/joe/EbookAutomation`, owner `joe`, `.venv`, systemd unit `ebookweb` (uvicorn `web_service.main:app` on `127.0.0.1:8001`).
- `EnvironmentFile=/etc/web_service.env` (the app's env — **not** touched by this work).
- Health endpoint: `http://127.0.0.1:8001/health`.
- DB migrations auto-apply idempotently on startup (`job_store.py::_apply_migrations`).
- Live nginx serving file: `/etc/nginx/sites-enabled/leafbind` (a **regular file**, not a symlink). `refresh-cloudflare-ips.sh` is **not yet on the box**.

## Assumptions

- **`master` is branch-protected with required CI checks.** This design makes `master`
  effectively *auto-execute on the production VM*, so the PR gate + green CI is the only
  thing standing between a merge and prod. If branch protection is not currently enforced,
  enabling it is a prerequisite (tracked alongside this work).
- `deploy.sh` from PR #153 is the deploy primitive. PR #153 should merge first; if it is
  still open at implementation time, the EB-331 branch is cut from `fix/EB-331-deploy-path-reconciliation`
  to avoid a conflicting `deploy.sh`.

## `deploy.sh` contract (from PR #153, with one EB-331 edit)

`deploy.sh` runs **as root** (git/pip via `sudo -u joe`, `systemctl` as root):
rollback-SHA capture → `git pull --ff-only origin master` → `pip install -r requirements.txt`
→ `systemctl restart ebookweb` → health check → on failure `git reset --hard <rollback>` +
pip + restart + recheck, `exit 1`.

**EB-331 edit (coordinated onto the #153 branch):** replace the single `sleep 3` + one
health check with a **poll loop** — check `/health` every 3s for up to ~45s before
declaring failure — to avoid false rollback on slow startup of an unattended deploy.

## Components — all in `deploy/`, installed onto the VM

| Artifact | Role |
|---|---|
| `deploy/autodeploy.sh` | The tick (see algorithm below). Modes: default, `--force`, `--emergency-bypass`, `--heartbeat`, `--dry-run`. |
| `deploy/discord-notify.sh` | Shared helper. Reads webhook from env; formats colored messages; **best-effort** (failure logs to journald, returns 0). Sourced by `autodeploy.sh` and the CF wrapper. |
| `deploy/ebookweb-autodeploy.service` | `Type=oneshot`, runs `autodeploy.sh` as root, `EnvironmentFile=/etc/ebookweb-autodeploy.env`, `Wants=`/`After=network-online.target`. |
| `deploy/ebookweb-autodeploy.timer` | `OnBootSec=2min`, `OnUnitActiveSec=5min`. |
| `deploy/ebookweb-heartbeat.service` + `.timer` | Daily; runs `autodeploy.sh --heartbeat`. |
| `deploy/refresh-cloudflare-ips.service` + `.timer` | `OnCalendar=monthly`; runs a wrapper around the existing `refresh-cloudflare-ips.sh` (failure → 🔴 Discord) against the explicit live path `/etc/nginx/sites-enabled/leafbind`. |
| `deploy/install-autodeploy.sh` | Idempotent installer (see below). |

## `autodeploy.sh` algorithm (default mode)

1. `flock -n /run/ebookweb-deploy.lock` — single locked entrypoint; if held, exit 0 (a deploy is already running).
2. `cd /home/joe/EbookAutomation`.
3. **Fetch:** `git fetch --prune origin +refs/heads/master:refs/remotes/origin/master`. On failure → 🔴 (deduped) + exit.
4. **Change detection:** compare `HEAD` to `refs/remotes/origin/master`. Equal → **exit 0 silently** (no Discord, no state change).
5. **Preflight guards** (all required; any failure → 🔴 with the tripped guard, no deploy):
   - current branch == `master`
   - working tree clean of *tracked* changes (`git diff --quiet && git diff --cached --quiet`)
   - `git merge-base --is-ancestor HEAD refs/remotes/origin/master` (fast-forwardable; not diverged/ahead)
6. Record `OLD=$(git rev-parse HEAD)`.
7. Run `deploy.sh`; capture combined output + exit code.
8. **On exit 0:** `POST=$(git rev-parse HEAD)`; `N=$(git rev-list --count $OLD..$POST)`; post 🟩 `deployed <OLD>..<POST> (N commits) — health OK`. (Count is recomputed from the *post-deploy* HEAD, since origin can advance between the wrapper's fetch and `deploy.sh`'s own pull.)
9. **On non-zero:** post 🔴 with the last ~15 lines of `deploy.sh` output (distinguishes pull-fail vs health-rollback by content).
10. Update dedupe state (success clears any failing state).

**`--force`:** skips step 4 (change detection) only. Steps 5 preflights still run. For when you want to redeploy current `master` immediately. This is the documented manual-deploy entrypoint (shares the flock with the timer — never run bare `deploy.sh` while the timer is enabled).

**`--emergency-bypass`:** the only mode that skips the step-5 safety preflights. Explicitly named so it can never be reached accidentally.

**`--heartbeat`:** no deploy. Runs the same explicit `git fetch ... +refs/heads/master:refs/remotes/origin/master` (heartbeat is not dry-run, so updating the remote-tracking ref is fine), computes behind-count via `git rev-list --count HEAD..refs/remotes/origin/master`, posts 🟢 `HEAD=<sha>, 0 behind, timer alive` (or 🟨 if behind > 0).

**`--dry-run`:** uses `git ls-remote origin refs/heads/master` (no remote-ref mutation), prints the decision and the actions it *would* take, and never restarts/posts/deploys.

## Alert dedupe / backoff

State file under `/var/lib/ebookweb-autodeploy/` records the last alert class + timestamp.
A 🔴 alert posts **on state transition** (healthy → failing) and then re-nags at most once
per ~3h while the same failure persists — never every 5 min. A successful deploy or
heartbeat clears the failing state (and posts a 🟩 recovery line on the first success after
a failure run).

## Discord behavior matrix

| Event | Post? | Color | Content |
|---|---|---|---|
| No change | silent | — | — |
| Deploy success | yes | 🟩 | `deployed <old>..<post> (N commits) — health OK` |
| Fetch failure | deduped | 🔴 | reason + short tail |
| Preflight fail (dirty / diverged / ahead / wrong branch) | deduped | 🔴 | which guard tripped |
| `deploy.sh` fail / rollback | deduped | 🔴 | last ~15 lines of output |
| Recovery (first success after failing) | yes | 🟩 | `recovered — health OK at <sha>` |
| Daily heartbeat | yes | 🟢 up-to-date / 🟨 behind | `HEAD=<sha>, N behind, timer alive` |
| CF refresh success | yes | 🟩 | one line, monthly |
| CF refresh failure | yes | 🔴 | exit code 1/2/3 meaning |

Discord posting is **best-effort**: a missing webhook or a Discord outage logs to journald
and returns success so the deploy is never blocked by the notification path.

## Secrets

`/etc/ebookweb-autodeploy.env` (`0600`, root) holds `DISCORD_DEPLOY_WEBHOOK_URL` — separate
from the app's `/etc/web_service.env`. Loaded via systemd `EnvironmentFile`. **Not committed**
(per the credential-write guard). `install-autodeploy.sh` creates a stub with placeholder if
absent; the real URL is pasted by hand.

## `install-autodeploy.sh` (idempotent)

1. Copy unit files to `/etc/systemd/system/`.
2. Create `/var/lib/ebookweb-autodeploy/` (state dir) and `/etc/ebookweb-autodeploy.env`
   (`0600`, stub) if absent.
3. Copy/refresh `refresh-cloudflare-ips.sh` to its VM location.
4. **CF target validation:** confirm `/etc/nginx/sites-enabled/leafbind` exists, contains the
   `# BEGIN/END CLOUDFLARE IPS` sentinels, and is included in `nginx -T` output. Fail loudly if not.
5. `systemctl daemon-reload`; enable + start the three timers.
6. Print `systemctl list-timers` for the new units.

## Error handling summary

| Failure | Behavior |
|---|---|
| Fetch fails | 🔴 (deduped); no deploy; VM unchanged. |
| Tree dirty / branch ≠ master / diverged / ahead | 🔴 (deduped); no deploy. |
| Health check fails post-restart | `deploy.sh` rolls back to pre-deploy SHA + restart + recheck; wrapper posts 🔴 with tail. |
| pip fails | `deploy.sh` non-zero (set -e); wrapper posts 🔴. |
| Timer dead | Daily heartbeat stops → noticed within a day; also `systemctl` failed state. |
| Discord down / webhook missing | Logged to journald; deploy proceeds. |
| Two ticks overlap | `flock` — second exits immediately. |
| Manual deploy during timer | Use `autodeploy.sh --force` (shares the lock). |

## Testing

- **Local:** `shellcheck` all new scripts; `autodeploy.sh --dry-run` prints decision/actions with no fetch-mutation, restart, post, or deploy.
- **On VM (staged):**
  - (a) no-op tick → silent, no Discord.
  - (b) push a trivial commit → deploy + 🟩 line + correct *post-deploy* SHA.
  - (c) dirty the tree → preflight 🔴, **no** deploy.
  - (d) force a health failure (e.g. break the app transiently) → `deploy.sh` rollback + 🔴 with tail.
  - (e) repeated failure → confirm dedupe (one alert, then ~3h re-nag, not every 5 min).
  - (f) CF refresh `--dry-run` against the repo copy (exercise the exit-3 path), then a live monthly run.
- **Idempotency:** two ticks with no change → two silent no-ops.

## Out of scope (restated)

Frontend/Vercel deploy · push/CI deploy model · the deploy-path reconciliation (PR #153) ·
containerization (EB-319) · Amazon-account or Resend webhook concerns (other tickets).

## Fix-up captured during brainstorm

PR #153's `deploy/README.md` has a typo: it says `"not /etc/web_service.env"` immediately
after stating the correct path *is* `/etc/web_service.env`. It should read
`"not /opt/ebookautomation/.env"`. Push this one-line fix onto the `fix/EB-331-deploy-path-reconciliation`
branch (that PR owns the file).
