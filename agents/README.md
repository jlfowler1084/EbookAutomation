# EbookAutomation — Agent Framework

## Overview

This directory contains specialized AI sub-agents that handle distinct responsibilities in the EbookAutomation pipeline. Each agent has a focused mandate, a defined input/output contract, and explicit boundaries on what it does NOT do.

The framework follows a simple principle: **better results come from constrained specialists, not unconstrained generalists.**

## Directory Structure

```
agents/
├── README.md                          ← You are here — framework overview
├── structure-analysis/                ← Chapter/heading detection specialist
│   ├── system-prompt.md              ← The agent's system prompt (sent to Claude API)
│   ├── contract.md                   ← Input/output contract + boundaries
│   └── examples/                     ← Known-good input/output pairs for testing
│       ├── oil-kings-input.txt       ← (future) sample input text
│       └── oil-kings-expected.json   ← (future) expected chapter map output
├── tts-preparation/                   ← (future) Voice tagging + SSML specialist
│   ├── system-prompt.md
│   └── contract.md
├── document-intake/                   ← (future) Source classification + text extraction
│   ├── system-prompt.md
│   └── contract.md
├── qa-evaluation/                     ← Visual quality evaluation specialist
│   ├── system-prompt.md              ← The agent's system prompt (enhanced rubric)
│   ├── contract.md                   ← Input/output contract + boundaries
│   └── examples/                     ← Known-good evaluation examples
└── foh-brief/                         ← (future) FOH daily brief generation specialist
    ├── system-prompt.md
    └── contract.md
```

## How Agents Work

### The Three Files

Every agent has at minimum:

1. **`system-prompt.md`** — The complete system prompt sent to Claude via the API. This is the agent's "brain." It defines what the agent knows, how it thinks, and what it produces. Written in second person ("You are the Structure Analysis Agent...").

2. **`contract.md`** — The interface specification. Defines the exact input format the agent expects, the exact output format it produces, failure modes, and which other components consume its output. This is the document *other agents and pipeline code* reference.

3. **`examples/`** — (Optional) Known-good input/output pairs for regression testing. When you improve a system prompt, run it against these examples to verify you haven't broken existing behavior.

### Calling an Agent

Agents are called through `Send-ToClaudeAPI` with the system prompt loaded from file:

```powershell
# Load the agent's system prompt
$agentPrompt = Get-Content "agents/structure-analysis/system-prompt.md" -Raw -Encoding UTF8

# Call the agent with scoped input
$result = Send-ToClaudeAPI -SystemPrompt $agentPrompt -UserMessage $inputText
```

The wrapper function (e.g., `Get-ChapterStructure`) handles:
- Input assembly (sampling, font candidate formatting)
- API call via `Send-ToClaudeAPI`
- Output parsing (JSON extraction)
- Error handling and fallback

### Model Selection

| Agent | Default Model | When to Use Opus |
|-------|--------------|------------------|
| Structure Analysis | claude-sonnet-4-6 | Books with ambiguous structure, unusual formatting, or >20 chapters |
| TTS Preparation | claude-sonnet-4-6 | Complex dialogue attribution or mixed-language text |
| QA Evaluation | claude-sonnet-4-6 | Evaluating subtle rendering issues |

## Adding a New Agent

1. Create the directory: `agents/<agent-name>/`
2. Write `system-prompt.md` — focus on: mandate, input format, output format, false positive patterns, failure modes
3. Write `contract.md` — define the interface that other components will code against
4. Create or modify the PowerShell wrapper function that loads the prompt and calls `Send-ToClaudeAPI`
5. Add example input/output pairs in `examples/` for regression testing
6. Update this README with the new agent's entry

## Design Principles

1. **Isolation over convenience.** Each agent should be callable independently. If you can't test an agent without running the full pipeline, the boundaries are wrong.

2. **Prompts are code.** System prompts live in version-controlled files, not inline strings. When you improve an agent, the diff is visible in Git just like a code change.

3. **Contracts are sacred.** If you change an agent's output format, you must update every downstream consumer. The contract.md documents these dependencies explicitly.

4. **Fail gracefully.** Every agent must handle: API failures, unexpected input formats, and edge cases. The pipeline should never crash because an agent returned unexpected output — it should log, fall back, and continue.

5. **Examples are tests.** Every agent should accumulate known-good examples over time. These become your regression suite — run new prompts against old examples before deploying.
