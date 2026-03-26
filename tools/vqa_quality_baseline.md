# Prompt: Run Visual QA on Passing Books

## Goal
Run Visual QA scoring on the 37 books that passed structural checks in our clean baseline. This gives us actual output quality data — not just "did it extract?" but "is it good?" Expected cost: ~$1.50 (37 books × ~$0.04 each).

## Steps

### 1. Identify the 37 passing books
Read both clean baseline JSON reports from `data/batch_reports/`:
- `batch_20260324_083332.json` (batch 1)
- `batch_20260324_091457.json` (batch 2)

Extract all books where `overall_status` == "PASS". Print the list with filenames.

### 2. Create a VQA staging folder
```powershell
mkdir F:\Projects\EbookAutomation\batch_qa_intake\vqa_run -Force
```

Copy ONLY the 37 passing books into this folder. The source PDFs should be in:
- `batch_qa_intake/completed/batch_1/`
- `batch_qa_intake/completed/batch_2/`

If a file isn't found there, check `C:\Users\Joe\Downloads`.

Print the count after copying to confirm: "Staged XX books for VQA run."

### 3. Run batch QA with VQA enabled
```powershell
cd F:\Projects\EbookAutomation
python tools/batch_qa.py run "F:\Projects\EbookAutomation\batch_qa_intake\vqa_run" --full --vqa --parallel 2
```

This will:
- Re-run HTML extraction (fast, already proven to work on these books)
- Run KFX conversion via Calibre for each book
- Run Visual QA scoring on each KFX file (~20s + ~$0.04 per book)

**Expected runtime:** ~30-45 minutes (extraction + KFX + VQA per book)
**Expected cost:** ~$1.50

Wait for completion.

### 4. Analyze VQA results
After the run completes, load the new JSON report and build an analysis:

```python
import json
from pathlib import Path

reports_dir = Path(r"F:\Projects\EbookAutomation\data\batch_reports")
# Find the most recent report (the VQA run)
latest = sorted(reports_dir.glob("batch_*.json"), key=lambda f: f.stat().st_mtime)[-1]

with open(latest, 'r', encoding='utf-8') as f:
    report = json.load(f)

books = report["books"]
vqa_scored = [b for b in books if b.get("visual_qa", {}).get("score") is not None]
vqa_scores = [b["visual_qa"]["score"] for b in vqa_scored]

print(f"\n{'=' * 60}")
print(f"  VQA Results — {len(vqa_scored)} books scored")
print(f"{'=' * 60}")
print(f"  Average score:  {sum(vqa_scores)/len(vqa_scores):.1f}")
print(f"  Median score:   {sorted(vqa_scores)[len(vqa_scores)//2]}")
print(f"  Range:          {min(vqa_scores)} – {max(vqa_scores)}")
print(f"  Above 80:       {sum(1 for s in vqa_scores if s >= 80)}")
print(f"  70-79:          {sum(1 for s in vqa_scores if 70 <= s < 80)}")
print(f"  60-69:          {sum(1 for s in vqa_scores if 60 <= s < 70)}")
print(f"  Below 60:       {sum(1 for s in vqa_scores if s < 60)}")

# Category score averages
categories = {}
for b in vqa_scored:
    for cat, score in b["visual_qa"].get("category_scores", {}).items():
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(score)

print(f"\n── Category Averages ──")
for cat, scores in sorted(categories.items(), key=lambda x: sum(x[1])/len(x[1])):
    avg = sum(scores) / len(scores)
    print(f"  {cat:<25} {avg:.1f}  (range {min(scores)}-{max(scores)})")

# Bottom 10 books by VQA score
print(f"\n── Bottom 10 by VQA Score ──")
by_score = sorted(vqa_scored, key=lambda b: b["visual_qa"]["score"])
for b in by_score[:10]:
    name = b["filename"][:45]
    score = b["visual_qa"]["score"]
    cats = b["visual_qa"].get("category_scores", {})
    worst_cat = min(cats, key=cats.get) if cats else "?"
    worst_val = cats.get(worst_cat, "?")
    print(f"  {score:>3}  {name:<47} (worst: {worst_cat}={worst_val})")

# Top 10 books by VQA score
print(f"\n── Top 10 by VQA Score ──")
for b in by_score[-10:]:
    name = b["filename"][:45]
    score = b["visual_qa"]["score"]
    print(f"  {score:>3}  {name}")

# Books that passed structural but failed VQA (below 70)
vqa_failed = [b for b in vqa_scored if b["visual_qa"]["score"] < 70]
print(f"\n── Passed Structural, Failed VQA ({len(vqa_failed)} books) ──")
for b in sorted(vqa_failed, key=lambda x: x["visual_qa"]["score"]):
    name = b["filename"][:45]
    score = b["visual_qa"]["score"]
    cats = b["visual_qa"].get("category_scores", {})
    print(f"  {score:>3}  {name}")
    for cat, val in sorted(cats.items(), key=lambda x: x[1]):
        print(f"       {cat:<25} {val}")

# API cost
total_cost = sum(b.get("visual_qa", {}).get("api_cost_usd", 0) for b in books)
print(f"\n── Total API Cost: ${total_cost:.2f} ──")

print(f"\n{'=' * 60}")
```

### 5. Build the quality tier list
Classify all 37 books into quality tiers:

| Tier | VQA Score | Meaning |
|------|-----------|---------|
| A (Excellent) | 85+ | Ready for Kindle, minimal issues |
| B (Good) | 70-84 | Usable, some minor quality issues |
| C (Needs Work) | 55-69 | Readable but noticeable problems |
| D (Poor) | Below 55 | Significant quality issues, needs pipeline fixes |

Print the tier distribution and list all C and D tier books with their worst category scores.

### 6. Identify the weakest VQA category
Which category (text_integrity, formatting, structure, readability, etc.) has the lowest average score across all books? That's the systemic weakness in the pipeline — the thing that would improve the most books if fixed.

Print:
```
Systemic Quality Issues (sorted by impact):
  1. [category]: avg XX — affects XX books below 70 in this category
  2. [category]: avg XX — affects XX books below 70
  ...
```

### 7. Save analysis and commit
Write the full VQA analysis to:
```
docs/superpowers/analysis/2026-03-24-vqa-quality-baseline.md
```

Include:
- Score distribution
- Category averages
- Tier list
- Bottom 10 detail
- Systemic weakness analysis
- Recommendations for what to fix based on the data

```powershell
git add data/batch_reports/ docs/
git commit -m "data: VQA quality baseline for 37 passing books

- Ran Visual QA on all 37 structurally-passing books
- Average score: XX, range XX-XX
- XX books above 80, XX in 70-79, XX below 70
- Weakest category: [whatever it is]
- Total API cost: $X.XX
- Full analysis in docs/superpowers/analysis/"
git push
```

## Important
- This WILL incur API costs (~$1.50 total). That is approved.
- Use `--parallel 2` — VQA makes API calls, don't overwhelm with too many concurrent
- If KFX conversion fails for a book, VQA is skipped for that book (no cost wasted)
- If a book's VQA score comes back below 70, that's useful data, not a problem to fix right now
- Do NOT modify any pipeline code — this is a measurement run
- The VQA reports (.json files) that visual_qa.py creates per-book are valuable — make sure they're preserved
