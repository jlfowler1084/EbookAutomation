---
date: 2026-04-13
topic: local-llm-integration-opportunities
status: brainstorm
hardware: RTX Pro 6000 Blackwell (96 GB VRAM)
models:
  - Qwen/Qwen3-VL-30B-A3B-Instruct-FP8 — vision-language MoE (30B total / ~3B active), vLLM on :8000
  - Qwen/Qwen3-Embedding-4B — embeddings, vLLM on :8001
---

# Local LLM Integration Opportunities — EbookAutomation

## Context

Joe has new hardware (RTX Pro 6000 Blackwell, 96 GB VRAM) and is running local
models via vLLM in WSL Docker containers with OpenAI-compatible APIs:

- **Port 8000** — `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8`. Vision-language MoE
  (30B total, ~3B active per token). Chosen because native FP8 weights map
  directly to Blackwell's FP8 tensor cores, the MoE architecture delivers
  dense-3B-class decode throughput for per-page scans, and Qwen3-VL's
  document-AI and OCR quality is measurably better than Qwen2.5-VL.
- **Port 8001** — `Qwen/Qwen3-Embedding-4B`

Both expose OpenAI-compatible endpoints (`/v1/chat/completions`,
`/v1/embeddings`), so integration is a thin client swap rather than a rewrite.

The strategic goal is to move expensive per-page AI work off Claude/Gemini APIs
and onto local inference, unlocking capabilities that are currently cost-gated
(full-book visual QA, per-page OCR fallback) while preserving Claude for
architectural reasoning and low-confidence escalation.

## Deployment Reference

```bash
# Qwen3-VL vision-language (MoE, native FP8 for Blackwell)
docker run --runtime nvidia --gpus all \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --env "HF_TOKEN=$HF_TOKEN" \
  -p 8000:8000 --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct-FP8 \
  --kv-cache-dtype fp8 \
  --max-model-len 65536 \
  --limit-mm-per-prompt '{"image": 16}' \
  --gpu-memory-utilization 0.80 \
  --trust-remote-code \
  --served-model-name qwen3-vl

# Qwen3 embedding model
docker run --runtime nvidia --gpus all \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --env "HF_TOKEN=$HF_TOKEN" \
  -p 8001:8000 --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-Embedding-4B \
  --trust-remote-code \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.12 \
  --served-model-name qwen3-embedding-4b
```

Notes on the VL command:

- `--quantization fp8` is omitted because the model ships with FP8 weights
  already — vLLM auto-detects the FP8 checkpoint. Passing `--quantization fp8`
  forces on-the-fly quantization of FP16 weights and will fail on a native
  FP8 model.
- `--limit-mm-per-prompt '{"image": 16}'` raises the default multi-image
  cap so full-book visual QA can batch 8–16 pages into a single request.
- `--trust-remote-code` is required for Qwen3-VL's custom image processor.

GPU budget rationale: Qwen3-VL-30B-A3B at FP8 is roughly 35–45 GB for weights
plus KV cache at 65k context. Running concurrently with the embedding model
(~10 GB) fits in 96 GB with headroom. For full-book VQA runs, stop the
embedding server to free VRAM for larger batch sizes and longer KV cache —
they don't need to run simultaneously.

## Integration Opportunities

Each opportunity is scored against three dimensions:

- **Value** — how much this improves book quality or unlocks new capability
- **Effort** — rough implementation complexity
- **Risk** — regression risk to the existing pipeline

### Vision Model (Qwen3-VL)

#### 1. Full-book visual QA on every page ★★★ TOP PRIORITY

**Value:** high · **Effort:** medium · **Risk:** low

Today `tools/visual_qa.py` samples 8 pages (20 in full mode) because Claude
Vision costs prohibit per-page scans on a 400-page book. Local inference
removes that cap entirely, enabling whole-book structural validation — the
exact regression detection the project's #1 time sink (fix-then-regression
cycles) needs.

Planned as a separate document: `docs/plans/2026-04-13-001-local-llm-visual-qa.md`.

#### 2. Tier-2 OCR ahead of Gemini

**Value:** high · **Effort:** medium · **Risk:** medium

Current OCR tier order:

```
pdfminer → pypdf → PyMuPDF → Gemini 2.0 Flash
```

Insert Qwen3-VL between PyMuPDF and Gemini. Local becomes the primary fallback
for pages where text extractors fail; Gemini becomes the last resort. Expected
outcome: Gemini API spend drops ~80% on scanned-page books while OCR quality
stays comparable on layout-clean pages.

**Risk note:** Qwen3-VL's OCR quality on noisy scans is not yet benchmarked
against Gemini 2.0 Flash on our test corpus. Needs a side-by-side eval on
Mexico Illicit before promotion.

#### 3. Layout-aware reading-order extraction

**Value:** medium-high · **Effort:** high · **Risk:** medium

Current multi-column extraction uses PyMuPDF coordinate heuristics via
pdfplumber. VL models can directly output JSON: `{ regions: [{bbox, text,
role}] }` that preserves reading order. Potentially replaces the brittle
column-detection filters (`docs/superpowers/plans/2026-03-21-two-column-*`).

Best treated as an A/B experiment rather than a straight replacement — the
coordinate-based path is fast and deterministic.

#### 4. Heading classification from rendered pages

**Value:** medium · **Effort:** medium · **Risk:** medium

Heading classification today uses font-size + regex signals from extracted
text. A VL model sees the rendered page, so it picks up visual weight,
position, and whitespace context that raw font metadata misses. Directly
targets the recurring "body tagged as heading" regression noted in CLAUDE.md.

**Escalation pattern:** run VL classification on pages where the text-based
classifier confidence is below threshold, not on every page.

#### 5. Figure and table captioning

**Value:** medium · **Effort:** low · **Risk:** low

TTS output currently goes silent at figures. VL captioning inserts a spoken
description ("Figure 3.2: a bar chart comparing …"), which dramatically
improves audiobook listenability for non-fiction. Low-risk add-on — doesn't
touch extraction logic.

#### 6. Visual diff for before/after conversion

**Value:** low-medium · **Effort:** medium · **Risk:** low

Render source PDF page next to rendered KFX page, ask VL model to flag
differences (missing paragraphs, dropped figures, reordered content). This is
a regression tool, not a shipping feature — runs during CI-style validation.

### Embedding Model (Qwen3-Embedding-4B)

#### 7. Semantic chapter boundary detection

**Value:** high · **Effort:** medium · **Risk:** low

Embed each paragraph, compute similarity between adjacent paragraphs, detect
drift spikes as chapter boundary candidates. Complements TOC/bookmark
reconciliation — catches chapters with stylistic rather than explicit markers
(Lincoln Highway's multi-narrator chapters). Runs as a confirmation signal:
high-drift + existing heading = strong chapter; high-drift + no heading =
candidate for review.

#### 8. Footnote ↔ reference linking via semantic match

**Value:** high · **Effort:** medium · **Risk:** medium

Current footnote pairing uses numeric markers, which breaks on dual-numbering
systems (Oil Kings). Embedding each footnote body and each in-text reference
context, then matching by semantic similarity, sidesteps numeric ambiguity
entirely. Requires careful fallback logic — numeric matching should stay as
the primary signal with semantic match as a disambiguator when numbers
collide.

#### 9. TOC reconciliation across OCR noise

**Value:** medium · **Effort:** low · **Risk:** low

Detected headings often drift from the source PDF's TOC entries due to OCR
noise and ligature artifacts. Embedding both and matching by cosine similarity
handles variants the current string-match path misses.

#### 10. Cross-book semantic search

**Value:** medium · **Effort:** medium · **Risk:** low

Index every processed book's chapter text into a local vector store. Enables:

- "Find books similar to X" for reuse of extraction profiles
- Query-driven research across your personal library
- FOH brief generation can pull thematically related entries

Not a pipeline feature — a standalone knowledge tool.

#### 11. Boilerplate and running-header detection

**Value:** medium · **Effort:** low · **Risk:** low

Embed text chunks that appear on multiple pages; high-similarity clusters
across page boundaries are almost always running headers, page numbers,
publisher boilerplate, or chapter-title headers repeated on every page.
Cleaner than the current regex-based header stripping, and generalizes across
books.

### Text Generation (Qwen3-VL in text mode)

#### 12. Structure Analysis Agent offload

**Value:** high · **Effort:** low · **Risk:** low

`docs/AI_Quality_Pass_Design.md` defines a pre-extraction structure analysis
agent currently running on Claude Haiku. Qwen3 can replace it with zero per-
book cost, enabling the pipeline to run structure analysis on every book
instead of only those flagged by pre-flight.

#### 13. QA Evaluation Agent offload

**Value:** medium · **Effort:** low · **Risk:** low

Same move for the post-conversion QA agent. Runs locally on every conversion,
flags issues, escalates only uncertain cases to Claude.

#### 14. Book metadata inference from cover and title pages

**Value:** medium · **Effort:** low · **Risk:** low

When embedded PDF metadata is missing and filename parsing fails, VL + text
model can read the cover/title/copyright pages and populate the metadata
fields directly. Replaces user-prompt fallback with automatic recovery.

#### 15. FOH daily brief summarization

**Value:** medium · **Effort:** low · **Risk:** low

FOH forum scraper currently calls Claude for summarization. Perfect local job —
runs on a schedule, no rate limit, unlimited rewrites for tone tuning.

## Escalation and Tiering Principles

Local inference should sit inside a unified tiering layer so tier promotion is
explicit and reversible:

```
Tier 0 — deterministic / rules-based (pdfminer, regex, coordinate heuristics)
Tier 1 — local model (Qwen3-VL / Qwen3-Embedding)
Tier 2 — cloud fallback (Gemini for OCR, Claude for reasoning)
Tier 3 — human review (explicit escalation flag)
```

Every opportunity above is a Tier 1 candidate. The tiering layer should
record, per page and per book, which tier produced the final output — that
becomes the audit trail for regressions. A consistent `tools/llm_client.py`
abstraction across Claude, Gemini, and local endpoints makes this
straightforward.

## What Should NOT Move Local

- **Plan generation and architectural reasoning** — stays on Claude Opus.
  Local models are not a substitute for structured planning and multi-file
  code reasoning.
- **Low-confidence visual QA cases** — escalate to Claude Vision. Local model
  becomes the filter, not the final judge.
- **Contract-sensitive regression audits** — where an authoritative signal
  matters for shipping decisions, pay for Claude.

## Prioritized Implementation Order

1. **Visual QA on every page** (opportunity #1) — planned separately
2. **Structure Analysis Agent offload** (#12) — lowest-risk quick win
3. **Tier-2 OCR on Qwen3-VL** (#2) — highest API-cost reduction
4. **Semantic chapter boundary detection** (#7) — targets known regression
   class
5. **Figure and table captioning** (#5) — listenability win for audiobooks
6. **Footnote semantic linking** (#8) — targets Oil Kings-class failures
7. **Everything else** — opportunistic

## Open Questions

1. **Concurrency envelope.** What's the max pages/sec Qwen3-VL-30B-A3B can
   process on Blackwell at 1024×1024 input resolution? Drives batch sizing
   for the visual QA loop. Measure during Phase 3 of the visual QA plan.
2. **Unified client abstraction.** Build `tools/llm_client.py` now as part of
   visual QA work, or defer until there's a second consumer?
3. **Cost tracking.** With local inference free, the cost-budget telemetry in
   `docs/api-cost-audit.md` needs a new dimension: local GPU-hours instead of
   dollars. Probably low priority but worth noting.
4. **Fallback to dense 32B.** If Qwen3-VL-30B-A3B's OCR calibration is
   weaker than expected during Phase 5 baseline comparison, the fallback is
   `Qwen/Qwen2.5-VL-32B-Instruct` served at FP8 via vLLM's on-the-fly
   quantization — 2–3× slower per page but measurably stronger on hard
   visual reasoning.

## Related Documents

- `docs/plans/2026-04-13-001-local-llm-visual-qa.md` (next step)
- `tools/visual_qa.py` — current Claude-only implementation
- `docs/superpowers/analysis/2026-03-24-vqa-quality-baseline.md` — baseline
  quality metrics to beat
- `docs/AI_Quality_Pass_Design.md` — existing AI agent design
- `docs/api-cost-audit.md` — cost baseline to track reductions against
