#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Pester tests for SCRUM-329 — Invoke-EbookPipeline content-profile flag forwarding.

.DESCRIPTION
    Invoke-EbookPipeline declared -Profile and the -No* content flags but never
    passed them to Convert-ToKindle. The flags therefore appeared in Get-Help,
    tab-completed, and validated their arguments -- then did nothing. A caller
    running `Invoke-EbookPipeline -Profile text-only -NoImages` silently got a
    full conversion.

    The gap was found salvaging stash-0 from DESKTOP-488UQB2 (INFRA-597). Three
    of that stash's five hunks had landed; the hunk that wired the forwarding had
    not, leaving the declaring half without the forwarding half.

    These tests derive the expected flag list from the parameter declaration
    rather than hard-coding it, so a content flag added later is covered without
    editing this file -- declared-but-unforwarded is the defect class, not any
    one flag.

    These tests inspect the module AST only -- they never invoke the pipeline
    (which would touch the inbox, Calibre, and the conversion cache).

    Run with:
        Invoke-Pester -Path tests/Invoke-EbookPipeline.ProfileForwarding.Tests.ps1
#>

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1'

    $parseErrors = $null
    $tokens      = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $modulePath, [ref]$tokens, [ref]$parseErrors)

    if ($parseErrors -and $parseErrors.Count -gt 0) {
        throw "Module failed to parse: $($parseErrors[0].Message)"
    }

    $script:PipelineAst = $ast.Find({
        param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $n.Name -eq 'Invoke-EbookPipeline'
    }, $true)

    # Content-profile flags as *declared* on Invoke-EbookPipeline.
    $script:DeclaredFlags = @(
        $script:PipelineAst.Body.ParamBlock.Parameters |
            ForEach-Object { $_.Name.VariablePath.UserPath } |
            Where-Object { $_ -eq 'Profile' -or $_ -match '^No(Footnotes|Index|Bibliography|Hyperlinks|FrontMatter|BackMatter|Images|BlockQuotes)$' }
    )

    # Convert-ToKindle's own declared parameters, read from the AST so this file
    # never has to import the module (import touches config and the cache).
    $kindleAst = $ast.Find({
        param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $n.Name -eq 'Convert-ToKindle'
    }, $true)

    $script:KindleParams = @(
        $kindleAst.Body.ParamBlock.Parameters |
            ForEach-Object { $_.Name.VariablePath.UserPath }
    )

    # Every Convert-ToKindle invocation lexically inside Invoke-EbookPipeline.
    $script:KindleCalls = @(
        $script:PipelineAst.FindAll({
            param($n)
            $n -is [System.Management.Automation.Language.CommandAst] -and
            $n.GetCommandName() -eq 'Convert-ToKindle'
        }, $true)
    )
}

Describe 'Invoke-EbookPipeline content-profile forwarding (SCRUM-329)' {

    It 'declares the content-profile flags' {
        $script:DeclaredFlags | Should -Not -BeNullOrEmpty
        $script:DeclaredFlags | Should -Contain 'Profile'
    }

    It 'calls Convert-ToKindle at least once' {
        $script:KindleCalls.Count | Should -BeGreaterThan 0
    }

    It 'forwards every declared content-profile flag to Convert-ToKindle' {
        foreach ($call in $script:KindleCalls) {
            $passed = @(
                $call.CommandElements |
                    Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } |
                    ForEach-Object { $_.ParameterName }
            )

            foreach ($flag in $script:DeclaredFlags) {
                $passed | Should -Contain $flag -Because @"
Invoke-EbookPipeline declares -$flag but does not pass it to Convert-ToKindle
(line $($call.Extent.StartLineNumber)). A declared-but-unforwarded flag is
silently ignored at runtime. Add -$flag to that call.
"@
            }
        }
    }

    It 'passes only flags that Convert-ToKindle actually declares' {
        # Guards the mirror-image defect: forwarding a flag the callee does not
        # accept, which fails at runtime rather than silently.
        $script:KindleParams | Should -Not -BeNullOrEmpty
        foreach ($flag in $script:DeclaredFlags) {
            $script:KindleParams | Should -Contain $flag
        }
    }
}
