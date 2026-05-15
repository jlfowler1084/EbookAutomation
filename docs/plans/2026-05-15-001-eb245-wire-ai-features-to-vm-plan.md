---
ticket: EB-245
title: Wire Gemini OCR + visual QA into production conversion path on Hetzner VM
created: 2026-05-15
author: Joe Fowler (planning session, Opus 4.7)
status: approved 2026-05-15
model_for_execution: sonnet
related: EB-210, EB-243, EB-237
---

## Approved decisions (locked 2026-05-15)

1. **Phase 0:** Merge EB-210 first, then start EB-245 from a clean master.
2. **Cost caps:** Default `premium_gemini_cost_limit_usd = 1.00`, `premium_vision_cost_limit_usd = 0.50`.
3. **VQA default state:** `premium_vqa_enabled = False` for the first production rollout. Enabled via env var flip once Gemini-only economics are observed.
4. **Test corpus:** Source scanned PDF from archive.org public domain. Document the URL in the Phase 6 test report.

# Plan — EB-245: Wire AI features into the premium conversion path on Hetzner VM

## 1. Goal

Make the input-side AI features (`--use-gemini`, `--use-vision`) and the output-side visual-QA pass available on premium conversions in production at leafbind.io, with bounded cost, premium-tier gating, and observable cost telemetry. Free tier stays deterministic (raw Calibre baseline).

## 2. Scope clarification — two AI features, not one

EB-245's description treats `--use-gemini` / `--use-vision` and "visual QA pass" as a single feature. They are actually two distinct things:

| Feature | Tool | When it runs | What it does |
|---|---|---|---|
| **Input-side AI extraction** | `tools/pdf_to_balabolka.py` flags `--use-gemini` / `--use-vision` | During extraction, before Calibre | Replaces pdfminer/pypdf with Gemini Flash (Tier 2.5) or Claude Vision (Tier 3) for the *transcription* step. Mutually exclusive — vision wins if both are set. |
| **Output-side visual QA** | `tools/visual_qa.py` | After Calibre conversion completes | Renders the output KFX to PNG via Calibre→PDF→Poppler, sends sampled pages to an OpenRouter VLM (default: Qwen3-VL-30B-A3B), emits a JSON QA report with pass/fail score. |

Both belong in premium. Free tier gets neither.

## 3. Current state — inventory done 2026-05-15

### 3.1 Local code state (master)

- `web_service/pipeline_runner.py` `run_premium()` lines 198-205: CLI invocation passes **no** AI flags.
- `web_service/config.py` `Settings` dataclass: no AI-key fields. Stripe + TOKEN_HMAC + Origins only.
- `tools/pdf_to_balabolka.py` lines 14196-14214: AI argparse flags exist — `--use-gemini`, `--gemini-cost-limit` (default 5.0), `--gemini-model`, `--use-vision`, `--vision-cost-limit` (default 15.0). Graceful degrade is already wired at lines 12719-12772 — vision/gemini failures fall through to standard extraction.
- `tools/visual_qa.py` line 1241+: standalone CLI with `--provider {cloud|claude|local}`, `--cloud-host openrouter`, reads `<HOST>_API_KEY` (e.g. `OPENROUTER_API_KEY`) for cloud and `ANTHROPIC_API_KEY` for claude. Defaults from `config/settings.json` `visual_qa` block: `provider: cloud`, `cloud_model: qwen/qwen3-vl-30b-a3b-instruct`.
- `tools/gemini_ocr.py` line 69: reads `GEMINI_API_KEY` from environment.

### 3.2 EB-210 branch state

- Local master is **behind** `feat/eb-210-vm-portability` by 1 commit (`5dab019`).
- That commit ships: `shutil.which("ebook-convert")` Linux fallback, local-provider hard-fail on Linux, `.env.template`, `scripts/vm-bringup.sh`, `docs/operations/vm-pipeline-runbook.md`.
- The VM is checked out on this feature branch, not master.

### 3.3 VM state (claude-dev-01, inventoried via SSH 2026-05-15)

System layer — **all green:**
- Ubuntu 24.04.4 LTS, Python 3.12.3, venv at `~/EbookAutomation/.venv`
- Calibre 7.6.0, tesseract 5.3.4, ocrmypdf 15.2.0, pdftoppm, gs 10.02.1, pwsh 7.6.1
- `~/ebook-data/{inbox,processing,archive,output}` present, `~/EbookAutomation/logs` present

Python packages — **all needed deps present:**
- `google-genai 1.68.0`, `anthropic 0.102.0`, `openai 1.109.1` (used by `CloudVLProvider` for OpenRouter)
- `pdf2image 1.17.0`, `pdfplumber 0.11.9`, `pillow 12.1.1`, `PyMuPDF 1.27.2.2`, `pypdf 6.9.2`, `pytesseract 0.3.13`
- `fastapi 0.136.1`, `uvicorn 0.47.0`, `python-dotenv 1.2.2`, `httpx 0.28.1`, `requests 2.33.0`

Service — **active and enabled:**
- Unit: `ebookweb.service`, status active+enabled
- `EnvironmentFile=/etc/web_service.env`
- Keys present in `/etc/web_service.env`: 6 Stripe keys + `TOKEN_HMAC_SECRET` + `WEB_SERVICE_ALLOWED_ORIGINS`

## 4. Gap analysis

| # | Gap | Severity | Owner |
|---|---|---|---|
| G1 | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` not in `/etc/web_service.env` | blocking | user provides values, agent writes file |
| G2 | `.env.template` documents `GOOGLE_API_KEY` but `gemini_ocr.py` reads `GEMINI_API_KEY` | small bug | agent |
| G3 | `run_premium()` does not pass `--use-gemini` / `--use-vision` / cost-cap flags to the subprocess | blocking | agent |
| G4 | No post-conversion visual-QA step in `run_premium()` — `visual_qa.py` exists as standalone CLI but is never invoked from the web service | blocking | agent |
| G5 | No AI-cost field in the job result / sidecar JSON | blocking (AC) | agent |
| G6 | `feat/eb-210-vm-portability` (1 commit ahead of master) is the active branch on the VM but never merged | hygiene, not blocking | needs decision |
| G7 | No integration tests for the new AI path on the VM | blocking (AC) | agent + user (test PDFs) |

### Already satisfied — no work needed

- All system packages on the VM
- All Python deps on the VM
- Graceful degrade on AI failure (already in `pdf_to_balabolka.py`)
- Tiered subprocess timeout policy (EB-237 already shipped — 120/300/600s by file size)
- Cost cap on Gemini (`--gemini-cost-limit` default $5) and Vision (`--vision-cost-limit` default $15)

## 5. Phased implementation

### Phase 0 — branch hygiene decision (BEFORE any code work)

Decide how to handle the unmerged `feat/eb-210-vm-portability` branch. Two options:

- **Option A — merge EB-210 to master first, then start EB-245.** Cleaner history. Recommended. Requires a quick PR + merge for EB-210 (the work is already done and the VM already runs it; this is just paperwork). Status of EB-210 transitions to Done as a side effect.
- **Option B — branch EB-245 worktree from `feat/eb-210-vm-portability`, ship both together.** Stacked branches; merge ordering matters. Avoids the EB-210 paperwork but couples the two tickets at merge time.

Pause point: ask user which option before proceeding.

### Phase 1 — VM env vars (G1)

User-action step. Cannot be automated because secrets must come from the user.

1. User pastes 3 key values into `/etc/web_service.env` on `claude-dev-01` (via the `! ssh claude-dev-01 'nano ...'` pattern, or by directly editing).
2. Agent verifies the keys appear (names only, never values) via `grep -oE '^[A-Z_]+=' /etc/web_service.env`.
3. Agent runs `systemctl restart ebookweb.service` and confirms `systemctl is-active` returns `active`.

Acceptance: `systemctl show ebookweb.service -p EnvironmentFiles` confirms the file is loaded; service is active; restart did not regress paid conversions in the request log.

### Phase 2 — fix `.env.template` (G2)

One-line edit. Change `GOOGLE_API_KEY=` to `GEMINI_API_KEY=` to match the code. Doc-only change. Lives on whichever branch Phase 0 chose.

Acceptance: `grep -E '^(OPENROUTER|ANTHROPIC|GEMINI)_API_KEY=' .env.template` returns 3 lines.

### Phase 3 — wire input-side AI flags into `run_premium()` (G3)

Worktree branch `feat/eb-245-premium-ai-wiring` off master.

**Flag correction (2026-05-15, mid-execution).** Initial plan said `--use-gemini`. Re-reading `pdf_to_balabolka.py` revealed two distinct Gemini flags:

| Flag | Behavior | Cost shape |
|---|---|---|
| `--use-gemini` | Always-on Tier 2.5 transcription on the entire book | $0.30-$0.50 per book × every premium conversion |
| `--gemini-remediate` | Selective fallback — only re-extracts pages flagged by `score_text_layer_quality(multi_sample=True)` problem-region analysis | $0 for clean PDFs, ~$0.02-$0.06 when scanned/garbled pages are detected |

`--gemini-remediate` matches the original EB-245 intent ("Gemini OCR fallback when text yield is below threshold"). User-approved correction logged 2026-05-15 — wire `--gemini-remediate`, not `--use-gemini`.

Edit `web_service/pipeline_runner.py` `run_premium()`:

```python
cmd = [
    str(cfg.python_path),
    str(cfg.pipeline_script),
    "--cli",
    "--input", str(input_path),
    "--output-dir", str(temp_dir),
    "--output-format", output_format,
    "--gemini-remediate",
    "--gemini-cost-limit", str(cfg.premium_gemini_cost_limit_usd),
]
```

`--use-vision` (full Claude Vision transcription) deferred to a follow-up ticket. It's mutually exclusive with the Gemini path in `pdf_to_balabolka.py` and ~5× the cost. Output-side VQA (Phase 4) covers the vision QA story without invoking input-side Claude Vision.

Add to `web_service/config.py` `Settings`:

```python
premium_gemini_cost_limit_usd: float = 1.0  # generous; typical use is $0.02-$0.06
```

VQA-related Settings fields (`premium_vqa_enabled`, `premium_vqa_cost_limit_usd`) land in Phase 4 to keep each commit focused on its single responsibility.

Acceptance: a premium conversion of a 50-page text PDF logs `--gemini-remediate` in the cmd line; clean PDFs show `gemini_cost == 0` because no pages are flagged.

### Phase 4 — post-conversion visual-QA step (G4)

After `run_premium()` succeeds, run `visual_qa.py` against the output KFX as a second subprocess. Reuse the existing `--provider cloud --cloud-host openrouter` defaults (already in `config/settings.json` `visual_qa` block, default cloud model `qwen/qwen3-vl-30b-a3b-instruct`).

Approach:

1. Refactor `run_premium()` to return both `RunResult` and an optional `VqaReport` field.
2. Add a `_run_vqa(output_path, cfg) -> VqaReport | None` helper that invokes `python tools/visual_qa.py --input <kfx> --provider cloud --output-format json` and parses the result.
3. Skip silently (log only) if `cfg.premium_vqa_enabled is False` or `OPENROUTER_API_KEY` is missing — graceful degrade.
4. Cap VQA wall-clock at 60s; on timeout, log and return None (the conversion is already done — VQA is best-effort).

Acceptance: a premium conversion produces a VQA score in the job sidecar.

### Phase 5 — cost telemetry / sidecar (G5)

Extend the job-result schema with:

```python
@dataclass(frozen=True)
class RunResult:
    success: bool
    output_path: str = ""
    output_size: int = 0
    error_message: str = ""
    # New in EB-245:
    gemini_cost_usd: float = 0.0
    vision_cost_usd: float = 0.0
    vqa_score: int | None = None
    vqa_pass: bool | None = None
```

Surface these in the job-status API response and in the per-job sidecar JSON. Add log lines `INFO ai_cost_summary job=<id> gemini=$X vision=$Y vqa_score=Z` so cost can be tailed.

Acceptance: per-job sidecar contains the 4 new fields; cost lines are tailable in the systemd journal.

### Phase 6 — integration tests on the VM (G7)

Run 4 real PDFs through premium on the VM with the new code deployed:

1. **Text-based small PDF** (~10 pages, ~2 MB) — confirm Gemini *does not* run (text yield is high; gemini fallback only fires on low text yield). Expected: `gemini_cost_usd == 0`, VQA score present.
2. **Scanned PDF** (image pages, no extractable text — source: archive.org public-domain scan) — confirm Gemini OCR runs. Expected: `gemini_cost_usd > 0`, transcription quality acceptable.
3. **Oversized cost simulation** — deliberately set `--gemini-cost-limit 0.01` via a dev override and confirm the abort path triggers, the deterministic pipeline still produces an EPUB. Expected: graceful degrade, success=True.
4. **AI provider 5xx simulation** — temporarily unset `GEMINI_API_KEY` on a dev VM run (or use a fake key); confirm conversion still succeeds with `gemini_cost_usd == 0`. Expected: graceful degrade.

All 4 results documented as a comment on EB-245.

### Phase 7 — close

1. PR, review, merge to master.
2. Deploy to VM (pull + restart service).
3. Run Phase 6 tests against production.
4. Post results to EB-245 and transition to Done.
5. EB-243 (marketing) gets unblocked from making the AI quality-pass claim. A round-2 marketing ticket lands the new copy.

## 6. Out of scope (deferred)

- Free-tier policy redesign (free still gets raw Calibre — flagged in ticket as a follow-up).
- `--use-vision` (full Claude Vision transcription) — defer to a follow-up once Gemini economics are observed.
- Fine-tuned cost optimization — get the cap working; tune later.
- New AI providers beyond Gemini + cloud VLM (existing stack only).

## 7. Open questions for the user

1. **Phase 0:** Merge EB-210 first (Option A, recommended) or stack EB-245 on the feature branch (Option B)?
2. **Phase 3 cost cap:** Is $1.00 Gemini + $0.50 VQA per premium conversion acceptable? (Premium pack price = $0.80/conversion. $1.50 ceiling allows occasional cost spike without margin disaster, but a runaway scanned book of 800+ pages could hit $1.00 cap and still bleed.) Lower defaults if too aggressive.
3. **Phase 4 VQA enablement default:** Is `premium_vqa_enabled = True` the right default, or should the first production rollout default to False and require an env-var flip?
4. **Phase 6 scanned PDF source:** Do you have a scanned-book PDF I can use for the test, or should I source one from archive.org public domain?

## 8. Estimated effort

- Phase 0: 15 minutes (user decision + branch ops)
- Phase 1: 10 minutes (user pastes keys + agent verifies)
- Phase 2: 5 minutes (1-line edit + PR)
- Phase 3: 1 hour (config plumbing + run_premium edit + unit tests)
- Phase 4: 1.5 hours (VQA helper + RunResult refactor + skip-path tests)
- Phase 5: 30 minutes (sidecar schema + log lines)
- Phase 6: 1 hour (run 4 integration scenarios on the VM)
- Phase 7: 30 minutes (PR + deploy + ticket close)

Total: roughly half a day of focused work after Phase 0 resolves.
