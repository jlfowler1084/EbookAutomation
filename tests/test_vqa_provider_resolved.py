"""Tests for EB-392 Unit 2: the shared local-VQA target resolver and the
``provider_resolved`` provenance block on VQA reports.

Covers:
  - ``resolve_local_vqa_target()`` precedence (cli > env > config > default)
    and its VqaTargetError when base_url cannot be resolved at any level.
  - ``build_report()``'s additive ``provider_resolved`` kwarg (mirrors
    ``capture_pipeline`` -- present verbatim when supplied, absent on legacy
    calls). Mirrors tests/test_capture_pipeline_derivation.py's
    ``_call_build_report`` helper pattern.
  - ``run_visual_qa()`` populating ``provider_resolved`` from a real
    LocalVisionProvider's describe() (with an injected probe stub -- both
    live local endpoints answer /v1/models on this machine, so every
    provider constructed here MUST stub the probe) as well as from a
    provider with no describe() (Claude/cloud shape).
  - ``visual_qa.main()`` mapping a missing base_url to exit 3, and the
    resolved base_url/model_served surfacing in both the JSON report and the
    stdout summary.
  - config/settings.json's local_model == "sb-vision" and the factory
    resolving the config base_url when no env/CLI override is present.

Import convention: ``from llm_providers.local_provider import
LocalVisionProvider`` (never ``tools.llm_providers``) -- tools/ is inserted
onto sys.path first, mirroring tests/test_local_provider_phase2.py and
tests/test_capture_pipeline_derivation.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visual_qa as vqa  # noqa: E402
from llm_providers.local_provider import LocalVisionProvider  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _stub_probe_32768(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
    """Network-free probe stub -- both http://localhost:8000/v1/models and
    http://192.168.1.33:8080/v1/models are live on this machine, so every
    LocalVisionProvider constructed in this file must inject a probe rather
    than risk hitting either real endpoint.
    """
    return {
        "n_ctx": 32768,
        "n_ctx_source": "models",
        "n_ctx_train": 262144,
        "model_served": model or "sb-vision",
        "models_listed": [model or "sb-vision"],
        "server_type": "llamacpp",
        "total_slots": 1,
        "model_path": "/models/sb-vision.gguf",
        "build_info": "b1234",
        "probe_ok": True,
    }


def _make_fake_completion(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 500,
    finish_reason: str = "stop",
) -> MagicMock:
    """Mirrors tests/test_local_provider_phase2.py's helper of the same name."""
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = content
    fake.choices[0].finish_reason = finish_reason
    fake.usage = MagicMock()
    fake.usage.prompt_tokens = prompt_tokens
    fake.usage.completion_tokens = completion_tokens
    return fake


def _patch_pipeline_internals(monkeypatch, tmp_path, total_pages=100):
    """Mirrors tests/test_capture_pipeline_derivation.py's helper of the same
    name -- patches Calibre/page-rendering/rubric-loading internals so
    run_visual_qa can execute its orchestration logic hermetically.
    """
    monkeypatch.setattr(vqa, "convert_to_pdf",
                        lambda input_path, calibre_path, **kw: str(tmp_path / "converted.pdf"))
    monkeypatch.setattr(vqa, "get_pdf_page_count", lambda *a, **kw: total_pages)
    monkeypatch.setattr(vqa, "get_pdf_bookmarks", lambda *a, **kw: [])
    monkeypatch.setattr(vqa, "select_sample_pages", lambda *a, **kw: [1])
    monkeypatch.setattr(vqa, "render_pages_to_png",
                        lambda *a, **kw: [(1, b"fake_png_bytes")])
    monkeypatch.setattr(vqa.Path, "exists", lambda self: True)
    monkeypatch.setattr(vqa.Path, "read_text", lambda self, **kw: "rubric content")


# ---------------------------------------------------------------------------
# build_report() -- provider_resolved kwarg (mirrors _call_build_report)
# ---------------------------------------------------------------------------

def _minimal_qa_data():
    return {
        "overall_score": 85,
        "category_scores": {},
        "pages": [{"page_number": 1, "score": 85, "issues": []}],
        "summary": "test",
        "top_issues": [],
    }


def _call_build_report(**extra):
    return vqa.build_report(
        book_path="book.kfx",
        qa_data=_minimal_qa_data(),
        total_pages=100,
        pages_sampled=8,
        dpi=150,
        model="sb-vision",
        input_tokens=1000,
        output_tokens=200,
        **extra,
    )


def test_build_report_emits_provider_resolved_verbatim():
    block = {
        "provider": "local", "base_url": "http://192.168.1.33:8080/v1",
        "model_requested": "sb-vision", "model_served": "sb-vision",
        "n_ctx": 32768, "n_ctx_source": "models", "total_slots": 1,
        "model_path": None, "probe_ok": True,
        "batch_size_effective": 8, "max_tokens_effective": 24576,
    }
    report = _call_build_report(provider_resolved=block)
    assert report["provider_resolved"] == block


def test_build_report_legacy_call_omits_provider_resolved():
    """Legacy callers (no provider_resolved kwarg) get no such key -- same
    omit-when-absent convention as capture_pipeline."""
    report = _call_build_report()
    assert "provider_resolved" not in report


def test_build_report_explicit_none_omits_provider_resolved():
    report = _call_build_report(provider_resolved=None)
    assert "provider_resolved" not in report


def test_build_report_provider_resolved_does_not_affect_other_fields():
    with_block = _call_build_report(provider_resolved={"provider": "local"})
    without_block = _call_build_report()
    shared_keys = set(without_block.keys())
    for key in shared_keys:
        assert with_block[key] == without_block[key], (
            f"Field '{key}' changed after adding provider_resolved"
        )


# ---------------------------------------------------------------------------
# resolve_local_vqa_target() -- precedence and error path
# ---------------------------------------------------------------------------

def test_resolver_env_wins_when_no_cli():
    result = vqa.resolve_local_vqa_target(
        settings={"visual_qa": {"local_base_url": "http://config.test/v1",
                                 "local_model": "config-model"}},
        env={"LOCAL_LLM_BASE_URL": "http://env.test/v1",
             "LOCAL_LLM_VISION_MODEL": "env-model"},
    )
    assert result["base_url"] == "http://env.test/v1"
    assert result["base_url_source"] == "env"
    assert result["model"] == "env-model"
    assert result["model_source"] == "env"
    assert result["env_base_url_present_but_empty"] is False
    assert result["env_model_present_but_empty"] is False


def test_resolver_config_wins_when_env_unset():
    result = vqa.resolve_local_vqa_target(
        settings={"visual_qa": {"local_base_url": "http://config.test/v1",
                                 "local_model": "config-model"}},
        env={},
    )
    assert result["base_url"] == "http://config.test/v1"
    assert result["base_url_source"] == "config"
    assert result["model"] == "config-model"
    assert result["model_source"] == "config"


def test_resolver_cli_beats_env_and_config():
    result = vqa.resolve_local_vqa_target(
        cli_base_url="http://cli.test/v1",
        cli_model="cli-model",
        settings={"visual_qa": {"local_base_url": "http://config.test/v1",
                                 "local_model": "config-model"}},
        env={"LOCAL_LLM_BASE_URL": "http://env.test/v1",
             "LOCAL_LLM_VISION_MODEL": "env-model"},
    )
    assert result["base_url"] == "http://cli.test/v1"
    assert result["base_url_source"] == "cli"
    assert result["model"] == "cli-model"
    assert result["model_source"] == "cli"


def test_resolver_empty_env_value_treated_as_unset_but_reported():
    """An empty-string env value falls through to config (treated as unset
    for resolution) but is flagged via *_present_but_empty so callers can
    tell "nothing set" apart from "deliberately blanked"."""
    result = vqa.resolve_local_vqa_target(
        settings={"visual_qa": {"local_base_url": "http://config.test/v1",
                                 "local_model": "config-model"}},
        env={"LOCAL_LLM_BASE_URL": "", "LOCAL_LLM_VISION_MODEL": ""},
    )
    assert result["base_url"] == "http://config.test/v1"
    assert result["base_url_source"] == "config"
    assert result["env_base_url_present_but_empty"] is True
    assert result["model"] == "config-model"
    assert result["model_source"] == "config"
    assert result["env_model_present_but_empty"] is True


def test_resolver_model_defaults_to_none_when_unresolved():
    result = vqa.resolve_local_vqa_target(
        settings={"visual_qa": {"local_base_url": "http://config.test/v1"}},
        env={},
    )
    assert result["model"] is None
    assert result["model_source"] == "default"


def test_resolver_missing_base_url_everywhere_raises_vqa_target_error():
    with pytest.raises(vqa.VqaTargetError):
        vqa.resolve_local_vqa_target(settings={"visual_qa": {}}, env={})


def test_resolver_defaults_settings_and_env_to_empty_when_none():
    """settings=None / env=None must not crash -- settings treated as {},
    env treated as os.environ (exercised indirectly: a config-only base_url
    with env=None only works if LOCAL_LLM_BASE_URL is genuinely unset in the
    real environment, so this test only checks the settings=None contract
    with an explicit CLI override to stay hermetic)."""
    result = vqa.resolve_local_vqa_target(cli_base_url="http://cli.test/v1", settings=None, env={})
    assert result["base_url"] == "http://cli.test/v1"
    assert result["base_url_source"] == "cli"


# ---------------------------------------------------------------------------
# config/settings.json -- sb-vision alias, resolver reads it correctly
# ---------------------------------------------------------------------------

def test_config_settings_json_local_model_is_sb_vision():
    settings = vqa.load_settings_json()
    assert settings.get("visual_qa", {}).get("local_model") == "sb-vision"


def test_resolver_uses_config_base_url_with_no_env_or_cli():
    """No CLI override, no env override (env={} simulates a clean process
    environment) -- the factory must resolve to config's base_url, not any
    literal localhost:8000 fallback."""
    settings = vqa.load_settings_json()
    result = vqa.resolve_local_vqa_target(settings=settings, env={})
    assert result["base_url"] == settings["visual_qa"]["local_base_url"]
    assert result["base_url_source"] == "config"
    assert result["model"] == "sb-vision"
    assert result["model_source"] == "config"


# ---------------------------------------------------------------------------
# run_visual_qa() -- provider_resolved populated from a real LocalVisionProvider
# ---------------------------------------------------------------------------

def test_run_visual_qa_local_provider_report_carries_full_provenance(monkeypatch, tmp_path):
    _patch_pipeline_internals(monkeypatch, tmp_path)
    kfx_input = tmp_path / "book.kfx"
    kfx_input.touch()

    provider = LocalVisionProvider(
        base_url="http://192.168.1.33:8080/v1", model="sb-vision",
        probe=_stub_probe_32768,
    )

    fake_content = json.dumps({
        "pages": [{"page_number": 1, "page_type": "body", "score": 90,
                   "pass": True, "issues": []}],
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        report = vqa.run_visual_qa(
            input_path=kfx_input,
            provider=provider,
            calibre_path="fake_calibre",
            poppler_path="",
            output_dir=str(tmp_path),
            dpi=150,
            max_pages=8,
            model="sb-vision",
            rubric_path="nonexistent_rubric.md",
            pass_threshold=70,
            fallback_enabled=False,
        )

    pr = report["provider_resolved"]
    assert pr["base_url"] == "http://192.168.1.33:8080/v1"
    assert pr["model_served"] == "sb-vision"
    assert pr["n_ctx"] == 32768
    assert pr["n_ctx_source"] == "models"
    assert pr["total_slots"] == 1
    assert pr["model_path"] == "/models/sb-vision.gguf"
    assert pr["probe_ok"] is True
    # n_ctx=32768 -> provider.max_batch_size() == 10, which is not less than
    # the default batch_size=8 param, so effective_batch stays at 8 (the
    # configured cap, not the number of images actually rendered -- only 1).
    assert pr["batch_size_effective"] == 8
    assert pr["max_tokens_effective"] is not None


def test_run_visual_qa_provider_without_describe_block_present_with_none_fields(
    monkeypatch, tmp_path,
):
    """A provider with no describe() (the Claude/cloud shape) must still get
    a provider_resolved block -- present, with None where there is no server
    metadata -- and must never raise."""
    _patch_pipeline_internals(monkeypatch, tmp_path)
    kfx_input = tmp_path / "book.kfx"
    kfx_input.touch()

    provider = MagicMock()
    provider.name = "claude"
    del provider.describe  # simulate a provider that genuinely has no describe()

    mock_response = MagicMock()
    mock_response.input_tokens = 500
    mock_response.output_tokens = 100
    mock_response.raw_text = json.dumps({
        "overall_score": 85, "category_scores": {},
        "pages": [{"page_number": 1, "score": 85, "issues": []}],
        "summary": "ok", "top_issues": [],
    })
    provider.two_pass_call.return_value = mock_response
    provider.call.return_value = mock_response
    provider.estimate_cost.return_value = 0.001

    report = vqa.run_visual_qa(
        input_path=kfx_input,
        provider=provider,
        calibre_path="fake_calibre",
        poppler_path="",
        output_dir=str(tmp_path),
        dpi=150,
        max_pages=8,
        model="claude-haiku-4-5",
        rubric_path="nonexistent_rubric.md",
        pass_threshold=70,
        fallback_enabled=False,
    )

    pr = report["provider_resolved"]
    assert pr["provider"] == "claude"
    assert pr["base_url"] is None
    assert pr["model_requested"] == "claude-haiku-4-5"
    assert pr["model_served"] is None
    assert pr["n_ctx"] is None
    assert pr["n_ctx_source"] is None
    assert pr["total_slots"] is None
    assert pr["model_path"] is None
    assert pr["probe_ok"] is None
    assert pr["batch_size_effective"] == 8  # default batch_size, no adaptive cap
    assert pr["max_tokens_effective"] is None


# ---------------------------------------------------------------------------
# visual_qa.main() -- exit 3 on unresolvable base_url; stdout summary fields
# ---------------------------------------------------------------------------

def test_main_exits_3_when_base_url_unresolvable(monkeypatch, capsys):
    monkeypatch.setattr(vqa, "load_settings_json", lambda: {"visual_qa": {}})
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_VISION_MODEL", raising=False)
    monkeypatch.setattr(
        sys, "argv",
        ["visual_qa.py", "--input", "fake.kfx", "--provider", "local"],
    )

    with pytest.raises(SystemExit) as excinfo:
        vqa.main()

    assert excinfo.value.code == 3
    err = capsys.readouterr().err
    assert "local_base_url" in err or "LOCAL_LLM_BASE_URL" in err


def test_main_stdout_summary_carries_base_url_and_model_served(monkeypatch, tmp_path, capsys):
    _patch_pipeline_internals(monkeypatch, tmp_path)
    kfx_input = tmp_path / "book.kfx"
    kfx_input.touch()

    fake_content = json.dumps({
        "pages": [{"page_number": 1, "page_type": "body", "score": 90,
                   "pass": True, "issues": []}],
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    def fake_local_provider(**kwargs):
        return LocalVisionProvider(probe=_stub_probe_32768, **kwargs)

    monkeypatch.setattr(vqa, "LocalVisionProvider", fake_local_provider)
    monkeypatch.setattr(
        vqa, "load_settings_json",
        lambda: {"visual_qa": {"local_base_url": "http://config.test/v1",
                                "local_model": "sb-vision"}},
    )
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_VISION_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_N_CTX", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "visual_qa.py", "--input", str(kfx_input), "--provider", "local",
        "--output-dir", str(tmp_path),
    ])

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(SystemExit) as excinfo:
            vqa.main()

    assert excinfo.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["base_url"] == "http://config.test/v1"
    assert out["model_served"] == "sb-vision"
