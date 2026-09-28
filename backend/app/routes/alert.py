"""POST /alert -- normalise, dedupe, recall, score, warn, hint, store.

memory_state threshold -- calibrated live, not guessed (same run as scoring.py's
similarity calibration, see that module's docstring for the full table): the 5 demo
alerts' best relevance ranged 0.42-1.07; 3 unrelated nonsense alerts ranged
0.0001-0.0013. NO_MATCH_THRESHOLD=0.05 sits with a large margin on both sides (~38x
above the nonsense ceiling, ~8x below the weakest real match).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app import incidents, ledger, memory, scoring
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

NO_MATCH_THRESHOLD = 0.05
EVIDENCE_LIMIT = 6
RECALL_TOP_N = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative(from_iso: str | None, to_iso: str | None) -> str:
    if not from_iso or not to_iso:
        return ""
    try:
        a = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
        b = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    days = abs((a - b).days)
    if days == 0:
        return "today"
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 8:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


def _excerpt(incident: dict, limit: int = 160) -> str:
    text = incident.get("symptoms") or incident.get("title") or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _build_evidence(hits: list[memory.RecallHit], submitted_at: str | None) -> list[Evidence]:
    evidence: list[Evidence] = []
    for hit in hits[:EVIDENCE_LIMIT]:
        incident = incidents.get_incident(hit.incident_id)
        if incident is None:
            continue
        source_bank = memory.BANK_INCIDENTS if memory.get_seed_incident(hit.incident_id) else memory.BANK_LIVE
        evidence.append(
            Evidence(
                incident_id=hit.incident_id,
                date=incident.get("date"),
                relative=_relative(submitted_at, incident.get("date")),
                service=incident.get("service"),
                severity=incident.get("severity"),
                excerpt=_excerpt(incident),
                relevance=round(min(max(hit.relevance or 0.0, 0.0), 1.0), 4),
                source_bank=source_bank,
            )
        )
    return evidence


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
    degraded = False
    degraded_reason: str | None = None

    # --- normalise ---------------------------------------------------------------
    if not alert.submitted_at:
        alert.submitted_at = _now_iso()
    masked_log = memory.mask_secrets(alert.log_snippet)
    alert.log_snippet = masked_log  # never retain or display the raw log

    # --- dedupe (alert's own submitted_at, never wall clock) -----------------------
    duplicate_of = incidents.find_recent_duplicate(alert.service, alert.error_signature, alert.submitted_at)
    deduplicated = duplicate_of is not None
    incident_id = duplicate_of or incidents.next_incident_id()

    # --- recall ---------------------------------------------------------------------
    ledger_data = ledger.read_ledger()
    query = incidents.alert_query(alert.model_dump())
    outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query, max_tokens=4096)
    hits = outcome.hits[:RECALL_TOP_N]
    if outcome.degraded:
        degraded = True
        degraded_reason = "memory unavailable or slow"

    best_relevance = max((h.relevance or 0.0 for h in hits), default=0.0)
    if ledger_data is None or ledger_data["totals"]["incidents"] == 0:
        memory_state = "empty"
    elif best_relevance < NO_MATCH_THRESHOLD:
        memory_state = "no_match"
    else:
        memory_state = "matched"

    evidence = _build_evidence(hits, alert.submitted_at) if memory_state == "matched" else []

    # --- score, warn, hint, recurrence (only meaningful with a real match) ----------
    ranked_fixes: list[scoring.RankedFix] = []
    warnings: list[WarningOut] = []
    team_hint: TeamHint | None = None
    recurrence: Recurrence | None = None

    if memory_state == "matched" and hits:
        top_incident_id = incidents.first_resolvable([h.incident_id for h in hits])
        if top_incident_id is not None:
            pool = incidents.pattern_pool(top_incident_id)
            if ledger_data is not None:
                counts = incidents.ledger_counts_for(top_incident_id, ledger_data)
                ranked_fixes = scoring.rank_fixes(hits, pool, counts)
            recurrence_data = incidents.compute_recurrence(pool)
            if recurrence_data is not None:
                recurrence = Recurrence(**recurrence_data)
            team_hint_data = incidents.compute_team_hint(pool)
            if team_hint_data is not None:
                team_hint = TeamHint(**team_hint_data)
            warnings = [WarningOut(**w) for w in incidents.build_warnings(ranked_fixes, pool, recurrence_data)]

    # --- store as a live incident (skip on dedupe -- it merges into the existing one) ---
    if not deduplicated:
        incidents.record_alert(incident_id, alert.model_dump(), [e.incident_id for e in evidence], memory_state)
        try:
            await memory.retain(
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
        except memory.MemoryUnavailableError:
            degraded = True
            degraded_reason = "memory unavailable or slow"

    return AlertResponse(
        incident_id=incident_id,
        deduplicated=deduplicated,
        status="open",
        memory_state=memory_state,
        alert=alert,
        evidence=evidence,
        ranked_fixes=[RankedFixOut(**r.to_dict()) for r in ranked_fixes],
        warnings=warnings,
        team_hint=team_hint,
        recurrence=recurrence,
        briefing_stream_url=f"/incidents/{incident_id}/briefing/stream",
        degraded=degraded,
        degraded_reason=degraded_reason,
    )
