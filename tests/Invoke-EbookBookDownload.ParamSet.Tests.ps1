#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Pester tests for EB-356 defect 2 — Invoke-EbookBookDownload -List binding.

.DESCRIPTION
    Before the fix, -List/-Stats/-History/-Resume were spread across all
    parameter sets while the default 'FromResult' set made -InputObject
    Mandatory. As a result `Invoke-EbookBookDownload -List` could not resolve a
    parameter set and failed with "missing mandatory parameters: InputObject".

    The fix moves those four query switches into a dedicated 'Query' set that has
    no mandatory parameters, so `-List` alone resolves cleanly.

    These tests inspect command *metadata* only — they never invoke the cmdlet
    (which would shell out to book_downloader.py and touch the download DB).

    Run with:
        Invoke-Pester -Path tests/Invoke-EbookBookDownload.ParamSet.Tests.ps1
#>

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1'
    Import-Module $modulePath -Force
}

Describe 'Invoke-EbookBookDownload parameter sets (EB-356 defect 2)' {

    It 'defines a dedicated Query parameter set' {
        InModuleScope EbookAutomation {
            $cmd = Get-Command Invoke-EbookBookDownload
            $cmd.ParameterSets.Name | Should -Contain 'Query'
        }
    }

    It 'binds -List/-Stats/-History/-Resume under the Query set' {
        InModuleScope EbookAutomation {
            $cmd = Get-Command Invoke-EbookBookDownload
            foreach ($p in 'List', 'Stats', 'History', 'Resume') {
                $cmd.Parameters[$p].ParameterSets.Keys | Should -Contain 'Query'
            }
        }
    }

    It 'does not place InputObject in the Query set' {
        InModuleScope EbookAutomation {
            $cmd = Get-Command Invoke-EbookBookDownload
            # InputObject must stay out of Query, else -List would demand it again.
            $cmd.Parameters['InputObject'].ParameterSets.Keys | Should -Not -Contain 'Query'
        }
    }

    It 'has no mandatory parameter in the Query set (so -List alone resolves)' {
        InModuleScope EbookAutomation {
            $cmd = Get-Command Invoke-EbookBookDownload
            $query = $cmd.ParameterSets | Where-Object Name -EQ 'Query'
            $mandatory = $query.Parameters | Where-Object { $_.IsMandatory }
            $mandatory | Should -BeNullOrEmpty
        }
    }
}
