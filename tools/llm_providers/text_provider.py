"""Local-first transport for extraction quality and chapter analysis.

The text gateway is deliberately configured separately from the vision server.
Only an explicit ``llm.text.provider=claude`` or ``EBOOK_TEXT_PROVIDER=claude``
selection enables paid requests. Local failures never trigger a cloud retry.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path

import requests

SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.json"


def load_text_config() -> dict:
    """Load the text route, defaulting to the local gateway if config is absent."""
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        settings = {}
    return settings.get("llm", {}).get("text", {})


def text_llm_enabled() -> bool:
    """Return whether optional text analysis is enabled, independently of keys."""
    return load_text_config().get("enabled", True) is not False


def resolve_text_target(
    config: Mapping | None = None,
    env: Mapping[str, str] | None = None,
    cloud_model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Resolve text-specific environment overrides before configuration defaults."""
    cfg = load_text_config() if config is None else config
    environment = os.environ if env is None else env
    provider = (environment.get("EBOOK_TEXT_PROVIDER") or cfg.get("provider") or "local").lower()
    if provider not in {"local", "claude"}:
        raise ValueError(f"Unsupported text LLM provider: {provider!r}")
    if provider == "local":
        base_url = (
            environment.get("LOCAL_LLM_TEXT_BASE_URL")
            or cfg.get("base_url")
            or "http://localhost:8000/v1"
        )
        model = environment.get("LOCAL_LLM_TEXT_MODEL") or cfg.get("model") or "sb-chat"
    else:
        base_url = "https://api.anthropic.com/v1"
        model = cfg.get("claude_model") or cloud_model
    timeout = float(cfg.get("timeout_seconds", 120))
    if timeout <= 0:
        raise ValueError("llm.text.timeout_seconds must be positive")
    return {"provider": provider, "base_url": base_url.rstrip("/"), "model": model, "timeout": timeout}


@lru_cache(maxsize=8)
def probe_text_endpoint(base_url: str, model: str) -> dict:
    """Record the gateway backend and context window once per process/target."""
    try:
        response = requests.get(base_url + "/models", timeout=5, allow_redirects=False)
        response.raise_for_status()
        models = response.json().get("data", [])
        served = next((item for item in models if item.get("id") == model), None)
        if served is None:
            return {"probe_ok": False, "reason": "requested model absent from /models"}
        meta = served.get("meta") or {}
        return {
            "probe_ok": True,
            "model_served": served.get("backend_model") or served["id"],
            "n_ctx": meta.get("n_ctx"),
            "quantization": meta.get("ftype"),
        }
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        return {"probe_ok": False, "reason": str(exc)}


def request_text(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    cloud_model: str = "claude-haiku-4-5-20251001",
    api_key: str | None = None,
    log: Callable[[str], None] | None = None,
) -> str:
    """Request a JSON text analysis from the selected provider without fallback.

    Credentials do not select a provider. Errors, empty output and truncated
    completions propagate so callers retain their existing graceful-skip behavior.
    """
    target = resolve_text_target(cloud_model=cloud_model)
    local = target["provider"] == "local"
    if log:
        log(f"  Text LLM: provider={target['provider']} model={target['model']} "
            f"base_url={target['base_url']}")
        if local:
            log(f"  Text LLM backend: {json.dumps(probe_text_endpoint(target['base_url'], target['model']))}")
    payload = {
        "model": target["model"],
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": user_message}],
    }
    headers = {"Content-Type": "application/json"}
    if local:
        payload["messages"].insert(0, {"role": "system", "content": system_prompt})
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["response_format"] = {"type": "json_object"}
        endpoint = "/chat/completions"
    else:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("Explicit Claude text provider requires ANTHROPIC_API_KEY")
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        payload["system"] = system_prompt
        endpoint = "/messages"
    response = requests.post(
        target["base_url"] + endpoint,
        headers=headers,
        json=payload,
        timeout=target["timeout"],
        allow_redirects=False,
    )
    response.raise_for_status()
    body = response.json()
    if local:
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("Local text response was truncated; analysis was not applied")
        content = choice["message"].get("content")
    else:
        if body.get("stop_reason") == "max_tokens":
            raise ValueError("Claude text response was truncated; analysis was not applied")
        content = "".join(block["text"] for block in body["content"] if block.get("type") == "text")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{target['provider']} text provider returned no content")
    return content.strip()
