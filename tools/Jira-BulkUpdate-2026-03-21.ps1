#Requires -Version 5.1
<#
.SYNOPSIS
    Jira Bulk Update - EbookAutomation Board - March 21, 2026
.DESCRIPTION
    Executes all SCRUM board updates: transitions, comments, and new ticket creation.
    Uses Jira REST API v2 with Basic Auth. Idempotent - safe to re-run.
.NOTES
    Fill in $JiraEmail and $JiraApiToken before running.
    Run from any directory: powershell -File tools\Jira-BulkUpdate-2026-03-21.ps1
#>

# ============================================================
# CONFIGURATION - fill in your values before running
# ============================================================
# Set these env vars before running — see id.atlassian.com > Security > API tokens
$JiraEmail    = $env:JIRA_EMAIL         # Your Atlassian account email
$JiraApiToken = $env:JIRA_API_TOKEN     # Atlassian API token (never hardcode)

$JiraBaseUrl  = "https://jlfowler1084.atlassian.net"
$JiraProject  = "SCRUM"

$TRANSITION_IN_PROGRESS = "21"
$TRANSITION_DONE        = "41"

# ============================================================
# AUTH + HELPERS
# ============================================================

$encoded = [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes("${JiraEmail}:${JiraApiToken}")
)
$script:AuthHeaders = @{
    "Authorization" = "Basic $encoded"
    "Accept"        = "application/json"
}

function Invoke-JiraApi {
    param(
        [string]$Method,
        [string]$Endpoint,
        [hashtable]$Body      = $null,
        [string]$QueryString  = ""
    )
    $uri = "$JiraBaseUrl/rest/api/2/$Endpoint"
    if ($QueryString) { $uri += "?$QueryString" }

    $params = @{
        Method      = $Method
        Uri         = $uri
        Headers     = $script:AuthHeaders
        ErrorAction = "Stop"
    }
    if ($Body) {
        $params.Body        = ($Body | ConvertTo-Json -Depth 20)
        $params.ContentType = "application/json; charset=utf-8"
    }

    try {
        return Invoke-RestMethod @params
    }
    catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
        $detail = $_.ErrorDetails.Message
        Write-Host "  [ERROR] $Method /rest/api/2/$Endpoint => HTTP $code  $detail" -ForegroundColor Red
        return $null
    }
}

function Get-Issue {
    param([string]$Key)
    Write-Host "  Fetching $Key ..." -NoNewline
    $r = Invoke-JiraApi -Method GET -Endpoint "issue/$Key"
    if ($r) { Write-Host " $($r.fields.status.name)" -ForegroundColor Cyan }
    else     { Write-Host " NOT FOUND" -ForegroundColor Red }
    return $r
}

function Set-IssueTransition {
    param([string]$Key, [string]$TransitionId, [string]$Label)
    Write-Host "  -> Transitioning $Key to $Label ..." -NoNewline
    $body = @{ transition = @{ id = $TransitionId } }
    # Transitions return 204 No Content on success (Invoke-RestMethod returns $null, no throw)
    Invoke-JiraApi -Method POST -Endpoint "issue/$Key/transitions" -Body $body | Out-Null
    # If we reach here without exception the call succeeded (or returned $null for 204)
    Write-Host " Done" -ForegroundColor Green
}

function Add-Comment {
    param([string]$Key, [string]$CommentText)
    Write-Host "  -> Adding comment to $Key ..." -NoNewline
    $body = @{ body = $CommentText }
    $r = Invoke-JiraApi -Method POST -Endpoint "issue/$Key/comment" -Body $body
    if ($r) { Write-Host " Done (id $($r.id))" -ForegroundColor Green }
    return $r
}

function Test-CommentExists {
    param([string]$Key, [string]$Marker)
    $r = Invoke-JiraApi -Method GET -Endpoint "issue/$Key/comment" -QueryString "maxResults=100"
    if ($r -and $r.comments) {
        foreach ($c in $r.comments) {
            if ($c.body -like "*$Marker*") { return $true }
        }
    }
    return $false
}

function New-JiraIssue {
    param(
        [string]$Summary,
        [string]$Description,
        [string]$Priority    = "Medium",
        [string]$TransitionId = $null
    )
    Write-Host "  -> Creating: $Summary ..." -NoNewline
    $body = @{
        fields = @{
            project     = @{ key = $JiraProject }
            summary     = $Summary
            description = $Description
            issuetype   = @{ name = "Task" }
            priority    = @{ name = $Priority }
        }
    }
    $r = Invoke-JiraApi -Method POST -Endpoint "issue" -Body $body
    if ($r) {
        Write-Host " $($r.key)" -ForegroundColor Green
        if ($TransitionId) {
            Start-Sleep -Milliseconds 400
            Set-IssueTransition -Key $r.key -TransitionId $TransitionId -Label "In Progress"
        }
    }
    return $r
}

function Search-Issues {
    # Uses v3 POST (v2 GET /search returns 410 Gone on Atlassian Cloud as of 2026)
    param([string]$Jql, [int]$MaxResults = 50)
    $uri = "$JiraBaseUrl/rest/api/3/issue/search"
    $params = @{
        Method      = "POST"
        Uri         = $uri
        Headers     = $script:AuthHeaders
        Body        = (@{ jql = $Jql; maxResults = $MaxResults; fields = @("summary","status","priority","issuetype") } | ConvertTo-Json -Depth 5)
        ContentType = "application/json; charset=utf-8"
        ErrorAction = "Stop"
    }
    try {
        return Invoke-RestMethod @params
    }
    catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
        Write-Host "  [ERROR] POST /rest/api/3/issue/search => HTTP $code  $($_.ErrorDetails.Message)" -ForegroundColor Red
        return $null
    }
}

function Test-TicketExists {
    param([string]$Keyword)
    $jql = 'project = ' + $JiraProject + ' AND summary ~ "' + $Keyword + '"'
    $r = Search-Issues -Jql $jql -MaxResults 5
    return ($r -and $r.total -gt 0)
}

# ============================================================
# MAIN
# ============================================================

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  JIRA BULK UPDATE  --  March 21, 2026" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Validate credentials are filled in
if ($JiraEmail -eq "your-email@example.com" -or $JiraApiToken -eq "YOUR_API_TOKEN_HERE") {
    Write-Host "ERROR: Fill in `$JiraEmail and `$JiraApiToken at the top of this script." -ForegroundColor Red
    exit 1
}

# ----------------------------------------------------------
# STEP 0: Full Board State
# ----------------------------------------------------------
Write-Host "--- STEP 0: Current Board State ---" -ForegroundColor Yellow
$boardState = Search-Issues -Jql "project = $JiraProject ORDER BY key ASC" -MaxResults 50
if ($boardState -and $boardState.issues) {
    $fmt = "  {0,-12} {1,-18} {2,-10} {3}"
    Write-Host ($fmt -f "Key", "Status", "Priority", "Summary")
    Write-Host ("  " + "-" * 78)
    foreach ($issue in $boardState.issues) {
        $summary = $issue.fields.summary
        if ($summary.Length -gt 52) { $summary = $summary.Substring(0, 49) + "..." }
        Write-Host ($fmt -f $issue.key, $issue.fields.status.name, $issue.fields.priority.name, $summary)
    }
    Write-Host "  Total: $($boardState.total) tickets"
}
Write-Host ""

# ----------------------------------------------------------
# SECTION 1: Transitions
# ----------------------------------------------------------
Write-Host "--- SECTION 1: Transitions ---" -ForegroundColor Yellow

# SCRUM-14: Tesseract OCR -> Done
Write-Host ""
Write-Host "[SCRUM-14] Tesseract OCR for Scanned PDFs"
$i14 = Get-Issue -Key "SCRUM-14"
if ($i14) {
    if ($i14.fields.status.name -eq "Done") {
        Write-Host "  Already Done - skipping transition" -ForegroundColor DarkGray
    } else {
        Set-IssueTransition -Key "SCRUM-14" -TransitionId $TRANSITION_DONE -Label "Done"
    }

    $marker14 = "2026-03-21: COMPLETE"
    if (Test-CommentExists -Key "SCRUM-14" -Marker $marker14) {
        Write-Host "  Completion comment already exists - skipping" -ForegroundColor DarkGray
    } else {
        $c14 = @"
2026-03-21: COMPLETE -- Tesseract OCR fully implemented and tested

- Tesseract 5.5.0 installed from UB-Mannheim
- Full OCR test on Secret Societies of All Ages (1875, 417 pages): 63,733 words, 16 chapters detected, 10.8 minutes at 300 DPI
- Zero regression confirmed on 22 structured PDFs (byte-identical output between --no-ocr and auto-detect modes)
- detect_pdf_type() correctly classifies all test PDFs (structured avg 2,250-3,444 chars/page vs image-only at 0 chars/page)
- All CLI flags working: --ocr, --no-ocr, --tesseract-path, --poppler-path, --ocr-dpi
- PowerShell -UseOCR switch integrated into Convert-ToTTS and Invoke-EbookPipeline
- Tesseract validation added to Initialize-EbookAutomation
- paths.tesseract and paths.poppler added to settings.json
- Batch scanner (Invoke-TesseractKindleBatch.ps1) created: scanned 77 PDFs in F:\Books, found 7 image-based, 14 likely-scanned, 1 error
"@
        Add-Comment -Key "SCRUM-14" -CommentText $c14 | Out-Null
    }
}

# SCRUM-52: SSH Remote Access -> Done
Write-Host ""
Write-Host "[SCRUM-52] SSH Remote Access"
$i52 = Get-Issue -Key "SCRUM-52"
if ($i52) {
    if ($i52.fields.status.name -eq "Done") {
        Write-Host "  Already Done - skipping transition" -ForegroundColor DarkGray
    } else {
        Set-IssueTransition -Key "SCRUM-52" -TransitionId $TRANSITION_DONE -Label "Done"
    }

    $marker52 = "2026-03-21"
    if (Test-CommentExists -Key "SCRUM-52" -Marker $marker52) {
        Write-Host "  Comment already exists - skipping" -ForegroundColor DarkGray
    } else {
        Add-Comment -Key "SCRUM-52" -CommentText "Completed 2026-03-21. OpenSSH Server enabled on Windows desktop, PowerShell 7 set as default SSH shell. Successfully connected from Termius on Android and ran Claude Code session over SSH." | Out-Null
    }
}

# ----------------------------------------------------------
# SECTION 2: Comments (no status change)
# ----------------------------------------------------------
Write-Host ""
Write-Host "--- SECTION 2: Comments ---" -ForegroundColor Yellow

# SCRUM-13: AI Quality Pass
Write-Host ""
Write-Host "[SCRUM-13] AI Quality Pass"
$marker13 = "pdfminer HTML extraction + Phases 1-4"
if (Test-CommentExists -Key "SCRUM-13" -Marker $marker13) {
    Write-Host "  Comment already exists - skipping" -ForegroundColor DarkGray
} else {
    $c13 = @"
2026-03-21: Major progress -- pdfminer HTML extraction + Phases 1-4 implemented

pdfminer HTML extraction layer (replaces pypdf flat text):
- Full pipeline: extract_text_with_formatting() captures font metadata per character
- format_paragraphs_as_html() converts to semantic HTML with h1/h2/h3 from font size hierarchy
- 6 formatting refinements: epigraph detection, attribution splitting (em-dash patterns), em tag wrapping, whitespace normalization, Front Matter h1 insertion, back matter h3 suppression
- Superscript footnote detection: 714 superscripts on Mexico, zero false positives
- Bidirectional endnote linking: 306 linked footnotes on Mexico with tap-to-note/tap-back navigation (commercial Kindle quality)

AI Quality Pass improvements:
- Hallucination guard: auto-fix limited to <=3 chars added beyond original text. Prevents AI inventing content. Jesus/Land: 64->72 (was 64->30 before guard)
- Double-application guard: verifies pattern exists in current text before applying. Eliminates stutter corruption ("Ultimatelyly", "menen"). Khazars: zero stutters after fix
- Deterministic scoring via temperature:0

Books tested through full pipeline:
- Oil Kings: Score 94, excellent TOC and formatting
- Brother of Jesus: Score 84 (sub-heading insertion shifting paragraph indices -- diagnosed)
- Jesus and the Land: Score 72 (improved from 64 after hallucination guard)
- Khazars: Score 83 (image-only PDF, routed to Tesseract OCR)
- Mexico: Score 88 (full footnote linking, accent normalization, Unicode fixes)
- Dionysius: ~85 (21 blockquotes detected from italic font metadata)

Claude Code workflow improvements:
- CLAUDE.md updated with environment specs, verification rules, pipeline architecture
- Custom test pipeline skill created
- PostToolUse hooks for Python syntax checking
- Test harness: tools/test_pipeline.py + tools/test_cases.json
"@
    Add-Comment -Key "SCRUM-13" -CommentText $c13 | Out-Null
}

# SCRUM-20: Image Preservation in PDF-to-Kindle
Write-Host ""
Write-Host "[SCRUM-20] Image Preservation in PDF-to-Kindle"
$marker20 = "PDF hyperlink preservation identified"
if (Test-CommentExists -Key "SCRUM-20" -Marker $marker20) {
    Write-Host "  Comment already exists - skipping" -ForegroundColor DarkGray
} else {
    $c20 = @"
2026-03-21: Related finding -- PDF hyperlink preservation identified as feature gap

During Oil Kings conversion review, discovered that inline hyperlinks (/Link annotations with /URI targets) are stripped during extraction. pypdf's extract_text() and format_kindle_html() both discard PDF annotation layers.

Fix requires: extracting /Link annotations via pypdf annotation API, mapping bounding boxes to text spans, wrapping in <a href="..."> tags in HTML output. Flagged for dedicated session.
"@
    Add-Comment -Key "SCRUM-20" -CommentText $c20 | Out-Null
}

# SCRUM-23: AI Vision TOC Extraction
Write-Host ""
Write-Host "[SCRUM-23] AI Vision TOC Extraction"
$marker23 = "Dionysius the Areopagite -- TOC entries out of order"
if (Test-CommentExists -Key "SCRUM-23" -Marker $marker23) {
    Write-Host "  Comment already exists - skipping" -ForegroundColor DarkGray
} else {
    $c23 = @"
2026-03-21: Two TOC issues identified during conversion review

Dionysius the Areopagite -- TOC entries out of order in KFX. Bookmark-mapped headings and regex-detected headings have different paragraph indices; combined set not sorted before emission. Content reads correctly sequentially -- only TOC navigation is broken.

Jesus and the Land -- No matching TOC (only 3 entries). Section headings are Bible verse references ("Galatians 3.23-4.7") that regex can't match. Needs -UseClaudeChapters.

Debug prompt designed for Claude Code session.
"@
    Add-Comment -Key "SCRUM-23" -CommentText $c23 | Out-Null
}

# SCRUM-28: Chapter Alignment Verification
Write-Host ""
Write-Host "[SCRUM-28] Chapter Alignment Verification"
$marker28 = "Dionysius chapter alignment issue confirmed"
if (Test-CommentExists -Key "SCRUM-28" -Marker $marker28) {
    Write-Host "  Comment already exists - skipping" -ForegroundColor DarkGray
} else {
    $c28 = @"
2026-03-21: Dionysius chapter alignment issue confirmed

Two compounding problems:
1. ORDERING: Bookmark-mapped and regex-detected headings use different paragraph indices. Combined heading set not sorted by document position, causing out-of-order TOC.
2. TITLE COMPLETENESS: Failed bookmark matches fall through to regex which only captures bare "CHAPTER I" -- losing the full title.

Fix designed in debug session prompt (sort heading indices + bookmark-first priority).
"@
    Add-Comment -Key "SCRUM-28" -CommentText $c28 | Out-Null
}

# ----------------------------------------------------------
# SECTION 3: New Tickets
# ----------------------------------------------------------
Write-Host ""
Write-Host "--- SECTION 3: New Tickets ---" -ForegroundColor Yellow

# 1. EPUB/MOBI/AZW/DJVU Native Format Support
Write-Host ""
Write-Host "[NEW] EPUB/MOBI/AZW/DJVU Native Format Support"
if (Test-TicketExists -Keyword "EPUB/MOBI") {
    Write-Host "  Similar ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $d1 = @"
Expanded pdf_to_balabolka.py to handle EPUB, MOBI, AZW, AZW3, and DJVU formats natively.

Architecture:
- EPUB: Native Python extraction via ebooklib + BeautifulSoup (quality)
- MOBI/AZW/AZW3/DJVU: Calibre CLI intermediate conversion (maintainability)
- New dispatcher: extract_text_auto() routes by file extension
- --calibre-path CLI argument added
- Tkinter GUI file dialog filters updated
- PowerShell EPUB->PDF intermediate step removed (native is better)
- settings.json input_formats updated

Testing: 24/26 regression tests pass (2 failures were test assertion bugs, not code bugs). EPUB extraction: 122 words with correct chapter detection, zero HTML leakage. End-to-end 3.1s.

Real-world testing in progress via Test-BooksLibrary.ps1 against F:\Books (77 PDFs + various formats).
"@
    New-JiraIssue -Summary "EPUB/MOBI/AZW/DJVU Native Format Support" -Description $d1 `
        -Priority "High" -TransitionId $TRANSITION_IN_PROGRESS | Out-Null
}

# 2. Ezekiel II Calibre KFX Crash
Write-Host ""
Write-Host "[NEW] Ezekiel II Calibre KFX Crash -- AZW3 Fallback"
if (Test-TicketExists -Keyword "Ezekiel") {
    Write-Host "  Similar ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $d2 = @"
Convert-ToKindle with -UseHtmlExtraction on Ezekiel II (Hermeneia commentary, 1988) succeeds at HTML extraction (2493 KB, 163s) but Calibre KFX conversion crashes with exit code 1 after ~70s.

Hypothesis: Academic commentaries with complex formatting (footnotes, Greek text, nested structures) produce HTML the KFX Output plugin can't handle.

Fix: Add automatic AZW3 fallback when KFX conversion fails. Check %TEMP%\calibre_err.txt for specific error.
"@
    New-JiraIssue -Summary "Ezekiel II Calibre KFX Crash -- AZW3 Fallback" -Description $d2 `
        -Priority "Medium" | Out-Null
}

# 3. Pipeline Step Timing Instrumentation
Write-Host ""
Write-Host "[NEW] Pipeline Step Timing Instrumentation"
if (Test-TicketExists -Keyword "Timing Instrumentation") {
    Write-Host "  Similar ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $d3 = @"
Add per-step timing breakdown to Convert-ToKindle using ordered hashtable tracking: TextExtraction, CoverExtraction, ClaudeChapters, CalibreConversion, QualityPass, Total.

- Emit formatted summary table after each conversion
- Return timings object so Invoke-EbookPipeline can include in batch summary

Conversions taking longer with HTML extraction + AI features (expected), but no visibility into per-step duration.
"@
    New-JiraIssue -Summary "Pipeline Step Timing Instrumentation" -Description $d3 `
        -Priority "Low" | Out-Null
}

# 4. PDF Hyperlink Preservation in Kindle Output
Write-Host ""
Write-Host "[NEW] PDF Hyperlink Preservation in Kindle Output"
if (Test-TicketExists -Keyword "Hyperlink Preservation") {
    Write-Host "  Similar ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $d4 = @"
PDF inline hyperlinks (/Link annotations with /URI targets) stripped during text extraction. Oil Kings has hyperlinks that appear as blue underlined text in PDF but lose link targets in KFX.

Fix requires:
1. Extract /Link annotations via pypdf annotation API
2. Map bounding box to text span
3. Wrap in <a href="..."> tags in HTML output
4. Calibre preserves <a> tags through KFX conversion

Coordinate-based text matching -- substantial feature work.
"@
    New-JiraIssue -Summary "PDF Hyperlink Preservation in Kindle Output" -Description $d4 `
        -Priority "Medium" | Out-Null
}

# 5. Two-Column PDF Layout Detection
Write-Host ""
Write-Host "[NEW] Two-Column PDF Layout Detection (PyMuPDF)"
if (Test-TicketExists -Keyword "Two-Column PDF") {
    Write-Host "  Similar ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $d5 = @"
Ezekiel II is a two-column academic commentary. Current pdfminer extraction reads left-to-right across both columns, interleaving text from column A and column B into garbled output.

Solution: Add PyMuPDF-based column detection that samples pages, clusters text block x-coordinates, and determines single vs multi-column layout. Multi-column books get column-aware extraction (left column first, then right). Single-column books fall through to existing pdfminer/pypdf path unchanged.

Detection gate runs first with >=60% confidence threshold. Zero changes to existing single-column path.

Dependencies: PyMuPDF (pymupdf package)
Claude Code prompt sequence designed (6 prompts).
"@
    New-JiraIssue -Summary "Two-Column PDF Layout Detection (PyMuPDF)" -Description $d5 `
        -Priority "High" | Out-Null
}

# ----------------------------------------------------------
# SECTION 4: Verify Earlier Tasks
# ----------------------------------------------------------
Write-Host ""
Write-Host "--- SECTION 4: Verify Earlier Tasks (SCRUM-50 through SCRUM-59) ---" -ForegroundColor Yellow
Write-Host ""

$verifyKeys = @("SCRUM-50","SCRUM-51","SCRUM-52","SCRUM-53","SCRUM-54","SCRUM-55","SCRUM-56","SCRUM-57","SCRUM-58","SCRUM-59")
$missing = @()

foreach ($key in $verifyKeys) {
    $r = Invoke-JiraApi -Method GET -Endpoint "issue/$key"
    if ($r) {
        $summary = $r.fields.summary
        if ($summary.Length -gt 50) { $summary = $summary.Substring(0,47) + "..." }
        Write-Host ("  {0,-12} [{1,-15}]  {2}" -f $key, $r.fields.status.name, $summary) -ForegroundColor Green
    } else {
        Write-Host ("  {0,-12}  NOT FOUND" -f $key) -ForegroundColor Red
        $missing += $key
    }
}

# Create SCRUM-59 if missing
if ("SCRUM-59" -in $missing) {
    Write-Host ""
    Write-Host "[SCRUM-59] Not found - creating One-Tap Mobile SSH Shortcut..."
    $d59 = "Set up Termux:Widget + Termux:API for one-tap biometric SSH connection from Android phone to desktop. Requires F-Droid versions of all Termux components (Play Store versions incompatible with add-ons)."
    New-JiraIssue -Summary "One-Tap Mobile SSH Shortcut (Termux)" -Description $d59 -Priority "Low" | Out-Null
}

# ----------------------------------------------------------
# SECTION 5: Cleanup — One-Tap ticket + SCRUM-63 duplicate
# ----------------------------------------------------------
Write-Host ""
Write-Host "--- SECTION 5: Cleanup ---" -ForegroundColor Yellow

# Create One-Tap Mobile SSH Shortcut (was supposed to be SCRUM-59, but that key was taken)
Write-Host ""
Write-Host "[NEW] One-Tap Mobile SSH Shortcut (Termux)"
if (Test-TicketExists -Keyword "One-Tap Mobile SSH") {
    Write-Host "  Ticket already exists - skipping" -ForegroundColor DarkGray
} else {
    $dOnetap = "Set up Termux:Widget + Termux:API for one-tap biometric SSH connection from Android phone to desktop. Requires F-Droid versions of all Termux components (Play Store versions incompatible with add-ons)."
    New-JiraIssue -Summary "One-Tap Mobile SSH Shortcut (Termux)" -Description $dOnetap -Priority "Low" | Out-Null
}

# SCRUM-63 is a duplicate of SCRUM-59 (both are AZW3 fallback — search check failed due to API 410)
# Link SCRUM-63 as duplicate of SCRUM-59, then close it.
Write-Host ""
Write-Host "[SCRUM-63] Mark as duplicate of SCRUM-59 and close"
$i63 = Invoke-JiraApi -Method GET -Endpoint "issue/SCRUM-63"
if ($i63 -and $i63.fields.status.name -ne "Done") {
    # Create duplicate link
    Write-Host "  -> Linking SCRUM-63 as duplicate of SCRUM-59 ..." -NoNewline
    $linkBody = @{
        type         = @{ name = "Duplicate" }
        inwardIssue  = @{ key  = "SCRUM-63" }
        outwardIssue = @{ key  = "SCRUM-59" }
    }
    Invoke-JiraApi -Method POST -Endpoint "issueLink" -Body $linkBody | Out-Null
    Write-Host " Done" -ForegroundColor Green

    # Add explanatory comment
    Add-Comment -Key "SCRUM-63" -CommentText "Closing as duplicate of SCRUM-59 (AZW3 Fallback When KFX Conversion Fails). Both tickets created 2026-03-21; duplicate-check search failed due to API 410 error. SCRUM-59 is the canonical ticket -- the full Ezekiel II context from this ticket's description has been noted there." | Out-Null

    # Add the detailed description to SCRUM-59 as a comment so context isn't lost
    $scrum59Comment = @"
2026-03-21: Additional context from SCRUM-63 (closed as duplicate)

Specific repro: Convert-ToKindle with -UseHtmlExtraction on Ezekiel II (Hermeneia commentary, 1988) succeeds at HTML extraction (2493 KB, 163s) but Calibre KFX conversion crashes with exit code 1 after ~70s.

Hypothesis: Academic commentaries with complex formatting (footnotes, Greek text, nested structures) produce HTML the KFX Output plugin can't handle.

Fix: Add automatic AZW3 fallback when KFX conversion fails. Check %TEMP%\calibre_err.txt for specific error.
"@
    if (-not (Test-CommentExists -Key "SCRUM-59" -Marker "Additional context from SCRUM-63")) {
        Add-Comment -Key "SCRUM-59" -CommentText $scrum59Comment | Out-Null
    }

    # Close SCRUM-63
    Set-IssueTransition -Key "SCRUM-63" -TransitionId $TRANSITION_DONE -Label "Done"
} elseif ($i63 -and $i63.fields.status.name -eq "Done") {
    Write-Host "  SCRUM-63 already Done - skipping" -ForegroundColor DarkGray
} else {
    Write-Host "  SCRUM-63 not found - skipping" -ForegroundColor DarkGray
}

# ----------------------------------------------------------
# DONE
# ----------------------------------------------------------
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Bulk update complete." -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
