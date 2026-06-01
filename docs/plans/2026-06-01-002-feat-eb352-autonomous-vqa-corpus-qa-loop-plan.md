---
title: "feat: Autonomous VQA corpus QA loop (self-improving pipeline) — EB-352"
type: feat
status: active
date: 2026-06-01
origin: docs/brainstorms/2026-06-01-vqa-autonomous-corpus-qa-loop-requirements.md
---

# feat: Autonomous VQA Corpus QA Loop (Self-Improving Pipeline) — EB-352

## Overview

Stand up a standing, self-improving QA loop for the ebook pipeline. **Hermes**
(the ClaudeInfra WSL2 cron control plane) detects new books in `F:\Books`, runs
the existing VQA stack, classifies findings into **trustworthy signals**, and
posts a triage digest — ramping *optional-on-evidence* from human-triaged digests
(T0) to gated auto-filing of EB Jira tickets (T2). A weekly full re-sweep catches
regressions introduced by *pipeline code changes*, not just bad content; a landed
fix auto-re-scores the books that triggered it.

The capability mostly exists (classify → convert → score → audit); the new work is
**orchestration + a trustworthy signal layer + a governed autonomy ramp**. The
hard, unbuilt core is the *signal* — turning a noisy 30B-VLM score into something
worth filing — which the research below shows must live at the book-level/artifact
layer, never at the per-page score.

## Problem Frame

The VQA stack is mature but hand-operated; sweeps run only when someone runs them,
so code-introduced regressions are caught late. As `F:\Books` grows (432 classified
books today) this does not scale. EB-352 automates the loop while respecting the
project's Calibration Sessions rule (never escalate harness output without a
determinism + known-good + spot-check pass). See origin:
docs/brainstorms/2026-06-01-vqa-autonomous-corpus-qa-loop-requirements.md.

## Requirements Trace

Carried from the origin requirements doc (IDs preserved):

- R1. Persistent book registry: work-identity key + `sha256` file-version key, per-book VQA score **history** (latest + prior), linked tickets.
- R2. Nightly delta detection by content hash; enqueue only new/changed books.
- R3. Weekly full-corpus re-sweep to catch code-introduced regressions.
- R4. Hermes cron orchestrates by invoking existing scripts over Windows interop; it does not reimplement scoring.
- R5. Fire-and-return batches; survive interruption / resume via the runner's accumulating `run-summary.json`.
- R6. Per-run completion status (success/partial/failed, counts) posted to Discord/Telegram, distinct from findings.
- R7. Reuse `tools/visual_qa.py` (Qwen3-VL) + `tools/compare_vqa_reports.py`; honor `evaluated`+`vqa_exit=1` = valid low score.
- R8. Ticket-worthy = **pattern**: downward class-wide drop across a `type_axis`, or baseline regression — not a one-off low score or neutral drift.
- R8a. **Per-book regression against the book's own prior recorded score** is also ticket-worthy (catches single-book breakage).
- R9. Infra failures (`api_failure`/`conversion_failure`/`no_pages_sampled`) surfaced, T1-retry-eligible, never filed as bugs.
- R10. **T0:** ranked triage digest for human review; no tickets auto-created. Default shipping state.
- R11. **T2 (gated, optional-on-evidence):** auto-file trustworthy signals only, dedup'd, evidence-linked.
- R12. Auto-filed tickets follow EB Jira conventions; fixes go through normal human review/merge (T3 forbidden).
- R12a. Hard per-run ticket-creation ceiling (configurable) as a runaway-filing circuit-breaker.
- R13. Calibration gate (run-twice determinism + known-good zero-FP + spot-check) before auto-filing; runs as a **standing canary**.
- R14. T2 enablement recorded as a logged EB-ticket decision comment (not an ADR); optional-on-evidence (built only if T0 evidence justifies).
- R15. **Fix-verification re-score** (in scope): on a fix landing, auto re-score triggering books and record recovery.
- R16. Full improvement ledger — *deferred to a separate task*.

## Scope Boundaries

- **No auto-fixing / auto-merging** of pipeline code (T3 forbidden). All fixes human-authored and merged.
- **No changes to the VQA scoring engine or rubric** — `tools/visual_qa.py` and the rubric reused as-is (the signal layer sits *on top* of report output).
- **No real-time / instant-on-drop trigger** — nightly delta + weekly full re-sweep only.
- Hermes' orchestration brain is local-only text Qwen (no Claude fallback in the orchestration path).

### Deferred to Separate Tasks

- **R16 full improvement ledger** (corpus-wide `book→report→finding→ticket→fix→re-score` history + trend reporting): future EB ticket, after R10/R11/R15 prove reliable.
- **Tiered-VQA blind-audit oracle** (EB-342/EB-343): EB-352's T2 trust gate *consumes* this; if EB-343 has not landed when T2 is enabled, a minimal standalone seeded blind-Claude slice is built instead (see Key Decisions).
- **Lane B/C** (OCR/Gemini escalation, fallback-cost probe): separate EB-340 lanes, out of scope.

## Context & Research

### Relevant Code and Patterns

- `tools/visual_qa.py` — provider-agnostic orchestrator; emits report JSON with `overall_score`, `evaluation_status`, `coverage_status`, `coverage_reason`, `pages_requested/rendered/evaluated`, `capture_pipeline`. Determinism delegated to providers.
- `tools/llm_providers/local_provider.py` / `cloud_vl_provider.py` — **already set `temperature:0`, `seed:42`, strict `json_schema`** on all request builders (single + two-pass). No determinism mechanism needs adding.
- `tools/compare_vqa_reports.py` — `compare` computes per-book + corpus-mean score deltas (`_compute_book_delta`, `_aggregate`); `audit` is a **page-sampling parity check only** (`_cmd_audit`, exit codes 0/1/2/3). **No `type_axis`/`classification` score aggregation exists** — class-wide-drop is net-new.
- `tools/run_eb340_sweep2.ps1` (worktree `feat/eb340-sweep2-runner`, **unmerged**) — phases `Preflight/Select/Convert/VQA/Both/Canary`; writes `manifest.json` (per-book: `id,type_axis,classification,confidence,source_path,sha256,mb,pages,needs_ocr,needs_paid_tier`), `run-summary.json` (adds `kfx_path,convert_ok,vqa_exit,overall_score,evaluation_status,pages_sampled/requested/total,requested/effective_dpi,coverage_status,coverage_reason,error`; merged-by-`id`, rewritten per book), and `run-meta.json` (git SHA, endpoint, n_ctx, config snapshot).
- `tools/run_overnight_batch.ps1` + `tools/sync_pattern_db.ps1` — existing unattended batch + Task Scheduler registration (`-Register`, `New-ScheduledTaskAction`/`Trigger`). The loop's scheduler hook extends this path (EB-222), not a new one.
- `tools/Jira-BulkUpdate-2026-03-21.ps1` — inline `New-JiraIssue` (hardcodes `issuetype:"Task"` + `$JiraProject="SCRUM"` — both stale, must parameterize) and `Search-Issues` (REST v3 `POST /issue/search`, correct). Auth via `JIRA_EMAIL`+`JIRA_API_TOKEN`.
- `config/settings.json` — `visual_qa` block (`enabled:false`, `provider:"local"`, `pass_threshold:70`, `fallback{...}`), `scheduler` block (`interval_minutes,task_name,run_on_login`), `converge_loop`, `quality_gate`.

### Institutional Learnings

- **Signal must be book-level/artifact, not page score** (`docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`): re-scoring is ±1 at book aggregate but ±10 per-page with flipping category labels. Sweep #2 doctrine = **"measure artifacts, not scores"** (`<pre>` count, `(cid:N)` count, `text_integrity` category, coverage fields).
- **Mode-(b) blind spot** (`docs/solutions/scrum-280-local-vqa-calibration-patterns.md`): local grader misses issues entirely (`issues:[]`) — a drop-only trigger can't see detection-failure regressions. Needs an inflation-independent oracle (the seeded blind-Claude audit slice).
- **Three $0 pre-gates before any comparison counts** (`docs/solutions/eb-149-...`, `scrum-282-...`): `coverage_status:complete`, page-selection parity / `capture_pipeline` match, `compare_vqa_reports.py audit` exit 0/2 (treat 3 as harness fault → don't file).
- **Frozen regression fixtures with provenance** (positive + negative) are mandatory for any tunable detector (`scrum-281-fallback-fingerprint-routing.md`); VQA baselines are worktree-gated test fixtures (EB-181), land via PR.
- **Tiered-VQA design** (`docs/superpowers/specs/2026-05-29-tiered-vqa-design.md`) is the substrate, not to duplicate — provides the blind-audit slice, 3-way coverage schema, and the mandatory calibration re-baseline.
- Forthcoming `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md` (sweep #2 output) will be the most relevant findings doc — re-check before implementing the signal layer.

### External References

None gathered — local patterns + institutional learnings fully cover the design surface; the determinism question is answered internally.

## Key Technical Decisions

- **Signal lives at the book-level/artifact layer, never per-page** — book-level aggregate (±1 stable) as a coarse secondary; primary signal = artifact metrics + per-book/class deltas vs a frozen golden baseline. Directly from sweep #1/#2 evidence.
- **Class-wide-drop is net-new logic** layered on `compare_vqa_reports.py` (which has no `type_axis` aggregation). Reuse `type_axis` from the runner's `run-summary.json`; do not re-derive.
- **Three $0 gates are preconditions to *any* signal counting**: `coverage_status:complete`, page-parity/`capture_pipeline` match, `audit` exit 0/2. A `partial`/inconclusive/`api_failure` run is never a signal source.
- **Frozen golden baseline, not rolling** — regression is measured vs a human-re-baselined golden (recorded SHA/date) plus a cumulative-drift check, to defeat slow-drift baseline poisoning.
- **T2 trust oracle = the tiered-VQA blind-Claude audit slice** (EB-343) when available, else a minimal standalone seeded slice built in Unit 7 — required because the mode-(b) blind spot makes drop-only triggers unsafe for auto-filing.
- **Calibration gate is a standing canary**, not a one-time door: the known-good baseline re-runs each cycle; any fileable signal on it self-disables T2 back to T0.
- **Extend `run_overnight_batch.ps1` + Task Scheduler** (EB-222 path) for scheduling; Hermes drives via interop (Plex pattern), fire-and-return with a completion hook.
- **Authorization shim is the trust boundary**, not the WSL→Windows line: Hermes passes a structured JSON payload to a narrow filing function that validates server-side and enforces R12a; only structured fields (scores, enums) reach Hermes' reasoning (prompt-injection containment).
- **Determinism is already enforced in code** — the spike characterizes book-level stability and sets thresholds; it does not add sampling controls.

## Open Questions

### Resolved During Planning

- *Is determinism missing?* No — `temperature:0`/`seed:42`/strict schema already set in both providers; stability is book-level (±1), per-page noisy. (research)
- *Does class-wide-drop aggregation exist?* No — net-new on top of `compare_vqa_reports.py`. (research)
- *New scheduler or reuse?* Reuse/extend `run_overnight_batch.ps1` + Task Scheduler. (research, EB-222)
- *How to defeat mode-(b) regressions?* Reuse the tiered-VQA seeded blind-Claude audit slice as the T2 oracle. (research)

### Deferred to Implementation

- Exact numeric thresholds for "class-wide drop" (min class size, delta band) — set during Unit 1 against frozen fixtures + sweep data.
- Registry storage form (SQLite vs JSON sidecar) and exact reconciliation with `run-summary.json` — decided in Unit 2 against real runner output.
- Hermes agent-mode vs script-mode for multi-hour batches — confirmed empirically in Unit 4 against the real runner once #170/#171 land.
- Finding-fingerprint exact shape and cooldown window — Unit 7, once signal output is observed in T0.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Signal-classification decision flow (the trust core):**

```
run-summary.json row
   │
   ├─ evaluation_status ∈ {api_failure, conversion_failure, no_pages_sampled}? ── yes ─▶ INFRA FAILURE (R9: T1 retry, never file)
   │                                                          no
   ├─ coverage_status != complete?  OR  capture_pipeline mismatch vs baseline?  ── yes ─▶ INCONCLUSIVE (report only, not a signal)
   │                                                          no
   ├─ compare_vqa_reports audit exit == 3? ───────────────────────────────────── yes ─▶ HARNESS FAULT (investigate, never file)
   │                                                          no (0 or 2)
   ▼
 classify against FROZEN GOLDEN baseline:
   • class-wide downward drop across a type_axis (>= threshold, min class size)   ─▶ SIGNAL: class-regression
   • per-book downward drop vs book's OWN prior recorded score (R8a)              ─▶ SIGNAL: book-regression
   • cumulative drift vs golden (slow-decline guard)                              ─▶ SIGNAL: drift-watch
   • else                                                                          ─▶ no signal (digest line only)
   ▼
 T0: rank + digest        ──(optional-on-evidence + calibration canary green)──▶  T2: dedup → ceiling → auth shim → file EB ticket
```

**Loop cadence:** nightly = delta (new/changed by hash) → score → classify → digest; weekly = full re-sweep (code-regression surface) + standing calibration canary.

## Output Structure

    tools/
      vqa_loop/                         # new package — the signal + orchestration layer
        __init__.py                     # created in Unit 1a (first Python unit)
        registry.py                     # Unit 2: book registry + delta detection
        signals.py                      # Unit 1a/1b/3: signal definitions + classifier (net-new class-wide-drop, gates)
        digest.py                       # Unit 5: triage digest + completion status
        oracle.py                       # Unit 7a: blind-Claude audit slice (net-new oracle; defeats mode-(b))
        autofile.py                     # Unit 7: T2 gated auto-file + dedup + canary
        rescore.py                      # Unit 8: fix-verification re-score
      Jira-Primitives.psm1              # Unit 6: extracted, parameterized Jira module + auth shim
      Invoke-VqaLoop.ps1                # Unit 4: Hermes-invoked orchestration entrypoint
    tests/
      vqa_loop/
        test_signals.py                 # Unit 1a/1b/3
        test_registry.py                # Unit 2
        test_digest.py                  # Unit 5
        test_oracle.py                  # Unit 7a
        test_autofile.py                # Unit 7
        test_rescore.py                 # Unit 8
        test_orchestration.ps1          # Unit 4 (Pester)
        test_jira_primitives.ps1        # Unit 6 (Pester)
    data/
      vqa_golden_baseline/              # Unit 1a: frozen + independently-validated golden baseline (worktree-gated, PR per EB-181)
    config/settings.json                # Unit 4/7: new vqa_loop config block

## Implementation Units

Grouped into phases. Phase 0 units have **no hard dependency on the unmerged runner** and can start immediately; Phase 1+ orchestration is gated on EB-340 PRs #170/#171.

### Phase 0 — Trust foundation (start now, no runner dependency)

> **Plan-review correction:** the original single Unit 1 claimed runner-independence,
> but class-wide-drop cannot be calibrated on master data — sweep #1's run-summary has
> 12 size-1 `type_axis` classes with `overall_score=None`, and the sweep #2 run-summary
> is empty. Unit 1 is therefore split: **1a** is codable now against the 10-book baseline
> corpus; **1b** is runner-gated. (Adversarial + feasibility reviewers, high confidence.)

- [ ] **Unit 1a: Per-book + drift signal definition, golden baseline, independent validation** *(startable now)*

**Goal:** Define the signals that DON'T need multi-book classes — per-book regression-against-prior (R8a) and cumulative-drift-vs-golden — characterize determinism, and freeze + **independently validate** a golden baseline.

**Requirements:** R7, R8a, R13 (foundation)

**Dependencies:** None — uses the existing 10-book baseline corpus, `tools/visual_qa.py`, `compare_vqa_reports.py`, sweep #1 logs on master.

**Files:**
- Create: `data/vqa_golden_baseline/` (frozen reports + `provenance.json`: git SHA, capture date, n_ctx, capture_pipeline, **independent-validation record**)
- Create: `tests/vqa_loop/test_signals.py` (fixture-driven threshold tests)

**Approach:**
- Characterize book-level determinism (re-score twice, confirm ±1 aggregate; quantify per-page/category noise) to set a min-detectable-effect band wider than measured noise.
- Define per-book regression-against-prior (R8a) and cumulative-drift-vs-golden vs the frozen golden.
- **Break the circular-calibration trap:** determinism (±1 on re-run) proves *stability*, not *correctness*. Validate the golden's scores against an independent reference (human spot-check, or a one-time blind-Claude pass on the golden capture) so the "known-good baseline" actually is known-good — required by the Calibration Sessions rule. (adversarial reviewer)

**Execution note:** Characterization-first — measure real determinism/noise before fixing any threshold; treat thresholds as derived from data, not assumed.

**Patterns to follow:** sweep #2 A/B "measure artifacts, not scores"; `compare_vqa_reports.py` `_compute_book_delta`/`_aggregate`; SCRUM-281 frozen-fixture discipline.

**Test scenarios:**
- Happy path: per-book score below its own prior (beyond band) → `book-regression` (R8a).
- Edge case: book-level Δ within ±noise band → no signal (avoids per-page-noise false positives).
- Edge case: neutral/upward drift → no signal (R8 directionality).
- Edge case: slow 3-pt/week decline vs golden → `drift-watch` fires cumulatively (but see Unit 5 — drift-watch is digest-only, never auto-filed).
- Error path: `coverage_status:partial` fixture → INCONCLUSIVE, never a signal.
- Error path: `capture_pipeline` mismatch between baseline and live → INCONCLUSIVE.

**Verification:** Per-book/drift suite passes with zero false positives on the negative set; golden baseline committed via PR (EB-181) with the independent-validation record attached.

- [ ] **Unit 1b: Class-wide-drop threshold calibration** *(gated on runner #170/#171 + a real multi-book sweep + sweep #2 findings)*

**Goal:** Define and calibrate the net-new class-wide-drop metric once real multi-book `type_axis` classes with populated scores exist.

**Requirements:** R8

**Dependencies:** Runner #170/#171 merged; a real `Both` sweep producing multi-book classes with scores; `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md` (not yet written — hard input, not a soft watch).

**Files:**
- Modify: `tests/vqa_loop/test_signals.py` (add class-wide-drop cases)

**Approach:**
- Define class-wide-drop = downward mean delta across books sharing a `type_axis`, with a min class size, composed with the audit's per-book and corpus-mean delta thresholds (`compare_vqa_reports.py` `_aggregate`).
- Calibrate thresholds against real sweep data; confirm the corpus actually contains type_axis classes of sufficient size (sweep #1 had none).

**Test scenarios:**
- Happy path: a fixture set with a real class-wide downward drop (class size ≥ min) → `class-regression`.
- Edge case: type_axis class below min size → not eligible for class-wide signal (falls back to per-book).

**Verification:** Class-wide threshold cases pass on real multi-book fixtures; min-class-size documented.

- [ ] **Unit 2: Book registry + delta detection**

**Goal:** Persistent registry keyed by work-identity (+ `sha256` file-version), storing per-book score history and linked tickets; nightly delta by hash.

**Requirements:** R1, R2

**Dependencies:** None to build; integrates with runner output in Unit 4.

**Files:**
- Create: `tools/vqa_loop/registry.py`
- Create: `tests/vqa_loop/test_registry.py`

**Approach:**
- Work-identity key (title+author or content-independent id) so a re-issued/edited file maps to the same work; `sha256` as the version key for delta detection.
- Ingest `run-summary.json` rows post-run; retain prior score for R8a.
- Decide storage (SQLite vs JSON sidecar) against real runner output; reconcile with `run-summary.json` lifecycle (per-run shard vs persistent store).

**Patterns to follow:** `data/ebook_patterns.db` (existing SQLite) for storage convention; runner `run-summary.json` schema.

**Test scenarios:**
- Happy path: new hash not in registry → flagged new; enqueued.
- Edge case: same work, changed bytes (new hash, same title/author) → mapped to same work, prior score carried (not treated as brand-new).
- Edge case: near-duplicate filenames (`(1)`/`(2)`) → not double-counted.
- Happy path: ingest a `run-summary.json` row → prior score retained for next-run R8a compare.
- Error path: malformed/partial run-summary row → skipped, logged, registry not corrupted.

**Verification:** Registry round-trips a synthetic corpus; delta detection returns exactly the changed set; prior-score history available to the signal classifier.

### Phase 1 — T0 detect → batch → digest (gated on runner #170/#171)

- [ ] **Unit 3: Signal classifier module**

**Goal:** Consume `run-summary.json`, apply the three $0 gates + infra-failure split, emit classified signals per the decision flow.

**Requirements:** R7, R8, R8a, R9

**Dependencies:** Unit 1 (thresholds/fixtures), Unit 2 (prior scores), runner output schema.

**Files:**
- Create: `tools/vqa_loop/signals.py`
- Create/extend: `tests/vqa_loop/test_signals.py`

**Approach:**
- Implement the decision flow: infra-failure → inconclusive (coverage/parity) → harness-fault (audit exit 3) → classify vs golden.
- Validate the scorer report JSON against schema before classifying (reject adversarial/malformed → infra failure) — prompt-injection containment at the data boundary.
- Emit structured signal objects (type, type_axis, evidence pointers, magnitude) only.

**Patterns to follow:** `compare_vqa_reports.py` audit exit-code gating; EB-149 coverage-status reading.

**Test scenarios:**
- Happy path: clean run with one class-regression → exactly one signal of that type.
- Error path: `api_failure` row → INFRA FAILURE (R9), no signal.
- Error path: audit exit 3 → HARNESS FAULT, no signal.
- Edge case: malformed scorer JSON → treated as infra failure, not a valid score.
- Integration: signals reference registry prior scores correctly for R8a.

**Verification:** On a recorded sweep, classifier output matches a hand-labeled signal set; zero signals on the known-good negative fixtures.

- [ ] **Unit 4: Orchestration entrypoint + scheduling (Hermes interop)**

**Goal:** A single entrypoint Hermes invokes that runs the cadence (nightly delta / weekly full), with preflight gating, fire-and-return, resume, and config.

**Requirements:** R3, R4, R5, R6

**Dependencies:** Runner #170/#171 merged (frozen CLI + `run-summary.json`); Units 2, 3.

**Files:**
- Create: `tools/Invoke-VqaLoop.ps1`
- Modify: `config/settings.json` (new `vqa_loop` block: cadence, thresholds path, channels, ceiling)
- Modify: `tools/run_overnight_batch.ps1` (or document the extension seam) for scheduler reuse
- Create: `tests/vqa_loop/test_orchestration` (Pester, where feasible)

**Approach:**
- Nightly: registry delta → runner `Both` over delta → classify. Weekly: full re-sweep + calibration canary.
- Preflight gate (n_ctx ≥ 32768, node-up) → on failure post "failed" status (R6), skip without enqueue; define retry vs manual-clear.
- Fire-and-return + completion hook (Plex `qbit-finished` pattern); resume via accumulating `run-summary.json`.
- Confirm Hermes agent-mode vs script-mode tolerance for multi-hour batches against the real runner; chunk the weekly sweep if it overruns the overnight window.
- Register via Task Scheduler (`sync_pattern_db.ps1 -Register` pattern, pwsh).

**Execution note:** Verify Hermes interop + n_ctx preflight empirically before wiring the schedule.

**Patterns to follow:** `tools/run_overnight_batch.ps1`, `tools/sync_pattern_db.ps1 -Register`, the registered Plex Hermes interop in `project-dependencies.json`.

**Test scenarios:**
- Happy path: nightly run with 2 new books processes exactly those 2 and classifies.
- Error path: node down / n_ctx < 32768 → "failed" status posted, no enqueue, no silent api_failure treated as clean.
- Edge case: interrupted mid-batch → resume continues from accumulated `run-summary.json` without double-processing.
- Integration: weekly full re-sweep surfaces a deliberately-introduced class-wide regression end-to-end.

**Verification:** A new PDF dropped in `F:\Books` gets a verdict within one nightly cycle, zero manual steps; weekly sweep catches a seeded regression.

- [ ] **Unit 5: Triage digest + completion status + liveness**

**Goal:** T0 output — ranked findings digest and a separate completion status to Discord/Telegram; loop liveness heartbeat.

**Requirements:** R6, R10, R13 (FP/volume measurement)

**Dependencies:** Units 3, 4.

**Files:**
- Create: `tools/vqa_loop/digest.py`
- Create: `tests/vqa_loop/test_digest.py`

**Approach:**
- Rank signals (class-regression > book-regression > drift-watch), embed evidence pointers + run-meta (git SHA, reproducibility).
- Completion status distinct from findings (R6).
- Record per-run FP-rate + filable-signal volume (these gate the T2 optional-on-evidence decision, R14).
- Liveness heartbeat: if a scheduled run posts no status within its window, raise a loud alert.

**Patterns to follow:** existing Discord webhook sender (`Send-DiscordWebhook.ps1` in ClaudeInfra); Hermes Telegram reply.

**Test scenarios:**
- Happy path: 3 signals → ranked digest with evidence links + git SHA.
- Edge case: zero signals → "clean run" completion status, no findings noise.
- Error path: missed run window → heartbeat alert fires.
- Integration: FP/volume counters accumulate across runs for the T2 readiness metric.

**Verification:** Digest renders for a recorded run; heartbeat fires on a simulated missed window.

### Phase 2 — Security hardening + T2 gated auto-file

- [ ] **Unit 6: Jira primitives module + authorization shim**

**Goal:** Extract `New-JiraIssue`/`Search-Issues` into a reusable, parameterized module (fix `SCRUM`→`EB`, parameterize issuetype), and add the authorization shim + per-run ceiling + scoped token.

**Requirements:** R11, R12, R12a (security)

**Dependencies:** None to build; consumed by Unit 7.

**Files:**
- Create: `tools/Jira-Primitives.psm1`
- Create: `tests/vqa_loop/test_jira_primitives` (Pester)
- Modify: `tools/Jira-BulkUpdate-2026-03-21.ps1` (re-point to the module to avoid divergence)

**Approach:**
- Parameterize project key (default `EB`) and issue type; keep REST v3 search.
- Authorization shim: a narrow filing function accepting only a structured payload (title, description, evidence path, signal-type) — Hermes cannot pass arbitrary args to `New-JiraIssue`.
- Enforce R12a per-run ceiling server-side; scoped/rotated Jira token (create/read on EB only), resolved from the secrets pattern, never a file Hermes reads.

**Patterns to follow:** `jira-workflow` skill (search-before-create, EB prefix); existing auth-header construction.

**Test scenarios:**
- Happy path: shim creates a ticket from a valid structured payload (mocked REST, assert one POST).
- Error path: payload exceeding the per-run ceiling → filing suppressed, warning emitted.
- Error path: malformed/over-broad payload → rejected by shim validation.
- Edge case: search-before-create finds an open dup → comments/links instead of filing.
- Integration: token scope failure (403) → surfaced, not silently swallowed.

**Verification:** Module imports cleanly; shim rejects arbitrary-arg attempts; ceiling enforced under a synthetic flood.

- [ ] **Unit 7: Calibration canary + T2 gated auto-file**

**Goal:** Standing calibration canary gating optional-on-evidence T2 auto-filing of trustworthy signals, dedup'd by stable pattern identity with cooldown.

**Requirements:** R11, R12, R13, R14

**Dependencies:** Units 1, 3, 5, 6; trust oracle (EB-343 blind-audit, else minimal seeded slice here).

**Files:**
- Create: `tools/vqa_loop/autofile.py`
- Create: `tests/vqa_loop/test_autofile.py`
- Modify: `config/settings.json` (`vqa_loop.t2` block: enabled flag, ceiling, cooldown, canary baseline path)

**Approach:**
- Standing canary: re-run known-good golden each cycle; any fileable signal on it → self-disable T2 to T0 + alert.
- Trust oracle: consume the tiered-VQA seeded blind-Claude audit (EB-343) when present; else build a minimal deterministic seeded slice (first/body/back + ~5% random, capped, seed = source-hash + config version) to defeat mode-(b).
- Dedup: stable pattern identity (`type_axis` + signal-kind), not the specific book set (which shifts with VLM noise); cooldown while a linked fix PR is open / N days post-merge before re-baseline.
- T2 enablement: logged EB-ticket decision comment (R14), gated on T0 FP/volume evidence.

**Execution note:** Test-first on the canary self-disable and dedup-identity logic — these are the safety-critical paths.

**Patterns to follow:** tiered-VQA blind-audit (`docs/superpowers/specs/2026-05-29-tiered-vqa-design.md`); SCRUM-281 frozen fixtures; `compare_vqa_reports.py audit` exit gating.

**Test scenarios:**
- Happy path: a confirmed class-regression (oracle-corroborated) → one EB ticket filed, evidence-linked.
- Error path: canary yields a fileable signal → T2 self-disables to T0, alert fired, nothing filed.
- Edge case: same pattern re-detected next night while fix PR open → cooldown suppresses re-file.
- Edge case: mode-(b) regression (local clean, blind-audit catches) → still filed via oracle path.
- Error path: known-good baseline → zero auto-filed tickets (R13 calibration).
- Integration: ceiling + shim (Unit 6) enforced on the auto-file path.

**Verification:** Calibration gate passes (determinism + zero-FP canary + spot-check) before enable; known-good baseline files zero tickets; canary self-disable proven.

### Phase 3 — Self-improvement slice

- [ ] **Unit 8: Fix-verification re-score**

**Goal:** When a fix lands (merged PR linking a filed ticket), auto re-score the triggering books and record recovery.

**Requirements:** R15

**Dependencies:** Units 2 (registry), 4 (orchestration), 6 (ticket links).

**Files:**
- Create: `tools/vqa_loop/rescore.py`
- Create: `tests/vqa_loop/test_rescore.py`

**Approach:**
- On a merge event linking an EB ticket, look up the triggering books from the registry, re-score them, compare vs the pre-fix score, record recovery (or not) and post the outcome.

**Patterns to follow:** registry (Unit 2) ticket links; runner VQA invocation.

**Test scenarios:**
- Happy path: fix lands → triggering books re-scored, recovery recorded and posted.
- Edge case: score did not recover → recorded as unresolved, ticket not auto-closed.
- Integration: registry updated with post-fix score for future R8a comparisons.

**Verification:** A simulated fix-merge re-scores exactly the triggering books and records the delta.

## System-Wide Impact

- **Interaction graph:** new `tools/vqa_loop/` package consumes runner `run-summary.json` + `visual_qa.py` reports; Hermes invokes `Invoke-VqaLoop.ps1` over interop; auto-file path reaches the Jira API via the shim.
- **Error propagation:** infra failures and harness faults are terminal-non-filing (R9); node-down → "failed" status; never a silent `api_failure` treated as clean.
- **State lifecycle risks:** registry vs `run-summary.json` reconciliation; interrupted-run resume must not double-file or double-process; cooldown prevents nightly re-file.
- **API surface parity:** `config/settings.json` gains a `vqa_loop` block (tracked pipeline config — prefer env overrides, never strand an edit); Jira module replaces the inline functions (avoid divergence).
- **Integration coverage:** weekly-sweep-catches-seeded-regression and canary-self-disable are the cross-layer behaviors unit tests alone won't prove.
- **Unchanged invariants:** `visual_qa.py` scoring/rubric untouched; the loop reads reports, never alters scoring.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Per-page VLM noise produces spurious class-drop signals | Med | High | Signal lives at book-level aggregate (±1) + min-detectable-effect band wider than measured noise (Unit 1); frozen-fixture validation |
| Mode-(b) regressions produce no drop (invisible) | Med | High | Blind-Claude audit oracle (EB-343 or minimal slice, Unit 7); never drop-only for T2 |
| Slow-drift baseline poisoning | Med | High | Frozen golden baseline + cumulative-drift check (Unit 1); human re-baseline only |
| Runner #170/#171 not merged / interface churns | High | High | Phase 0 starts without it; freeze runner CLI + `run-summary.json` as shared interface before Phase 1 |
| Hermes can't tolerate multi-hour batches | Med | Med | Fire-and-return + completion hook; chunk weekly sweep; verify empirically (Unit 4) |
| Weekly 432-book sweep overruns overnight window | Med | Med | Chunk / rotate; consider gating heavy resweep on pipeline-code commits against the 10-book baseline |
| Autonomous agent misfiles a ticket storm | Low | High | Per-run ceiling (R12a) + auth shim + standing canary self-disable |
| Prompt injection via malicious PDF reaching reasoning | Low | High | Only structured fields reach Hermes reasoning; scorer-JSON schema validation (Unit 3); job isolation |

## Dependencies / Prerequisites

- **Hard:** EB-340 PRs #170/#171 (`tools/run_eb340_sweep2.ps1`) on master, CLI + `run-summary.json` frozen (blocks Phase 1+).
- **Cross-project:** ClaudeInfra Hermes (ADR-0043) T0/T1 infra *implemented*, registered in `project-dependencies.json` (done). Confirm before Phase 1 scheduling.
- **Soft:** tiered-VQA blind-audit (EB-342/EB-343) for the T2 oracle; else minimal slice in Unit 7.
- **Watch:** forthcoming `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md` — re-check before Unit 1.

## Phased Delivery

- **Phase 0 (startable now):** Unit 1a (per-book + drift signal, validated golden baseline) + Unit 2 skeleton (registry module against the sweep #1 schema as a proxy). The runner-schema reconciliation sub-task of Unit 2 and all of Unit 1b are **runner-gated**, not Phase 0.
- **Phase 1 (after #170/#171 merge + interface freeze):** Unit 1b (class-wide-drop calibration), Units 3–5 (classifier + orchestration + T0 digest), Unit 2 reconciliation. Ship T0 and run for ≥2 weeks; measure FP-rate + signal volume against the **numeric T2-readiness criterion** (must be stated before T0 ends — see Success Metrics).
- **Phase 2 (optional-on-evidence — design sketch until T0 evidence + logged EB decision):** Units 6–7 — Jira module + shim + oracle slice (Unit 7a) + calibration canary + T2 auto-file. Do not implement until the T2-readiness criterion is met.
- **Phase 3 (gated on T2 activation):** Unit 8 — fix-verification re-score (depends on T2-filed ticket links; if T2 never enables, provide a manual re-score CLI flag on Unit 4 instead).

## Documentation / Operational Notes

- Update `CLAUDE.md` Visual QA section once the loop ships; document the cadence, the signal taxonomy, and the T2 enable/disable procedure.
- Record the T2 enablement decision as a logged comment on EB-352 (R14).
- Operational: Hermes liveness heartbeat is a first-class alert; a silently-dead loop is worse than none.

## Plan Review Findings (2026-06-01) — apply during implementation

A 5-persona plan review (coherence/feasibility/scope/adversarial/security) ran on this
plan. Structural corrections (Unit 1→1a/1b split, oracle as Unit 7a, phased-delivery
re-gating, output-structure files, R2-naming, audit-exit-1 clarity) are already folded in
above. The following are carried as explicit implementation obligations:

**Trust integrity (P1):**
- *Circular calibration* — the golden baseline is captured from the same noisy VLM; determinism ≠ correctness. Unit 1a's independent-validation step is mandatory, not optional.
- *Oracle is net-new (Unit 7a)* — EB-343 has no committed code; the blind-Claude slice must be built here with a defined page-selection algorithm, rubric/prompt, reconciliation rule vs the local score, per-cycle Claude cost cap, and an explicit "corroborated" definition used in Unit 7's tests.

**Registry identity (P1):** the runner's `run-summary.json` has **no title/author field** (only synthetic `id`, `source_path`, `sha256`). Unit 2 must source work-identity from embedded PDF metadata (the existing Book Metadata System) or normalized `source_path`, and specify edition-collision handling (Vol 1 vs Vol 2, same title+author).

**Security (P1/P2) — Unit 6/7:**
- Auth-shim payload needs a concrete schema: field types, max lengths, `signal-type` enum, and an `evidence-path` constraint (relative within `data/vqa_golden_baseline/` or the run log dir, **no traversal**) — close the path-traversal vector.
- Module exposes only `New-VqaJiraIssue` + `Search-VqaJiraIssues`; **no** update/delete/transition verbs. Use a restricted Jira API token (create-issue + browse-project on EB only), read from `JIRA_API_TOKEN` env (same pattern as the existing script), never a file Hermes reads. State a rotation cadence or drop the word "rotated".
- Ticket ceiling: state a default value; test ceiling=1 (boundary), ceiling=0 → **disabled/T0 fallback** (not "unlimited"); counter increments on **attempt**, not on HTTP 200 (prevents retry-loop bypass). Add 401/429 handling tests.
- Canary re-enable after self-disable must be **manual** (human config/logged-EB-decision), never automatic on next clean cycle; add the test. Add a canary **sensitivity** test (inject realistic drift → canary fires), not just the disable-branch test.

**Prompt-injection data path (P1) — Unit 3/5:** annotate every `run-summary.json`/VQA-report field that reaches Hermes' reasoning as numeric/enum (safe) vs freeform (`title`, `author`, `coverage_reason` — must strip/truncate). Unit 5 sanitizes freeform fields before any Hermes-bound digest message.

**Scope / right-sizing (P2):**
- Phase 2/3 units are design sketches until the T2-readiness criterion is met — do not pre-build.
- Drop the `tools/Jira-BulkUpdate-2026-03-21.ps1` re-point (out-of-scope housekeeping); if stale, retire it as a separate chore.
- Consider collapsing the package to 1–2 modules for T0 and promoting to a package only when Phase 2 activates.
- `drift-watch` is **digest-only commentary**, never auto-filed (no dedicated T2 path).

**Open (needs a decision during implementation):**
- A **numeric T2-readiness criterion** (target FP-rate + min filable-signal volume over the T0 window) must be set before T0 ends — "optional-on-evidence" currently has no falsifiable line (see Success Metrics).
- Commit to SQLite for the registry now (`data/ebook_patterns.db` precedent) rather than deferring the storage decision, since Units 3/4 integrate against it.
- Confirm Hermes ADR-0043 T0/T1 infra is *implemented* (not only designed) before Phase 1 scheduling; the `project-dependencies.json` EB-352 edge is registered (this session).

## Success Metrics

- **T2-readiness criterion (must be set before T0 ends):** e.g. T0 false-positive rate ≤ X% over ≥2 weeks AND ≥ N filable signals/week — the falsifiable gate for the R14 optional-on-evidence decision.
- A new PDF in `F:\Books` receives a VQA verdict within one nightly cycle, zero manual steps.
- The weekly re-sweep surfaces a deliberately-introduced class-wide regression.
- Known-good baseline produces zero auto-filed tickets across the calibration canary's standing operation.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-01-vqa-autonomous-corpus-qa-loop-requirements.md](docs/brainstorms/2026-06-01-vqa-autonomous-corpus-qa-loop-requirements.md)
- Jira: EB-352 (this work), EB-340 (auto-enable VQA / sweep2 runner prerequisite), EB-342/EB-343 (tiered-VQA / blind-audit oracle), EB-347 (F1 coverage), EB-149/SCRUM-282 (coverage + baselines).
- Related code: `tools/visual_qa.py`, `tools/compare_vqa_reports.py`, `tools/run_eb340_sweep2.ps1`, `tools/run_overnight_batch.ps1`, `tools/Jira-BulkUpdate-2026-03-21.ps1`.
- Learnings: `docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`, `docs/solutions/scrum-280-local-vqa-calibration-patterns.md`, `docs/solutions/scrum-282-vqa-baseline-methodology.md`, `docs/solutions/eb-149-vqa-coverage-loss-surfacing.md`, `docs/superpowers/specs/2026-05-29-tiered-vqa-design.md`.
- Cross-project: `project-dependencies.json` (ClaudeInfra Hermes → EbookAutomation, EB-352).
