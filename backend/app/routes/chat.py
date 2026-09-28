"""POST /chat -- recall_merged on the question (plus the incident's own context when
incident_id is given), answer via llm.py using ONLY recalled evidence + ledger facts.
Same citation guard as GET /incidents/{id}/briefing/stream: every INC-xxx cited in the
answer must be one of the recalled evidence ids, else regenerate once, then a template
answer built from the evidence -- never the LLM's un-guarded text.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import analysis, incidents, ledger, llm, memory
from app.models import ChatRequest, ChatResponse, Evidence

router = APIRouter()


def _ledger_facts_text(top_incident_id: str | None) -> str:
    if top_incident_id is None:
        return "(no fix-outcome data available)"
    ledger_data = ledger.read_ledger()
    if ledger_data is None:
        return "(no fix-outcome data available)"
    counts = incidents.ledger_counts_for(top_incident_id, ledger_data)
    if not counts:
        return "(no fix-outcome data available)"
    lines = [
        f"{fix_type}: worked {c['worked']}, partial {c['partial']}, failed {c['failed']}"
        for fix_type, c in counts.items()
    ]
    return "\n".join(lines)


def _build_prompt(question: str, evidence: list[dict], ledger_facts: str) -> list[dict[str, str]]:
    evidence_lines: list[str] = []
    for e in evidence:
        inc = incidents.get_incident(e["incident_id"]) or {}
        fixes_summary = ", ".join(
            f"{f.get('fix_type')} ({f.get('outcome')}, resolver: {f.get('resolver', 'unknown')})"
            for f in inc.get("fix_attempts", [])
        )
        resolver_str = inc.get("resolver") or "unknown"
        parts = [
            f"Incident {e['incident_id']} ({e.get('service')}, {e.get('severity')}, {e.get('date')}):",
            f"  Title: {inc.get('title', '')}",
            f"  Symptoms: {e.get('excerpt')}",
            f"  Resolver: {resolver_str}",
        ]
        if fixes_summary:
            parts.append(f"  Fixes tried: {fixes_summary}")
        if inc.get("root_cause"):
            parts.append(f"  Root cause: {inc.get('root_cause')}")
        evidence_lines.append("\n".join(parts))

    evidence_text = "\n\n".join(evidence_lines)
    system = (
        "You are an incident response assistant answering a question. Use ONLY the "
        "evidence incidents and fix-outcome facts below. You may cite an incident ID "
        "(like INC-002) ONLY if it appears in the evidence list -- never invent one. "
        "If the question is unrelated to incidents/systems (e.g. weather, general chit-chat) "
        "or if the evidence contains no relevant history to answer it, you must say that "
        "you have no relevant incident history to answer that, and cite nothing. "
        'Respond with strict JSON only: {"answer": string}'
    )
    user = (
        f"Question: {question}\n\n"
        f"Evidence (only these incidents may be cited):\n{evidence_text or '(none)'}\n\n"
        f"Fix-outcome facts for the most relevant pattern:\n{ledger_facts}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _template_answer(evidence: list[dict]) -> str:
    if not evidence:
        return "I don't have any relevant incident history to answer that."
    ids = ", ".join(e["incident_id"] for e in evidence[:3])
    return f"Based on {len(evidence)} recalled incident(s) ({ids}), see the evidence panel for the details behind this."


@router.post("/chat", response_model=ChatResponse)
async def post_chat(payload: ChatRequest) -> ChatResponse:
    incident_context = ""
    if payload.incident_id is not None:
        incident = incidents.get_incident(payload.incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})
        incident_context = f" {incident.get('title', '')}. {incident.get('symptoms', '')}"

    query = f"{payload.question}{incident_context}"
    outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query)
    # Same no_match floor as analysis.analyze_alert() -- otherwise an unrelated question
    # still surfaces whatever the lowest-relevance hits in the bank happen to be.
    hits = [h for h in outcome.hits if (h.relevance or 0.0) >= analysis.NO_MATCH_THRESHOLD][: analysis.RECALL_TOP_N]
    evidence = analysis.build_evidence(hits, None)
    allowed = {e["incident_id"] for e in evidence}

    top_incident_id = incidents.first_resolvable([h.incident_id for h in hits]) if hits else None
    ledger_facts = _ledger_facts_text(top_incident_id)

    answer: str | None = None
    if evidence:
        messages = _build_prompt(payload.question, evidence, ledger_facts)
        for _attempt in range(2):
            result = await llm.complete(messages, json_mode=True)
            if result.degraded or not result.parsed:
                continue
            candidate = result.parsed.get("answer") if isinstance(result.parsed, dict) else None
            if not candidate:
                continue
            cited = analysis.extract_incident_ids(candidate)
            if cited <= allowed:
                answer = candidate
                break

    if answer is None:
        answer = _template_answer(evidence)

    return ChatResponse(answer=answer, evidence=[Evidence(**e) for e in evidence])
