"""Thin async wrapper around the Anthropic SDK.

Every AI call in the platform goes through here. Benefits:
  - single place to swap models
  - unified retry / timeout / token accounting
  - prompts are versioned files, loaded by name
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from alpago.core.config import settings
from alpago.core.logging import log

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def load_prompt(name: str) -> str:
    """Load a versioned prompt file. e.g. 'screen_cv.v1' -> prompts/screen_cv.v1.txt"""
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


async def ask(
    *,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    """Send one message, return the assistant's text."""
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": model or settings.ai_model_standard,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    log.debug(
        "ai.call",
        model=kwargs["model"],
        in_tokens=resp.usage.input_tokens,
        out_tokens=resp.usage.output_tokens,
    )
    return "".join(block.text for block in resp.content if block.type == "text")


async def ask_json(
    *,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
) -> dict:
    """Ask for a JSON reply. Expects the model to return a single JSON object
    (optionally wrapped in a ```json code fence). Raises ValueError on bad JSON.
    """
    text = await ask(prompt=prompt, system=system, model=model, max_tokens=max_tokens, temperature=0.1)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned non-JSON: {text[:200]}") from e
