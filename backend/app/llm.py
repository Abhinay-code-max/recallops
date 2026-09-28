"""Single wrapper for all Groq LLM calls in this app -- per CLAUDE.md, no other module
imports groq directly.

Confirmed live before building this (not guessed):
- Both LLM_MODEL_PRIMARY=openai/gpt-oss-120b and LLM_MODEL_FALLBACK=qwen/qwen3.8-27b
  exist on Groq (checked via client.models.list()).
- gpt-oss-120b puts its chain-of-thought in a separate message.reasoning field, not
  inline in .content -- confirmed via a live completion (message.model_dump() has a
  distinct "reasoning" key). qwen3.8-27b also exposes a reasoning field (None in the
  tested case). This module never reads .reasoning; it additionally strips any inline
  <think>/<reasoning> tags from .content defensively, in case a different prompt or
  model ever inlines them instead.
- response_format={"type": "json_object"} is supported by both models on Groq and
  produced valid JSON in testing -- used for every json_mode call, on top of the
  _repair_json fallback below, to reduce (not eliminate) malformed JSON.

Behaviour: retries the primary model (transient failures / malformed JSON when
json_mode=True), then falls back to the fallback model with the same retry policy, all
within one total deadline. Never raises -- on total failure this returns
LLMResult(degraded=True), so callers (e.g. the briefing route) fall back to a template
instead of a 500.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from groq import AsyncGroq

from app.config import get_settings

logger = logging.getLogger("recallops.llm")

_THINK_TAG_RE = re.compile(r"<(think|reasoning)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_MAX_ATTEMPTS_PER_MODEL = 2
_RETRY_BACKOFF_SECONDS = 0.5


@lru_cache
def get_client() -> AsyncGroq:
    settings = get_settings()
    return AsyncGroq(api_key=settings.groq_api_key, timeout=settings.llm_timeout)


@dataclass
class LLMResult:
    text: str
    degraded: bool
    model_used: str | None = None
    parsed: Any | None = None  # set only when json_mode=True and parsing succeeded


def _strip_thinking(text: str) -> str:
    return _THINK_TAG_RE.sub("", text).strip()


def _repair_json(text: str) -> Any | None:
    """Progressively looser strategies to pull valid JSON out of an LLM response."""
    text = _CODE_FENCE_RE.sub("", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


async def _call_model(client: Any, model: str, messages: list[dict], *, json_mode: bool, temperature: float) -> str:
    kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=temperature)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    return _strip_thinking(content)


async def complete(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
    client: Any = None,
) -> LLMResult:
    """The one entry point for all LLM calls. `client` is injectable for tests (a fake
    object exposing an async `chat.completions.create(...)`); defaults to the real
    AsyncGroq singleton."""
    settings = get_settings()
    active_client = client if client is not None else get_client()

    async def _try_model(model: str) -> tuple[str, Any | None] | None:
        for attempt in range(1, _MAX_ATTEMPTS_PER_MODEL + 1):
            try:
                text = await _call_model(active_client, model, messages, json_mode=json_mode, temperature=temperature)
            except Exception as exc:
                logger.warning("llm %s attempt %d/%d failed: %s", model, attempt, _MAX_ATTEMPTS_PER_MODEL, type(exc).__name__)
                if attempt < _MAX_ATTEMPTS_PER_MODEL:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            if not json_mode:
                return text, None
            parsed = _repair_json(text)
            if parsed is not None:
                return text, parsed
            logger.warning("llm %s attempt %d/%d returned unparsable JSON", model, attempt, _MAX_ATTEMPTS_PER_MODEL)
            if attempt < _MAX_ATTEMPTS_PER_MODEL:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
        return None

    async def _run() -> LLMResult:
        for model in (settings.llm_model_primary, settings.llm_model_fallback):
            result = await _try_model(model)
            if result is not None:
                text, parsed = result
                return LLMResult(text=text, degraded=False, model_used=model, parsed=parsed)
        return LLMResult(text="", degraded=True)

    try:
        return await asyncio.wait_for(_run(), timeout=settings.llm_timeout)
    except Exception as exc:
        logger.warning("llm.complete degraded: %s", type(exc).__name__)
        return LLMResult(text="", degraded=True)
