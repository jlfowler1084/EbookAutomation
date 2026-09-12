"""Local vision OCR and explicit provider selection for conversion/remediation.

The public routing functions preserve the Gemini OCR result contracts. Local
inference is the default; selecting ``EBOOK_OCR_PROVIDER=gemini`` or
``llm.ocr.provider=gemini`` is required to use the paid backend. A failed local
request never causes a cloud request.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gemini_ocr import (
    _GEMINI_TRANSCRIPTION_PROMPT,
    _cleanup_safe_path,
    _ensure_safe_path,
    _get_page_count,
    _render_pages,
)
from llm_providers.local_provider import LocalVisionProvider
from visual_qa import (
    default_n_ctx_from_env,
    load_settings_json,
    resolve_local_vqa_target,
)


def get_ocr_provider(settings: Mapping[str, Any] | None = None) -> str:
    """Resolve the OCR provider; API key presence never enables paid calls."""
    if settings is None:
        settings = load_settings_json()
    configured = settings.get("llm", {}).get("ocr", {}).get("provider", "local")
    provider = (os.environ.get("EBOOK_OCR_PROVIDER") or configured or "local").strip().lower()
    if provider not in {"local", "gemini"}:
        raise ValueError(
            f"Unknown OCR provider {provider!r}; choose local or gemini via "
            "EBOOK_OCR_PROVIDER or llm.ocr.provider"
        )
    return provider


def _page_text(raw_text: str, page_number: int) -> str:
    """Normalize one page while rejecting wrong or repeated page markers."""
    text = raw_text.strip()
    if not text:
        raise ValueError(f"Empty OCR response for page {page_number}")
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = text[:-3].strip()
    if not text:
        raise ValueError(f"Empty OCR response for page {page_number}")
    markers = re.findall(r"<<PAGE:(\d+)>>", text)
    if markers and markers != [str(page_number)]:
        raise ValueError(f"OCR page markers {markers} do not match page {page_number}")
    if markers:
        marker = f"<<PAGE:{page_number}>>"
        if not text.startswith(marker):
            raise ValueError(f"Unexpected commentary before OCR page {page_number}")
        text = text[len(marker):].strip()
    return text


def _local_pages(
    pdf_path: str,
    page_numbers: Sequence[int],
    log: Callable[[str], None],
    poppler_path: str | None,
    dpi: int,
    require_complete: bool,
) -> dict[str, Any] | None:
    """Transcribe pages serially, preserving coverage and resolved identity."""
    if dpi <= 0:
        raise ValueError("OCR DPI must be positive")
    requested_pages = list(dict.fromkeys(page_numbers))
    if not requested_pages:
        log("  Local OCR: no pages specified")
        return None
    if any(not isinstance(page, int) or isinstance(page, bool) or page < 1
           for page in requested_pages):
        raise ValueError("OCR page numbers must be positive integers")

    target = resolve_local_vqa_target(settings=load_settings_json())
    provider = LocalVisionProvider(
        base_url=target["base_url"], model=target["model"],
        n_ctx=default_n_ctx_from_env(),
    )
    resolved = provider.describe()
    model = target["model"] or resolved.get("model_served")
    if not model:
        raise RuntimeError("Local OCR could not resolve a served vision model")
    # The shared provider's image estimate is calibrated at 150 DPI. Keep
    # small-window nodes at that resolution; the upgraded 32K node uses 200.
    effective_dpi = min(dpi, 150) if resolved["n_ctx"] < 16384 else dpi
    max_tokens = min(8192, provider.output_budget_for(1))
    provider.batch_size_effective = 1
    provider.max_tokens_effective = max_tokens
    log(f"  Local OCR: {model} at {target['base_url']} "
        f"(n_ctx={resolved['n_ctx']}, {effective_dpi} DPI, one page/request; $0)")

    pages: dict[int, str] = {}
    failed_pages: list[int] = []
    input_tokens = output_tokens = 0
    safe_pdf, temporary_dir = _ensure_safe_path(str(pdf_path))
    try:
        for index, page_number in enumerate(requested_pages, start=1):
            log(f"  Local OCR: page {page_number} ({index}/{len(requested_pages)})")
            try:
                images = _render_pages(
                    safe_pdf, [page_number], dpi=effective_dpi,
                    poppler_path=poppler_path,
                )
                if len(images) != 1 or images[0][0] != page_number:
                    raise ValueError(f"Renderer did not return page {page_number}")
                image_data = base64.b64encode(images[0][1]).decode("ascii")
                payload = {
                    "model": model,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
                    "messages": [
                        {"role": "system", "content": _GEMINI_TRANSCRIPTION_PROMPT},
                        {"role": "user", "content": [
                            {"type": "text", "text": f"--- Page {page_number} ---"},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{image_data}",
                            }},
                            {"type": "text", "text": (
                                f"Transcribe only this page. Begin with <<PAGE:{page_number}>>. "
                                "Return that marker alone if the page has no text."
                            )},
                        ]},
                    ],
                }
                # Reuse the local transport, retry policy and finish_reason
                # truncation guard, without VQA's JSON grading schema.
                response = provider.call(payload)
                input_tokens += response.input_tokens
                output_tokens += response.output_tokens
                pages[page_number] = _page_text(response.raw_text, page_number)
            except Exception as exc:
                # Page remediation can preserve successful local pages while
                # leaving failures in their original form. Full-book OCR must
                # never replace a book with only a successful subset.
                log(f"  Local OCR: page {page_number} failed: {exc}")
                failed_pages.append(page_number)
                if require_complete:
                    log("  Local OCR: incomplete transcription rejected; paid fallback disabled")
                    return None
    finally:
        _cleanup_safe_path(temporary_dir)

    if not pages:
        log("  Local OCR: no usable pages; paid fallback disabled")
        return None
    resolved = provider.describe()
    resolved["dpi_effective"] = effective_dpi
    return {
        "pages": pages,
        "pages_processed": len(pages),
        "failed_pages": failed_pages,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": 0.0,
        "provider": "local",
        "extraction_method": "local_vision",
        "provider_resolved": resolved,
    }


def extract_text_ocr(
    pdf_path: str,
    log: Callable[[str], None],
    api_key: str | None = None,
    poppler_path: str | None = None,
    dpi: int = 200,
    batch_size: int = 5,
    cost_limit: float = 5.0,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Extract a complete book locally, or with explicitly selected Gemini.

    ``model``, ``api_key``, ``batch_size`` and ``cost_limit`` retain their
    Gemini meanings. Local target selection shares the VQA resolver, and
    local inference always uses one page per request.
    """
    if get_ocr_provider() == "gemini":
        from gemini_ocr import extract_text_gemini

        log("  OCR: explicitly selected paid Gemini provider")
        result = extract_text_gemini(
            pdf_path, log, api_key=api_key, poppler_path=poppler_path,
            dpi=dpi, batch_size=batch_size, cost_limit=cost_limit, model=model,
        )
        if result:
            result.update(provider="gemini", extraction_method="gemini_flash")
        return result

    total_pages = _get_page_count(pdf_path)
    if total_pages == 0:
        log("  Local OCR: PDF has no readable pages")
        return None
    result = _local_pages(
        pdf_path, list(range(1, total_pages + 1)), log,
        poppler_path, dpi, require_complete=True,
    )
    if result is not None:
        result["total_pages"] = total_pages
        result["text"] = "\n\n".join(
            f"<<PAGE:{page}>>\n{text}" for page, text in result["pages"].items()
        )
    return result


def remediate_pages_ocr(
    pdf_path: str,
    page_numbers: Sequence[int],
    log: Callable[[str], None],
    api_key: str | None = None,
    poppler_path: str | None = None,
    dpi: int = 200,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Re-extract selected pages with the configured OCR provider."""
    if get_ocr_provider() == "gemini":
        from gemini_ocr import remediate_pages_gemini

        log("  OCR remediation: explicitly selected paid Gemini provider")
        result = remediate_pages_gemini(
            pdf_path, list(page_numbers), log, api_key=api_key,
            poppler_path=poppler_path, dpi=dpi, model=model,
        )
        if result:
            result.update(provider="gemini", extraction_method="gemini_flash")
        return result
    return _local_pages(
        pdf_path, page_numbers, log, poppler_path, dpi, require_complete=False,
    )
