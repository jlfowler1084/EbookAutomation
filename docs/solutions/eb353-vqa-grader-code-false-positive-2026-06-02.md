---
title: "EB-353 — VQA grader false-positive on legible code/syntax-template text"
date: 2026-06-02
ticket: EB-353
module: visual_qa, agents/qa-evaluation, llm_providers/local_provider
tags: [vqa, qwen3-vl, grader-calibration, prompt-engineering, false-positive, determinism, code-blocks]
problem_type: bug-fix
status: shipped-with-caveat
---

# EB-353 — VQA grader false-positive on legible code/syntax-template text

## Problem

The local Qwen3-VL VQA grader (`tools/visual_qa.py` → `agents/qa-evaluation/system-prompt.md`,
R9700 node `192.168.1.33:8080`) emitted false-positive `major`/`critical`
**"garbled OCR / extraction failure"** findings on **legible** content, cratering page scores
(23–50, pass=False) and threatening false escalation to paid Gemini/OCR (Tier 2.5). Ground-truthed
against rendered pages:

- **Python-in-Easy-Steps p62/76/80/94**: a legible if/elif/else **syntax template**
  (`statements-to-execute-when-test-expression-1-is-True`) flagged "severe text extraction failure".
- **Python p177/p201**: legible code (`lang="en">`, `var_1 = IntVar()`) flagged "garbled".
- **ML-for-Asset-Managers (abp06) p58**: a fully legible `def formBlockMatrix(...)` snippet flagged
  "significant corruption / genuine OCR artifacts".
- **abp06 p65/p66** (discovered during this work): the grader **hallucinated `cid:3`/`x2SX`
  corruption on clean prose pages and scored them 0** — the bug was broader than the ticket described.

## Root cause

The Text Integrity rubric conflated two orthogonal axes:

1. **Is the text legible?** (character correctness — the real text_integrity concern)
2. **Did code/templates keep their line breaks / indentation / monospace?** (a layout / paragraph_flow concern)

The rubric listed "OCR debris / garbled characters" as flags but never (a) defined what genuine
corruption *is*, (b) exempted code/identifier/operator/placeholder tokens, or (c) routed lost
formatting to the right category. So the VLM pattern-matched code's visual unusualness onto "OCR
corruption" and escalated severity.

## Fix (prompt-only, reversible)

Rewrote the Text Integrity section of `agents/qa-evaluation/system-prompt.md` (mirrored in the legacy
`tools/visual_qa_rubric.md`):

- **Legibility gate** — "if you can read/transcribe it, it is legible; legible text scores 70–100
  no matter how its lines are wrapped"; do NOT claim "OCR/extraction failure" or suggest re-running
  OCR on legible text.
- **Genuine-corruption definition** — requires *character-level evidence* you must quote: mojibake,
  `(cid:NN)` glyphs, the Unicode replacement character `U+FFFD`/boxes, math glyph-soup, random
  substitution. Only this is text_integrity corruption.
- **Code/template exemption** — source code, `camelCase`/`snake_case` identifiers, operators, and
  hyphenated placeholder/template tokens are legitimate content, never OCR debris.
- **Category routing** — legible text (code, template, or prose) that merely lost line structure is a
  `paragraph_flow`/`page_layout` issue at **at most moderate** severity, never major/critical.
- **Mixed-page rule** — a page may hold BOTH real corruption (math) and legible code; score regions
  independently so a `(cid:N)` equation does not make an adjacent legible snippet "illegible".
- **Pagination** — page-break truncation is not "missing/incomplete" content.

Also: `tools/llm_providers/local_provider.py` doc/comment references to rubric line numbers were
replaced with **section anchors** (the rubric edit shifted line numbers — caught by adversarial review).

Locked by `tests/test_vqa_grader_prompt_contract.py` (15 deterministic substring/codepoint
assertions on both prompt artifacts) so the guardrails cannot be silently deleted.

## Verification — what was reliable vs not

- **Reliable: render-based ground truth.** KFX→PDF→PNG renders of p62/p58/p65/p66/p51 were viewed
  directly. Confirmed the FPs are real bugs, the fix's direction is correct, and **genuine `(cid:N)`
  corruption is preserved** (abp06 p51/77/79 — recall-safe, the property EB-348 depends on).
- **Reliable: deterministic contract tests** (15 in the new prompt-contract file) + full `pytest tests/`
  suite **968 passed, 4 skipped** at ship time + manifest verified.
- **NOT reliable right now: live canary scores.** See determinism finding below.

## Key lessons (compounding)

### 1. Prompt over-engineering: every clause is also a false-positive surface
An adversarial review correctly noted the legibility gate could suppress genuine split-word defects,
and recommended a "split words remain a defect" carve-out. Adding it **empirically regressed** the
Python canary — the VLM adopted the new "split across lines with hyphens" framing and re-applied it
to the legible hyphenated templates (mechanistically confirmed in the finding text). **A
logically-valid review finding produced an empirically-harmful prompt change.** For LLM prompts, the
canary is the arbiter, not logical completeness — added guardrail text can create new FP hooks. The
carve-out was reverted; split-word recall is still covered by the pre-existing "Common issues" list.

### 2. The grader is NOT bit-deterministic under load — re-calibrate on a quiesced node
The ticket asserted determinism ("two runs 81≡81, 0/50"). Measured here: an early isolated
double-run was 0/50, but a later double-run diverged **5/50 per-page (±15–20)** with overall 77 vs 75
on identical input — while the *unfixed* prompt stayed at 80 across jobs. This is load-dependent
non-determinism on the shared R9700 node (matches the EB-340 "directional determinism" note), most
likely concurrent sessions interleaving on llama.cpp continuous batching. **Consequence:** canary
*score* deltas (86→78→77→75) are dominated by grader noise, not prompt edits — fine-grained
score-based prompt tuning is invalid until the grader is bit-deterministic. Per the calibration rule
("run twice on the same input; if results differ, fix the metric before using"), this is a harness
defect, tracked as a follow-up, and **must be resolved before trusting VQA scores, measuring EB-348
rendering deltas, or flipping `visual_qa.enabled`.**

### 3. Calibration discipline caught both the regression and the non-determinism
The matched back-to-back BEFORE/AFTER protocol + determinism double-runs + render spot-checks
surfaced the carve-out regression and the grader non-determinism that single-run score comparisons
would have hidden. Worth the cost.

## Follow-ups
1. **Grader determinism** (EB-361): make the local VQA grader bit-deterministic (single-client
   serialization or llama.cpp batching config), then re-baseline EB-353/EB-340 scores on a quiesced node.
2. **EB-348** (next): code-block + math `(cid:N)` rendering. Note PR #168 already merged its
   `<pre>`/code-block preservation + cid-glyph scoring; remaining scope is likely math→Gemini/MathML.
   Sequence after a deterministic grader so rendering-score deltas are measured cleanly (abp06 p51 is
   the canonical mixed case). EB-348 was marked **Done** via PR #168 (code-block/cid-scoring work) — but
   state-check first: any remaining math→Gemini/MathML scope may warrant a follow-up rather than reopening.
3. **Residual FPs** on the hardest dense code+math pages (abp06 p58/p62) persist intermittently under
   the non-deterministic grader; re-evaluate once the grader is deterministic.
