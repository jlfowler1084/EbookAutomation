#!/usr/bin/env python3
"""Gemini Flash OCR integration for EbookAutomation.

Tier 2.5 extraction: more capable than Tesseract, 10-20x cheaper than Claude Vision.
Uses Google's Gemini 2.5 Flash model for page-image-to-text transcription.

Requires:
    pip install google-genai
    GEMINI_API_KEY environment variable

Two modes:
    Mode A: Full book transcription (all pages)
    Mode B: Page remediation (only VQA-flagged pages)
"""

import os
import re
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_GEMINI_TRANSCRIPTION_PROMPT = """Transcribe ALL text from each page image EXACTLY as it appears.

Rules:
1. Transcribe every word. Never summarize, skip, or paraphrase.
2. Preserve paragraph breaks as blank lines.
3. Mark ALL chapter titles, section headings, and part headings with ## prefix. This is critical for navigation. If text appears visually larger, bolder, or centered on the page — or if it reads like a chapter title (e.g., "Chapter 1", "THE BATTLE OF BUNKER HILL", "INTRODUCTION") — always prefix it with ##. When in doubt, add the ## marker. Examples: ## CHAPTER I, ## THE BATTLE OF BUNKER HILL, ## Introduction, ## Part One: The Early Years.
4. Preserve italic text with *italic* and bold with **bold**.
5. Preserve footnote numbers as [^1], [^2], etc.
6. For block quotes, prefix each line with >
7. Transcribe non-Latin scripts (Hebrew, Greek, etc.) in their original script.
8. Rejoin hyphenated words across line breaks ("con-\\ntinue" → "continue").
9. Do NOT include page numbers, running headers, or running footers.
10. Do NOT add any commentary about the transcription.
11. Separate each page with: <<PAGE:N>> where N is the page number.
12. If a page is blank or image-only with no text, output just the page marker."""


def _get_gemini_client(api_key=None):
    """Create and return a Gemini API client."""
    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "google-genai SDK is required for Gemini OCR. "
            "Install with: python -m pip install google-genai")

    key = api_key or os.environ.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError(
            "Gemini OCR requires GEMINI_API_KEY. "
            "Get a free key from https://aistudio.google.com")

    return genai.Client(api_key=key)


def _ensure_safe_path(pdf_path):
    """Return an ASCII-safe path for poppler, copying if needed.

    Poppler (pdftoppm) can't handle non-ASCII filenames on Windows.
    Returns (safe_path, tmp_dir_or_None). Caller must clean up tmp_dir.
    """
    try:
        pdf_path.encode('ascii')
        return pdf_path, None
    except (UnicodeEncodeError, UnicodeDecodeError):
        import tempfile, shutil
        tmp_dir = tempfile.mkdtemp(prefix='gemini_ocr_')
        tmp_copy = os.path.join(tmp_dir, 'input.pdf')
        shutil.copy2(pdf_path, tmp_copy)
        return tmp_copy, tmp_dir


def _cleanup_safe_path(tmp_dir):
    """Remove temp directory created by _ensure_safe_path."""
    if tmp_dir and os.path.isdir(tmp_dir):
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except OSError:
            pass


def _render_pages(pdf_path, page_numbers, dpi=200, poppler_path=None):
    """Render specific PDF pages to PNG bytes.

    Returns list of (page_number, png_bytes) tuples.
    If pdf_path contains non-ASCII chars, caller should use _ensure_safe_path
    once and pass the safe path to avoid repeated file copies.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from visual_qa import render_pages_to_png, find_poppler_path
    resolved_poppler = find_poppler_path(poppler_path)

    return render_pages_to_png(pdf_path, page_numbers, dpi=dpi,
                                poppler_path=resolved_poppler)


def _get_page_count(pdf_path):
    """Get total page count from a PDF."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_path).pages)
    except Exception:
        return 0


def extract_text_gemini(pdf_path, log, api_key=None, poppler_path=None,
                         dpi=200, batch_size=5, cost_limit=5.0,
                         model='gemini-2.5-flash'):
    """Mode A: Full book transcription via Gemini Flash.

    Renders every page, sends to Gemini in batches, returns clean text.
    Cost: ~$0.0016/page -> ~$0.50 for a 300-page book.

    Returns:
        dict: {text, pages_processed, total_pages, input_tokens, output_tokens, cost_usd}
        or None on failure
    """
    client = _get_gemini_client(api_key)
    from google.genai import types

    total_pages = _get_page_count(pdf_path)
    if total_pages == 0:
        log("  Gemini: PDF has 0 pages")
        return None

    log(f"  Gemini: PDF has {total_pages} pages")

    # Cost estimate (Gemini 2.5 Flash: $0.30/M input, $2.50/M output)
    est_input = total_pages * 1290
    est_output = total_pages * 500
    est_cost = (est_input / 1_000_000) * 0.30 + (est_output / 1_000_000) * 2.50

    log(f"  Gemini: Estimated cost: ${est_cost:.2f} "
        f"({total_pages} pages x ~1790 tokens at {dpi} DPI)")

    if est_cost > cost_limit:
        log(f"  Gemini: ABORTED — estimated cost ${est_cost:.2f} "
            f"exceeds limit ${cost_limit:.2f}")
        return None

    all_page_numbers = list(range(1, total_pages + 1))
    all_text_parts = []
    total_input_tokens = 0
    total_output_tokens = 0
    pages_processed = 0

    # Copy PDF once to ASCII-safe temp path (avoids re-copying per batch)
    safe_pdf, _tmp_dir = _ensure_safe_path(pdf_path)
    if _tmp_dir:
        log(f"  Gemini: Copied to temp path (Unicode filename workaround)")

    try:
        # Diagnostic: confirm heading instruction is present in prompt
        if '##' in _GEMINI_TRANSCRIPTION_PROMPT:
            log(f"  Gemini prompt includes ## heading instruction (rule #3 confirmed)")
        else:
            log(f"  WARNING: Gemini prompt missing ## heading instruction")

        for batch_start in range(0, len(all_page_numbers), batch_size):
            batch_pages = all_page_numbers[batch_start:batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (len(all_page_numbers) + batch_size - 1) // batch_size

            log(f"  Gemini: Batch {batch_num}/{total_batches} — "
                f"pages {batch_pages[0]}-{batch_pages[-1]}")

            try:
                page_images = _render_pages(safe_pdf, batch_pages, dpi=dpi,
                                             poppler_path=poppler_path)
            except Exception as e:
                log(f"  Gemini: Failed to render batch {batch_num}: {e}")
                continue

            if not page_images:
                log(f"  Gemini: No images rendered for batch {batch_num}")
                continue

            contents = []
            for page_num, png_bytes in page_images:
                contents.append(types.Part.from_bytes(
                    data=png_bytes, mime_type='image/png'))
                contents.append(f'--- Page {page_num} ---')
            contents.append(
                f"Transcribe pages {batch_pages[0]} through {batch_pages[-1]} now.")

            try:
                response = client.models.generate_content(
                    model=model,
                    config={'system_instruction': _GEMINI_TRANSCRIPTION_PROMPT},
                    contents=contents
                )

                text = response.text or ''
                usage = response.usage_metadata
                in_tok = (usage.prompt_token_count or 0) if usage else 0
                out_tok = (usage.candidates_token_count or 0) if usage else 0

                total_input_tokens += in_tok
                total_output_tokens += out_tok
                pages_processed += len(batch_pages)

                if text:
                    all_text_parts.append(text)

                log(f"  Gemini: Batch {batch_num} complete — "
                    f"{in_tok:,} in / {out_tok:,} out tokens")

            except Exception as e:
                log(f"  Gemini: Batch {batch_num} failed: {e}")
                continue
    finally:
        _cleanup_safe_path(_tmp_dir)

    if not all_text_parts:
        log("  Gemini: No text extracted from any batch")
        return None

    full_text = '\n'.join(all_text_parts)
    actual_cost = ((total_input_tokens / 1_000_000) * 0.30 +
                   (total_output_tokens / 1_000_000) * 2.50)

    word_count = len(full_text.split())
    log(f"  Gemini: Complete — {pages_processed}/{total_pages} pages, "
        f"{word_count:,} words, ${actual_cost:.4f}")

    return {
        'text': full_text,
        'pages_processed': pages_processed,
        'total_pages': total_pages,
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'cost_usd': actual_cost,
    }


def remediate_pages_gemini(pdf_path, page_numbers, log, api_key=None,
                            poppler_path=None, dpi=200,
                            model='gemini-2.5-flash'):
    """Mode B: Page-level remediation via Gemini Flash.

    Only re-extracts specific pages identified as low quality.
    Cost: ~$0.002/page — remediating 10 pages costs ~$0.02.

    Returns:
        dict: {pages: {N: text, ...}, input_tokens, output_tokens, cost_usd}
        or None on failure
    """
    if not page_numbers:
        log("  Gemini remediate: no pages specified")
        return None

    client = _get_gemini_client(api_key)
    from google.genai import types

    log(f"  Gemini remediate: processing {len(page_numbers)} pages: {page_numbers}")

    safe_pdf, _tmp_dir = _ensure_safe_path(pdf_path)
    try:
        page_images = _render_pages(safe_pdf, page_numbers, dpi=dpi,
                                     poppler_path=poppler_path)
    except Exception as e:
        log(f"  Gemini remediate: render failed: {e}")
        return None
    finally:
        _cleanup_safe_path(_tmp_dir)

    if not page_images:
        log("  Gemini remediate: no images rendered")
        return None

    contents = []
    for page_num, png_bytes in page_images:
        contents.append(types.Part.from_bytes(
            data=png_bytes, mime_type='image/png'))
        contents.append(f'--- Page {page_num} ---')
    contents.append(
        f"Transcribe these {len(page_numbers)} pages. "
        f"Separate each page with <<PAGE:N>> markers.")

    try:
        response = client.models.generate_content(
            model=model,
            config={'system_instruction': _GEMINI_TRANSCRIPTION_PROMPT},
            contents=contents
        )

        text = response.text or ''
        usage = response.usage_metadata
        in_tok = usage.prompt_token_count if usage else 0
        out_tok = usage.candidates_token_count if usage else 0

        actual_cost = ((in_tok / 1_000_000) * 0.30 +
                       (out_tok / 1_000_000) * 2.50)

        log(f"  Gemini remediate: {in_tok:,} in / {out_tok:,} out tokens, "
            f"${actual_cost:.4f}")

        # Parse per-page results
        pages_dict = {}
        current_page = None
        current_text = []

        for line in text.split('\n'):
            page_match = re.match(r'<<PAGE:(\d+)>>', line)
            if page_match:
                if current_page is not None and current_text:
                    pages_dict[current_page] = '\n'.join(current_text).strip()
                current_page = int(page_match.group(1))
                current_text = []
            elif current_page is not None:
                current_text.append(line)

        if current_page is not None and current_text:
            pages_dict[current_page] = '\n'.join(current_text).strip()

        log(f"  Gemini remediate: got text for {len(pages_dict)} pages")

        return {
            'pages': pages_dict,
            'input_tokens': in_tok,
            'output_tokens': out_tok,
            'cost_usd': actual_cost,
        }

    except Exception as e:
        log(f"  Gemini remediate: API call failed: {e}")
        return None
