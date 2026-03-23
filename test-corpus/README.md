# Test Corpus (Hot Folder)

Drop ebook files here for automated regression testing.

## Supported formats

- `.pdf` — routed through pdfminer/PyMuPDF auto-detection
- `.epub` — EPUB extraction path
- `.mobi`, `.azw`, `.azw3` — Calibre intermediate path (not yet supported in harness)

## How it works

1. **Drop a file** into this folder (e.g., `MyBook.pdf`)
2. **First run** (`python tools/test_pipeline.py --corpus`): the pipeline processes the file and saves a baseline as `MyBook.baseline.json`
3. **Subsequent runs**: the pipeline compares output against the saved baseline and reports regressions
4. **Re-capture**: `python tools/test_pipeline.py --corpus --recapture "MyBook"` overwrites the baseline

## Sidecar files

| File | Purpose |
|------|---------|
| `<name>.baseline.json` | Auto-captured baseline snapshot (committed to git) |
| `<name>.expect.json` | Manual override assertions — same schema as hardcoded test expectations (committed to git) |

## Notes

- The ebook files themselves are **not** committed (copyrighted material) — only `.baseline.json` and `.expect.json` sidecars are tracked in git.
- If you replace a source file with a different version, the harness detects the changed file hash and warns that the baseline may be stale.
- Corpus tests run after hardcoded and auto-captured tests in the full suite.
