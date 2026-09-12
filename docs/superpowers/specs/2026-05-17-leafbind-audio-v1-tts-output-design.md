# leafbind audio v1 — TTS output via desktop-GPU worker

**Date:** 2026-05-17
**Status:** Approved; tickets filed
**Epic:** EB-310
**Related:** SCRUM-325 (Kokoro replaces Balabolka — Done), EB-305 (output-format demand research — To Do)

**Filed tickets:**
- EB-310 — Epic
- EB-311 — Listening QA (soft gate)
- EB-312 — Desktop Kokoro worker
- EB-313 — VM audio job dispatch
- EB-314 — Frontend FormatSelector + BETA tag
- EB-315 — Async delivery UX
- EB-316 — Pricing page + premium-tier copy
- EB-317 — Rename pdf_to_balabolka.py
- EB-318 — VM TTS readiness doc
- EB-319 — v2 migration spike

---

## Goal

Add chaptered audiobook output to leafbind.io's premium tier. Users select "audio" alongside epub/mobi/kfx, the conversion produces both M4B (with chapter markers) and MP3 (with ID3 chapter frames), and the user picks which to download. Launch behind a BETA banner pending full-corpus listening QA.

## Why this batch, why now

- The Kokoro neural TTS pipeline (SCRUM-325, Done) is already in master and produces high-quality, chapter-aware audio on desktop. The TTS output capability exists but is not exposed anywhere except the local Windows pipeline.
- leafbind's structural advantage (chapter detection, footnote linking, OCR remediation) means a converted audiobook preserves navigation that raw-text TTS tools cannot. This is the differentiator — voice quality only needs to be "good enough."
- Audio is the next obvious format to add to drive top-of-funnel traffic. The other formats (epub/mobi/kfx) are commoditized; chaptered audiobook from arbitrary PDFs is not.

## Decisions (locked in 2026-05-17)

| Decision | Choice | Why |
|---|---|---|
| Compute location | **Desktop GPU + Tailscale** | Zero incremental cost at zero traffic. PC is always on. Cloud GPU is the v2 migration when volume justifies it. |
| QA gate | **Soft: 2-book sample, BETA banner** | Oil Kings (endnotes) + Mexico Illicit (OCR debris). Ship behind BETA if acceptable; full-corpus QA continues in parallel. |
| Pricing/tier | **Premium-only, joins KFX** | No new SKU, no Stripe work. Audio is one more `PREMIUM_FORMATS` entry. Defers cost-per-book question to v2. |
| Output format | **Both M4B and MP3, user picks at download** | Single synthesis pass, dual mux via ffmpeg. M4B for audiobook apps, MP3 for universal compatibility. |
| TTS engine | **Kokoro (existing)** | Already shipped via SCRUM-325. Default voice `af_heart`. Voice picker deferred to a future ticket. |

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  leafbind.io (Cloudflare → Hetzner VM)                              │
│                                                                      │
│  POST /convert  ──→  pipeline_runner.py                              │
│                       │                                              │
│                       ├─ format ∈ {epub,mobi,kfx} → existing path    │
│                       │                                              │
│                       └─ format == audio → enqueue audio job         │
│                                              ↓                       │
│                                         job_queue (new "audio")      │
└─────────────────────────────────────────────┼──────────────────────┘
                                              │ Tailscale
                                              ↓
┌────────────────────────────────────────────────────────────────────┐
│  Desktop PC (Windows, Tailscale node)                               │
│                                                                      │
│  kokoro_worker.py (long-running)                                     │
│    poll ← VM /worker/claim    (HMAC over shared secret)              │
│    fetch text + job metadata                                         │
│    run tools/kokoro_synth.py → per-chapter WAVs                      │
│    ffmpeg → MyBook.m4b  (chapter markers + cover art if available)  │
│    ffmpeg → MyBook.mp3  (ID3v2 chapter frames)                       │
│    POST artifacts → VM /worker/result                                │
└─────────────────────────────────────────────┼──────────────────────┘
                                              │ Tailscale
                                              ↓
                                    VM stores artifacts
                                    sends "audio ready" email
                                    status page → download (M4B/MP3)
```

### Worker abstraction
The worker must be **runtime-location agnostic**. Same job protocol whether it runs on the desktop or in a cloud GPU container. Anything that hardcodes the desktop (paths, hostnames, env-var names) is technical debt blocking v2.

### Stale-job handling
If no worker claims a job for >4 hours, the VM emails the user that conversion is delayed and offers a refund/retry path. This is the failure mode for "desktop offline."

## Tickets in this batch

All filed under project EB. Epic and child keys below are the actual filed tickets.

### EB-310 — Epic: TTS audio output on leafbind (v1: desktop worker)
Umbrella epic. Links to all child tickets. Acceptance: premium users can request "audio" output on leafbind.io, receive a chaptered M4B + MP3, behind a BETA banner.

### EB-311 — Listening QA: Oil Kings + Mexico Illicit Kokoro sample (soft gate)
Synthesize first 5–10 minutes of each book on the desktop using current Kokoro pipeline. Listen and score. Output: written signoff or a triaged bug list. Unblocks EB-314, EB-315.

### EB-312 — Desktop Kokoro worker: Tailscale-attached job runner
New `worker/` directory or similar. Long-running Python service: polls VM, claims one job at a time, runs `kokoro_synth.py`, mux M4B + MP3 with ffmpeg, uploads results, marks job complete. Auth via HMAC-signed requests with shared secret over Tailscale. Idempotent on restart. Failure modes: synthesis crash, ffmpeg failure, upload retry. Runs as Windows scheduled task or service.

### EB-313 — VM audio job dispatch + pipeline_runner branch
Touches `web_service/routes/convert.py`, `pipeline_runner.py`, `job_queue.py`, `job_store.py`. New job type `audio`. When `output_format=audio`, extract text (step 1, unchanged), enqueue audio job, return job ID. New endpoints `/worker/claim`, `/worker/result`, `/worker/heartbeat`. Stale-worker timeout: 4 hours. Schema migration for new job columns if needed.

### EB-314 — Frontend: add 'audio' to premium FormatSelector + BETA tag
Touches `web_service/frontend/components/FormatSelector.tsx` and any tier-aware copy. Add `audio` to `PREMIUM_FORMATS`. BETA badge on the option. Description: "Chaptered audiobook (M4B + MP3) — ~30–90 min to render." Blocked by EB-311 and EB-313.

### EB-315 — Async delivery UX: status page progress + email on completion
Touches `web_service/frontend/app/(app)/status/[id]/page.tsx`, recovery/notification machinery. Status page shows "X of Y chapters synthesized" while job runs. Completion email with download link. "Delayed" email if no worker claim in 4 hours. Download page exposes M4B/MP3 choice. Blocked by EB-311, EB-313, EB-314.

### EB-316 — Pricing page + premium-tier copy update
Touches `web_service/frontend/app/(marketing)/pricing/page.tsx` and any structured-data pages. Add "Chaptered audiobook (M4B + MP3)" to Premium feature list. Update JSON-LD product schema. Can ship as "coming soon" before audio is live.

### EB-317 — Rename `pdf_to_balabolka.py` → `extract_tts_text.py` (+ module refs)
Big-touch rename. The tool no longer targets Balabolka. New name reflects function. Update PowerShell module imports (`Convert-ToTTS`, `Invoke-KokoroTTS`, `Invoke-Balabolka` wrappers), CLAUDE.md references, `scripts/vm-bringup.sh`, `docs/operations/vm-pipeline-runbook.md`, every README, every `docs/plans/*.md` reference. Verify regression suite still passes after rename.

### EB-318 — VM TTS readiness doc + bringup script cleanup
Small doc update. `docs/operations/vm-pipeline-runbook.md`: clarify VM produces no audio; desktop worker is the canonical audio path. `scripts/vm-bringup.sh`: ensure no stale Balabolka/TTS install lines. ~30-minute task.

### EB-319 — v2 migration spike: containerize worker for cloud GPU (Modal/RunPod)
Spike, not v1 launch blocker. Build a Dockerfile for the worker, run one job on Modal or RunPod with CUDA + Kokoro ONNX, confirm latency and cost. Document migration trigger thresholds (e.g., daily audio jobs > N, or stale-worker incidents > M/month). Output: docs/plans entry capturing the v2 switchover procedure.

## Dependency graph

```
EB-311 (QA) ────────────────┐
                            ↓
EB-312 (worker) → EB-313 (VM dispatch) → EB-314 (UI) → EB-315 (UX) → BETA launch
                                                   ↑
                                            EB-316 (pricing copy) — parallel anywhere
EB-317 (rename), EB-318 (VM doc), EB-319 (v2 spike) — independent, anywhere
```

## Risks and open questions

- **Desktop uptime.** PC always-on assumption is durable, but mass power outage / Windows update reboot will delay queue. Mitigation: stale-worker email at 4h is the customer-visible SLA.
- **Cover art source.** M4B supports embedded cover art; current pipeline doesn't extract PDF cover thumbnails. v1 ships without cover art; defer to a follow-up if customer feedback wants it.
- **Voice selection.** v1 hardcodes Kokoro's `af_heart`. A voice picker is deferred. If customers ask for male narrator, file as enhancement.
- **Storage growth.** Each audio job produces ~50–300 MB across M4B + MP3. Need a cleanup policy: delete artifacts N days after delivery (matches existing token TTL of 30 days from EB-301).
- **Email infrastructure.** Async delivery requires a working transactional email path. Confirm during EB-5 that the recovery-email machinery (EB-264/-265 work) can be reused for completion notifications.
- **Worker auth.** HMAC over shared secret is fine inside Tailscale. If v2 moves the worker to cloud GPU outside the Tailnet, auth needs reconsidering (probably mTLS or signed JWTs).
- **Listening QA outcome may regress scope.** If Oil Kings + Mexico Illicit don't sound acceptable, EB-4/EB-5/EB-6 stay paused and a remediation ticket is filed instead. The soft-gate explicitly admits this possibility.

## Out of scope for v1

- Voice picker / multiple voice options at conversion time
- Voice cloning or character-aware fiction TTS (SCRUM-198 territory)
- Cover art extraction and embedding
- Streaming/in-browser playback (download-only for v1)
- Free-tier audio preview
- Cloud GPU production (v2 — EB-9 spike sets it up but doesn't ship it)
- Multilingual TTS (Kokoro is English-only for v1 use)
- Pre-existing audiobook re-conversion / improvement passes
