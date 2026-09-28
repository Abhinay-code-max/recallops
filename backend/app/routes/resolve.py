from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app import incidents, llm, memory
from app.models import Postmortem, ResolveRequest, ResolveResponse
from app.routes import insights

router = APIRouter()


def _template_postmortem(incident: dict, feedback: list[dict], resolver: str, resolution_notes: str | None) -> dict:
    timeline = [{"time": incident.get("submitted_at") or "", "event": f"Alert fired: {incident.get('title')}"}]
    for fb in feedback:
        timeline.append({"time": "", "event": f"Tried {fb['fix_type']} -> {fb['outcome']}"})
    worked = next((fb["fix_type"] for fb in reversed(feedback) if fb["outcome"] == "worked"), None)
    return {
        "timeline": timeline,
        "root_cause": incident.get("root_cause") or "See incident symptoms and evidence for root cause details.",
        "fix": resolution_notes or (f"{worked} resolved the incident." if worked else "Resolved -- see feedback history."),
        "action_items": ["Confirm the permanent fix ships, not just the mitigation.", "Update the runbook for this pattern."],
    }


async def _generate_postmortem(incident: dict, feedback: list[dict], resolver: str, resolution_notes: str | None) -> dict:
    feedback_text = "\n".join(f"- {fb['fix_type']}: {fb['outcome']} ({fb.get('notes') or ''})" for fb in feedback) or "(no feedback recorded)"
    messages = [
        {
            "role": "system",
            "content": (
                "Write a concise incident postmortem. Respond with strict JSON only: "
                '{"timeline": [{"time": string, "event": string}], "root_cause": string, '
                '"fix": string, "action_items": [string, ...]}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Incident {incident['incident_id']}: {incident.get('title')}\n"
                f"Service: {incident.get('service')}, severity: {incident.get('severity')}\n"
                f"Symptoms: {incident.get('symptoms')}\n"
                f"Fix attempts:\n{feedback_text}\n"
                f"Resolver: {resolver}\n"
                f"Resolution notes: {resolution_notes or '(none provided)'}"
            ),
        },
    ]
    result = await llm.complete(messages, json_mode=True)
    if not result.degraded and result.parsed:
        try:
            return Postmortem(**result.parsed).model_dump()
        except Exception:
            pass
    return _template_postmortem(incident, feedback, resolver, resolution_notes)


@router.post("/resolve", response_model=ResolveResponse)
async def post_resolve(payload: ResolveRequest) -> ResolveResponse:
    incident = incidents.get_incident(payload.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})

    feedback = incidents.feedback_for(payload.incident_id)
    postmortem = await _generate_postmortem(incident, feedback, payload.resolver, payload.resolution_notes)

    incidents.record_resolution(payload.incident_id, payload.resolver, payload.minutes_to_resolve, postmortem)
    insights.clear_cache()

    memories_stored = 0
    try:
        content = (
            f"Postmortem for {payload.incident_id}: {postmortem['root_cause']} Fix: {postmortem['fix']} "
            f"Resolver: {payload.resolver}."
        )
        result = await memory.retain(
            memory.BANK_LIVE,
            content,
            document_id=f"live-postmortem-{payload.incident_id}",
            context=f"postmortem for {payload.incident_id}",
            timestamp=datetime.now(timezone.utc),
            update_mode="replace",
            metadata={
                "incident_id": payload.incident_id,
                "service": incident.get("service") or "",
                "severity": incident.get("severity") or "",
                "date": datetime.now(timezone.utc).isoformat(),
                "outcome": "worked",
            },
            tags=memory.seed_tags(incident.get("service") or "", incident.get("severity") or "SEV3", payload.incident_id),
        )
        memories_stored = getattr(result, "items_count", 1) or 1
        incidents.record_memories_stored(memories_stored)
    except memory.MemoryUnavailableError:
        pass

    return ResolveResponse(postmortem=Postmortem(**postmortem), memories_stored=memories_stored)
