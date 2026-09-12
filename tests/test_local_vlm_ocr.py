"""Local OCR routing, response integrity, and real HTML remediation seam."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import gemini_ocr
import local_vlm_ocr as ocr
from llm_providers.base import VisionResponse
from llm_providers.local_provider import OutputTruncatedError


def quiet(message: str) -> None:
    pass


@pytest.fixture
def local(monkeypatch):
    """Replace hardware/SDK boundaries, preserving routing and page parsing."""
    monkeypatch.setenv("EBOOK_OCR_PROVIDER", "local")
    monkeypatch.setenv("GEMINI_API_KEY", "unused-paid-key")
    monkeypatch.setenv("LOCAL_LLM_N_CTX", "")
    monkeypatch.setattr(ocr, "load_settings_json", lambda: {
        "visual_qa": {"local_base_url": "http://vision:8080/v1", "local_model": "sb-vision"},
    })
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "")
    monkeypatch.setenv("LOCAL_LLM_VISION_MODEL", "")
    provider = MagicMock()
    provider.describe.return_value = {
        "base_url": "http://vision:8080/v1", "model_served": "sb-vision",
        "n_ctx": 32768, "total_slots": 1, "probe_ok": True,
    }
    provider.output_budget_for.return_value = 24576
    provider.call.return_value = VisionResponse("<<PAGE:1>>\nThe complete first page.", 100, 20)
    constructor = MagicMock(return_value=provider)
    monkeypatch.setattr(ocr, "LocalVisionProvider", constructor)
    monkeypatch.setattr(ocr, "_get_page_count", lambda path: 1)
    monkeypatch.setattr(ocr, "_ensure_safe_path", lambda path: (path, None))
    cleanup = MagicMock()
    monkeypatch.setattr(ocr, "_cleanup_safe_path", cleanup)
    renderer = MagicMock(side_effect=lambda path, pages, **kwargs: [(pages[0], b"png")])
    monkeypatch.setattr(ocr, "_render_pages", renderer)
    cloud = MagicMock(side_effect=AssertionError("Unexpected paid OCR request"))
    monkeypatch.setattr(gemini_ocr, "extract_text_gemini", cloud)
    monkeypatch.setattr(gemini_ocr, "remediate_pages_gemini", cloud)
    return provider, constructor, renderer, cleanup, cloud


def test_local_default_ignores_cloud_model_and_key(local):
    provider, constructor, _, cleanup, cloud = local
    result = ocr.extract_text_ocr("book.pdf", quiet, model="gemini-paid-model")
    assert result["text"] == "<<PAGE:1>>\nThe complete first page."
    assert result["cost_usd"] == 0
    assert result["extraction_method"] == "local_vision"
    assert result["provider_resolved"]["n_ctx"] == 32768
    constructor.assert_called_once_with(base_url="http://vision:8080/v1", model="sb-vision", n_ctx=None)
    payload = provider.call.call_args.args[0]
    assert payload["model"] == "sb-vision"
    assert payload["max_tokens"] == 8192
    assert payload["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["messages"][1]["content"][1]["type"] == "image_url"
    cleanup.assert_called_once()
    cloud.assert_not_called()


@pytest.mark.parametrize("failure", [
    RuntimeError("vision offline"),
    OutputTruncatedError("length", 8192, 8192),
    VisionResponse("", 100, 20),
    VisionResponse("<<PAGE:7>>\nWrong page.", 100, 20),
    VisionResponse("<<PAGE:1>>\nA\n<<PAGE:1>>\nB", 100, 20),
])
def test_local_failures_never_call_paid_backend(local, failure):
    provider, _, _, cleanup, cloud = local
    if isinstance(failure, Exception):
        provider.call.side_effect = failure
    else:
        provider.call.return_value = failure
    assert ocr.extract_text_ocr("book.pdf", quiet) is None
    cleanup.assert_called_once()
    cloud.assert_not_called()


def test_full_book_rejects_partial_coverage(local, monkeypatch):
    provider, _, _, _, cloud = local
    monkeypatch.setattr(ocr, "_get_page_count", lambda path: 3)
    provider.call.side_effect = [
        VisionResponse("<<PAGE:1>>\nFirst page.", 100, 20),
        RuntimeError("lost connection"),
    ]
    assert ocr.extract_text_ocr("book.pdf", quiet) is None
    assert provider.call.call_count == 2
    cloud.assert_not_called()


def test_remediation_keeps_successes_and_reports_failures(local):
    provider, _, renderer, _, cloud = local
    provider.call.side_effect = [
        VisionResponse("<<PAGE:2>>\nRecovered body.", 100, 20),
        RuntimeError("failed page 4"),
        VisionResponse("<<PAGE:5>>", 100, 1),
    ]
    result = ocr.remediate_pages_ocr("book.pdf", [2, 4, 5, 2], quiet)
    assert result["pages"] == {2: "Recovered body.", 5: ""}
    assert result["failed_pages"] == [4]
    assert result["pages_processed"] == 2
    assert [call.args[1] for call in renderer.call_args_list] == [[2], [4], [5]]
    cloud.assert_not_called()


def test_small_window_reduces_render_resolution(local):
    provider, _, renderer, _, _ = local
    provider.describe.return_value["n_ctx"] = 8192
    provider.output_budget_for.return_value = 3468
    result = ocr.extract_text_ocr("book.pdf", quiet)
    assert result["provider_resolved"]["dpi_effective"] == 150
    assert renderer.call_args.kwargs["dpi"] == 150
    assert provider.call.call_args.args[0]["max_tokens"] == 3468


def test_provider_explicit_config_env_and_invalid_values(monkeypatch):
    monkeypatch.delenv("EBOOK_OCR_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "key-is-not-permission")
    assert ocr.get_ocr_provider({}) == "local"
    assert ocr.get_ocr_provider({"llm": {"ocr": {"provider": "gemini"}}}) == "gemini"
    monkeypatch.setenv("EBOOK_OCR_PROVIDER", "local")
    assert ocr.get_ocr_provider({"llm": {"ocr": {"provider": "gemini"}}}) == "local"
    monkeypatch.setenv("EBOOK_OCR_PROVIDER", "misspelled")
    with pytest.raises(ValueError, match="Unknown OCR provider"):
        ocr.get_ocr_provider({})


def test_explicit_gemini_routes_to_existing_backend(local, monkeypatch):
    provider, _, _, _, cloud = local
    monkeypatch.setenv("EBOOK_OCR_PROVIDER", "gemini")
    cloud.side_effect = None
    cloud.return_value = {"text": "cloud text", "cost_usd": 0.02}
    result = ocr.extract_text_ocr("book.pdf", quiet, model="chosen-gemini")
    assert result["provider"] == "gemini"
    assert cloud.call_args.kwargs["model"] == "chosen-gemini"
    provider.call.assert_not_called()


def test_legacy_vision_entry_uses_configured_ocr(local):
    import extract_tts_text as pipeline

    result = pipeline.extract_text_vision("book.pdf", quiet, api_key="old-anthropic-key")
    assert result["provider"] == "local"
    local[-1].assert_not_called()


def test_blank_pages_survive_bridge_and_cli_page_validation():
    import extract_tts_text as pipeline

    paragraphs, _ = pipeline.vision_text_to_para_dicts("<<PAGE:2>>\n\n<<PAGE:3>>", quiet)
    assert [p["page_number"] for p in paragraphs if p["is_page_marker"]] == [2, 3]
    assert pipeline._parse_ocr_pages("5,2,5") == [2, 5]
    with pytest.raises(Exception, match="positive"):
        pipeline._parse_ocr_pages("0,2")


def test_process_html_remediates_exact_page_with_real_formatter(tmp_path, monkeypatch):
    """Exercise the actual process entry, bridge, formatter and HTML rewrite."""
    import extract_tts_text as pipeline
    from pypdf import PdfWriter

    pdf = tmp_path / "book.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    writer.write(pdf)
    body = "This is the original paragraph with enough ordinary words to preserve its formatting. " * 12
    paragraphs, body_size = pipeline.vision_text_to_para_dicts(
        f"<<PAGE:1>>\nBefore sentinel. {body}\n<<PAGE:2>>\nBroken sentinel. {body}"
        f"\n<<PAGE:3>>\nAfter sentinel. {body}", quiet,
    )
    monkeypatch.setattr(pipeline, "extract_bookmarks", lambda *args: [])
    monkeypatch.setattr(pipeline, "resolve_bookmarks_by_coordinates", lambda *args: None)
    monkeypatch.setattr(pipeline, "extract_with_pdfminer_html", lambda *args, **kwargs: (paragraphs, body_size))
    monkeypatch.setattr(pipeline, "score_text_layer_quality", lambda *args, **kwargs: {
        "score": 65, "recommendation": "accept", "tier_suggestion": 2, "details": {},
    })
    monkeypatch.setattr(pipeline, "compute_ocr_debris_density", lambda text: 0.9)
    monkeypatch.setattr(pipeline, "text_llm_enabled", lambda: False)
    monkeypatch.setattr(pipeline, "extract_text_ocr", MagicMock(side_effect=AssertionError("Whole-book OCR")))
    monkeypatch.setattr(ocr, "extract_text_ocr", MagicMock(side_effect=AssertionError("Whole-book VLM")))
    for name in ("_fix_word_merges_html", "_mark_a2_running_headers", "_fix_ligature_splits", "_strip_page_number_debris"):
        monkeypatch.setattr(pipeline, name, lambda *args: None)
    monkeypatch.setattr(pipeline, "rejoin_html_fragments", lambda paragraphs, *args: paragraphs)
    remediate = MagicMock(return_value={
        "pages": {2: "## Repaired chapter\n\nThe recovered *italic phrase* remains in this paragraph."},
        "provider": "local", "provider_resolved": {"model_served": "sb-vision"}, "cost_usd": 0,
    })
    monkeypatch.setattr(ocr, "remediate_pages_ocr", remediate)
    output = tmp_path / "book.html"
    result = pipeline.process_kindle_html(
        str(pdf), str(output), quiet, no_cache=True, extract_images=False,
        skip_footnotes=True, ocr_pages=[2],
    )
    html = output.read_text(encoding="utf-8")
    assert remediate.call_args.args[1] == [2]
    assert "Broken sentinel" not in html
    assert "Before sentinel" in html and "After sentinel" in html
    assert "Repaired chapter" in html
    assert "<em>italic phrase</em>" in html
    assert 'id="page_2"' in html
    assert result["ocr_remediation"]["applied_pages"] == [2]
    assert result["ocr_remediation"]["failed_pages"] == []
    pipeline.extract_text_ocr.assert_not_called()
    ocr.extract_text_ocr.assert_not_called()


@pytest.mark.parametrize("target_page", [1, 2])
def test_targeted_ocr_preserves_neighbor_text_through_real_cross_page_rejoin(tmp_path, monkeypatch, target_page):
    """Replacement must precede merging; either side of a boundary is safe."""
    import extract_tts_text as pipeline
    from pypdf import PdfWriter

    pdf = tmp_path / "boundary.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    writer.write(pdf)
    paragraphs, body_size = pipeline.vision_text_to_para_dicts(
        "<<PAGE:1>>\nOpening sentinel begins a paragraph that crosses a page boundary in the"
        "\n<<PAGE:2>>\nneighbor sentinel continuation completes this ordinary sentence."
        "\n<<PAGE:3>>\nFinal sentinel remains a complete paragraph on the untouched final page.", quiet,
    )
    monkeypatch.setattr(pipeline, "extract_bookmarks", lambda *args: [])
    monkeypatch.setattr(pipeline, "resolve_bookmarks_by_coordinates", lambda *args: None)
    monkeypatch.setattr(pipeline, "extract_with_pdfminer_html", lambda *args, **kwargs: (paragraphs, body_size))
    # A severely garbled source must still reach explicit page remediation.
    monkeypatch.setattr(pipeline, "score_text_layer_quality", lambda *args, **kwargs: {
        "score": 20, "recommendation": "ocr", "tier_suggestion": 2,
        "details": {"common_word_rate": {"hit_rate": 0}},
    })
    monkeypatch.setattr(pipeline, "compute_ocr_debris_density", lambda text: 0.9)
    monkeypatch.setattr(pipeline, "extract_text_ocr", MagicMock(side_effect=AssertionError("Whole-book OCR")))
    monkeypatch.setattr(ocr, "extract_text_ocr", MagicMock(side_effect=AssertionError("Whole-book VLM")))
    replacement = (
        "Corrected opening begins a paragraph that crosses a page boundary in the"
        if target_page == 1 else
        "recovered neighbor continuation completes this ordinary sentence."
    )
    remediate = MagicMock(return_value={
        "pages": {target_page: replacement}, "provider": "local", "cost_usd": 0,
    })
    monkeypatch.setattr(ocr, "remediate_pages_ocr", remediate)
    messages = []
    output = tmp_path / "boundary.html"
    result = pipeline.process_kindle_html(
        str(pdf), str(output), messages.append, no_cache=True, extract_images=False,
        skip_footnotes=True, ocr_pages=[target_page],
    )
    html = output.read_text(encoding="utf-8")
    assert "Final sentinel" in html
    assert html.count("neighbor sentinel" if target_page == 1 else "Opening sentinel") == 1
    assert html.count("Corrected opening" if target_page == 1 else "recovered neighbor") == 1
    assert ("Opening sentinel" if target_page == 1 else "neighbor sentinel") not in html
    assert any("Fragment rejoin: 1 paragraphs merged" in message for message in messages)
    assert not any("PyMuPDF text fallback" in message for message in messages)
    assert result["ocr_remediation"]["applied_pages"] == [target_page]
    assert remediate.call_count == 1
    pipeline.extract_text_ocr.assert_not_called()
    ocr.extract_text_ocr.assert_not_called()
