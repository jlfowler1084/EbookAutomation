# EbookAutomation — Qwen Code Context

This project is a **PDF/EPUB → TTS + Kindle automation pipeline**. It extracts text from ebooks, cleans OCR artifacts, detects chapters and headings, and outputs either plain text for Balabolka audio conversion or semantic HTML for Kindle delivery (via Calibre KFX). The goal is a hands-off inbox-to-audiobook flow for the books Joe reads.

## Tech stack

- **PowerShell 5.1+** — primary orchestration, module (`EbookAutomation.psm1`), inbox automation
- **Python 3.12** — core extraction and HTML generation in `tools/pdf_to_balabolka.py`
- **pdfminer.six / pypdf / PyMuPDF** — layered PDF extraction (fallback chain)
- **Balabolka + FFmpeg** — local TTS and audio post-processing
- **Calibre (KFX output)** — Kindle delivery format conversion
- **Claude API** — heading classification (body vs. heading vs. subheading)
- **Gemini API** — OCR fallback when text extraction fails
- **SQLite** — pipeline state, processed book tracking

## Directory layout

```
EbookAutomation.psm1        main PowerShell module
settings.json               pipeline config (paths, voices, options) — NOT .claude/settings.json
module/                     .psm1 module source + manifest
  inbox/                    drop zone for new books
  processing/               active conversions
  output/                   finished artifacts (audio + KFX)
tools/
  pdf_to_balabolka.py       core extraction + HTML generation engine
  test_pipeline.py          6-book regression harness
  test_voice_tags.py        TTS SSML regression suite (also gates SecondBrain SB-PSModules)
tests/                      regression corpus (the 6 books)
docs/                       design docs, decision records
```

## Write permissions

All directories in this project are writable — this is pure code. Modify PowerShell modules, Python tools, tests, configs, and docs freely. The only things to leave alone are `.env` and anything matched by `.gitignore`.

## Key entry points

```powershell
# Run the full regression harness
python tools/test_pipeline.py

# Validate TTS voice tag regressions (cross-project gate for SB-PSModules)
python tools/test_voice_tags.py

# Convert a single book from the command line
python tools/pdf_to_balabolka.py --input book.pdf --mode balabolka
python tools/pdf_to_balabolka.py --input book.pdf --mode kindle

# PowerShell inbox automation
Invoke-EbookPipeline
```

## Testing — non-negotiable

This project has a **6-book baseline regression suite** that must pass before any heading classification or extraction change ships:

| Book | What it tests |
|---|---|
| **Oil Kings** | Endnote detection and in-text endnote linking |
| **Mexico Illicit** | OCR cleanup on a noisy scan |
| **Lincoln Highway** | Multi-narrator handling in fiction |
| **Atomic Habits** | Heading classification (body vs. H1/H2/H3) |
| **Sapiens** | Long chapter boundaries |
| **Extreme Ownership** | Baseline smoke test |

Before shipping any change that touches `pdf_to_balabolka.py`, chapter detection, heading classification, or the PowerShell pipeline, run `python tools/test_pipeline.py` and verify:
- Endnote count matches expected
- Body vs. heading classification is correct
- Chapter count matches expected
- PAGE markers are present and correct
- TOC nesting is accurate

There's also a post-edit hook that auto-runs quick tests on changed files — don't fight it.

### Cross-project testing rule (SB-8)

`tools/test_voice_tags.py` is the canonical gate for SSML emission across **this project and SecondBrain's SB-PSModules**. Any function in either project that emits SAPI XML voice/rate/silence tags must have a regression case here before it ships. The test asserts:

- SAPI XML format only, no colon-syntax pseudo-tags
- No standalone tag lines
- Voices restricted to: Microsoft Steffan, Aria, Jenny, Guy Online

If you touch TTS-emitting code in either project, add the test case here **first**, then make the change.

## Code style

### PowerShell
- **Verb-Noun naming** — `Convert-PdfToKindle`, `Invoke-EbookPipeline`, never `DoThing` or `pdf_convert`
- **`[CmdletBinding()]`** on every advanced function
- **`Export-ModuleMember`** in `.psm1` files — explicit exports, no implicit surface
- **`Write-EbookLog`** for all status output, never `Write-Host` (breaks log capture)
- **UTF-8 encoding** on all script files, no em-dashes, no bash `&` operator
- **Windows paths only** — `C:\...`, `F:\...`, never `/home/...` or forward slashes

### Python
- **`argparse`** for CLI entry points, **`tkinter`** for any GUI
- **`logging` module**, never `print()`, for status output
- **`if __name__ == "__main__":`** guards in runnable modules
- **UTF-8 stdout reconfig** on Windows when output may be captured
- **Paths resolved** via `Path(__file__).resolve().parent`
- **`python -m pip install`**, not bare `pip`
- Follows the `python-core` and `python-architecture` conventions from `~/.claude/skills/`

## Useful Qwen Code tasks

- Refactoring Python extraction engine phases (pdfminer fallback logic, column detection, OCR cleanup regex)
- Adding new test cases to the 6-book baseline when a new book reveals a class of bug
- Wiring Gemini OCR fallback into the extraction chain
- Building new PowerShell cmdlets for batch conversions, reporting, or inbox management
- Debugging heading classification failures using Claude API prompts
- Writing Pester tests for the PowerShell module surface
- Improving Balabolka SSML output and voice selection logic
- Updating the post-edit hook and regression runners

## Gotchas

- **Heading classification changes cascade.** A tweak to how H1 vs. H2 is detected changes the TOC, which changes Calibre KFX compatibility. Always run the full 6-book pipeline before shipping.
- **Ligature fixes break endnote linking** if you're not careful. The `fi` and `fl` substitutions interact with endnote anchor text — test Oil Kings after any ligature regex change.
- **Two `settings.json` files exist** in this project space and they are not the same:
  - `EbookAutomation/settings.json` — pipeline config (paths, voices, inbox/output locations)
  - `.claude/settings.json` — Claude Code harness config
  Don't cross the streams.
- **Never use cloud TTS.** Balabolka + local SAPI voices only. This is a hard rule for cost and offline reliability.
- **Never use Unix paths.** All paths in PowerShell and Python must be Windows-style absolute paths.
- **Don't add Python dependencies** without updating `requirements.txt` — the test harness validates the environment.
- **Don't commit `.env`** or any file containing API keys (Claude, Gemini, or otherwise).

## See also

**`CLAUDE.md`** at the project root is the authoritative source for Claude Code-specific infrastructure — hooks, subagent coordination, worktree policy, regression manifest, and Jira ticket prompt format. Qwen Code doesn't use most of that machinery directly, but if you're debugging a session issue or looking up the canonical definition of a convention referenced here, read CLAUDE.md for the full story.

The global CLAUDE.md at `C:\Users\Joe\.claude\CLAUDE.md` contains cross-project rules (git workflow, worktree conventions, commit prefixes, API cost governance) that apply here too.

For cross-project dependencies — especially the shared TTS gate with SecondBrain's SB-PSModules — see `F:\Obsidian\SecondBrain\Resources\project-dependencies.json`.
