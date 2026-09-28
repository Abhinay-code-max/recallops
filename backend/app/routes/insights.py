"""GET /insights -- every number comes from deterministic, structured-data facts
(app/incidents.py's compute_patterns/compute_open_permanent_fixes/compute_team_knowledge/
compute_fix_speed_comparison, plus historical_recurrence per recurring pattern), never
from Hindsight or the LLM. reflect() is called exactly once on the incidents bank, given
the already-computed facts as context, and its text is attached as reflect_summary
(narrative only) -- callers must never parse a number back out of it.

Cached (single result, no params to key on); invalidated by POST /feedback, POST
/resolve, and POST /reset (each of those changes the structured data this depends on).
"""
from __future__ import annotations

import json

from fastapi import APIRouter

from app import incidents, memory
from app.models import (
    FixSpeedComparison,
    InsightPattern,
    InsightsResponse,
    OpenPermanentFix,
    RecurringInsight,
    Recurrence,
    TeamKnowledge,
)

router = APIRouter()

_cache: InsightsResponse | None = None


def clear_cache() -> None:
    global _cache
    _cache = None


def _reflect_context(patterns: list[dict], recurring: list[dict], open_fixes: list[dict], team: list[dict], fix_speed: dict) -> str:
    return json.dumps(
        {
            "patterns": patterns,
            "recurring": recurring,
            "open_permanent_fixes": open_fixes,
            "team_knowledge": team,
            "fix_speed_comparison": fix_speed,
        },
        default=str,
    )


@router.get("/insights", response_model=InsightsResponse)
async def get_insights() -> InsightsResponse:
    global _cache
    if _cache is not None:
        return _cache

    patterns = incidents.compute_patterns()

    recurring: list[dict] = []
    by_signature: dict[str, list[dict]] = {}
    for inc in incidents.all_incidents_normalized():
        by_signature.setdefault(inc["error_signature"], []).append(inc)
    for signature, incs in sorted(by_signature.items()):
        if len(incs) < 2:
            continue
        recurrence = incidents.historical_recurrence(incs)
        if recurrence is None:
            continue
        recurring.append({"service": incs[0]["service"], "title": signature.replace("_", " ").capitalize(), "recurrence": recurrence})

    open_fixes = incidents.compute_open_permanent_fixes()
    team = incidents.compute_team_knowledge()
    fix_speed = incidents.compute_fix_speed_comparison()

    context = _reflect_context(patterns, recurring, open_fixes, team, fix_speed)
    try:
        reflect_summary = await memory.reflect(
            memory.BANK_INCIDENTS,
            query="Given these computed patterns, recurring incidents, open permanent fixes, team knowledge and fix-speed comparison, what should the team know?",
            context=context,
        )
    except memory.MemoryUnavailableError:
        reflect_summary = "Memory reflection is unavailable right now; the figures above are still exact, computed from structured incident data."

    response = InsightsResponse(
        patterns=[InsightPattern(**p) for p in patterns],
        recurring=[RecurringInsight(service=r["service"], title=r["title"], recurrence=Recurrence(**r["recurrence"])) for r in recurring],
        open_permanent_fixes=[OpenPermanentFix(**f) for f in open_fixes],
        team_knowledge=[TeamKnowledge(**t) for t in team],
        fix_speed_comparison=FixSpeedComparison(**fix_speed),
        reflect_summary=reflect_summary,
    )
    _cache = response
    return response
