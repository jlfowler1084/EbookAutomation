---
title: VQA baseline methodology — five reusable patterns from SCRUM-282
type: solution
status: compound
date: 2026-04-20
origin_ticket: SCRUM-282
origin_plan: docs/plans/2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md
predecessor: docs/solutions/scrum-281-fallback-fingerprint-routing.md
related_tickets: [SCRUM-274, SCRUM-275, SCRUM-279, SCRUM-280, SCRUM-281, SCRUM-283, SCRUM-286, SCRUM-287]
tags: [vqa, baseline-methodology, provenance-field, audit-subcommand, git-rollback, temp-promote, stem-normalization, source-format-drift]
---

# VQA baseline methodology — five reusable patterns from SCRUM-282

Compound-knowledge writeup of five reusable patterns from the SCRUM-282 methodology fix. Written after PR #6 merged cleanly (`b8f7893`) with 10 commits on the branch and post-merge audit exiting 0 on all 6 baselines. The value isn't the fix itself — it's the small vocabulary of patterns that kept the work rigorous without overbuilding, and that can be reused for any future "data drift silently breaks regression gates" class of problem.

## Context

SCRUM-280's P2 Investigation (A) surfaced that the Atomic Habits Claude baseline in `data/vqa_baseline_post_274/` was captured from the original PDF source (266 pages) rather than the KFX→Calibre path (272 pages). Because `select_sample_pages()` in `tools/visual_qa.py` is deterministic on `(pages_total, bookmark_pages)`, the baseline sampled `[1, 2, 3, 73, 92, 145, 158, 232]` while live smoke runs sampled `[1, 2, 3, 91, 94, 149, 152, 238]` — zero interior-page overlap. Direct |Δ| comparison was unreliable; Atomic Habits had to be excluded from the R2 gate math as a result.

The 5 other books in the baseline directory happened to be parity-stable. No field on the baseline JSON recorded which source path produced it, so the drift class was only detectable after the fact by comparing sample arrays.

SCRUM-282 shipped: a reusable audit capability, a `capture_pipeline` provenance field, a capture-time KFX-shadow warning, an archived-and-recaptured Atomic Habits baseline, a backfill of the 5 in-parity baselines, and a CLAUDE.md rule. 10 commits, 46 passing tests, plus two follow-ups (SCRUM-286 for `--json` output, SCRUM-287 for exception-handling narrowing) filed from the `ce:review` pass.

The five patterns below are what compounded — the specific techniques worth remembering, not the solution itself.

---

## Lesson 1 — Name new provenance fields distinctly from existing ones, even if they seem to describe the same thing

**Pattern:** When adding a new field to record provenance (where something came from, how it was produced, which pipeline branch ran), check whether a field with the same name already exists elsewhere in the repo with *different* semantics. A same-named field with different semantics is worse than a distinct name, because readers will conflate them.

**Evidence:** The SCRUM-282 requirements doc proposed `source_format` as the new VQA-baseline field. The multi-persona plan review caught the collision: `source_format` already existed in `tools/test_pipeline.py:467`, `tools/pattern_db.py:162`, `module/EbookAutomation.psm1:6276`, and all 6 `test-corpus/*.baseline.json` files, where it carried extension-derived semantics (`"pdf"`, `"kfx"`). `tools/import_vqa_reports.py:92` was also already reading VQA baselines and deriving format from the `book` field's extension. A VQA-baseline field with the same name but pipeline-branch semantics would have silently conflated with the extraction-pipeline field. Renamed to `capture_pipeline` with values `"kfx-calibre"` / `"pdf-direct"` — distinct enough to rule out semantic conflation, and the value format itself names the pipeline branch rather than the input extension.

**Why this matters:** The entire point of SCRUM-282 was to fix a drift class rooted in ambiguous provenance. Shipping a same-named field with different semantics would have created the next drift class. "Clear semantics" is not a free property of a schema field — it's earned by keeping names and value ranges distinctive.

**When to apply:** Any time `ce:plan` proposes a new schema field, `ce:review` should grep for the field name across the repo before the plan is ratified. This is a cheap check and catches a high-impact class of error. For SCRUM-282 the grep took 2 seconds and changed the plan materially.

---

## Lesson 2 — Audit via the real determinism surface, not a pages_total proxy

**Pattern:** When a deterministic function produces an output that becomes a durable artifact (baseline, fingerprint, checksum), the audit that verifies the artifact's correctness should re-invoke the *same function* and compare the *actual output*, not a coarser proxy. Coarser proxies can coincidentally match while the real output drifts.

**Evidence:** The requirements doc initially specified auditing via `pages_total` diff — compare the baseline's stored page count against a fresh KFX-derived PDF's page count, mismatch means drift. The adversarial reviewer stress-tested this and surfaced the gap: `select_sample_pages(total_pages, bookmark_pages)` is deterministic on *both* inputs. Two source formats could coincidentally produce matching `pages_total` yet divergent `bookmark_pages`, which would yield different sampled pages — and the pages_total audit would pass with zero real signal. The fix: compare the `pages[].page_number` arrays directly. The baseline already stored these arrays from the original capture, so the audit has zero Claude API cost — a fresh local `convert_to_pdf` + `select_sample_pages()` run is enough. Verified end-to-end: the live corpus audit exits 0 on all 6 books, confirming the 5 in-parity baselines are genuinely in parity (not coincidentally so).

**Why this matters:** Audits often default to proxy checks because they feel faster or simpler. But a proxy that passes when the underlying property has drifted is worse than no audit — it creates false confidence. The cost of exercising the real function is usually tractable (here: local Calibre conversion per book, ~10 min wall-clock for 6 books).

**When to apply:** Any time you're writing a regression audit against a deterministic generator. Ask: "If I change the upstream inputs the function actually consumes, would my audit detect it?" If not, the audit is a proxy check wearing regression clothing.

---

## Lesson 3 — Shadow-detection warnings need normalized-stem matching, not byte-exact equality

**Pattern:** When a warning fires on "input X shadows existing artifact Y," the matching rule between X's name and Y's name must account for filename-convention drift — underscores vs spaces, trailing author suffixes, non-ASCII characters, case variation. Byte-exact stem equality misses exactly the cases the warning was written to catch.

**Evidence:** The original U3 plan specified "warn when PDF input stem matches a KFX stem." The feasibility reviewer caught that the motivating Atomic Habits case would *not* trigger: PDF stem `Atomic Habits_ Tiny Changes, ..., Break Bad Ones` has underscores and no author, while KFX stem `Atomic Habits Tiny Changes, ..., Break Bad Ones - James Clear` has spaces and a ` - James Clear` suffix. Byte-exact match fails on both axes. The plan was revised to use a 4-step normalization: lowercase → strip ` - <author>` suffix (with author-heuristic constraints) → replace non-alnum with space (with `re.UNICODE` so non-ASCII characters survive) → collapse whitespace. The `ce:review` pass then stress-tested the normalization itself and caught three more gotchas: non-ASCII titles collapsing to empty string (regex lacked `re.UNICODE`), leading-separator filenames also collapsing to empty (`sep_idx >= 0` accepted position 0), and embedded subtitles (`"Foo - A Subtitle"`) getting eaten by an unconstrained `rfind` suffix strip.

**Why this matters:** Normalization rules are a classic source of subtle bugs. Each step can have edge cases that cancel out the intended behavior. The discipline that caught the gaps was: *always construct adversarial inputs that would defeat the heuristic before calling it done*. Write the test cases before the code. The sibling compound doc SCRUM-281 shipped a similar pattern — fingerprint detection needs adversarial calibration against inputs the detector wasn't written for.

**When to apply:** Any time you're writing a string-match rule between two names that originated from different tool chains. The tools' naming conventions will diverge; your match rule has to collapse the divergence without collapsing legitimate differences into false matches.

---

## Lesson 4 — Destructive data operations ship as temp-promote + two-commit sequences, not single commits

**Pattern:** When a data operation is irreversible or expensive to replay (a re-capture that costs real API spend, an archive-and-replace, a backfill that transforms existing records), the ship sequence should validate the new artifact in a scratch location *before* touching the active location, and split the state transition across two commits so `git revert` is a genuine rollback path.

**Evidence:** SCRUM-282's U4 re-captured the Atomic Habits Claude baseline via the KFX pipeline at a cost of $0.079 in Claude Sonnet Vision spend. The original plan had a single-commit protocol: `git mv` the drifted baseline to `.archive/`, run the re-capture, write the new baseline — one commit. The plan-review adversarial reviewer caught the hazard: if the re-capture failed mid-flight (API outage, KFX corruption, network glitch), the active baseline directory would be missing Atomic Habits until the operator manually restored it. Worse, the existing `output/kindle/Atomic Habits...James Clear_visual_qa_report.json` (an April 18 smoke run) would be silently overwritten by the re-capture write. The revised protocol: (1) re-capture to `/tmp/scrum-282-recapture/` in a scratch dir; (2) run the audit subcommand against the scratch file and halt if it doesn't exit 0; (3) Commit A = archive move only; (4) Commit B = promote the validated scratch file into the active directory. Rollback becomes `git revert HEAD~1..HEAD` and atomically restores both the archive and the original baseline. Executed exactly this way in the shipped branch.

**Why this matters:** "One commit per logical change" is a good default, but destructive data operations *are not a single logical change* — they're a transaction consisting of a pre-state archive, a validation, and a post-state promotion. Collapsing them into one commit destroys the rollback guarantee. The two-commit split costs nothing at ship time and saves the operator when something goes wrong between the archive and the promote.

**When to apply:** Any operation that (a) costs real money to replay, (b) transforms data in place, or (c) depends on an external service succeeding. Replace single-commit with archive-commit → validate-in-scratch → promote-commit. If the validation step lives in a separate tool (like U1's audit subcommand here), so much the better — the validation becomes reusable.

---

## Lesson 5 — Check git-tracking status before designing git-based rollback protocols on data files

**Pattern:** Plans that rely on `git mv`, `git revert`, or any git history operation for rollback must verify the target files are actually git-tracked. Data directories (`data/`, `output/`, `fixtures/`, `artifacts/`) are commonly `.gitignore`'d in projects where they hold operator-local or build-output artifacts. A planned rollback protocol against ignored files is a no-op — commits would be empty and `git revert` would have nothing to undo.

**Evidence:** This was the one planning-phase miss that survived into implementation. The SCRUM-282 plan's temp-promote protocol (Lesson 4) assumed `data/vqa_baseline_post_274/` was git-tracked. It wasn't — `data/vqa_baseline_post_274/` appeared in `.gitignore`. The Sonnet implementer caught it in Phase 5 pre-flight and halted with two issues: (a) the baselines are gitignored, so `git mv` and the two-commit protocol produce empty commits, (b) `/tmp` doesn't exist on Windows. Resolved by adding a pre-commit that lifted the gitignore and initial-tracked the 6 existing baselines, then proceeded with the planned protocol. Afterward, added a feedback memory note for future `ce:plan` passes: run `git ls-files <target>` as a Phase 1 audit step before designing any git-based rollback.

**Why this matters:** This is the hardest kind of planning miss to catch in review — the omission is not in what the plan *says*, it's in what the plan *assumes*. Document reviewers can stress-test explicit decisions but struggle to catch unexamined preconditions. The fix is mechanical: make "are the target files tracked?" an explicit checklist item in Phase 1 audits when the plan touches `data/`, `output/`, or similar directories.

**When to apply:** At the start of any `ce:plan` that touches files outside `src/`, `tools/`, `tests/`, or other directories known to be tracked by convention. Add to Phase 1 pre-flight: `git ls-files <target-dir> | head` — if empty, the dir is ignored and any git-based protocol against it needs a tracking-lift step first.

---

## Meta-lesson — Review rigor earns its keep on real bugs, not theoretical ones

Running `document-review` on the requirements doc surfaced 3 P1 improvements; running `document-review` on the plan surfaced 4 P1 improvements; running `ce:review` on the implementation surfaced 6 P1 findings (4 fixed in-branch, 2 deferred to SCRUM-286/SCRUM-287). Each review pass caught *different* classes of problem that earlier passes couldn't see.

- **Requirements review** caught *product-level* gaps — the audit mechanism was too weak, the schema field name was wrong, stem consistency wasn't a requirement.
- **Plan review** caught *architectural* gaps — the `source_format` collision with existing fields, the U4 single-commit rollback hazard, the U3 normalization's false-match paths.
- **Code review** caught *implementation* gaps — non-ASCII normalization bug, hardcoded `max_samples`, bare-invocation crash, test hermeticity violation.

The aggregate result: 13 P1 issues surfaced and addressed, across three review tiers, all before merge. Two of them (the field collision and the non-ASCII normalization bug) were *latent data correctness issues* that would have fired silently in production. No single reviewer could have found them all.

The practical pattern: run the full CE cycle — `ce:brainstorm` → `document-review` → `ce:plan` → `document-review` → `ce:work` → `ce:review` → merge — on any change with durable consequences. The cost is real (multiple reviewer passes, multiple rounds of revisions) but the alternative is shipping latent bugs that get discovered next quarter when the corpus grows.

---

## References

- Plan: `docs/plans/2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md`
- Requirements: `docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md`
- Predecessor compound docs:
  - `docs/solutions/scrum-280-local-vqa-calibration-patterns.md`
  - `docs/solutions/scrum-281-fallback-fingerprint-routing.md`
  - `docs/solutions/scrum-283-cloud-vlm-evaluation.md`
- Merge commit: `b8f7893`
- Key code sites:
  - `tools/compare_vqa_reports.py::_cmd_audit` (Lesson 2 — sampled-pages audit)
  - `tools/visual_qa.py::_normalize_book_stem` (Lesson 3 — normalization rule)
  - `tools/visual_qa.py::_get_kfx_dir` (test hermeticity seam)
- Follow-ups filed: SCRUM-286 (`--json` output), SCRUM-287 (exception taxonomy)
