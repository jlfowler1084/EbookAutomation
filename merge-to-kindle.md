# EB-76 — Merge-ToKindle: Multi-File Merge + KFX Conversion

## Session Name
Merge-ToKindle

## Claude Code Model
Sonnet — this is straightforward function wiring following existing patterns.

## Context
The EbookAutomation module at `F:\Projects\EbookAutomation\` converts ebooks to Kindle KFX format. Currently there is no way to merge multiple files (e.g., a series of Obsidian Markdown notes) into a single KFX book. Users must manually concatenate files in Obsidian before converting. We need a new `Merge-ToKindle` exported function that concatenates multiple input files and feeds the result to the existing `Convert-ToKindle` pipeline.

## What NOT to Change
- Do NOT modify `Convert-ToKindle` internals — `Merge-ToKindle` calls it as-is
- Do NOT restructure `settings.json`
- Do NOT modify any Python files — this is a PowerShell-only change
- Do NOT remove or reorder existing functions in the `.psm1`
- Do NOT change the existing `.psd1` exports — only ADD the new entry

## Phase 1 — Diagnosis (MANDATORY)
Before writing any code:
1. Read `module/EbookAutomation.psm1` — locate the `Convert-ToKindle` function signature and understand its parameters (especially `-InputFile`, `-OutputDir`, `-UseHtmlExtraction`)
2. Read `module/EbookAutomation.psd1` — confirm current exports list
3. Search for any existing merge/concatenation logic in the module
4. Report findings before proceeding

## Phase 2 — Implementation

### 2a. Add `Merge-ToKindle` function to `EbookAutomation.psm1`

Insert a new `#region -- Merge to Kindle` block **immediately before** the `#region -- Send to Kindle Device` section.

Function signature and behavior:

```powershell
function Merge-ToKindle {
    <#
    .SYNOPSIS
        Merge multiple files into a single Kindle KFX book.
    .DESCRIPTION
        Accepts multiple input files (Markdown, TXT, HTML, or any Calibre-supported
        format), concatenates them in natural sort order with section headings derived
        from filenames, and converts the merged result to KFX via Convert-ToKindle.

        Wildcard/glob patterns are supported in -InputFiles.

        Each source file becomes a top-level chapter (# heading) in the merged
        document. Existing headings within each file are demoted one level
        (# → ##, ## → ###) to preserve hierarchy under the file-level chapter.
    .PARAMETER InputFiles
        One or more file paths or wildcard patterns. Resolved files are sorted
        using natural (alphanumeric) ordering so "01_Intro" comes before "02_Core"
        and "10_Appendix".
    .PARAMETER Title
        Book title for KFX metadata. If omitted, derived from the common prefix
        of the input filenames.
    .PARAMETER Author
        Author name for KFX metadata.
    .PARAMETER OutputDir
        Folder for the output KFX file. Defaults to output\kindle from settings.json.
    .PARAMETER UseHtmlExtraction
        Pass through to Convert-ToKindle for any PDF inputs in the merge set.
    .PARAMETER KeepMergedFile
        Do not delete the intermediate merged Markdown file after conversion.
        Useful for debugging.
    .EXAMPLE
        Merge-ToKindle -InputFiles "F:\notes\Miso_Interview_Prep_*.md" -Title "Miso Interview Prep"
    .EXAMPLE
        Merge-ToKindle -InputFiles @("01_STAR.md","02_Hands_On.md","03_Knowledge.md") -Title "Interview Prep" -Author "Joe"
    .EXAMPLE
        Get-ChildItem .\notes\*.md | Merge-ToKindle -Title "Combined Notes"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline, ValueFromPipelineByPropertyName, Position = 0)]
        [Alias('Path','FullName')]
        [string[]]$InputFiles,

        [string]$Title,
        [string]$Author,
        [string]$OutputDir,
        [switch]$UseHtmlExtraction,
        [switch]$KeepMergedFile
    )

    begin {
        $collectedFiles = [System.Collections.Generic.List[string]]::new()
    }

    process {
        # Accumulate from pipeline and parameter
        foreach ($pattern in $InputFiles) {
            $resolved = Resolve-Path $pattern -ErrorAction SilentlyContinue
            if ($resolved) {
                foreach ($r in $resolved) {
                    $collectedFiles.Add($r.Path)
                }
            } else {
                Write-EbookLog "Merge: pattern resolved no files: $pattern" -Level WARN
            }
        }
    }

    end {
        if ($collectedFiles.Count -eq 0) {
            Write-EbookLog "Merge: no input files found" -Level ERROR
            return $false
        }

        if ($collectedFiles.Count -eq 1) {
            Write-EbookLog "Merge: only 1 file found — passing directly to Convert-ToKindle"
            $convertParams = @{ InputFile = $collectedFiles[0] }
            if ($OutputDir)           { $convertParams.OutputDir          = $OutputDir }
            if ($UseHtmlExtraction)   { $convertParams.UseHtmlExtraction  = $true }
            return Convert-ToKindle @convertParams
        }

        # ── Natural sort ──
        # Sort so that numeric prefixes are ordered numerically:
        # 01_Foo, 02_Bar, 10_Baz (not 01, 10, 02 as lexicographic would give)
        $sorted = $collectedFiles | Sort-Object {
            # Pad all digit runs to 20 chars for natural ordering
            [regex]::Replace($_, '\d+', { param($m) $m.Value.PadLeft(20, '0') })
        }

        Write-EbookLog "Merge: $($sorted.Count) files to merge (natural sort order):"
        foreach ($f in $sorted) {
            Write-EbookLog "  - $(Split-Path $f -Leaf)"
        }

        # ── Derive title from common filename prefix if not provided ──
        if (-not $Title) {
            $names = $sorted | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_) }
            # Find longest common prefix
            $prefix = $names[0]
            foreach ($name in $names[1..($names.Count - 1)]) {
                while ($name.Length -lt $prefix.Length -or
                       $name.Substring(0, [Math]::Min($prefix.Length, $name.Length)) -ne $prefix.Substring(0, [Math]::Min($prefix.Length, $name.Length))) {
                    $prefix = $prefix.Substring(0, $prefix.Length - 1)
                    if ($prefix.Length -eq 0) { break }
                }
            }
            # Clean up trailing separators
            $Title = ($prefix -replace '[_\-\s]+$', '').Trim()
            if (-not $Title) { $Title = 'Merged Document' }
            # Convert underscores to spaces for readability
            $Title = $Title -replace '_', ' '
            Write-EbookLog "Merge: auto-derived title: $Title"
        }

        # ── Build merged Markdown ──
        $cfg = Get-EbookConfig
        $processingDir = Resolve-ProjectPath $cfg.paths.processing
        if (-not (Test-Path $processingDir)) {
            New-Item $processingDir -ItemType Directory -Force | Out-Null
        }

        $safeName = ($Title -replace '[^\w\-]', '_')
        $mergedFile = Join-Path $processingDir "${safeName}_merged.md"

        Write-EbookLog "Merge: building merged document..."
        $sb = [System.Text.StringBuilder]::new()

        # Add title as document heading
        [void]$sb.AppendLine("# $Title")
        [void]$sb.AppendLine()

        foreach ($filePath in $sorted) {
            $fileName = [IO.Path]::GetFileNameWithoutExtension($filePath)
            $ext = [IO.Path]::GetExtension($filePath).ToLower()

            # Derive section title: strip numeric prefixes and clean up
            $sectionTitle = $fileName -replace '^\d+[\._\-\s]*', ''
            $sectionTitle = $sectionTitle -replace '_', ' '
            if (-not $sectionTitle) { $sectionTitle = $fileName }

            Write-EbookLog "Merge: appending $fileName as section '$sectionTitle'"

            # Section heading
            [void]$sb.AppendLine("## $sectionTitle")
            [void]$sb.AppendLine()

            # Read file content
            $content = Get-Content $filePath -Raw -Encoding UTF8 -ErrorAction Stop

            # Demote existing Markdown headings by one level (# → ##, ## → ###, etc.)
            # Process line by line to only match headings at start of line
            $lines = $content -split "`r?`n"
            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i] -match '^(#{1,5})\s') {
                    $lines[$i] = '#' + $lines[$i]
                }
            }
            $content = $lines -join "`r`n"

            [void]$sb.AppendLine($content)
            [void]$sb.AppendLine()
            [void]$sb.AppendLine('---')
            [void]$sb.AppendLine()
        }

        # Write merged file
        Set-Content $mergedFile -Value $sb.ToString() -Encoding UTF8 -NoNewline
        $mergedMB = [math]::Round((Get-Item $mergedFile).Length / 1MB, 2)
        Write-EbookLog "Merge: merged document written -> $mergedFile ($mergedMB MB)" -Level SUCCESS

        # ── Convert via existing pipeline ──
        $convertParams = @{ InputFile = $mergedFile }
        if ($OutputDir) {
            $convertParams.OutputDir = $OutputDir
        }
        if ($UseHtmlExtraction) {
            $convertParams.UseHtmlExtraction = $true
        }

        # Override metadata since Convert-ToKindle would parse the temp filename
        # We need to inject title/author — Convert-ToKindle reads Get-EbookMetadataFromFilename
        # but for a merged file the filename won't parse well.
        # Solution: rename the merged file to encode metadata for the parser.
        if ($Author) {
            $metaName = "${safeName} - ${Author}_merged.md"
        } else {
            $metaName = "${safeName}_merged.md"
        }
        $metaPath = Join-Path $processingDir $metaName
        if ($metaPath -ne $mergedFile) {
            Rename-Item $mergedFile $metaPath -Force -ErrorAction SilentlyContinue
            $mergedFile = $metaPath
            $convertParams.InputFile = $mergedFile
        }

        Write-EbookLog "Merge: handing off to Convert-ToKindle..."
        $result = Convert-ToKindle @convertParams

        # ── Cleanup ──
        if (-not $KeepMergedFile -and (Test-Path $mergedFile)) {
            Remove-Item $mergedFile -Force -ErrorAction SilentlyContinue
            Write-EbookLog "Merge: cleaned up intermediate file"
        } elseif ($KeepMergedFile) {
            Write-EbookLog "Merge: intermediate file kept at $mergedFile"
        }

        return $result
    }
}
```

**Key design decisions to follow:**
- Use `begin/process/end` pattern so it works with pipeline input (`Get-ChildItem *.md | Merge-ToKindle`)
- Natural sort via regex digit-padding (same technique used in batch_qa.py)
- Demote headings by prepending `#` only to lines starting with `#` followed by a space
- Add `---` (horizontal rule) between sections as visual separator
- Auto-derive title from common filename prefix when `-Title` not provided
- Encode metadata into the temp filename so `Get-EbookMetadataFromFilename` picks it up
- Single-file passthrough (no merge overhead if only 1 file resolves)

### 2b. Export in `EbookAutomation.psd1`

Add `'Merge-ToKindle'` to the `FunctionsToExport` array. Place it after `'Convert-ToKindle'` to keep related functions grouped.

### 2c. Add to `Invoke-EbookPipeline` awareness (informational only)

Do NOT wire `Merge-ToKindle` into `Invoke-EbookPipeline` — it is a standalone command, not part of the inbox scan loop. But add a brief comment near the `Convert-ToKindle` call in the pipeline noting that `Merge-ToKindle` exists for multi-file scenarios.

## Phase 3 — Verification

1. **Syntax check:** `Import-Module "F:\Projects\EbookAutomation\module\EbookAutomation.psd1" -Force` must succeed without errors
2. **Help check:** `Get-Help Merge-ToKindle -Full` must display all parameter documentation
3. **Export check:** `Get-Command -Module EbookAutomation | Select-Object Name` must include `Merge-ToKindle`
4. **Dry test with 2+ small .md files:** Create two test markdown files in processing\, run `Merge-ToKindle -InputFiles "processing\test_*.md" -Title "Test Merge" -KeepMergedFile`, and verify:
   - The merged file is created with correct heading hierarchy
   - Each file appears as a `## Section` under the `# Title`
   - Existing `#` headings in source files are demoted to `##`
   - Natural sort ordering is correct (file_01 before file_02 before file_10)
5. **Report:** exact line count of merged file, section headings found, any errors

## Commit
```
feat: EB-76 — Merge-ToKindle multi-file merge + KFX conversion
```
