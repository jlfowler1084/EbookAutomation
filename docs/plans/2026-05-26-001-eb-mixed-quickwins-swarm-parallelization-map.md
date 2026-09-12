# Parallelization Map — Mixed Quick-Wins Swarm (2026-05-26)

**Coordinator:** main session (Opus) · **Delivery:** each stream = own `.worktrees/` branch → PR → coordinator merges in order
**Base branch:** `master` · **Test:** `python -m pytest tests/`

## Streams

| Stream | Ticket | Branch | Files owned (FENCED — touch nothing else) | Intent summary (drift defense) |
|---|---|---|---|---|
| A | EB-255 | `feat/EB-255-run-premium-fix` | `web_service/pipeline_runner.py` (`run_premium`, L326), `tests/test_pipeline_runner*.py` | Make premium tier actually convert: fix `pdf_to_balabolka.py` invocation flags + add the Calibre `ebook-convert` step. Free tier untouched. |
| B | EB-253 | `feat/EB-253-utm-attribution` | `web_service/routes/checkout.py`, frontend checkout/success components, `docs/marketing/utm-conventions.md` | Pass UTM params through Stripe Checkout end-to-end so attribution survives the redirect. |
| C | EB-290 | `feat/EB-290-scribe-hero` | `web_service/frontend/app/(app)/` hero, `web_service/frontend/public/` image assets | Add a real (existing, verified-Scribe) screenshot to the homepage hero. Reuse images from `/guides/pdf-to-kfx-for-kindle-scribe`. No LCP regression. |
| D | EB-305 | `feat/EB-305-output-format-demand` | new file under `docs/marketing/` only | Research demand for additional output formats (forum scrape + competitor landscape) → one committed doc. |

## Overlap check (pre-spawn)
- A = backend only (`pipeline_runner.py`); B = `routes/checkout.py` + frontend checkout; C = frontend homepage hero; D = docs only.
- **B and C both under `web_service/frontend/`** but in disjoint page trees (checkout/success vs `(app)` hero). Shared-risk files (`globals.css`, `layout.tsx`, analytics lib) are **frozen** — neither stream edits them; flag to coordinator if needed.
- No stream writes another's files → safe to run all 4 concurrently.

## Merge order
D → A → C → B (doc-only first; B last, carries the signed-event e2e gate).

## Merge gate (per PR, coordinator-owned)
1. Diff stays inside fenced files.
2. `python -m pytest tests/` green (A, B).
3. C: Lighthouse Perf on `/` not regressed vs pre-EB-279 baseline.
4. Stream return checkpoint diff matches the intent summary above (premise-drift check).

## Excluded (with reason)
- **EB-278** (DMARC) — time-gated to 2026-06-15; production-email risk; AC#1 needs human report review.
- **EB-294** (keyword discovery) — paid tool + GSC + manual SERP; deliverable doc already partly exists.
- **EB-321** — overlaps Stream A in `run_premium`; sequence *after* EB-255 lands.
- **EB-237** — also edits `pipeline_runner.py`; conflicts with Stream A.
