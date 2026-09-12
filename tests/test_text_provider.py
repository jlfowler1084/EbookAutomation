"""Local routing and no-paid-fallback contracts for text analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from llm_providers import text_provider
import extract_tts_text


@pytest.fixture(autouse=True)
def local_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_provider, "load_text_config", lambda: {})
    monkeypatch.setattr(text_provider.requests, "get", Mock(side_effect=requests.ConnectionError("test probe disabled")))
    text_provider.probe_text_endpoint.cache_clear()
    for name in ("EBOOK_TEXT_PROVIDER", "LOCAL_LLM_TEXT_BASE_URL", "LOCAL_LLM_TEXT_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def response(content: str | None = '{"issues": []}', finish: str = "stop") -> Mock:
    result = Mock()
    result.json.return_value = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    return result


def test_local_default_ignores_paid_keys_and_vision_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "paid-key-must-not-be-forwarded")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://vision-host:8080/v1")
    post = Mock(return_value=response())
    monkeypatch.setattr(text_provider.requests, "post", post)
    assert text_provider.request_text(system_prompt="Analyze JSON", user_message="Book text", max_tokens=100) == '{"issues": []}'
    args, kwargs = post.call_args
    assert args[0] == "http://localhost:8000/v1/chat/completions"
    assert "x-api-key" not in kwargs["headers"]
    assert kwargs["json"]["model"] == "sb-chat"
    assert kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert kwargs["json"]["messages"][0]["role"] == "system"


def test_text_overrides_are_independent_of_vision() -> None:
    target = text_provider.resolve_text_target(
        {"base_url": "http://configured:8000/v1", "model": "configured"},
        {"LOCAL_LLM_TEXT_BASE_URL": "http://text:8000/v1/", "LOCAL_LLM_TEXT_MODEL": "flash", "LOCAL_LLM_BASE_URL": "http://vision/v1"},
    )
    assert target["base_url"] == "http://text:8000/v1"
    assert target["model"] == "flash"


def test_explicit_cloud_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EBOOK_TEXT_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    result = Mock()
    result.json.return_value = {"content": [{"type": "text", "text": "{}"}]}
    post = Mock(return_value=result)
    monkeypatch.setattr(text_provider.requests, "post", post)
    text_provider.request_text(system_prompt="JSON", user_message="Text", max_tokens=100)
    args, kwargs = post.call_args
    assert args[0] == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "test-key"
    assert "chat_template_kwargs" not in kwargs["json"]


def test_cloud_config_selects_cloud_but_local_env_wins() -> None:
    assert text_provider.resolve_text_target({"provider": "claude"}, {})["provider"] == "claude"
    assert text_provider.resolve_text_target({"provider": "claude"}, {"EBOOK_TEXT_PROVIDER": "local"})["provider"] == "local"


def test_missing_key_does_not_call_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EBOOK_TEXT_PROVIDER", "claude")
    post = Mock()
    monkeypatch.setattr(text_provider.requests, "post", post)
    with pytest.raises(ValueError, match="requires ANTHROPIC_API_KEY"):
        text_provider.request_text(system_prompt="JSON", user_message="Text", max_tokens=100)
    post.assert_not_called()


def test_local_failure_never_retries_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    post = Mock(side_effect=requests.ConnectionError("local offline"))
    monkeypatch.setattr(text_provider.requests, "post", post)
    with pytest.raises(requests.ConnectionError):
        text_provider.request_text(system_prompt="JSON", user_message="Text", max_tokens=100)
    assert post.call_count == 1
    assert post.call_args.args[0].startswith("http://localhost:")


@pytest.mark.parametrize("content,finish", [(None, "stop"), ("", "stop"), ("{}", "length")])
def test_empty_and_truncated_outputs_fail_closed(monkeypatch: pytest.MonkeyPatch, content: str | None, finish: str) -> None:
    monkeypatch.setattr(text_provider.requests, "post", Mock(return_value=response(content, finish)))
    with pytest.raises(ValueError):
        text_provider.request_text(system_prompt="JSON", user_message="Text", max_tokens=100)


def test_quality_analysis_reaches_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=response('{"issues": [], "recommendations": []}'))
    monkeypatch.setattr(text_provider.requests, "post", post)
    paragraphs = [f"Paragraph {i} with extractionArtifact and enough text to qualify as body text." for i in range(8)]
    _, report = extract_tts_text.ai_quality_pass(paragraphs, lambda _: None)
    assert post.call_count == 1
    assert report["original_score"] == 100


def test_subheading_analysis_reaches_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=response('{"headings": []}'))
    monkeypatch.setattr(text_provider.requests, "post", post)
    paragraphs = ["THE FIRST SECTION", "This is a long body paragraph which follows the section heading. " * 3]
    result, _ = extract_tts_text.ai_detect_subheadings(paragraphs, lambda _: None, has_bookmarks=False)
    assert post.call_count == 1
    assert result == paragraphs


def test_fragment_analysis_reaches_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=response('{"joins": []}'))
    monkeypatch.setattr(text_provider.requests, "post", post)
    paragraphs = ["This is an ordinary paragraph with enough prose and a final stop. " * 3 for _ in range(12)]
    paragraphs[3] = "This paragraph is clearly cut off in the middle of the"
    paragraphs[4] = "sentence and continues for a while with additional explanation. " * 3
    extract_tts_text.ai_rejoin_fragments(paragraphs, lambda _: None)
    assert post.call_count >= 1
    assert all(call.args[0].startswith("http://localhost:") for call in post.call_args_list)


def test_enabled_does_not_require_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert text_provider.text_llm_enabled()
    monkeypatch.setattr(text_provider, "load_text_config", lambda: {"enabled": False})
    assert not text_provider.text_llm_enabled()


def test_config_loading_uses_llm_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"llm": {"text": {"provider": "local", "model": "flash"}}}), encoding="utf-8-sig")
    monkeypatch.setattr(text_provider, "SETTINGS_PATH", config)
    # The autouse fixture replaces the loader; test the original function via
    # its separately captured reference below.
    assert _real_load_text_config()["model"] == "flash"


_real_load_text_config = text_provider.load_text_config


def test_probe_caches_actual_gateway_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    result = Mock()
    result.json.return_value = {"data": [{"id": "sb-chat", "backend_model": "sb-flash", "meta": {"n_ctx": 131072, "ftype": "Q4_K - Medium"}}]}
    get = Mock(return_value=result)
    monkeypatch.setattr(text_provider.requests, "get", get)
    first = text_provider.probe_text_endpoint("http://localhost:8000/v1", "sb-chat")
    second = text_provider.probe_text_endpoint("http://localhost:8000/v1", "sb-chat")
    assert first == second
    assert first == {"probe_ok": True, "model_served": "sb-flash", "n_ctx": 131072, "quantization": "Q4_K - Medium"}
    get.assert_called_once()
