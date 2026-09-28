from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import incidents
from app.models import IncidentDetail, IncidentSummary

router = APIRouter()


@router.get("/incidents", response_model=list[IncidentSummary])
async def get_incidents() -> list[IncidentSummary]:
    return [IncidentSummary(**row) for row in incidents.list_incidents()]


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str) -> IncidentDetail:
    incident = incidents.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})

    outcome = incident.get("outcome") or "open"
    return IncidentDetail(
        incident_id=incident["incident_id"],
        title=incident["title"],
        service=incident["service"],
        severity=incident["severity"],
        date=incident.get("date"),
        resolver=incident.get("resolver"),
        minutes_to_resolve=incident.get("minutes_to_resolve"),
        outcome=outcome,
        log_snippet=incident.get("log_snippet"),
        symptoms=incident.get("symptoms"),
        root_cause=incident.get("root_cause"),
        fix_attempts=incident.get("fix_attempts") or [],
        postmortem=incident.get("postmortem"),
    )
