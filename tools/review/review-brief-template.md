> ⚠️ Schema status: This template references a JSON output schema whose
> formal definition is owned by EB-33. The sample fragments below are
> illustrative; finalize alignment when EB-33 lands.

# Review Brief Template

This document is injected as context at **Round 1** for both Claude and Codex before either
agent has seen the snapshot. It establishes shared ground truth about the project, the file
under review, and known concerns.

**Injected variables:** `{{FILE}}`, `{{ROLE_IN_PIPELINE}}`, `{{KNOWN_CONCERNS}}`

---

## Project Overview

**EbookAutomation** is a PowerShell + Python automation suite for:
- Converting ebooks to TTS-ready text for Balabolka
- Converting PDFs to Kindle-formatted KFX files via Calibre
- Generating podcast/audiobook MP3s
- FOH (Friends of Habersham) forum scraping and daily brief generation

**Location:** `F:\Projects\EbookAutomation\`
**Repo:** jlfowler1084/EbookAutomation (private), **Branch:** master

**Pipeline architecture (sequential, left to right):**
```
inbox/
  → pre-flight analysis
  → extraction (pdfminer / pypdf / PyMuPDF column-aware)
  → HTML generation
  → heading classification
  → TOC generation
  → bookmark reconciliation
  → footnote linking
  → Calibre conversion
  → KFX output
  → optional TTS (Balabolka)
```

Each stage feeds the next. A silent failure or behavioral change in any stage
propagates downstream and typically surfaces only at Calibre conversion or
visual QA — far from the source.

---

## Coding Standards

### PowerShell
- Use **Verb-Noun** naming: `Convert-PdfToHtml`, `Export-AudioBook`, `Test-Pipeline`
- Use `Write-EbookLog` for structured logging — never `Write-Host`
- Use `Export-ModuleMember` for all public functions in `.psm1`
- Use `[CmdletBinding()]` and `param()` blocks in every function
- Use `$ErrorActionPreference = 'Stop'` in all scripts

### Python
- Use `argparse` for CLI interfaces
- Use `logging` module — never `print()` for status output
- Include `if __name__ == "__main__":` guards in all runnable modules
- Reconfigure stdout/stderr to UTF-8 on Windows when output may be captured
- Resolve paths relative to script location using `Path(__file__).resolve().parent`
- Use `py -3.12 -m pip install` — not bare `pip`

### General
- Generate complete working code, not fragments
- When modifying existing files, show specific changes with surrounding context
- Do not use Unix-style paths (`/home/...`) — use Windows paths (`C:\...`, `F:\...`)

---

## Regression-Prevention Rules (Critical — Read Before Proposing Any Change)

**The #1 time sink in this project is fix-then-regression cycles.**

Changes to heading levels cascade into TOC nesting and Calibre compatibility.
A fix for one book has broken four others multiple times.

### Non-negotiable pre-conditions before proposing changes to:
- **Heading detection / heading classification** — analyze current behavior across
  ALL 6 corpus books first. Do NOT propose code changes without cross-corpus impact analysis.
- **TOC generation** — heading classification changes break TOC nesting and Calibre compatibility.
- **Bookmark reconciliation** — depends on heading output; changes ripple into KFX structure.
- **Footnote / endnote linking** — ligature fixes can break endnote linking. Both subsystems
  interact through the same text normalization phase.
- **OCR cleanup** — ligature normalization affects downstream pattern matching.

### Test corpus (6 books, all must pass after any pipeline change):
| Book | Regression Focus |
|------|-----------------|
| The Oil Kings (Cooper) | Complex endnotes, dual numbering |
| Mexico's Illicit Drug Networks (Jones) | OCR artifacts, ligatures |
| The Return of the Gods (Cahn) | Thematic chapter names, non-sequential structure |
| Atomic Habits (Clear) | Dense formatting, callout boxes |
| Decline of the West (Spengler) | TOC depth, footnote pairing on long-form prose |
| Python in Easy Steps (McGrath) | Short, regular chapters — baseline sanity canary |

### Known historical regressions (use as regression anchors):
- **SCRUM-299:** Running headers were being classified as chapter headings, inflating TOC depth.
  Fixed by adding `_is_running_header()` guard in the font-size classifier. Any change to
  heading detection must verify this guard remains effective.
- **Ligature / endnote interaction:** Normalizing `fi`, `fl`, `ffi` ligatures in OCR output
  can corrupt endnote reference patterns (e.g., `"fi1"` where `fi` was a ligature and `1`
  was the note number). Test endnote counts before and after any ligature change.
- **Heading-level collapse:** Mapping `h3` to `h2` for Calibre compatibility broke nested
  chapter/section structure in multi-level books (Spengler). Never flatten heading levels
  without checking Spengler's TOC output.

---

## File Under Review

**File:** `{{FILE}}`

**Role in pipeline:** `{{ROLE_IN_PIPELINE}}`

---

## Known Issues or Concerns for This Review

The following concerns have been flagged by the project maintainer before this review session.
Both reviewers should pay particular attention to these areas:

```
{{KNOWN_CONCERNS}}
```

---

## What "Good" Looks Like

A successful review produces:
1. **Concrete, actionable proposals** — every issue has exact `current_code`, `proposed_code`,
   and a rationale that explains the real-world failure mode, not just style preference.
2. **Severity honesty** — `critical` means the pipeline will produce wrong output today.
   `nitpick` means "this is fine but could be cleaner." Do not inflate severity to get attention.
3. **Regression awareness** — any proposal touching the non-negotiable pipeline stages above
   includes an explicit cross-corpus impact statement.
4. **No phantom issues** — do not flag patterns that are correct for this project's environment
   (e.g., Windows path syntax, PowerShell idioms that look unusual to Unix-trained reviewers).
5. **Disagreements have evidence** — counter-proposals include alternative code and a testable
   reason why the alternative is better.

A review that flags 2 real issues with concrete fixes is more valuable than one that flags
12 issues where 10 are noise. Calibrate accordingly.
