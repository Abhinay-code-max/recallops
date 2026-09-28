"""Hindsight memory layer: banks, retain/recall/reflect wrappers, secret masking.

Confirmed against the installed hindsight-client==0.10.1 package by introspection and by
running every call live against real Hindsight Cloud -- see docs/HINDSIGHT_NOTES.md,
including "## Verified behaviours" for the live-tested facts this module's design is
built on (timestamp truncation, update_mode semantics, no single-document delete,
concurrency/event-loop behaviour, metadata/document_id coverage, delete_bank
consistency).

This module is async-first: FastAPI runs one event loop per worker, and Step A's live
concurrency test confirmed that's the only combination that's actually safe --
`asyncio.gather` over the native async twins (aretain/arecall/areflect) on ONE client
instance, entirely within one event loop, worked cleanly, while a raw
ThreadPoolExecutor sharing one sync client instance crashed every call (a previously
sync client even broke later in the same process once asyncio.run() ran elsewhere).
There is no synchronous entry point in this module on purpose.

Banks per docs/SPEC.md section 4, plus one addition from this project's parallel-agent
Step B rules (no single-document/memory delete exists -- see HINDSIGHT_NOTES.md point
3 -- so live-created memories can't be selectively wiped out of a bank that also holds
seed data):
  - incidents, fix-outcomes, team: seeded, effectively read-only after POST /seed.
  - baseline: intentionally empty, always -- the no-memory demo comparison.
  - recallops-live: live-created memories only (feedback, chat notes, postmortems),
    document_id prefixed "live-...". POST /reset deletes and recreates this bank only;
    recall_merged() queries it alongside the seeded banks so live writes show up in
    recall without needing per-document deletion.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from hindsight_client import Hindsight
from hindsight_client_api.exceptions import ApiException, NotFoundException

from app.config import get_settings

logger = logging.getLogger("recallops.memory")

BANK_INCIDENTS = "incidents"
BANK_FIX_OUTCOMES = "fix-outcomes"
BANK_TEAM = "team"
BANK_BASELINE = "baseline"
BANK_LIVE = "recallops-live"
SEEDED_BANKS = (BANK_INCIDENTS, BANK_FIX_OUTCOMES, BANK_TEAM)
ALL_BANKS = (BANK_INCIDENTS, BANK_FIX_OUTCOMES, BANK_TEAM, BANK_BASELINE, BANK_LIVE)

_BANK_MISSIONS = {
    BANK_INCIDENTS: "Every ShipFast incident: symptoms, root cause, resolution, postmortem.",
    BANK_FIX_OUTCOMES: "Each fix attempt for a ShipFast incident and whether it worked, partially worked, or failed.",
    BANK_TEAM: "Who resolved what at ShipFast, their specialties, and their fix preferences.",
    BANK_BASELINE: "Intentionally empty -- used only for the no-memory demo comparison.",
    BANK_LIVE: "Live feedback, chat notes and postmortems captured during a demo session. Cleared by POST /reset.",
}

_RETRYABLE_EXCEPTIONS = (ApiException, TimeoutError, OSError)
_RECALL_REFLECT_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.5
# Step B: "total time per recall is capped at ~12s including retries, returning
# degraded=true instead of raising."
RECALL_TOTAL_TIMEOUT_SECONDS = 12.0

LIVE_DOCUMENT_PREFIX = "live-"


class MemoryUnavailableError(Exception):
    """Hindsight did not respond successfully. Used for writes (retain, ensure_banks,
    reset) where a silent/degraded fallback would hide a real data-integrity problem --
    callers should surface this as an error, not paper over it."""


@lru_cache
def get_client() -> Hindsight:
    settings = get_settings()
    return Hindsight(
        base_url=settings.hindsight_base_url,
        api_key=settings.hindsight_api_key or None,
        timeout=settings.hindsight_timeout,
    )


async def ensure_banks() -> None:
    """Create (or upsert) all five banks concurrently. Safe to call repeatedly."""
    client = get_client()
    await asyncio.gather(
        *(client.acreate_bank(bank_id=bank_id, name=bank_id, mission=_BANK_MISSIONS[bank_id]) for bank_id in ALL_BANKS)
    )


async def reset_live_bank() -> None:
    """Delete and recreate BANK_LIVE only. Per Step B: no single-document delete exists
    (HINDSIGHT_NOTES.md point 3), so wiping live-created memories means dropping the
    whole live bank and recreating it empty -- the seeded banks are untouched."""
    client = get_client()
    try:
        await client.adelete_bank(bank_id=BANK_LIVE)
    except NotFoundException:
        pass  # already gone -- fine, we're about to recreate it anyway
    await client.acreate_bank(bank_id=BANK_LIVE, name=BANK_LIVE, mission=_BANK_MISSIONS[BANK_LIVE])


def seed_tags(service: str, severity: str, incident_id: str, pattern_tags: list[str] | None = None) -> list[str]:
    """svc:<service>, sev:<n>, inc:<INC-id>, plus the pattern tag(s). Step B: never used
    as a recall filter by default -- cross-service matches matter -- but kept on every
    seeded retain so a future feature can filter by them deliberately."""
    sev_num = severity.replace("SEV", "")
    return [f"svc:{service}", f"sev:{sev_num}", f"inc:{incident_id}", *(pattern_tags or [])]


def live_document_id(kind: str, incident_id: str, suffix: str | int) -> str:
    """document_id for a live-created memory, e.g. live-feedback-INC-002-1."""
    return f"{LIVE_DOCUMENT_PREFIX}{kind}-{incident_id}-{suffix}"


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
    incident_id: str
    date: str | None
    relevance: float | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecallOutcome:
    hits: list[RecallHit]
    degraded: bool = False


def _resolve_incident_id(result: Any) -> str | None:
    """Hit mapping (Step B): incident_id from metadata, else from document_id."""
    metadata = result.metadata or {}
    incident_id = metadata.get("incident_id")
    if incident_id:
        return incident_id
    document_id = result.document_id or ""
    if document_id.startswith("incident-"):
        return document_id[len("incident-") :]
    return None


def _relevance(result: Any) -> float:
    return result.scores.final if result.scores is not None else 0.0


# --- retry helper (recall/reflect only -- see module docstring / HINDSIGHT_NOTES.md
# for why retain is not retried) -----------------------------------------------------
async def _with_retries(fn, *, max_attempts: int, op_name: str):
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            logger.warning("hindsight %s attempt %d/%d failed: %s", op_name, attempt, max_attempts, type(exc).__name__)
            if attempt < max_attempts:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise MemoryUnavailableError(f"Hindsight {op_name} failed after {max_attempts} attempts") from last_exc


# --- public wrappers -----------------------------------------------------------------
async def retain(
    bank_id: str,
    content: str,
    *,
    context: str | None = None,
    document_id: str | None = None,
    metadata: dict[str, str] | None = None,
    tags: list[str] | None = None,
    timestamp=None,
    update_mode: str | None = None,
):
    """Retain one memory. Masks secrets in `content` first.

    Not retried: a retried sync/async retain isn't guaranteed idempotent (Hindsight's
    operation_id idempotency key only applies when retain_async=True -- see
    HINDSIGHT_NOTES.md's retain section), so a failure raises MemoryUnavailableError
    once instead of risking a duplicate memory.
    """
    masked_content = mask_secrets(content)
    client = get_client()
    try:
        return await client.aretain(
            bank_id=bank_id,
            content=masked_content,
            context=context,
            document_id=document_id,
            metadata=metadata,
            tags=tags,
            timestamp=timestamp,
            update_mode=update_mode,
        )
    except _RETRYABLE_EXCEPTIONS as exc:
        logger.warning("hindsight retain(%s) failed: %s", bank_id, type(exc).__name__)
        raise MemoryUnavailableError(f"Hindsight retain({bank_id}) failed") from exc


async def recall_merged(bank_ids: list[str], query: str, *, max_tokens: int = 4096, budget: str = "mid") -> RecallOutcome:
    """Query multiple banks concurrently and merge into one incident-deduped hit list.

    Hit mapping (Step B): incident_id from metadata, else from document_id; dedupe by
    incident_id keeping the best score; skip hits that map to nothing (e.g. team-bank
    memories, which aren't incident-shaped). Capped at RECALL_TOTAL_TIMEOUT_SECONDS
    total, including retries -- on timeout or total failure this returns an empty,
    degraded=True outcome instead of raising, so a route can still answer 200.
    """
    client = get_client()

    async def _recall_one(bank_id: str):
        return await _with_retries(
            lambda: client.arecall(bank_id=bank_id, query=query, max_tokens=max_tokens, budget=budget),
            max_attempts=_RECALL_REFLECT_MAX_ATTEMPTS,
            op_name=f"recall({bank_id})",
        )

    async def _do() -> tuple[list[RecallHit], bool]:
        responses = await asyncio.gather(*(_recall_one(b) for b in bank_ids), return_exceptions=True)
        any_failed = False
        best_by_incident: dict[str, RecallHit] = {}
        for bank_id, response in zip(bank_ids, responses):
            if isinstance(response, Exception):
                any_failed = True
                logger.warning("recall_merged: bank %s failed: %s", bank_id, response)
                continue
            for result in response.results:
                incident_id = _resolve_incident_id(result)
                if incident_id is None:
                    continue
                relevance = _relevance(result)
                existing = best_by_incident.get(incident_id)
                if existing is None or (relevance or 0.0) > (existing.relevance or 0.0):
                    best_by_incident[incident_id] = RecallHit(
                        incident_id=incident_id,
                        date=result.occurred_start or result.mentioned_at,
                        relevance=relevance,
                        text=result.text,
                        metadata=result.metadata or {},
                    )
        hits = sorted(best_by_incident.values(), key=lambda h: -(h.relevance or 0.0))
        return hits, any_failed

    try:
        hits, any_failed = await asyncio.wait_for(_do(), timeout=RECALL_TOTAL_TIMEOUT_SECONDS)
        return RecallOutcome(hits=hits, degraded=any_failed)
    except Exception as exc:
        logger.warning("recall_merged(%s) degraded: %s", bank_ids, exc)
        return RecallOutcome(hits=[], degraded=True)


async def ping() -> tuple[str, float]:
    """Cheap health check: list 1 memory from the incidents bank. Returns
    ("ok"|"slow"|"down", elapsed_seconds). Used by GET /health per the contract."""
    client = get_client()
    t0 = time.time()
    try:
        await asyncio.wait_for(client.alist_memories(bank_id=BANK_INCIDENTS, limit=1), timeout=3.0)
    except Exception:
        return "down", time.time() - t0
    elapsed = time.time() - t0
    return ("ok" if elapsed < 2.0 else "slow"), elapsed


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache
def all_seed_incidents() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((_DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8")))


def get_seed_incident(incident_id: str) -> dict[str, Any] | None:
    """Look up one seed incident by ID (from backend/data/seed_incidents.json), or None
    if it's not a seed incident (e.g. a live incident, INC-023+)."""
    return {inc["incident_id"]: inc for inc in all_seed_incidents()}.get(incident_id)


def pattern_siblings(top_incident_id: str) -> list[dict[str, Any]]:
    """Given the top recalled incident, return all OTHER incidents sharing its
    error_signature, read from the structured seed data -- never from Hindsight (a
    recall/reflect call has no reliable notion of "everything with this signature";
    that's exactly the kind of exact count Hindsight is never used for -- see
    backend/app/ledger.py).

    Documented as "pattern siblings": for fix-count purposes only (e.g. scoring.py
    widening its ledger.json lookup to every incident of the same pattern, not just the
    ones recall happened to surface). Never merge these into an evidence list -- they
    were not returned by recall, so citing one would violate the CLAUDE.md rule that
    briefings may only cite incident IDs recall actually returned.

    Seed-only by design (matches this function's job: this project's seed data). A
    top incident that's live instead (not in seed data) returns []; app/incidents.py is
    where seed and live incidents of the same pattern get combined for scoring.
    """
    top = get_seed_incident(top_incident_id)
    if top is None:
        return []
    signature = top["error_signature"]
    return [
        inc
        for inc in all_seed_incidents()
        if inc["incident_id"] != top_incident_id and inc["error_signature"] == signature
    ]


async def reflect(bank_id: str, query: str, *, budget: str = "low", context: str | None = None) -> str:
    client = get_client()
    response = await _with_retries(
        lambda: client.areflect(bank_id=bank_id, query=query, budget=budget, context=context),
        max_attempts=_RECALL_REFLECT_MAX_ATTEMPTS,
        op_name=f"reflect({bank_id})",
    )
    return response.text
