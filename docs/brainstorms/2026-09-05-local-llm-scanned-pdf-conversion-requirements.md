# Local-LLM Upgrade for PDF-to-Kindle Conversion — Requirements & Phased Plan

**Date:** 2026-09-05
**Status:** Approved by Joe 2026-09-05 — decisions in §9; next step is the Phase 0 implementation plan
**Ticket:** Epic **EB-391**. Phases: EB-392 (P0), EB-393 (P1), EB-394 (P2), EB-395 (P3), EB-396 (P4), EB-397 (P5), each blocked by the previous. Cross-project: **SB-231** (sb-vision ctx raise).
**Scope:** PDF-to-Kindle conversion only. Web service, TTS, FOH brief, and book_filer are out of scope except where they share a call site.

## 1. Goal

Joe now has a much stronger local text LLM ("Qwen Flash", Qwen3.8-Flash-Next on the
RTX PRO 6000 96 GB) and a local Qwen3-VL vision model on the second PC (R9700 32 GB).
Three outcomes are wanted:

1. **Zero cloud dependency** for the conversion pipeline — retire the Claude and Gemini
   API calls that visual QA, OCR, and structure detection currently make.
2. **Poor-quality image-scanned PDFs convert into something readable on a Kindle** — today
   this class fails (scan-class VQA mean 57.4, floor 12).
3. **A repeatable benchmark loop** over books that have historically failed, so every
   change is measured against the same corpus before and after.

## 2. Findings (current state, 2026-09-05)

### 2.1 Cloud AI call sites in the conversion path

| Site | Purpose | Provider | Local option today? |
|---|---|---|---|
| `tools/extract_tts_text.py` ~L10589 | sub-heading (h3) classification | Anthropic haiku, hardcoded `requests.post` | **No** |
| `tools/extract_tts_text.py` ~L10793 | AI rejoin of page-split fragments | Anthropic haiku | **No** |
| `tools/extract_tts_text.py` ~L11050 / ~L11499 | AI quality pass (detect + verify) | Anthropic haiku | **No** |
| `tools/extract_tts_text.py` ~L2190 | Tier 3 Claude Vision OCR | Anthropic sonnet | **No — and dead code**: imports `call_claude_vision`, removed in SCRUM-274 |
| `tools/gemini_ocr.py` | Tier 2.5 whole-book OCR + page remediation | Google Gemini SDK | **No** |
| `module/EbookAutomation.psm1` L5113-5360 | chapter/structure detection (`Get-ChapterStructure`) | Anthropic sonnet via `Invoke-RestMethod`; **auto-enabled for every PDF when `ANTHROPIC_API_KEY` is set** | **No** |
| `tools/llm_providers/local_provider.py` | VQA grading | local (OpenAI-compatible) | Yes — default |
| `tools/llm_providers/claude_provider.py` via `visual_qa.py` | VQA fingerprint fallback | Anthropic sonnet; **on by default** (`visual_qa.fallback.enabled: true`) | Config-only fix |

There is a vision-provider abstraction (`tools/llm_providers/`) but **no text-LLM provider
abstraction** at all. The Flash model is only reachable through raw HTTP today.

### 2.2 The scanned-PDF path is broken by wiring, not by OCR quality

All of the following are confirmed against source:

1. `-UseOCR` / `--ocr` is a **no-op on the live Kindle HTML path**. `process_kindle_html`
   has no OCR parameter; `args.ocr` is only read in the TTS branch (`extract_tts_text.py`
   ~L14903). The converge loop's `'ocr'` strategy routes to `process_kindle`, which has no
   OCR code at all.
2. The EB-349 classifier-driven escalation is **dead code**: `classifier_verdict` is never
   passed from the CLI (already ticketed as EB-362, undecided).
3. The only live auto-trigger for LLM OCR is debris density ≥ 0.15 — which is ~0 on a
   truly text-free scan, so the books that most need OCR never trigger it.
4. `auto_gemini_on_scan` is `false` in `config/settings.json`; the classifier's
   `ocr,gemini` recommendation is logged and ignored (Zeitgeist 2025 is the on-record case).
5. The 10-phase `fix_ocr_artifacts` suite (rn→m, i→1, o→0, header stripping) **never runs
   on the HTML path** — scanned books get the least cleanup of any route.
6. Tier arbitration is **whole-document**: Tesseract-vs-pdfminer and Gemini-vs-pdfminer
   compare concatenated text. A book clean for 400 pages and garbage for 30 re-OCRs all or none.
7. **No per-page confidence** (`image_to_string` only, never `image_to_data`), **no image
   preprocessing** (no deskew/binarize/despeckle), **no layout-aware OCR** (bounding boxes
   and column detection are discarded on every OCR path).
8. Full-page scan rasters are dropped by the image extractor (>90% of page → skipped) with
   **no fallback**, so a page where OCR fails vanishes entirely from the ebook.
9. Detecting a scan can *cause* a hard failure: the Tesseract pre-check aborts the
   conversion if Tesseract is missing, while providing no OCR benefit.
10. Three independent scan detectors exist (`classify_source.py`, `detect_pdf_type`,
    `Invoke-TesseractKindleBatch.ps1` Phase 1) with different samples and thresholds.
    `Invoke-TesseractKindleBatch.ps1` is an unintegrated one-off.
11. **Zero integration tests** for any OCR escalation; the EB-349 tests assert against
    re-implemented copies of the gate condition, which is why the dead parameter was never caught.

### 2.3 Live local-LLM infrastructure (probed 2026-09-05)

| Endpoint | What it is | Text | Vision | Notes |
|---|---|---|---|---|
| `http://localhost:8000/v1` (alias `sb-chat`) | SB-227 gateway → llama.cpp b10679 CUDA, **`sb-flash` = Qwen3.8-Flash-Next** (125B-A6B MoE, ~84 GB, Q3_K_XL), n_ctx 32768 | 0.4–2.5 s, `json_schema` works, `enable_thinking:false` honored | **No** (no mmproj loaded → HTTP 500 on images) | Gateway backend can flip to vLLM 27B/35B when the coordinator parks Flash. Flash has an mmproj and can be relaunched with `-Vision`. |
| `http://192.168.1.33:8080/v1` (alias **`sb-vision`**) | llama.cpp Vulkan on DESKTOP-488UQB2 / R9700, **Qwen3VL-30B-A3B-Instruct Q4_K_M + mmproj** | 0.3 s | **Yes** (1.8 s on a tiny image) | **n_ctx 8192**, `--parallel 1` (single-slot, satisfies EB-361), `--image-min-tokens 1024`. ~12 GiB VRAM headroom. Reachable via LAN, Tailscale `100.102.46.97`, MagicDNS `desktop-488uqb2`. |
| `http://localhost:11434` (Ollama) | `qwen3.5:122b-a10b`, 87 GB, vision-capable | cold load >150 s | accepted image, empty output (needs `think:false`) | Contends with Flash for the same GPU. Not a standing option. |
| `http://localhost:8001/v1` | vLLM `sb-embed` (Qwen3-Embedding-8B) | embeddings only | — | — |

**Two live defects found by the probe:**

- **`.env` currently breaks local VQA.** `.env` sets `LOCAL_LLM_BASE_URL=http://localhost:8000/v1`
  and `LOCAL_LLM_VISION_MODEL=qwen3.5-35b-a3b-fp8`; that alias now resolves to `sb-flash`, which
  has no projector. Every VQA image request returns HTTP 500. The working values are
  `http://192.168.1.33:8080/v1` + model alias **`sb-vision`** (the config's `local_model` is the
  GGUF file name, not the served alias). This is EB-390's scope.
- **Context budget mismatch.** `GRADING_MAX_OUTPUT_TOKENS = 24576` assumes n_ctx 32768; sb-vision
  runs 8192. With ≥1024 image tokens per page, the default `batch_size: 8` overflows the window
  before any output. Either raise `-Ctx` in SecondBrain's `serve-qwen-vl.ps1` (KV cache for the
  30B-A3B at 32K is ~3 GiB, fits the headroom) or cap `batch_size ≤ 3`.

Installed tooling: Tesseract 5.4, Poppler 25.07, Calibre 9.9, PyMuPDF 1.27, pdfplumber,
pytesseract, openai SDK. **Not installed:** torch, opencv, ocrmypdf, marker, docling, surya,
easyocr, paddleocr.

### 2.4 Problem books — what actually fails

From `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md` and the EB-377 sweep:

| Class | n | VQA mean | Notes |
|---|---|---|---|
| digital | 10 | 82.1 | robust |
| two-column | 5 | 83.4 | robust |
| ocr | 2 | 70.5 | |
| **scan** | 14 | **57.4** (min 12) | every sub-50 outlier, all 5 partial-coverage books |

Open EB-377 follow-ups: EB-382 (VQA-low, 11 books), EB-383 (chapter detection zero, 8/50),
EB-384 (formatting lost, 7), EB-385 (footnotes unlinked, 6), EB-386/387/388/389/390.

**Neither `tests/expected_baselines.json` nor `tools/test_cases.json` contains a single scanned
book.** The failure class the project loses on has zero regression coverage.

## 3. Benchmark corpus (proposed `test-corpus/scan-bench/manifest.json`)

Sources confirmed on disk. Manifest references paths (no copies; two books exceed 80 MB).

### Track A — scanned / low-quality (the improvement target)

| # | Book | Location | Why |
|---|---|---|---|
| A1 | Monumental Christianity (Lundy, 1876) | `test-corpus/a2-pilot/` | VQA **12**, genuinely corrupt 1876 OCR text layer, render-verified true positive. The floor. |
| A2 | First Folio of Shakespeare (Norton Facsimile, Compressed) | `test-corpus/a2-pilot/` | 116 MB / 968 pp / 376 chars of text; JBIG2; 26-min timeouts; VQA 46. Image-only + large-file + timeout in one. |
| A3 | Jesus and the Victory of God (N.T. Wright) | `F:\Books\_Needs_Review\` | Zero extractable text from pypdf and pdfminer; JPEG2000. The pass/fail gate for "does an extraction *failure* auto-escalate to OCR". |
| A4 | Israelology (Fruchtenbaum) | `test-corpus/Fruchtenbaum.pdf` | Core regression book **and** live VQA 42; guards EB-367 header-bleed fix while measuring OCR gains. |
| A5 | Secret Societies of All Ages (Heckethorn, 1875) | `F:\Books\_Needs_Review\` | Only image-only PDF ever fully processed (Tesseract, ~70). Positive control. |
| A6 | Zeitgeist 2025 (Horn) | `F:\Books\07 Conspiracy...\Horn, Thomas R\` | Classifier says `ocr,gemini`; default path ignores it; visible `KKKKK` / `(cid:N)` artifacts. |
| A7 | The Hindu Pantheon (Moor) | `F:\Books\_Needs_Review\` | CCITTFax, zero text, non-Latin script. Stretch case; defines the "facsimile fallback" boundary. |

### Track B — general quality (must not regress; measures Phase 4)

| # | Book | Location | Why |
|---|---|---|---|
| B1 | The Oil Kings (Cooper) | `archive/` | Primary canary, 17 checks. Any movement = regression. |
| B2 | Python in Easy Steps (McGrath) | `archive/` | Structure benchmark with a binary metric: `<table>`/`<pre>` count > 0 (today 0). |
| B3 | Dionysius the Areopagite (Rolt) | `archive/` | Long running header + orphan page anchors + canonical VQA truncation case. |
| B4 | Arthur Versluis — Esoteric Origins | `F:\Books\01 History\...\Unknown\` | Worst live EB-377 failure (VQA 30, chapters 0, footnotes unlinked), render-verified. |
| B5 | Mexican Phoenix (Brading) | `F:\Books\_Needs_Review\` | VQA 91 with **0 chapters** — pure chapter-detection isolate. |
| B6 | Machine Learning for Asset Managers (López de Prado) | `F:\Books\09 Technology...\` | Real `(cid:N)` math corruption + known grader false-positive on legible code on the same page. Calibration case. |

Per-book metrics captured every run: VQA overall + per-page, chapter count vs source TOC
(`chapter_alignment.py`), word count, `score_text_layer_quality`, ligature splits, double
spaces, footnote linked/unlinked, page-marker survival, wall-clock per stage, cost (must be $0),
resolved provider URL + model.

## 4. Approaches considered

### 4.1 OCR strategy for scanned pages

| | A. VLM-native OCR (Qwen3-VL transcribes each page) | B. Classical OCR upgraded (Tesseract + preprocessing + per-page confidence) | C. Dedicated document-AI stack (marker / docling / surya on the Blackwell) |
|---|---|---|---|
| Quality on old/degraded scans | **Best** — language priors recover Victorian type, ligatures, broken glyphs | Weakest on 1876-class scans (~70 ceiling seen on Heckethorn) | Strong on layout/tables; degraded-scan quality varies by model |
| Throughput | Slowest: ~1 K image tokens + ~700 output tokens per page on the R9700 (Vulkan); needs measuring | Fastest: 1–3 s/page CPU | Fast on GPU, but torch + CUDA 12.8 (sm_120) install on the 96 GB box |
| Layout / headings | Semantic (`##` markers), no coordinates | Bounding boxes + confidence via `image_to_data`; columns recoverable | Native reading order, tables, equations |
| Integration cost | Low — `gemini_ocr.py` prompt contract + `vision_text_to_para_dicts` bridge already exist; swap transport | Medium — per-page loop, preprocessing (opencv), confidence gating | High — new venv, markdown bridge, EB-172 bake-off never run |
| New dependencies | none | `opencv-python` | torch, marker/docling |

**Recommendation: A + B as a per-page tiered engine, C as a timeboxed spike.**
Tesseract with preprocessing and per-page confidence handles the easy pages fast;
pages below a confidence/quality threshold escalate to `sb-vision`. This is the standard
hybrid, it reuses everything already built for Gemini, and it makes the VLM cost proportional
to how bad the scan is instead of to the page count. Option C stays as the EB-172 bake-off,
run once against A2/A7 to decide whether a document-AI model beats the hybrid on facsimiles.

### 4.2 VQA adjudicator once Claude is gone

The Claude fingerprint fallback exists because the local grader has two documented failure
modes (SCRUM-280): score inflation and missed issues. Options: (1) drop it and accept;
(2) a **second local model as adjudicator** — Flash relaunched with `-Vision` on the Blackwell
grades a deterministic blind-audit slice (the EB-343 design, with the adjudicator swapped);
(3) keep Claude opt-in only. **Recommendation: (3) immediately (default off), then a Phase 5
spike on (2).** One final, bounded Claude run over the 6-book baseline can calibrate the local
adjudicator, after which the key is never needed.

### 4.3 Text-LLM sites

One `TextLLMProvider` (OpenAI-compatible, mirrors `LocalVisionProvider`: `json_schema`,
`enable_thinking:false`, explicit timeout, `/v1/models` capability probe) behind a
`llm.text` config block (`provider: local|anthropic`, `base_url`, `model`). Target the
gateway (`localhost:8000`, alias `sb-chat`), not the loopback-only `:8082`. The PowerShell
`Get-ChapterStructure` gets a `Send-ToLocalLLM` sibling; its prompt is already externalized
in `agents/structure-analysis/system-prompt.md`, so only transport changes.

## 5. Target architecture

```
inbox PDF
  └─ classify_source (single detector; per-page text yield + image dominance)
       └─ --classifier-json → process_kindle_html          (EB-362 option a)
            ├─ per-page text-layer quality score
            ├─ page tier decision:  keep | tesseract | vlm | raster
            │     tesseract: opencv deskew/binarize → image_to_data (conf + bbox) → column order
            │     vlm:       render 200 DPI → sb-vision → markdown w/ headings → para dicts
            │     raster:    embed page PNG as <figure> (never drop a page)
            ├─ merge per page → OCR-artifact phases (2/2b/2c, 0/9) on OCR-sourced text
            ├─ book policy: median page quality < T → facsimile mode (k2pdfopt reflow / image ebook)
            └─ structure: Flash (sb-chat) chapter/heading arbitration over full-book candidates
  └─ Calibre → KFX
  └─ VQA: sb-vision tiered (light/standard/full), $0, fallback off; local adjudicator (Phase 5)
  └─ scan-bench harness: same 13 books, same metrics, every run
```

## 6. Phased plan

Each phase is one PR-sized unit with its own benchmark run. Nothing in Phase N+1 starts
until Phase N's benchmark shows no regression on Track B.

### Phase 0 — Ground truth (no pipeline logic changes)
- Fix the `.env`/config override so local VQA actually works: `LOCAL_LLM_BASE_URL=http://192.168.1.33:8080/v1`, `LOCAL_LLM_VISION_MODEL=sb-vision`; make `visual_qa.py` persist the resolved URL + model + `n_ctx` in every report. **(EB-390)**
- Resolve the 8192-ctx mismatch: request `-Ctx 32768` on `serve-qwen-vl.ps1` (SecondBrain change) or cap `batch_size`. Run `vqa_determinism_check.py --runs 2 --tolerance 0`. **(EB-364)**
- Build `tools/scan_bench.py` + `test-corpus/scan-bench/manifest.json` (13 books, §3). Run once on current master = baseline row 0. Store under `data/scan_bench/` (worktree + PR per EB-181).
- Spike (throwaway): measure `sb-vision` page-transcription seconds/page and quality on 5 pages each of A1, A2, A5. Decides Phase 3 batch sizing.

### Phase 1 — Zero-cloud default path
- `tools/llm_providers/text_provider.py` (`TextLLMProvider`) + `llm.text` config block.
- Route the four Python Anthropic sites and `Get-ChapterStructure` through it; `anthropic` stays as an opt-in provider value.
- `tools/local_vlm_ocr.py`: same page-batch/prompt/`<<PAGE:N>>` contract as `gemini_ocr.py`, transport = `sb-vision`. Gemini becomes opt-in.
- `visual_qa.fallback.enabled: false` by default. Delete the dead Tier 3 Claude Vision path or re-point it to the provider abstraction.
- **Acceptance:** full scan-bench run with `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` unset. Track B metrics ≥ baseline row 0 (Oil Kings 17/17). Cost $0.

### Phase 2 — Fix scanned-PDF routing
- One classifier; `--classifier-json` plumbed into `process_kindle_html`; delete the dead `classifier_verdict` default. **(EB-362, option a)**
- `--ocr` honored on the HTML path; converge-loop `'ocr'` strategy targets the HTML path.
- Zero-text / low-yield auto-escalation based on per-page text yield, not debris density.
- OCR-artifact phases applied on the HTML path for OCR-sourced text.
- Tesseract/Poppler paths always passed; remove the Tesseract pre-check hard fail.
- Integration tests that call `process_kindle_html` on small synthetic scanned PDFs (render text → PNG → PDF), covering each escalation gate.
- **Acceptance:** A3 and A6 auto-route to OCR with no flags; A3 chapter count > 0; existing 41 pipeline tests green.

### Phase 3 — Page-level OCR quality engine
- Per-page tiering (keep / tesseract / vlm / raster) with `image_to_data` confidence + `score_text_layer_quality` per page; opencv deskew + adaptive binarize before Tesseract.
- Column order on the OCR path from Tesseract block boxes; VLM markdown headings via the existing bridge.
- Page raster fallback (`<figure>`), never drop a page.
- Book-level facsimile mode: k2pdfopt-reflowed PDF (or image ebook) when median page quality stays below threshold after all tiers.
- Optional EB-172 bake-off: marker or docling on A2/A7 vs the hybrid.
- **Acceptance:** A1 VQA 12 → ≥ 60; A4 42 → ≥ 70; A5 ≥ 70 held; A2 and A7 produce a readable facsimile output with a recorded reason; no Track B regression.

### Phase 4 — Local-LLM structure upgrades (EB-383 / 384 / 385 cluster)
- `Get-ChapterStructure` on Flash with full-book heading candidates (32 K ctx) instead of three text zones; arbitrate font-based + pattern + bookmark candidates.
- Flash-scored formatting preservation (lists/tables/`<pre>`) and footnote-marker linking on the sampled pages.
- **Acceptance:** B5, B4, A3 chapter counts match source TOC via `chapter_alignment.py`; B2 emits `<table>`/`<pre>` > 0.

### Phase 5 — VQA at scale, local-only (EB-340 / 342 / 343 / 150, adapted)
- Auto-enable VQA in the batch; tiered policy from `docs/superpowers/specs/2026-05-29-tiered-vqa-design.md`.
- Spike: Flash `-Vision` as blind-audit adjudicator vs one final Claude calibration run on the 6-book baseline.
- **Acceptance:** overnight batch runs VQA on every book at $0; adjudicator disagreement rate recorded.

## 7. Tool recommendations

| Tool | Verdict | Why |
|---|---|---|
| Raise `sb-vision` n_ctx to 32768 (SecondBrain `serve-qwen-vl.ps1`) | **Do first** | Unblocks batch VQA and multi-page VLM OCR; ~3 GiB KV cache fits the R9700 headroom. |
| `opencv-python` | **Add** (Phase 3, `requirements.txt`) | Deskew, adaptive threshold, despeckle before Tesseract. Small, no GPU. |
| `pytesseract.image_to_data` (already installed) | **Use** | Per-word confidence + bounding boxes; no new install. |
| k2pdfopt | **Add** (Phase 3, external binary) | Reflows scanned page images to Kindle-sized pages without OCR. The correct output for facsimiles like the First Folio. |
| Flash relaunch with `-Vision` on the Blackwell | **Spike** (Phase 0/5) | CUDA-speed VLM with 32 K ctx; candidate for fast OCR tier and for the local VQA adjudicator. Contends with Flash text use. |
| marker-pdf / docling (torch, CUDA 12.8+) | **Bake-off only** (EB-172) | Only if the hybrid fails on facsimile-class books. Isolated venv, not `requirements.txt`. |
| ocrmypdf | **Skip** | Windows build lacks unpaper/`--clean`; opencv + pytesseract covers it. |
| easyocr / paddleocr | **Skip** | No advantage over Tesseract + VLM for English book pages. |
| Ollama `qwen3.5:122b` | **Skip** | 87 GB, contends with Flash; not a standing service. |

## 8. Risks

- **Grader trust.** VQA scores on code-heavy books are suspect (EB-353); scan-track deltas must be spot-checked on rendered PNGs, per the Calibration Sessions rule. The determinism double-run gates every benchmark.
- **Throughput.** VLM OCR on the R9700 may be minutes per hundred pages; the per-page tiering keeps it bounded, and the Phase 0 spike sizes it before commitment.
- **Gateway drift.** `localhost:8000` can silently flip backends; the provider must probe `/v1/models` and record the resolved model in every report.
- **Cross-project change.** The ctx increase lives in SecondBrain's `sb-qwen-service`. NEW DEPENDENCY: EbookAutomation → SecondBrain: VQA and VLM OCR require `sb-vision` served with n_ctx ≥ 32768.
- **Refactor tension.** `docs/plans/2026-04-11-001-feat-booksmith-extraction-plan.md` proposes stripping the OCR/vision flags out of `process_kindle_html`; this plan fixes them in place. Decide which wins before Phase 2.

## 9. Decisions (resolved 2026-09-05)

1. **Ticket.** New epic EB-391 with one child task per phase (EB-392 through EB-397), phase N+1 `is blocked by` phase N; epic relates to EB-3. Existing tickets linked rather than duplicated: EB-390/364/361 (P0), EB-339 (P1), EB-362/349 (P2), EB-172/382/368 (P3), EB-383/384/385 (P4), EB-340/342/343/150 (P5).
2. **Adjudicator policy:** Claude fingerprint fallback default-off from Phase 1; local Flash-Vision blind-audit adjudicator spiked in Phase 5 after one final bounded Claude calibration run.
3. **ctx fix:** SecondBrain-side `-Ctx 32768` on `serve-qwen-vl.ps1` (SB-231). Until it lands, `LocalVisionProvider` probes `/v1/models` for `n_ctx` and caps batch size defensively instead of overflowing.
4. **Facsimile output:** k2pdfopt-reflowed PDF first (the Scribe reads it natively); image-based KFX only if that proves unacceptable.
5. **Booksmith refactor:** deferred. All phases fix the OCR wiring in place inside `process_kindle_html`; the extraction-module split waits until every local update has landed.
