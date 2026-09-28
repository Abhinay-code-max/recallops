import json
from pathlib import Path

from app.memory import mask_secrets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_masks_bearer_token() -> None:
    text = "inbound_headers Authorization: Bearer demo-token-0000 x-signature=sha256=stale"
    masked = mask_secrets(text)
    assert "demo-token-0000" not in masked
    assert "Authorization: Bearer [REDACTED]" in masked


def test_masks_password_in_connection_uri() -> None:
    text = "connection_uri=redis://default:password=hunter2-demo@session-store-0.internal:6379/0"
    masked = mask_secrets(text)
    assert "hunter2-demo" not in masked
    assert "password=[REDACTED]" in masked
    assert "session-store-0.internal:6379/0" in masked  # rest of the URI is untouched


def test_masks_generic_api_key_and_secret() -> None:
    assert "sk-abc123" not in mask_secrets("api_key=sk-abc123")
    assert "topsecret" not in mask_secrets("secret: topsecret")
    assert "tok-999" not in mask_secrets("token=tok-999")


def test_leaves_non_secret_text_unchanged() -> None:
    text = "p99_latency=4820ms error_rate=23.4% deploy=v2.3.0 (12 min ago)"
    assert mask_secrets(text) == text


def test_masking_is_idempotent() -> None:
    text = "Authorization: Bearer demo-token-0000"
    once = mask_secrets(text)
    twice = mask_secrets(once)
    assert once == twice


def test_masks_both_planted_secrets_in_seed_data() -> None:
    incidents = json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))
    by_id = {inc["incident_id"]: inc for inc in incidents}

    masked_013 = mask_secrets(by_id["INC-013"]["log_snippet"])
    assert "demo-token-0000" not in masked_013

    masked_019 = mask_secrets(by_id["INC-019"]["log_snippet"])
    assert "hunter2-demo" not in masked_019
