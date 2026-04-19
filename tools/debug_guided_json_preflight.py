"""Unit 4 Step 1 — backend-enforcement preflight probe.

Sends a deliberately-unsatisfiable JSON schema to sb-chat.  If vLLM's
guided-decoding backend is active (guidance or outlines), one of two
outcomes occurs:

  PASS A — server rejects the request with 4xx/5xx (schema validation
            caught before inference).
  PASS B — model emits {"x": "impossible_value_that_model_cannot_choose"}
            because the decoder was forced to the only valid token sequence.

FAIL — model emits any other value for x.  xgrammar silently accepted-and-
        ignored the schema.  Step 2 corpus smoke must NOT run until this is
        resolved via the backend-forcing rollback:
          extra_body={"structured_outputs": {"backend": "guidance"}}

Usage:
    py -3.12 tools/debug_guided_json_preflight.py
    py -3.12 tools/debug_guided_json_preflight.py --base-url http://localhost:8000/v1
    py -3.12 tools/debug_guided_json_preflight.py --model qwen3.5-35b-a3b-fp8

Exit codes:
    0  PASS (enforcement proved)
    1  FAIL (schema silently ignored — rollback required before Step 2)
    2  PASS via server rejection (4xx/5xx)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import openai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("preflight")

FORCED_VALUE = "impossible_value_that_model_cannot_choose"

UNSATISFIABLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x"],
    "properties": {
        "x": {
            "type": "string",
            "enum": [FORCED_VALUE],
        }
    },
}

PROMPT = "Return JSON."


def run_preflight(base_url: str, model: str) -> int:
    """Return 0 (PASS-B), 1 (FAIL), or 2 (PASS-A server rejection)."""
    client = openai.OpenAI(base_url=base_url, api_key="not-needed")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 64,
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "preflight_probe",
                "strict": True,
                "schema": UNSATISFIABLE_SCHEMA,
            },
        },
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }

    logger.info("Preflight probe — base_url=%s  model=%s", base_url, model)
    logger.info("Schema: %s", json.dumps(UNSATISFIABLE_SCHEMA, indent=2))
    logger.info("Sending request...")

    try:
        extra_body = payload.pop("extra_body")
        response = client.chat.completions.create(**payload, extra_body=extra_body)
    except openai.APIStatusError as exc:
        logger.info("Server rejected request with HTTP %s: %s", exc.status_code, exc.message)
        logger.info("")
        logger.info("RESULT: PASS (A) — server-side rejection proves enforcement is live.")
        return 2
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        return 1

    choice = response.choices[0]
    raw = (choice.message.content or "").strip()
    finish_reason = getattr(choice, "finish_reason", "unknown")

    logger.info("finish_reason : %s", finish_reason)
    logger.info("raw response  : %s", raw)

    try:
        parsed = json.loads(raw)
        x_value = parsed.get("x", "<missing>")
    except json.JSONDecodeError:
        x_value = f"<unparseable: {raw[:80]}>"

    logger.info("x value       : %r", x_value)

    if x_value == FORCED_VALUE:
        logger.info("")
        logger.info("RESULT: PASS (B) — decoder forced the only valid token sequence.")
        logger.info("  Schema enforcement is live (guidance or outlines backend active).")
        return 0
    else:
        logger.error("")
        logger.error("RESULT: FAIL — model emitted %r instead of %r.", x_value, FORCED_VALUE)
        logger.error("  xgrammar silently accepted-and-ignored the schema.")
        logger.error("  Apply backend-forcing rollback before running Step 2 smoke:")
        logger.error(
            '  Add extra_body["structured_outputs"]["backend"] = "guidance" in build_request().'
        )
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="vLLM guided_json enforcement preflight probe")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/v1",
        help="sb-chat OpenAI-compatible endpoint base URL",
    )
    parser.add_argument(
        "--model",
        default="qwen3.5-35b-a3b-fp8",
        help="Model identifier as registered in sb-chat",
    )
    args = parser.parse_args()

    exit_code = run_preflight(base_url=args.base_url, model=args.model)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
