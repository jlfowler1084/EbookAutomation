# Agent Framework: Structure Analysis Agent — Externalize Prompt

## Session Name
Agent Framework Setup

## Overview
Create the `agents/` directory structure and refactor `Get-ChapterStructure` to load its system prompt from an external file instead of having it hardcoded inline. Also add a convenience wrapper `Invoke-StructureAgent` for manual/diagnostic use.

## Claude Code Model
Sonnet — this is straightforward file creation + function refactoring with no architectural ambiguity.

## Steps

### 1. Create directory structure

Create these directories and files:
```
F:\Projects\EbookAutomation\agents\
F:\Projects\EbookAutomation\agents\structure-analysis\
F:\Projects\EbookAutomation\agents\structure-analysis\examples\
```

### 2. Copy agent files into place

Copy the following files from `prompts/` into the agents directory:
- `agents/README.md` — framework overview
- `agents/structure-analysis/system-prompt.md` — the agent's system prompt
- `agents/structure-analysis/contract.md` — input/output contract

The contents of these three files are provided below in the AGENT FILES section.

### 3. Refactor Get-ChapterStructure to load external prompt

In `module/EbookAutomation.psm1`, find the `Get-ChapterStructure` function. Replace the inline `$systemPrompt = @"..."@` here-string with code that loads the prompt from file:

```powershell
# -- Step 3: Build Claude prompt (load from agent file)
$agentPromptFile = Join-Path $script:ModuleRoot 'agents\structure-analysis\system-prompt.md'
if (Test-Path $agentPromptFile) {
    $systemPrompt = Get-Content $agentPromptFile -Raw -Encoding UTF8
    Write-EbookLog "Chapter detection: loaded agent prompt from $agentPromptFile"
} else {
    Write-EbookLog "Chapter detection: agent prompt file not found at $agentPromptFile -- using inline fallback" -Level WARN
    $systemPrompt = @"
You are analyzing an ebook to build its table of contents. Identify the CHAPTER STRUCTURE.
Respond with a raw JSON array. Each entry: {"title": "...", "level": 1, "is_back_matter": false, "page_estimate": 0, "confidence": 0.9, "notes": ""}
level 1 = Part/Book/Volume, level 2 = Chapter, level 3 = Sub-section.
"@
}
```

**Important:** Keep a minimal inline fallback so the function still works if the file is missing. The fallback should be bare-bones — just enough to get a valid response. The full, high-quality prompt lives in the file.

### 4. Add Invoke-StructureAgent wrapper function

Add this new function to `module/EbookAutomation.psm1` (in the Claude API region, after `Get-ChapterStructure`):

```powershell
function Invoke-StructureAgent {
    <#
    .SYNOPSIS  Run the Structure Analysis Agent standalone for diagnostics.
    .DESCRIPTION
        Convenience wrapper for testing chapter detection on a single file
        without running the full conversion pipeline. Loads the agent prompt
        from agents/structure-analysis/system-prompt.md, runs font-based
        detection + Claude API analysis, and outputs results to console and
        optionally to a JSON file.
    .PARAMETER InputFile
        Path to the source PDF or EPUB file.
    .PARAMETER OutputJson
        Optional path to write the chapter map JSON. If omitted, results are
        displayed to console only.
    .PARAMETER Model
        Claude model to use. Defaults to claude-sonnet-4-6. Use claude-opus-4-6
        for complex books.
    .EXAMPLE
        Invoke-StructureAgent -InputFile "C:\Books\MyBook.pdf"
    .EXAMPLE
        Invoke-StructureAgent -InputFile "C:\Books\MyBook.pdf" -OutputJson "chapters.json" -Model claude-opus-4-6
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$InputFile,
        [string]$OutputJson,
        [string]$Model = 'claude-sonnet-4-6'
    )

    if (-not (Test-Path $InputFile)) {
        Write-EbookLog "Structure Agent: file not found -- $InputFile" -Level ERROR
        return $null
    }

    Write-EbookLog "=========================================="
    Write-EbookLog "Structure Analysis Agent — Standalone Run"
    Write-EbookLog "  Input:  $InputFile"
    Write-EbookLog "  Model:  $Model"
    Write-EbookLog "=========================================="

    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    # Extract text for analysis
    $cfg    = Get-EbookConfig
    $python = $cfg.paths.python
    $ext    = [System.IO.Path]::GetExtension($InputFile).TrimStart('.').ToLower()

    # Use pypdf for quick raw text extraction
    $tempText = Join-Path $env:TEMP ('struct_agent_{0}.txt' -f [System.IO.Path]::GetRandomFileName())
    $extractCmd = @"
from pypdf import PdfReader
import sys
try:
    r = PdfReader(r'$InputFile')
    text = '\n'.join(p.extract_text() or '' for p in r.pages)
    with open(r'$tempText', 'w', encoding='utf-8') as f:
        f.write(text)
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"@
    & $python -c $extractCmd 2>$null

    if (-not (Test-Path $tempText)) {
        Write-EbookLog "Structure Agent: text extraction failed" -Level ERROR
        return $null
    }

    $textContent = Get-Content $tempText -Raw -Encoding UTF8
    Remove-Item $tempText -Force -ErrorAction SilentlyContinue
    $wordCount = ($textContent -split '\s+').Count
    Write-EbookLog "Structure Agent: extracted $wordCount words from source"

    # Run chapter detection (reuses existing Get-ChapterStructure)
    $chapters = Get-ChapterStructure -TextContent $textContent -InputFile $InputFile

    $sw.Stop()
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)

    if ($chapters -and $chapters.Count -gt 0) {
        Write-EbookLog "Structure Agent: detected $($chapters.Count) headings in ${elapsed}s" -Level SUCCESS

        # Display results
        Write-Host "`n--- Chapter Map ---" -ForegroundColor Cyan
        foreach ($ch in $chapters) {
            $indent = '  ' * ($ch.level - 1)
            $bm = if ($ch.is_back_matter) { ' [back matter]' } else { '' }
            $conf = if ($ch.confidence) { " ($([math]::Round($ch.confidence * 100))%)" } else { '' }
            Write-Host "  ${indent}L$($ch.level)  $($ch.title)${bm}${conf}" -ForegroundColor White
        }
        Write-Host ""

        # Write JSON if requested
        if ($OutputJson) {
            $chapters | ConvertTo-Json -Depth 4 | Set-Content $OutputJson -Encoding UTF8
            Write-EbookLog "Structure Agent: chapter map written to $OutputJson"
        }
    } else {
        Write-EbookLog "Structure Agent: no chapters detected (${elapsed}s)" -Level WARN
    }

    return $chapters
}
```

### 5. Export the new function

Add `'Invoke-StructureAgent'` to both:
- The `Export-ModuleMember -Function @(...)` call at the bottom of `EbookAutomation.psm1`
- The `FunctionsToExport` array in `EbookAutomation.psd1`

### 6. Update CLAUDE.md

Add `Invoke-StructureAgent` to the Exported Functions table in `CLAUDE.md`:

```
| `Invoke-StructureAgent` | Standalone Structure Analysis Agent for chapter detection diagnostics |
```

Also add a new section to CLAUDE.md:

```markdown
---

## Agent Framework

Agent system prompts live in `agents/<agent-name>/system-prompt.md`. Each agent also has a `contract.md` defining its input/output interface. See `agents/README.md` for the full framework documentation.

| Agent | Directory | Called By | Purpose |
|-------|-----------|-----------|---------|
| Structure Analysis | `agents/structure-analysis/` | `Get-ChapterStructure`, `Invoke-StructureAgent` | Chapter/heading detection from book text |
```

### 7. Git commit and push

```
git add agents/ module/EbookAutomation.psm1 module/EbookAutomation.psd1 CLAUDE.md
git commit -m "feat: agent framework with Structure Analysis Agent

- New agents/ directory with README, system-prompt.md, contract.md
- Get-ChapterStructure now loads prompt from external file
- New Invoke-StructureAgent for standalone diagnostics
- Agent framework docs: design principles, directory structure, adding new agents
- CLAUDE.md updated with agent framework section"
git push
```

---

## AGENT FILES

### agents/README.md

(Copy from: prompts/agent-framework-setup.md — Section provided separately via Claude.ai project download)

### agents/structure-analysis/system-prompt.md

(Copy from: prompts/agent-framework-setup.md — Section provided separately via Claude.ai project download)

### agents/structure-analysis/contract.md

(Copy from: prompts/agent-framework-setup.md — Section provided separately via Claude.ai project download)

**Note:** All three files are provided as downloads from the Claude.ai conversation where this prompt was generated. Copy them into `agents/` before running the refactoring steps.
