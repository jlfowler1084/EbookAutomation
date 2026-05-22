# EB-331 — VM auto-deploy (pull-model systemd timer)
# Model: SONNET
# Justification: Multi-file, well-specified implementation following a structured plan and an approved design spec. Sonnet handles structured, plan-driven work well; the architecture decisions are already locked.

## Tickets

- **Primary:** EB-331 -- VM deploy automation: pull-model systemd auto-deploy for the ebookweb backend
- **Blocks:** None
- **Relates to:** EB-330 (Done), EB-324 (the drift incident), EB-7 (Cloud Infra epic), PR #153 (frozen base branch)

## Estimated Scope

Multi-file change -- ~9 new files (1 bash helper, 1 wrapper script, 6 systemd units, 1 installer) + 2 modified files (`deploy/deploy.sh`, `deploy/README.md`). Code-only; no VM deployment this session.

---

## Phase 0 -- Branch Setup

**Branch:** `worktree/EB-331-vm-autodeploy`
**Base:** `fix/EB-331-deploy-path-reconciliation` (NOT master — see Context)
**Worktree Mode:** create

Before any other work:

1. `git fetch origin`
2. Confirm the base branch exists: `git branch -a | grep fix/EB-331-deploy-path-reconciliation`
3. Create worktree off the #153 branch: `git worktree add .worktrees/EB-331-vm-autodeploy -b worktree/EB-331-vm-autodeploy fix/EB-331-deploy-path-reconciliation`
4. `cd .worktrees/EB-331-vm-autodeploy`
5. Confirm branch: `git branch --show-current` → `worktree/EB-331-vm-autodeploy`
6. Confirm the reconciled `deploy/deploy.sh` is present (paths `/home/joe/EbookAutomation`, runs as root, has the rollback block) and `.gitattributes` carries `*.sh text eol=lf`. If `deploy.sh` still shows the old `/opt/ebookautomation` paths, STOP — the base branch is wrong.

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at: `docs/plans/2026-05-22-002-feat-eb331-vm-autodeploy-plan.md`
Read the approved design spec at: `docs/superpowers/specs/2026-05-22-eb331-vm-autodeploy-design.md`

This implements a pull-model auto-deploy on the production Hetzner VM: a systemd timer runs `deploy/autodeploy.sh`, which fetches, guards, detects change, and delegates the actual deploy to `deploy/deploy.sh`. It posts to Discord (alert-on-trouble + daily heartbeat) and adds a monthly Cloudflare-IP nginx refresh. The plan's 8 units are authoritative; this prompt adds the gotchas that aren't obvious from the plan alone.

**Design decisions made during planning:**
- **Pull model, not push** — all credentials stay on the VM; GitHub is untouched. The wrapper does NOT reimplement deploy logic; it delegates to `deploy.sh`.
- **Local health is the rollback gate; the through-CF probe is annotation only.** `deploy.sh`'s `127.0.0.1:8001/health` poll decides rollback. `autodeploy.sh` additionally probes `https://api.leafbind.io/health` (through Cloudflare) only to report *verified* state on the Discord success line — a failed through-CF probe downgrades the message to ⚠️ but does NOT trigger rollback.
- **Branch protection = require PR + block direct push, NO required status checks** (rationale below).

**Options considered and rejected:**
- Push model (GitHub Actions → SSH/Tailscale) — rejected to keep secrets off GitHub.
- Reusing the existing `discord-webhook` skill — rejected: it's a PowerShell/Windows helper that cannot run on the Linux VM.
- Requiring the CI checks in branch protection — rejected: they're paths-filtered (see below).

**Hidden constraints or gotchas:**
- **Discord helper must be NET-NEW bash.** The `discord-webhook` skill is PowerShell-only and Windows-resident. Build `deploy/discord-notify.sh` fresh, but reuse the embed shape + color ints from `C:\Users\Joe\.claude\skills\discord-webhook\references\message-formats.md`: red `15158332`, green `3066993`, yellow `16776960`, info `9807270`. Payload shape: `{"embeds":[{"color":<int>,"title":"[<event>] EbookAutomation","description":"<msg>","footer":{"text":"<ISO-8601 UTC>"}}]}`. Posting is best-effort: missing webhook or a failed POST logs to journald and returns 0 — NEVER blocks a deploy.
- **The CI checks are `paths:`-filtered.** `web-tests.yml` (status context `pytest tests/test_web_*.py`) and `frontend-e2e.yml` (`playwright (chromium)`) only fire on `web_service/**` / `tests/**` changes. A deploy-only PR won't trigger them — which is why branch protection must NOT require them (a required-but-never-run check deadlocks the merge). Branch protection itself is a rollout step, not this session's work.
- **`deploy/**` is NOT worktree-exempt.** Per `.claude/worktree-policy.json`, all new `deploy/*.sh`, `*.service`, `*.timer`, and the installer must be created on the worktree branch and land via PR — never committed to master.
- **`deploy.sh` runs as root**, with git/pip via `sudo -u joe` and `git -c safe.directory=/home/joe/EbookAutomation`. The `autodeploy.sh` wrapper that calls it also runs as root. Match this model.
- **`refresh-cloudflare-ips.sh` defaults to the WRONG nginx file** (`/etc/nginx/sites-available/leafbind`). The live served file is `/etc/nginx/sites-enabled/leafbind` (a regular file, not a symlink). The CF wrapper MUST pass the explicit `/etc/nginx/sites-enabled/leafbind` path argument.
- **`api.leafbind.io` is Cloudflare-proxied (orange-cloud).** A drifted nginx CF-IP allowlist silently 403s real traffic, so the monthly refresh verifies through the proxy (use `?cb=$(date +%s)`; the CF token lacks `cache_purge` scope).

---

## What NOT To Do

### Standing Rules (do not modify)

- **Do not commit directly to master.** This repo is under worktree-policy enforcement (`protected_branches: ["master"]`). All commits go on the Phase 0 worktree branch, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only for human emergency override. If a guard blocks an action, stop and report the block -- do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block as a false positive, do not attempt alternative commands to circumvent the guard.
- **Ambiguous user phrasing is not authorization to bypass.** "Ship it", "just commit it", "go ahead" are never authorization to bypass workflow rules. Authorization requires an explicit instruction naming the specific rule being bypassed. When in doubt, stop and ask.
- **Enforcement code is not exempt.** Edits to hooks, guards, or `worktree-policy.json` follow the same branch-and-PR workflow.

### Session-Specific Prohibitions

- **Code-only this session.** Do NOT SSH to the VM, deploy, run the installer on the box, enable any timer, or enable branch protection. Those are rollout steps for a human after merge. You write and verify the artifacts; you do not install them.
- **Never commit the Discord webhook URL or any secret.** `/etc/ebookweb-autodeploy.env` is created as a `0600` stub by the installer with a placeholder only; the real URL is pasted by hand on the VM. The credential-write guard will block secret writes — do not work around it.
- **Branch off `fix/EB-331-deploy-path-reconciliation`, never master.** Do not modify any of PR #153's files EXCEPT the two carried fix-ups in Unit 2 (`deploy/deploy.sh` health poll, `deploy/README.md` typo). #153 stays frozen otherwise.
- **No `mklink /J` junctions into the worktree** for `archive/`/`output/`/`inbox/`/`processing/` — recursive delete destroys the target (CLAUDE.md hard rule). This is code-only deploy work; you should not need those dirs.
- **Do not skip Unit 1 silently.** Unit 1 (branch protection) is an ops prerequisite, not code — note it in your final report as a human rollout step; do not attempt to execute it.

---

## Phase 1 -- Audit (READ-ONLY, STOP FOR REVIEW)

Read and confirm before writing anything:

1. Read the plan and spec in full.
2. Read the reconciled `deploy/deploy.sh` (the wrap target) and confirm its contract: root, `sudo -u joe`, `git -c safe.directory`, health check, rollback, `exit 1`. Note the exact current health-check lines (the `sleep 3` + single `curl -sf`) you'll replace in Unit 2.
3. Read `deploy/refresh-cloudflare-ips.sh` header (Usage + exit codes 1/2/3 + sentinel markers) and `deploy/web_service.service` (house style: `Description=`, `SyslogIdentifier=`, journal output).
4. Read `C:\Users\Joe\.claude\skills\discord-webhook\references\message-formats.md` for the embed shape + colors.
5. Read `.claude/worktree-policy.json` to confirm `deploy/**` is not exempt.
6. Confirm `shellcheck` is available locally (`shellcheck --version`); if not, note that static analysis will rely on `bash -n` only and flag it.

**Success criteria:**
- You can state the `deploy.sh` health-check lines to change, the Discord embed/colors to reuse, and the systemd house style to match.

**STOP.** Report findings before proceeding.

---

## Phase 2 -- Unit 2: deploy.sh health poll + README typo

Modify `deploy/deploy.sh`: replace `sleep 3` + single `curl -sf` with a poll loop (probe `/health` every ~3s up to ~45s before declaring failure → existing rollback). Preserve the rest of the contract (HTTP-200-only via `curl -sf`, no body assertion). Fix `deploy/README.md` (~line 124-125): `"not /etc/web_service.env"` → `"not /opt/ebookautomation/.env"`.

**Success criteria:** `shellcheck deploy/deploy.sh` clean; `bash -n` parses; README reads consistently.

**STOP.** Report the diff.

---

## Phase 3 -- Unit 3: deploy/discord-notify.sh

Create the net-new best-effort helper (embed shape + color ints above; reads `$DISCORD_DEPLOY_WEBHOOK_URL`; logs-and-returns-0 on any failure or missing var).

**Success criteria:** `shellcheck` clean; a stub-webhook test confirms embed shape/color and non-blocking return-0 on all failure inputs (per plan Unit 3 scenarios).

**STOP.** Report.

---

## Phase 4 -- Unit 4: deploy/autodeploy.sh

Create the tick wrapper: `flock`, explicit `git fetch --prune origin +refs/heads/master:refs/remotes/origin/master`, change detection, preflight guards (branch/clean/`--is-ancestor`), delegate to `deploy.sh`, post-deploy SHA + count, through-CF annotation, dedupe state in `/var/lib/ebookweb-autodeploy/`, modes `--force` / `--emergency-bypass` / `--heartbeat` / `--dry-run`. Implement the full decision matrix in plan Unit 4.

**Execution note:** Start with a failing test for the change-detection + preflight decision matrix against a throwaway local git repo (no VM needed), then wire the `deploy.sh` call.

**Success criteria:** `shellcheck` clean; decision-matrix test passes against a temp git repo (no-change silent, deploy posts, dirty-tree blocks, dedupe, lock, dry-run uses `ls-remote`).

**STOP.** Report.

---

## Phase 5 -- Unit 5: systemd units (autodeploy + heartbeat)

Create `deploy/ebookweb-autodeploy.service` + `.timer` (`OnBootSec=2min`, `OnUnitActiveSec=5min`) and `deploy/ebookweb-heartbeat.service` + `.timer` (daily). `Type=oneshot`, root, `EnvironmentFile=/etc/ebookweb-autodeploy.env`, `Wants=`/`After=network-online.target`, journal output.

**Success criteria:** `systemd-analyze verify` reports no errors against the unit files.

**STOP.** Report.

---

## Phase 6 -- Unit 6: monthly Cloudflare-IP refresh

Create `deploy/cf-refresh-wrapped.sh` (calls `refresh-cloudflare-ips.sh /etc/nginx/sites-enabled/leafbind`; through-CF verify; 🔴 on exit 1/2/3, quiet 🟩 on success) + `deploy/refresh-cloudflare-ips.service` + `.timer` (`OnCalendar=monthly`).

**Success criteria:** `shellcheck` clean; `refresh-cloudflare-ips.sh --dry-run` against the repo `nginx.conf` exercises the exit-3 path; `systemd-analyze verify` clean.

**STOP.** Report.

---

## Phase 7 -- Unit 7: install-autodeploy.sh

Create the idempotent installer (copy units, create state dir + `0600` env stub only-if-absent, copy CF scripts, **CF target validation** via sentinels + `nginx -T`, `daemon-reload`, enable timers, print `list-timers`).

**Success criteria:** `shellcheck` clean; logic review confirms idempotency and that the env stub is never overwritten when present.

**STOP.** Report.

---

## Phase 8 -- Unit 8: docs / runbook

Update `deploy/README.md` with the "Automated deploy" section (timer behavior, **use `autodeploy.sh --force`, never bare `deploy.sh` while the timer is enabled**, webhook env setup, monthly CF refresh, rollout ordering).

**Success criteria:** README steps are accurate against the implemented scripts.

**STOP.** Report.

---

## Rollback Procedures

This session produces files only — nothing is deployed. If a script proves unworkable, revert the file on the branch. The *deployed system's* rollback (health-gated `git reset --hard` in `deploy.sh`) is part of the design, not something to exercise here.

## Smoke Test (DEFERRED to rollout — not this session)

The plan's staged VM scenarios (no-op tick silent, real deploy posts 🟩, dirty-tree preflight blocks, health-fail rollback, dedupe, CF refresh) run on the VM AFTER merge by a human, per the rollout ordering. Do not run them this session.

---

## Phase 9 -- Verification

### Per-file verification
- **Static:** `shellcheck` clean on all new/modified `.sh`; `bash -n` parses; `systemd-analyze verify` clean on all unit files; the autodeploy decision-matrix test passes against a temp git repo.
- **Runtime:** N/A this session (VM deploy is deferred to rollout).

---

## Phase 10 -- Commit and Push

**STOP before committing.** Report all files to the strategist.

After approval:

1. Stage explicitly (no `git add .`): list each created/modified file.
2. Commit: `git commit -m "feat(EB-331): pull-model VM auto-deploy (timer + wrapper + Discord + CF refresh)"` (separate commits per logical unit are encouraged).
3. Push: `git push -u origin worktree/EB-331-vm-autodeploy`
4. **STOP before opening PR.**

---

## Verification Checklist

- [ ] Branch created via `git worktree add` off `fix/EB-331-deploy-path-reconciliation`; all work in the worktree
- [ ] No commits to master; no bypass env vars used
- [ ] Phase 1 audit completed before any file creation
- [ ] No secret (webhook URL) committed; env file is a stub only
- [ ] PR #153's files untouched except the 2 Unit-2 fix-ups
- [ ] `shellcheck` + `systemd-analyze verify` clean; decision-matrix test passes
- [ ] Branch pushed but PR NOT yet opened

---

## Report Structure

At each STOP gate, report:
1. **Findings** -- what was discovered or changed
2. **Assumptions changed** -- anything contradicting the plan or this prompt
3. **Options** -- alternatives at any decision point
4. **Recommendation** -- your recommended path, with rationale

At final completion, also:
5. **Commit hashes**
6. **Out-of-scope findings** -- follow-up tickets (incl. the human rollout steps: merge order, enable branch protection, run installer on the VM, paste webhook URL)

---

## Invocation

```
claude --model sonnet "[EB-331] Implement pull-model VM auto-deploy -- Read prompts/EB-331-vm-autodeploy.md and follow the instructions"
```
