---
ticket: SCRUM-295
type: subagent-swarm-stream
model: claude-sonnet-4-6
branch: worktree/SCRUM-295-vqa-bert-timeout
worktree_dir: .worktrees/worktree-SCRUM-295-vqa-bert-timeout
swarm_session: 2026-04-25
created: 2026-04-25
---

# SCRUM-295 — VQA subprocess hits 300s timeout on BERT_Pre_Training

## Mission
Diagnose the silent 300s timeout on `BERT_Pre_Training.pdf` VQA, identify root cause, and either (a) make it complete in <60s or (b) make it report a diagnostic error instead of silently timing out. **Diagnose first; do not just bump the timeout.**

## In-scope files (verified)
- `tools/visual_qa.py` — entry point
- `tools/batch_qa.py` — outer 300s subprocess timeout lives at `run_visual_qa_for_book` (~line 729)
- `tools/llm_providers/cloud_vl_provider.py` — actual cloud-VLM HTTP path; suspected hang lives here
- `test-corpus/a2-pilot/BERT_Pre_Training.pdf` (source) — verify the corresponding KFX exists under `output/kindle/` before reproducing

You may add diagnostic logging anywhere in the three files above. **Out of scope:** `tools/llm_providers/claude_provider.py` (fallback path — not the failing path).

## Parallelization Map (per INFRA-216 pilot)
- **Branch:** `worktree/SCRUM-295-vqa-bert-timeout`
- **Files touched:** `tools/visual_qa.py`, `tools/batch_qa.py` (~line 729, the outer subprocess timeout), `tools/llm_providers/cloud_vl_provider.py` (suspected hang location). May add diagnostic logging in any of the three.
- **Dependencies:** none. VQA subsystem is fully isolated from extraction/linker/PowerShell streams.
- **Shared interfaces frozen:** the VQA subprocess result schema (`{score, passed, category_scores, api_cost_usd, duration_seconds, ...}`) — coordinator and downstream batch scripts depend on this shape. **Do not** change keys.
- **Overlap risk:** zero. No other stream touches `tools/llm_providers/` or VQA orchestration.
- **Merge order:** any time. Independent of other streams.
- **Merge gate:** BERT VQA completes in <60s **OR** exits with a diagnostic error (not silent timeout); Foucault and MapReduce canaries still pass; PR description contains a "Root cause" paragraph.
- **Checkpoint commit:** `fix(SCRUM-295):` with root cause in the commit message body.
- **Intent summary (drift defense):** "Diagnose the silent 300s hang on BERT, fix the root cause OR turn the timeout into a diagnostic error. Do NOT just bump the outer timeout. Do NOT rewrite cloud_vl_provider's retry logic from scratch."

## Worktree setup
1. Branch: `worktree/SCRUM-295-vqa-bert-timeout`
2. Directory: `.worktrees/worktree-SCRUM-295-vqa-bert-timeout`
3. **No `mklink /J` junctions.** CLAUDE.md 2026-04-22 incident.
4. VQA needs corpus + API key:
   ```pwsh
   $env:ARCHIVE_DIR        = 'F:\Projects\EbookAutomation\archive'
   $env:OUTPUT_DIR         = 'F:\Projects\EbookAutomation\output'
   $env:OPENROUTER_API_KEY = '<already set in your shell — verify with [Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY","User")>'
   ```
   Coordinator confirms `OPENROUTER_API_KEY` is set at the user/system scope.

## Reproduction (from ticket)
SCRUM-290 batch `batch_20260421_102832`:
```json
"visual_qa": {
  "attempted": true,
  "score": null,
  "passed": false,
  "category_scores": {},
  "api_cost_usd": 0,
  "duration_seconds": 300.0
}
```
`duration_seconds == 300` exactly = the hard cap in `tools/batch_qa.py::run_visual_qa_for_book`. Not crash, not completion — silent stop.

Reference KFX: `test-corpus/a2-pilot/BERT_Pre_Training.pdf` (13 pages, 0.7 MB source → 1.4 MB KFX). Foucault canary: similar size, ~36s VQA. Expected wall-time: ~30s for 8-page quick mode.

## Investigation steps (do these in order, document each)
1. **Reproduce in isolation.** Re-run `python tools/visual_qa.py` against the BERT KFX directly (not via batch). Is the timeout deterministic or transient?
2. **Add verbose logging** in `cloud_vl_provider.py` around each batch HTTP request and response parsing step. Find where time is actually spent. Capture a verbose log of one full hung run; attach to PR.
3. **Try `--full` mode** (20 pages at 150 DPI). Does the symptom change? (Helps distinguish quick-mode-specific from layout-specific.)
4. **Compare with MapReduce** (the other double-column ML paper from A2 pilot). It scored fine in 49s. Same provider, same batch shape — what's different about BERT?
5. **Check for retry loop** in `cloud_vl_provider.py`. SCRUM-283 pattern (`OutputTruncatedError`) is one suspect — verify by inspecting whether the outer 300s is being consumed by inner retries with no backoff cap.
6. **Decision point.** After steps 1–5, write the "Root cause" paragraph in your PR description:
   - If root cause is **clear and locally fixable** (retry loop, missing per-request timeout, parse error) → proceed to fix.
   - If root cause is **a provider-side hang you cannot fix locally** → take the diagnostic-error acceptance path: add logging that names the failure mode and surfaces a non-silent timeout. Do **not** wedge a speculative fix.
   - If root cause is **still unclear after 5 steps** → stop and report to the coordinator with your evidence. Do not loop back to step 1 with new assumptions; that's the smell of throwing fixes at the wall.

## Acceptance (from ticket)
- [ ] Root cause identified and documented in PR.
- [ ] BERT VQA either completes within 60s OR reports a diagnostic error (not silent timeout).
- [ ] If network-related: add a shorter VLM-call timeout (e.g., 60s per request) with explicit retry, rather than relying on a single 300s outer timeout.

## Drift watchpoints (HARD)
- **DIAGNOSE BEFORE FIX.** The PR description must contain a paragraph titled "Root cause" with a clear explanation. If you can't write that paragraph honestly, you haven't finished — do not patch around the symptom.
- **DO NOT** simply bump the 300s outer timeout. That's not a fix; that's hiding the bug. If your final diff is `300 → 600`, the PR is rejected.
- **DO NOT** rewrite `cloud_vl_provider.py` retry logic from scratch. If retries are part of the cause, add a per-request timeout and a retry **cap**, but keep the existing structure.
- **DO NOT** disable cloud VQA and fall back to Claude as the fix. Claude fallback is for known-fingerprint failures (SCRUM-281), not for "the cloud provider hung once." Fix the cloud path or report a diagnostic error.
- **DO NOT** edit `tools/batch_qa.py` orchestration unless the bug is genuinely there. Symptom appears in `batch_qa.py`, but the ticket suspects `cloud_vl_provider.py` is upstream of the hang. Edit the upstream file.
- If the root cause turns out to be a model/provider issue you can't fix locally (provider returns malformed response, etc.), **stop** and report to the coordinator. The acceptance "report diagnostic error" path is the right call there — don't wedge a half-fix.

## Pre-merge gates
1. **BERT VQA completes** in isolation in <60s, OR exits with a diagnostic error message that names the failure mode (timeout, retry-cap-exceeded, parse-error, etc.).
2. **Foucault canary still works** (similar-size book that was passing). Run VQA on Foucault — confirm no regression.
3. **MapReduce still works** (other double-column ML paper). Confirm no regression on the book that was already fine.
4. If a per-request timeout was added: unit test or smoke test that the new timeout fires when expected.

You do **not** need to run the 6-book regression suite — VQA changes don't touch extraction.

## Commit + PR
- Commit prefix: `fix(SCRUM-295):` for the diagnostic + fix. `test(SCRUM-295):` if smoke tests added.
- Open PR titled `SCRUM-295: Fix VQA silent timeout on BERT (root cause: <X>)`. Title must include the root cause in one phrase. Body must include:
  - **Root cause** paragraph (mandatory)
  - Verbose-log evidence
  - Before/after timing on BERT, Foucault, MapReduce
  - Explicit "I did NOT just bump the outer timeout" line if the change is timeout-related
- **DO NOT merge.** Coordinator merges.

## CE compound step
After PR merges, write `docs/solutions/scrum-295-vqa-bert-timeout.md`. Cover: the SCRUM-290 A2 batch → SCRUM-295 chain, the actual root cause (truncation? retry loop? provider hang?), the relationship to SCRUM-283 if any, and the diagnostic-error pattern as a future-proofing tool against silent timeouts.

## Out of scope (explicit)
- General VQA performance optimization. This is one book, one symptom, one fix.
- DocVQA-shaped failure detection (SCRUM-284). Separate ticket.
- Switching to a different VLM provider. Provider choice is upstream of this ticket.
- Migrating cloud VQA to streaming responses. Architectural — not within this scope.

## Reporting back
On PR open, post to the coordinator:
- PR URL
- One-sentence root cause
- Before/after timing on the three reference books (BERT, Foucault, MapReduce)
- Whether you completed BERT in <60s or chose the diagnostic-error path (and why)
- Any drift you suppressed
