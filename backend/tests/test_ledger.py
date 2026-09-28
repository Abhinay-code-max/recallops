"""Ledger rebuild-if-missing-or-stale. None of this touches Hindsight or Groq -- not
marked @pytest.mark.live."""
import json

import pytest
from fastapi.testclient import TestClient

from app import ledger
from app.main import app


def test_ensure_fresh_rebuilds_when_ledger_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.json")
    incidents = ledger.load_seed_incidents()

    assert ledger.read_ledger() is None
    fresh = ledger.ensure_fresh(incidents)

    expected = ledger.compute_ledger(incidents)
    assert fresh["totals"] == expected["totals"]
    assert fresh["counts"] == expected["counts"]
    assert ledger.LEDGER_PATH.exists()


def test_ensure_fresh_rebuilds_when_source_hash_stale(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.json")
    incidents = ledger.load_seed_incidents()
    stale = ledger.compute_ledger(incidents)
    stale["source_hash"] = "not-the-real-hash"
    stale["totals"]["incidents"] = 0  # visibly wrong, so we can tell it got replaced
    ledger.LEDGER_PATH.write_text(json.dumps(stale), encoding="utf-8")

    fresh = ledger.ensure_fresh(incidents)

    assert fresh["source_hash"] != "not-the-real-hash"
    assert fresh["totals"]["incidents"] == len(incidents)


def test_ensure_fresh_keeps_ledger_when_hash_matches(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.json")
    incidents = ledger.load_seed_incidents()
    ledger.write_ledger(incidents)
    original = ledger.read_ledger()

    again = ledger.ensure_fresh(incidents)

    assert again["generated_at"] == original["generated_at"]  # untouched, not rebuilt


def test_deleting_ledger_then_starting_the_app_rebuilds_matching_counts() -> None:
    existing_bytes = ledger.LEDGER_PATH.read_bytes() if ledger.LEDGER_PATH.exists() else None
    try:
        if ledger.LEDGER_PATH.exists():
            ledger.LEDGER_PATH.unlink()
        assert ledger.read_ledger() is None

        with TestClient(app):
            pass  # entering/exiting runs the app's lifespan startup, which calls ledger.ensure_fresh()

        rebuilt = ledger.read_ledger()
        assert rebuilt is not None
        expected = ledger.compute_ledger(ledger.load_seed_incidents())
        assert rebuilt["totals"] == expected["totals"]
        assert rebuilt["counts"] == expected["counts"]
    finally:
        if existing_bytes is not None:
            ledger.LEDGER_PATH.write_bytes(existing_bytes)
