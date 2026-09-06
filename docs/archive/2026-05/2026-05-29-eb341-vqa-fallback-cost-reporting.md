# EB-341: VQA Fallback Cost-Reporting Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make VQA report and persist an authoritative total cost (local + Claude fallback) so the CLI summary and the conversion DB stop under-reporting whenever the Claude fallback fires.

**Architecture:** `build_report` currently writes `token_usage.estimated_cost_usd` as the *primary-provider* cost only, and adds `fallback_estimated_cost_usd` as a separate field when the fallback fires — but never sums them. Add a canonical `token_usage.total_estimated_cost_usd` (primary + fallback), preserve the existing breakdown fields for backward compatibility, and update the two consumers (CLI summary, DB persistence) to read the canonical total with a legacy fallback.

**Tech Stack:** Python 3.12 (pytest), PowerShell module (`.psm1`) with an embedded Python persistence heredoc. Project test command: `python -m pytest tests/`.

**Prerequisite / sequencing:** EB-341 is the standalone blocker for EB-340 and the tiered-VQA work. It ships first, on its own worktree branch, before any tiering code.

**Worktree:** This touches `tools/visual_qa.py` and `module/EbookAutomation.psm1` (multi-file code change) — create an isolated worktree first via the `superpowers:using-git-worktrees` / `worktree-management` skill. Suggested branch: `fix/EB-341-vqa-fallback-cost`.

---

## File Structure

- **Modify** `tools/visual_qa.py`
  - `build_report` (~L718–743): add `total_estimated_cost_usd` to the `token_usage` dict; keep `estimated_cost_usd` (primary) and `fallback_estimated_cost_usd` (fallback) as breakdown fields.
  - CLI summary `print(...)` block (~L1416–1424): emit the canonical total.
- **Modify** `module/EbookAutomation.psm1`
  - DB persistence heredoc (~L2316–2321): read `total_estimated_cost_usd`, falling back to `estimated_cost_usd` for legacy reports.
- **Modify** `tools/import_vqa_reports.py` (~L100) and `tools/pattern_db.py` (~L1970)
  - Report-import / pattern-DB cost reads: same legacy-safe total read so re-imported reports do not re-introduce the under-report.
- **Modify** `tests/test_visual_qa_hybrid_routing.py`
  - Add `TestFallbackCostTotal` — locks the summation contract and legacy/no-fallback behavior.

---

## Task 1: Canonical total cost in `build_report`

**Files:**
- Modify: `tools/visual_qa.py:718-743`
- Test: `tests/test_visual_qa_hybrid_routing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visual_qa_hybrid_routing.py`:

```python
class TestFallbackCostTotal:
    """EB-341: token_usage.total_estimated_cost_usd is the authoritative
    local + fallback total. Breakdown fields are preserved."""

    _QA_DATA = {
        "evaluation_status": "evaluated",
        "overall_score": 90,
        "category_scores": {},
        "pages": [],
        "summary": "ok",
        "top_issues": [],
    }

    def test_total_equals_primary_when_no_fallback(self):
        # provider=None -> legacy sonnet pricing: in*3/M + out*15/M
        report = visual_qa.build_report(
            "Book.kfx", self._QA_DATA, total_pages=10, pages_sampled=8,
            dpi=100, model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=1000,
        )
        tu = report["token_usage"]
        # (1000/1e6)*3 + (1000/1e6)*15 = 0.018
        assert tu["estimated_cost_usd"] == 0.018
        assert tu["total_estimated_cost_usd"] == 0.018
        assert "fallback_estimated_cost_usd" not in tu

    def test_total_sums_primary_and_fallback(self):
        report = visual_qa.build_report(
            "Book.kfx", self._QA_DATA, total_pages=10, pages_sampled=8,
            dpi=100, model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=1000,
            fallback_tokens=(500, 200), fallback_cost_usd=0.05,
            fallback_provider_name="claude", fallback_model="claude-sonnet-4-6",
        )
        tu = report["token_usage"]
        assert tu["estimated_cost_usd"] == 0.018          # primary preserved
        assert tu["fallback_estimated_cost_usd"] == 0.05  # breakdown preserved
        assert tu["total_estimated_cost_usd"] == 0.068     # 0.018 + 0.05
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_visual_qa_hybrid_routing.py::TestFallbackCostTotal -v`
Expected: FAIL — `KeyError: 'total_estimated_cost_usd'` (field does not exist yet).

- [ ] **Step 3: Add the canonical total to the primary `token_usage` block**

In `tools/visual_qa.py`, change the `token_usage` dict in `build_report` (currently L718–722):

```python
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 4),
            "total_estimated_cost_usd": round(estimated_cost, 4),
        }
```

(When no fallback fires, the total equals the primary cost.)

- [ ] **Step 4: Include fallback cost in the total when the fallback fired**

In `build_report`, in the `if fallback_tokens is not None:` block (currently L731–741), after setting `fallback_estimated_cost_usd`, recompute the canonical total:

```python
    if fallback_tokens is not None:
        fb_in, fb_out = fallback_tokens
        report["token_usage"]["fallback_input_tokens"] = fb_in
        report["token_usage"]["fallback_output_tokens"] = fb_out
        report["token_usage"]["fallback_estimated_cost_usd"] = round(
            fallback_cost_usd or 0.0, 4
        )
        report["token_usage"]["total_estimated_cost_usd"] = round(
            estimated_cost + (fallback_cost_usd or 0.0), 4
        )
        if fallback_provider_name:
            report["token_usage"]["fallback_provider"] = fallback_provider_name
        if fallback_model:
            report["token_usage"]["fallback_model"] = fallback_model
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_visual_qa_hybrid_routing.py::TestFallbackCostTotal -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full hybrid-routing suite to confirm no regression**

Run: `python -m pytest tests/test_visual_qa_hybrid_routing.py -v`
Expected: PASS (all existing tests still green — the change is additive).

- [ ] **Step 7: Commit**

```bash
git add tools/visual_qa.py tests/test_visual_qa_hybrid_routing.py
git commit -m "fix(EB-341): add canonical total_estimated_cost_usd to VQA report"
```

---

## Task 2: CLI summary reports the canonical total

**Files:**
- Modify: `tools/visual_qa.py:1416-1424`

- [ ] **Step 1: Write the failing test**

Append to `TestFallbackCostTotal` in `tests/test_visual_qa_hybrid_routing.py`:

```python
    def test_cli_summary_key_is_total(self):
        """The CLI summary dict must expose the canonical total, not the
        primary-only field, so a fallback run is not under-reported."""
        import inspect
        src = inspect.getsource(visual_qa.main)
        assert '"total_estimated_cost_usd"' in src or \
               "report[\"token_usage\"][\"total_estimated_cost_usd\"]" in src
        # Guard against the old primary-only read remaining as the summary value.
        assert '"estimated_cost_usd": report["token_usage"]["estimated_cost_usd"]' not in src
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest "tests/test_visual_qa_hybrid_routing.py::TestFallbackCostTotal::test_cli_summary_key_is_total" -v`
Expected: FAIL — the summary still reads the primary-only `estimated_cost_usd`.

- [ ] **Step 3: Update the CLI summary print block (legacy-safe read)**

In `tools/visual_qa.py`, change the summary `print(json.dumps({...}))` block (currently the `"estimated_cost_usd"` line at L1423). Use a legacy-safe `.get` chain so any test that mocks `run_visual_qa` with a report carrying only `estimated_cost_usd` (no canonical total) does not `KeyError`:

```python
        # Print summary to stdout
        _tu = report["token_usage"]
        print(json.dumps({
            "book": report["book"],
            "overall_score": report["overall_score"],
            "overall_pass": report["overall_pass"],
            "pages_sampled": report["pages_sampled"],
            "pages_total": report["pages_total"],
            "summary": report["summary"],
            "estimated_cost_usd": _tu.get("total_estimated_cost_usd", _tu.get("estimated_cost_usd", 0)),
        }, indent=2))
```

(Key name kept as `estimated_cost_usd` for output-shape stability; the *value* is now the authoritative total, with a legacy fallback for reports/mocks that predate the canonical field.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest "tests/test_visual_qa_hybrid_routing.py::TestFallbackCostTotal::test_cli_summary_key_is_total" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/visual_qa.py tests/test_visual_qa_hybrid_routing.py
git commit -m "fix(EB-341): CLI summary reports total VQA cost incl. fallback"
```

---

## Task 3: DB persistence reads the canonical total (with legacy fallback)

**Files:**
- Modify: `module/EbookAutomation.psm1:2316-2321`

The persistence code is an embedded Python heredoc inside the PowerShell module. Legacy
reports (produced before Task 1) have no `total_estimated_cost_usd`, so the read must
fall back to `estimated_cost_usd`.

- [ ] **Step 1: Update the embedded persistence read**

In `module/EbookAutomation.psm1`, change the `cost_usd` line (currently L2321):

```python
    conv_kwargs['cost_usd'] = tu.get('total_estimated_cost_usd', tu.get('estimated_cost_usd', 0))
```

- [ ] **Step 2: Verify the module parses and the function is exported**

Run:
```powershell
pwsh -NoProfile -Command "Import-Module ./module/EbookAutomation.psm1 -Force; if (Get-Command Convert-PdfToKindle) { 'MODULE OK' }"
```
Expected: prints `MODULE OK` with no parse errors.

- [ ] **Step 3: Verify the legacy-fallback expression in isolation**

Run (proves the `.get` chain handles both new and legacy report shapes):
```powershell
py -3.12 -c "tu_new={'total_estimated_cost_usd':0.068,'estimated_cost_usd':0.018}; tu_old={'estimated_cost_usd':0.018}; assert tu_new.get('total_estimated_cost_usd', tu_new.get('estimated_cost_usd',0))==0.068; assert tu_old.get('total_estimated_cost_usd', tu_old.get('estimated_cost_usd',0))==0.018; print('DB READ OK')"
```
Expected: prints `DB READ OK`.

- [ ] **Step 4: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "fix(EB-341): DB persistence reads total VQA cost, legacy-safe"
```

---

## Task 4: Report-import consumers read the canonical total

**Files:**
- Modify: `tools/import_vqa_reports.py:100`
- Modify: `tools/pattern_db.py:1970`

Both the report-import path and the pattern DB read `token_usage.estimated_cost_usd`
directly. If new reports are imported/replayed into the DB later, they would re-introduce
the under-report. Apply the same legacy-safe total read.

- [ ] **Step 1: Update `import_vqa_reports.py`**

In `tools/import_vqa_reports.py`, change the cost read (currently L100):

```python
    cost = token_usage.get("total_estimated_cost_usd", token_usage.get("estimated_cost_usd", 0))
```

- [ ] **Step 2: Update `pattern_db.py`**

In `tools/pattern_db.py`, change the `cost_usd` argument (currently L1970):

```python
        cost_usd=token_usage.get("total_estimated_cost_usd", token_usage.get("estimated_cost_usd", 0)),
```

- [ ] **Step 3: Verify both modules import cleanly**

Run:
```powershell
py -3.12 -c "import sys; sys.path.insert(0,'tools'); import import_vqa_reports, pattern_db; print('IMPORTS OK')"
```
Expected: prints `IMPORTS OK` with no error.

- [ ] **Step 4: Verify the legacy-fallback read on both report shapes**

Run:
```powershell
py -3.12 -c "tu_new={'total_estimated_cost_usd':0.068,'estimated_cost_usd':0.018}; tu_old={'estimated_cost_usd':0.018}; r=lambda tu: tu.get('total_estimated_cost_usd', tu.get('estimated_cost_usd',0)); assert r(tu_new)==0.068 and r(tu_old)==0.018; print('IMPORT READ OK')"
```
Expected: prints `IMPORT READ OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/import_vqa_reports.py tools/pattern_db.py
git commit -m "fix(EB-341): report-import + pattern DB read total VQA cost, legacy-safe"
```

---

## Task 5: Full regression + manifest verification

**Files:** none (verification only)

- [ ] **Step 1: Run the visual-QA test suite**

Run: `python -m pytest tests/test_visual_qa_hybrid_routing.py tests/test_visual_qa_page_alignment.py -v`
Expected: PASS (all green).

- [ ] **Step 2: Run the project test command**

Run: `python -m pytest tests/`
Expected: PASS (no new failures vs the pre-change baseline).

- [ ] **Step 3: Verify the feature manifest is intact**

Run: `powershell -File tools\verify-manifest.ps1 -Verbose`
Expected: no removed/truncated functions, files, or config keys.

- [ ] **Step 4: Final commit (if manifest or test artifacts changed)**

```bash
git add -A
git commit -m "test(EB-341): full regression + manifest verification green"
```

---

## Self-Review

**Spec coverage (EB-341 scope from the design doc):**
- Canonical `token_usage.total_estimated_cost_usd` → Task 1. ✓
- Provider-separated breakdown preserved (`estimated_cost_usd`, `fallback_estimated_cost_usd`) → Task 1 keeps both. ✓
- CLI under-reporting (visual_qa.py:1423), legacy-safe `.get` read → Task 2. ✓
- DB under-reporting (EbookAutomation.psm1:2321), legacy-safe → Task 3. ✓
- Report-import consumers (import_vqa_reports.py:100, pattern_db.py:1970), legacy-safe → Task 4. ✓
- Regression safety / manifest → Task 5. ✓

**Placeholder scan:** No TBD/TODO; every code step shows exact code; every command has expected output. ✓

**Type/name consistency:** `total_estimated_cost_usd` used identically in Tasks 1–3; `estimated_cost_usd` (primary) and `fallback_estimated_cost_usd` (breakdown) names match the existing `build_report` fields. ✓

**Out of scope (deferred to later units):** tier policy, full coverage, adjudication, batch auto-enable, re-baseline. EB-341 is cost-accounting only.
