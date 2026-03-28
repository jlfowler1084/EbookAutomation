# SCRUM-34 — PowerShell Module Help System

## Session Name
powershell-help-system

## Claude Code Model
**Sonnet** — Straightforward mechanical additions following an established pattern. No architectural decisions, no subtle debugging.

## Ticket
SCRUM-34 — PowerShell Module Help System (sub-tasks 3a + 3c)

## Objective
Add complete comment-based help blocks to all 17 exported functions in `module/EbookAutomation.psm1`, plus create new `Set-EbookDefaults` / `Get-EbookDefaults` cmdlets. Do NOT modify any function logic — this is help-text and new cmdlets only.

---

## Part 1: Comment-Based Help on Exported Functions

Every exported function needs a complete help block with `.SYNOPSIS`, `.DESCRIPTION`, `.PARAMETER` (for each param), and at least one `.EXAMPLE`. Some functions already have partial help — fill in the gaps. Some already have good help — leave those alone or just add missing `.EXAMPLE` blocks.

### Functions and their current help state (line numbers for reference):

| Function | Line | Has SYNOPSIS | Has DESCRIPTION | Has PARAMETER | Has EXAMPLE | Action Needed |
|---|---|---|---|---|---|---|
| `Get-EbookConfig` | 20 | Yes (1-line) | No | N/A (no params) | No | Add DESCRIPTION + EXAMPLE |
| `Write-EbookLog` | 162 | Yes (1-line) | No | No | No | Add DESCRIPTION + PARAMETER + EXAMPLE |
| `Convert-ToTTS` | 227 | Yes | Yes | Partial | Yes | Review completeness — likely OK |
| `Convert-ToKindle` | 534 | Yes | Yes | Partial | No | Add EXAMPLE blocks |
| `Send-ToKindle` | 2144 | Yes | Yes | Yes | Yes | Likely complete — verify |
| `Invoke-EbookPipeline` | 2632 | Yes | Yes | Partial | Yes | Review — may need new params documented |
| `Install-EbookScheduledTask` | 3046 | Yes | Yes | No | No | Add PARAMETER + EXAMPLE |
| `Uninstall-EbookScheduledTask` | 3116 | Yes (1-line) | No | N/A | No | Add DESCRIPTION + EXAMPLE |
| `Get-EbookTaskStatus` | 3131 | Yes (1-line) | No | N/A | No | Add DESCRIPTION + EXAMPLE |
| `Initialize-EbookAutomation` | 3158 | Yes (1-line) | No | No | No | Add DESCRIPTION + PARAMETER + EXAMPLE |
| `Convert-BriefToYouTube` | 3330 | Yes | Yes | Yes | Yes | Likely complete — verify |
| `Invoke-Balabolka` | 3538 | Yes | Yes | Yes (1-line each) | No | Add EXAMPLE blocks |
| `Send-ToClaudeAPI` | 3665 | Yes | Yes | Yes | No | Add EXAMPLE blocks |
| `Get-ChapterStructure` | 3737 | Yes | Yes | Yes | No | Add EXAMPLE blocks |
| `Test-EbookPipeline` | 3897 | Yes (bare) | No | Bare | No | Add DESCRIPTION + PARAMETER details + EXAMPLE |
| `Test-ConversionQuality` | 3935 | Yes | Yes | Yes | Yes | Likely complete — verify |
| `Invoke-ConvergeLoop` | 4105 | Yes | Yes | Yes | No | Add EXAMPLE blocks |

### Help block template to follow:
```powershell
<#
.SYNOPSIS
    One-line summary of what the function does.
.DESCRIPTION
    Detailed explanation of what the function does, when to use it,
    and any important behavior notes.
.PARAMETER ParamName
    Description of the parameter, including type, default value,
    and any validation constraints.
.EXAMPLE
    PS> Convert-ToTTS -InputFile "C:\Books\mybook.pdf"
    Converts mybook.pdf to Balabolka TTS text using default output directory.
.EXAMPLE
    PS> Convert-ToTTS -InputFile "C:\Books\mybook.epub" -OutputDir "D:\Output" -UseOCR
    Converts an EPUB with OCR enabled, saving to a custom output directory.
.NOTES
    Part of the EbookAutomation module.
#>
```

### Rules:
- Read each function's actual parameters and logic to write accurate help
- Use realistic file paths in examples (`F:\Books\`, `F:\Projects\EbookAutomation\output\`, etc.)
- `.PARAMETER` entries must match actual param names exactly (case-sensitive)
- Don't add `.NOTES` unless there's something genuinely useful to note (e.g., "Requires Calibre installed", "Calls Claude API — incurs costs")
- Do NOT change any function logic, parameter definitions, or behavior
- For functions that already have good help, just verify completeness and add missing `.EXAMPLE` blocks if needed — don't rewrite what's already good

---

## Part 2: Set-EbookDefaults / Get-EbookDefaults Cmdlets

Create two new functions that read/write user preferences to `config\user-defaults.json` (separate from `settings.json`).

### `Get-EbookDefaults`
- Reads `config\user-defaults.json` if it exists
- Returns the parsed object (or a default hashtable if file doesn't exist)
- Default values:
```json
{
    "voice": "Microsoft Steffan Online",
    "speed": 0,
    "volume": 100,
    "input_folder": "inbox",
    "output_folder_tts": "output\\balabolka-txt",
    "output_folder_kindle": "output\\kindle",
    "generate_mp3": false
}
```

### `Set-EbookDefaults`
- Parameters: `-Voice`, `-Speed`, `-Volume`, `-InputFolder`, `-OutputFolderTTS`, `-OutputFolderKindle`, `-GenerateMP3`
- All parameters optional — only updates the ones provided (merge, not overwrite)
- Reads existing defaults, merges new values, writes back to `config\user-defaults.json`
- Uses `Write-EbookLog` for logging
- Full comment-based help on both functions

### Wiring:
- Add both functions to the `Export-ModuleMember` list (currently at line ~4693)
- Add both functions to the `FunctionsToExport` array in `module/EbookAutomation.psd1`
- Place the function definitions BEFORE the `#region -- Module exports` section (before line 4691)
- Support `$env:EBOOK_AUTOMATION_ROOT` override for portability — check at module load time: if this env var is set, use it as project root instead of deriving from `$PSScriptRoot`. Modify the `$script:ModuleRoot` assignment at the top of the file (line ~12) to check for this.

---

## What NOT to Do
- Do NOT modify any existing function logic, parameter definitions, or behavior
- Do NOT restructure the file or move functions around
- Do NOT add new dependencies
- Do NOT modify `settings.json`
- Do NOT modify any Python files — this is PSM1/PSD1 only

---

## Verification

After all changes:
1. Run `python tools/test_pipeline.py --quick` — all tests must pass
2. Verify: `Import-Module .\module\EbookAutomation.psd1 -Force` loads without errors
3. Verify: `Get-Help Convert-ToTTS -Full` produces complete output with DESCRIPTION, PARAMETER, and EXAMPLE sections
4. Verify: `Get-Help Set-EbookDefaults -Full` produces complete output
5. Verify: `Get-Help Get-EbookDefaults -Full` produces complete output
6. Git commit with message: `docs: SCRUM-34 — complete comment-based help on all exported functions + Set/Get-EbookDefaults cmdlets`
7. Git push
8. Transition SCRUM-34 to Done (transition ID 41) via Atlassian MCP
9. Add completion comment to SCRUM-34 listing: number of functions updated, new cmdlets added, and confirmation that Get-Help works
