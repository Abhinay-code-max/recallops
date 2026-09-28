"""Hindsight memory layer: banks, retain/recall/reflect wrappers, secret masking.

Confirmed against the installed hindsight-client==0.10.1 package by introspection (see
docs/HINDSIGHT_NOTES.md for the full write-up) and against real Hindsight Cloud calls in
scripts/hindsight_smoke.py:
  - hindsight_client.Hindsight(base_url, api_key, timeout) is a sync client; it also
    supports `with Hindsight(...) as client:` (has __enter__/__exit__/close/aclose).
  - client.create_bank(bank_id, name, mission) upserts -- calling it again on an existing
    bank_id does not error, it just updates the profile. Safe to call on every startup.
  - client.retain(bank_id, content, context, document_id, metadata, tags, operation_id) ->
    RetainResponse(success, bank_id, items_count, operation_id, usage). Its own docstring
    says operation_id is "ignored by sync retain" -- it's only honored for idempotent
    retries when retain_async=True. We call retain synchronously (so feedback/postmortem
    writes are immediately recallable), which means a retried sync retain is NOT
    guaranteed idempotent -- so this module does not auto-retry retain. A failure raises
    MemoryUnavailableError once, rather than risk writing the same memory twice.
  - client.recall(bank_id, query, max_tokens, budget, ...) -> RecallResponse(results=[...]).
    Each RecallResult has: id, text, type, context, occurred_start, occurred_end,
    mentioned_at, document_id, metadata (dict we control), tags, and scores -- scores is a
    RecallScores *pydantic model*, not a dict (confirmed via RecallScores.model_fields),
    with attributes .final/.semantic/.keyword/.reranker.
  - client.reflect(bank_id, query, budget, context) -> ReflectResponse(text, based_on,
    usage). `.text` is the natural-language answer.
  - retain/recall/reflect are all POST endpoints. The client's own aiohttp_retry layer
    only retries DELETE/GET/HEAD/OPTIONS/PUT/TRACE (POST is excluded, presumably because
    it isn't safe to retry without an idempotency key) -- recall/reflect are read-only, so
    this module retries them itself; retain is not retried, for the reason above.
  - HTTP-level errors raise hindsight_client_api.exceptions.ApiException (and subclasses
    BadRequestException/UnauthorizedException/ForbiddenException/NotFoundException/
    ServiceException). Network/timeout failures before a response exists surface as
    OSError/TimeoutError from the underlying aiohttp transport.

Banks per docs/SPEC.md section 4: incidents, fix-outcomes, team, baseline (baseline is
never retained to -- it exists only for the no-memory demo comparison).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from hindsight_client import Hindsight
from hindsight_client_api.exceptions import ApiException

from app.config import get_settings

logger = logging.getLogger("recallops.memory")

BANK_INCIDENTS = "incidents"
BANK_FIX_OUTCOMES = "fix-outcomes"
BANK_TEAM = "team"
BANK_BASELINE = "baseline"
ALL_BANKS = (BANK_INCIDENTS, BANK_FIX_OUTCOMES, BANK_TEAM, BANK_BASELINE)

_RETRYABLE_EXCEPTIONS = (ApiException, TimeoutError, OSError)
_RECALL_REFLECT_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.5


class MemoryUnavailableError(Exception):
    """Hindsight did not respond successfully after retries.

    Callers (routes) should catch this and return a graceful, non-frozen response --
    per docs/SPEC.md section 10: "Hindsight unavailable or slow: timeout with graceful
    message; UI does not freeze."
    """


@lru_cache
def get_client() -> Hindsight:
    settings = get_settings()
    return Hindsight(
        base_url=settings.hindsight_base_url,
        api_key=settings.hindsight_api_key or None,
        timeout=settings.hindsight_timeout,
    )


def ensure_banks() -> None:
    """Create (or upsert) all four banks. Safe to call repeatedly / on every startup."""
    client = get_client()
    missions = {
        BANK_INCIDENTS: "Every ShipFast incident: symptoms, root cause, resolution, postmortem.",
        BANK_FIX_OUTCOMES: "Each fix attempt for a ShipFast incident and whether it worked, partially worked, or failed.",
        BANK_TEAM: "Who resolved what at ShipFast, their specialties, and their fix preferences.",
        BANK_BASELINE: "Intentionally empty -- used only for the no-memory demo comparison.",
    }
    for bank_id in ALL_BANKS:
        client.create_bank(bank_id=bank_id, name=bank_id, mission=missions[bank_id])


# --- secret masking -----------------------------------------------------------------
# Order matters: header/URI-shaped patterns before the generic key=value fallback.
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"((?:password|passwd|pwd)\s*=\s*)[^\s@&]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"((?:api[_-]?key|secret|token)\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
]


def mask_secrets(text: str) -> str:
    """Scrub tokens/passwords/keys out of text before it is retained to Hindsight."""
    masked = text
    for pattern, replacement in _SECRET_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


# --- typed recall result --------------------------------------------------------------
@dataclass
class RecallHit:
    incident_id: str | None
    date: str | None
    relevance: float | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _to_recall_hit(result: Any) -> RecallHit:
    metadata = result.metadata or {}
    return RecallHit(
        incident_id=metadata.get("incident_id"),
        date=result.occurred_start or result.mentioned_at,
        relevance=result.scores.final if result.scores is not None else None,
        text=result.text,
        metadata=metadata,
    )


# --- retry helper -----------------------------------------------------------------
def _with_retries(fn, *, max_attempts: int, op_name: str):
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            logger.warning("hindsight %s attempt %d/%d failed: %s", op_name, attempt, max_attempts, type(exc).__name__)
            if attempt < max_attempts:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise MemoryUnavailableError(f"Hindsight {op_name} failed after {max_attempts} attempts") from last_exc


# --- public wrappers -----------------------------------------------------------------
def retain(
    bank_id: str,
    content: str,
    *,
    context: str | None = None,
    document_id: str | None = None,
    metadata: dict[str, str] | None = None,
    tags: list[str] | None = None,
):
    """Retain one memory. Masks secrets in `content` first.

    Not retried: retain is called synchronously (so it's immediately recallable), and the
    client's operation_id idempotency key only applies to async retain -- a sync retry
    isn't guaranteed to be a no-op, so on failure this raises MemoryUnavailableError once
    instead of risking a duplicate memory.
    """
    masked_content = mask_secrets(content)
    client = get_client()

    try:
        return client.retain(
            bank_id=bank_id,
            content=masked_content,
            context=context,
            document_id=document_id,
            metadata=metadata,
            tags=tags,
        )
    except _RETRYABLE_EXCEPTIONS as exc:
        logger.warning("hindsight retain(%s) failed: %s", bank_id, type(exc).__name__)
        raise MemoryUnavailableError(f"Hindsight retain({bank_id}) failed") from exc


def recall(bank_id: str, query: str, *, max_tokens: int = 4096, budget: str = "mid") -> list[RecallHit]:
    client = get_client()
    response = _with_retries(
        lambda: client.recall(bank_id=bank_id, query=query, max_tokens=max_tokens, budget=budget),
        max_attempts=_RECALL_REFLECT_MAX_ATTEMPTS,
        op_name=f"recall({bank_id})",
    )
    return [_to_recall_hit(r) for r in response.results]


def reflect(bank_id: str, query: str, *, budget: str = "low", context: str | None = None) -> str:
    client = get_client()
    response = _with_retries(
        lambda: client.reflect(bank_id=bank_id, query=query, budget=budget, context=context),
        max_attempts=_RECALL_REFLECT_MAX_ATTEMPTS,
        op_name=f"reflect({bank_id})",
    )
    return response.text
