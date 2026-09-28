"""POST /alert -- normalise, dedupe, then app.analysis.analyze_alert() for the
recall/score/warn/hint/recurrence pipeline, then store as a live incident + retain.
See app/analysis.py for the pure (side-effect-free) analysis pipeline itself, shared
with POST /compare's with_memory path and POST /chat's evidence building.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app import analysis, incidents, memory
from app.models import (
    Alert,
    AlertResponse,
    Evidence,
    RankedFixOut,
    Recurrence,
    TeamHint,
    Warning as WarningOut,
)

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _retain_content(incident_id: str, alert: Alert, masked_log: str) -> str:
    return (
        f"Date: {alert.submitted_at} | {incident_id} | {alert.service} | {alert.severity}\n"
        f"Title: {alert.title}\n"
        f"Error signature: {alert.error_signature}\n"
        f"Symptoms: {alert.symptoms or ''}\n"
        f"Log: {masked_log}"
    )


@router.post("/alert", response_model=AlertResponse)
async def post_alert(alert: Alert) -> AlertResponse:
    # --- normalise ---------------------------------------------------------------
    if not alert.submitted_at:
        alert.submitted_at = _now_iso()
    masked_log = memory.mask_secrets(alert.log_snippet)
    alert.log_snippet = masked_log  # never retain or display the raw log

    # --- dedupe (alert's own submitted_at, never wall clock) -----------------------
    duplicate_of = incidents.find_recent_duplicate(alert.service, alert.error_signature, alert.submitted_at)
    deduplicated = duplicate_of is not None
    incident_id = duplicate_of or incidents.next_incident_id()

    # --- analyze (pure: recall, score, warn, hint, recurrence) -----------------------
    result = await analysis.analyze_alert(alert.model_dump())
    degraded, degraded_reason = result.degraded, result.degraded_reason

    # --- store as a live incident (skip on dedupe -- it merges into the existing one) ---
    if not deduplicated:
        incidents.record_alert(incident_id, alert.model_dump(), [e["incident_id"] for e in result.evidence], result.memory_state)
        try:
            retained = await memory.retain(
                memory.BANK_LIVE,
                _retain_content(incident_id, alert, masked_log),
                document_id=f"live-alert-{incident_id}",
                context="live alert",
                timestamp=datetime.fromisoformat(alert.submitted_at.replace("Z", "+00:00")),
                update_mode="replace",
                metadata={
                    "incident_id": incident_id,
                    "service": alert.service,
                    "severity": alert.severity,
                    "date": alert.submitted_at,
                    "outcome": "open",
                },
                tags=memory.seed_tags(alert.service, alert.severity, incident_id),
            )
            incidents.record_memories_stored(getattr(retained, "items_count", 1) or 1)
        except memory.MemoryUnavailableError:
            degraded = True
            degraded_reason = "memory unavailable or slow"

    return AlertResponse(
        incident_id=incident_id,
        deduplicated=deduplicated,
        status="open",
        memory_state=result.memory_state,
        alert=alert,
        evidence=[Evidence(**e) for e in result.evidence],
        ranked_fixes=[RankedFixOut(**r.to_dict()) for r in result.ranked_fixes],
        warnings=[WarningOut(**w) for w in result.warnings],
        team_hint=TeamHint(**result.team_hint) if result.team_hint else None,
        recurrence=Recurrence(**result.recurrence) if result.recurrence else None,
        briefing_stream_url=f"/incidents/{incident_id}/briefing/stream",
        degraded=degraded,
        degraded_reason=degraded_reason,
    )
