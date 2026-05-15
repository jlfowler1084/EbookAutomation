---
ticket: EB-257
date: 2026-05-15
author: Joe Fowler
tags: [vercel, deploy, infra, production-branch, leafbind, frontend]
module: web_service/frontend
problem_type: silent-misconfig
related:
  - EB-252 (Plausible analytics — surfaced this bug during post-deploy verification)
  - vercel-deploy-verification skill (~/.claude/skills/vercel-deploy-verification/SKILL.md)
  - CareerPilot CAR-209/210/211 (different root cause, same outcome — `production-alias-stuck`)
---

# Vercel Production Branch misconfiguration — leafbind.io master pushes landing as Preview

## Symptom

Frontend commits merged to `master` were silently shipping as `target: preview` instead of `target: production`. The `leafbind.io` and `www.leafbind.io` aliases stayed pinned to a stale build while master moved 7+ commits ahead. `Vercel: success` showed green on every PR check because the deployments WERE successful — they just weren't promoted to production.

Affected window: 2026-05-14 16:04 UTC (project creation) through 2026-05-15 13:24 EDT (manual `vercel promote` of EB-252 fix). Roughly 21 hours.

Affected tickets that silently sat unshipped: EB-238 (Lora font preload), EB-243 (premium repositioning), EB-252 (Plausible analytics).

## Root cause

The Vercel `leafbind` project's `link.productionBranch` was set to `main`. The `EbookAutomation` repo uses `master` as its production branch. Mismatch → no auto-promotion.

The misconfiguration was created at project initialization. Vercel's project-create flow appears to default `productionBranch` to `main` regardless of what the repo's actual default branch is. The CLI's `vercel project inspect` does NOT display `productionBranch`, so the mismatch was invisible to the surface-level check the vercel-deploy-verification skill prescribes.

## How it was diagnosed

This is the documented diagnosis chain so future similar incidents resolve faster:

1. **Initial signal:** EB-252 post-deploy verification (`curl https://leafbind.io/` then grep for Plausible script tag) returned no script — but `POST /api/event` proved the fix was deployed somewhere. Contradiction.
2. **Vercel CLI list:** `npx vercel ls leafbind --scope <team>` showed exactly ONE `Production` row (3h old) and ~12 subsequent `Preview` rows. All Preview deploys had healthy build durations (14-21s, not 0ms ghost), so this is NOT the CAR-209/210/211 Root Directory pattern.
3. **Alias inspection:** `npx vercel inspect <prod-url> --scope <team>` confirmed `leafbind.io` aliased to the 3h-old `dpl_8kc15tE2JV5smaC3QQiW5SK7QdA9`. The latest preview shared the `leafbind-git-master-...` alias but NOT the `leafbind.io` alias.
4. **CLI-side dead end:** `npx vercel project inspect` doesn't show `productionBranch`. Confirmed via running it on the leafbind project — output stops before the field is reached.
5. **REST API confirms diagnosis:** `GET /v9/projects/<id>` returns `link.productionBranch: 'main'` — the explicit mismatch.

## The fix that worked

**Dashboard (the only path):**

1. Open https://vercel.com/jlfowler1084s-projects/leafbind/settings/git
2. Under "Production Branch", change `main` → `master`
3. Click Save
4. Verify: re-run `GET /v9/projects/<id>` via REST API, confirm `link.productionBranch: 'master'`

**Reason the API path doesn't work:** Vercel's documented REST API endpoints for project management do not expose `productionBranch` as an editable field. All four attempts during EB-257 failed:

```bash
# Returns 400: "should NOT have additional property `link`"
curl -X PATCH /v9/projects/<id> -d '{"link":{"productionBranch":"master"}}'

# Returns 400: "should NOT have additional property `productionBranch`"
curl -X PATCH /v9/projects/<id> -d '{"productionBranch":"master"}'

# Returns 400: "should NOT have additional property `gitProductionBranch`"
curl -X PATCH /v9/projects/<id> -d '{"gitProductionBranch":"master"}'

# Returns 200, response shows project state, but `productionBranch` unchanged
curl -X POST /v9/projects/<id>/link -d '{"type":"github","repo":"...","productionBranch":"master"}'

# Even DELETE + POST sequence: link gets recreated with the same productionBranch
```

If a future Vercel API release adds support, prefer the API. Until then: dashboard.

## Post-fix verification

After flipping the dashboard setting, do NOT trust that it took effect — verify programmatically:

```bash
TOKEN=$(python -c "import json; print(json.load(open(r'C:\\Users\\Joe\\AppData\\Roaming\\com.vercel.cli\\Data\\auth.json'))['token'])")
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.vercel.com/v9/projects/prj_0hRzHdEk7usKdJnZ6PjcFmK6WTbm?teamId=team_CLMfllQxa3BgT7JdiGll4c6y" \
  | python -c "import json,sys; print('productionBranch:', json.load(sys.stdin).get('link',{}).get('productionBranch'))"
# Expect: productionBranch: master
```

Then push a trivial commit to master (the post-fix docs commit qualifies) and verify the new deploy lands as `Production`:

```bash
npx vercel ls leafbind --scope team_CLMfllQxa3BgT7JdiGll4c6y | head -3
# Expect: top row shows "Production" environment, not "Preview"
```

## How to avoid this on the next Vercel project

Add to project-creation runbook (whenever spinning up a new Vercel project):

1. Create the project as usual
2. **Immediately after, set Production Branch explicitly via dashboard** — do not trust the default. Even if your repo's default branch IS `main`, set it explicitly so the next maintainer can see it was a deliberate choice.
3. **Push a no-op commit** (a docs change to the README, a typo fix) and verify it lands as `Production` in `vercel ls`. This is the only proof the wire-up works.
4. Record the verified `productionBranch` value in `docs/solutions/` for the project.

This is the same lesson as CAR-209/210/211: **the Vercel UI / GitHub status check is not a reliable shipping signal — only `vercel ls` build duration + target column tells the truth.**

## Why this extends the vercel-deploy-verification skill

The existing skill at `~/.claude/skills/vercel-deploy-verification/SKILL.md` covers the Root Directory misconfiguration (0ms ghost builds). This incident is a **different** failure mode with the same outcome (production-alias-stuck): builds are real (~17s), they just have the wrong `target`. The skill's verification ritual catches both — step 2 ("real build duration") is fine, step 4 ("alias on the new deployment row") catches this one.

Worth adding to the skill: a note that the `productionBranch` field is NOT visible via `vercel project inspect` CLI and requires REST API or dashboard to inspect. The current skill doesn't mention this gap.

## References

- vercel-deploy-verification skill: `~/.claude/skills/vercel-deploy-verification/SKILL.md`
- Original incident (different root cause, same symptom): `F:\Projects\CareerPilot\docs\solutions\best-practices\vercel-deploy-verification.md`
- EB-252 verification comment (the surfacing context): https://jlfowler1084.atlassian.net/browse/EB-252
- EB-257 ticket: https://jlfowler1084.atlassian.net/browse/EB-257
- Vercel project ID: `prj_0hRzHdEk7usKdJnZ6PjcFmK6WTbm`
- Vercel team ID: `team_CLMfllQxa3BgT7JdiGll4c6y`
