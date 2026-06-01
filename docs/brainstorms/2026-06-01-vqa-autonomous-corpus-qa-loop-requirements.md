---
date: 2026-06-01
topic: vqa-autonomous-corpus-qa-loop
---

# Autonomous VQA Corpus QA Loop (Self-Improving Pipeline)

## Problem Frame

The VQA stack (classification, batch runner, vision scorer, baseline audit, Jira
primitives) is mature but **operated by hand** — every sweep is a manual chain of
scripts, and findings become tickets only when a human reads a sweep doc. As the
`F:\Books` corpus grows (432 classified books today), this manual loop does not
scale, and pipeline regressions introduced by code changes are caught only when
someone happens to run a sweep.

The goal is a standing, self-improving loop: new books are detected and QA'd
automatically, the *pipeline itself* is re-checked for regressions on a schedule,
and trustworthy findings become Jira tickets — so the quality safety net grows
stronger every time the corpus or the code changes. The hard part is not
capability (the verbs exist) but **orchestration and trust**: turning a noisy
30B-VLM score into a signal worth filing without flooding the board.

The newly-available **Hermes** control plane (WSL2 agent, cron scheduler, tiered
autonomy per ClaudeInfra ADR-0043) supplies the missing orchestration brain, and
its autonomy tiers supply the trust ramp.

## Loop Overview

```
                         ┌─────────────────────────────────────────────┐
        nightly cron ───▶│ 1. DISCOVER   diff F:\Books vs registry      │
        weekly cron  ───▶│    (sha256 delta)  +  weekly: full re-sweep  │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
       reuse existing ──▶│ 2. CLASSIFY → CONVERT → VQA SCORE → AUDIT    │
       scripts          │    classify_source.py / run_eb340_sweep2.ps1 │
       (Hermes invokes) │    visual_qa.py (Qwen3-VL) / compare_vqa...   │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
       the trust core ─▶│ 3. CLASSIFY SIGNAL                           │
                         │   pattern (regression / class-wide drop) =   │
                         │   ticket-worthy.  one-off low score = report │
                         │   only.  infra failure = retry, never file.  │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                ┌────────────── AUTONOMY RAMP (ADR-0043) ──────────────┐
                ▼                                                       ▼
   PHASE 1 (T0, ship first)                       PHASE 2 (T2, gated)
   post ranked triage digest      ── calibration ──▶  auto-file Jira tickets
   to Discord/Telegram;              gate passes       (trustworthy signals
   human files tickets               + ADR             only, dedup'd)
                                                              │
                                              fixes → normal human review/merge
                                                       (T3 auto-merge FORBIDDEN)
```

## Requirements

**Discovery & Registry**
- R1. Maintain a persistent **book registry** recording each corpus book's
  classification, its VQA report history (latest **and** prior score, to enable the
  per-book regression signal in R8a), and any linked Jira ticket(s). Keyed by a
  stable **work identity** (e.g. title+author or a content-independent book_id) so a
  legitimately re-issued/edited file maps to the same work, with the `sha256` carried
  as the file-version key for delta detection. The registry is the dedup substrate
  and the foundation for the later improvement ledger (R16).
- R2. **Nightly**, diff `F:\Books` against the registry by `sha256` to find
  new/changed books and enqueue only that delta for processing.
- R3. **Weekly**, run a full-corpus re-sweep regardless of delta, to surface
  regressions introduced by *pipeline code changes* (not just new content). This
  is what makes the loop a pipeline-QA system, not only a content-QA system.

**Orchestration (Hermes)**
- R4. A Hermes cron (WSL2 control plane) drives the loop end-to-end by invoking the
  **existing** PowerShell/Python scripts over Windows interop (the proven Plex
  pattern). Hermes orchestrates and reasons over results; it does not reimplement
  classification, conversion, or scoring.
- R5. Long-running batches run fire-and-return with results collected on
  completion; the loop must survive interruption and resume (reuse the runner's
  accumulating `run-summary.json`).
- R6. Every run posts a **completion status** (success / partial / failed, books
  processed, infra-failure count) to Discord/Telegram — kept distinct from
  findings output.

**VQA Execution & Signal Classification**
- R7. Reuse the existing vision scorer (`tools/visual_qa.py`, Qwen3-VL @
  `192.168.1.33:8080`) and baseline audit (`tools/compare_vqa_reports.py`). Honor
  the established result taxonomy: `evaluation_status=evaluated` + `vqa_exit=1` is
  a **valid scored result** (score below threshold), not an infra failure.
- R8. Classify findings into signals. A **ticket-worthy signal is a PATTERN** — a
  *downward* regression vs. baseline (`audit` exit 2 in the degrading direction) or
  a class-wide score *drop* across a `type_axis` — **not** a one-off low score on a
  single book, and **not** a neutral/upward drift. Per-book low scores are reported
  (digest) but never auto-ticketed. (`type_axis` is the book-class field produced by
  `Get-TypeAxis` in `run_eb340_sweep2.ps1`; it is distinct from `classify_source.py`'s
  `classification` field — planning must pick which one keys the class-drop logic.)
- R8a. A **per-book regression against the book's own prior recorded score** is also
  ticket-worthy — a book whose score dropped materially vs. its last registry entry,
  distinct from a first-seen low score. This catches single-book pipeline breakage
  (the project's documented #1 failure mode: "a fix for one book has broken 4
  others"), which a class-wide-only filter would miss because no other book shares
  that structure.
- R9. Infra failures (`api_failure`, `conversion_failure`, `no_pages_sampled`) are
  surfaced and eligible for idempotent retry (T1), never filed as pipeline bugs.

**Triage, Ticketing & Autonomy Ramp**
- R10. **Phase 1 (T0):** post a ranked triage digest of candidate findings for
  human review; no tickets auto-created. This is the default shipping state.
- R11. **Phase 2 (T2, gated):** after the calibration gate (R13) passes and T2 is
  enabled (R14), Hermes auto-files Jira tickets for trustworthy signals only, with
  dedup against existing open tickets (search-before-create) and a link back to the
  registry/report evidence.
- R12. Auto-filed tickets follow project Jira conventions (EB board prefix, bug
  labeling, acceptance criteria). Fixes always go through normal human
  review/merge — Hermes never merges (T3 forbidden).
- R12a. A **hard per-run ticket-creation ceiling** (configurable, e.g. 5) gates the
  auto-file path: exceeding it suppresses all filing for that run, posts a warning
  to Discord/Telegram, and requires manual clearance. This is a runaway-filing
  circuit-breaker against a misconfigured threshold or a classification bug.

**Calibration Gate (T0 → T2 promotion)**
- R13. Before any auto-filing is enabled, a **calibration gate** must pass:
  (a) run-twice determinism on identical input, (b) zero false positives on a
  known-good baseline, (c) spot-check of 2–3 findings per class against source.
  This is a hard precondition encoding the global Calibration Sessions rule.
- R14. Enabling T2 is recorded as a **logged decision comment on the EB ticket**
  (not a formal ADR — proportionate governance for a solo-dev tool while remaining
  auditable). T2 is **optional-on-evidence, not a committed destination**: it is
  built only if T0 demonstrates a measured signal volume that makes manual filing a
  real time cost (criterion in Success Criteria). If the T0 digest stays quiet, T0 is
  the terminal state and T2 is cut, not built.

**Self-Improvement Loop**
- R15. **Fix-verification re-score (minimal self-improvement slice, in scope).** When
  a fix lands (a merged PR linking a filed ticket), auto re-score the specific books
  that triggered the finding and record whether the affected book/class score
  recovered; post the outcome to the digest/channel. This closing step is what makes
  the loop genuinely *self-improving* rather than a cron-driven linter, and is cheap
  given the registry (R1) already retains per-book score history.
- R16. *(Deferred — future scope)* Extend the registry into a full **improvement
  ledger** linking `book → report → finding → ticket → fix → re-score` across the
  whole corpus history, with trend reporting. Build only after R10/R11/R15 prove the
  signal and the re-score slice are reliable.

## Success Criteria
- A new PDF dropped into `F:\Books` receives a VQA verdict within one nightly
  cycle with zero manual steps.
- The weekly full re-sweep detects a deliberately-introduced pipeline regression
  (a class-wide score drop) and surfaces it as a signal.
- During T0, the digest's findings are reviewed and both a **false-positive rate**
  and a **filable-signal volume** are measured — together these gate the
  optional-on-evidence decision to build T2 (R14).
- After T2, every auto-filed ticket corresponds to a real signal (class-wide drop,
  baseline regression, or per-book regression-against-self), is dedup'd, and the
  known-good baseline produces zero auto-filed tickets (validated by the calibration
  gate, which re-runs as a standing canary — see Resolve Before Planning).
- A shipped fix that links a filed ticket triggers an automatic re-score of the
  triggering books, and the score recovery (or lack of it) is recorded (R15).
- The loop's own liveness is observable: if a scheduled run does not post a
  completion status within its window, a loud alert fires (a silently-dead automation
  is worse than none — it creates false confidence).
- Corpus growth strengthens coverage: each new book becomes part of the
  fixture set rather than a one-time check.

## Scope Boundaries
- **No auto-fixing or auto-merging** of pipeline code (T3 forbidden); all fixes are
  human-authored and human-merged.
- **No changes to the VQA scoring engine or rubric** — `visual_qa.py` and the
  rubric are reused as-is.
- **Not** EB-340 Lane B (OCR/Gemini escalation) or Lane C (fallback-cost probe) —
  those are separate lanes with their own prerequisites (classifier-handoff,
  fallback-cost gate) and are explicitly out of scope here.
- **No real-time / instant-on-drop trigger** — nightly delta + weekly full
  re-sweep was chosen over folder-watch for predictability and to avoid competing
  with daytime machine use.
- Hermes' orchestration brain is local-only text Qwen (no Claude fallback in the
  orchestration path); only the vision scorer and any explicit fallback inside
  `visual_qa.py` may reach cloud models.

## Key Decisions
- **Orchestrate with Hermes cron, reuse existing scripts** — the capability already
  exists; the gap is orchestration + trust, not scoring. Hermes is an invoker, not
  a reimplementation.
- **Ticket signal = pattern + per-book regression, not raw score** — keeps the Jira
  board clean and avoids a false-positive flood from a 30B VLM, while still catching
  single-book breakage by comparing each book to its *own* prior score (R8a). Note:
  class-wide-drop detection is **net-new logic** layered on `compare_vqa_reports.py
  audit` (the audit does per-book and corpus-mean deltas, not type_axis grouping) —
  not free reuse.
- **Autonomy ramp T0 → T2, optional-on-evidence, behind a calibration gate** — the
  ramp *is* the de-risking mechanism. Ship T0 (zero blast radius), measure
  false-positive rate and signal volume, then build T2 only if the evidence justifies
  it, recording the decision as a logged EB-ticket comment (lightweight governance,
  not a formal ADR).
- **Nightly delta + weekly full re-sweep** — catches both new-content issues and
  regressions the code introduced; the weekly sweep is what closes the
  self-improvement loop on pipeline changes. (Open question: gate the heavy resweep
  on pipeline-code commits against the curated 10-book baseline rather than blind
  full-corpus — see Resolve Before Planning.)
- **Registry as foundation** — enables per-book regression (R8a) and dedup now, and
  the full ledger (R16) later, with no rework.

## Dependencies / Assumptions
- Hermes can invoke project `pwsh`/`python` over Windows interop — **verified** by
  the live Plex automation (`Get-PlexDownload.ps1` pattern).
- The vision Qwen node (`192.168.1.33:8080`) must be up with `n_ctx ≥ 32768`; a
  preflight gate for this already exists in `run_eb340_sweep2.ps1`.
- Jira primitives exist as **inline functions** `New-JiraIssue` and `Search-Issues`
  (not `Search-JiraIssues`) in `tools/Jira-BulkUpdate-2026-03-21.ps1`, with no
  `Export-ModuleMember` — they are not importable as-is. Planning must extract them
  into a reusable module before Hermes can call them, and the pipeline→ticket
  integration is net-new — verified.
- A dedicated, **scope-restricted Jira API token** (create/read issues on the EB
  project only — not the developer's personal full-access token), with a documented
  rotation cadence, must back the auto-file path; store it under the project's
  existing secrets pattern, not in any file Hermes can read directly.
- **Hard prerequisite (blocking, not just an assumption):** the EB-340 sweep2
  runner (PRs #170/#171) must merge to master before this work begins; the nightly
  loop builds on `tools/run_eb340_sweep2.ps1`, which exists only on the unmerged
  `feat/eb340-sweep2-runner` branch today. Its CLI and `run-summary.json` schema
  must be treated as a frozen shared interface before planning. (Note: this is a
  dependency on EB-340 *sweep2*, distinct from EB-340 Lanes B/C, which are out of
  scope per Scope Boundaries.)
- Jira API token resolves Windows-side; Hermes interop inherits Windows
  credentials (secrets do not cross into WSL).

## Outstanding Questions

### Resolve Before Planning
*(Product decisions are resolved; these are load-bearing technical questions the
document review surfaced as too central to defer silently. Treat them as the first
planning spikes — `ce:plan` should not produce an orchestration design without them.)*
- [Affects R8][Net-new + needs research] Define "class-wide drop" numerically (min
  class size, delta/window) **and** confirm it is built as net-new logic on the
  audit. This is the trust core; it has no definition or implementation today.
- [Affects R13][Needs research] Is the Qwen3-VL scorer deterministic enough for the
  gate? Measure night-to-night variance on identical input and specify the
  stability mechanism (temperature/seed pinning, or median-of-N re-scores). If the
  VLM is inherently noisy, R13(a) is untestable and any |Δ| threshold fires
  spuriously.
- [Affects R13][Design] Make the calibration gate a **standing canary**, not a
  one-time door: re-run the known-good baseline regularly; if it ever yields a
  fileable signal, T2 self-disables back to T0 (guards against post-promotion drift
  from model re-quant, Calibre/Poppler updates, n_ctx changes).
- [Affects R3/R13][Design] Regression gate must compare against a **frozen golden
  baseline** (human-re-baselined with recorded SHA/date), plus a cumulative-drift
  check vs. that golden — otherwise a rolling baseline ratifies slow decline and
  nothing ever fires.
- [Affects R1/R5][Technical] Resolve registry storage + reconciliation with the
  runner's `run-summary.json` here (load-bearing for dedup and resume); decide
  whether a delta-state file suffices until R16 vs. a full registry now.
- [Affects R5][Needs research] Does Hermes agent-mode tolerate multi-hour VQA
  batches, or must batches run script-mode fire-and-return with a completion hook
  (the Plex `qbit-finished` pattern)? R5's resume design forks on this.

### Deferred to Planning
- [Affects R11][Technical] Finding-fingerprint = stable **pattern identity**
  (type_axis + signal kind), not the specific set of books (which shifts with VLM
  noise); plus a **cooldown** so a signal does not re-file nightly while a linked fix
  PR is open or within N days post-merge before re-baseline.
- [Affects R4/R6][Security] Define an **authorization shim** as the real trust
  boundary: Hermes passes only a structured JSON payload to a narrow ticket-filing
  function that validates server-side and enforces R12a — Hermes cannot pass
  arbitrary args to `New-JiraIssue`.
- [Affects R7/R8][Security] **Untrusted-PDF / prompt-injection** containment: only
  structured fields (numeric scores, enum status) may reach Hermes' Qwen reasoning —
  never free text extracted from book content; carry forward the prior job-isolation
  decision for malicious files.
- [Affects R3][Cost] Per-book wall-clock budget and whether a full 432-book (growing)
  weekly sweep fits the overnight window on one vision node; consider chunking,
  rotating subsets, or gating the heavy resweep on pipeline-code commits against the
  10-book baseline instead.
- [Affects R4][Reliability] Loop-level behavior when the runner Preflight aborts
  (node down / n_ctx < 32768): post "failed" status, skip without enqueuing, define
  retry vs. manual-clear.
- [Affects R7][Security] Validate the vision scorer's JSON against schema before it
  reaches the classifier; treat malformed/adversarial responses as infra failures
  (R9), not valid scores.
- [Affects R4][Cross-project] Register the Hermes dependency in
  `project-dependencies.json` and confirm ADR-0043 T0/T1 infra is *implemented*, not
  only designed, before this work is scheduled.

## Next Steps
All **product** decisions are resolved. The `Resolve Before Planning` items are
load-bearing *technical* questions best answered as the first spikes inside planning
(they need codebase exploration and a determinism measurement, not more product
dialogue).
-> /ce:plan for structured implementation planning, opening with the trust-mechanics
spikes (signal definition, VLM determinism, frozen-golden baseline) before the
orchestration design. Gate the whole plan on the EB-340 #170/#171 merge prerequisite.
