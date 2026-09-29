"""Test isolation: tests NOT marked `live` must never reach Hindsight or Groq.

Entering `with TestClient(app)` runs the real app lifespan (main.py), which creates banks, checks
whether the incidents bank is empty (and would auto-seed), and starts a background reflect -- all
Hindsight network calls. For non-live tests those three startup side effects are replaced with
no-ops. Production code is untouched; tests that mock `memory.reflect` themselves still override
this default, and `live` tests keep the real behaviour.
"""
from __future__ import annotations

import pytest

from app import memory, seeding


@pytest.fixture(autouse=True)
def _no_network_in_offline_tests(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live") is not None:
        return

    async def _noop_ensure_banks() -> None:
        return None

    async def _offline_reflect(*args, **kwargs) -> str:
        return ""

    monkeypatch.setattr(memory, "ensure_banks", _noop_ensure_banks)
    monkeypatch.setattr(memory, "reflect", _offline_reflect)
    monkeypatch.setattr(seeding, "start_auto_seed_if_empty", lambda: None)
