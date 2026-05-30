"""EB-350: proactive adaptive batch sizing from the provider context window.

The grader's reactive overflow retry (ContextWindowOverflowError -> single-page
retry) stays in place; these tests cover the *proactive* path that sizes batches
to the probed n_ctx before any request is sent.
"""
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import visual_qa  # noqa: E402
from visual_qa import (  # noqa: E402
    estimate_max_batch_for_context,
    resolve_effective_batch_size,
)

# ~1000 tokens of rubric (4 chars/token heuristic), representative of the real prompt.
RUBRIC = "x" * 4000


# ---------------------------------------------------------------------------
# Pure estimator
# ---------------------------------------------------------------------------

def test_small_ctx_reduces_batch():
    # An 8k context at 100 DPI cannot hold 8 page-images -> expect a reduction.
    eff = estimate_max_batch_for_context(8192, 100, RUBRIC, 8)
    assert 1 <= eff < 8


def test_large_ctx_keeps_configured():
    # A 32k context comfortably holds 8 images at 100 DPI -> no reduction.
    eff = estimate_max_batch_for_context(32768, 100, RUBRIC, 8)
    assert eff == 8


def test_higher_dpi_costs_more():
    # 150-DPI images cost ~dpi**2 more tokens -> smaller-or-equal batch than 72 DPI.
    hi_dpi = estimate_max_batch_for_context(8192, 150, RUBRIC, 8)
    lo_dpi = estimate_max_batch_for_context(8192, 72, RUBRIC, 8)
    assert hi_dpi <= lo_dpi


def test_never_below_one():
    # Even a tiny context at very high DPI must still attempt one image.
    assert estimate_max_batch_for_context(1024, 300, RUBRIC, 8) == 1


def test_none_or_zero_nctx_returns_configured():
    assert estimate_max_batch_for_context(None, 100, RUBRIC, 8) == 8
    assert estimate_max_batch_for_context(0, 100, RUBRIC, 8) == 8


def test_batch_size_one_is_passthrough():
    assert estimate_max_batch_for_context(8192, 150, RUBRIC, 1) == 1


def test_cfg_override_changes_estimate():
    # A larger per-image token estimate should reduce the batch further.
    base = estimate_max_batch_for_context(32768, 100, RUBRIC, 8)
    bigger = estimate_max_batch_for_context(
        32768, 100, RUBRIC, 8, cfg={"tokens_per_image_100dpi": 6000}
    )
    assert bigger <= base


# ---------------------------------------------------------------------------
# Provider-aware wrapper
# ---------------------------------------------------------------------------

class _ProbeProvider:
    name = "local"

    def __init__(self, n_ctx):
        self._n = n_ctx

    def probe_context_window(self):
        return self._n


class _NoProbeProvider:
    name = "cloud"


def test_resolve_with_probe_reduces():
    eff, n_ctx = resolve_effective_batch_size(_ProbeProvider(8192), 8, 100, RUBRIC)
    assert n_ctx == 8192
    assert 1 <= eff < 8


def test_resolve_without_probe_passthrough():
    eff, n_ctx = resolve_effective_batch_size(_NoProbeProvider(), 8, 100, RUBRIC)
    assert n_ctx is None
    assert eff == 8


def test_resolve_probe_returns_none_passthrough():
    eff, n_ctx = resolve_effective_batch_size(_ProbeProvider(None), 8, 100, RUBRIC)
    assert n_ctx is None
    assert eff == 8


def test_resolve_probe_raises_is_safe():
    class _Boom:
        name = "local"

        def probe_context_window(self):
            raise RuntimeError("boom")

    eff, n_ctx = resolve_effective_batch_size(_Boom(), 8, 100, RUBRIC)
    assert eff == 8 and n_ctx is None


def test_resolve_probe_returns_nonint_passthrough():
    # Regression: a MagicMock provider auto-creates probe_context_window() returning
    # a truthy Mock. A non-int probe result must fall back to the configured size,
    # not poison the estimator with arithmetic on a non-number.
    class _Garbage:
        name = "local"

        def probe_context_window(self):
            return object()  # not an int

    eff, n_ctx = resolve_effective_batch_size(_Garbage(), 8, 150, RUBRIC)
    assert eff == 8 and n_ctx is None


# ---------------------------------------------------------------------------
# LocalVisionProvider probe parsing (skipped on Linux — provider refuses to
# instantiate off-LAN per EB-210/EB-339)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform.startswith("linux"),
                    reason="LocalVisionProvider raises on Linux (off-LAN guard)")
def test_local_provider_probe_parses_llamacpp_props(monkeypatch):
    # local_provider uses a relative import (from .base import ...), so it must be
    # imported package-qualified (tools/ is already on sys.path above).
    from llm_providers.local_provider import LocalVisionProvider

    p = LocalVisionProvider(base_url="http://192.168.1.33:8080/v1")
    monkeypatch.setattr(
        p, "_http_get_json",
        lambda url, timeout=4.0: (
            {"default_generation_settings": {"n_ctx": 8192}}
            if url.endswith("/props") else None
        ),
    )
    assert p.probe_context_window() == 8192
    # Cached: a second call returns the same value without re-probing.
    assert p.probe_context_window() == 8192


@pytest.mark.skipif(sys.platform.startswith("linux"),
                    reason="LocalVisionProvider raises on Linux (off-LAN guard)")
def test_local_provider_probe_parses_vllm_models(monkeypatch):
    # local_provider uses a relative import (from .base import ...), so it must be
    # imported package-qualified (tools/ is already on sys.path above).
    from llm_providers.local_provider import LocalVisionProvider

    p = LocalVisionProvider(base_url="http://localhost:8000/v1")
    monkeypatch.setattr(
        p, "_http_get_json",
        lambda url, timeout=4.0: (
            {"data": [{"id": "qwen", "max_model_len": 32768}]}
            if url.endswith("/models") else None
        ),
    )
    assert p.probe_context_window() == 32768


@pytest.mark.skipif(sys.platform.startswith("linux"),
                    reason="LocalVisionProvider raises on Linux (off-LAN guard)")
def test_local_provider_probe_failure_returns_none(monkeypatch):
    # local_provider uses a relative import (from .base import ...), so it must be
    # imported package-qualified (tools/ is already on sys.path above).
    from llm_providers.local_provider import LocalVisionProvider

    p = LocalVisionProvider(base_url="http://192.168.1.33:8080/v1")
    monkeypatch.setattr(p, "_http_get_json", lambda url, timeout=4.0: None)
    assert p.probe_context_window() is None
