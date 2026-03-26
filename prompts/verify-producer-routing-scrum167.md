# Prompt: Verify Producer Routing SCRUM-167

## Session Name
Verify Producer Routing SCRUM-167

## Claude Code Model
Use **Sonnet** — this is verification only, no code changes.

## Context
SCRUM-167 (Producer-based auto-routing — recommend Gemini for LuraDocument/Internet Archive PDFs) was run in a Claude Code session that may have been closed. We need to check if the changes were committed and pushed, and verify the implementation status.

## Steps

### 1. Check git log for SCRUM-167 related commits
```bash
git log --oneline -20
```
Look for any commits mentioning "producer", "routing", "SCRUM-167", "LuraDocument", "Internet Archive", or "Gemini recommendation".

### 2. Check classify_source.py for producer-based routing
```bash
grep -n "LuraDocument\|Internet Archive\|gemini\|recommended_strategies\|producer" tools/classify_source.py | head -30
```
If `classify_source.py` now returns `recommended_strategies: ['gemini']` for LuraDocument/IA producers, the work is done.

### 3. Check for any uncommitted changes
```bash
git status
git diff --stat
```

### 4. Report status
Tell me one of:
- **DONE**: Committed + pushed, show me the relevant commit hash and summary
- **PARTIALLY DONE**: Changes exist but uncommitted — show me what's staged/modified
- **NOT STARTED**: No evidence of SCRUM-167 implementation

Do NOT make any code changes. This is verification only.
