"""POST /compare -- without_memory: one LLM call with ONLY the alert, no evidence
(illustrated by actually recalling against the always-empty baseline bank first, so
"no evidence" is demonstrated, not just asserted); with_memory: the same
app.analysis.analyze_alert() pipeline POST /alert uses, plus a synchronous
BriefingSections generation via routes/briefing.generate_sections() (same hallucination
guard as the SSE briefing).

No side effects, by construction: this route never calls incidents.next_incident_id(),
incidents.record_alert(), or memory.retain() -- analyze_alert() itself is pure (see
app/analysis.py), and nothing here adds state on top of it. No dedupe check either
(there's no incident being created to dedupe against).
"""
from __future__ import annotations

from fastapi import APIRouter

from app import analysis, llm, memory
from app.models import (
    BriefingSections,
    CompareRequest,
    CompareResponse,
    Evidence,
    RankedFixOut,
    WithMemory,
    WithoutMemory,
    Warning as WarningOut,
)
from app.routes.briefing import generate_sections, template_sections

router = APIRouter()


async def _without_memory_text(alert_dict: dict) -> str:
    # Demonstrate the empty baseline bank: a real recall against it, always returns
    # nothing -- this is what "no memory" actually means, not just an unfilled prompt.
    await memory.recall_merged([memory.BANK_BASELINE], alert_dict.get("title") or "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an incident response assistant with NO access to any past incident "
                "history -- this is a stateless baseline for comparison against a "
                "memory-backed agent. Given this new alert, give brief, generic "
                "troubleshooting guidance: a short checklist a team would follow with zero "
                "prior context. Plain text, not JSON, a few sentences or a short list."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Alert: {alert_dict.get('title')}. Service: {alert_dict.get('service')}, "
                f"severity: {alert_dict.get('severity')}.\n"
                f"Symptoms: {alert_dict.get('symptoms')}\nError: {alert_dict.get('error_message')}"
            ),
        },
    ]
    result = await llm.complete(messages, json_mode=False)
    if result.degraded or not result.text:
        return (
            "Generic first response (no incident history available): check recent deploys, "
            "check logs and metrics for the affected service, and restart or scale the "
            "affected component if it's safe to do so."
        )
    return result.text


@router.post("/compare", response_model=CompareResponse)
async def post_compare(payload: CompareRequest) -> CompareResponse:
    alert = payload.alert
    alert_dict = alert.model_dump()
    alert_dict["log_snippet"] = memory.mask_secrets(alert.log_snippet)

    without_text = await _without_memory_text(alert_dict)
    result = await analysis.analyze_alert(alert_dict)

    incident_like = {
        "title": alert.title,
        "service": alert.service,
        "severity": alert.severity,
        "symptoms": alert.symptoms,
        "error_message": alert.error_message,
        "memory_state": result.memory_state,
        "evidence_incident_ids": [e["incident_id"] for e in result.evidence],
        # Passed through so generate_sections can ground the briefing in ranking data:
        "ranked_fixes": [r.to_dict() for r in result.ranked_fixes],
        "warnings": result.warnings,
        "team_hint": result.team_hint,
        "recurrence": result.recurrence,
    }
    if result.evidence:
        sections, _cited = await generate_sections(incident_like)
    else:
        sections = template_sections(incident_like)

    return CompareResponse(
        without_memory=WithoutMemory(text=without_text),
        with_memory=WithMemory(
            sections=BriefingSections(**sections),
            evidence=[Evidence(**e) for e in result.evidence],
            ranked_fixes=[RankedFixOut(**r.to_dict()) for r in result.ranked_fixes],
            warnings=[WarningOut(**w) for w in result.warnings],
        ),
    )
