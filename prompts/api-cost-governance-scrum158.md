# Prompt: API Cost Governance — SCRUM-158

## Session Name
API Cost Governance SCRUM-158

## Claude Code Model
Use **Sonnet** — this is config wiring + find-and-replace across files, not architectural design.

## Context
Full API cost audit found 8+ paid API call sites across 4 files. Four calls use Sonnet for simple classification tasks where Haiku would suffice. All model strings are hardcoded. Goal: centralize model config in settings.json, downgrade 4 calls to Haiku (~70% savings each), and add a rules-based gate to skip AI quality pass when not needed.

Current monthly cost (10 books): ~$1.50-3.00/mo
Target after optimizations: ~$0.45-0.90/mo (~60-70% reduction)

## Implementation — Execute in order

### P1: Add `api_models` section to config/settings.json

Add a new top-level `api_models` key to `config/settings.json`:

```json
"api_models": {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-20250514",
    "gemini_flash": "gemini-2.5-flash"
}
```

Do NOT restructure any existing settings.json keys. Just add this new section.

### P2: Make pdf_to_balabolka.py read models from config

Find every hardcoded model string in `tools/pdf_to_balabolka.py`. There should be ~4 call sites for Claude API calls. For each one:

1. Read the model from settings.json via the existing config loader (find how the file currently loads settings — there should be a `load_settings()` or similar function)
2. Replace the hardcoded model string with config lookup

**Downgrade these 4 functions from Sonnet to Haiku:**
- `ai_detect_subheadings()` → reads `api_models.haiku`
- `ai_rejoin_fragments()` → reads `api_models.haiku`
- `ai_quality_pass()` detection call → reads `api_models.haiku`
- `ai_quality_pass()` verification call → reads `api_models.haiku`

**These STAY on Sonnet (do not downgrade):**
- Chapter detection / `Get-ChapterStructure` — multi-level hierarchy reasoning
- Visual QA rubric scoring — vision + nuanced assessment
- Claude Vision extraction (Tier 3) — premium OCR, explicit opt-in

### P3: Make EbookAutomation.psm1 read model from config

Find `Send-ToClaudeAPI` in `module/EbookAutomation.psm1`. It likely has a hardcoded default model string. Change it to read from `settings.json` `api_models.sonnet` as the default, falling back to the current hardcoded value if the config key doesn't exist.

### P4: Make visual_qa.py read model from config

Find the model string in `tools/visual_qa.py`. It should stay on Sonnet (vision + nuanced assessment) but read from `api_models.sonnet` in settings.json instead of hardcoded.

### P5: Make gemini_ocr.py read model from config

Find model strings in `tools/gemini_ocr.py` (likely 1-2 Gemini model references). Read from `api_models.gemini_flash` in settings.json.

### P6: Add rules-based gate before AI Quality Pass

In `pdf_to_balabolka.py`, before the `ai_quality_pass()` function makes API calls, add a pre-check:

1. Run regex checks for known artifacts: ligature splits (`ﬁ`/`ﬂ` → `fi`/`fl`), encoding errors (`â€™` → `'`), garbled Unicode
2. If zero regex-detected issues are found, skip the AI quality pass entirely
3. Log: `"  AI Quality Pass: skipped (no regex-detected issues)"` when gate bypasses
4. Log: `"  AI Quality Pass: {N} regex issues found, running AI verification"` when gate allows

### P7: Create governance docs

Create `docs/api-registry.md` with a table documenting ALL API call sites:

| File | Function | Model | Purpose | Cost/call |
|------|----------|-------|---------|-----------|
| pdf_to_balabolka.py | ai_detect_subheadings() | Haiku | Classify ALL CAPS candidates | ~$0.001 |
| ... | ... | ... | ... | ... |

Populate by scanning all files for API calls (search for `anthropic`, `claude`, `gemini`, `api.anthropic.com`, `generativelanguage`).

Also add an "API Cost Governance" section to `CLAUDE.md`:
```
## API Cost Governance
- All model strings are centralized in config/settings.json under `api_models`
- Never hardcode model strings — always read from config
- Use Haiku for classification, detection, and simple extraction tasks
- Use Sonnet for reasoning, chapter detection, and vision tasks
- Update docs/api-registry.md when adding or changing API call sites
```

### P8: Git commit and push

```bash
git add -A
git commit -m "feat: API cost governance — config-driven models, Haiku downgrades, quality gate

SCRUM-158: Centralized all model strings in settings.json api_models section.
Downgraded 4 Sonnet calls to Haiku (subheadings, rejoin, quality pass).
Added regex pre-gate to skip AI quality pass when no issues detected.
Created docs/api-registry.md documenting all API call sites.
~60-70% cost reduction on auto-triggered API calls."
git push
```

## Important
- Do NOT restructure settings.json schema — only ADD the `api_models` key
- Do NOT change any API call logic, prompts, or behavior — only the model selection
- Do NOT downgrade chapter detection, VQA scoring, or Vision extraction — these need Sonnet
- Preserve backward compatibility: if `api_models` key is missing from config, fall back to current hardcoded defaults
- Use Python 3.12 for any testing (`py -3.12`)
- Run test suite after changes: `py -3.12 tools/test_pipeline.py`
