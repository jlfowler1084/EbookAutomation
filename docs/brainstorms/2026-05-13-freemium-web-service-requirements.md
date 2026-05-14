---
date: 2026-05-13
topic: freemium-ebook-conversion-web-service
status: draft
---

# Freemium Ebook Conversion Web Service

## Problem Frame

The EbookAutomation pipeline produces significantly better Kindle conversions than raw
Calibre — handling multi-column layouts, font-based heading detection, footnote linking,
and OCR cleanup. With the Hetzner VM (claude-dev-01) now bootstrapped and the pipeline
deployed, the marginal cost of exposing this as a web service is small.

The goal is a freemium web service where organic search traffic finds "PDF to Kindle"
or "convert PDF to KFX" queries, experiences the quality difference between a basic
Calibre pass-through (free) and the smart pipeline (premium), and converts to a
pay-per-use credit purchase.

### Relationship to BookSmith (OSS)

A previous brainstorm (`docs/brainstorms/2026-04-10-kindlecraft-open-source-launch-requirements.md`)
explored the same pipeline as an open-source CLI (BookSmith) and explicitly deferred
a hosted web service. The Hetzner VM bootstrapped in EB-221/EB-222 changes the
infrastructure equation. These two products are complementary, not competing:

- **BookSmith OSS** (separate project, deferred): CLI tool for technical users who run locally
- **This web service**: Hosted version for non-technical users; BookSmith OSS can later
  serve as the clean extraction engine underneath it

The web service does NOT wait for BookSmith to ship. It wraps the existing pipeline directly.

### Market Risk Note

The PDF-to-Kindle converter market is crowded (Zamzar, CloudConvert, PDF2Kindle.com). The
differentiation hypothesis is:

1. **Quality layer**: Smart heading detection, footnote linking, and KFX output — none of
   the commodity converters do this
2. **KFX output specifically**: "Convert PDF to KFX" has almost no search competition;
   most converters produce EPUB or MOBI
3. **Privacy**: No account required, files deleted immediately — competitors store files
4. **Scale**: A profitable side project needs hundreds of premium customers, not millions

This is a testable hypothesis. The requirements include an SEO-first approach that builds
organic authority before heavy infrastructure investment.

---

## Core Use Cases

**Primary:** PDF → Kindle (KFX) — academic papers, books, and documents readers want on
their Kindle device with proper structure (headings, TOC, footnotes intact)

**Secondary:** General ebook format conversion — EPUB, MOBI, AZW/AZW3 → other formats
for device compatibility

**Explicitly out of scope (v1):** TTS / audiobook output, MP3 generation, batch processing,
user accounts, direct Kindle email delivery

---

## Requirements

### R1 — Free Tier: Basic Conversion

Free users receive a raw Calibre pass-through conversion with no structure enhancement.
No account or email required. Files accepted up to 20MB.

- R1a. Input formats accepted: PDF, EPUB, MOBI, AZW, AZW3
- R1b. Output formats offered: EPUB, MOBI
- R1c. No heading detection, footnote linking, OCR cleanup, or KFX output
- R1d. Result download link valid for 1 hour; file deleted after download or expiry
- R1e. Rate limit: 3 free conversions per IP per 24 hours (enforced by Cloudflare +
  backend)

### R2 — Premium Tier: Smart Conversion

Premium users receive the full EbookAutomation pipeline including the quality layer.
Unlocked by purchasing a credit pack via Stripe.

- R2a. All free tier input formats plus DJVU and TXT
- R2b. Output formats: EPUB, MOBI, KFX (Kindle-native format)
- R2c. Smart extraction: font-based heading detection, multi-column layout handling,
  9-phase OCR artifact cleanup, footnote/endnote linking, pre-flight PDF analysis
- R2d. File size limit: 100MB
- R2e. Result download link valid for 24 hours; file deleted after download or expiry
- R2f. One credit consumed per conversion regardless of file size or output format

### R3 — Credit Purchase (Stateless / No Accounts)

No user accounts are required at any tier. Credit purchases use signed tokens.

- R3a. Stripe Checkout session issues a signed conversion token (JWT or HMAC-signed
  opaque token) on successful payment
- R3b. Token is single-use, bound to the conversion type, and expires in 7 days
- R3c. Credit pack sizes offered at launch: 5 credits ($X), 20 credits ($Y)
  (exact pricing determined during planning based on infrastructure cost)
- R3d. Tokens are validated server-side; no database of user accounts is maintained
- R3e. A token database entry (token hash → used/unused + expiry) is required on
  the backend to prevent double-spend — this is not a user account, it is a
  tamper-resistance mechanism

### R4 — Job Queue and Status

Conversions are asynchronous. The UI polls for status.

- R4a. File upload returns a job ID immediately
- R4b. Client polls `/status/<job-id>` at 5-second intervals
- R4c. Job states: `queued`, `running`, `done`, `failed`
- R4d. Failed jobs return a human-readable error message
- R4e. Concurrent job limit: 3 simultaneous conversions on the VM (enforced by the queue)
- R4f. Conversion timeout: 120 seconds per job; jobs exceeding this are failed and
  cleaned up

### R5 — File Handling and Privacy

No user files persist beyond the conversion lifecycle.

- R5a. Uploaded files are written to an isolated temp directory per job
- R5b. Output files are stored in a separate per-job output directory
- R5c. All job files (input + output) are deleted on download, on expiry, or on failure
- R5d. Job IDs use cryptographically random UUIDs (not sequential integers)
- R5e. No file contents are logged; only file size and MIME type are recorded in
  application logs

### R6 — Security Hardening

- R6a. File type validated via magic bytes (not just extension) — reject non-ebook
  MIME types before processing
- R6b. Each conversion runs as an isolated subprocess with a dedicated temp directory
  that is destroyed on completion
- R6c. Subprocess runs under a restricted system user with no write access outside
  the temp directory
- R6d. HTTPS enforced via Let's Encrypt; Cloudflare in front for DDoS protection
  and rate limiting
- R6e. API endpoints accept only multipart form data for uploads; all other inputs
  are JSON with strict schema validation
- R6f. Documented upgrade path: per-job Docker containerization when conversion volume
  justifies the overhead (post-MVP)
- R6g. No credentials, API keys, or secrets stored in the codebase or config files;
  all secrets via environment variables

### R7 — SEO and Landing Pages

SEO is the primary acquisition channel. The web framework must support SSR.

**Competitive context (researched 2026-05-13):** Generic "PDF to Kindle" is dominated by
10+ commodity converters (Aspose, CloudConvert, Zamzar, PDF2Kindle.com, etc.) that are
all Calibre pass-throughs with no quality layer. Quality-aware terms ("academic PDF to
Kindle", "PDF footnotes Kindle", "multi-column PDF Kindle") have near-zero competition.
The quality comparison content angle is completely unaddressed by any competitor.

**Primary SEO targets (quality-aware, low competition):**
- "academic PDF to Kindle converter"
- "convert PDF to KFX" (competitors exist but are basic wrappers — quality story wins)
- "PDF footnotes Kindle" / "PDF with footnotes to Kindle"
- "multi-column PDF Kindle"
- "why does my PDF look bad on Kindle" (informational — drives quality comparison page)

**Secondary SEO targets (high-competition, compete on free tier):**
- "PDF to Kindle converter" (generic — used for free tier landing, not primary)
- "PDF to EPUB" / "EPUB to MOBI" (very crowded, supporting pages only)

- R7a. Next.js with SSR/SSG for all public-facing pages
- R7b. Dedicated keyword-optimized landing pages:
  - `/` — Primary: quality-aware converter pitch, not generic "PDF to Kindle"
  - `/pdf-to-kfx` — "convert PDF to KFX" (medium competition, quality advantage)
  - `/academic-pdf-to-kindle` — "academic PDF to Kindle converter" (low competition, high intent)
  - `/quality` — Quality comparison page: before/after screenshots of complex academic
    PDFs through raw Calibre vs. the smart pipeline. This is the link-bait page
    for r/kindle, r/ebooks, and academic communities.
  - `/epub-to-mobi` — Secondary format conversion (supporting page)
- R7c. Structured data markup (Schema.org `SoftwareApplication`, FAQ schema on landing pages)
- R7d. Core Web Vitals compliance — LCP < 2.5s, CLS < 0.1
- R7e. Open Graph and Twitter Card meta tags on all public pages
- R7f. XML sitemap and robots.txt at root
- R7g. Quality comparison page must include real side-by-side screenshots of a complex
  academic PDF (multi-column, footnotes) converted via raw Calibre vs. the smart
  pipeline — this is the primary link-building asset

### R8 — Stack and Infrastructure

- R8a. Backend: Python + FastAPI, hosted on claude-dev-01 (Hetzner VM)
- R8b. Frontend: Next.js, deployed to Vercel (free tier sufficient for v1 traffic) or
  served from the same VM via Nginx reverse proxy
- R8c. Job queue: in-process asyncio queue for v1 (Redis + Celery upgrade path
  documented for when concurrency demands it)
- R8d. Token/job state storage: SQLite on VM for v1 (single-writer, low concurrency)
- R8e. Cloudflare as CDN and DDoS layer in front of both frontend and API
- R8f. Let's Encrypt SSL for the API domain

---

## Success Criteria

- A user can upload a complex academic PDF (multi-column, footnotes) and see a
  noticeably better Kindle output from the premium tier vs. the free basic conversion
  within 3 minutes of arrival
- A new visitor landing on the homepage can complete a free conversion without
  creating an account
- The `/pdf-to-kfx` landing page ranks on page 1 of Google for "convert PDF to KFX"
  within 90 days of launch
- A credit purchase completes without error and produces a working download link
- All uploaded files are provably deleted within 24 hours (verified by log audit)

---

## Scope Boundaries

**In scope for v1:**
- Free basic conversion (Calibre pass-through)
- Premium smart conversion (full EbookAutomation pipeline)
- Credit purchase via Stripe (stateless signed tokens)
- Async job queue with status polling
- SEO landing pages and structured data
- File lifecycle management (upload → convert → download → delete)
- Security: file validation, subprocess isolation, rate limiting, HTTPS

**Explicitly out of scope for v1:**
- User accounts, login, or saved conversion history
- Email-to-Kindle delivery (existing `tools/email_to_kindle.py` is ready but deferred)
- TTS / audiobook output
- Batch processing (multiple files at once)
- API access for programmatic use
- Docker containerization per job (documented upgrade path, not v1)
- Redis / Celery job queue (upgrade path documented)
- Visual QA reporting for users
- Mobile app

---

## Key Decisions

- **Stateless over accounts**: No user PII collected or stored. Token-based credits
  (signed JWT/HMAC) prevent double-spend without a user database. Privacy-as-feature
  is a genuine differentiator vs. Zamzar and CloudConvert.
- **Credits over subscription**: Target users convert occasionally (not daily). Per-use
  credits have lower psychological friction than recurring billing for an infrequent
  task.
- **Quality tier over count tier**: Free tier demonstrates that a conversion is possible;
  premium tier demonstrates why quality matters. The upgrade prompt sells itself when
  users see garbled headings or missing TOC in the free result.
- **Next.js for SEO**: SSR is table stakes for organic search. Plain SPA (React without
  SSR) would require separate static pages for SEO, which is more work.
- **Same VM to start**: claude-dev-01 is already running the pipeline. Adding a web
  service is a marginal infrastructure change, not a new cost center. Migrate to a
  dedicated VM when traffic justifies it.

---

## Risks and Open Questions

### Unresolved

- **[Market risk]** Can quality differentiation drive enough organic traffic to justify
  the build? The "PDF to KFX" niche is low-competition but also low-volume. SEO-first
  approach (R7) is designed to test this before investing in the full billing
  infrastructure.
- **[Calibre licensing]** Calibre is GPL. The web service invokes it as an external
  subprocess (same as the current desktop pipeline), not by importing Calibre Python
  modules. This should be GPL-clean, but confirm before launch.
- **[Pricing]** Credit pack pricing ($X for 5, $Y for 20) depends on infrastructure
  cost per conversion. Benchmark conversion time and VM cost per job during planning.
- **[Domain]** Domain name selection is deferred. Avoid trademarked terms (Kindle,
  Amazon). Target `.io` or `.app` with "convert" or "ebook" in the name.

### Deferred to Planning

- API endpoint design (FastAPI routes, request/response schemas)
- Next.js page structure and component design
- Stripe webhook handling and token generation implementation
- SQLite schema for job state and token tracking
- Nginx / Caddy reverse proxy configuration on claude-dev-01
- Deployment pipeline (GitHub Actions → SSH deploy to VM)
- Monitoring and alerting (failed jobs, queue depth, disk usage)

---

## Phased Delivery

### Phase 1 — Core Conversion Service (Backend + Basic UI)
- FastAPI backend: file upload, job queue, status polling, file lifecycle
- Subprocess wrapper around the existing EbookAutomation pipeline
- Basic Next.js UI: upload form, status polling, download
- Free tier only (no Stripe integration yet)
- Deploy to claude-dev-01 behind Cloudflare

### Phase 2 — Premium Tier + Billing
- Stripe Checkout integration
- Signed token generation and validation
- Token/job state SQLite DB
- UI: pricing page, credit purchase flow, token redemption

### Phase 3 — SEO and Launch
- Keyword-optimized landing pages (R7b)
- Structured data markup
- Quality comparison page with before/after screenshots
- XML sitemap, robots.txt
- Core Web Vitals audit and fix

### Phase 4 — Security Hardening
- Magic-byte file validation
- Rate limiting enforcement (Cloudflare + backend)
- Subprocess restricted user
- Secrets audit

---

## Next Steps

→ Questions resolved. Ready for `/ce:plan` to produce the Phase 1 implementation plan.
  Recommend starting with Phase 1 (backend + basic UI) to validate the full pipeline
  integration before investing in billing.
