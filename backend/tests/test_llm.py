"""Tests llm.complete() against a fake Groq-shaped client -- no network calls, so these
cover the retry/fallback/JSON-repair/degraded logic in isolation from real Groq latency.
"""
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.llm import complete

settings = get_settings()


class ScriptedClient:
    """Each call to chat.completions.create() consumes the next scripted behavior, in
    order: a string is returned as message.content, an Exception instance is raised."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls: list[str] = []
        outer = self

        class _Completions:
            async def create(_self, model, messages, temperature, response_format=None):
                outer.calls.append(model)
                if not outer._script:
                    raise AssertionError("ScriptedClient script exhausted")
                behavior = outer._script.pop(0)
                if isinstance(behavior, Exception):
                    raise behavior
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=behavior))])

        self.chat = SimpleNamespace(completions=_Completions())


@pytest.mark.asyncio
async def test_success_on_first_try() -> None:
    client = ScriptedClient(["hello world"])
    result = await complete([{"role": "user", "content": "hi"}], client=client)
    assert result.text == "hello world"
    assert result.degraded is False
    assert result.model_used == settings.llm_model_primary
    assert client.calls == [settings.llm_model_primary]


@pytest.mark.asyncio
async def test_strips_inline_think_tags() -> None:
    client = ScriptedClient(["<think>internal scratch notes</think>final answer"])
    result = await complete([{"role": "user", "content": "hi"}], client=client)
    assert result.text == "final answer"
    assert "internal scratch notes" not in result.text


@pytest.mark.asyncio
async def test_json_mode_valid_json() -> None:
    client = ScriptedClient(['{"a": 1}'])
    result = await complete([{"role": "user", "content": "hi"}], json_mode=True, client=client)
    assert result.parsed == {"a": 1}
    assert result.degraded is False


@pytest.mark.asyncio
async def test_json_mode_repairs_code_fence_and_junk() -> None:
    client = ScriptedClient(['Sure, here you go:\n```json\n{"a": 1}\n```\nHope that helps!'])
    result = await complete([{"role": "user", "content": "hi"}], json_mode=True, client=client)
    assert result.parsed == {"a": 1}


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_secondary_model() -> None:
    # primary gets 2 attempts (both unparsable), fallback succeeds on its first attempt
    client = ScriptedClient(["not json", "still not json", '{"a": 2}'])
    result = await complete([{"role": "user", "content": "hi"}], json_mode=True, client=client)
    assert result.parsed == {"a": 2}
    assert result.degraded is False
    assert result.model_used == settings.llm_model_fallback
    assert client.calls == [settings.llm_model_primary, settings.llm_model_primary, settings.llm_model_fallback]


@pytest.mark.asyncio
async def test_all_attempts_timeout_returns_degraded() -> None:
    client = ScriptedClient([TimeoutError(), TimeoutError(), TimeoutError(), TimeoutError()])
    result = await complete([{"role": "user", "content": "hi"}], client=client)
    assert result.degraded is True
    assert result.text == ""
    assert result.model_used is None
    assert len(client.calls) == 4  # 2 attempts x 2 models


@pytest.mark.asyncio
async def test_json_mode_all_malformed_returns_degraded() -> None:
    client = ScriptedClient(["bad", "bad", "bad", "bad"])
    result = await complete([{"role": "user", "content": "hi"}], json_mode=True, client=client)
    assert result.degraded is True
    assert result.parsed is None
