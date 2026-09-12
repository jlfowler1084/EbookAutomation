#Requires -Modules Pester
Import-Module (Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1') -Force

Describe 'Local-first text routing' {
    InModuleScope EbookAutomation {
        BeforeEach {
            $script:TextLLMProbes = @{}
            $script:savedTextEnv = @{}
            foreach ($key in @('EBOOK_TEXT_PROVIDER', 'LOCAL_LLM_TEXT_BASE_URL', 'LOCAL_LLM_TEXT_MODEL', 'ANTHROPIC_API_KEY', 'EBOOK_OCR_PROVIDER')) {
                $script:savedTextEnv[$key] = [Environment]::GetEnvironmentVariable($key)
                [Environment]::SetEnvironmentVariable($key, $null)
            }
            Mock Get-EbookConfig { [pscustomobject]@{ llm = @{ text = @{} } } }
            Mock Write-EbookLog {}
            Mock Send-ToClaudeAPI { 'cloud' }
            Mock Invoke-RestMethod { @{ choices = @(@{ finish_reason = 'stop'; message = @{ content = 'local' } }) } }
        }
        AfterEach {
            foreach ($key in $script:savedTextEnv.Keys) {
                [Environment]::SetEnvironmentVariable($key, $script:savedTextEnv[$key])
            }
        }
        It 'uses local with a paid key present' {
            $env:ANTHROPIC_API_KEY = 'must-not-select-cloud'
            Send-ToTextLLM -SystemPrompt 'Classify.' -UserMessage 'Book' | Should -Be 'local'
            Should -Invoke Invoke-RestMethod -Times 1 -Exactly -ParameterFilter { $Uri -eq 'http://localhost:8000/v1/chat/completions' }
            Should -Invoke Send-ToClaudeAPI -Times 0
        }
        It 'does not fall back to cloud when local is unavailable' {
            Mock Invoke-RestMethod { throw 'local offline' }
            Send-ToTextLLM -SystemPrompt 'Classify.' -UserMessage 'Book' | Should -BeNullOrEmpty
            Should -Invoke Send-ToClaudeAPI -Times 0
        }
        It 'uses cloud only with explicit provider selection' {
            $env:EBOOK_TEXT_PROVIDER = 'claude'
            Send-ToTextLLM -SystemPrompt 'Classify.' -UserMessage 'Book' | Should -Be 'cloud'
            Should -Invoke Send-ToClaudeAPI -Times 1 -Exactly
            Should -Invoke Invoke-RestMethod -Times 0
        }
        It 'rejects truncated local output' {
            Mock Invoke-RestMethod { @{ choices = @(@{ finish_reason = 'length'; message = @{ content = 'partial' } }) } }
            Send-ToTextLLM -SystemPrompt 'Classify.' -UserMessage 'Book' | Should -BeNullOrEmpty
            Should -Invoke Send-ToClaudeAPI -Times 0
        }
        It 'honors the disabled text setting without any request' {
            Mock Get-EbookConfig { @{ llm = @{ text = @{ enabled = $false } } } }
            Send-ToTextLLM -SystemPrompt 'Classify.' -UserMessage 'Book' | Should -BeNullOrEmpty
            Should -Invoke Invoke-RestMethod -Times 0
            Should -Invoke Send-ToClaudeAPI -Times 0
        }
        It 'defaults OCR to local independently of keys' {
            $env:ANTHROPIC_API_KEY = 'unused'
            Get-EbookOCRProvider | Should -Be 'local'
        }
        It 'lets explicit local OCR override cloud configuration' {
            Mock Get-EbookConfig { @{ llm = @{ ocr = @{ provider = 'gemini' } } } }
            $env:EBOOK_OCR_PROVIDER = 'local'
            Get-EbookOCRProvider | Should -Be 'local'
        }
        It 'retains explicitly configured cloud OCR' {
            Mock Get-EbookConfig { @{ llm = @{ ocr = @{ provider = 'gemini' } } } }
            Get-EbookOCRProvider | Should -Be 'gemini'
        }
        It 'rejects ambiguous whole-book and targeted OCR before conversion' {
            $result = Convert-ToKindle -InputFile 'unused.pdf' -OcrPages 2,4 -UseVision
            $result.Success | Should -BeFalse
            Should -Invoke Invoke-RestMethod -Times 0
        }
        It 'reads the final OCR provenance JSON from mixed extraction logs' {
            $logPath = Join-Path $TestDrive 'extraction.log'
            @('progress line', '{"unrelated":true}', '{"html_path":"book.html","ocr_remediation":{"provider":"local","applied_pages":[2,4],"failed_pages":[],"cost_usd":0,"provider_resolved":{"n_ctx":32768}}}') |
                Set-Content -LiteralPath $logPath -Encoding UTF8
            $result = Get-OcrRemediationFromLog -LogPath $logPath
            $result.applied_pages | Should -Be @(2, 4)
            $result.provider_resolved.n_ctx | Should -Be 32768
            Should -Invoke Write-EbookLog -Times 1 -ParameterFilter { $Message -like '*provider=local applied=[[]2,4[]] failed=[[][]] cost=$0.0000*' }
        }
        It 'returns no OCR provenance for ordinary extraction output' {
            $logPath = Join-Path $TestDrive 'ordinary.log'
            '{"html_path":"book.html","size":300}' | Set-Content -LiteralPath $logPath
            Get-OcrRemediationFromLog -LogPath $logPath | Should -BeNullOrEmpty
        }
    }
}
