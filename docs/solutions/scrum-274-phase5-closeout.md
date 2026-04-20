---
title: SCRUM-274 Phase 5 close-out — what shipped vs what was planned
type: close-out
status: partial
date: 2026-04-20
origin_ticket: SCRUM-274
origin_plan: docs/plans/2026-04-13-001-local-llm-visual-qa.md
related_tickets: [SCRUM-275, SCRUM-279, SCRUM-280, SCRUM-281, SCRUM-282, SCRUM-283, SCRUM-288, SCRUM-289]
tags: [scrum-274, phase-5, closeout, architectural-pivot, cloud-primary, fingerprint-fallback]
---

# SCRUM-274 Phase 5 close-out

Closes SCRUM-274 as **partial**. Phases 1–2 shipped as planned; Phases 3–4 were superseded by a different architecture (SCRUM-281 fingerprint-fallback, SCRUM-282 baseline methodology, SCRUM-283 cloud VLM evaluation) that solves the same operational problem — cheap primary pass with judicious expensive re-evaluation — without the full-book compute cost the plan assumed.

## What SCRUM-274 set out to do

The plan's #1 driver was the project's fix-then-regression cycle. Claude Vision at ~$0.10–$0.30/page made full-book scans of a 6-book corpus cost $40–$120 per regression run. The plan proposed a local vLLM Qwen3-VL provider to drop marginal cost to zero and a score-threshold escalation tier that sent low-confidence pages to Claude.

Five phases:
1. Provider abstraction (refactor, `VisionProvider` interface)
2. Local provider (vLLM OpenAI-compatible client against sb-chat)
3. Full-book mode (`--all-pages`, `--batch-size`)
4. Escalation tier (`--escalate-below SCORE`)
5. Baseline + docs, with a go/no-go on promoting local as default

## What actually shipped — and via which tickets

| Phase | Plan status | Reality | Shipping ticket |
|---|---|---|---|
| 1 — Provider abstraction | complete, bit-identical gate passed 2026-04-18 | shipped | SCRUM-274 (commit `0014c1c`) |
| 2 — Local provider | complete (sample mode, calibrated) | shipped with R2 residual | SCRUM-275, SCRUM-279, SCRUM-280 |
| 3 — Full-book mode | **not shipped** | deferred — fingerprint fallback routes cheap primary → expensive judge on known-regression pages without needing every-page local inference | superseded by SCRUM-281 |
| 4 — Escalation tier | **not shipped as planned** | fingerprint-matched fallback replaced score-threshold escalation; different mechanism, same goal | SCRUM-281 |
| 5 — Baseline + docs | this document | — | SCRUM-274 (this commit) |

### Why Phases 3–4 were superseded, not postponed

The plan's operational premise was "make every-page Claude unaffordable → run every page on local → escalate the small fraction Claude still needs to judge." The mechanism is score-threshold routing: run local, keep high-scoring results, re-run low-scoring pages on Claude.

SCRUM-281 landed a different mechanism with the same economic shape: **fingerprint-matched fallback**. Pages whose content signature matches a known-failure corpus are automatically routed to Claude; everything else stays on the cheap primary. The primary became cloud (Qwen3-VL via OpenRouter) rather than local, because cloud inference on a well-calibrated model turned out cheaper per-book than operating the local stack for full-book loads on a workstation that also serves other projects.

The two mechanisms aren't strictly equivalent:
- **Score-threshold escalation** is content-blind — it trusts the primary's own self-grading to decide what to escalate. Reliable only if the primary's score distribution is calibrated against Claude's (the SCRUM-280 R2 gate, which did not pass within the capability ceiling of the local model).
- **Fingerprint fallback** is content-aware — it routes based on learned pattern recognition of the pages where the primary is known to get things wrong. It doesn't need the primary's score to be calibrated in absolute terms; it needs the fingerprint corpus to cover the regression-interesting surface.

For the project's actual need — "don't let a regression slip past VQA on books we know about" — fingerprint fallback is more directly aligned than score-threshold escalation. Phase 3's `--all-pages` isn't required to reach that bar.

## Acceptance criteria — final status

The plan's 9 acceptance criteria, mapped to shipped reality:

1. **Zero regression on Claude path.** ✅ MET — bit-identical baseline gate passed 2026-04-18 against 6-book rebuilt corpus. Commit `0014c1c`.
2. **Local provider works.** ✅ MET — schema-valid reports on all 6 books in sample mode. SCRUM-275 Phase 2.
3. **Full-book mode completes without OOM.** ⬜ DEFERRED — no `--all-pages` path shipped. Rolled into SCRUM-289 (backlog).
4. **Escalation tier routes correctly.** ⬜ SUPERSEDED — no `--escalate-below` path shipped. Fingerprint fallback (SCRUM-281) fills the same role via a different mechanism; verified in SCRUM-281 acceptance tests.
5. **Provider abstraction is clean.** ✅ MET — `tools/llm_providers/{base,claude,local,cloud}_provider.py` all under the interface. Adding cloud provider (SCRUM-283) required zero changes to `visual_qa.py` orchestration.
6. **Configuration is declarative.** ✅ MET — `config/settings.json` `visual_qa` block covers provider, cloud_host, cloud_model, local_model, local_base_url, max_pages, pass_threshold, fallback sub-block. Env overrides documented in `.env.example`.
7. **Feature manifest passes.** ⚠️ PARTIALLY MET until this commit — `visual_qa.py` flag list in `feature-manifest.json` was stale (missing `--provider`, `--cloud-host`, `--fallback-enabled`, `--fallback-claude-model`, `--fallback-corpus-path`). This commit updates the manifest; `--all-pages`, `--batch-size`, `--escalate-below` correctly absent because they never shipped.
8. **Baseline comparison documented.** ⚠️ REINTERPRETED — the plan's "side-by-side Claude sample vs local full-book vs escalated final" was predicated on Phases 3–4 shipping as originally designed. With the architecture pivot, the more useful artifact is the operational architecture doc in CLAUDE.md (already updated post-SCRUM-281/282) and the compound-knowledge writeups for SCRUM-281 (fingerprint fallback) and SCRUM-282 (baseline methodology). No further go/no-go doc needed — `provider: cloud` is already the default, with local available as a tier-fallback for sensitivity testing.
9. **Cost reduction measurable.** ✅ DIRECTIONALLY MET — cloud Qwen3-VL via OpenRouter runs at a small fraction of Claude-Sonnet-per-page rates, with Claude spend now concentrated on fingerprint-matched pages only. Exact percentage not quantified because the project never ran full-book Claude as a baseline (the plan called for it but it was cost-prohibitive — which is the exact motivation). Token spend telemetry per provider is captured in each report's `token_counts` block.

Summary: **5 MET, 2 SUPERSEDED, 1 DEFERRED, 1 PARTIALLY MET (this commit closes)**.

## Residuals filed from this close-out

- **SCRUM-288** — Local VQA grader-leniency calibration (R2 residual from SCRUM-280). Scope: achieve mean absolute score Δ < 15 vs Claude across the 6-book corpus for the local provider, via prompt-engineering ladder or model swap. Priority: low, because local is no longer the default path; relevant only if someone revives the local tier for a specific audit workflow.
- **SCRUM-289** — Full-book `--all-pages` mode for visual_qa. Scope: implement Phase 3 from the original SCRUM-274 plan. Priority: backlog, because fingerprint fallback covers the regression-detection need. Revisit if a use case emerges that the fingerprint approach cannot cover (e.g., first-time audit of an unfamiliar book with no fingerprint corpus entries).

## What this close-out does not do

- **Does not retire the local provider code.** `tools/llm_providers/local_provider.py` remains. It's still a valid tier option and serves SCRUM-280 R2 if someone picks that up. SCRUM-274 AC #5 requires it stay callable.
- **Does not change `settings.json` default.** `provider: cloud` remains the default; nothing here reverts that.
- **Does not claim AC #8 in its original form.** The plan's baseline comparison doc was predicated on Phases 3–4 shipping. It doesn't exist because the underlying full-book mechanism was superseded, not because the work was skipped.
- **Does not address the stray PDF-sourced Atomic Habits baseline** (`data/vqa_baseline_post_274/Atomic Habits_ Tiny Changes, Remarkable Results_... .json`, 266 pages, no `capture_pipeline` field). That file is out of scope for this close-out — it appears to be a residual artifact post-dating SCRUM-282's archive step (commit `57f1242`). Cleanup is a separate housekeeping task.

## References

- Original plan: `docs/plans/2026-04-13-001-local-llm-visual-qa.md`
- Phase 1 baseline report: `docs/plans/2026-04-18-scrum-274-phase1-baseline-report.json`
- SCRUM-281 compound-knowledge: `docs/solutions/scrum-281-fallback-fingerprint-routing.md`
- SCRUM-282 compound-knowledge: `docs/solutions/scrum-282-vqa-baseline-methodology.md`
- SCRUM-283 compound-knowledge: `docs/solutions/scrum-283-cloud-vlm-evaluation.md`
- SCRUM-280 calibration patterns: `docs/solutions/scrum-280-local-vqa-calibration-patterns.md`
- Architecture of record (current): `CLAUDE.md` § Visual QA System
- Config of record (current): `config/settings.json` § visual_qa
