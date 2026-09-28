"""GET /insights -- deterministic facts (app/incidents.py's compute_*, never Hindsight)
are computed fresh on every request: cheap, local, so this always responds in well
under a second. reflect_summary (str|None) and reflect_status
("pending"|"ready"|"failed") come from a background task instead, so a slow reflect()
call (up to ~45s -- see memory.REFLECT_TOTAL_TIMEOUT_SECONDS) never blocks the route.

reflect is (re)started: at app startup (main.py's lifespan, regardless of whether the
bank is populated yet -- if it's empty, seeding.start_auto_seed_if_empty()'s own
completion calls invalidate() again once there's real data to reflect on), after every
POST /seed, after every POST /reset, and after POST /feedback / POST /resolve change
the structured data the previous reflect_summary was about.
"""
from __future__ import annotations

import asyncio
import json
import logging

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
logger = logging.getLogger("recallops.insights")

_reflect_status: str = "pending"
_reflect_summary: str | None = None
_reflect_task: "asyncio.Task | None" = None


def _compute_facts() -> dict:
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
        recurring.append(
            {"service": incs[0]["service"], "title": signature.replace("_", " ").capitalize(), "recurrence": recurrence}
        )

    return {
        "patterns": patterns,
        "recurring": recurring,
        "open_permanent_fixes": incidents.compute_open_permanent_fixes(),
        "team_knowledge": incidents.compute_team_knowledge(),
        "fix_speed_comparison": incidents.compute_fix_speed_comparison(),
    }


async def _run_reflect() -> None:
    global _reflect_status, _reflect_summary
    try:
        context = json.dumps(_compute_facts(), default=str)
        summary = await memory.reflect(
            memory.BANK_INCIDENTS,
            query=(
                "Given these computed patterns, recurring incidents, open permanent "
                "fixes, team knowledge and fix-speed comparison, what should the team know?"
            ),
            context=context,
        )
        _reflect_summary = summary
        _reflect_status = "ready"
    except Exception as exc:
        logger.warning("background reflect failed: %s", type(exc).__name__)
        _reflect_summary = None
        _reflect_status = "failed"


def invalidate() -> None:
    """Clears the cached reflect result and restarts the background task. Call after
    anything that changes the structured data reflect summarizes: POST /seed,
    POST /reset, POST /feedback, POST /resolve, and once at app startup.

    Safe to call with no event loop running (e.g. sync test fixtures resetting module
    state between tests): reflect_status still resets to "pending", but the background
    task itself just doesn't start until the next call happens inside a running loop.
    """
    global _reflect_status, _reflect_summary, _reflect_task
    if _reflect_task is not None and not _reflect_task.done():
        _reflect_task.cancel()
    _reflect_status = "pending"
    _reflect_summary = None
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _reflect_task = None  # no loop running -- don't even construct the coroutine
        return
    _reflect_task = asyncio.create_task(_run_reflect())


# Earlier prompts' callers (and this module's own git history) named this clear_cache();
# kept as an alias since "clearing" now also means "restart the background reflect".
clear_cache = invalidate


@router.get("/insights", response_model=InsightsResponse)
async def get_insights() -> InsightsResponse:
    facts = _compute_facts()
    return InsightsResponse(
        patterns=[InsightPattern(**p) for p in facts["patterns"]],
        recurring=[
            RecurringInsight(service=r["service"], title=r["title"], recurrence=Recurrence(**r["recurrence"]))
            for r in facts["recurring"]
        ],
        open_permanent_fixes=[OpenPermanentFix(**f) for f in facts["open_permanent_fixes"]],
        team_knowledge=[TeamKnowledge(**t) for t in facts["team_knowledge"]],
        fix_speed_comparison=FixSpeedComparison(**facts["fix_speed_comparison"]),
        reflect_summary=_reflect_summary,
        reflect_status=_reflect_status,
    )
