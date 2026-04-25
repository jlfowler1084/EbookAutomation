#Requires -Modules Pester
<#
.SYNOPSIS
    Pester 5 tests for the tolerant JSON parser introduced in SCRUM-313.
.DESCRIPTION
    All parser behavior is tested through the public Get-ChapterStructure
    function with Send-ToClaudeAPI mocked to avoid real network requests.

    Validates three failure modes observed in production:
    A) Conversational prose preamble before the JSON array (Sub-failure A)
    B) Single JSON object instead of an array (Sub-failure B)
    C) Markdown code fence wrapping (```json ... ```)
    D) Happy path — clean JSON array must not regress

    Also verifies that on a completely unparseable response the function
    falls back gracefully (returns $null so the caller uses PDF bookmarks).
.NOTES
    Uses InModuleScope EbookAutomation so that Mock Send-ToClaudeAPI
    intercepts the internal call inside Get-ChapterStructure.

    The module import is placed at the TOP LEVEL of the file (before Describe)
    because Pester 5 resolves InModuleScope during DISCOVERY, before BeforeAll
    runs. Placing Import-Module in BeforeAll is too late for InModuleScope to
    pick up the correct module.

    The user profile auto-imports the main-tree EbookAutomation via SecondBrain.
    We remove all pre-loaded instances and import only the worktree revision so
    InModuleScope resolves to the right module (with the SCRUM-313 parser fix).
#>

# -- Module setup (top-level, runs during Pester discovery) ----------------
# Remove every pre-loaded EbookAutomation copy before importing the worktree
# revision. Profile may auto-import the main-tree copy via SecondBrain module.
do {
    $existing = Get-Module EbookAutomation -ErrorAction SilentlyContinue
    if ($existing) { $existing | Remove-Module -Force -ErrorAction SilentlyContinue }
} while (Get-Module EbookAutomation -ErrorAction SilentlyContinue)

$_worktreeModulePath = Join-Path $PSScriptRoot '..' 'module' 'EbookAutomation.psm1'
Import-Module (Resolve-Path $_worktreeModulePath).Path -Force -ErrorAction Stop
# --------------------------------------------------------------------------

Describe 'Get-ChapterStructure parser tolerance (SCRUM-313)' {
    InModuleScope EbookAutomation {

        # ------------------------------------------------------------------
        # Sub-failure A: conversational preamble before JSON array
        # ------------------------------------------------------------------
        Context 'Sub-failure A: conversational preamble before JSON array' {

            It 'extracts the array and ignores leading prose' {
                Mock Send-ToClaudeAPI {
                    return @'
Looking at the font-detected candidates and text samples, I need to analyze this carefully.

[{"title": "Chapter 1", "level": 2, "is_back_matter": false, "page_estimate": 1, "confidence": 0.95, "notes": ""}]
'@
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'Chapter 1'
            }

            It 'handles multi-sentence preamble with book title mention (Secret Doctrine case)' {
                Mock Send-ToClaudeAPI {
                    return @'
Looking at this input carefully, I can see this is H.P. Blavatsky''s *The Secret Doctrine*. Let me analyze the heading candidates.

[{"title": "Proem", "level": 2, "is_back_matter": false, "page_estimate": 1, "confidence": 0.92, "notes": ""},
 {"title": "Part One", "level": 1, "is_back_matter": false, "page_estimate": 10, "confidence": 0.95, "notes": ""}]
'@
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 2
                $result[0].title | Should -Be 'Proem'
            }

            It 'handles preamble ending with colon (Prophets of Israel case)' {
                Mock Send-ToClaudeAPI {
                    return @'
Analyzing the font candidates and text samples carefully:

[{"title": "Introduction", "level": 2, "is_back_matter": false, "page_estimate": 5, "confidence": 0.88, "notes": ""}]
'@
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'Introduction'
            }

            It 'handles TDNT-style preamble with bold markdown' {
                Mock Send-ToClaudeAPI {
                    return @'
This is Volume VIII of the **Theological Dictionary of the New Testament**. Based on the font candidates, here are the chapters:

[{"title": "TDNT Entry 1", "level": 2, "is_back_matter": false, "page_estimate": 1, "confidence": 0.9, "notes": ""}]
'@
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'TDNT Entry 1'
            }
        }

        # ------------------------------------------------------------------
        # Sub-failure B: single JSON object instead of array
        # ------------------------------------------------------------------
        Context 'Sub-failure B: single JSON object instead of array' {

            It 'wraps bare single object as a one-element result' {
                Mock Send-ToClaudeAPI {
                    return '{"title": "Preface", "level": 2, "is_back_matter": false, "page_estimate": 9, "confidence": 0.92, "notes": "Clearly labeled front matter"}'
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'Preface'
            }

            It 'wraps fenced single object as a one-element result' {
                Mock Send-ToClaudeAPI {
                    # Backtick-escaped here so PowerShell heredoc does not break on fences
                    return "``````json`n{`"title`": `"Preface`", `"level`": 2, `"is_back_matter`": false, `"page_estimate`": 9, `"confidence`": 0.92, `"notes`": `"`"}`n``````"
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'Preface'
            }
        }

        # ------------------------------------------------------------------
        # Markdown fenced block stripping
        # ------------------------------------------------------------------
        Context 'Markdown fenced block stripping' {

            It 'extracts array from ```json fence' {
                Mock Send-ToClaudeAPI {
                    return "``````json`n[{`"title`": `"Chapter 1`", `"level`": 2, `"is_back_matter`": false, `"page_estimate`": 1, `"confidence`": 0.9, `"notes`": `"`"}]`n``````"
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 1
                $result[0].title | Should -Be 'Chapter 1'
            }
        }

        # ------------------------------------------------------------------
        # Happy path: clean JSON array (regression guard)
        # ------------------------------------------------------------------
        Context 'Happy path: clean JSON array (regression guard)' {

            It 'passes through a clean array with no modification' {
                Mock Send-ToClaudeAPI {
                    return '[{"title": "Chapter 1", "level": 2, "is_back_matter": false, "page_estimate": 1, "confidence": 0.95, "notes": ""},{"title": "Chapter 2", "level": 2, "is_back_matter": false, "page_estimate": 20, "confidence": 0.95, "notes": ""}]'
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 2
                $result[0].title | Should -Be 'Chapter 1'
                $result[1].title | Should -Be 'Chapter 2'
            }

            It 'handles multi-line clean array' {
                Mock Send-ToClaudeAPI {
                    return @'
[
  {"title": "Prologue", "level": 2, "is_back_matter": false, "page_estimate": 1, "confidence": 0.95, "notes": ""},
  {"title": "Chapter 1", "level": 2, "is_back_matter": false, "page_estimate": 10, "confidence": 0.9, "notes": ""}
]
'@
                }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -Not -BeNullOrEmpty
                $result.Count | Should -Be 2
                $result[0].title | Should -Be 'Prologue'
            }
        }

        # ------------------------------------------------------------------
        # Fallback behavior
        # ------------------------------------------------------------------
        Context 'Fallback: API returns null' {

            It 'returns null when the API call itself fails (bookmark fallback path)' {
                Mock Send-ToClaudeAPI { return $null }
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -BeNullOrEmpty
            }
        }

        Context 'Fallback: completely unparseable response' {

            It 'returns null and does not throw on garbage response' {
                Mock Send-ToClaudeAPI { return 'This response contains no JSON at all.' }
                { Get-ChapterStructure -TextContent 'Sample text' } | Should -Not -Throw
                $result = Get-ChapterStructure -TextContent 'Sample text'
                $result | Should -BeNullOrEmpty
            }
        }
    }
}
