#!/usr/bin/env python3
"""Unified pre-flight document analysis and conversion recipe generator.

Analyzes a source document in <10 seconds and produces a complete conversion
recipe including profile, extraction strategy, content filter flags, confidence
score, and human-readable reasoning.

Delegates to existing classify_source.py and pattern_db.py for classification
and historical data, adds NEW text quality assessment and bookmark analysis.

CLI:
    python tools/preflight_analysis.py --input "book.pdf" [--db-path "..."] [--verbose]

Output (JSON to stdout):
    {
        "source_file": "path/to/book.pdf",
        "format": "pdf",
        "page_count": 350,
        "analysis": { ... },
        "recipe": { ... },
        "duration_seconds": 4.2
    }
"""

import argparse
import json
import os
import re
import sys
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Sibling imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg, verbose=False, _verbose_flag=[False]):
    """Print diagnostic to stderr (only if verbose)."""
    if verbose:
        _verbose_flag[0] = True
    if _verbose_flag[0]:
        print(msg, file=sys.stderr)


def _log_always(msg):
    """Print diagnostic to stderr unconditionally."""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Step 1: Source Classification (delegates to classify_source.py)
# ---------------------------------------------------------------------------

def _classify_source(pdf_path, log_fn):
    """Delegate to existing classify_source.py.  Returns classification dict."""
    try:
        from classify_source import classify_pdf
        result = classify_pdf(str(pdf_path))
        log_fn(f"  Classification: {result.get('classification')} "
               f"(confidence {result.get('confidence', 0):.2f})")
        return result
    except Exception as e:
        log_fn(f"  Classification failed (non-blocking): {e}")
        return {
            "classification": "unknown",
            "confidence": 0.0,
            "signals": {
                "text_density_per_page": 0,
                "file_size_per_page_kb": 0,
            },
            "recommended_strategies": [],
            "flags": {
                "needs_ocr": False,
                "likely_two_column": False,
                "needs_paid_tier": False,
                "recommended_paid_tier": None,
            },
        }


# ---------------------------------------------------------------------------
# Step 2: Text Quality Assessment (NEW)
# ---------------------------------------------------------------------------

def _assess_text_quality(pdf_path, page_count, log_fn):
    """Sample 5 pages from body content (10%-90%) and score text quality.

    Returns dict with quality_tier, ocr_artifact_rate, unicode_printable_ratio,
    common_word_hit_rate, sample_pages, score.
    """
    default = {
        "quality_tier": "unknown",
        "ocr_artifact_rate": 0.0,
        "unicode_printable_ratio": 0.0,
        "common_word_hit_rate": 0.0,
        "sample_pages": 0,
        "score": 0,
    }
    try:
        from pypdf import PdfReader
        from pdf_to_balabolka import score_text_layer_quality
    except ImportError as e:
        log_fn(f"  Text quality: skipped (import failed: {e})")
        return default

    try:
        reader = PdfReader(str(pdf_path))
        total = len(reader.pages)
        if total == 0:
            return default

        # Page sampling: skip first/last 10%, pick 5 evenly spaced
        if total < 20:
            sample_indices = list(range(total))
        else:
            start = max(1, int(total * 0.10))
            end = min(total - 1, int(total * 0.90))
            span = end - start
            if span < 5:
                sample_indices = list(range(start, end + 1))
            else:
                step = span / 4  # 5 samples: start, +step, +2step, +3step, end
                sample_indices = [int(start + i * step) for i in range(5)]

        # Extract text from sampled pages
        texts = []
        for idx in sample_indices:
            try:
                page_text = reader.pages[idx].extract_text() or ""
                texts.append(page_text)
            except Exception:
                pass

        if not texts:
            log_fn("  Text quality: no text extracted from sampled pages")
            return default

        combined = "\n".join(texts)
        if len(combined) < 100:
            log_fn(f"  Text quality: insufficient text ({len(combined)} chars)")
            return {**default, "sample_pages": len(texts), "quality_tier": "poor"}

        # Score using existing quality scorer
        quality = score_text_layer_quality(combined)
        score = quality['score']
        details = quality['details']

        hit_rate = details.get('common_word_rate', {}).get('hit_rate', 0.0)
        unicode_ratio = details.get('unicode_printable', {}).get('ratio', 0.0)
        ocr_artifact_rate = round(1.0 - hit_rate, 4)

        # Tier mapping
        if score >= 75:
            tier = "clean"
        elif score >= 50:
            tier = "moderate"
        else:
            tier = "poor"

        result = {
            "quality_tier": tier,
            "ocr_artifact_rate": ocr_artifact_rate,
            "unicode_printable_ratio": round(unicode_ratio, 4),
            "common_word_hit_rate": round(hit_rate, 4),
            "sample_pages": len(texts),
            "score": score,
        }
        log_fn(f"  Text quality: {tier} (score {score}/100, "
               f"artifact rate {ocr_artifact_rate:.0%})")
        return result

    except Exception as e:
        log_fn(f"  Text quality assessment failed (non-blocking): {e}")
        return default


# ---------------------------------------------------------------------------
# Step 3: Chapter Structure Assessment (NEW — bookmarks only)
# ---------------------------------------------------------------------------

def _assess_chapter_structure(pdf_path, page_count, classification, log_fn):
    """Assess chapter detection viability from PDF bookmarks.

    Returns dict with bookmark_count, bookmarks_readable,
    recommended_chapter_source, claude_chapters_recommended.
    """
    default = {
        "bookmark_count": 0,
        "bookmarks_readable": False,
        "recommended_chapter_source": "regex",
        "claude_chapters_recommended": bool(os.environ.get('ANTHROPIC_API_KEY')),
    }
    try:
        from pypdf import PdfReader
    except ImportError as e:
        log_fn(f"  Chapter structure: skipped (import failed: {e})")
        return default

    try:
        reader = PdfReader(str(pdf_path))
        outline = reader.outline if hasattr(reader, 'outline') else []

        # Flatten nested outlines
        bookmarks = []
        _flatten_outline(outline, bookmarks)

        count = len(bookmarks)
        if count == 0:
            log_fn("  Chapter structure: no bookmarks found")
            has_api = bool(os.environ.get('ANTHROPIC_API_KEY'))
            return {
                "bookmark_count": 0,
                "bookmarks_readable": False,
                "recommended_chapter_source": "claude" if has_api else "regex",
                "claude_chapters_recommended": has_api,
            }

        # Check readability: >80% should be real text (not garbled/empty)
        readable_count = sum(1 for b in bookmarks if _is_readable_bookmark(b))
        readable_ratio = readable_count / count if count > 0 else 0.0

        readable = readable_ratio > 0.80
        min_bookmarks = 3

        if count >= min_bookmarks and readable:
            source = "bookmarks"
            claude_rec = False
        else:
            has_api = bool(os.environ.get('ANTHROPIC_API_KEY'))
            source = "claude" if has_api else "regex"
            claude_rec = has_api

        result = {
            "bookmark_count": count,
            "bookmarks_readable": readable,
            "recommended_chapter_source": source,
            "claude_chapters_recommended": claude_rec,
        }
        log_fn(f"  Chapter structure: {count} bookmarks, "
               f"{readable_count} readable ({readable_ratio:.0%}) "
               f"→ {source}")
        return result

    except Exception as e:
        log_fn(f"  Chapter structure assessment failed (non-blocking): {e}")
        return default


def _flatten_outline(outline, result):
    """Recursively flatten a pypdf outline into a list of title strings."""
    if not outline:
        return
    for item in outline:
        if isinstance(item, list):
            _flatten_outline(item, result)
        elif hasattr(item, 'title'):
            result.append(item.title or "")
        elif isinstance(item, dict) and '/Title' in item:
            result.append(item['/Title'] or "")


def _is_readable_bookmark(title):
    """Check if a bookmark title is readable text (not garbled/empty)."""
    if not title or not title.strip():
        return False
    stripped = title.strip()
    if len(stripped) < 2:
        return False
    # Garbled text: high ratio of non-ASCII or control characters
    printable = sum(1 for c in stripped if c.isprintable())
    if printable / len(stripped) < 0.70:
        return False
    # Garbled text: no alphabetic characters at all
    if not any(c.isalpha() for c in stripped):
        return False
    return True


# ---------------------------------------------------------------------------
# Step 4: Historical Data Lookup (delegates to pattern_db.py)
# ---------------------------------------------------------------------------

def _lookup_historical_data(pdf_path, classification, db_path, log_fn):
    """Delegate to existing pattern_db.get_recommended_strategy().

    Returns a normalized dict matching the preflight output schema.
    """
    default = {
        "has_history": False,
        "source": "default",
        "best_prior_score": None,
        "prior_strategy": [],
        "prior_conversions": 0,
    }
    try:
        from pattern_db import get_recommended_strategy
    except ImportError as e:
        log_fn(f"  Historical data: skipped (import failed: {e})")
        return default, None

    try:
        raw = get_recommended_strategy(
            source_file_path=str(pdf_path),
            source_type=classification.get('classification'),
            format='pdf',
            db_path=db_path,
        )

        source = raw.get('source', 'default')
        has_history = source != 'default'

        result = {
            "has_history": has_history,
            "source": source,
            "best_prior_score": raw.get('best_prior_score'),
            "prior_strategy": raw.get('strategy_order', []),
            "prior_conversions": raw.get('prior_conversions', 0),
        }
        if has_history:
            log_fn(f"  Historical data: {source} — "
                   f"{raw.get('prior_conversions', 0)} prior conversions, "
                   f"best score {raw.get('best_prior_score')}")
        else:
            log_fn("  Historical data: none")
        return result, raw

    except Exception as e:
        log_fn(f"  Historical data lookup failed (non-blocking): {e}")
        return default, None


# ---------------------------------------------------------------------------
# Step 5: Recipe Generation (decision tree)
# ---------------------------------------------------------------------------

def _generate_recipe(classification, text_quality, chapter_structure,
                     historical_data, raw_historical, format_type):
    """Combine all signals into a conversion recipe.

    Decision tree (PDF):
      1. scan_no_text → text-only, [ocr], skip all structural
      2. scan_with_text + poor (<50) → text-only, [legacy, ocr], skip footnotes+index
      3. scan_with_text + moderate (50-74) → clean-read, [legacy], skip unusable
      4. scan_with_text + clean (75+) → full, [html_extraction, legacy], all elements
      5. digital_native → full, [html_extraction, legacy], all elements
      6. EPUB → full, [epub_html, direct]
      7. Other → full, [direct]

    Historical data override: exact book with score >= 70 uses that strategy.
    """
    cls_type = classification.get('classification', 'unknown')
    cls_conf = classification.get('confidence', 0.0)
    tq_score = text_quality.get('score', 0) if text_quality else 0
    tq_tier = text_quality.get('quality_tier', 'unknown') if text_quality else 'unknown'
    tq_artifact = text_quality.get('ocr_artifact_rate', 0.0) if text_quality else 0.0
    bm_count = chapter_structure.get('bookmark_count', 0) if chapter_structure else 0
    bm_source = chapter_structure.get('recommended_chapter_source', 'regex') if chapter_structure else 'regex'
    bm_readable = chapter_structure.get('bookmarks_readable', False) if chapter_structure else False
    claude_chap = chapter_structure.get('claude_chapters_recommended', False) if chapter_structure else False
    hist_source = historical_data.get('source', 'default') if historical_data else 'default'
    hist_score = historical_data.get('best_prior_score') if historical_data else None
    hist_strat = historical_data.get('prior_strategy', []) if historical_data else []
    hist_convs = historical_data.get('prior_conversions', 0) if historical_data else 0

    reasoning = []
    confidence = cls_conf

    # --- Non-PDF fast paths ---
    if format_type == 'epub':
        reasoning.append("EPUB format: digital-native, using EPUB HTML extraction")
        return {
            "profile": "full",
            "extraction_strategy": ["epub_html", "direct"],
            "flags": {
                "UseHtmlExtraction": False,
                "UseClaudeChapters": False,
                "UseOCR": False,
                "ForceColumns": False,
                "NoFootnotes": False,
                "NoIndex": False,
                "NoHyperlinks": False,
            },
            "confidence": 0.90,
            "reasoning": reasoning,
        }

    if format_type in ('mobi', 'azw', 'azw3'):
        reasoning.append(f"{format_type.upper()} format: direct Calibre conversion")
        return {
            "profile": "full",
            "extraction_strategy": ["direct"],
            "flags": {
                "UseHtmlExtraction": False,
                "UseClaudeChapters": False,
                "UseOCR": False,
                "ForceColumns": False,
                "NoFootnotes": False,
                "NoIndex": False,
                "NoHyperlinks": False,
            },
            "confidence": 0.85,
            "reasoning": reasoning,
        }

    # --- PDF decision tree ---
    signals = classification.get('signals', {})
    density = signals.get('text_density_per_page', 0)
    kb_page = signals.get('file_size_per_page_kb', 0)

    reasoning.append(
        f"Source: {cls_type} ({kb_page:.1f} KB/page, "
        f"{density:.0f} chars/page, confidence {cls_conf:.2f})"
    )

    if text_quality and tq_tier != 'unknown':
        reasoning.append(
            f"Text quality: {tq_tier} (score {tq_score}/100, "
            f"OCR artifact rate {tq_artifact:.0%})"
        )

    if bm_count > 0:
        readable_note = "readable" if bm_readable else "garbled/unreadable"
        reasoning.append(
            f"{bm_count} bookmarks detected ({readable_note}) "
            f"— using {bm_source} for chapters"
        )
    else:
        reasoning.append("No bookmarks — " + (
            "Claude chapter detection recommended"
            if claude_chap else "regex-based chapter detection"
        ))

    # Base recipe from classification + text quality
    if cls_type == 'scan_no_text':
        # Case 1: Image-only scan
        profile = "text-only"
        strategy = ["ocr"]
        flags = _no_structural_flags()
        flags["UseOCR"] = True
        claude_chap_flag = False
        reasoning.append(
            "No text layer — OCR required, skipping all structural elements"
        )

    elif cls_type == 'scan_with_text':
        if tq_score < 50:
            # Case 2: Poor quality scan
            profile = "text-only"
            strategy = ["legacy", "ocr"]
            flags = _default_flags()
            flags["NoFootnotes"] = True
            flags["NoIndex"] = True
            claude_chap_flag = False
            reasoning.append(
                "Poor quality scan — text-only profile, "
                "skipping footnotes and index (unreliable with OCR artifacts)"
            )
        elif tq_score < 75:
            # Case 3: Moderate quality scan
            profile = "clean-read"
            strategy = ["legacy"]
            flags = _default_flags()
            flags["NoHyperlinks"] = True
            claude_chap_flag = claude_chap
            reasoning.append(
                "Moderate quality scan — clean-read profile, "
                "skipping hyperlinks (likely garbled)"
            )
        else:
            # Case 4: Clean quality scan (good OCR)
            profile = "full"
            strategy = ["html_extraction", "legacy"]
            flags = _default_flags()
            flags["UseHtmlExtraction"] = True
            claude_chap_flag = claude_chap
            reasoning.append(
                "Clean scan with good OCR — full profile, HTML extraction"
            )

    elif cls_type == 'digital_native':
        # Case 5: Digital native
        profile = "full"
        strategy = ["html_extraction", "legacy"]
        flags = _default_flags()
        flags["UseHtmlExtraction"] = True
        claude_chap_flag = claude_chap
        reasoning.append(
            "Digital native PDF — full profile, HTML extraction preferred"
        )

    else:
        # Unknown — safe defaults
        profile = "full"
        strategy = ["html_extraction", "legacy"]
        flags = _default_flags()
        flags["UseHtmlExtraction"] = True
        claude_chap_flag = claude_chap
        reasoning.append(
            "Classification unknown — using safe defaults (full profile, HTML extraction)"
        )

    # Column detection override
    if classification.get('flags', {}).get('likely_two_column'):
        if "column_aware" not in strategy:
            strategy.insert(0, "column_aware")
        flags["ForceColumns"] = True
        reasoning.append("Two-column layout detected — column-aware extraction prepended")

    # Claude chapters flag
    flags["UseClaudeChapters"] = claude_chap_flag

    # --- Historical data override ---
    if (historical_data and historical_data.get('has_history') and
            hist_source in ('book_history', 'publisher_profile') and
            hist_score is not None and hist_score >= 70 and
            hist_strat):
        # High-confidence historical match — use proven strategy
        strategy = list(hist_strat)
        reasoning.append(
            f"Historical override ({hist_source}): "
            f"{hist_convs} prior conversions, best score {hist_score} "
            f"with {' -> '.join(hist_strat)}"
        )
        # Boost confidence for agreement
        confidence = min(0.95, confidence + 0.10)

        # Apply historical flags if available
        if raw_historical and raw_historical.get('flags'):
            hist_flags = raw_historical['flags']
            if hist_flags.get('UseClaudeChapters'):
                flags['UseClaudeChapters'] = True
            if hist_flags.get('ForceColumns'):
                flags['ForceColumns'] = True
                if 'column_aware' not in strategy:
                    strategy.insert(0, 'column_aware')

    elif (historical_data and historical_data.get('has_history') and
            hist_source != 'default'):
        # Historical data exists but didn't override — note agreement/disagreement
        confidence = min(0.95, confidence + 0.05)
        reasoning.append(
            f"Historical data ({hist_source}): {hist_convs} conversions, "
            f"best score {hist_score or 'N/A'} — blended with classification"
        )

    # --- Confidence adjustments ---
    if tq_score < 30 or tq_score > 85:
        confidence = min(0.95, confidence + 0.05)
    confidence = min(0.95, round(confidence, 2))

    return {
        "profile": profile,
        "extraction_strategy": strategy,
        "flags": flags,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def _default_flags():
    """Return a fresh set of default (all-off) recipe flags."""
    return {
        "UseHtmlExtraction": False,
        "UseClaudeChapters": False,
        "UseOCR": False,
        "ForceColumns": False,
        "NoFootnotes": False,
        "NoIndex": False,
        "NoHyperlinks": False,
    }


def _no_structural_flags():
    """Return flags with all structural content stripped (for bad scans)."""
    return {
        "UseHtmlExtraction": False,
        "UseClaudeChapters": False,
        "UseOCR": False,
        "ForceColumns": False,
        "NoFootnotes": True,
        "NoIndex": True,
        "NoHyperlinks": True,
    }


# ---------------------------------------------------------------------------
# Main entry: analyze_document()
# ---------------------------------------------------------------------------

def analyze_document(pdf_path, settings=None, db_path=None, verbose=False):
    """Run all pre-flight analysis steps and produce a conversion recipe.

    Args:
        pdf_path: Path to the source ebook file.
        settings: Optional settings dict (from settings.json).
        db_path: Optional explicit database path for pattern_db.
        verbose: Enable diagnostic logging to stderr.

    Returns:
        PreflightResult dict with source_file, format, page_count,
        analysis, recipe, duration_seconds.
    """
    t0 = time.time()
    log_fn = lambda msg: _log(msg, verbose)

    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Source file not found: {pdf_path}")

    ext = pdf_path.suffix.lstrip('.').lower()
    is_pdf = ext == 'pdf'

    # Get page count (PDFs only)
    page_count = 0
    if is_pdf:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
        except Exception:
            pass

    log_fn(f"Pre-flight analysis: {pdf_path.name} ({page_count} pages, {ext})")

    # Load settings for tunable thresholds (optional)
    cfg = _load_settings(settings)

    # --- Step 1: Source Classification ---
    if is_pdf:
        classification = _classify_source(pdf_path, log_fn)
        # Use page count from classification signals if we didn't get it above
        if page_count == 0:
            page_count = classification.get('signals', {}).get('total_pages', 0)
    else:
        classification = {
            "classification": f"{ext}_native",
            "confidence": 0.90,
            "signals": {},
            "recommended_strategies": [],
            "flags": {"needs_ocr": False, "likely_two_column": False},
        }

    # --- Step 2: Text Quality Assessment (PDFs only) ---
    if is_pdf:
        text_quality = _assess_text_quality(pdf_path, page_count, log_fn)
    else:
        text_quality = None

    # --- Step 3: Chapter Structure (PDFs only) ---
    if is_pdf:
        chapter_structure = _assess_chapter_structure(
            pdf_path, page_count, classification, log_fn
        )
    else:
        chapter_structure = {
            "bookmark_count": 0,
            "bookmarks_readable": False,
            "recommended_chapter_source": "format_native",
            "claude_chapters_recommended": False,
        }

    # --- Step 4: Historical Data Lookup (PDFs only) ---
    if is_pdf:
        historical_data, raw_historical = _lookup_historical_data(
            pdf_path, classification, db_path, log_fn
        )
    else:
        historical_data = {
            "has_history": False,
            "source": "default",
            "best_prior_score": None,
            "prior_strategy": [],
            "prior_conversions": 0,
        }
        raw_historical = None

    # --- Step 5: Generate Recipe ---
    recipe = _generate_recipe(
        classification, text_quality, chapter_structure,
        historical_data, raw_historical, ext
    )

    duration = round(time.time() - t0, 2)

    # Build the source_classification subset for output
    cls_output = {
        "classification": classification.get("classification"),
        "confidence": classification.get("confidence", 0.0),
        "signals": {
            "text_density_per_page": classification.get("signals", {}).get("text_density_per_page", 0),
            "file_size_per_page_kb": classification.get("signals", {}).get("file_size_per_page_kb", 0),
        },
        "flags": {
            "needs_ocr": classification.get("flags", {}).get("needs_ocr", False),
            "likely_two_column": classification.get("flags", {}).get("likely_two_column", False),
        },
    }

    result = {
        "source_file": str(pdf_path),
        "format": ext,
        "page_count": page_count,
        "analysis": {
            "source_classification": cls_output,
            "text_quality": text_quality,
            "chapter_structure": chapter_structure,
            "historical_data": historical_data,
        },
        "recipe": recipe,
        "duration_seconds": duration,
    }

    log_fn(f"Pre-flight complete in {duration}s — "
           f"recipe: profile={recipe['profile']}, "
           f"strategy={' -> '.join(recipe['extraction_strategy'])}, "
           f"confidence={recipe['confidence']}")

    return result


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------

def _load_settings(settings=None):
    """Load preflight settings from dict or settings.json file."""
    if settings:
        return settings.get('preflight', {})
    try:
        settings_path = PROJECT_ROOT / "config" / "settings.json"
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('preflight', {})
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Pre-flight document analysis and conversion recipe generator"
    )
    ap.add_argument("--input", required=True, help="Path to source ebook file")
    ap.add_argument("--db-path", default=None,
                    help="Path to pattern database (default: auto-detect)")
    ap.add_argument("--settings", default=None,
                    help="Path to settings.json (default: config/settings.json)")
    ap.add_argument("--verbose", action="store_true",
                    help="Enable diagnostic logging to stderr")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Load settings if provided
    settings = None
    if args.settings:
        try:
            with open(args.settings, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception as e:
            print(f"WARNING: Failed to load settings: {e}", file=sys.stderr)

    # Enable verbose logging
    if args.verbose:
        _log("", verbose=True)  # Set the verbose flag

    result = analyze_document(
        args.input,
        settings=settings,
        db_path=args.db_path,
        verbose=args.verbose,
    )

    # JSON to stdout
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
