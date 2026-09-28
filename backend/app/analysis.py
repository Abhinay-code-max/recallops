"""Pure alert-analysis pipeline: recall, memory_state, evidence, ranked_fixes, warnings,
team_hint, recurrence. No side effects whatsoever -- no incident storage, no retain, no
dedupe, no counters. Shared by routes/alert.py (which wraps this with dedupe + storage +
retain) and routes/compare.py's with_memory path (which must have NO side effects at
all, per Prompt 4 item 1) and routes/chat.py (which needs the same evidence shape).

NO_MATCH_THRESHOLD -- calibrated live, not guessed (scripts/calibrate_similarity.py):
the 5 demo alerts' best relevance ranged 0.42-1.07; 3 unrelated nonsense alerts ranged
0.0007-0.0076. NO_MATCH_THRESHOLD=0.05 sits with a large margin on both sides.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app import incidents, ledger, memory, scoring

NO_MATCH_THRESHOLD = 0.05
EVIDENCE_LIMIT = 6
RECALL_TOP_N = 8


def relative_time(from_iso: str | None, to_iso: str | None) -> str:
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


def excerpt(incident: dict[str, Any], limit: int = 160) -> str:
    text = incident.get("symptoms") or incident.get("title") or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_evidence(hits: list[memory.RecallHit], submitted_at: str | None) -> list[dict[str, Any]]:
    """Returns plain dicts shaped like the Evidence contract type -- callers wrap in
    models.Evidence."""
    evidence: list[dict[str, Any]] = []
    for hit in hits[:EVIDENCE_LIMIT]:
        incident = incidents.get_incident(hit.incident_id)
        if incident is None:
            continue
        source_bank = memory.BANK_INCIDENTS if memory.get_seed_incident(hit.incident_id) else memory.BANK_LIVE
        evidence.append(
            {
                "incident_id": hit.incident_id,
                "date": incident.get("date"),
                "relative": relative_time(submitted_at, incident.get("date")),
                "service": incident.get("service"),
                "severity": incident.get("severity"),
                "excerpt": excerpt(incident),
                "relevance": round(scoring.normalize_similarity(hit.relevance or 0.0), 4),
                "source_bank": source_bank,
            }
        )
    return evidence


@dataclass
class AlertAnalysis:
    memory_state: str
    hits: list[memory.RecallHit]
    evidence: list[dict[str, Any]]
    ranked_fixes: list[scoring.RankedFix]
    warnings: list[dict[str, Any]]
    team_hint: dict[str, Any] | None
    recurrence: dict[str, Any] | None
    degraded: bool
    degraded_reason: str | None = None


async def analyze_alert(alert_dict: dict[str, Any]) -> AlertAnalysis:
    ledger_data = ledger.read_ledger()
    query = incidents.alert_query(alert_dict)
    outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query, max_tokens=4096)
    hits = outcome.hits[:RECALL_TOP_N]
    degraded = outcome.degraded
    degraded_reason = "memory unavailable or slow" if degraded else None

    best_relevance = max((h.relevance or 0.0 for h in hits), default=0.0)
    if ledger_data is None or ledger_data["totals"]["incidents"] == 0:
        memory_state = "empty"
    elif best_relevance < NO_MATCH_THRESHOLD:
        memory_state = "no_match"
    else:
        memory_state = "matched"

    evidence = build_evidence(hits, alert_dict.get("submitted_at")) if memory_state == "matched" else []

    ranked_fixes: list[scoring.RankedFix] = []
    warnings: list[dict[str, Any]] = []
    team_hint: dict[str, Any] | None = None
    recurrence: dict[str, Any] | None = None

    if memory_state == "matched" and hits:
        top_incident_id = incidents.first_resolvable([h.incident_id for h in hits])
        if top_incident_id is not None:
            pool = incidents.pattern_pool(top_incident_id)
            if ledger_data is not None:
                counts = incidents.ledger_counts_for(top_incident_id, ledger_data)
                ranked_fixes = scoring.rank_fixes(hits, pool, counts)
            recurrence = incidents.compute_recurrence(pool)
            team_hint = incidents.compute_team_hint(pool)
            warnings = incidents.build_warnings(ranked_fixes, pool, recurrence)

    return AlertAnalysis(
        memory_state=memory_state,
        hits=hits,
        evidence=evidence,
        ranked_fixes=ranked_fixes,
        warnings=warnings,
        team_hint=team_hint,
        recurrence=recurrence,
        degraded=degraded,
        degraded_reason=degraded_reason,
    )
