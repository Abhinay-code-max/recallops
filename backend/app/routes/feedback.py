from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app import incidents, ledger, memory, scoring, security
from app.models import FeedbackRequest, FeedbackResponse, RankedFixOut, Warning as WarningOut
from app.routes import insights

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def post_feedback(feedback: FeedbackRequest) -> FeedbackResponse:
    incident = incidents.get_incident(feedback.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})

    security.check_feedback_allowed(feedback.incident_id, feedback.fix_type)
    incidents.record_feedback(feedback.incident_id, feedback.fix_type, feedback.outcome, feedback.notes)
    insights.clear_cache()

    memories_stored = 0
    try:
        content = (
            f"{feedback.incident_id} ({incident.get('service')}): fix '{feedback.fix_type}' "
            f"outcome={feedback.outcome}. {feedback.notes or ''}"
        )
        result = await memory.retain(
            memory.BANK_LIVE,
            content,
            document_id=f"live-fb-{uuid.uuid4()}",
            context=f"feedback for {feedback.incident_id}",
            timestamp=datetime.now(timezone.utc),
            update_mode="replace",
            metadata={
                "incident_id": feedback.incident_id,
                "service": incident.get("service") or "",
                "severity": incident.get("severity") or "",
                "date": datetime.now(timezone.utc).isoformat(),
                "outcome": feedback.outcome,
                "fix_type": feedback.fix_type,
            },
            tags=memory.seed_tags(incident.get("service") or "", incident.get("severity") or "SEV3", feedback.incident_id),
        )
        memories_stored = getattr(result, "items_count", 1) or 1
        incidents.record_memories_stored(memories_stored)
    except memory.MemoryUnavailableError:
        pass

    ranked_fixes: list[scoring.RankedFix] = []
    warnings: list[WarningOut] = []
    top_incident_id = feedback.incident_id
    pool = incidents.pattern_pool(top_incident_id)
    if pool:
        query = incidents.alert_query(incident)
        outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query)
        ledger_data = ledger.read_ledger()
        if outcome.hits and ledger_data is not None:
            counts = incidents.ledger_counts_for(top_incident_id, ledger_data)
            ranked_fixes = scoring.rank_fixes(outcome.hits, pool, counts)
            recurrence_data = incidents.compute_recurrence(pool)
            warnings = [WarningOut(**w) for w in incidents.build_warnings(ranked_fixes, pool, recurrence_data)]

    return FeedbackResponse(
        ranked_fixes=[RankedFixOut(**r.to_dict()) for r in ranked_fixes],
        warnings=warnings,
        memories_stored=memories_stored,
    )
