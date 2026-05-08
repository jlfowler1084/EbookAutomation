# EB-142: Calibre KFX Stderr Capture for Large-PDF Failure Diagnosis

## Problem

During the 2026-04-23 overnight batch, Calibre's KFX-Output plugin exited with code 1
on six large PDFs (19-65 MB). The batch log recorded only "Calibre exited with code 1"
with no stderr or stdout content, making root-cause diagnosis impossible.

Affected books:
- Wilsonianism (64.7 MB) — Lloyd E. Ambrosius
- FDR Political Life (40 MB)
- Theological Dictionary Vol 8 (47.7 MB)
- Helen Boak Women in Weimar (19.3 MB)
- Liebermann Exile Inc (20.1 MB)
- Prophets of Israel (19.7 MB)

## Root Cause

The PowerShell `Convert-PdfToKindle` function already redirected Calibre's stderr to a
temp file via `-RedirectStandardError $errFile`, but the logging code on failure had two
problems:

1. It only read `$errFile` (stderr) and not `$outLog` (stdout). Calibre writes most of
   its progress and error messages to **stdout**, not stderr — so the actual error was
   silently discarded.
2. The stderr tail was limited to 10 lines (primary failure) or 5 lines (AZW3 fallback),
   which may have truncated verbose Calibre output.
3. The prefix was `"Kindle:   $line"` — not easy to grep in logs.

The Python `extract_text_via_calibre()` function already included `result.stderr` in its
RuntimeError message but did not log individual lines before raising, so the error
context was buried in exception tracebacks rather than surfaced as log lines.

## Fix Applied (EB-142)

### module/EbookAutomation.psm1

**Primary KFX failure path** (triggered when Calibre exits non-zero during KFX conversion):
- Tail limit raised from 10 to 50 lines for stderr
- Added stdout capture: reads `$outLog` (last 50 lines) with `[CALIBRE_STDOUT]` prefix
- Changed log prefix from `"Kindle:   $line"` to `"[CALIBRE_STDERR] $line"`

**AZW3 fallback failure path** (triggered when AZW3 fallback also fails):
- Same changes: tail 50 for stderr, add stdout capture, `[CALIBRE_STDERR]`/`[CALIBRE_STDOUT]` prefixes

### tools/pdf_to_balabolka.py

**`extract_text_via_calibre()` function**:
- On non-zero exit, logs each line of stderr with `[CALIBRE_STDERR]` prefix before raising
- Logs each line of stdout with `[CALIBRE_STDOUT]` prefix before raising
- RuntimeError message unchanged (still includes raw stderr for exception tracebacks)

## How to Diagnose Future KFX Failures

After this patch, search the batch log with:

```
grep "\[CALIBRE_STDERR\]\|\[CALIBRE_STDOUT\]" logs/overnight-batch-*.log
```

The Calibre KFX plugin typically reports failures like:
- Plugin load errors (KFX Output plugin not installed or incompatible version)
- Memory/size errors for very large books
- Font embedding failures
- Image processing errors

## Repro Status

Wilsonianism PDF is available in `archive/` (Lloyd E. Ambrosius, Palgrave Macmillan 2002).
Repro requires running the full KFX conversion pipeline on a >19 MB PDF and triggering
the Calibre exit-code-1 condition. The patch is diagnostic-only; the conversion strategy
(HTML -> KFX -> AZW3 fallback) is unchanged.
