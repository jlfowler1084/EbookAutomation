# Agent Framework: QA Evaluation Agent — Externalize Rubric

## Session Name
QA Evaluation Agent Setup

## Overview
Add the QA Evaluation Agent to the `agents/` directory framework. Update `visual_qa.py` to load its rubric from the new agent prompt file instead of `tools/visual_qa_rubric.md`. The old rubric file stays as a fallback.

## Claude Code Model
Sonnet — straightforward file creation + path update in visual_qa.py.

## Prerequisites
The `agents/` directory and `agents/README.md` must already exist from the Structure Analysis Agent setup. If they don't, create them first using `prompts/agent-framework-setup.md`.

## Steps

### 1. Create the QA Evaluation Agent directory

```
F:\Projects\EbookAutomation\agents\qa-evaluation\
F:\Projects\EbookAutomation\agents\qa-evaluation\examples\
```

### 2. Copy agent files into place

Copy the following files from `prompts/` into the agents directory:
- `agents/qa-evaluation/system-prompt.md` — the agent's system prompt (enhanced rubric)
- `agents/qa-evaluation/contract.md` — input/output contract

The contents of these two files are provided as downloads from the Claude.ai conversation. They should already be in the `agents/qa-evaluation/` directory if the download/copy step was followed.

### 3. Update visual_qa.py to prefer the agent prompt file

In `tools/visual_qa.py`, find the `run_visual_qa()` function. It currently loads the rubric like this:

```python
rubric_path = Path(rubric_path)
if not rubric_path.exists():
    raise FileNotFoundError(f"Rubric file not found: {rubric_path}")
rubric_text = rubric_path.read_text(encoding='utf-8')
```

Replace that rubric loading block with logic that prefers the agent prompt file, falling back to the legacy rubric:

```python
# Prefer agent framework prompt, fall back to legacy rubric
agent_prompt_path = Path(__file__).resolve().parent.parent / 'agents' / 'qa-evaluation' / 'system-prompt.md'
legacy_rubric_path = Path(rubric_path)

if agent_prompt_path.exists():
    rubric_text = agent_prompt_path.read_text(encoding='utf-8')
    logger.info("Loaded QA agent prompt from %s", agent_prompt_path)
elif legacy_rubric_path.exists():
    rubric_text = legacy_rubric_path.read_text(encoding='utf-8')
    logger.info("Loaded legacy rubric from %s (agent prompt not found)", legacy_rubric_path)
else:
    raise FileNotFoundError(
        f"No QA rubric found. Checked:\n"
        f"  Agent prompt: {agent_prompt_path}\n"
        f"  Legacy rubric: {legacy_rubric_path}"
    )
```

**Important:** Do NOT delete `tools/visual_qa_rubric.md`. It stays as a fallback and for backward compatibility. The agent prompt file is the preferred source going forward.

### 4. Update the default rubric path in settings.json reference

In `visual_qa.py`, find where it reads `default_rubric` from settings.json. Add a comment noting the precedence:

```python
# Note: visual_qa.py now prefers agents/qa-evaluation/system-prompt.md over this path.
# This setting is used as a fallback only.
default_rubric = vqa_settings.get("rubric_path", r"tools\visual_qa_rubric.md")
```

### 5. Update agents/README.md

Add the QA Evaluation Agent to the directory structure listing and the agent table:

In the directory structure section, add:

```
├── qa-evaluation/                     ← Visual quality evaluation specialist
│   ├── system-prompt.md              ← The agent's system prompt (enhanced rubric)
│   ├── contract.md                   ← Input/output contract + boundaries
│   └── examples/                     ← Known-good evaluation examples
```

### 6. Update CLAUDE.md

Add to the Agent Framework table:

```
| QA Evaluation | `agents/qa-evaluation/` | `Test-ConversionQuality`, `visual_qa.py` | Visual quality evaluation of rendered ebook pages |
```

### 7. Git commit and push

```
git add agents/qa-evaluation/ tools/visual_qa.py CLAUDE.md agents/README.md
git commit -m "feat: QA Evaluation Agent added to agent framework

- New agents/qa-evaluation/ with system-prompt.md and contract.md
- Enhanced rubric with detailed scoring tables, severity weights, common mistakes
- visual_qa.py now prefers agent prompt file over legacy tools/visual_qa_rubric.md
- Legacy rubric preserved as fallback for backward compatibility
- Contract documents: input format, output schema, downstream consumers, cost profile
- CLAUDE.md and agents/README.md updated"
git push
```

---

## What Changed From the Legacy Rubric

The new `system-prompt.md` in the agent framework is an enhanced version of the original `tools/visual_qa_rubric.md`. Key improvements:

1. **Agent identity and mandate section** — clearly scopes what the agent owns and doesn't own
2. **Detailed scoring tables per category** — explicit score ranges (90-100, 70-89, etc.) with meanings
3. **"Do NOT penalize" guidance** — prevents over-scoring academic books and intentional formatting
4. **Common evaluation mistakes section** — documents failure patterns seen in practice
5. **Severity deduction values** — explicit point deductions (critical: -25, major: -15, moderate: -10, minor: -5)
6. **Page type classification** — agent identifies page types (cover, toc, body, etc.) for better downstream analysis
7. **TOC evaluation scoping** — only evaluate TOC on pages that show it, don't penalize body pages

The output JSON schema is fully backward-compatible with what `visual_qa.py` already parses.
