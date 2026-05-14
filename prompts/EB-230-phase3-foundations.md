# EB-230 Phase 3: Design Foundations + Synthetic PDF (Unit 0 + Unit 1)
# Model: SONNET
# Justification: Structured implementation following a complete plan. Unit 0 is
# npm install + config file creation + surgical layout.tsx edit. Unit 1 is LaTeX
# authoring + pipeline run + screenshot capture. Both are THINK + DO tasks within
# a clearly scoped plan — Sonnet is the right tier.

## Tickets

- **Primary:** EB-230 — Phase 3 SEO landing pages + quality comparison + structured data
- **Blocks:** EB-230 Units 2–9 (all subsequent pages depend on Unit 0 foundations)
- **Relates to:** EB-45 (parent), INFRA-371 (SEO skill), INFRA-393 (web-aesthetics skill)

## Estimated Scope

Multi-file frontend change — Unit 0 creates 4 new files + modifies 2 existing;
Unit 1 creates the LaTeX source, compiled PDF, 6 PNG screenshots, and a SCREENSHOTS.md.
Frontend build verification required after Unit 0.

---

## Phase 0 — Branch Setup

**Branch:** `worktree/EB-230-phase3-foundations`
**Base:** `master`
**Worktree mode:** create

Before any other work:

1. `git checkout master && git pull origin master`
2. Create worktree:
   ```powershell
   git worktree add .worktrees/EB-230-phase3-foundations -b worktree/EB-230-phase3-foundations
   ```
3. Change into the worktree:
   ```powershell
   cd .worktrees/EB-230-phase3-foundations
   ```
4. Confirm branch: `git branch --show-current` should output `worktree/EB-230-phase3-foundations`
5. Confirm clean state: `git status` should show no modifications

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at:
`docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

The plan is thorough. Three constraints are the highest-risk failure modes for
Unit 0 — they are documented in the plan but are easy to miss in a 1100-line doc.
Locate them before writing any code:

1. **Tailwind Preflight MUST be disabled.** The existing pages (`/`, `/pricing`,
   `/recover`, `/status/[id]`) use ONLY inline styles — no CSS file exists at all.
   Tailwind's `@tailwind base` (Preflight) resets browser defaults globally and
   WILL break those existing pages if enabled. The plan specifies
   `corePlugins: { preflight: false }` in `tailwind.config.js` — see Unit 0
   Step 4 code block. This is the #1 way Unit 0 silently breaks production.

2. **`globals.css` must NOT include `@tailwind base`.** It contains only
   `@tailwind components` and `@tailwind utilities`. The plan's Unit 0 Step 5
   code block shows this explicitly. Adding `@tailwind base` (even accidentally)
   activates Preflight and triggers the same breakage as point 1.

3. **`tailwind.config.js` uses CommonJS `require()`, not ESM `import`.** The
   Tailwind config runs in Node/CommonJS context. `require("./design-tokens")`
   is correct. Using ESM `import` will crash the Tailwind PostCSS plugin at build
   time. The plan's Unit 0 Gotchas section calls this out explicitly.

**Design decisions locked in (do not re-litigate):**
- Tailwind v3 (not v4)
- Default `next/image` loader; quality comparison images as `<img>` from `public/`
- LaTeX for the synthetic PDF (not Typst, not HTML+Paged.js)
- Manual screenshots checked in; no Playwright CI regeneration
- `design-tokens.ts` stays small: 6 colors, 7 type sizes, 8 spacing steps, 3 shadows, 2 radii

**Options rejected (do not propose these):**
- Route group `(marketing)` layout — not needed; Preflight-disabled Tailwind works from
  the root layout without a scoped sub-layout
- CSS Modules for Tailwind scoping — not how Tailwind works; Preflight disable is the
  correct mechanism
- Tailwind v4 CSS-first config — deferred; v3 is the stable choice for this install

**Hidden constraints:**
- `web_service/frontend/public/` does not exist yet. Create it as part of Unit 1
  before committing any screenshots. Next.js serves `public/` as static root;
  the directory must exist before `next build` references any `public/` asset.
- `tailwind.config.js` lives in `web_service/frontend/` (the Next.js project root
  for the frontend build), NOT in the repo root. PostCSS config lives there too.
- GSC verification is a manual prerequisite in Unit 0 Step 8. It requires a browser
  action by the user — stop and ask the user to complete the GSC DNS TXT step before
  proceeding. The Cloudflare MCP can add the DNS TXT record; the user must click
  "Verify" in GSC after propagation (~5–10 min).
- The LaTeX compilation for Unit 1 requires `pdflatex` or `xelatex`. On Windows,
  install MiKTeX (`winget install MiKTeX.MiKTeX`) if not already present.

---

## What NOT To Do

### Standing Rules (do not modify — sourced from deployment-prompt-template.md)

- **Do not commit directly to master.** This repo is under ADR-0029 enforcement. All
  commits must go on the branch created in Phase 0, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only
  for human emergency override. If a guard blocks an action, stop and report the block
  — do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not
  reinterpret the block as a false positive, do not attempt alternative commands to
  circumvent the guard. Report the exact block message to the user and wait.
- **Ambiguous user phrasing is not authorization to bypass.** "Ship it", "just commit
  it", "go ahead and push" are never authorization to bypass workflow rules.

### Session-Specific Prohibitions

- **Do not touch any existing page files.** `app/page.tsx`, `app/pricing/page.tsx`,
  `app/recover/page.tsx`, `app/status/[id]/page.tsx`, and all their components are
  off-limits for Unit 0 and Unit 1. The ONLY existing file to modify is
  `app/layout.tsx` (brand metadata + globals.css import).
- **Do not add `@tailwind base` to `globals.css`.** Ever. See Context above.
- **Do not run `npm install` or `npm run build` on the VM.** Unit 0 work runs locally
  on the desktop. The VM deployment is a separate step outside this session's scope.
- **Do not write any JSX page components.** Units 2–6 (the actual pages) are out of
  scope for this session. If you finish Unit 0 + Unit 1 cleanly, stop and report.
- **Do not create the `public/quality/` directory until Unit 1.** Unit 0 has no
  dependency on it; creating it early can confuse the Unit ordering.
- **Do not author the `sitemap.ts` or `robots.ts` files.** Those are Unit 8.

---

## Phase 1 — Audit (READ-ONLY, STOP FOR REVIEW)

Before writing any code, read and confirm the current state of the frontend:

1. Read `web_service/frontend/app/layout.tsx` — confirm the current title is
   `"EbookAutomation — Ebook Converter"` and there is no `globals.css` import.
2. Read `web_service/frontend/package.json` — confirm Next.js 15.1.0, React 19,
   no Tailwind dependency present.
3. Read `web_service/frontend/next.config.js` — confirm no PostCSS or CSS-framework
   references.
4. Run `Get-ChildItem web_service/frontend/app -Recurse -Filter "*.css"` — confirm
   zero CSS files exist.
5. Run `Get-ChildItem web_service/frontend/public -ErrorAction SilentlyContinue` —
   confirm `public/` does not yet exist.
6. Confirm the plan file is present:
   `Test-Path "docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md"`

**Success criteria:**
- `layout.tsx` title is the old brand string (not yet updated)
- No Tailwind in `package.json`
- No CSS files exist
- `public/` directory absent
- Plan file confirmed present

**STOP.** Report the audit findings before proceeding to Phase 2.

---

## Phase 2 — Unit 0: Design Foundations + Brand Cleanup + GSC Prereq

Follow the plan's Unit 0 exactly. Work from `web_service/frontend/` for all npm
and file operations.

**Steps:**

1. Install Tailwind v3 dependencies (from `web_service/frontend/`):
   ```powershell
   cd web_service\frontend
   npm install -D tailwindcss@^3.4 autoprefixer postcss
   ```

2. Create `web_service/frontend/postcss.config.js` — exact content from plan
   Unit 0 Step 2.

3. Create `web_service/frontend/design-tokens.ts` — exact content from plan
   Unit 0 Step 3. Do not add tokens beyond what the plan specifies.

4. Create `web_service/frontend/tailwind.config.js` — exact content from plan
   Unit 0 Step 4. **Verify `corePlugins: { preflight: false }` is present.**

5. Create `web_service/frontend/app/globals.css` — contains ONLY:
   ```css
   @tailwind components;
   @tailwind utilities;
   ```
   No `@tailwind base`. No other content.

6. Edit `web_service/frontend/app/layout.tsx`:
   - Add `import "./globals.css";` as the first line
   - Update `metadata.title` to `"leafbind — PDF to Kindle Converter"`
   - Update `metadata.description` to the new brand copy from the plan
   - Add `metadata.openGraph` block from the plan
   - Preserve the existing `body style` attribute unchanged

7. Run the build to verify:
   ```powershell
   npm run build
   ```
   Expected: no TypeScript errors, no PostCSS errors, no missing module warnings.

8. **GSC prereq (requires user interaction):** Stop and ask the user to:
   - Open https://search.google.com/search-console
   - Check whether `https://leafbind.io` is already verified
   - If NOT: get the DNS TXT verification value from GSC; add it via the
     Cloudflare MCP as a TXT record on `@` for `leafbind.io`; click Verify
     in GSC after ~10 min propagation
   - Report the GSC verification status before you proceed

**Success criteria:**
- `npm run build` exits 0 with no errors or TypeScript warnings
- `tailwind.config.js` contains `corePlugins: { preflight: false }`
- `globals.css` contains no `@tailwind base`
- `layout.tsx` has the new brand title and globals.css import
- GSC verification status confirmed (verified or step recorded as pending)
- All existing page routes (`/`, `/pricing`, `/recover`) render correctly
  — verify by running `npm run dev` and spot-checking in the browser

**STOP.** Report the build output, the list of files created/modified, and the
GSC verification status before proceeding to Phase 3.

---

## Phase 3 — Unit 1: Synthetic PDF + Screenshots

Follow the plan's Unit 1 exactly.

**Steps:**

1. Verify LaTeX is available:
   ```powershell
   pdflatex --version
   ```
   If not installed: `winget install MiKTeX.MiKTeX` and restart the terminal.

2. Create `web_service/test-pdfs/` directory if it does not exist.

3. Author `web_service/test-pdfs/leafbind-demo.tex` — the LaTeX source for the
   synthetic academic paper. Follow the specification in the plan's Unit 1:
   - `\documentclass[twocolumn]{article}`
   - `\usepackage{lipsum}` for body text filler
   - At least 5 footnotes (`\footnote{}`), two on the same page, one spanning a
     page boundary
   - 6+ headings: `\section{}`, `\subsection{}`, `\subsubsection{}`
   - One `\begin{figure}` with `\caption{}`
   - A bibliography stub
   - Paper title: "The Epistemology of Computational Systems"

4. Compile the PDF:
   ```powershell
   cd web_service\test-pdfs
   pdflatex leafbind-demo.tex
   pdflatex leafbind-demo.tex   # Run twice for TOC/bibliography resolution
   ```
   Verify `leafbind-demo.pdf` is created and non-zero in size.

5. Convert via free tier (Calibre):
   ```powershell
   ebook-convert leafbind-demo.pdf leafbind-demo-calibre.epub
   ```

6. Convert via premium pipeline (from repo root):
   ```powershell
   python tools/pdf_to_balabolka.py --cli --input web_service/test-pdfs/leafbind-demo.pdf
   ```
   Note the output path.

7. Open both outputs in an ebook viewer. Capture side-by-side comparison screenshots
   of the three failure modes: columns, footnotes, headings. Crop to the relevant
   region (~800×600 px per screenshot).

8. Create `web_service/frontend/public/quality/` directory and place the 6 PNGs:
   ```
   calibre-columns.png
   pipeline-columns.png
   calibre-footnotes.png
   pipeline-footnotes.png
   calibre-headings.png
   pipeline-headings.png
   ```

9. Create `web_service/test-pdfs/SCREENSHOTS.md` documenting the exact commands
   used for steps 4–7 (pdflatex invocation, ebook-convert command, pipeline
   invocation, viewer used, crop dimensions).

**Success criteria:**
- `leafbind-demo.pdf` exists, opens in a PDF viewer, renders in two columns
- Both EPUB outputs open without errors in an ebook viewer
- All 6 PNG comparison files exist in `public/quality/`, each < 1 MB
- `SCREENSHOTS.md` documents all reproduction steps

**STOP.** Report: confirmation that the PDF renders in two columns, the file sizes
of all 6 PNGs, and any issues with the pipeline conversion.

---

## Phase 4 — Verification

### Per-file verification

- **`tailwind.config.js`**: `corePlugins.preflight === false` present; `content` glob
  matches `./app/**/*.{ts,tsx}` and `./components/**/*.{ts,tsx}`
- **`globals.css`**: Contains exactly 2 lines — `@tailwind components;` and
  `@tailwind utilities;`. No other content.
- **`design-tokens.ts`**: No raw hex values in any other file introduced in this session
- **`app/layout.tsx`**: New title is "leafbind — PDF to Kindle Converter"; body style
  attribute preserved unchanged; no other existing page broken
- **PNG screenshots**: 6 files present; each is a 2-up or side-by-side comparison
  showing a visible quality difference

### Runtime verification

```powershell
cd web_service\frontend
npm run build
```
Expected: exit 0, no errors, Tailwind CSS chunk in build output.

```powershell
npm run dev
```
Open `http://localhost:3000` — confirm existing homepage renders identically to
production (layout, upload form, colors). Check `http://localhost:3000/pricing` too.

---

## Phase 5 — Commit and Push

**STOP before committing.** Report the full file list to the user.

After approval:

1. Stage all Unit 0 + Unit 1 files:
   ```powershell
   git add web_service/frontend/tailwind.config.js
   git add web_service/frontend/postcss.config.js
   git add web_service/frontend/design-tokens.ts
   git add web_service/frontend/app/globals.css
   git add web_service/frontend/app/layout.tsx
   git add web_service/frontend/package.json
   git add web_service/frontend/package-lock.json
   git add web_service/test-pdfs/leafbind-demo.tex
   git add web_service/test-pdfs/leafbind-demo.pdf
   git add web_service/test-pdfs/SCREENSHOTS.md
   git add web_service/frontend/public/quality/
   ```

2. Commit:
   ```powershell
   git commit -m "feat(EB-230): Unit 0+1 — Tailwind foundations, design tokens, brand cleanup, synthetic PDF"
   ```

3. Push:
   ```powershell
   git push -u origin worktree/EB-230-phase3-foundations
   ```

4. **STOP before opening PR.**

---

## Pre-Flight Environment Checks

Before Phase 2, verify:

- Node.js is available: `node --version` (should be v20+)
- npm is available: `npm --version`
- `pdflatex` is available for Unit 1: `pdflatex --version`
- Calibre `ebook-convert` is available for Unit 1: `ebook-convert --version`
- Python pipeline is accessible: `python tools/pdf_to_balabolka.py --help`

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` and all work happened in the worktree
- [ ] No commits were made to master
- [ ] No bypass env vars were used
- [ ] Phase 1 audit was completed before any file creation
- [ ] `tailwind.config.js` has `corePlugins: { preflight: false }`
- [ ] `globals.css` has NO `@tailwind base` line
- [ ] `npm run build` exits 0 with no errors
- [ ] Existing routes (`/`, `/pricing`) render correctly in dev server
- [ ] 6 PNG screenshots committed to `public/quality/`
- [ ] GSC verification status confirmed
- [ ] Branch is pushed but PR is NOT yet opened

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Options** — If a decision point was reached, what are the alternatives
4. **Recommendation** — Your recommended path, with rationale

At final completion, also include:
5. **Commit hash** — For the commit made
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket

---

## Invocation

```
claude --model sonnet "[EB-230] Phase 3 Unit 0+1: Tailwind foundations + synthetic PDF -- Read prompts/EB-230-phase3-foundations.md and follow the instructions"
```
