<#
.SYNOPSIS
    Dry-run-first ebook source migration into F:\Books\_Inbox\Migration.

.DESCRIPTION
    Inventories ebook-like files from current and legacy source roots, stages
    missing files into a migration inbox, and writes an auditable manifest.

    Safety policy:
    - Calibre Library sources are copy-only; originals are never removed.
    - Downloads sources are staged by copy + hash verification, then the source
      file is removed only in -Apply mode.
    - Dry-run is the default and mutates no source or F:\Books path.
    - Reparse-point directories are not traversed.

.EXAMPLE
    .\scripts\Invoke-BookSourceMigration.ps1

.EXAMPLE
    .\scripts\Invoke-BookSourceMigration.ps1 -Apply -RunCategorizationScan
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TargetRoot = "F:\Books",
    [string]$MigrationRoot = "",
    [string]$ReportRoot = "data\batch_reports\book_source_migration",
    [string]$Stamp = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [switch]$Apply,
    [switch]$RunCategorizationScan,
    [switch]$NoDefaultSources,
    [string[]]$AdditionalCopySource = @(),
    [string[]]$AdditionalMoveSource = @(),
    [string[]]$Extensions = @("pdf", "epub", "mobi", "azw", "azw3", "djvu", "fb2", "lit", "rtf", "docx", "cbz", "cbr"),
    [switch]$NoExistingHashScan,
    [int]$Limit = 0,
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Python = "python"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($MigrationRoot)) {
    $MigrationRoot = Join-Path $TargetRoot "_Inbox\Migration"
}

$RunMigrationRoot = Join-Path $MigrationRoot $Stamp

function Resolve-ConfiguredPath {
    param(
        [string]$Base,
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return (Join-Path $Base $Path)
}

$ResolvedReportRoot = Resolve-ConfiguredPath -Base $ProjectRoot -Path $ReportRoot
$RunReportRoot = Join-Path $ResolvedReportRoot $Stamp

function New-SourceSpec {
    param(
        [string]$Name,
        [string]$Path,
        [string]$Kind,
        [ValidateSet("copy", "move")]
        [string]$Policy
    )

    [PSCustomObject]@{
        name = $Name
        path = $Path
        kind = $Kind
        policy = $Policy
    }
}

function Get-SafeName {
    param([string]$Value)

    $safe = $Value -replace '[\\/:*?"<>|]', '_'
    $safe = $safe -replace '\s+', '_'
    $safe = $safe.Trim("._ ")
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "source"
    }
    return $safe
}

function Test-PathWithin {
    param(
        [string]$Path,
        [string]$Root
    )

    try {
        $pathFull = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
        $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    }
    catch {
        return $false
    }

    if ([string]::Equals($pathFull, $rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $rootFull + "\"
    return $pathFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-ReparsePoint {
    param([string]$Path)

    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        return (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
    }
    catch {
        return $true
    }
}

function Get-RelativePathCompat {
    param(
        [string]$Root,
        [string]$Path
    )

    try {
        $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + "\"
        $pathFull = [System.IO.Path]::GetFullPath($Path)
        if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $pathFull.Substring($rootFull.Length)
        }
    }
    catch {
        return (Split-Path -Leaf $Path)
    }
    return (Split-Path -Leaf $Path)
}

function Get-UniqueDestination {
    param(
        [string]$Path,
        [hashtable]$Reserved
    )

    $candidate = $Path
    $dir = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $ext = [System.IO.Path]::GetExtension($leaf)
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($leaf)
    $i = 2
    while ((Test-Path -LiteralPath $candidate) -or $Reserved.ContainsKey($candidate.ToLowerInvariant())) {
        $candidate = Join-Path $dir ("{0} ({1}){2}" -f $stem, $i, $ext)
        $i += 1
    }
    $Reserved[$candidate.ToLowerInvariant()] = $true
    return $candidate
}

function Get-BookFilesSafe {
    param(
        [string]$Root,
        [hashtable]$ExtensionLookup,
        [System.Collections.ArrayList]$Notes
    )

    $results = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $Root)) {
        [void]$Notes.Add("source unavailable: $Root")
        return @()
    }
    if (Test-ReparsePoint -Path $Root) {
        [void]$Notes.Add("source skipped, reparse point: $Root")
        return @()
    }

    $stack = New-Object System.Collections.Stack
    $stack.Push($Root)

    while ($stack.Count -gt 0) {
        $dir = [string]$stack.Pop()
        if (Test-ReparsePoint -Path $dir) {
            [void]$Notes.Add("directory skipped, reparse point: $dir")
            continue
        }

        try {
            $entries = Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop
        }
        catch {
            [void]$Notes.Add("directory skipped, cannot enumerate: $dir :: $($_.Exception.Message)")
            continue
        }

        foreach ($entry in $entries) {
            if ($entry.PSIsContainer) {
                if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    [void]$Notes.Add("directory skipped, reparse point: $($entry.FullName)")
                    continue
                }
                $stack.Push($entry.FullName)
                continue
            }

            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                [void]$Notes.Add("file skipped, reparse point: $($entry.FullName)")
                continue
            }

            $ext = $entry.Extension.TrimStart(".").ToLowerInvariant()
            if ($ExtensionLookup.ContainsKey($ext)) {
                [void]$results.Add($entry)
            }
        }
    }

    return @($results | Sort-Object FullName)
}

function Get-Sha256 {
    param([string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Add-KnownHash {
    param(
        [hashtable]$KnownHashes,
        [string]$Hash,
        [string]$Path
    )

    if (-not $KnownHashes.ContainsKey($Hash)) {
        $KnownHashes[$Hash] = $Path
    }
}

function Add-DefaultSources {
    param([System.Collections.ArrayList]$Sources)

    if ($env:USERPROFILE) {
        [void]$Sources.Add((New-SourceSpec -Name "current-downloads" -Path (Join-Path $env:USERPROFILE "Downloads") -Kind "downloads" -Policy "move"))
        [void]$Sources.Add((New-SourceSpec -Name "current-calibre-default" -Path (Join-Path $env:USERPROFILE "Calibre Library") -Kind "calibre" -Policy "copy"))
    }

    $settingsPath = Join-Path $ProjectRoot "config\settings.json"
    if (Test-Path -LiteralPath $settingsPath) {
        try {
            $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
            if ($settings.library.calibre_library) {
                [void]$Sources.Add((New-SourceSpec -Name "current-calibre-configured" -Path ([string]$settings.library.calibre_library) -Kind "calibre" -Policy "copy"))
            }
        }
        catch {
            # The migration can still run from explicit/default roots without config.
        }
    }

    [void]$Sources.Add((New-SourceSpec -Name "old-desktop-downloads-users-share" -Path "\\DESKTOP-488UQB2\Users\Joe\Downloads" -Kind "downloads" -Policy "move"))
    [void]$Sources.Add((New-SourceSpec -Name "old-desktop-calibre-users-share" -Path "\\DESKTOP-488UQB2\Users\Joe\Calibre Library" -Kind "calibre" -Policy "copy"))
    [void]$Sources.Add((New-SourceSpec -Name "old-desktop-downloads-admin-share" -Path "\\DESKTOP-488UQB2\C$\Users\Joe\Downloads" -Kind "downloads" -Policy "move"))
    [void]$Sources.Add((New-SourceSpec -Name "old-desktop-calibre-admin-share" -Path "\\DESKTOP-488UQB2\C$\Users\Joe\Calibre Library" -Kind "calibre" -Policy "copy"))
}

New-Item -ItemType Directory -Force -Path $RunReportRoot | Out-Null

$extensionLookup = @{}
foreach ($ext in $Extensions) {
    $clean = $ext.TrimStart(".").ToLowerInvariant()
    if ($clean) {
        $extensionLookup[$clean] = $true
    }
}

$sources = New-Object System.Collections.ArrayList
if (-not $NoDefaultSources) {
    Add-DefaultSources -Sources $sources
}

$manualIndex = 1
foreach ($src in $AdditionalCopySource) {
    [void]$sources.Add((New-SourceSpec -Name ("manual-copy-{0}" -f $manualIndex) -Path $src -Kind "manual-copy" -Policy "copy"))
    $manualIndex += 1
}
$manualIndex = 1
foreach ($src in $AdditionalMoveSource) {
    [void]$sources.Add((New-SourceSpec -Name ("manual-move-{0}" -f $manualIndex) -Path $src -Kind "manual-move" -Policy "move"))
    $manualIndex += 1
}

$dedupedSources = New-Object System.Collections.ArrayList
$seenSources = @{}
foreach ($src in $sources) {
    $key = ("{0}|{1}" -f $src.path, $src.policy).ToLowerInvariant()
    if (-not $seenSources.ContainsKey($key)) {
        $seenSources[$key] = $true
        [void]$dedupedSources.Add($src)
    }
}
$sources = $dedupedSources

$notes = New-Object System.Collections.ArrayList
$knownHashes = @{}
$reservedDestinations = @{}

if (-not $NoExistingHashScan -and (Test-Path -LiteralPath $TargetRoot)) {
    $existingFiles = Get-BookFilesSafe -Root $TargetRoot -ExtensionLookup $extensionLookup -Notes $notes
    foreach ($file in $existingFiles) {
        try {
            Add-KnownHash -KnownHashes $knownHashes -Hash (Get-Sha256 -Path $file.FullName) -Path $file.FullName
        }
        catch {
            [void]$notes.Add("existing file hash skipped: $($file.FullName) :: $($_.Exception.Message)")
        }
    }
}

$sourceRootRows = New-Object System.Collections.ArrayList
$manifestRows = New-Object System.Collections.ArrayList
$processedCandidates = 0
$stagedCount = 0
$sourceRemovedCount = 0
$scanStatus = "not requested"

foreach ($source in $sources) {
    $exists = Test-Path -LiteralPath $source.path
    $sourceBlockedReason = ""

    if ($exists -and (Test-PathWithin -Path $source.path -Root $RunMigrationRoot)) {
        $exists = $false
        $sourceBlockedReason = "source is inside this migration run root"
    }
    elseif ($exists -and (Test-PathWithin -Path $source.path -Root $TargetRoot) -and
        -not (Test-PathWithin -Path $source.path -Root $MigrationRoot)) {
        $exists = $false
        $sourceBlockedReason = "source is inside target library root; refusing to ingest target as a source"
    }

    [void]$sourceRootRows.Add([PSCustomObject]@{
        name = $source.name
        path = $source.path
        kind = $source.kind
        policy = $source.policy
        exists = [bool]$exists
        blocked_reason = $sourceBlockedReason
    })

    if (-not $exists) {
        if ($sourceBlockedReason) {
            [void]$notes.Add("source blocked: $($source.path) :: $sourceBlockedReason")
        }
        else {
            [void]$notes.Add("source unavailable: $($source.path)")
        }
        continue
    }

    $files = Get-BookFilesSafe -Root $source.path -ExtensionLookup $extensionLookup -Notes $notes
    foreach ($file in $files) {
        if ($Limit -gt 0 -and $processedCandidates -ge $Limit) {
            break
        }
        $processedCandidates += 1

        $rowTime = (Get-Date).ToString("o")
        $rel = Get-RelativePathCompat -Root $source.path -Path $file.FullName
        $sha = ""
        $action = ""
        $dest = ""
        $executed = $false
        $sourceRemoved = $false
        $reason = ""

        if ($file.Length -eq 0) {
            $action = "skip-zero-byte"
            $reason = "zero-byte file"
        }
        else {
            try {
                $sha = Get-Sha256 -Path $file.FullName
            }
            catch {
                $action = "skip-hash-error"
                $reason = $_.Exception.Message
            }
        }

        if ($sha -and $knownHashes.ContainsKey($sha)) {
            $action = "skip-existing-hash"
            $reason = "matching sha256 already known at $($knownHashes[$sha])"
        }
        elseif ($sha) {
            $sourceSafe = Get-SafeName -Value $source.name
            $plannedDest = Join-Path (Join-Path $RunMigrationRoot $sourceSafe) $rel
            if (-not (Test-PathWithin -Path $plannedDest -Root $RunMigrationRoot)) {
                $action = "skip-unsafe-destination"
                $reason = "planned destination escapes migration run root"
            }
            else {
                $dest = Get-UniqueDestination -Path $plannedDest -Reserved $reservedDestinations
                $action = if ($source.policy -eq "move") { "stage-move" } else { "stage-copy" }
                $reason = if ($Apply) { "pending apply" } else { "dry-run only" }

                if ($Apply) {
                    if ($PSCmdlet.ShouldProcess($file.FullName, "$action to $dest")) {
                        try {
                            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
                            Copy-Item -LiteralPath $file.FullName -Destination $dest -ErrorAction Stop
                            $destHash = Get-Sha256 -Path $dest
                            if ($destHash -ne $sha) {
                                throw "staged copy hash mismatch: $destHash != $sha"
                            }
                            $executed = $true
                            $stagedCount += 1
                            Add-KnownHash -KnownHashes $knownHashes -Hash $sha -Path $dest
                            $reason = "staged and hash-verified"

                            if ($source.policy -eq "move") {
                                Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                                $sourceRemoved = $true
                                $sourceRemovedCount += 1
                                $reason = "staged, hash-verified, source removed per downloads policy"
                            }
                        }
                        catch {
                            $reason = "apply failed: $($_.Exception.Message)"
                        }
                    }
                    else {
                        $reason = "WhatIf/ShouldProcess declined"
                    }
                }
                else {
                    Add-KnownHash -KnownHashes $knownHashes -Hash $sha -Path $dest
                }
            }
        }

        [void]$manifestRows.Add([PSCustomObject]@{
            stamp = $Stamp
            source_name = $source.name
            source_kind = $source.kind
            source_policy = $source.policy
            source_path = $file.FullName
            relative_path = $rel
            extension = $file.Extension.TrimStart(".").ToLowerInvariant()
            size = [int64]$file.Length
            sha256 = $sha
            planned_action = $action
            destination_path = $dest
            apply = [bool]$Apply
            executed = [bool]$executed
            source_removed = [bool]$sourceRemoved
            reason = $reason
            timestamp = $rowTime
        })
    }
}

$manifestJsonl = Join-Path $RunReportRoot "migration-manifest.jsonl"
$manifestCsv = Join-Path $RunReportRoot "migration-manifest.csv"
$sourceRootsJson = Join-Path $RunReportRoot "source-roots.json"
$summaryPath = Join-Path $RunReportRoot "summary.md"
$reviewBriefPath = Join-Path $RunReportRoot "claude-review-brief.md"

$manifestRows |
    ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 } |
    Set-Content -LiteralPath $manifestJsonl -Encoding UTF8
$manifestRows | Export-Csv -LiteralPath $manifestCsv -NoTypeInformation -Encoding UTF8
$sourceRootRows | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $sourceRootsJson -Encoding UTF8

if ($RunCategorizationScan) {
    if (-not $Apply) {
        $scanStatus = "skipped: categorization scan requires -Apply because dry-run creates no staging tree"
    }
    elseif ($stagedCount -eq 0) {
        $scanStatus = "skipped: no files staged"
    }
    else {
        $scanOut = Join-Path $RunReportRoot "book_filer_scan"
        $scanScript = Join-Path $ProjectRoot "tools\book_filer\scan.py"
        $oldSeed = $env:PYTHONHASHSEED
        $env:PYTHONHASHSEED = "0"
        try {
            $scanOutput = & $Python $scanScript --root $RunMigrationRoot --out-dir $scanOut --stamp $Stamp --force 2>&1
            $scanExit = $LASTEXITCODE
            $scanOutput | Set-Content -LiteralPath (Join-Path $RunReportRoot "book_filer_scan.log") -Encoding UTF8
            $scanStatus = "exit $scanExit; artifacts: $scanOut"
        }
        finally {
            $env:PYTHONHASHSEED = $oldSeed
        }
    }
}

$actionCounts = @{}
foreach ($row in $manifestRows) {
    if (-not $actionCounts.ContainsKey($row.planned_action)) {
        $actionCounts[$row.planned_action] = 0
    }
    $actionCounts[$row.planned_action] += 1
}

$summary = New-Object System.Collections.ArrayList
[void]$summary.Add("# Book Source Migration - $Stamp")
[void]$summary.Add("")
[void]$summary.Add("Mode: " + $(if ($Apply) { "apply" } else { "dry-run" }))
[void]$summary.Add("Target root: $TargetRoot")
[void]$summary.Add("Migration run root: $RunMigrationRoot")
[void]$summary.Add("Report root: $RunReportRoot")
[void]$summary.Add("")
[void]$summary.Add("## Counts")
[void]$summary.Add("")
[void]$summary.Add("- Source roots checked: $($sourceRootRows.Count)")
[void]$summary.Add("- Candidate files processed: $processedCandidates")
[void]$summary.Add("- Rows written: $($manifestRows.Count)")
[void]$summary.Add("- Files staged: $stagedCount")
[void]$summary.Add("- Download-source files removed: $sourceRemovedCount")
[void]$summary.Add("- Categorization scan: $scanStatus")
[void]$summary.Add("")
[void]$summary.Add("## Action Breakdown")
[void]$summary.Add("")
foreach ($key in ($actionCounts.Keys | Sort-Object)) {
    [void]$summary.Add("- ${key}: $($actionCounts[$key])")
}
[void]$summary.Add("")
[void]$summary.Add("## Source Roots")
[void]$summary.Add("")
foreach ($src in $sourceRootRows) {
    $status = if ($src.exists) { "available" } else { "unavailable" }
    if ($src.blocked_reason) {
        $status = "blocked: $($src.blocked_reason)"
    }
    [void]$summary.Add("- $($src.name) [$($src.policy)]: $status - $($src.path)")
}
if ($notes.Count -gt 0) {
    [void]$summary.Add("")
    [void]$summary.Add("## Notes")
    [void]$summary.Add("")
    foreach ($note in ($notes | Select-Object -First 100)) {
        [void]$summary.Add("- $note")
    }
    if ($notes.Count -gt 100) {
        [void]$summary.Add("- ... and $($notes.Count - 100) more")
    }
}
$summary | Set-Content -LiteralPath $summaryPath -Encoding UTF8

$reviewBrief = @(
    "# Claude Code Review Brief - Book Source Migration",
    "",
    "Jira: EB-379",
    "",
    "Review artifacts:",
    "- Source roots: $sourceRootsJson",
    "- Manifest JSONL: $manifestJsonl",
    "- Manifest CSV: $manifestCsv",
    "- Summary: $summaryPath",
    "",
    "Review focus:",
    "- Confirm no Calibre policy path removes the source file.",
    "- Confirm Downloads policy removes a source only after staged-copy hash verification.",
    "- Confirm dry-run has no source or F:\Books mutation path.",
    "- Confirm source roots inside the target library are blocked.",
    "- Confirm unreachable DESKTOP-488UQB2 paths are reported rather than guessed.",
    "- Confirm categorization is a separate book_filer scan artifact, not an unreviewed shelf move."
)
$reviewBrief | Set-Content -LiteralPath $reviewBriefPath -Encoding UTF8

Write-Host "Book source migration $($(if ($Apply) { 'apply' } else { 'dry-run' })) complete."
Write-Host "Rows: $($manifestRows.Count); staged: $stagedCount; removed from downloads sources: $sourceRemovedCount"
Write-Host "Report: $summaryPath"

if ($Apply -and $RunCategorizationScan) {
    Write-Host "Categorization scan: $scanStatus"
}
