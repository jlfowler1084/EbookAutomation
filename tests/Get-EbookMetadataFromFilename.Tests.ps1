#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Pester tests for Get-EbookMetadataFromFilename (SCRUM-316).

.DESCRIPTION
    Anchors the metadata-extraction-from-filename behavior. The function is
    internal to the EbookAutomation module (not Export-ModuleMember-ed), so
    the tests run via InModuleScope. Run with:
        Invoke-Pester -Path tests/Get-EbookMetadataFromFilename.Tests.ps1
#>

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1'
    Import-Module $modulePath -Force
}

Describe 'Get-EbookMetadataFromFilename' {
    Context 'SCRUM-316: leading series prefix and last-year preference' {
        It "extracts series='Great Books in Philosophy' and year='1989' from Feuerbach filename" {
            InModuleScope EbookAutomation {
                $name = '(Great Books in Philosophy) Ludwig Feuerbach - The Essence of Christianity (Great Books in Philosophy)-Prometheus Books (1989).pdf'
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Series | Should -Be 'Great Books in Philosophy'
                $meta.Year   | Should -Be '1989'
            }
        }

        It "strips the leading series prefix from Authors when captured into Series (SCRUM-322)" {
            InModuleScope EbookAutomation {
                $name = '(Great Books in Philosophy) Ludwig Feuerbach - The Essence of Christianity (Great Books in Philosophy)-Prometheus Books (1989).pdf'
                $meta = Get-EbookMetadataFromFilename $name
                # Bug A: previously '(Great Books in Philosophy) Ludwig Feuerbach'
                $meta.Authors | Should -Be 'Ludwig Feuerbach'
            }
        }

        It 'returns empty Series when there is no leading parenthetical' {
            InModuleScope EbookAutomation {
                $name = 'Andrew Scott Cooper - The Oil Kings (2011, Simon & Schuster) - libgen.li.pdf'
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Series | Should -Be ''
                $meta.Year   | Should -Be '2011'
            }
        }

        It 'does NOT treat a leading 4-digit-year parenthetical as a series tag' {
            InModuleScope EbookAutomation {
                $name = '(2011) Some Author - Some Book.pdf'
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Series | Should -Be ''
                $meta.Year   | Should -Be '2011'
            }
        }

        It 'prefers the LAST parens-bound year when multiple years exist' {
            InModuleScope EbookAutomation {
                # 2nd-edition reprint pattern: original year early, reprint year late
                $name = 'Some Author - Original Work (1925) Reissued (2018, Penguin).pdf'
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Year | Should -Be '2018'
            }
        }

        It "extracts year from Anna's Archive double-dash format (no parens)" {
            InModuleScope EbookAutomation {
                $name = "Franklin D_ Roosevelt _ A Political Life -- Robert Dallek -- Penguin Random House LLC, New York, 2017 -- Penguin Books -- 9780143111214 -- f016463eb0e6d5dfcf347e293cbaf6c7 -- Anna's Archive.pdf"
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Year | Should -Be '2017'
            }
        }
    }

    Context 'Existing-behavior regression cases' {
        It 'parses Oil Kings (libgen format) the same as before' {
            InModuleScope EbookAutomation {
                $name = 'Andrew Scott Cooper - The Oil Kings (2011, Simon & Schuster) - libgen.li.pdf'
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Authors | Should -Be 'Andrew Scott Cooper'
                $meta.Title   | Should -Be 'The Oil Kings'
                $meta.Year    | Should -Be '2011'
            }
        }

        It "parses Anna's Archive double-dash format the same as before" {
            InModuleScope EbookAutomation {
                $name = "My Book Title -- John Doe -- Publisher -- 2020 -- Anna's Archive.epub"
                $meta = Get-EbookMetadataFromFilename $name
                $meta.Title   | Should -Be 'My Book Title'
                $meta.Authors | Should -Be 'John Doe'
                $meta.Year    | Should -Be '2020'
            }
        }
    }
}
