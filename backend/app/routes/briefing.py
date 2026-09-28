"""GET /incidents/{incident_id}/briefing/stream (SSE).

Generates BriefingSections as validated JSON via llm.py, using ONLY the incident's
recalled evidence as context. Hallucination guard (CLAUDE.md: "briefings may cite only
incident IDs returned by recall"): every INC-xxx substring found anywhere in the
generated sections must be one of the incident's own evidence_incident_ids (set at
alert time by routes/alert.py, capped to what was actually shown as evidence) --
otherwise regenerate once, then fall back to a template briefing built from structured
data (memory.py/incidents.py), never the LLM. Streams only validated text: small token
chunks of the already-guarded/template text, then a `sections` event, then `done` with
cited_incident_ids. Cached per incident_id so a second request for the same incident
doesn't call the LLM again.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import incidents, llm
from app.models import BriefingSections

router = APIRouter()

_INCIDENT_ID_RE = re.compile(r"\bINC-\d{3,}\b")
_TOKEN_CHUNK_SIZE = 40

_briefing_cache: dict[str, dict[str, Any]] = {}


def clear_cache() -> None:
    _briefing_cache.clear()


def _cited_incident_ids(sections: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(sections.get("root_cause", "")),
            str(sections.get("blast_radius", "")),
            str(sections.get("last_fixed_by") or ""),
            " ".join(sections.get("first_actions", []) or []),
        ]
    )
    return set(_INCIDENT_ID_RE.findall(text))


def _build_prompt(incident: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence_text = "\n\n".join(
        f"Incident {e['incident_id']} ({e.get('service')}, {e.get('severity')}, {e.get('date')}):\n"
        f"Symptoms: {e.get('symptoms')}\n"
        f"Root cause: {e.get('root_cause')}\n"
        f"Resolver: {e.get('resolver')}"
        for e in evidence
    )
    system = (
        "You are an incident response assistant writing a short triage briefing. Use ONLY "
        "the evidence incidents listed below. You may reference an incident ID (like "
        "INC-002) ONLY if it appears in that evidence list -- never invent or cite any "
        "other incident ID, and never make one up. Respond with strict JSON only: "
        '{"root_cause": string, "blast_radius": string, '
        '"first_actions": [string, string, string], "last_fixed_by": string or null}'
    )
    user = (
        f"New alert: {incident['title']}. Service: {incident.get('service')}, "
        f"severity: {incident.get('severity')}.\n"
        f"Symptoms: {incident.get('symptoms')}\n"
        f"Error: {incident.get('error_message')}\n\n"
        f"Evidence (only these incidents may be cited):\n{evidence_text or '(none)'}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _template_sections(incident: dict[str, Any]) -> dict[str, Any]:
    memory_state = incident.get("memory_state", "no_match")
    service = incident.get("service") or "the service"

    if memory_state == "empty":
        return {
            "root_cause": "No incident history is available yet -- this looks like the first incident of its kind on record, so there's nothing to compare it against.",
            "blast_radius": f"{service} is affected; scope not yet confirmed.",
            "first_actions": [
                "Check recent deploys and rollbacks for this service.",
                "Check logs and metrics for the affected service.",
                "Restart or scale the affected component if it's safe to do so.",
            ],
            "last_fixed_by": None,
        }

    evidence_ids = incident.get("evidence_incident_ids") or []
    if not evidence_ids:
        return {
            "root_cause": "No similar past incident was found -- this doesn't match a known pattern, so there's no history-based root cause to report.",
            "blast_radius": f"{service} is affected; scope not yet confirmed.",
            "first_actions": [
                "Check recent deploys and rollbacks for this service.",
                "Check logs and metrics for the affected service.",
                "Escalate to the service owner if the cause isn't clear within a few minutes.",
            ],
            "last_fixed_by": None,
        }

    top_id = evidence_ids[0]
    top = incidents.get_incident(top_id)
    pool = incidents.pattern_pool(top_id)
    team_hint = incidents.compute_team_hint(pool)
    return {
        "root_cause": (top or {}).get("root_cause") or f"Matches the pattern seen in {top_id}; see the evidence panel for details.",
        "blast_radius": f"{service} affected, matching the pattern from {top_id}.",
        "first_actions": [
            f"Review {top_id} and the ranked fixes panel for what worked before.",
            "Check recent deploys and rollbacks for this service.",
            "Check logs and metrics for the affected service.",
        ],
        "last_fixed_by": (team_hint or {}).get("person"),
    }


async def _generate_sections(incident: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    evidence_ids: list[str] = incident.get("evidence_incident_ids") or []
    allowed = set(evidence_ids)

    if evidence_ids:
        evidence = [e for e in (incidents.get_incident(eid) for eid in evidence_ids) if e is not None]
        messages = _build_prompt(incident, evidence)

        for _attempt in range(2):
            result = await llm.complete(messages, json_mode=True)
            if result.degraded or not result.parsed:
                continue
            try:
                sections = BriefingSections(**result.parsed).model_dump()
            except Exception:
                continue
            cited = _cited_incident_ids(sections)
            if cited <= allowed:
                return sections, sorted(cited)

    return _template_sections(incident), []


async def _stream_events(incident_id: str) -> AsyncIterator[bytes]:
    cached = _briefing_cache.get(incident_id)
    if cached is None:
        incident = incidents.get_incident(incident_id)
        sections, cited_incident_ids = await _generate_sections(incident)
        cached = {"sections": sections, "cited_incident_ids": cited_incident_ids}
        _briefing_cache[incident_id] = cached

    sections = cached["sections"]
    text = (
        f"Root cause: {sections['root_cause']}\n\n"
        f"Blast radius: {sections['blast_radius']}\n\n"
        "First actions:\n" + "\n".join(f"- {a}" for a in sections["first_actions"])
    )
    if sections.get("last_fixed_by"):
        text += f"\n\nLast fixed by: {sections['last_fixed_by']}"

    for i in range(0, len(text), _TOKEN_CHUNK_SIZE):
        yield _sse("token", {"text": text[i : i + _TOKEN_CHUNK_SIZE]})
        await asyncio.sleep(0)

    yield _sse("sections", sections)
    yield _sse("done", {"cited_incident_ids": cached["cited_incident_ids"]})


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


@router.get("/incidents/{incident_id}/briefing/stream")
async def get_briefing_stream(incident_id: str) -> StreamingResponse:
    if incidents.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})
    return StreamingResponse(_stream_events(incident_id), media_type="text/event-stream")
