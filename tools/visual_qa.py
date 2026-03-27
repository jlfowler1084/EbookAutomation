#!/usr/bin/env python3
"""
visual_qa.py — Automated Visual Quality Assurance for Ebook Conversions

Converts a KFX/AZW3/EPUB file to paginated PDF via Calibre, renders sampled
pages to PNG via pdf2image/poppler, sends them to the Claude Vision API with
a rubric prompt, and produces a structured JSON QA report.

Usage:
    python visual_qa.py --input "output\\kindle\\Author - Title.kfx"
    python visual_qa.py --input "book.kfx" --dpi 200 --max-pages 15
    python visual_qa.py --input "book.epub" --model claude-sonnet-4-6 --verbose
"""

import argparse
import base64
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger("visual_qa")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_poppler_path(explicit_path=None):
    """Locate the poppler bin directory."""
    if explicit_path and os.path.isdir(explicit_path):
        return explicit_path

    # Check relative to this script (tools\poppler\...\Library\bin)
    script_dir = Path(__file__).resolve().parent
    poppler_root = script_dir / "poppler"

    # Walk into poppler dir — may have nested release dirs
    # e.g. tools/poppler/Release-25.12.0-0/poppler-25.12.0/Library/bin
    if poppler_root.is_dir():
        for lib_bin in poppler_root.rglob("Library/bin"):
            if (lib_bin / "pdftoppm.exe").exists():
                return str(lib_bin)

    # Also check direct paths
    candidates = [
        script_dir / "poppler" / "Library" / "bin",
        script_dir / "poppler" / "bin",
        script_dir.parent / "tools" / "poppler" / "Library" / "bin",
    ]
    for p in candidates:
        if p.is_dir() and (p / "pdftoppm.exe").exists():
            return str(p)

    return None  # Let pdf2image try system PATH


def find_calibre(explicit_path=None):
    """Locate ebook-convert.exe."""
    if explicit_path and os.path.isfile(explicit_path):
        return explicit_path

    # Check common install locations
    candidates = [
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p

    return None


def load_settings_json():
    """Try to load project settings.json for default paths."""
    script_dir = Path(__file__).resolve().parent
    settings_path = script_dir.parent / "config" / "settings.json"
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# Step 1: Convert to PDF via Calibre
# ---------------------------------------------------------------------------

def convert_to_pdf(input_path, calibre_path, output_dir=None):
    """Convert KFX/AZW3/EPUB to PDF via Calibre's ebook-convert."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not calibre_path or not os.path.isfile(calibre_path):
        raise FileNotFoundError(
            f"Calibre ebook-convert.exe not found at: {calibre_path}\n"
            "Install Calibre or pass --calibre with the correct path."
        )

    # Output PDF goes to a temp directory to avoid cluttering the workspace
    if output_dir:
        pdf_dir = Path(output_dir)
    else:
        pdf_dir = Path(tempfile.mkdtemp(prefix="visual_qa_"))

    pdf_path = pdf_dir / (input_path.stem + ".pdf")

    logger.info("Converting %s to PDF via Calibre...", input_path.name)
    cmd = [
        calibre_path,
        str(input_path),
        str(pdf_path),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )

    if result.returncode != 0:
        stderr_snippet = (result.stderr or "")[:500]
        raise RuntimeError(
            f"Calibre conversion failed (exit {result.returncode}):\n{stderr_snippet}"
        )

    if not pdf_path.exists():
        raise RuntimeError(f"Calibre did not produce expected PDF: {pdf_path}")

    logger.info("PDF created: %s", pdf_path)
    return str(pdf_path)


# ---------------------------------------------------------------------------
# Step 2: Page sampling
# ---------------------------------------------------------------------------

def get_pdf_page_count(pdf_path):
    """Get total page count from a PDF."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return len(reader.pages)
    except ImportError:
        pass

    # Fallback: try pdfinfo from poppler
    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(pdf_path)
        return info.get("Pages", 0)
    except Exception:
        pass

    return 0


def get_pdf_bookmarks(pdf_path):
    """Extract bookmark page numbers for chapter-first-page sampling."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        pages = set()

        def _walk(outlines, reader_obj):
            for item in outlines:
                if isinstance(item, list):
                    _walk(item, reader_obj)
                else:
                    try:
                        page_num = reader_obj.get_destination_page_number(item)
                        if page_num is not None:
                            pages.add(page_num + 1)  # 1-indexed
                    except Exception:
                        pass

        if reader.outline:
            _walk(reader.outline, reader)
        return sorted(pages)
    except Exception:
        return []


def select_sample_pages(total_pages, max_samples=8, bookmark_pages=None):
    """Select a representative sample of pages for evaluation.

    Sampling strategy for small sample sizes (≤ 10):
    - Pages 1-2: cover + front matter (always)
    - 1-2 bookmark/chapter-start pages
    - 1-2 early-to-mid body pages (evenly spaced)
    - 2-3 late body + back matter pages (notes, index, bibliography
      tend to have the most issues)

    For larger sample sizes (> 10), adds more bookmark pages and evenly
    spaced body pages throughout the book.
    """
    if total_pages == 0:
        return []
    if total_pages <= max_samples:
        return list(range(1, total_pages + 1))

    selected = set()

    # Always include first pages (cover, front matter)
    for p in range(1, min(3, total_pages) + 1):
        selected.add(p)

    # Include some bookmark pages (chapter starts) — but not too many
    if bookmark_pages:
        bm_pages = sorted(set(bookmark_pages))
        if max_samples <= 10:
            # Take up to 2 bookmark pages, preferring ones spread through the book
            if len(bm_pages) <= 2:
                selected.update(bm_pages)
            else:
                # Pick one from first third, one from last third
                third = len(bm_pages) // 3
                selected.add(bm_pages[third])
                selected.add(bm_pages[-third] if third > 0 else bm_pages[-1])
        else:
            # Larger sample: include all bookmark pages (will be trimmed later)
            for p in bm_pages:
                if 1 <= p <= total_pages:
                    selected.add(p)

    # Fill remaining slots with evenly spaced pages, biased toward the back
    remaining = max_samples - len(selected)
    if remaining > 0:
        # Divide the book into zones
        back_start = int(total_pages * 0.75)
        mid_start = int(total_pages * 0.15)

        # Allocate: ~40% of remaining to back matter, ~60% to body
        back_slots = max(1, remaining * 2 // 5)
        body_slots = remaining - back_slots

        # Body pages (evenly spaced from 15% to 75%)
        if body_slots > 0 and back_start > mid_start:
            step = (back_start - mid_start) / (body_slots + 1)
            for i in range(1, body_slots + 1):
                p = int(mid_start + step * i)
                if 1 <= p <= total_pages:
                    selected.add(p)

        # Back matter pages (evenly spaced from 75% to end)
        if back_slots > 0 and total_pages > back_start:
            step = (total_pages - back_start) / (back_slots + 1)
            for i in range(1, back_slots + 1):
                p = int(back_start + step * i)
                if 1 <= p <= total_pages:
                    selected.add(p)

    # If we still need more pages, fill the largest gaps
    while len(selected) < max_samples and len(selected) < total_pages:
        sorted_pages = sorted(selected)
        max_gap = 0
        gap_start = 0
        for i in range(len(sorted_pages) - 1):
            gap = sorted_pages[i+1] - sorted_pages[i]
            if gap > max_gap:
                max_gap = gap
                gap_start = sorted_pages[i]
        if max_gap <= 1:
            break
        selected.add(gap_start + max_gap // 2)

    return sorted(selected)[:max_samples]


# ---------------------------------------------------------------------------
# Step 3: Render pages to PNG
# ---------------------------------------------------------------------------

def render_pages_to_png(pdf_path, page_numbers, dpi=150, poppler_path=None):
    """Render specific PDF pages to PNG images.

    Returns a list of (page_number, png_bytes) tuples.
    """
    from pdf2image import convert_from_path

    kwargs = {'dpi': dpi, 'fmt': 'png'}
    if poppler_path:
        kwargs['poppler_path'] = poppler_path

    rendered = []
    for page_num in page_numbers:
        logger.info("  Rendering page %d...", page_num)
        try:
            images = convert_from_path(
                pdf_path,
                first_page=page_num,
                last_page=page_num,
                **kwargs
            )
            if images:
                import io
                buf = io.BytesIO()
                images[0].save(buf, format='PNG')
                rendered.append((page_num, buf.getvalue()))
        except Exception as e:
            logger.warning("  Failed to render page %d: %s", page_num, e)

    return rendered


# ---------------------------------------------------------------------------
# Step 4: Send to Claude Vision API
# ---------------------------------------------------------------------------

def build_vision_request(page_images, rubric_text, model):
    """Build the Claude API request payload with page images + rubric."""
    content = []

    # Add each page image
    for page_num, png_bytes in page_images:
        b64_data = base64.b64encode(png_bytes).decode('utf-8')
        content.append({
            "type": "text",
            "text": f"--- Page {page_num} ---"
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64_data,
            }
        })

    content.append({
        "type": "text",
        "text": (
            "Evaluate all pages above against the rubric. "
            "Return ONLY valid JSON (no markdown fences, no commentary). "
            "Include a 'pages' array with one object per page evaluated, "
            "each containing: page_number, page_type, score (0-100), pass (bool), "
            "and issues (array of objects with category, severity, description, suggestion)."
        )
    })

    return {
        "model": model,
        "max_tokens": 8192,
        "system": rubric_text,
        "messages": [
            {"role": "user", "content": content}
        ]
    }


def call_claude_vision(payload, api_key):
    """Send the vision request to Claude API with retry for overload errors."""
    import requests
    import time

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    image_count = sum(1 for b in payload["messages"][0]["content"]
                      if isinstance(b, dict) and b.get("type") == "image")
    logger.info("Sending %d images to Claude Vision API...", image_count)

    max_retries = 3
    backoff_seconds = [10, 30, 60]

    for attempt in range(max_retries + 1):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=300,
        )

        if response.status_code == 200:
            break  # Success

        # Retry on overload (529) and rate limit (429)
        if response.status_code in (429, 529) and attempt < max_retries:
            wait = backoff_seconds[attempt]
            logger.warning("  API returned %d (attempt %d/%d) — retrying in %ds...",
                           response.status_code, attempt + 1, max_retries, wait)
            time.sleep(wait)
            continue

        # Non-retryable error or retries exhausted
        error_body = response.text[:500]
        raise RuntimeError(
            f"Claude API returned {response.status_code}: {error_body}"
        )

    # Parse successful response
    result = response.json()

    # Extract usage stats
    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # Extract text content
    text_blocks = [
        b["text"] for b in result.get("content", [])
        if b.get("type") == "text"
    ]
    raw_text = "\n".join(text_blocks).strip()

    return raw_text, input_tokens, output_tokens


def parse_qa_response(raw_text):
    """Parse Claude's JSON response, stripping any markdown fences."""
    # Strip markdown code fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        # Remove closing fence
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude response as JSON: %s", e)
        logger.error("Raw response (first 500 chars): %s", raw_text[:500])
        # Return a minimal error report
        return {
            "overall_score": 0,
            "overall_pass": False,
            "pages": [],
            "category_scores": {},
            "summary": f"Failed to parse QA response: {e}",
            "top_issues": [],
            "parse_error": True,
            "raw_response": raw_text[:2000],
        }


# ---------------------------------------------------------------------------
# Step 5: Assemble final report
# ---------------------------------------------------------------------------

def build_report(book_path, qa_data, total_pages, pages_sampled, dpi, model,
                 input_tokens, output_tokens, pass_threshold=70):
    """Assemble the final QA report JSON."""

    # Estimate cost (Sonnet pricing as default)
    model_lower = model.lower()
    if "opus" in model_lower:
        input_cost_per_m = 5.00
        output_cost_per_m = 25.00
    elif "haiku" in model_lower:
        input_cost_per_m = 1.00
        output_cost_per_m = 5.00
    else:  # sonnet
        input_cost_per_m = 3.00
        output_cost_per_m = 15.00

    estimated_cost = (
        (input_tokens / 1_000_000) * input_cost_per_m +
        (output_tokens / 1_000_000) * output_cost_per_m
    )

    overall_score = qa_data.get("overall_score", 0)

    report = {
        "book": os.path.basename(book_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "pages_sampled": pages_sampled,
        "pages_total": total_pages,
        "dpi": dpi,
        "overall_score": overall_score,
        "overall_pass": overall_score >= pass_threshold,
        "pass_threshold": pass_threshold,
        "category_scores": qa_data.get("category_scores", {}),
        "pages": qa_data.get("pages", []),
        "summary": qa_data.get("summary", ""),
        "top_issues": qa_data.get("top_issues", []),
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 4),
        }
    }

    return report


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_visual_qa(input_path, api_key, calibre_path, poppler_path,
                  output_dir, dpi, max_pages, model, rubric_path,
                  pass_threshold=70):
    """Execute the full visual QA pipeline."""

    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    mode_label = "full" if (max_pages > 10 and dpi >= 150) else "quick"
    logger.info("VQA mode: %s (%d pages, %d DPI)", mode_label, max_pages, dpi)

    # --- Load rubric ---
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

    # --- Convert to PDF ---
    input_ext = input_path.suffix.lower()
    if input_ext == ".pdf":
        # Already a PDF, skip conversion
        pdf_path = str(input_path)
        logger.info("Input is already PDF, skipping Calibre conversion")
    else:
        pdf_path = convert_to_pdf(input_path, calibre_path)

    # --- Get page info ---
    total_pages = get_pdf_page_count(pdf_path)
    if total_pages == 0:
        raise RuntimeError(f"Could not determine page count for: {pdf_path}")
    logger.info("PDF has %d pages", total_pages)

    bookmark_pages = get_pdf_bookmarks(pdf_path)
    if bookmark_pages:
        logger.info("Found %d bookmark pages for sampling", len(bookmark_pages))

    # --- Select and render pages ---
    sample_pages = select_sample_pages(total_pages, max_pages, bookmark_pages)
    logger.info("Sampling %d pages: %s", len(sample_pages), sample_pages)

    resolved_poppler = find_poppler_path(poppler_path)
    page_images = render_pages_to_png(pdf_path, sample_pages, dpi, resolved_poppler)

    if not page_images:
        raise RuntimeError("No pages were rendered successfully")

    logger.info("Rendered %d pages at %d DPI", len(page_images), dpi)

    # --- Send to Claude (batched) ---
    BATCH_SIZE = 8
    all_pages_results = []
    total_input_tokens = 0
    total_output_tokens = 0

    batches = []
    for i in range(0, len(page_images), BATCH_SIZE):
        batches.append(page_images[i:i + BATCH_SIZE])

    logger.info("Sending %d images in %d batch(es) of up to %d...",
                len(page_images), len(batches), BATCH_SIZE)

    for batch_idx, batch in enumerate(batches, 1):
        logger.info("  Batch %d/%d: %d pages [%s]",
                     batch_idx, len(batches), len(batch),
                     ", ".join(str(p) for p, _ in batch))
        payload = build_vision_request(batch, rubric_text, model)
        try:
            raw_text, in_tok, out_tok = call_claude_vision(payload, api_key)
            total_input_tokens += in_tok
            total_output_tokens += out_tok
            logger.info("  Batch %d: %d input, %d output tokens",
                         batch_idx, in_tok, out_tok)

            batch_data = parse_qa_response(raw_text)
            # Collect per-page results from this batch
            if isinstance(batch_data, dict):
                pages = batch_data.get("pages", [])
                all_pages_results.extend(pages)
        except Exception as e:
            logger.error("  Batch %d failed: %s", batch_idx, e)
            # Continue with remaining batches — partial results are better than none

    logger.info("All batches complete: %d input tokens, %d output tokens total",
                total_input_tokens, total_output_tokens)
    input_tokens = total_input_tokens
    output_tokens = total_output_tokens

    # --- Merge batch results ---
    # Build a merged qa_data from all batch results
    # Re-score based on all collected page results
    if all_pages_results:
        page_scores = [p.get("score", 0) for p in all_pages_results if isinstance(p, dict)]
        overall_score = round(sum(page_scores) / len(page_scores)) if page_scores else 0

        # Aggregate category scores from per-page issues
        # Count issues per category weighted by severity
        severity_weights = {"critical": 25, "major": 15, "moderate": 10, "minor": 5}
        cat_deductions = {}
        cat_page_counts = {}

        # Track which categories appear on which pages
        for page in all_pages_results:
            if not isinstance(page, dict):
                continue
            page_cats = set()
            for issue in page.get("issues", []):
                cat = issue.get("category", "unknown")
                sev = issue.get("severity", "minor")
                deduction = severity_weights.get(sev, 5)
                cat_deductions[cat] = cat_deductions.get(cat, 0) + deduction
                page_cats.add(cat)
            for cat in page_cats:
                cat_page_counts[cat] = cat_page_counts.get(cat, 0) + 1

        # Convert deductions to scores (100 minus average deduction per page with issues)
        category_scores = {}
        for cat in cat_deductions:
            avg_deduction = cat_deductions[cat] / max(cat_page_counts.get(cat, 1), 1)
            category_scores[cat] = max(0, round(100 - avg_deduction))

        # Collect top issues (severity moderate or higher)
        top_issues = []
        seen_descriptions = set()
        for page in all_pages_results:
            if not isinstance(page, dict):
                continue
            for issue in page.get("issues", []):
                desc = issue.get("description", "")
                if desc not in seen_descriptions and issue.get("severity") in ("moderate", "major", "critical"):
                    top_issues.append(issue)
                    seen_descriptions.add(desc)

        # Build summary from the last batch (which has the most context) or generate one
        qa_data = {
            "overall_score": overall_score,
            "overall_pass": overall_score >= pass_threshold,
            "pages": all_pages_results,
            "category_scores": category_scores,
            "summary": f"Evaluated {len(all_pages_results)} pages across {len(batches)} batch(es). Average page score: {overall_score}/100.",
            "top_issues": top_issues[:10],
        }
    else:
        qa_data = {
            "overall_score": 0,
            "overall_pass": False,
            "pages": [],
            "category_scores": {},
            "summary": "All API batches failed — no pages were evaluated.",
            "top_issues": [],
        }

    # --- Build report ---
    report = build_report(
        str(input_path), qa_data, total_pages, len(page_images),
        dpi, model, input_tokens, output_tokens, pass_threshold
    )

    # --- Write report ---
    if output_dir:
        report_dir = Path(output_dir)
    else:
        report_dir = input_path.parent

    report_name = input_path.stem + "_visual_qa_report.json"
    report_path = report_dir / report_name

    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("Report written: %s", report_path)
    logger.info("Overall score: %d/100 (%s)",
                report["overall_score"],
                "PASS" if report["overall_pass"] else "FAIL")

    # --- Cleanup temp PDF if we created one ---
    if input_ext != ".pdf" and pdf_path != str(input_path):
        try:
            os.remove(pdf_path)
            # Try to remove the temp dir if empty
            pdf_dir = os.path.dirname(pdf_path)
            if pdf_dir and not os.listdir(pdf_dir):
                os.rmdir(pdf_dir)
        except OSError:
            pass

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    settings = load_settings_json()
    paths = settings.get("paths", {})

    # Resolve defaults from settings.json
    default_calibre = paths.get("calibre", r"C:\Program Files\Calibre2\ebook-convert.exe")
    default_poppler = paths.get("poppler", "")
    if default_poppler and not os.path.isabs(default_poppler):
        # Resolve relative to project root; find_poppler_path will search for the bin dir
        script_dir = Path(__file__).resolve().parent
        resolved = script_dir.parent / default_poppler
        # Check if this dir contains Library/bin directly
        direct_bin = resolved / "Library" / "bin"
        if direct_bin.is_dir() and (direct_bin / "pdftoppm.exe").exists():
            default_poppler = str(direct_bin)
        else:
            # Let find_poppler_path handle nested dirs at runtime
            default_poppler = ""

    vqa_settings = settings.get("visual_qa", {})
    default_dpi = vqa_settings.get("dpi", 100)
    default_max_pages = vqa_settings.get("max_pages", 8)
    default_threshold = vqa_settings.get("pass_threshold", 70)
    # Note: visual_qa.py now prefers agents/qa-evaluation/system-prompt.md over this path.
    # This setting is used as a fallback only.
    default_rubric = vqa_settings.get("rubric_path", "")
    if not default_rubric:
        default_rubric = str(Path(__file__).resolve().parent / "visual_qa_rubric.md")
    elif not os.path.isabs(default_rubric):
        default_rubric = str(Path(__file__).resolve().parent.parent / default_rubric)

    parser = argparse.ArgumentParser(
        description="Visual QA for ebook conversions using Claude Vision API"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to KFX, AZW3, EPUB, or PDF file"
    )
    parser.add_argument(
        "--api-key", default=None,
        help="Anthropic API key (falls back to ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--calibre", default=default_calibre,
        help="Path to ebook-convert.exe"
    )
    parser.add_argument(
        "--poppler", default=default_poppler or None,
        help="Path to poppler bin directory"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for the report JSON (default: same as input file)"
    )
    parser.add_argument(
        "--dpi", type=int, default=default_dpi,
        help=f"PNG render resolution (default: {default_dpi})"
    )
    parser.add_argument(
        "--max-pages", type=int, default=default_max_pages,
        help=f"Maximum pages to sample (default: {default_max_pages})"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Full evaluation mode: 20 pages at 150 DPI (overrides --dpi and --max-pages defaults)"
    )
    parser.add_argument(
        "--model", default=None,
        help="Claude model for evaluation (default: from settings.json or claude-sonnet-4-6)"
    )
    parser.add_argument(
        "--rubric", default=default_rubric,
        help="Path to rubric prompt file"
    )
    parser.add_argument(
        "--pass-threshold", type=int, default=default_threshold,
        help=f"Minimum score to pass (default: {default_threshold})"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Detailed logging to stderr"
    )

    args = parser.parse_args()

    # Resolve model from settings.json if not specified on CLI
    if args.model is None:
        settings = load_settings_json()
        args.model = settings.get("api_models", {}).get("sonnet_latest", "claude-sonnet-4-6")

    # --full overrides to comprehensive evaluation
    if args.full:
        if not any(a.startswith('--dpi') for a in sys.argv):
            args.dpi = 150
        if not any(a.startswith('--max-pages') for a in sys.argv):
            args.max_pages = 20

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    # Resolve API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        parser.error(
            "No API key provided. Use --api-key or set ANTHROPIC_API_KEY env var."
        )

    try:
        report = run_visual_qa(
            input_path=args.input,
            api_key=api_key,
            calibre_path=args.calibre,
            poppler_path=args.poppler,
            output_dir=args.output_dir,
            dpi=args.dpi,
            max_pages=args.max_pages,
            model=args.model,
            rubric_path=args.rubric,
            pass_threshold=args.pass_threshold,
        )

        # Print summary to stdout
        print(json.dumps({
            "book": report["book"],
            "overall_score": report["overall_score"],
            "overall_pass": report["overall_pass"],
            "pages_sampled": report["pages_sampled"],
            "pages_total": report["pages_total"],
            "summary": report["summary"],
            "estimated_cost_usd": report["token_usage"]["estimated_cost_usd"],
        }, indent=2))

        sys.exit(0 if report["overall_pass"] else 1)

    except Exception as e:
        logger.error("Visual QA failed: %s", e)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
