#!/usr/bin/env python3
"""Pre-flight PDF source classification.

Analyzes a PDF in 3-5 seconds to determine its source type (digital-native,
scan with text, scan without text) so the converge loop can route it to the
right extraction strategy sequence before iteration 1.

CLI:
    python tools/classify_source.py --input "book.pdf"

Output (JSON to stdout):
    {
        "classification": "digital_native",
        "confidence": 0.92,
        "signals": { ... },
        "recommended_strategies": ["html_extraction", "legacy", "column_aware"],
        "flags": { ... }
    }
"""

import argparse
import json
import logging
import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr,  # keep stdout clean for JSON output
)
log = logging.getLogger(__name__)

# --- Known PDF producer strings ---
SCAN_PRODUCERS = [
    "google", "abbyy", "xerox", "kofax", "scansn", "fujitsu",
    "canon", "epson", "hp scan", "naps2", "vuescan",
]
DIGITAL_PRODUCERS = [
    "indesign", "acrobat", "latex", "word", "libreoffice", "prince",
    "weasyprint", "wkhtmltopdf", "quark", "scribus", "pages",
    "openoffice", "microsoft",
]


def _load_config():
    """Load classify settings from config/settings.json if available."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
    defaults = {
        "sample_pages": 3,
        "min_text_density_digital": 500,
        "min_text_density_scan_with_text": 50,
        "scan_producers": SCAN_PRODUCERS,
    }
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            classify_cfg = cfg.get("classify", {})
            for k, v in classify_cfg.items():
                defaults[k] = v
        except Exception:
            pass
    return defaults


def _pick_sample_pages(total_pages, n_samples=3):
    """Pick n body pages to sample, skipping front matter (first 5 pages)."""
    if total_pages <= 5:
        # Very short PDF — sample what we can
        return [max(0, total_pages - 1)]

    body_start = min(5, total_pages - 1)
    body_end = total_pages - 1

    if n_samples == 1:
        return [body_start]

    # Pick: page ~10 (or body_start), page at 33%, page at 66%
    candidates = [
        min(10, body_end),
        body_start + (body_end - body_start) // 3,
        body_start + 2 * (body_end - body_start) // 3,
    ]
    # De-duplicate and clamp
    pages = sorted(set(max(body_start, min(p, body_end)) for p in candidates))
    return pages[:n_samples]


def _signal_file_size_ratio(pdf_path, page_count):
    """Signal 1: File size per page ratio (instant)."""
    file_size = os.path.getsize(pdf_path)
    if page_count <= 0:
        return file_size, 0.0
    bytes_per_page = file_size / page_count
    kb_per_page = bytes_per_page / 1024.0
    log.info("Signal 1 (file size): %.1f KB/page (%d bytes, %d pages)",
             kb_per_page, file_size, page_count)
    return file_size, kb_per_page


def _signal_text_density(pdf_path, sample_pages):
    """Signal 2: Text density sampling via pypdf (< 2 seconds)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf not available — skipping text density signal")
        return None, []

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        log.warning("pypdf failed to open PDF: %s", e)
        return None, []

    char_counts = []
    for page_idx in sample_pages:
        if page_idx >= len(reader.pages):
            continue
        try:
            text = reader.pages[page_idx].extract_text() or ""
            char_counts.append(len(text.strip()))
        except Exception:
            char_counts.append(0)

    if not char_counts:
        return 0.0, char_counts

    avg_density = sum(char_counts) / len(char_counts)
    log.info("Signal 2 (text density): %.1f chars/page avg (samples: %s)",
             avg_density, char_counts)
    return avg_density, char_counts


def _signal_image_vs_text(pdf_path, sample_pages):
    """Signal 3: Image vs text object ratio via PyMuPDF + column detection."""
    try:
        import fitz  # pymupdf
    except ImportError:
        log.warning("pymupdf not available — skipping image/text signal")
        return None, 0, False

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        log.warning("pymupdf failed to open PDF: %s", e)
        return None, 0, False

    image_dominant_count = 0
    two_column_count = 0

    for page_idx in sample_pages:
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]

        # Check text blocks vs images
        text_blocks = page.get_text("blocks")
        images = page.get_images(full=True)
        text_block_count = len([b for b in text_blocks if b[6] == 0])  # type 0 = text

        # Image dominance: no text blocks but has images
        if text_block_count == 0 and len(images) > 0:
            image_dominant_count += 1
        elif len(images) > 0:
            # Check if images cover > 80% of page area
            page_area = page.rect.width * page.rect.height
            img_area = 0
            for img in images:
                # Get image bounding boxes from the page
                # img tuple: (xref, smask, width, height, bpc, colorspace, alt.colorspace, name, filter, referencer)
                pass  # We can't easily get bbox from get_images; use block-level check instead
            # Fallback: if only 1 text block and multiple images, likely scan
            if text_block_count <= 1 and len(images) >= 1:
                image_dominant_count += 1

        # Column detection: check if text block x-coordinates cluster into two groups
        if text_block_count >= 4:
            x_coords = sorted([b[0] for b in text_blocks if b[6] == 0])
            page_width = page.rect.width
            mid = page_width / 2.0

            left_blocks = [x for x in x_coords if x < mid * 0.8]
            right_blocks = [x for x in x_coords if x > mid * 0.6]

            if left_blocks and right_blocks and len(left_blocks) >= 2 and len(right_blocks) >= 2:
                # Check that left and right clusters are distinct
                left_max = max(left_blocks)
                right_min = min(right_blocks)
                if right_min - left_max > page_width * 0.05:
                    two_column_count += 1

    doc.close()

    image_dominant = image_dominant_count >= 2 or (
        len(sample_pages) == 1 and image_dominant_count == 1
    )
    likely_two_column = two_column_count >= 2 or (
        len(sample_pages) == 1 and two_column_count == 1
    )

    log.info("Signal 3 (image/text): %d/%d image-dominant pages, two_column=%s",
             image_dominant_count, len(sample_pages), likely_two_column)
    return image_dominant, image_dominant_count, likely_two_column


def _signal_producer(pdf_path):
    """Signal 4: PDF Producer and Creator metadata (instant)."""
    producer = None
    creator = None
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        meta = reader.metadata
        if meta:
            producer = meta.get('/Producer', '') or ''
            if not producer:
                producer = getattr(meta, 'producer', '') or ''
            creator = meta.get('/Creator', '') or ''
            if not creator:
                creator = getattr(meta, 'creator', '') or ''
    except Exception:
        pass

    if not producer:
        # Try pymupdf as fallback
        try:
            import fitz
            doc = fitz.open(pdf_path)
            meta = doc.metadata
            producer = meta.get('producer', '') or ''
            creator = creator or meta.get('creator', '') or ''
            doc.close()
        except Exception:
            pass

    log.info("Signal 4 (producer): '%s'", producer or '(none)')
    return producer or '', creator or ''


def classify_pdf(pdf_path: str | Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify a PDF source file. Returns a dict with classification results."""
    if config is None:
        config = _load_config()

    pdf_path = str(pdf_path)
    result = {
        "classification": "unknown",
        "confidence": 0.0,
        "signals": {
            "text_density_per_page": 0.0,
            "file_size_per_page_kb": 0.0,
            "text_pages_sampled": 0,
            "text_pages_with_content": 0,
            "image_dominant_pages": 0,
            "pdf_producer": "",
            "pdf_creator": "",
            "has_text_layer": False,
            "total_pages": 0,
        },
        "recommended_strategies": [],
        "flags": {
            "skip_html_extraction": False,
            "needs_ocr": False,
            "likely_two_column": False,
            "needs_paid_tier": False,
            "recommended_paid_tier": None,
        },
    }

    # Get page count via pypdf
    total_pages = 0
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
    except ImportError:
        log.error("pypdf not available — cannot classify")
        return result
    except Exception as e:
        log.error("Failed to read PDF: %s", e)
        return result

    if total_pages == 0:
        log.warning("PDF has 0 pages")
        return result

    result["signals"]["total_pages"] = total_pages

    n_samples = config.get("sample_pages", 3)
    sample_pages = _pick_sample_pages(total_pages, n_samples)
    result["signals"]["text_pages_sampled"] = len(sample_pages)

    # Signal 1: File size ratio
    file_size, kb_per_page = _signal_file_size_ratio(pdf_path, total_pages)
    result["signals"]["file_size_per_page_kb"] = round(kb_per_page, 1)

    # Signal 2: Text density
    text_density, char_counts = _signal_text_density(pdf_path, sample_pages)
    if text_density is not None:
        result["signals"]["text_density_per_page"] = round(text_density, 1)
        result["signals"]["text_pages_with_content"] = sum(1 for c in char_counts if c > 50)
        result["signals"]["has_text_layer"] = text_density > 50
    else:
        text_density = 0.0

    # Signal 3: Image vs text (pymupdf) + column detection
    image_dominant = False
    image_dominant_count = 0
    likely_two_column = False
    img_result = _signal_image_vs_text(pdf_path, sample_pages)
    if img_result[0] is not None:
        image_dominant, image_dominant_count, likely_two_column = img_result
        result["signals"]["image_dominant_pages"] = image_dominant_count
        result["flags"]["likely_two_column"] = likely_two_column

    # Signal 4: Producer metadata
    producer, creator = _signal_producer(pdf_path)
    result["signals"]["pdf_producer"] = producer
    result["signals"]["pdf_creator"] = creator

    # --- Classification decision tree ---
    min_digital = config.get("min_text_density_digital", 500)
    min_scan_text = config.get("min_text_density_scan_with_text", 50)
    scan_producers_list = config.get("scan_producers", SCAN_PRODUCERS)

    producer_lower = producer.lower()
    is_scan_producer = any(sp in producer_lower for sp in scan_producers_list)
    is_digital_producer = any(dp in producer_lower for dp in DIGITAL_PRODUCERS)

    if text_density < min_scan_text and image_dominant:
        # Scan with no usable text layer, pages are images
        result["classification"] = "scan_no_text"
        result["confidence"] = 0.95
        result["recommended_strategies"] = ["ocr"]
        result["flags"]["needs_ocr"] = True
        result["flags"]["skip_html_extraction"] = True

    elif text_density < min_scan_text and not image_dominant:
        # Very low text but not obviously image-dominant — might be metadata-only
        result["classification"] = "scan_no_text"
        result["confidence"] = 0.70
        result["recommended_strategies"] = ["ocr"]
        result["flags"]["needs_ocr"] = True
        result["flags"]["skip_html_extraction"] = True

    elif text_density < min_digital and (image_dominant or kb_per_page > 100):
        # Has some text (likely OCR layer) but source is a scan
        result["classification"] = "scan_with_text"
        result["confidence"] = 0.85
        result["recommended_strategies"] = ["legacy", "column_aware", "ocr"]
        result["flags"]["skip_html_extraction"] = True

    elif text_density >= min_digital and not image_dominant:
        # Good text density, not image-dominant — digital native
        result["classification"] = "digital_native"
        result["confidence"] = 0.90
        result["recommended_strategies"] = ["html_extraction", "legacy", "column_aware"]
        result["flags"]["skip_html_extraction"] = False

    else:
        # Edge case: high text density but image-dominant (unusual)
        result["classification"] = "digital_native"
        result["confidence"] = 0.60
        result["recommended_strategies"] = ["html_extraction", "legacy", "column_aware"]
        result["flags"]["skip_html_extraction"] = False

    # Boost confidence if producer metadata agrees
    if is_scan_producer and result["classification"].startswith("scan"):
        result["confidence"] = min(1.0, result["confidence"] + 0.05)
    elif is_digital_producer and result["classification"] == "digital_native":
        result["confidence"] = min(1.0, result["confidence"] + 0.05)
    elif is_scan_producer and result["classification"] == "digital_native":
        # Producer says scan but text density says digital — reduce confidence
        result["confidence"] = max(0.3, result["confidence"] - 0.15)
    elif is_digital_producer and result["classification"].startswith("scan"):
        # Producer says digital but density says scan — reduce confidence
        result["confidence"] = max(0.3, result["confidence"] - 0.15)

    # ── Producer-based routing overrides (SCRUM-148 + SCRUM-167) ────
    # Internet Archive scans — Tesseract can't read LuraDocument-recoded images
    if 'internet archive' in producer_lower:
        if text_density < 200:
            result["classification"] = "scan_no_text"
            result["confidence"] = max(result["confidence"], 0.85)
            result["flags"]["needs_ocr"] = True
            result["flags"]["needs_paid_tier"] = True
            result["flags"]["recommended_paid_tier"] = "gemini"
            result["recommended_strategies"] = ["gemini", "vision", "ocr", "html_extraction"]
            log.info("Producer override: Internet Archive with low text density "
                     "-> scan_no_text (paid tier recommended)")
        else:
            # Has some text — try OCR first, Gemini as backup
            result["classification"] = "scan_with_text"
            result["confidence"] = max(result["confidence"], 0.70)
            result["recommended_strategies"] = ["ocr", "html_extraction", "gemini"]
            log.info("Producer override: Internet Archive with text "
                     "-> scan_with_text (OCR preferred, Gemini backup)")

    # LuraDocument recoded PDFs — image content in incompatible format
    if 'luradocument' in producer_lower or 'lura' in producer_lower:
        if text_density < 200:
            result["classification"] = "scan_no_text"
            result["confidence"] = max(result["confidence"], 0.80)
            result["flags"]["needs_ocr"] = True
            result["flags"]["needs_paid_tier"] = True
            result["flags"]["recommended_paid_tier"] = "gemini"
            result["recommended_strategies"] = ["gemini", "vision", "ocr", "html_extraction"]
            log.info("Producer override: LuraDocument with low text density "
                     "-> scan_no_text (paid tier recommended)")

    # Override: high text density + high file size per page = scan with OCR text layer
    # Digital-native PDFs are typically < 15 KB/page (text + vector graphics only)
    # Scanned PDFs with OCR are typically > 25 KB/page (full-page raster image + text layer)
    if result["classification"] == "digital_native" and kb_per_page > 25:
        result["classification"] = "scan_with_text"
        result["confidence"] = max(result["confidence"] - 0.1, 0.6)
        result["recommended_strategies"] = ["html_extraction", "legacy", "column_aware"]
        result["flags"]["skip_html_extraction"] = False
        log.info("Reclassified: digital_native -> scan_with_text "
                 "(file size %.1f KB/page indicates scanned pages with OCR text layer)",
                 kb_per_page)
        # If producer also matches known scan tools, boost confidence
        if is_scan_producer:
            result["confidence"] = min(result["confidence"] + 0.1, 0.95)

    # ── Compound failure prediction (SCRUM-167) ─────────────────────
    # Any producer with high image density + no text + no bookmarks
    # is almost certainly a scan that needs paid-tier extraction.
    # Conservative: requires BOTH low text density (<50 chars/page)
    # AND high file size (>50 KB/page = large raster images).
    if (not result["flags"].get("needs_paid_tier")
            and text_density < 50
            and kb_per_page > 50):
        result["flags"]["needs_paid_tier"] = True
        result["flags"]["recommended_paid_tier"] = "gemini"
        if "gemini" not in result["recommended_strategies"]:
            result["recommended_strategies"] = (
                ["gemini"] + result["recommended_strategies"]
            )
        log.info("Compound failure prediction: low text (%.0f chars/page) + "
                 "large file (%.0f KB/page) -> paid tier recommended",
                 text_density, kb_per_page)

    # Column detection: prepend column_aware if detected
    if likely_two_column:
        strats = result["recommended_strategies"]
        if "column_aware" in strats:
            strats.remove("column_aware")
        strats.insert(0, "column_aware")
        result["recommended_strategies"] = strats

    result["confidence"] = round(result["confidence"], 2)

    log.info("Classification: %s (confidence: %.2f)",
             result["classification"], result["confidence"])
    log.info("Recommended strategies: %s",
             " -> ".join(result["recommended_strategies"]))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-flight PDF source classification"
    )
    parser.add_argument(
        '--input', required=True,
        help='Path to PDF file to classify'
    )
    args = parser.parse_args()

    pdf_path = args.input
    if not os.path.isfile(pdf_path):
        log.error("File not found: %s", pdf_path)
        sys.exit(1)

    result = classify_pdf(pdf_path)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
