#Requires -Modules Pester
Import-Module (Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1') -Force

Describe 'Confirmed PDF chapter heading insertion' {
    InModuleScope EbookAutomation {
        BeforeEach { Mock Write-EbookLog {} }

        It 'promotes h3 to h2 and preserves id, attributes and inline content across line breaks' {
            $html = "<h3 id='chapter-2' class='chapter'>European`n<em>Esoteric</em>  Currents</h3>"
            $result = Update-HtmlChapterHeadings -HtmlContent $html -Chapters @(@{ title = 'European Esoteric Currents'; level = 2 })
            $result.HtmlContent | Should -Be "<h2 id='chapter-2' class='chapter'>European`n<em>Esoteric</em>  Currents</h2>"
            $result.Promoted | Should -Be 1
            $result.Missing | Should -Be 0
        }

        It 'promotes h3 to h1 when the chapter model requests a part' {
            $result = Update-HtmlChapterHeadings -HtmlContent '<h3 id="part">Part One</h3>' -Chapters @(@{ title = 'Part One'; level = 1 })
            $result.HtmlContent | Should -Be '<h1 id="part">Part One</h1>'
            $result.Promoted | Should -Be 1
        }

        It 'preserves established h1 and h2 levels when a weaker level is suggested' {
            $html = '<h1 id="intro">Introduction</h1><h2 id="history">History</h2>'
            $result = Update-HtmlChapterHeadings -HtmlContent $html -Chapters @(@{ title = 'Introduction'; level = 2 }, @{ title = 'History'; level = 3 })
            $result.HtmlContent | Should -Be $html
            $result.Existing | Should -Be 2
            $result.Promoted | Should -Be 0
        }

        It 'matches decoded heading entities and nonbreaking whitespace' {
            $result = Update-HtmlChapterHeadings -HtmlContent '<h3 id="a">Magic&nbsp;&amp; Science</h3>' -Chapters @(@{ title = 'Magic & Science'; level = 2 })
            $result.HtmlContent | Should -Be '<h2 id="a">Magic&nbsp;&amp; Science</h2>'
        }

        It 'reports missing titles instead of claiming every heading was already present' {
            $result = Update-HtmlChapterHeadings -HtmlContent '<h2>Introduction</h2><p>Ordinary body text.</p>' -Chapters @(@{ title = 'Introduction'; level = 2 }, @{ title = 'Lost Chapter'; level = 2 })
            $result.Existing | Should -Be 1
            $result.Missing | Should -Be 1
            Should -Invoke Write-EbookLog -Times 1 -ParameterFilter { $Message -eq 'Kindle: chapter headings: 0 inserted, 0 promoted, 1 already present, 1 not found' -and $Level -eq 'WARN' }
        }

        It 'retains paragraph insertion while tolerating wrapped titles' {
            $result = Update-HtmlChapterHeadings -HtmlContent "<p>European`nEsoteric Currents</p>" -Chapters @(@{ title = 'European Esoteric Currents'; level = 2 })
            $result.HtmlContent | Should -Be '<h2>European Esoteric Currents</h2>'
            $result.Inserted | Should -Be 1
        }

        It 'does not change numbered h3 labels or body paragraphs without a matching chapter title' {
            $html = '<h3>1</h3><h3>Introduction</h3><p>Introduction discusses the purpose of this book.</p>'
            $result = Update-HtmlChapterHeadings -HtmlContent $html -Chapters @(@{ title = 'Introduction'; level = 2 })
            $result.HtmlContent | Should -Be '<h3>1</h3><h2>Introduction</h2><p>Introduction discusses the purpose of this book.</p>'
        }
    }
}
