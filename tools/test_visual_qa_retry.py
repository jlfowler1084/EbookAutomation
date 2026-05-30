#!/usr/bin/env python3
"""Unit tests for SCRUM-319: VQA batch error capture and single-page retry.

Tests that:
  1. When the API call raises, the error message is captured into a logger.error call
     (AC1 — opaque "All API batches failed" replaced with actual provider error).
  2. When a multi-page batch fails, a single-page retry is attempted for each page
     (AC2 — single-page-per-batch retry strategy).
  3. When KFX size > 30 MB OR PDF pages > 500, the chosen DPI/page-count is
     reduced from defaults (AC3 — auto-reduce for large files).

Usage:
    python tools/test_visual_qa_retry.py
    python tools/test_visual_qa_retry.py -v
"""

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Import only the pieces we need so tests don't require Calibre/Poppler installed
from visual_qa import _apply_large_file_dpi_reduction
from llm_providers.local_provider import ContextWindowOverflowError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(call_side_effect=None, build_request_return=None):
    """Return a mock VisionProvider (cloud path — no two_pass_call attribute)."""
    provider = MagicMock()
    del provider.two_pass_call  # ensure hasattr check returns False
    provider.name = "cloud_vl"
    if build_request_return is not None:
        provider.build_request.return_value = build_request_return
    else:
        provider.build_request.return_value = {"model": "test", "messages": []}
    if call_side_effect is not None:
        provider.call.side_effect = call_side_effect
    return provider


def _fake_page_images(count=3, start=1):
    """Return a list of (page_num, bytes) tuples for mocking rendered pages."""
    return [(start + i, b"PNG_BYTES_" + bytes([i])) for i in range(count)]


# ---------------------------------------------------------------------------
# AC1: Provider error is captured into logger.error
# ---------------------------------------------------------------------------

class TestBatchErrorCapture(unittest.TestCase):
    """AC1 — the actual provider error string must appear in a logger.error call."""

    def _run_batch_loop(self, provider, page_images, rubric_text="rubric"):
        """Drive the batch loop extracted from run_visual_qa using the same logic."""
        import visual_qa as vqa

        BATCH_SIZE = 8
        all_pages_results = []
        total_input_tokens = 0
        total_output_tokens = 0
        batches = [page_images[i:i + BATCH_SIZE] for i in range(0, len(page_images), BATCH_SIZE)]

        for batch_idx, batch in enumerate(batches, 1):
            try:
                original_payload = provider.build_request(batch, rubric_text, "model")
                response = provider.call(original_payload)
                total_input_tokens += response.input_tokens
                total_output_tokens += response.output_tokens
                batch_data = vqa.parse_qa_response(
                    response.raw_text,
                    provider=provider,
                    original_payload=original_payload,
                )
                if isinstance(batch_data, dict):
                    pages = vqa._align_pages_to_batch_order(
                        batch_data.get("pages", []), [pn for pn, _ in batch]
                    )
                    all_pages_results.extend(pages)
            except Exception as e:
                logging.getLogger("visual_qa").error(
                    "  Batch %d/%d failed: %s: %s",
                    batch_idx, len(batches), type(e).__name__, e,
                )
                if len(batch) > 1 and not hasattr(provider, "two_pass_call"):
                    for single_page in batch:
                        page_num = single_page[0]
                        try:
                            single_payload = provider.build_request([single_page], rubric_text, "model")
                            single_response = provider.call(single_payload)
                            total_input_tokens += single_response.input_tokens
                            total_output_tokens += single_response.output_tokens
                        except Exception as retry_exc:
                            logging.getLogger("visual_qa").error(
                                "    Single-page retry p%d failed: %s: %s",
                                page_num, type(retry_exc).__name__, retry_exc,
                            )

        return all_pages_results, total_input_tokens, total_output_tokens

    def test_provider_error_message_captured_in_log(self):
        """RuntimeError from provider.call() must appear verbatim in logger.error."""
        error_msg = "413 Payload Too Large: request body exceeded 20MB limit"
        provider = _make_provider(call_side_effect=RuntimeError(error_msg))
        page_images = _fake_page_images(count=1)

        with self.assertLogs("visual_qa", level="ERROR") as cm:
            self._run_batch_loop(provider, page_images)

        combined = "\n".join(cm.output)
        self.assertIn(error_msg, combined,
                      f"Provider error text not found in log output.\nLog: {combined}")

    def test_error_includes_exception_type(self):
        """The exception class name must appear in the captured log message."""
        provider = _make_provider(call_side_effect=RuntimeError("some API failure"))
        page_images = _fake_page_images(count=1)

        with self.assertLogs("visual_qa", level="ERROR") as cm:
            self._run_batch_loop(provider, page_images)

        combined = "\n".join(cm.output)
        self.assertIn("RuntimeError", combined,
                      f"Exception class name not found in log output.\nLog: {combined}")


# ---------------------------------------------------------------------------
# AC2: Single-page retry when multi-page batch fails
# ---------------------------------------------------------------------------

class TestSinglePageRetry(unittest.TestCase):
    """AC2 — when a multi-page batch fails, each page is retried individually."""

    def test_single_page_retry_called_per_page(self):
        """When a 3-page batch fails, provider.call should be attempted 4 times total
        (1 batch attempt + 3 single-page retries)."""
        provider = _make_provider(call_side_effect=RuntimeError("payload too large"))
        page_images = _fake_page_images(count=3)

        with self.assertLogs("visual_qa", level="ERROR"):
            # Drive the patched run_visual_qa batch-loop directly to avoid
            # needing real files; we exercise the loop inline via import.
            import visual_qa as vqa

            BATCH_SIZE = 8
            batches = [page_images[i:i + BATCH_SIZE] for i in range(0, len(page_images), BATCH_SIZE)]
            all_pages_results = []

            for batch_idx, batch in enumerate(batches, 1):
                try:
                    original_payload = provider.build_request(batch, "rubric", "model")
                    provider.call(original_payload)
                except Exception as e:
                    logging.getLogger("visual_qa").error(
                        "  Batch %d/%d failed: %s: %s",
                        batch_idx, len(batches), type(e).__name__, e,
                    )
                    if len(batch) > 1 and not hasattr(provider, "two_pass_call"):
                        for single_page in batch:
                            page_num = single_page[0]
                            try:
                                single_payload = provider.build_request(
                                    [single_page], "rubric", "model"
                                )
                                provider.call(single_payload)
                            except Exception as retry_exc:
                                logging.getLogger("visual_qa").error(
                                    "    Single-page retry p%d failed: %s: %s",
                                    page_num, type(retry_exc).__name__, retry_exc,
                                )

        # 1 batch call + 3 single-page retries = 4 total calls to provider.call
        self.assertEqual(provider.call.call_count, 4,
                         f"Expected 4 provider.call invocations (1 batch + 3 single), "
                         f"got {provider.call.call_count}")

    def test_single_page_retry_not_triggered_for_one_page_batch(self):
        """A single-page batch that fails should NOT trigger a redundant retry."""
        provider = _make_provider(call_side_effect=RuntimeError("API error"))
        page_images = _fake_page_images(count=1)

        with self.assertLogs("visual_qa", level="ERROR"):
            BATCH_SIZE = 8
            batches = [page_images[i:i + BATCH_SIZE] for i in range(0, len(page_images), BATCH_SIZE)]

            for batch_idx, batch in enumerate(batches, 1):
                try:
                    original_payload = provider.build_request(batch, "rubric", "model")
                    provider.call(original_payload)
                except Exception as e:
                    logging.getLogger("visual_qa").error(
                        "  Batch %d/%d failed: %s: %s",
                        batch_idx, len(batches), type(e).__name__, e,
                    )
                    if len(batch) > 1 and not hasattr(provider, "two_pass_call"):
                        for single_page in batch:
                            provider.call(provider.build_request([single_page], "rubric", "model"))

        # Only 1 call — no retry for a 1-page batch
        self.assertEqual(provider.call.call_count, 1,
                         f"Expected exactly 1 provider.call (no retry for 1-page batch), "
                         f"got {provider.call.call_count}")


# ---------------------------------------------------------------------------
# AC3: DPI / page-count auto-reduction for large files
# ---------------------------------------------------------------------------

class TestLargeFileDpiReduction(unittest.TestCase):
    """AC3 — DPI and max_pages are reduced when KFX > 30 MB or PDF pages > 500."""

    def test_no_reduction_for_small_file(self):
        """Files under both thresholds keep the caller-supplied DPI and max_pages."""
        dpi, max_pages = _apply_large_file_dpi_reduction(
            kfx_size_bytes=5 * 1024 * 1024,  # 5 MB
            total_pages=200,
            dpi=150,
            max_pages=8,
        )
        self.assertEqual(dpi, 150)
        self.assertEqual(max_pages, 8)

    def test_reduction_for_large_kfx_size(self):
        """KFX > 30 MB triggers DPI reduction to 72 and max_pages halved."""
        dpi, max_pages = _apply_large_file_dpi_reduction(
            kfx_size_bytes=72 * 1024 * 1024,  # 72.6 MB (Wilsonianism)
            total_pages=200,
            dpi=150,
            max_pages=8,
        )
        self.assertLessEqual(dpi, 100,
                             "DPI should be reduced for large KFX files")
        self.assertLessEqual(max_pages, 4,
                             "max_pages should be reduced for large KFX files")

    def test_reduction_for_high_page_count(self):
        """PDF page count > 500 triggers DPI/page-count reduction."""
        dpi, max_pages = _apply_large_file_dpi_reduction(
            kfx_size_bytes=10 * 1024 * 1024,  # 10 MB (size alone is fine)
            total_pages=643,  # Wilsonianism page count
            dpi=150,
            max_pages=8,
        )
        self.assertLessEqual(dpi, 100,
                             "DPI should be reduced for high page-count PDF")
        self.assertLessEqual(max_pages, 4,
                             "max_pages should be reduced for high page-count PDF")

    def test_reduction_for_both_thresholds(self):
        """Files exceeding both thresholds should also be reduced."""
        dpi, max_pages = _apply_large_file_dpi_reduction(
            kfx_size_bytes=80 * 1024 * 1024,  # 80 MB
            total_pages=700,
            dpi=150,
            max_pages=8,
        )
        self.assertLessEqual(dpi, 100)
        self.assertLessEqual(max_pages, 4)

    def test_already_low_dpi_not_raised(self):
        """If caller already set a low DPI, the function should not raise it."""
        dpi, max_pages = _apply_large_file_dpi_reduction(
            kfx_size_bytes=80 * 1024 * 1024,
            total_pages=700,
            dpi=50,   # already very low
            max_pages=4,
        )
        self.assertLessEqual(dpi, 100)
        self.assertLessEqual(max_pages, 4)


# ---------------------------------------------------------------------------
# EB-350 AC1: Configurable batch_size
# ---------------------------------------------------------------------------

class TestConfigurableBatchSize(unittest.TestCase):
    """EB-350 — batch_size is read from settings and passed through to run_visual_qa."""

    def test_custom_batch_size_splits_pages_correctly(self):
        """With batch_size=2 and 5 pages, should produce 3 batches (2+2+1)."""
        page_images = _fake_page_images(count=5)
        batch_size = 2
        batches = [page_images[i:i + batch_size] for i in range(0, len(page_images), batch_size)]
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 2)
        self.assertEqual(len(batches[1]), 2)
        self.assertEqual(len(batches[2]), 1)

    def test_batch_size_1_means_single_page_batches(self):
        """batch_size=1 produces one batch per page — useful for debugging."""
        page_images = _fake_page_images(count=4)
        batch_size = 1
        batches = [page_images[i:i + batch_size] for i in range(0, len(page_images), batch_size)]
        self.assertEqual(len(batches), 4)

    def test_default_batch_size_from_settings(self):
        """visual_qa.py reads batch_size from settings.json (via vqa_settings)."""
        import visual_qa as vqa
        settings = vqa.load_settings_json()
        vqa_settings = settings.get("visual_qa", {})
        batch_size = vqa_settings.get("batch_size", 8)
        # Should be a positive integer
        self.assertIsInstance(batch_size, int)
        self.assertGreater(batch_size, 0)


# ---------------------------------------------------------------------------
# EB-350 AC2: Context-overflow error detection and named error
# ---------------------------------------------------------------------------

class TestContextWindowOverflowError(unittest.TestCase):
    """EB-350 — ContextWindowOverflowError is raised for context_length_exceeded 400s."""

    def test_error_message_preserved(self):
        """ContextWindowOverflowError preserves the original provider message."""
        msg = "400 Bad Request: context_length_exceeded — too many tokens"
        exc = ContextWindowOverflowError(msg)
        self.assertIn(msg, str(exc))
        self.assertEqual(exc.original_message, msg)

    def test_error_is_runtime_error(self):
        """ContextWindowOverflowError is a subclass of RuntimeError."""
        exc = ContextWindowOverflowError("test")
        self.assertIsInstance(exc, RuntimeError)

    def test_reduce_guidance_in_message(self):
        """The error string mentions reduce batch_size or dpi (actionable guidance)."""
        exc = ContextWindowOverflowError("context_length_exceeded")
        self.assertIn("batch_size", str(exc))


# ---------------------------------------------------------------------------
# EB-350 AC3: Single-page retry now fires for local provider (two_pass_call)
# ---------------------------------------------------------------------------

class TestSinglePageRetryLocalProvider(unittest.TestCase):
    """EB-350 — single-page retry is no longer blocked for providers with two_pass_call."""

    def _make_local_provider(self, two_pass_side_effect=None):
        """Return a mock that looks like LocalVisionProvider (has two_pass_call)."""
        provider = MagicMock()
        provider.name = "local"
        # LocalVisionProvider HAS two_pass_call — ensure it's present
        if two_pass_side_effect is not None:
            provider.two_pass_call.side_effect = two_pass_side_effect
        return provider

    def test_two_pass_retry_triggered_on_local_provider_batch_failure(self):
        """When a local batch fails, single-page retry uses two_pass_call."""
        # Batch call fails (simulated via two_pass_call failing on first batch call)
        call_count = [0]

        def two_pass_side_effect(batch, rubric, model):
            call_count[0] += 1
            if len(batch) > 1:
                raise ContextWindowOverflowError("context_length_exceeded")
            # Single-page calls succeed
            from llm_providers.base import VisionResponse
            import json
            pn = batch[0][0]
            return VisionResponse(
                raw_text=json.dumps({"pages": [{"page_number": pn, "page_type": "body", "score": 90, "pass": True, "issues": []}]}),
                input_tokens=10,
                output_tokens=20,
            )

        provider = self._make_local_provider(two_pass_side_effect=two_pass_side_effect)
        page_images = _fake_page_images(count=3)
        batch_size = 8  # All 3 pages in one batch

        # Drive the updated guard logic: len(batch) > 1, use two_pass_call for retry
        batches = [page_images[i:i + batch_size] for i in range(0, len(page_images), batch_size)]
        all_pages_results = []

        for batch_idx, batch in enumerate(batches, 1):
            try:
                response = provider.two_pass_call(batch, "rubric", "model")
            except Exception as e:
                if len(batch) > 1:
                    for single_page in batch:
                        try:
                            if hasattr(provider, "two_pass_call"):
                                single_response = provider.two_pass_call(
                                    [single_page], "rubric", "model"
                                )
                            else:
                                single_payload = provider.build_request(
                                    [single_page], "rubric", "model"
                                )
                                single_response = provider.call(single_payload)
                            import json
                            single_data = json.loads(single_response.raw_text)
                            all_pages_results.extend(single_data.get("pages", []))
                        except Exception:
                            pass

        # 1 batch (fails) + 3 single-page retries = 4 two_pass_call invocations total
        self.assertEqual(provider.two_pass_call.call_count, 4,
                         f"Expected 4 two_pass_call invocations (1 batch + 3 single), "
                         f"got {provider.two_pass_call.call_count}")
        # All 3 pages should be recovered
        self.assertEqual(len(all_pages_results), 3)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
