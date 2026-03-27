# SCRUM-125: Multi-Extractor Comparison

## Session Name
SCRUM-125 Multi-Extractor Comparison

## Claude Code Model
Opus

## Jira
SCRUM-125 — In Progress

## Overview
When Tier 1 extraction scores borderline (60-80), run all three available text extractors (pypdf, pdfminer, PyMuPDF) in parallel, score each, and pick the winner automatically. This is a fast within-extraction comparison — not a full converge loop iteration — that adds ~10-15 seconds to catch cases where one extractor handles a particular PDF much better than the default choice.

**CRITICAL**: `pdf_to_balabolka.py` is 11,000+ lines. Use `grep -n` to find exact locations — never guess line numbers.

## Project Root
`F:\Projects\EbookAutomation\`

---

## Architecture Decision

The multi-extractor comparison lives as a **standalone function** that can be called from:
1. `process_kindle_html()` — between Tier 1 extraction and Tier 2 OCR escalation
2. `extract_text()` — for the non-HTML (balabolka) text path

It does NOT replace the converge loop. The converge loop tries different strategies across full convert→VQA iterations. This comparison is faster: raw text extraction → quality score → pick winner, all within a single pipeline step.

**Trigger condition**: Tier 1 quality score is 60-80 (borderline). Below 60 goes straight to Tier 2 OCR escalation. Above 80 is good enough — no comparison needed.

**Configurable**: Off by default in regular pipeline, opt-in via `--compare-extractors` flag. Always available to the converge loop.

---

## Part 1: The `compare_extractors()` Function

Add this function near the other extraction functions in `pdf_to_balabolka.py` (grep for `def extract_text_auto` to find the right neighborhood — around line 2120):

```python
def compare_extractors(pdf_path, log, current_text=None, current_score=None,
                       current_extractor=None, force_columns=False):
    """Run all available Tier 1 extractors and pick the best result.

    Tries up to 3 extractors (pypdf, pdfminer, PyMuPDF), scores each with
    score_text_layer_quality(), and returns the winner. If current_text is
    provided (from a prior extraction attempt), it's included in the comparison
    without re-running that extractor.

    Args:
        pdf_path: Path to the PDF file
        log: Logging function
        current_text: Optional text from an already-completed extraction
        current_score: Optional quality score from the already-completed extraction
        current_extractor: Name of the already-completed extractor ('pypdf', 'pdfminer', 'pymupdf')
        force_columns: If True, include PyMuPDF column-aware in comparison

    Returns:
        dict with keys:
            'winner': str — name of winning extractor
            'text': str — extracted text from winner
            'score': int — quality score of winner
            'comparison': dict — all extractor results: {name: {'score': int, 'word_count': int, 'time_seconds': float}}
            'improved': bool — True if a different extractor beat the current one
    """
    import time as _t

    results = {}

    # Include current result if provided
    if current_text and current_extractor:
        results[current_extractor] = {
            'text': current_text,
            'score': current_score or 0,
            'word_count': len(current_text.split()),
            'time_seconds': 0,  # already completed
        }

    # Define extractors to try
    extractors = []

    # 1. pypdf — fast, handles simple PDFs well
    if current_extractor != 'pypdf':
        def _extract_pypdf():
            try:
                from pypdf import PdfReader
            except ImportError:
                return None
            reader = PdfReader(pdf_path)
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append(f"<<PAGE:{i+1}>>\n{text}")
            return "\n".join(pages) if pages else None
        extractors.append(('pypdf', _extract_pypdf))

    # 2. pdfminer — handles complex font encodings better
    if current_extractor != 'pdfminer':
        def _extract_pdfminer():
            try:
                from pdfminer.layout import LAParams
                from pdfminer.pdfpage import PDFPage
                from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
                from pdfminer.converter import TextConverter
            except ImportError:
                return None
            import io
            laparams = LAParams()
            all_pages = []
            with open(pdf_path, 'rb') as f:
                for i, page in enumerate(PDFPage.get_pages(f)):
                    rsrcmgr = PDFResourceManager()
                    output = io.StringIO()
                    device = TextConverter(rsrcmgr, output, laparams=laparams)
                    interpreter = PDFPageInterpreter(rsrcmgr, device)
                    try:
                        interpreter.process_page(page)
                        text = output.getvalue()
                        if text and text.strip():
                            all_pages.append(f"<<PAGE:{i+1}>>\n{text}")
                    except Exception:
                        pass
                    device.close()
                    output.close()
            return "\n".join(all_pages) if all_pages else None
        extractors.append(('pdfminer', _extract_pdfminer))

    # 3. PyMuPDF — best for multi-column, also good for clean PDFs
    if current_extractor != 'pymupdf':
        def _extract_pymupdf():
            try:
                import pymupdf
            except ImportError:
                return None
            doc = pymupdf.open(pdf_path)
            pages = []
            for pg_idx in range(len(doc)):
                page = doc[pg_idx]
                text = page.get_text("text")
                if text and text.strip():
                    pages.append(f"<<PAGE:{pg_idx+1}>>\n{text}")
            doc.close()
            return "\n".join(pages) if pages else None
        extractors.append(('pymupdf', _extract_pymupdf))

    # Run each extractor and score
    log(f"  Multi-extractor comparison: testing {len(extractors)} additional extractor(s)...")

    for name, func in extractors:
        start = _t.time()
        try:
            text = func()
            elapsed = round(_t.time() - start, 1)
            if text and len(text.strip()) >= 100:
                quality = score_text_layer_quality(text)
                score = quality.get('score', 0) if quality else 0
                word_count = len(text.split())
                results[name] = {
                    'text': text,
                    'score': score,
                    'word_count': word_count,
                    'time_seconds': elapsed,
                }
                log(f"    {name}: score={score}/100, words={word_count}, time={elapsed}s")
            else:
                log(f"    {name}: insufficient text output ({elapsed}s)")
        except Exception as e:
            elapsed = round(_t.time() - start, 1)
            log(f"    {name}: failed ({e}) ({elapsed}s)")

    if not results:
        log(f"  No extractors produced usable output")
        return {
            'winner': current_extractor or 'none',
            'text': current_text or '',
            'score': current_score or 0,
            'comparison': {},
            'improved': False,
        }

    # Pick the winner (highest score, ties broken by word count)
    winner_name = max(results.keys(),
                      key=lambda k: (results[k]['score'], results[k]['word_count']))
    winner = results[winner_name]

    improved = (winner_name != current_extractor) if current_extractor else False
    improvement = winner['score'] - (current_score or 0)

    if improved:
        log(f"  Winner: {winner_name} (score={winner['score']}/100, "
            f"+{improvement} over {current_extractor})")
    else:
        log(f"  Original extractor wins: {winner_name} (score={winner['score']}/100)")

    # Build comparison summary (without full text, for diagnostics)
    comparison = {
        name: {
            'score': r['score'],
            'word_count': r['word_count'],
            'time_seconds': r['time_seconds'],
        }
        for name, r in results.items()
    }

    return {
        'winner': winner_name,
        'text': winner['text'],
        'score': winner['score'],
        'comparison': comparison,
        'improved': improved,
    }
```

---

## Part 2: Wire into `process_kindle_html()` (HTML Extraction Path)

Find the section in `process_kindle_html()` between the Tier 1 quality scoring and the Tier 2 OCR escalation. Grep for `STEP 1e: Auto-escalation` to find the exact location.

The current flow is:
1. STEP 1: pdfminer HTML extraction → score
2. STEP 1a-1c: word merge fixes, fragment rejoin, ligature fixes, encoding normalization
3. STEP 1d: Zero-text OCR escalation (if < 200 words)
4. STEP 1e: Auto-escalation to Tier 2 if score <= 70

Insert a new step **between 1d and 1e** (call it STEP 1d2 or similar):

```python
        # ── STEP 1d2: Multi-extractor comparison for borderline quality ──
        # If score is 60-80 (borderline), try alternate Tier 1 extractors before
        # escalating to Tier 2 OCR. A different extractor might handle this PDF's
        # font encoding better.
        _extractor_comparison = None
        if (tier_used == 1 and compare_extractors_enabled
                and 60 <= tier1_score <= 80):
            log(f"\n-- STEP 1d2: Multi-extractor comparison ----------------")
            log(f"  Borderline score ({tier1_score}/100) — comparing extractors")

            # Get plain text from current para_dicts for scoring comparison
            current_plain = '\n'.join(d.get('text', '') for d in para_dicts)

            comparison = compare_extractors(
                pdf_path, log,
                current_text=current_plain,
                current_score=tier1_score,
                current_extractor='pdfminer',
            )
            _extractor_comparison = comparison.get('comparison')

            if comparison['improved'] and comparison['score'] > tier1_score:
                new_score = comparison['score']
                winner = comparison['winner']
                log(f"  Switching to {winner} (score: {tier1_score} → {new_score})")

                # Re-extract using the winning extractor to get para_dicts
                # (compare_extractors returns plain text, but we need para_dicts
                # for the HTML formatting pipeline)
                if winner == 'pypdf':
                    # Use extract_text() which returns plain text
                    # Convert plain text back to para_dicts
                    plain_text = comparison['text']
                    plain_text, _ = normalize_encoding(plain_text, log=log)
                    # Split into paragraphs and build para_dicts
                    para_dicts = _plain_text_to_para_dicts(plain_text, log)
                    extraction_method = 'pypdf_comparison_winner'
                elif winner == 'pymupdf':
                    plain_text = comparison['text']
                    plain_text, _ = normalize_encoding(plain_text, log=log)
                    para_dicts = _plain_text_to_para_dicts(plain_text, log)
                    extraction_method = 'pymupdf_comparison_winner'
                # If pdfminer won, we already have para_dicts — no change needed

                # Update scores
                tier1_score = new_score
                quality = score_text_layer_quality(comparison['text'], log=log)
            else:
                log(f"  Original pdfminer extraction wins — no change")
```

### Helper: `_plain_text_to_para_dicts()`

The comparison function returns plain text, but `process_kindle_html()` needs `para_dicts` (list of dicts with 'text', 'font_size', 'is_bold', etc.). Add a simple converter:

```python
def _plain_text_to_para_dicts(text, log):
    """Convert plain text (with <<PAGE:N>> markers) to para_dicts format.

    Used when multi-extractor comparison switches to a non-pdfminer extractor.
    Font metadata is unavailable, so all paragraphs get default styling.
    Headings are detected heuristically from ALL-CAPS lines.
    """
    para_dicts = []
    current_page = 1

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Parse page markers
        page_match = re.match(r'<<PAGE:(\d+)>>', line)
        if page_match:
            current_page = int(page_match.group(1))
            para_dicts.append({
                'text': line,
                'font_size': 0,
                'is_bold': False,
                'is_italic': False,
                'page_number': current_page,
                'is_page_marker': True,
            })
            continue

        # Heuristic heading detection: ALL-CAPS, short, starts a section
        is_heading = (line == line.upper() and len(line) < 80
                      and len(line.split()) <= 8 and line[0].isalpha())

        para_dicts.append({
            'text': line,
            'font_size': 14 if is_heading else 10,  # default body size
            'is_bold': is_heading,
            'is_italic': False,
            'page_number': current_page,
            'is_page_marker': False,
            'char_count': len(line),
        })

    log(f"  Converted {len(para_dicts)} paragraphs from plain text (no font metadata)")
    # Compute body_size (most common font_size)
    body_size = 10  # default
    return para_dicts, body_size
```

### The `compare_extractors_enabled` flag

This comes from the CLI args. Add to the function signature of `process_kindle_html()`:

```python
def process_kindle_html(pdf_path, output_path, log, ...,
                        compare_extractors_enabled=False):
```

---

## Part 3: Wire into `extract_text()` (Legacy Text Path)

Find `extract_text()` (grep — around line 1736). Currently it:
1. Checks for multi-column layout → PyMuPDF
2. Samples pypdf quality → if high merge rate, switch to pdfminer
3. Runs the chosen extractor
4. Scores with `score_text_layer_quality()`

Add the comparison after the quality scoring (grep for `Text layer quality score` near end of `extract_text()`):

```python
    # ── Multi-extractor comparison for borderline quality ──
    if compare_extractors_enabled and 60 <= quality['score'] <= 80:
        log(f"  Borderline quality ({quality['score']}/100) — comparing extractors")
        comparison = compare_extractors(
            pdf_path, log,
            current_text=full_text,
            current_score=quality['score'],
            current_extractor='pypdf',  # or 'pdfminer' if that was chosen above
        )
        if comparison['improved']:
            log(f"  Switching to {comparison['winner']} "
                f"(score: {quality['score']} → {comparison['score']})")
            full_text = comparison['text']
            quality = score_text_layer_quality(full_text, log)

    return full_text
```

Add `compare_extractors_enabled=False` to the `extract_text()` signature.

---

## Part 4: CLI Flag and PSM1 Parameter

### pdf_to_balabolka.py CLI
Find the argparse setup (grep for `add_argument`). Add:

```python
ap.add_argument("--compare-extractors", action="store_true", default=False,
                help="For borderline PDFs (score 60-80), try all 3 extractors and pick the best")
```

Pass it through to the extraction functions where they're called (grep for `process_kindle_html(` and `extract_text(` call sites in the CLI main block):

```python
# In the CLI main block where process_kindle_html is called:
compare_extractors_enabled=args.compare_extractors,

# In the CLI main block where extract_text is called:
compare_extractors_enabled=args.compare_extractors,
```

### EbookAutomation.psm1
Add `-CompareExtractors` switch to `Convert-ToKindle`:

```powershell
[switch]$CompareExtractors
```

Wire into the Python argument building (grep for `$pyArgs` in Convert-ToKindle):

```powershell
if ($CompareExtractors) {
    $pyArgs += " --compare-extractors"
    Write-EbookLog "Kindle: multi-extractor comparison ENABLED"
}
```

Also add it to `Invoke-ConvergeLoop` parameters and pass through to Convert-ToKindle. The converge loop should **always** enable comparison for borderline results:

```powershell
# In the Invoke-ConvergeLoop Convert-ToKindle call:
-CompareExtractors
```

### settings.json
Add a config option for automatic comparison:

```json
{
  "extraction": {
    "compare_extractors": false,
    "comparison_low_threshold": 60,
    "comparison_high_threshold": 80
  }
}
```

Read these thresholds in `compare_extractors()` or at the call sites.

---

## Part 5: Record Comparison Results

### In the result dict
`process_kindle_html()` returns a result dict at the end (grep for `return result` or `result =` near the end). Add the comparison data:

```python
if _extractor_comparison:
    result['extractor_comparison'] = _extractor_comparison
    result['extraction_method'] = extraction_method  # already set
```

### In pattern_db
Add `extractor_comparison TEXT` column to the conversions table (follow the existing ALTER TABLE migration pattern):

```python
try:
    conn.execute("ALTER TABLE conversions ADD COLUMN extractor_comparison TEXT")
except:
    pass
```

Update `add_conversion()` to accept `extractor_comparison=None`. If passed as dict, `json.dumps()` it.

### In the PSM1 db-write block
Find the inline Python block that calls `add_conversion` (grep for `add_conversion` in PSM1). If the JSON output from `pdf_to_balabolka.py` includes `extractor_comparison`, pass it through:

```python
# After reading the extraction output JSON:
ec = extraction_result.get('extractor_comparison')
if ec:
    conv_kwargs['extractor_comparison'] = json.dumps(ec) if isinstance(ec, dict) else ec
```

### CLI: `pattern_db.py extractor-stats` command

New command showing which extractors win most often:

```python
def _cmd_extractor_stats(args):
    """Show which extractors win in multi-extractor comparisons."""
    conn = get_db(args.db if hasattr(args, 'db') and args.db else None)
    try:
        cursor = conn.execute("""
            SELECT extractor_comparison
            FROM conversions
            WHERE extractor_comparison IS NOT NULL
              AND extractor_comparison != ''
        """)
        rows = cursor.fetchall()
        if not rows:
            print("No extractor comparison data recorded yet.")
            print("Run conversions with --compare-extractors to start collecting data.")
            return

        from collections import Counter
        wins = Counter()
        total = 0
        for r in rows:
            try:
                data = json.loads(r['extractor_comparison'])
                if isinstance(data, dict):
                    # Find the winner (highest score)
                    best = max(data.items(), key=lambda x: x[1].get('score', 0))
                    wins[best[0]] += 1
                    total += 1
            except (json.JSONDecodeError, ValueError):
                continue

        print(f"Extractor Comparison Results ({total} comparisons)")
        print(f"{'Extractor':<20} {'Wins':>6} {'Win %':>7}")
        print("-" * 35)
        for name, count in wins.most_common():
            pct = (count / total * 100) if total else 0
            print(f"{name:<20} {count:>6} {pct:>6.1f}%")
    finally:
        conn.close()
```

Register: `subparsers.add_parser('extractor-stats', help='Show extractor comparison win rates')` and add to commands dict.

---

## Part 6: Export from PSM1 Module Manifest

If any new exported functions are added, update `EbookAutomation.psd1` and the `Export-ModuleMember` block at the bottom of the PSM1.

For this ticket, no new exported functions — just new parameters on existing functions.

---

## Testing

```bash
cd F:\Projects\EbookAutomation
python -m pytest tests/ -x -v
```
All existing tests must pass. The main regression risk is the new `compare_extractors_enabled` parameter on `process_kindle_html()` and `extract_text()` — ensure all callers are updated (default=False means existing paths are unaffected).

### Manual verification
```bash
# Test with a known borderline PDF:
python pdf_to_balabolka.py --input "inbox\some-borderline-book.pdf" --mode kindle --compare-extractors --output-dir output\kindle

# Should see output like:
#   Multi-extractor comparison: testing 2 additional extractor(s)...
#     pypdf: score=72/100, words=45000, time=3.2s
#     pymupdf: score=78/100, words=46200, time=2.8s
#   Winner: pymupdf (score=78/100, +6 over pdfminer)

# Test extractor stats CLI (after running a few comparisons):
python tools/pattern_db.py extractor-stats
```

---

## Git
```bash
git add -A
git commit -m "SCRUM-125: Multi-extractor comparison for borderline PDFs

- Add compare_extractors() — runs pypdf/pdfminer/PyMuPDF, scores each, picks winner
- Wire into process_kindle_html() as Step 1d2 (between quality check and OCR escalation)
- Wire into extract_text() for legacy text path
- Trigger: quality score 60-80 (borderline, not bad enough for OCR escalation)
- --compare-extractors CLI flag (off by default)
- -CompareExtractors PSM1 switch, always-on in converge loop
- Configurable thresholds in settings.json extraction section
- Results recorded in conversions.extractor_comparison (JSON)
- pattern_db.py extractor-stats command for win rate analysis
- Closes SCRUM-120 epic (Intelligent Extraction Phases 1-5 complete)"
git push origin master
```

## Jira
After completion, comment on SCRUM-125 via MCP:
```
Shipped multi-extractor comparison:
- compare_extractors() tries all 3 Tier 1 extractors (pypdf, pdfminer, PyMuPDF), scores each, picks winner
- Triggers on borderline quality (60-80) — below 60 escalates to OCR, above 80 is accepted
- Wired into process_kindle_html() (Step 1d2) and extract_text()
- --compare-extractors flag (off by default), always-on in converge loop
- Comparison results stored in pattern DB for routing intelligence
- extractor-stats CLI command for win rate analysis
- Closes SCRUM-120 epic (Phases 1-5 complete)
- All tests pass, zero regression
```
Then transition SCRUM-125 → Done (transition ID 41).

Also comment on SCRUM-120 epic:
```
All phases complete — closing epic:
- Phase 1: Quality Scorer ✅
- Phase 2: Tesseract 5 Re-OCR (Tier 2) ✅
- Phase 3: Claude Vision (Tier 3) + Gemini Flash (Tier 2.5) ✅
- Phase 4: Extraction Cache ✅
- Phase 5: Multi-Extractor Comparison (SCRUM-125) ✅
```
Then transition SCRUM-120 → Done (transition ID 41).
