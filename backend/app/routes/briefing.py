"""GET /incidents/{incident_id}/briefing/stream (SSE).

Generates BriefingSections as validated JSON via llm.py, grounded in:
  - recalled evidence (symptoms, root_cause, resolver per incident)
  - ranked_fixes (with scores), warnings, team_hint, recurrence
    stored on the incident record at alert time by routes/alert.py.

Hallucination guard (CLAUDE.md: "briefings may cite only incident IDs returned by
recall"): every INC-xxx substring found anywhere in the generated sections must be one
of the incident's own evidence_incident_ids -- otherwise regenerate once, then fall back
to a template briefing built from structured data (memory.py/incidents.py), never the
LLM.

Grounding guard (Prompt 4c): post-validate that:
  - first_actions[0] mentions the top-ranked fix type (regenerate once then template if
    not -- the template always obeys this rule).
  - NO first_action recommends a fix_type that has only failed in the ledger (detected by
    matching common verb forms: "rollback"/"roll back" etc against the fix_type labels and
    words). Regenerate once then template if violated.

When memory_state is "matched", cited_incident_ids must be non-empty after validation;
otherwise regenerate once, then template (template citations come from the top recalled
evidence ids, not LLM text).

BriefingSections gains a `sources` field: {root_cause:[ids], first_actions:[ids],
last_fixed_by:id|null} -- populated by extracting all INC-xxx references from each
sub-field of the validated sections.

SSE token events are sent in chunks of ~_TOKEN_CHUNK_SIZE chars with ~20 ms between
them so the UI can render a real streaming experience.

Cached per incident_id so a second request for the same incident doesn't call the LLM.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import incidents, llm
from app.analysis import extract_incident_ids
from app.models import BriefingSections, BriefingSources

router = APIRouter()

_TOKEN_CHUNK_SIZE = 20  # characters per SSE token event
_TOKEN_DELAY_S = 0.020  # 20 ms between token events

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
    return extract_incident_ids(text)


def _sources_from_sections(sections: dict[str, Any]) -> dict[str, Any]:
    """Populate sources by extracting INC-xxx refs from each BriefingSections sub-field."""
    root_cause_ids = sorted(extract_incident_ids(str(sections.get("root_cause", ""))))
    first_actions_ids = sorted(extract_incident_ids(" ".join(sections.get("first_actions", []) or [])))
    last_fixed_by_id_set = extract_incident_ids(str(sections.get("last_fixed_by") or ""))
    last_fixed_by_id = next(iter(last_fixed_by_id_set), None)
    return {"root_cause": root_cause_ids, "first_actions": first_actions_ids, "last_fixed_by": last_fixed_by_id}


def _fix_words(fix_type: str) -> set[str]:
    """Lower-case word set for a fix_type label used for grounding validation."""
    return set(re.split(r"[_\s]+", fix_type.lower()))


def _action_mentions_failed_fix(action: str, failed_fix_types: list[str]) -> bool:
    """True if a first_action text appears to recommend a fix that has only failed."""
    action_lower = action.lower()
    for ftype in failed_fix_types:
        words = _fix_words(ftype)
        # Special-case common synonyms
        if "rollback" in words or "rollback_to_previous_deploy" == ftype:
            if "rollback" in action_lower or "roll back" in action_lower:
                return True
        if "restart" in words:
            if "restart" in action_lower:
                return True
        # Generic: if >50% of the fix_type words appear in the action
        if len(words) >= 2 and sum(1 for w in words if w in action_lower) >= len(words) // 2:
            return True
    return False


def _validate_grounding(
    sections: dict[str, Any],
    top_fix_type: str | None,
    failed_only_fix_types: list[str],
    allowed_ids: set[str],
    memory_state: str,
) -> str | None:
    """Return a string describing the first grounding violation, or None if clean."""
    cited = _cited_incident_ids(sections)
    if cited - allowed_ids:
        return f"hallucinated citation(s): {cited - allowed_ids}"

    if memory_state == "matched" and not cited:
        return "memory_state is matched but no evidence ids were cited"

    if top_fix_type:
        first_action = (sections.get("first_actions") or [""])[0].lower()
        top_words = _fix_words(top_fix_type)
        if not any(w in first_action for w in top_words):
            return f"first_actions[0] does not mention top ranked fix '{top_fix_type}'"

    for action in sections.get("first_actions", []):
        if _action_mentions_failed_fix(action, failed_only_fix_types):
            return f"first_action recommends a failed-only fix: '{action}'"

    return None  # clean


def _build_prompt(
    incident: dict[str, Any],
    evidence: list[dict[str, Any]],
    ranked_fixes: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    team_hint: dict[str, Any] | None,
    recurrence: dict[str, Any] | None,
    top_fix_type: str | None,
    failed_only_fix_types: list[str],
) -> list[dict[str, str]]:
    evidence_text = "\n\n".join(
        f"Incident {e['incident_id']} ({e.get('service')}, {e.get('severity')}, {e.get('date')}):\n"
        f"Symptoms: {e.get('symptoms')}\n"
        f"Root cause: {e.get('root_cause')}\n"
        f"Resolver: {e.get('resolver')}"
        for e in evidence
    )

    # Ranked fix context
    ranked_text = ""
    if ranked_fixes:
        ranked_lines = [
            f"  {f['rank']}. {f['fix_type']} (score={f['score']:+.3f}, worked={f['worked']}, "
            f"partial={f['partial']}, failed={f['failed']}, recent_failures={f['recent_failures']})"
            for f in ranked_fixes[:5]
        ]
        ranked_text = "Ranked fixes (use the top one as first_actions[0]):\n" + "\n".join(ranked_lines)

    failed_text = ""
    if failed_only_fix_types:
        failed_text = (
            f"\nFAILED-ONLY fixes (do NOT recommend these in any first_action, not even as a last resort): "
            f"{', '.join(failed_only_fix_types)}"
        )

    recurrence_text = f"\nRecurrence: {recurrence['message']}" if recurrence else ""
    team_text = f"\nTeam expert: {team_hint['person']} ({team_hint['reason']})" if team_hint else ""

    system = (
        "You are an incident response assistant writing a short triage briefing. Use ONLY "
        "the evidence incidents listed below. You may reference an incident ID (like "
        "INC-002) ONLY if it appears in that evidence list -- never invent or cite any "
        "other incident ID, and never make one up.\n"
        f"RULES:\n"
        f"  1. first_actions[0] MUST recommend the top-ranked fix: '{top_fix_type}'.\n"
        f"  2. No first_action may recommend any fix that has ONLY failed before.\n"
        f"  3. Cite at least one evidence incident ID somewhere in root_cause or first_actions.\n"
        'Respond with strict JSON only: '
        '{"root_cause": string, "blast_radius": string, '
        '"first_actions": [string, string, string], "last_fixed_by": string or null}'
    )
    user = (
        f"New alert: {incident['title']}. Service: {incident.get('service')}, "
        f"severity: {incident.get('severity')}.\n"
        f"Symptoms: {incident.get('symptoms')}\n"
        f"Error: {incident.get('error_message')}\n\n"
        f"Evidence (only these incidents may be cited):\n{evidence_text or '(none)'}\n\n"
        f"{ranked_text}{failed_text}{recurrence_text}{team_text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def template_sections(
    incident: dict[str, Any],
    ranked_fixes: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    team_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
            "sources": {"root_cause": [], "first_actions": [], "last_fixed_by": None},
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
            "sources": {"root_cause": [], "first_actions": [], "last_fixed_by": None},
        }

    top_id = evidence_ids[0]
    top = incidents.get_incident(top_id)
    pool = incidents.pattern_pool(top_id)
    computed_team_hint = team_hint or incidents.compute_team_hint(pool)

    # Build first_actions grounded in ranked_fixes (top fix first, skip failed-only)
    rfs = ranked_fixes or []
    failed_only = {f["fix_type"] for f in rfs if f.get("worked", 0) == 0 and f.get("partial", 0) == 0 and f.get("failed", 0) > 0}
    candidate_fixes = [f for f in rfs if f["fix_type"] not in failed_only]

    first_action_0 = f"Apply the top-ranked fix: {candidate_fixes[0]['label'] if candidate_fixes else 'see ranked fixes panel'} (from {top_id})."
    first_actions = [
        first_action_0,
        f"Review {top_id} and the ranked fixes panel for what worked before.",
        "Monitor service metrics and escalate to the team expert if the fix doesn't hold.",
    ]

    return {
        "root_cause": (top or {}).get("root_cause") or f"Matches the pattern seen in {top_id}; see the evidence panel for details.",
        "blast_radius": f"{service} affected, matching the pattern from {top_id}.",
        "first_actions": first_actions,
        "last_fixed_by": (computed_team_hint or {}).get("person"),
        "sources": {"root_cause": [top_id], "first_actions": [top_id], "last_fixed_by": None},
    }


async def generate_sections(incident: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Guarded BriefingSections generation: LLM grounded only in incident's
    evidence_incident_ids + ranked_fixes/warnings/team_hint/recurrence stored at alert
    time. Hallucination guard + grounding guard (regenerate once then template fallback).
    Public: also used by POST /compare's with_memory path (routes/compare.py), which
    needs the exact same guarantee without the SSE/caching wrapper below."""
    evidence_ids: list[str] = incident.get("evidence_incident_ids") or []
    allowed = set(evidence_ids)
    memory_state = incident.get("memory_state", "no_match")

    # Pull ranking data stored on the incident at alert time
    ranked_fixes: list[dict[str, Any]] = incident.get("ranked_fixes") or []
    warnings_list: list[dict[str, Any]] = incident.get("warnings") or []
    team_hint: dict[str, Any] | None = incident.get("team_hint")
    recurrence: dict[str, Any] | None = incident.get("recurrence")

    # Determine top fix and failed-only fixes for grounding validation
    top_fix_type: str | None = ranked_fixes[0]["fix_type"] if ranked_fixes else None
    failed_only_fix_types: list[str] = [
        f["fix_type"]
        for f in ranked_fixes
        if f.get("worked", 0) == 0 and f.get("partial", 0) == 0 and f.get("failed", 0) > 0
    ]

    if evidence_ids:
        evidence = [e for e in (incidents.get_incident(eid) for eid in evidence_ids) if e is not None]
        messages = _build_prompt(
            incident, evidence, ranked_fixes, warnings_list, team_hint, recurrence,
            top_fix_type, failed_only_fix_types,
        )

        for _attempt in range(2):
            result = await llm.complete(messages, json_mode=True)
            if result.degraded or not result.parsed:
                continue
            try:
                # Parse only the core fields from LLM; sources is computed, not from LLM
                raw = result.parsed
                sections_core = {
                    "root_cause": raw.get("root_cause", ""),
                    "blast_radius": raw.get("blast_radius", ""),
                    "first_actions": raw.get("first_actions", []),
                    "last_fixed_by": raw.get("last_fixed_by"),
                    "sources": {"root_cause": [], "first_actions": [], "last_fixed_by": None},
                }
                sections = BriefingSections(**sections_core).model_dump()
            except Exception:
                continue

            violation = _validate_grounding(sections, top_fix_type, failed_only_fix_types, allowed, memory_state)
            if violation is None:
                # Populate sources from validated sections
                sections["sources"] = _sources_from_sections(sections)
                cited = sorted(_cited_incident_ids(sections))
                return sections, cited

    # Template fallback: always cites the top evidence id
    tmpl = template_sections(incident, ranked_fixes=ranked_fixes, team_hint=team_hint)
    # Template citations come from evidence_ids (not LLM text)
    template_cited = sorted(evidence_ids[:2]) if evidence_ids else []
    return tmpl, template_cited


async def _stream_events(incident_id: str) -> AsyncIterator[bytes]:
    cached = _briefing_cache.get(incident_id)
    if cached is None:
        incident = incidents.get_incident(incident_id)
        sections, cited_incident_ids = await generate_sections(incident)
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
        await asyncio.sleep(_TOKEN_DELAY_S)

    yield _sse("sections", sections)
    yield _sse("done", {"cited_incident_ids": cached["cited_incident_ids"]})


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


@router.get("/incidents/{incident_id}/briefing/stream")
async def get_briefing_stream(incident_id: str) -> StreamingResponse:
    if incidents.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "incident not found"}})
    return StreamingResponse(_stream_events(incident_id), media_type="text/event-stream")
