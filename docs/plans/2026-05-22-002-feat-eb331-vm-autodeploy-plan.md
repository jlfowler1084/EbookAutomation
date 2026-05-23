---
title: "feat: EB-331 VM auto-deploy (pull-model systemd timer)"
type: feat
status: active
date: 2026-05-22
origin: docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md
---

# feat: EB-331 VM auto-deploy (pull-model systemd timer)

## Overview

Codify the manual VM deploy sequence into an unattended, self-healing, self-reporting
pull-model loop, so a merge to `master` reaches the production `ebookweb` FastAPI backend
within ~5 minutes and any failure is visible in Discord. A systemd timer on the Hetzner VM
runs a new `deploy/autodeploy.sh` wrapper that fetches, guards, detects change, and delegates
the actual deploy to `deploy/deploy.sh` (from PR #153). Adds Discord alerting (alert-on-trouble
+ daily heartbeat, deduped, best-effort), and a monthly Cloudflare-IP nginx refresh timer.

Backend only — the Vercel frontend already auto-deploys and is out of scope.

## Problem Frame

There is no auto-deploy from `master` to the production VM; merges accumulate undeployed
until someone runs the deploy by hand. At the EB-324 Send-to-Kindle go-live (2026-05-22) the
VM was **45 commits behind** — the entire backend was merged but never deployed, and the
go-live flag was flipped against code not on the box (route 404'd). "No news" currently looks
identical to "all healthy." See origin: `docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md`.

## Requirements Trace

- **R1.** A merge to `master` auto-deploys to the VM within ~5 min (pull model, systemd timer). (origin: Decisions)
- **R2.** Deploys are safe: fast-forward-only, preflight-guarded, health-checked, auto-rollback on failure. (origin: error handling)
- **R3.** Failures and liveness are visible in Discord: alert-on-trouble + daily heartbeat, deduped, never blocking the deploy. (origin: alerting + dedupe)
- **R4.** A single locked entrypoint prevents manual/timer overlap (`--force` keeps safety preflights; `--emergency-bypass` is the only guard-skip). (origin: overlap handling)
- **R5.** `master` is branch-protected (require PR, block direct push) before the timer is enabled. (origin: Prerequisites)
- **R6.** The Cloudflare-IP nginx allowlist is refreshed monthly, against the live served file, with failure surfaced to Discord. (origin: components)
- **R7.** The two carried fix-ups land: `deploy.sh` ~45s health poll + `deploy/README.md` typo. (origin: fix-ups)

## Scope Boundaries

- Backend `ebookweb` only. No frontend/Vercel deploy automation.
- No push/CI deploy model (pull model chosen and locked).
- No containerization (EB-319).
- No change to the app's `/etc/web_service.env` or the app systemd unit beyond what PR #153 already lands.

### Deferred to Separate Tasks

- **PR #153** (`fix/EB-331-deploy-path-reconciliation`) owns the deploy-path reconciliation and stays frozen; EB-331 branches off it. Merge order: #153 → rebase EB-331 onto `master` → merge EB-331.
- **`ce:compound` follow-up:** write a net-new `docs/solutions/best-practices/` entry (no existing entry covers systemd timers / pull-deploy / VM Discord posting / monthly CF-IP refresh).

## Context & Research

### Relevant Code and Patterns

- `deploy/deploy.sh` (reconciled copy on the #153 branch) — the deploy primitive this work wraps. Runs **as root**, git/pip via `sudo -u joe`, `systemctl` as root, `git -c safe.directory=$APP_DIR`, health gate + rollback, `exit 1` on health failure. EB-331 layers trigger + visibility on top.
- `deploy/refresh-cloudflare-ips.sh` — existing CF-IP rewriter. Rich header convention: **Usage** + **Exit codes** block (`0` ok, `1` fetch fail, `2` sentinels missing, `3` `nginx -t` fail). Defaults to `/etc/nginx/sites-available/leafbind` — **must be passed the explicit live path** `/etc/nginx/sites-enabled/leafbind` (a regular file, not symlink).
- `deploy/web_service.service` (reconciled #153 copy) — house style to mirror for new units: `Description=`, `SyslogIdentifier=`, `StandardOutput=journal`/`StandardError=journal`. EB-331 units intentionally deviate (documented, not a contradiction): `Type=oneshot`, run as **root**, `Wants=`/`After=network-online.target`.
- Shell conventions (both `deploy/*.sh`): `#!/usr/bin/env bash`, `set -euo pipefail`, explicit `exit N` + `>&2` on failure paths. `.gitattributes` `*.sh text eol=lf` pin rides in on the #153 branch.
- `.github/workflows/web-tests.yml` (status context **`pytest tests/test_web_*.py`**) and `frontend-e2e.yml` (**`playwright (chromium)`**) — both `paths:`-filtered; deploy-only PRs do not trigger them (drives the R5 branch-protection shape).
- Discord embed shape + color ints to reuse from `discord-webhook` skill `references/message-formats.md`: red `15158332`, green `3066993`, yellow `16776960`, info `9807270`. Payload: `{"embeds":[{"color":<int>,"title":"...","description":"...","footer":{"text":"<ISO-8601 UTC>"}}]}`. **The skill's helper is PowerShell/Windows — cannot run on the VM**, so the bash helper is net-new but mirrors this shape.

### Institutional Learnings

- `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md` — "deploy succeeded ≠ deploy shipped." A green exit is necessary-not-sufficient; assert against the live origin. The repo's production branch is `master`, not `main`.
- `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md` — `api.leafbind.io` is the VM FastAPI backend, **Cloudflare-proxied (orange)**. An nginx CF-IP allowlist that drifts silently 403s real traffic; verify the monthly refresh with a request *through* the proxy. Fail-closed, never fail-open.
- `docs/solutions/eb252-next-plausible-next16-compat.md` + `verify-tool-dependent-hypotheses-before-shipping-diagnosis-2026-05-15.md` — health must be an active independent probe with expected response, not inferred from a non-crashing process.
- `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md` — the CF API token lacks `cache_purge` scope; for a cold through-proxy fetch use `?cb=$(date +%s)` and assert `cf-cache-status: MISS`.

### External References

- None required — internal infra (bash, systemd, git, Discord webhook) with strong local grounding. External research skipped.

## Key Technical Decisions

- **Pull model, not push.** All credentials stay on the VM; GitHub untouched. (origin)
- **Wrap, don't reimplement.** `autodeploy.sh` delegates the deploy to `deploy.sh`; rollback logic is not duplicated.
- **Net-new bash `discord-notify.sh`**, mirroring the PowerShell skill's embed shape/colors, since that helper can't run on Linux. Best-effort: missing webhook or Discord outage logs to journald and returns 0 — never blocks a deploy.
- **Local health is the rollback gate; through-CF probe is annotation only.** `deploy.sh`'s `127.0.0.1:8001/health` poll decides rollback. `autodeploy.sh` additionally probes `https://api.leafbind.io/health` (through CF) to report *verified* state on the Discord success line, but a failed through-CF probe does **not** trigger rollback (avoids false rollback on transient CF/network blips) — it downgrades the success line to a ⚠️ "deployed, but origin probe failed — check CF/nginx" note.
- **Branch protection = require PR + block direct push, no required status checks.** The CI checks are `paths:`-filtered, so requiring them would deadlock deploy-only PRs on a forever-pending check. This closes the real EB-324 gap (direct-to-master / flag-flip-against-unmerged) without CI friction; right-sized for solo-dev self-review.
- **Successful no-change fetch clears failing state** (recovery within one tick, not at next heartbeat).
- **Single flock'd entrypoint** at `/run/ebookweb-deploy.lock`; manual deploys go through `autodeploy.sh --force`.

## Open Questions

### Resolved During Planning

- Push vs pull model → **pull** (origin).
- Branch-protection strictness vs path-filtered checks → **require PR, no required checks**.
- Reuse vs new Discord helper → **new bash helper**, reuse embed shape/colors (the skill is PowerShell-only).
- Through-CF verification role → **annotation, not rollback trigger**.

### Deferred to Implementation

- Exact bash idioms for the dedupe state file format (timestamp + last-alert-class) — settle when writing `autodeploy.sh`.
- Whether `systemd-analyze verify` runs clean against the units as written, or needs minor directive adjustments — confirm at implementation.
- Final retry/sleep constants inside the `deploy.sh` 45s poll loop (e.g., 3s × 15) — tune against observed `ebookweb` cold-start time on the VM.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
ebookweb-autodeploy.timer (OnBootSec=2min, OnUnitActiveSec=5min)
  └─> ebookweb-autodeploy.service (oneshot, root, EnvironmentFile=/etc/ebookweb-autodeploy.env)
        └─> deploy/autodeploy.sh
              flock /run/ebookweb-deploy.lock
              git fetch --prune origin +refs/heads/master:refs/remotes/origin/master
              HEAD == origin/master ?
                ├─ yes → clear-any-failing-state (recovery line if was failing) → exit 0   [silent]
                └─ no  → preflight: branch==master & tree-clean & ff-ancestor
                          ├─ fail → 🔴 discord-notify (deduped) → exit
                          └─ pass → OLD=HEAD
                                    deploy/deploy.sh   (pull→pip→restart→health-poll→rollback)
                                    ├─ exit 0 → POST=HEAD; N=count(OLD..POST)
                                    │            through-CF probe api.leafbind.io/health
                                    │            🟩 discord-notify "deployed OLD..POST (N) — health OK[/⚠️ origin probe failed]"
                                    └─ exit≠0 → 🔴 discord-notify (deduped) + last ~15 lines

ebookweb-heartbeat.timer (daily) → autodeploy.sh --heartbeat → 🟢/🟨 "HEAD=…, N behind, alive"
refresh-cloudflare-ips.timer (monthly) → cf-refresh wrapper → refresh-cloudflare-ips.sh /etc/nginx/sites-enabled/leafbind
                                          through-CF verify → 🟩 ok / 🔴 fail(exit 1/2/3)
```

## Implementation Units

- [ ] **Unit 1: Branch-protect `master` (blocking prerequisite)**

**Goal:** Require a PR before merging to `master` and block direct pushes, so master no longer accepts unreviewed direct commits before it becomes auto-executing on prod.

**Requirements:** R5

**Dependencies:** None. Must be in place before Unit 6's timer is *enabled* on the VM (Unit 8 rollout), not before the code units.

**Files:** None (GitHub repo setting via API/UI on `jlfowler1084/EbookAutomation`).

**Approach:**
- Enable "require a pull request before merging" + block direct pushes to `master`. Do **not** add required status checks (the `pytest tests/test_web_*.py` / `playwright (chromium)` contexts are `paths:`-filtered and would deadlock deploy-only PRs on a pending check).
- Keep "require branches up to date" optional; allow the solo maintainer to self-approve.
- Record the resulting protection state (verified `protected:false` as of 2026-05-22 → expected `protected:true` after).

**Test scenarios:**
- Happy path: after enabling, a direct push to `master` is rejected; a PR can still be merged. → verified via the GitHub API protection endpoint returning `protected:true` and a rejected direct push.
- Edge case: a PR touching only `deploy/**` (no app-test trigger) can still be merged (no forever-pending required check blocks it).

**Verification:** GitHub API reports `master` protected with PR-required; a deploy-only PR merges without a stuck check.

---

- [ ] **Unit 2: Carried fix-ups — `deploy.sh` 45s health poll + README typo**

**Goal:** Land the two fix-ups the spec parks in the EB-331 branch (kept off the frozen #153 PR).

**Requirements:** R7, R2

**Dependencies:** EB-331 branch cut from `fix/EB-331-deploy-path-reconciliation`.

**Files:**
- Modify: `deploy/deploy.sh` (replace `sleep 3` + single `curl -sf` health check with a poll loop: probe `/health` every ~3s for up to ~45s before declaring failure → rollback)
- Modify: `deploy/README.md` (line ~124-125: `"not /etc/web_service.env"` → `"not /opt/ebookautomation/.env"`)

**Approach:**
- Preserve `deploy.sh`'s existing contract (root, `sudo -u joe`, rollback-on-failure, `exit 1`); only the health-detection window changes from one-shot to a bounded poll. Keep the HTTP-200-only check via `curl -sf` (do not assert body content) per existing convention.

**Patterns to follow:** existing `deploy.sh` rollback block; `set -euo pipefail`; `>&2` on failure.

**Test scenarios:**
- Happy path: service healthy within the window → poll exits success on first/early probe, no rollback.
- Edge case: service slow to start (healthy at ~20s) → poll keeps probing and succeeds without false rollback (the bug this fixes).
- Error path: service never healthy within ~45s → rollback to pre-deploy SHA + restart + recheck, `exit 1`.
- Docs: README parenthetical now reads `/opt/ebookautomation/.env` and no longer contradicts the correct path stated immediately before.

**Verification:** `shellcheck deploy/deploy.sh` clean; `bash -n` parses; a staged slow-start does not trigger rollback; README reads consistently.

---

- [ ] **Unit 3: `deploy/discord-notify.sh` shared helper**

**Goal:** A net-new, best-effort bash helper that posts a colored Discord embed; sourced by `autodeploy.sh` and the CF wrapper.

**Requirements:** R3

**Dependencies:** None.

**Files:**
- Create: `deploy/discord-notify.sh`
- Test: `tests/deploy/test_discord_notify.bats` (or a shell test against a stub webhook; see note)

**Approach:**
- Single function/entry: takes a color class (red/green/yellow/info) + title + message; builds the embed JSON (`{"embeds":[{"color":<int>,"title":"[<event>] EbookAutomation","description":"<msg>","footer":{"text":"<ISO-8601 UTC>"}}]}`) with the reused color ints; POSTs to `$DISCORD_DEPLOY_WEBHOOK_URL`.
- **Best-effort:** if the env var is unset/empty or the POST fails (non-2xx / curl error), log to journald (`logger`/stderr) and `return 0`. Never `exit`/propagate failure.

**Patterns to follow:** `discord-webhook` skill `references/message-formats.md` embed shape + colors; non-blocking try/catch posture (mirrored as "log and return 0").

**Test scenarios:**
- Happy path: given a stub webhook URL capturing the request, posting "deployed X" produces a single embed with the green color int, the title, and an ISO-8601 UTC footer.
- Edge case: `DISCORD_DEPLOY_WEBHOOK_URL` unset → function logs a warning and returns 0 (no error, no output to the caller's failure path).
- Error path: webhook returns 500 / curl times out → logged to journald, returns 0 (does not abort the caller).
- Edge case: message contains characters needing JSON escaping (quotes, newlines) → payload remains valid JSON.

**Verification:** `shellcheck` clean; stub-webhook test confirms embed shape/color and the non-blocking return-0 behavior on all failure inputs.

---

- [ ] **Unit 4: `deploy/autodeploy.sh` tick wrapper**

**Goal:** The change-detecting, guarded, deduped wrapper that decides whether to deploy and reports to Discord.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Unit 2 (`deploy.sh` contract), Unit 3 (`discord-notify.sh`).

**Files:**
- Create: `deploy/autodeploy.sh`
- Test: `tests/deploy/test_autodeploy.bats` (logic testable against a throwaway local git repo; see note)

**Approach:**
- `flock -n /run/ebookweb-deploy.lock` (held → exit 0). `cd /home/joe/EbookAutomation`.
- Explicit fetch `git fetch --prune origin +refs/heads/master:refs/remotes/origin/master`; on fail → 🔴 (deduped) + exit.
- Change detect: `HEAD` vs `refs/remotes/origin/master`. Equal → clear failing state (recovery 🟩 only if was failing) → exit 0.
- Preflight (all required): branch==`master`; tree clean of tracked changes; `git merge-base --is-ancestor HEAD refs/remotes/origin/master`. Any fail → 🔴 (deduped, names the tripped guard) + no deploy.
- `OLD=$(git rev-parse HEAD)`; run `deploy.sh`, capture exit + output.
  - exit 0 → `POST=$(git rev-parse HEAD)`; `N=$(git rev-list --count $OLD..$POST)`; through-CF probe `https://api.leafbind.io/health` (best-effort, `?cb=` cold-bust); 🟩 success line with verified state (or ⚠️ if origin probe failed).
  - exit≠0 → 🔴 (deduped) with last ~15 lines of output.
- Modes: `--force` (skip change-detection only; preflights still run); `--emergency-bypass` (only mode that skips preflights); `--heartbeat` (no deploy; explicit fetch, behind-count, 🟢/🟨); `--dry-run` (use `git ls-remote origin refs/heads/master`, no remote-ref mutation, print decision/actions, never restart/post/deploy).
- Dedupe: state file under `/var/lib/ebookweb-autodeploy/`; 🔴 posts on healthy→failing transition then re-nags at most ~once/3h; any success clears it.

**Execution note:** Start with a failing test for the change-detection + preflight decision matrix against a throwaway local git repo (no VM needed) before wiring the `deploy.sh` call.

**Patterns to follow:** `deploy.sh` root/`sudo -u joe`/`safe.directory` conventions; `set -euo pipefail`; rich header with Usage + modes.

**Test scenarios:**
- Happy path (no change): `HEAD == origin/master` → silent exit 0, no Discord post.
- Happy path (deploy): origin ahead by N, preflights pass, `deploy.sh` exits 0 → posts 🟩 with `OLD..POST` and `N` recomputed from post-deploy HEAD.
- Edge case (recovery): previous tick was failing, this tick is a no-change success → posts a single 🟩 recovery line and clears state.
- Error path (fetch fail): `git fetch` fails → 🔴 (deduped), no deploy.
- Error path (dirty tree): tracked file modified → preflight 🔴 names "dirty tree", **no** deploy.
- Error path (diverged/ahead): `HEAD` not ancestor of origin → preflight 🔴, no deploy.
- Error path (deploy.sh fail): `deploy.sh` exit 1 (health rollback) → 🔴 with last ~15 lines.
- Edge case (dedupe): same failure on consecutive ticks → one alert, then no re-post until ~3h elapses (not every 5 min).
- Edge case (lock held): second invocation while lock held → exits 0 immediately, no double-deploy.
- Mode (`--dry-run`): uses `ls-remote`, mutates no remote-tracking ref, posts nothing, restarts nothing.
- Mode (`--force`): redeploys current master but still aborts on a dirty tree (preflights run).
- Integration (through-CF annotation): `deploy.sh` exits 0 but `api.leafbind.io/health` probe fails → success line downgraded to ⚠️, but **no rollback**.

**Verification:** `shellcheck` clean; the decision-matrix test passes against a temp git repo; staged VM run shows correct silent/post behavior per scenario.

---

- [ ] **Unit 5: systemd units — autodeploy + heartbeat**

**Goal:** Drive `autodeploy.sh` on a 5-min tick (with a guaranteed first run after boot) and a daily heartbeat.

**Requirements:** R1, R3

**Dependencies:** Unit 4.

**Files:**
- Create: `deploy/ebookweb-autodeploy.service`, `deploy/ebookweb-autodeploy.timer`
- Create: `deploy/ebookweb-heartbeat.service`, `deploy/ebookweb-heartbeat.timer`

**Approach:**
- `*-autodeploy.service`: `Type=oneshot`, runs as root, `EnvironmentFile=/etc/ebookweb-autodeploy.env`, `ExecStart=.../deploy/autodeploy.sh`, `Wants=`/`After=network-online.target`, journal output, `Description=`/`SyslogIdentifier=` per house style.
- `*-autodeploy.timer`: `OnBootSec=2min`, `OnUnitActiveSec=5min`.
- `*-heartbeat.service`: same env/user, `ExecStart=.../deploy/autodeploy.sh --heartbeat`.
- `*-heartbeat.timer`: daily (`OnCalendar=daily`, `Persistent=true`).

**Patterns to follow:** `deploy/web_service.service` house style (journal, `Description=`, `SyslogIdentifier=`); documented deviations (oneshot/root/network-online.target).

**Test scenarios:**
- Test expectation: none (declarative unit files). Validated by `systemd-analyze verify` on the unit files and by Unit 7's install (daemon-reload + `list-timers` showing both timers scheduled with a next-run).

**Verification:** `systemd-analyze verify` reports no errors; after install, `systemctl list-timers` shows both timers with a future trigger.

---

- [ ] **Unit 6: Monthly Cloudflare-IP refresh timer + wrapper**

**Goal:** Refresh the nginx Cloudflare-IP allowlist monthly against the live served file, verify through the proxy, and alert on failure.

**Requirements:** R6

**Dependencies:** Unit 3 (`discord-notify.sh`).

**Files:**
- Create: `deploy/cf-refresh-wrapped.sh` (calls `refresh-cloudflare-ips.sh /etc/nginx/sites-enabled/leafbind`; on non-zero exit posts 🔴 with the 1/2/3 meaning; on success does a through-CF verify then posts a quiet 🟩)
- Create: `deploy/refresh-cloudflare-ips.service`, `deploy/refresh-cloudflare-ips.timer`

**Approach:**
- Pass the **explicit** live path `/etc/nginx/sites-enabled/leafbind` (the script defaults to `sites-available`, the wrong file).
- After a successful rewrite+reload, verify a real request **through** CF (`https://api.leafbind.io/health`, `?cb=$(date +%s)`, expect 200) so a drift that 403s legitimate proxied traffic is caught — do not rely on a local-only curl.
- `*.service` runs as root; `*.timer` `OnCalendar=monthly`, `Persistent=true`.

**Patterns to follow:** `refresh-cloudflare-ips.sh` exit-code header (1 fetch / 2 sentinels / 3 nginx -t); `discord-notify.sh`.

**Test scenarios:**
- Happy path: monthly run rewrites the allowlist, `nginx -t` passes, reload succeeds, through-CF probe returns 200 → quiet 🟩.
- Error path (fetch fail, exit 1): Cloudflare IP endpoints unreachable → 🔴 "fetch failure".
- Error path (sentinels missing, exit 2): target file lacks `# BEGIN/END CLOUDFLARE IPS` → 🔴 "sentinels not found", file untouched.
- Error path (nginx -t fail, exit 3): rewritten config invalid → 🔴 "nginx -t failed; not reloaded".
- Integration: after a successful local reload, the through-CF probe still 403s/fails → 🔴 "reloaded but origin probe failed — possible IP drift".

**Verification:** `shellcheck` clean; `--dry-run` of `refresh-cloudflare-ips.sh` against the repo `nginx.conf` exercises the exit-3 path; staged live run posts the right Discord line.

---

- [ ] **Unit 7: `deploy/install-autodeploy.sh` idempotent installer**

**Goal:** One command on the VM installs/refreshes everything and validates the CF target before enabling timers.

**Requirements:** R1, R3, R6

**Dependencies:** Units 3-6.

**Files:**
- Create: `deploy/install-autodeploy.sh`

**Approach (idempotent):**
1. Copy the three pairs of unit files to `/etc/systemd/system/`.
2. Create `/var/lib/ebookweb-autodeploy/` (state dir) and `/etc/ebookweb-autodeploy.env` (`0600`, stub with a `DISCORD_DEPLOY_WEBHOOK_URL=` placeholder) **only if absent** — never overwrite a real secret.
3. Copy/refresh `refresh-cloudflare-ips.sh` + wrapper to their VM location.
4. **CF target validation (fail loudly):** confirm `/etc/nginx/sites-enabled/leafbind` exists, contains the `# BEGIN/END CLOUDFLARE IPS` sentinels, and is included in `nginx -T` output.
5. `systemctl daemon-reload`; enable + start the three timers.
6. Print `systemctl list-timers` for the new units.

**Patterns to follow:** `set -euo pipefail`; explicit `exit N` + `>&2`; never commit/echo secrets (credential-write guard).

**Test scenarios:**
- Happy path: clean VM → units copied, state dir + `0600` env stub created, CF validation passes, timers enabled, `list-timers` printed.
- Edge case (idempotent re-run): re-running with a real `/etc/ebookweb-autodeploy.env` present → env file is **not** overwritten; timers re-enabled without error.
- Error path (CF target missing/no sentinels/not in nginx -T): installer fails loudly with a clear message and does **not** enable the CF timer against a wrong/missing file.
- Edge case (permissions): created env file is `0600` root-owned.

**Verification:** `shellcheck` clean; staged install on the VM enables timers and the CF-validation gate blocks on a deliberately-wrong path.

---

- [ ] **Unit 8: Docs + rollout runbook**

**Goal:** Document the auto-deploy system, the manual-deploy-via-`--force` rule, and the webhook setup; capture the VM bring-up sequence.

**Requirements:** R3, R4, R5

**Dependencies:** Units 1-7.

**Files:**
- Modify: `deploy/README.md` (new "Automated deploy" section: how the timer works, **use `autodeploy.sh --force`, never bare `deploy.sh`, while the timer is enabled**, the `/etc/ebookweb-autodeploy.env` webhook setup step, the heartbeat/alert behavior, and the monthly CF refresh).

**Approach:**
- Document the rollout ordering: Unit 1 (branch protection) must be enabled before the timer is enabled on the VM. Document the `git`-based VM bring-up (run `install-autodeploy.sh`, paste the real webhook URL into `/etc/ebookweb-autodeploy.env`, confirm `list-timers`).

**Test scenarios:**
- Test expectation: none (documentation). Reviewed for accuracy against the implemented scripts and the `leafbind-vm-ops-facts` ground truth.

**Verification:** README steps reproduce a working install when followed on the VM.

## System-Wide Impact

- **Interaction graph:** New systemd timers → `autodeploy.sh` → `deploy.sh` → `systemctl restart ebookweb`. New monthly timer → `refresh-cloudflare-ips.sh` → `nginx -s reload`. Discord webhook is the only outbound side effect; it is best-effort and cannot block a deploy.
- **Error propagation:** Deploy failures roll back inside `deploy.sh` (local health gate) and surface as 🔴 Discord (deduped). Notification failures degrade to journald, never abort. Through-CF probe failure annotates but does not roll back.
- **State lifecycle risks:** `flock` prevents overlapping deploys (timer vs `--force`). Dedupe state file is the only persistent runtime state; a corrupt/missing state file degrades to "post the alert" (fail-safe toward visibility).
- **API surface parity:** None — no app endpoints change. `/health` contract is consumed read-only.
- **Integration coverage:** The decision matrix (no-change / deploy / dirty / diverged / fetch-fail / deploy-fail / dedupe / lock / dry-run / force / through-CF) is enumerated in Unit 4 test scenarios — these are the cross-layer behaviors mocks alone won't prove.
- **Unchanged invariants:** `deploy.sh`'s root/`sudo -u joe`/rollback contract is preserved (only the health window widens). The app systemd unit, `/etc/web_service.env`, and the frontend deploy path are untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Auto-deploy ships a bad commit to prod unattended | `master` branch-protected (PR-required) so commits are reviewed; `deploy.sh` health-gates + rolls back; 🔴 Discord on failure. |
| `master` auto-executes on prod with no required checks | Accepted trade-off (path-filtered checks would deadlock infra PRs); checks still run + are visible on app PRs; solo maintainer self-reviews. Documented in Key Decisions. |
| Silent dead timer (the EB-324 failure mode) | Daily heartbeat + `systemctl` failed state surface a stalled timer within a day. |
| Discord webhook URL leaked into git | Stored only in `/etc/ebookweb-autodeploy.env` (`0600`, never committed); installer creates a stub, not the secret; credential-write guard blocks accidental commits. |
| CF-IP refresh rewrites the wrong nginx file | Wrapper passes the explicit `/etc/nginx/sites-enabled/leafbind`; installer validates the file exists, has sentinels, and is in `nginx -T`. |
| CF-IP drift silently 403s proxied traffic | Monthly run verifies through the CF proxy, not just a local curl. |
| Alert spam every 5 min on a persistent failure | Dedupe state: post on transition + ~3h re-nag only. |
| Merge conflict with frozen PR #153 on `deploy.sh` | EB-331 branches off #153; merge order #153 → rebase → EB-331. |
| No bash test framework in repo | Logic units tested via `shellcheck` + a throwaway-git-repo decision-matrix test (bats or plain shell); unit files via `systemd-analyze verify`; declarative/doc units carry `Test expectation: none`. |

## Documentation / Operational Notes

- **Rollout ordering:** (1) merge PR #153; (2) merge EB-331 PR; (3) enable `master` branch protection (Unit 1); (4) on the VM: run `install-autodeploy.sh`, paste the real `DISCORD_DEPLOY_WEBHOOK_URL` into `/etc/ebookweb-autodeploy.env`, confirm `systemctl list-timers`; (5) staged smoke: merge a trivial PR (direct pushes are blocked after step 3), then watch the next tick deploy it + post the 🟩 Discord line.
- **VM access:** Tailscale node `claude-dev-01` (`100.68.98.58`), `ssh root@` — per `leafbind-vm-ops-facts` memory.
- **`ce:compound`:** on completion, write a net-new `docs/solutions/best-practices/` entry (e.g. `vm-pull-deploy-timer-and-cloudflare-ip-refresh-2026-05-22.md`) — no existing solution covers systemd timers / pull-deploy / VM Discord posting / monthly CF-IP refresh.
- **Worktree policy:** `deploy/**` is NOT exempt — all new files land via the EB-331 worktree branch and a PR (never direct to `master`).

## Parallelization Map

**N/A.** Units are sequential and dependency-ordered (Unit 3 → 4 → 5/6 → 7 → 8; Unit 1 is an independent ops prerequisite gating rollout, not code). This plan is not running through the INFRA-216 subagent swarm pilot, so per the v1 scope no Parallelization Map is required.

## Sources & References

- **Origin document:** [docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md](docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md)
- Related code: `deploy/deploy.sh`, `deploy/refresh-cloudflare-ips.sh`, `deploy/web_service.service`, `.github/workflows/web-tests.yml`, `.github/workflows/frontend-e2e.yml`
- Related PRs/issues: PR #153 (`fix/EB-331-deploy-path-reconciliation`), EB-324, EB-330, EB-7
- Learnings: `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md`, `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md`, `docs/solutions/eb252-next-plausible-next16-compat.md`, `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md`
- Memory: `leafbind-vm-ops-facts` (VM access, paths, deploy sequence)
