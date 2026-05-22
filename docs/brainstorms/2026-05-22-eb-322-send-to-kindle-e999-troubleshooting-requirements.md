---
title: "EB-322 — Send-to-Kindle E999 troubleshooting page"
type: requirements
status: ready-for-planning
date: 2026-05-22
ticket: EB-322
parent: EB-303 (Phase 3b — decided first launch, 2026-05-22)
predecessor: EB-241 (Phase 2 — shipped)
source_research: docs/seo/eb-241-semrush-trial-sprint-2026-05.md (Findings L, Q, R, Z, AA)
---

# EB-322 — Send-to-Kindle E999 troubleshooting page

## Problem / opportunity

The EB-308 Semrush trial sprint identified the Send-to-Kindle error-code cluster as the
**highest-leverage opportunity in the entire dataset** (Finding R): a wide-open SERP with
peak commercial intent. A failed Send-to-Kindle is the exact moment a user reaches for a
third-party tool like leafbind.

| Pain keyword | US volume | Notes |
|---|---|---|
| e999 - send to kindle internal error | 2,900 | Flagship; users copy-paste the code mid-task |
| e999 - send to kindle internal error: (colon) | 2,400 | **Same SERP** — Google dedupes (Finding Z) |
| an authentication failure occured send to kindle app | 1,000 | KD=0 (no SERP signal — needs manual review) |
| send to kindle doesn't work | 480 | Amazon's STK landing ranks #3 here (Finding AA) |

**e999 cluster = ~5,300/mo on a single SERP** (colon variant dedupes), KD 15–25 (Finding Q).
The e999 SERP has **zero authoritative sources** in the top 20 (Amazon UK Help at #15 only),
13 forum/Q&A results, 5 small ad-monetized troubleshooting blogs, and **zero conversion-tool
competitors** (Finding R). No existing page combines a definitive fix guide with a
conversion-tool fallback.

## Users & search intent

A user mid-failure: they tried Send-to-Kindle, hit `E999 internal error` (or an auth failure,
or silent non-delivery), and pasted the error into Google looking for an **immediate fix**.
High frustration, high intent, low patience. They want (1) what the error means, (2) concrete
diagnostic steps, and (3) a way out if the fixes don't apply.

## Decisions (resolved in this brainstorm, 2026-05-22)

1. **Architecture: separate dedicated page.** Not an expansion of Unit 2
   (`/guides/send-to-kindle-not-working`). Unit 2 is symptom-organized (7 fixes, 260/mo); this
   page is **error-code-organized** (5,300/mo). Different SERP intent — error-code lookup vs
   symptom browsing. Confirmed Unit 2 currently contains zero `e999` mentions, so the cluster
   is genuinely uncovered.
2. **URL slug: `/guides/send-to-kindle-error-e999`.** Foregrounds the error code per Finding AA
   (Amazon's authority is weakest on the error-code-specific SERP). Distinct from Unit 2's
   `not-working` stem to avoid near-duplicate signal.
3. **Auth-failure section: include, but exclude from the ranking gate.** Full H2 section (real
   STK failure mode, rounds out topical authority, PAA/AIO-eligible), but the 1,000/mo keyword
   has KD=0 (no SERP signal) — counted as a bonus pending manual SERP review, not a launch target.
4. **`send to kindle doesn't work` (480/mo): secondary H3 anchor only.** Amazon's STK landing
   sits at #3 on that SERP (Finding AA); the page title/H1 must NOT foreground this phrasing.
5. **Unit 2 untouched in this PR** (EB-322 non-goal). New page links **to** Unit 2 ("general
   Send-to-Kindle fixes"); the reciprocal link from Unit 2 → this page is a deferred follow-up.

## Content structure

- **H1 / title:** foreground "E999" + "internal error". (Title ≤ 60 chars.)
- **Lede (≥ 300 words):** what E999 means (Amazon's generic internal-error response covering
  oversize, malformed file, DRM, transient server-side conversion failure); what auth-failure
  means; what "doesn't work" silent failures look like. Cite Amazon's official STK help page.
- **H2 — E999 internal error** → H3 sub-anchors: oversize file (50 MB email / 200 MB web),
  malformed EPUB (strict XHTML/manifest validation), DRM-protected file (silently rejected),
  transient server-side conversion failure.
- **H2 — Authentication failure (Send-to-Kindle app)** → token expiry (sign out/in), region
  mismatch, MFA prompt swallowed, app version too old.
- **H2 — "Doesn't work" silent failures** → accepted-but-never-appears (~24h window), wrong
  destination device, sync paused, kindle.com vs free.kindle.com confusion.
- **CTA (honest, R4 discipline):** route fixable cases to the fixes (most users don't need
  leafbind); route the **unfixable subset** (size cap, malformed, DRM) to leafbind's hosted
  PDF→KFX workflow as the "skip Send-to-Kindle entirely" path. No overselling.
- **JSON-LD:** Article + FAQPage schema (Phase 2 precedent).
- **AIO/PAA formatting:** each error section standalone-citable; first-line definitive answer.

## Scope boundaries (non-goals)

- No expansion of Unit 2 in this PR.
- No DRM stripping/removal instructions — describe Amazon's behavior only (legal-sensitivity
  boundary, same as EB-320).
- No Amazon-account-recovery copy — STK auth failures sometimes route to broader Amazon-account
  issues; do not scope leafbind into Amazon-account troubleshooting.
- No backlink outreach (Phase 4 / EB-309).
- No Position Tracking reconfiguration — adding the e999 keyword is a separate manual Joe action
  in the Semrush web UI.

## Success criteria

- Single page shipped at `/guides/send-to-kindle-error-e999`, one PR, same-PR hygiene per EB-295
  (sitemap + llms.txt + Footer/guides-hub link).
- Article + FAQPage JSON-LD validated against Google Rich Results Test.
- Pre-merge: link-check CI green, schema-validator pass (2-layer pattern).
- Post-merge: indexed within 14 days; EB-292 attribution smoke confirms `referrer` captures the
  new path.
- **Ranking gate, primary (60 days):** top-50 for ≥ 2 of {e999 internal error, send to kindle
  doesn't work}. (Auth-failure excluded — KD=0.)
- **Ranking gate, stretch (120 days):** top-20 for the e999 flagship.

## Open / deferred items

- **Manual SERP review** of `an authentication failure occured send to kindle app` (KD=0) to
  decide whether it deserves its own ranking target later.
- **Reciprocal internal link** Unit 2 → this page (deferred follow-up; out of this PR).
- **Position Tracking keyword add** (`e999 - send to kindle internal error`) — manual Joe action,
  web UI; fills the free-tier slot to 10/10 alongside `does kindle support epub` (per EB-303
  decision comment 2026-05-22).

## References

- EB-322 ticket (content shape, AC, Unit 2 overlap analysis)
- EB-303 Phase 3b decided launch sequence (2026-05-22) — this is the **first** page
- Unit 2 precedent: `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx`
- EPUB-pillar plan (architecture inheritance): `docs/plans/2026-05-17-001-feat-eb-320-epub-on-kindle-pillar-plan.md`
- Trial synthesis: `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` (Findings L, Q, R, Z, AA)
