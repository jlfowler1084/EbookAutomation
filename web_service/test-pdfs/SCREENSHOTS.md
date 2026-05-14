# Quality Comparison Screenshots — Reproduction Guide

These screenshots are committed to `web_service/frontend/public/quality/` and served
statically by Next.js. They power the `/quality` comparison page (Unit 2).

## Artifacts

| File | Description |
|---|---|
| `leafbind-demo.tex` | LaTeX source — synthetic two-column academic paper |
| `leafbind-demo.pdf` | Compiled PDF (two passes required for cross-refs) |
| `leafbind-demo-calibre.epub` | Free-tier Calibre raw PDF→EPUB output |
| `leafbind-demo_balabolka.txt` | Premium pipeline extraction (column-aware + footnote linking) |
| `leafbind-calibre.txt` | Calibre EPUB flattened to plain text (for diff comparison) |
| `make-comparison-html.py` | Script that generates the 6 comparison HTML files |
| `calibre-*.html` / `pipeline-*.html` | Rendered HTML used as screenshot source |

## Reproduction Steps

### Step 1 — Compile the LaTeX PDF

```powershell
# Requires MiKTeX (winget install MiKTeX.MiKTeX)
# Configure auto-install on first run:
initexmf --set-config-value=[MPM]AutoInstall=1

cd web_service\test-pdfs

# Two passes required: first pass generates .aux; second resolves cross-refs
pdflatex -interaction=nonstopmode leafbind-demo.tex
pdflatex -interaction=nonstopmode leafbind-demo.tex
```

Expected output: `leafbind-demo.pdf` (~177 KB, 6 pages, two-column layout).

### Step 2 — Calibre free-tier conversion

```powershell
ebook-convert leafbind-demo.pdf leafbind-demo-calibre.epub
```

Expected output: `leafbind-demo-calibre.epub` (~25 KB).

To inspect Calibre's raw text extraction:

```powershell
ebook-convert leafbind-demo-calibre.epub leafbind-calibre.txt
```

### Step 3 — Premium pipeline conversion

Run from the repo root (not from the worktree):

```powershell
cd F:\Projects\EbookAutomation
python tools/pdf_to_balabolka.py `
  --input "web_service/test-pdfs/leafbind-demo.pdf" `
  --html-extraction `
  --force-columns `
  --output-dir "web_service/test-pdfs"
```

Expected output: `leafbind-demo_balabolka.txt` (~14 KB).

Note: The `--cli` flag referenced in the original plan does not exist in the current
pipeline version. Use `--html-extraction --force-columns` to activate column-aware
extraction and semantic HTML mode.

### Step 4 — Generate comparison HTML

```powershell
python web_service/test-pdfs/make-comparison-html.py
```

This generates 6 HTML files in `web_service/test-pdfs/`:
- `calibre-columns.html` / `pipeline-columns.html`
- `calibre-footnotes.html` / `pipeline-footnotes.html`
- `calibre-headings.html` / `pipeline-headings.html`

### Step 5 — Capture screenshots via Playwright

Start a local HTTP server to serve the HTML files (Playwright blocks `file://` URLs):

```powershell
# Run from web_service/test-pdfs/
python -m http.server 8899
```

Then use Playwright (Claude Code MCP plugin) or this Playwright script to capture:

```javascript
// Playwright screenshot script
const { chromium } = require('playwright');
const path = require('path');

const pages = [
  'calibre-columns', 'pipeline-columns',
  'calibre-footnotes', 'pipeline-footnotes',
  'calibre-headings', 'pipeline-headings',
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 620, height: 700 });

  for (const name of pages) {
    await page.goto(`http://localhost:8899/${name}.html`);
    await page.screenshot({
      path: `../frontend/public/quality/${name}.png`,
      fullPage: true,
    });
    console.log(`Captured ${name}.png`);
  }

  await browser.close();
})();
```

### Screenshot dimensions

- Viewport: 620 × 700 px
- Output format: PNG, full-page
- Crop: not cropped (full page captures ~600 × 500 effective content area)
- Output directory: `web_service/frontend/public/quality/`

### Failure modes demonstrated

| Comparison | Calibre (failure) | Pipeline (success) |
|---|---|---|
| Columns | Left/right column text interleaved on same lines | Columns extracted in reading order |
| Footnotes | All footnotes dumped at page bottom, disconnected | Each footnote appears inline at its reference |
| Headings | Section titles as plain paragraph text | h2/h3 semantic heading hierarchy |
